import sys
from pathlib import Path
import pytest

scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from regression_gate import (
    bootstrap_mean_diff_ci,
    evaluate_ci_regression_gate,
    welch_t_test,
)


def test_welch_t_test_detects_clear_shift_and_identical_distributions():
    baseline = [10000.0, 10120.0, 9950.0, 10080.0, 10010.0, 9990.0]
    regressed = [8900.0, 9050.0, 8980.0, 9010.0, 8950.0, 9020.0]

    res = welch_t_test(baseline, regressed)
    assert res["pct_change"] < -9.0
    assert res["p_value"] < 0.001
    assert res["cohens_d"] < -5.0

    same = welch_t_test(baseline, baseline)
    assert same["t_statistic"] == 0.0
    assert same["p_value"] == 1.0
    assert same["cohens_d"] == 0.0


def test_ci_regression_gate_distinguishes_regression_improvement_and_noise():
    # Clear RPS regression (higher_is_better=True)
    base_rps = [50000, 50400, 49800, 50100, 50200, 49900]
    slow_rps = [44000, 44300, 43900, 44100, 44200, 44050]
    gate_reg = evaluate_ci_regression_gate(base_rps, slow_rps, min_regression_pct=5.0, alpha=0.05)
    assert gate_reg["verdict"] == "REGRESSION"
    assert gate_reg["statistically_significant"] is True
    assert gate_reg["bootstrap_ci"]["excludes_zero"] is True

    # Clear latency improvement (higher_is_better=False: latency dropped 15ms -> 10ms)
    base_lat = [15.1, 14.9, 15.2, 15.0, 14.8, 15.1]
    fast_lat = [10.1, 9.9, 10.2, 10.0, 9.8, 10.1]
    gate_imp = evaluate_ci_regression_gate(
        base_lat, fast_lat, min_regression_pct=5.0, alpha=0.05, higher_is_better=False
    )
    assert gate_imp["verdict"] == "IMPROVEMENT"
    assert gate_imp["statistically_significant"] is True

    # High-variance noisy samples whose mean dropped >5% but NOT statistically significant
    noisy_base = [100.0, 140.0, 80.0, 120.0, 90.0]
    noisy_cand = [70.0, 135.0, 75.0, 115.0, 95.0]
    gate_noise = evaluate_ci_regression_gate(noisy_base, noisy_cand, min_regression_pct=5.0, alpha=0.05)
    assert gate_noise["verdict"] in ("NOISE_INCONCLUSIVE", "PASS")
    assert gate_noise["statistically_significant"] is False


def test_regression_gate_validates_minimum_samples():
    with pytest.raises(ValueError):
        welch_t_test([100.0], [90.0, 85.0])
    with pytest.raises(ValueError):
        bootstrap_mean_diff_ci([100.0, 101.0], [float("nan")])
