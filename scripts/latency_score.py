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
    m = re.match(r"^(\d+(?:\.\d*)?|\.\d+)\s*(ns|us|µs|μs|ms|s|m)?$", val_str)
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    if not math.isfinite(v) or v < 0:
        return None
    mult = {
        "ns": 1e-3,
        "us": 1.0,
        "µs": 1.0,
        "μs": 1.0,
        "ms": 1e3,
        "s": 1e6,
        "m": 60e6,
        None: 1.0,
    }
    return v * mult[m.group(2)]


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

    w_cpu = _positive_finite(weights[0]) if len(weights) > 0 else W_CPU
    w_p99 = _positive_finite(weights[1]) if len(weights) > 1 else W_P99
    w_mean = _positive_finite(weights[2]) if len(weights) > 2 else W_MEAN
    w_cpu = w_cpu if w_cpu is not None else W_CPU
    w_p99 = w_p99 if w_p99 is not None else W_P99
    w_mean = w_mean if w_mean is not None else W_MEAN

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
        r["score"] = 100.0 * rf * (w_cpu * cpu_s + w_p99 * p99_s + w_mean * mean_s)
    return rows


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
