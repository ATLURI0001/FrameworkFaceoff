#!/usr/bin/env python3
"""Scoring for the fixed-rate profiles: `latency-1m`, `latency-10k`,
`latency-500k-8cpu` and `8gbit`.

Every other profile here ranks on one number, requests per second. This one
cannot: the rate is pinned, so every entry that finishes serves the same load
and the interesting differences are in what it cost and how the tail behaved.

The score is

    rateFactor = min(1, achieved_rps / 950_000)
    quality    = 0.50*cpuScore + 0.25*p99Score + 0.25*meanScore
    score      = 100 * rateFactor * quality

with, against the best value present in the field:

    cpuScore   = bestCpu / cpu                       (linear)
    p99Score   = 1 - log10(p99  / bestP99 ) / 3      (clamped to 0..1)
    meanScore  = 1 - log10(mean / bestMean)          (clamped to 0..1)

Why the three shapes differ. CPU per request spans about 3.3x across the
entries that hold the rate, so a plain ratio behaves well over it. The p99 tail
spans five orders of magnitude - 151us to 7.6s among rate-holders - and a plain
ratio there collapses to near zero for everything but the leader, spending the
weight without separating anybody; a three-decade scale keeps the field
distinguishable while still charging for a bad tail: ten times the best costs a
third of the term, a thousand times costs all of it.

The mean is the queueing signal. By Little's law it is the number of requests
in flight divided by the rate, so a server that lets requests wait to amortise
its wake-ups shows it here and nowhere else: among entries that answer without
queueing it spans about 2x, and a mean ten times the best means a request spends
nine tenths of its life waiting. That is worth nothing, hence one decade.

p99.9 used to hold the third slot and is still recorded, but no longer scored:
one stall in a twenty-second run moves it a hundredfold (a 166us p99 next to a
25ms p99.9), which at the weight it carried was noise deciding ranks.

The decade spans are fixed rather than derived from the worst entry on purpose,
so one pathological entry joining the board cannot move everybody else's score.
For the same reason nothing is rescaled to make the leader exactly 100: the top
entry scores in the low-to-mid 90s because no single entry is simultaneously
best on cost and on both tails, and that gap is information.

Two modes:

    latency_score.py --pick <dir> [--profile P]   best of N runs (benchmark.sh)
    latency_score.py --table [--profile P]        score the published results
"""

from __future__ import annotations
import argparse
import json
import math
import re
import sys
from pathlib import Path

# Full credit at 95% of what was offered. The generator never quite reaches its
# target -- ~998K against 1M is a clean run -- so the threshold has to sit below
# it or nobody would ever earn the whole factor.
FULL_RATE = {
    "latency-1m":  950_000.0,
    "latency-10k":   9_500.0,
    # Four cores plus SMT at 500K: 95% of the target, like the others.
    "latency-500k-8cpu": 475_000.0,
    # 8gbit is paced too, so it scores the same way: 95% of its 50K target.
    # Keep in step with LAT_FULL in site/leaderboard/index.html - check_badge_parity.js
    # compares the two and fails the deploy when they disagree.
    "8gbit":     47_500.0,
}
DEFAULT_PROFILE = "latency-1m"
W_CPU, W_P99, W_MEAN = 0.50, 0.25, 0.25
DECADES = 3.0        # p99: a third of the term per decade above the best
MEAN_DECADES = 1.0   # mean: ten times the best is zero


def to_us(value) -> float | None:
    """'173.0us' / '1.5ms' / '2s' -> microseconds. None when unparseable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        fval = float(value)
        return fval if math.isfinite(fval) and fval >= 0 else None
    val_str = str(value).strip().replace(",", "").replace("_", "")
    m = re.match(r"^(\d+(?:\.\d*)?|\.\d+)\s*(ns|us|µs|μs|ms|s|sec|secs|second|seconds|m|min|mins)?$", val_str, re.IGNORECASE)
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    if not math.isfinite(v) or v < 0:
        return None
    unit = (m.group(2) or "").lower()
    mult = {
        "ns": 1e-3,
        "us": 1.0,
        "µs": 1.0,
        "μs": 1.0,
        "ms": 1e3,
        "s": 1e6,
        "sec": 1e6,
        "secs": 1e6,
        "second": 1e6,
        "seconds": 1e6,
        "m": 60e6,
        "min": 60e6,
        "mins": 60e6,
        "": 1.0,
    }
    return v * mult.get(unit, 1.0)


def _clamp(v: float) -> float:
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
        return 0.0
    return 0.0 if v < 0 else 1.0 if v > 1 else float(v)


def _positive_finite(v) -> float | None:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    fv = float(v)
    return fv if math.isfinite(fv) and fv > 0 else None


def rate_factor(rps: float, full: float) -> float:
    if not isinstance(rps, (int, float)) or isinstance(rps, bool) or not math.isfinite(rps):
        return 0.0
    full_val = _positive_finite(full)
    if full_val is None:
        return 0.0
    return _clamp(float(rps) / full_val)


def decade_score(value: float | None, best: float | None,
                 decades: float = DECADES) -> float:
    """1.0 at the best value, falling to 0 over `decades` decades above it."""
    val = _positive_finite(value)
    best_val = _positive_finite(best)
    dec_val = _positive_finite(decades)
    if val is None or best_val is None or dec_val is None:
        return 0.0
    return _clamp(1.0 - math.log10(max(val, best_val) / best_val) / dec_val)


def linear_score(value: float | None, best: float | None) -> float:
    val = _positive_finite(value)
    best_val = _positive_finite(best)
    if val is None or best_val is None:
        return 0.0
    return _clamp(best_val / val)


def normalize_weights(weights: tuple[float, float, float] | list[float] | None = None) -> tuple[float, float, float]:
    """Normalize 3-element scoring weights to sum to 1.0. Defaults to (W_CPU, W_P99, W_MEAN)."""
    if not weights or len(weights) < 3:
        return (W_CPU, W_P99, W_MEAN)
    w_cpu = _positive_finite(weights[0])
    w_p99 = _positive_finite(weights[1])
    w_mean = _positive_finite(weights[2])
    if w_cpu is None or w_p99 is None or w_mean is None:
        return (W_CPU, W_P99, W_MEAN)
    total = w_cpu + w_p99 + w_mean
    if total <= 0:
        return (W_CPU, W_P99, W_MEAN)
    return (w_cpu / total, w_p99 / total, w_mean / total)


def format_score_summary(row: dict) -> str:
    """Format row scoring metrics into a concise single-line diagnostic."""
    if not isinstance(row, dict):
        return "invalid_row"
    fw = str(row.get("framework") or row.get("fw") or "unknown")
    score = float(row.get("score") or 0.0)
    rf = float(row.get("rateFactor") or 0.0)
    cpu_s = float(row.get("cpuScore") or 0.0)
    p99_s = float(row.get("p99Score") or 0.0)
    mean_s = float(row.get("meanScore") or 0.0)
    return f"{fw}: score={score:.1f} (rateFactor={rf:.3f}, cpuScore={cpu_s:.2f}, p99Score={p99_s:.2f}, meanScore={mean_s:.2f})"


def score_rows(
    rows: list[dict],
    profile: str = DEFAULT_PROFILE,
    weights: tuple[float, float, float] = (W_CPU, W_P99, W_MEAN),
) -> list[dict]:
    """Annotate rows with their score. Each row needs rps, cpu, p99, mean.

    Bests are taken over the rows given, so a caller scoring one framework's
    three runs gets them normalised against each other, and a caller scoring the
    board gets them normalised against the field.
    """
    if profile not in FULL_RATE:
        raise ValueError(f"Unknown profile: {profile!r}")

    w_cpu, w_p99, w_mean = normalize_weights(weights)

    def best_of(key):
        vals = [
            float(r[key])
            for r in rows
            if isinstance(r, dict)
            and isinstance(r.get(key), (int, float))
            and not isinstance(r.get(key), bool)
            and math.isfinite(r[key])
            and r[key] > 0
        ]
        return min(vals) if vals else None

    b_cpu, b_p99, b_mean = best_of("cpu"), best_of("p99"), best_of("mean")
    full = FULL_RATE[profile]
    for r in rows:
        if not isinstance(r, dict):
            continue
        rf = rate_factor(r.get("rps") or 0, full)
        cpu_s = linear_score(r.get("cpu"), b_cpu)
        p99_s = decade_score(r.get("p99"), b_p99)
        mean_s = decade_score(r.get("mean"), b_mean, MEAN_DECADES)
        r["rateFactor"] = rf
        r["cpuScore"], r["p99Score"], r["meanScore"] = cpu_s, p99_s, mean_s
        score = 100.0 * rf * (w_cpu * cpu_s + w_p99 * p99_s + w_mean * mean_s)
        r["score"] = max(0.0, min(100.0, score))
    return rows


def from_us(us: float | None, unit: str = "ms") -> str:
    """Format microseconds back to human-readable string with units (us, ms, s)."""
    if us is None or isinstance(us, bool) or not isinstance(us, (int, float)) or not math.isfinite(us) or us < 0:
        return "N/A"
    clean_unit = unit.lower().strip()
    if clean_unit in ("us", "µs", "μs"):
        return f"{us:.1f}us"
    elif clean_unit in ("s", "sec"):
        return f"{us / 1e6:.2f}s"
    return f"{us / 1e3:.2f}ms"


def rank_rows(rows: list[dict], reverse: bool = True) -> list[dict]:
    """Sort scored rows by score descending with tie-breaking on rps and p99, annotating 'rank'."""
    if not isinstance(rows, list):
        return []
    valid_rows = [r for r in rows if isinstance(r, dict)]
    sorted_rows = sorted(
        valid_rows,
        key=lambda r: (
            float(r.get("score") or 0.0),
            float(r.get("rps") or 0.0),
            -float(r.get("p99") or float("inf")),
        ),
        reverse=reverse,
    )
    for idx, r in enumerate(sorted_rows, start=1):
        r["rank"] = idx
    return sorted_rows


def compute_relative_deltas(rows: list[dict], baseline_framework: str) -> list[dict]:
    """Calculate percentage deltas in score, rps, and p99 relative to a baseline framework."""
    if not isinstance(rows, list) or not isinstance(baseline_framework, str):
        return []
    baseline = None
    for r in rows:
        if isinstance(r, dict) and r.get("framework") == baseline_framework:
            baseline = r
            break
    if not baseline:
        return rows

    b_score = float(baseline.get("score") or 0.0)
    b_rps = float(baseline.get("rps") or 0.0)
    b_p99 = float(baseline.get("p99") or 0.0)

    for r in rows:
        if not isinstance(r, dict):
            continue
        score = float(r.get("score") or 0.0)
        rps = float(r.get("rps") or 0.0)
        p99 = float(r.get("p99") or 0.0)

        r["deltaScorePct"] = round(((score - b_score) / b_score) * 100.0, 2) if b_score > 0 else 0.0
        r["deltaRpsPct"] = round(((rps - b_rps) / b_rps) * 100.0, 2) if b_rps > 0 else 0.0
        r["deltaP99Pct"] = round(((p99 - b_p99) / b_p99) * 100.0, 2) if b_p99 > 0 else 0.0

    return rows


def export_summary_json(rows: list[dict]) -> dict:
    """Export summary metrics including total count, top performer, and score percentiles."""
    if not isinstance(rows, list):
        return {"count": 0, "topFramework": None, "medianScore": 0.0, "maxScore": 0.0}
    valid = [r for r in rows if isinstance(r, dict) and isinstance(r.get("score"), (int, float))]
    if not valid:
        return {"count": 0, "topFramework": None, "medianScore": 0.0, "maxScore": 0.0}

    scores = sorted(float(r["score"]) for r in valid)
    n = len(scores)
    median = (scores[n // 2] if n % 2 != 0 else (scores[n // 2 - 1] + scores[n // 2]) / 2.0)
    top_row = max(valid, key=lambda r: float(r.get("score") or 0.0))

    return {
        "count": len(valid),
        "topFramework": top_row.get("framework"),
        "maxScore": round(float(top_row.get("score") or 0.0), 2),
        "medianScore": round(median, 2),
    }


def compute_efficiency_ratio(cpu_us: float | None, rps: float | None) -> float | None:
    """Calculate throughput efficiency as requests per second per CPU microsecond."""
    if cpu_us is None or rps is None or isinstance(cpu_us, bool) or isinstance(rps, bool):
        return None
    if not isinstance(cpu_us, (int, float)) or not isinstance(rps, (int, float)):
        return None
    if not math.isfinite(cpu_us) or not math.isfinite(rps) or cpu_us <= 0 or rps <= 0:
        return None
    return round(float(rps) / float(cpu_us), 2)


def filter_top_tier(rows: list[dict], min_score: float = 80.0, max_p99_us: float | None = None) -> list[dict]:
    """Filter rows meeting minimum quality score and optional tail latency SLA ceiling."""
    if not isinstance(rows, list):
        return []
    if not isinstance(min_score, (int, float)) or isinstance(min_score, bool) or not math.isfinite(min_score):
        min_score = 80.0
    min_score = max(0.0, min(100.0, float(min_score)))

    max_p99 = None
    if max_p99_us is not None and isinstance(max_p99_us, (int, float)) and not isinstance(max_p99_us, bool) and math.isfinite(max_p99_us) and max_p99_us > 0:
        max_p99 = float(max_p99_us)

    filtered = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        score = float(r.get("score") or 0.0)
        if score < min_score:
            continue
        if max_p99 is not None:
            p99 = r.get("p99")
            if p99 is None or float(p99) > max_p99:
                continue
        filtered.append(r)
    return filtered


def format_markdown_leaderboard(rows: list[dict], max_entries: int = 10) -> str:
    """Format scored framework rows into a clean GitHub Flavored Markdown table."""
    header = [
        "| Rank | Framework | Score | RPS | Mean Latency | p99 Latency |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    if not isinstance(rows, list) or not rows:
        return "\n".join(header) + "\n"
    if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries <= 0:
        max_entries = 10

    lines = list(header)
    for r in rows[:max_entries]:
        if not isinstance(r, dict):
            continue
        rank = str(r.get("rank", "-"))
        fw = str(r.get("framework") or r.get("fw") or "unknown")
        score = f"{float(r['score']):.1f}" if isinstance(r.get("score"), (int, float)) else "-"
        rps = f"{float(r['rps']):,.0f}" if isinstance(r.get("rps"), (int, float)) else "-"
        mean = f"{float(r['mean']):.1f}µs" if isinstance(r.get("mean"), (int, float)) else "-"
        p99 = f"{float(r['p99']):.1f}µs" if isinstance(r.get("p99"), (int, float)) else "-"
        lines.append(f"| {rank} | {fw} | {score} | {rps} | {mean} | {p99} |")
    return "\n".join(lines) + "\n"


def _kv(path: Path) -> dict:
    out = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def pick(dirpath: str | Path, profile: str = DEFAULT_PROFILE) -> int | None:
    """Best of the runs recorded under dirpath. Prints nothing on failure."""
    d = Path(dirpath)
    if not d.is_dir():
        return None
    rows = []
    for kv_file in sorted(d.glob("*.kv")):
        n = kv_file.stem
        if not n.isdigit():
            continue
        kv = _kv(kv_file)
        meta = _kv(d / f"{n}.meta") if (d / f"{n}.meta").exists() else {}
        try:
            reqs = float(kv.get("status_2xx") or 0)
            cpu_usec = float(meta.get("cpu_usec") or 0)
        except ValueError:
            reqs = cpu_usec = 0.0
        try:
            rps = float(kv.get("rps") or 0)
            if not math.isfinite(rps) or rps < 0:
                rps = 0.0
        except ValueError:
            rps = 0.0
        rows.append({
            "run": int(n),
            "rps": rps,
            # Per-request CPU, which is what the published metric is. Falls back
            # to None when the cgroup read failed, and linear_score treats that
            # as zero rather than as free.
            "cpu": (cpu_usec / reqs) if (reqs > 0 and cpu_usec > 0 and math.isfinite(reqs) and math.isfinite(cpu_usec)) else None,
            "p99": to_us(kv.get("p99_lat")),
            "mean": to_us(kv.get("avg_lat")),
        })
    if not rows:
        return None
    score_rows(rows, profile)
    return max(rows, key=lambda r: (r["score"], r["rps"], -r["run"]))["run"]


def table(results_dir: Path, profile: str = DEFAULT_PROFILE) -> None:
    rows = []
    for f in sorted(results_dir.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for key, r in (d.get("results") or {}).items():
            if not key.startswith(profile + "-"):
                continue
            rows.append({
                "fw": d.get("framework", f.stem),
                "rps": r.get("rps") or 0,
                "cpu": r.get("cpu_per_req_us"),
                "p99": to_us(r.get("p99_latency")),
                "mean": to_us(r.get("avg_latency")),
            })
    if not rows:
        print(f"no {profile} results found", file=sys.stderr)
        return
    score_rows(rows, profile)
    rows.sort(key=lambda r: -r["score"])
    print("%-24s %7s %7s %9s %11s %11s" %
          ("framework", "score", "rate", "us/req", "mean", "p99"))
    for r in rows:
        print("%-24s %7.1f %7.3f %9s %11s %11s" % (
            r["fw"], r["score"], r["rateFactor"],
            "-" if r["cpu"] is None else f"{r['cpu']:.1f}",
            "-" if r["mean"] is None else f"{r['mean']:.0f}",
            "-" if r["p99"] is None else f"{r['p99']:.0f}"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pick", metavar="DIR", help="print the winning run number")
    ap.add_argument("--table", action="store_true", help="score published results")
    ap.add_argument("--results", default=None, help="results dir for --table")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, choices=sorted(FULL_RATE),
                    help="which fixed-rate profile to score")
    a = ap.parse_args()
    if a.pick:
        w = pick(a.pick, a.profile)
        if w is None:
            return 1
        print(w)
        return 0
    if a.table:
        root = Path(__file__).resolve().parent.parent
        table(Path(a.results) if a.results else root / "site" / "data" / "results", a.profile)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
