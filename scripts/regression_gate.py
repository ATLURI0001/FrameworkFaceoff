"""Statistical CI benchmark regression gate using Welch's t-test and non-parametric bootstrap CI.

Zero external dependencies: computes exact Welch-Satterthwaite two-tailed p-values via
regularized incomplete beta function (Lentz's continued fraction) so CI runners can
reliably distinguish genuine performance regressions from measurement noise.
"""

from __future__ import annotations

import math
import random
from typing import Iterable


def _clean_samples(values: Iterable[float]) -> list[float]:
    if values is None:
        return []
    out: list[float] = []
    for v in values:
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            out.append(float(v))
    return out


def _betacf(a: float, b: float, x: float, max_iter: int = 200, eps: float = 3e-12) -> float:
    """Evaluate continued fraction for incomplete beta function via modified Lentz's method."""
    fpmin = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """Compute regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _student_t_two_tailed_p(t_stat: float, df: float) -> float:
    """Compute exact two-tailed p-value for Student's t distribution."""
    if not math.isfinite(t_stat) or df <= 0.0:
        return 1.0
    if t_stat == 0.0:
        return 1.0
    x = df / (df + t_stat * t_stat)
    return max(0.0, min(1.0, _regularized_incomplete_beta(df / 2.0, 0.5, x)))


def welch_t_test(baseline: Iterable[float], candidate: Iterable[float]) -> dict:
    """Run unequal-variance Welch's t-test and compute Cohen's d effect size."""
    b = _clean_samples(baseline)
    c = _clean_samples(candidate)
    n1, n2 = len(b), len(c)
    if n1 < 2 or n2 < 2:
        raise ValueError("Both baseline and candidate require at least 2 finite samples")

    m1 = sum(b) / n1
    m2 = sum(c) / n2
    v1 = sum((x - m1) ** 2 for x in b) / (n1 - 1)
    v2 = sum((x - m2) ** 2 for x in c) / (n2 - 1)

    se_sq = v1 / n1 + v2 / n2
    diff = m2 - m1
    pct_change = ((diff / m1) * 100.0) if m1 != 0.0 else 0.0

    pooled_std = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    cohens_d = (diff / pooled_std) if pooled_std > 0.0 else (0.0 if diff == 0.0 else math.copysign(math.inf, diff))

    if se_sq == 0.0:
        t_stat = 0.0 if diff == 0.0 else math.copysign(math.inf, diff)
        p_val = 1.0 if diff == 0.0 else 0.0
        df = float(n1 + n2 - 2)
    else:
        t_stat = diff / math.sqrt(se_sq)
        denom = ((v1 / n1) ** 2) / (n1 - 1) + ((v2 / n2) ** 2) / (n2 - 1)
        df = (se_sq * se_sq) / denom if denom > 0.0 else float(n1 + n2 - 2)
        p_val = _student_t_two_tailed_p(t_stat, df)

    return {
        "baseline_mean": round(m1, 4),
        "candidate_mean": round(m2, 4),
        "mean_diff": round(diff, 4),
        "pct_change": round(pct_change, 3),
        "t_statistic": round(t_stat, 4) if math.isfinite(t_stat) else t_stat,
        "degrees_of_freedom": round(df, 2),
        "p_value": round(p_val, 6),
        "cohens_d": round(cohens_d, 4) if math.isfinite(cohens_d) else cohens_d,
    }


def bootstrap_mean_diff_ci(
    baseline: Iterable[float],
    candidate: Iterable[float],
    *,
    n_resamples: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict:
    """Compute deterministic non-parametric bootstrap percentile CI for (candidate_mean - baseline_mean)."""
    b = _clean_samples(baseline)
    c = _clean_samples(candidate)
    if len(b) < 2 or len(c) < 2:
        raise ValueError("Both baseline and candidate require at least 2 finite samples")
    n_resamples = max(100, min(20_000, int(n_resamples)))
    confidence = max(0.5, min(0.999, float(confidence)))

    rng = random.Random(seed)
    n1, n2 = len(b), len(c)
    diffs: list[float] = []
    for _ in range(n_resamples):
        m1 = sum(b[rng.randrange(n1)] for _ in range(n1)) / n1
        m2 = sum(c[rng.randrange(n2)] for _ in range(n2)) / n2
        diffs.append(m2 - m1)
    diffs.sort()

    alpha = 1.0 - confidence
    lo_idx = max(0, int(math.floor((alpha / 2.0) * n_resamples)))
    hi_idx = min(n_resamples - 1, int(math.ceil((1.0 - alpha / 2.0) * n_resamples)) - 1)
    lower, upper = diffs[lo_idx], diffs[hi_idx]

    return {
        "lower": round(lower, 4),
        "upper": round(upper, 4),
        "confidence": confidence,
        "excludes_zero": (lower > 0.0) or (upper < 0.0),
    }


def evaluate_ci_regression_gate(
    baseline: Iterable[float],
    candidate: Iterable[float],
    *,
    min_regression_pct: float = 5.0,
    alpha: float = 0.05,
    higher_is_better: bool = True,
    n_resamples: int = 1000,
    seed: int = 42,
) -> dict:
    """Classify benchmark delta into PASS, IMPROVEMENT, REGRESSION, or NOISE_INCONCLUSIVE."""
    welch = welch_t_test(baseline, candidate)
    boot = bootstrap_mean_diff_ci(
        baseline, candidate, n_resamples=n_resamples, confidence=1.0 - alpha, seed=seed
    )

    pct = welch["pct_change"]
    statistically_significant = welch["p_value"] < alpha and boot["excludes_zero"]
    is_worse = (pct < -abs(min_regression_pct)) if higher_is_better else (pct > abs(min_regression_pct))
    is_better = (pct > abs(min_regression_pct)) if higher_is_better else (pct < -abs(min_regression_pct))

    if statistically_significant and is_worse:
        verdict = "REGRESSION"
    elif statistically_significant and is_better:
        verdict = "IMPROVEMENT"
    elif (is_worse or is_better) and not statistically_significant:
        verdict = "NOISE_INCONCLUSIVE"
    else:
        verdict = "PASS"

    return {
        "verdict": verdict,
        "statistically_significant": statistically_significant,
        "welch": welch,
        "bootstrap_ci": boot,
    }
