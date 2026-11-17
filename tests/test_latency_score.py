import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from latency_score import (
    to_us,
    _clamp,
    _kv,
    rate_factor,
    decade_score,
    linear_score,
    score_rows,
    pick,
    normalize_weights,
    format_score_summary,
    from_us,
    rank_rows,
    compute_relative_deltas,
    export_summary_json,
    compute_efficiency_ratio,
    filter_top_tier,
    format_markdown_leaderboard,
    FULL_RATE,
    DEFAULT_PROFILE,
)


class TestLatencyScore(unittest.TestCase):
    def test_to_us_parsing(self):
        # Numeric passthrough
        self.assertIsNone(to_us(None))
        self.assertEqual(to_us(150), 150.0)
        self.assertEqual(to_us(250.5), 250.5)

        # Microseconds
        self.assertAlmostEqual(to_us("173.0us"), 173.0)
        self.assertAlmostEqual(to_us("  50us "), 50.0)
        self.assertAlmostEqual(to_us("120µs"), 120.0)  # micro sign
        self.assertAlmostEqual(to_us("120μs"), 120.0)  # Greek mu

        # Milliseconds
        self.assertAlmostEqual(to_us("1.5ms"), 1500.0)
        self.assertAlmostEqual(to_us("0.05ms"), 50.0)

        # Seconds and minutes
        self.assertAlmostEqual(to_us("2s"), 2000000.0)
        self.assertAlmostEqual(to_us("0.001s"), 1000.0)
        self.assertAlmostEqual(to_us("1m"), 60000000.0)

        # Nanoseconds
        self.assertAlmostEqual(to_us("500ns"), 0.5)
        self.assertAlmostEqual(to_us("1000ns"), 1.0)

        # Plain number string with no unit defaults to us
        self.assertAlmostEqual(to_us("42"), 42.0)

        # Invalid formats
        self.assertIsNone(to_us("unparseable"))
        self.assertIsNone(to_us("123abc"))
        self.assertIsNone(to_us(""))

    def test_clamp(self):
        self.assertEqual(_clamp(-0.5), 0.0)
        self.assertEqual(_clamp(0.0), 0.0)
        self.assertEqual(_clamp(0.42), 0.42)
        self.assertEqual(_clamp(1.0), 1.0)
        self.assertEqual(_clamp(1.5), 1.0)

    def test_rate_factor(self):
        full = FULL_RATE["latency-1m"]  # 950,000.0
        self.assertEqual(rate_factor(0, full), 0.0)
        self.assertAlmostEqual(rate_factor(475_000, full), 0.5)
        self.assertEqual(rate_factor(950_000, full), 1.0)
        self.assertEqual(rate_factor(1_000_000, full), 1.0)  # clamped to 1.0

    def test_linear_score(self):
        # Exactly best
        self.assertEqual(linear_score(10.0, 10.0), 1.0)
        # Double the CPU usage => half the score
        self.assertAlmostEqual(linear_score(20.0, 10.0), 0.5)
        # Better than best (e.g. outlier or clamped)
        self.assertEqual(linear_score(5.0, 10.0), 1.0)
        # Invalid / missing / zero values
        self.assertEqual(linear_score(None, 10.0), 0.0)
        self.assertEqual(linear_score(10.0, None), 0.0)
        self.assertEqual(linear_score(0.0, 10.0), 0.0)
        self.assertEqual(linear_score(10.0, 0.0), 0.0)
        self.assertEqual(linear_score(-5.0, 10.0), 0.0)

    def test_decade_score(self):
        best = 100.0  # 100 us
        # Exactly best
        self.assertEqual(decade_score(best, best, decades=3.0), 1.0)

        # 1 decade above best (1000 us vs 100 us) with decades=3.0 -> 1 - 1/3 = 2/3
        self.assertAlmostEqual(decade_score(1000.0, best, decades=3.0), 2.0 / 3.0)

        # 2 decades above best (10,000 us) -> 1 - 2/3 = 1/3
        self.assertAlmostEqual(decade_score(10_000.0, best, decades=3.0), 1.0 / 3.0)

        # 3 decades above best (100,000 us) -> 1 - 3/3 = 0.0
        self.assertAlmostEqual(decade_score(100_000.0, best, decades=3.0), 0.0)

        # 4 decades above best (1,000,000 us) -> clamped to 0.0
        self.assertEqual(decade_score(1_000_000.0, best, decades=3.0), 0.0)

        # Value better than best (should be 1.0)
        self.assertEqual(decade_score(50.0, best, decades=3.0), 1.0)

        # 1 decade above best with decades=1.0 (meanScore behavior)
        self.assertAlmostEqual(decade_score(1000.0, best, decades=1.0), 0.0)

        # Invalid or non-positive
        self.assertEqual(decade_score(None, best), 0.0)
        self.assertEqual(decade_score(best, None), 0.0)
        self.assertEqual(decade_score(0, best), 0.0)
        self.assertEqual(decade_score(best, 0), 0.0)
        self.assertEqual(decade_score(best, best, decades=0), 0.0)

    def test_score_rows(self):
        rows = [
            {"rps": 950_000, "cpu": 1.0, "p99": 200.0, "mean": 100.0},
            {"rps": 950_000, "cpu": 2.0, "p99": 2000.0, "mean": 1000.0},
            {"rps": 475_000, "cpu": 1.0, "p99": 200.0, "mean": 100.0},
        ]
        scored = score_rows(rows, profile="latency-1m")

        # Row 0 has best in everything and full rate -> score should be 100.0
        self.assertAlmostEqual(scored[0]["rateFactor"], 1.0)
        self.assertAlmostEqual(scored[0]["cpuScore"], 1.0)
        self.assertAlmostEqual(scored[0]["p99Score"], 1.0)
        self.assertAlmostEqual(scored[0]["meanScore"], 1.0)
        self.assertAlmostEqual(scored[0]["score"], 100.0)

        # Row 1 has full rate, but cpu=2.0 (score 0.5), p99=2000 (score 2/3), mean=1000 (score 0)
        # quality = 0.5*0.5 + 0.25*(2/3) + 0.25*0 = 0.25 + 0.166666... = 0.416666...
        # score = 100 * 1.0 * 0.416666... ≈ 41.67
        self.assertAlmostEqual(scored[1]["rateFactor"], 1.0)
        self.assertAlmostEqual(scored[1]["cpuScore"], 0.5)
        self.assertAlmostEqual(scored[1]["score"], 100.0 * (0.5 * 0.5 + 0.25 * (2.0 / 3.0)))

        # Row 2 has best metrics, but half rate factor (0.5)
        self.assertAlmostEqual(scored[2]["rateFactor"], 0.5)
        self.assertAlmostEqual(scored[2]["score"], 50.0)

    def test_pick_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Run 1: lower rps
            (tmppath / "1.kv").write_text("status_2xx=500000\nrps=500000\np99_lat=300us\navg_lat=150us\n")
            (tmppath / "1.meta").write_text("cpu_usec=500000\n")

            # Run 2: full rps, best metrics
            (tmppath / "2.kv").write_text("status_2xx=950000\nrps=950000\np99_lat=150us\navg_lat=80us\n")
            (tmppath / "2.meta").write_text("cpu_usec=475000\n")

            winning_run = pick(tmpdir, "latency-1m")
            self.assertEqual(winning_run, 2)

    def test_nan_boolean_and_negative_outlier_guards(self):
        self.assertIsNone(to_us(True))
        self.assertIsNone(to_us(float("nan")))
        self.assertIsNone(to_us(float("inf")))
        self.assertIsNone(to_us("1.2.3ms"))
        self.assertEqual(_clamp(float("nan")), 0.0)

        rows = [
            {"rps": 950_000, "cpu": -5.0, "p99": float("nan"), "mean": 100.0},
            {"rps": 950_000, "cpu": 1.0, "p99": 200.0, "mean": 100.0},
            {"rps": 950_000, "cpu": 2.0, "p99": 2000.0, "mean": 1000.0},
        ]
        scored = score_rows(rows, profile="latency-1m")
        # Negative/NaN corrupt row 0 must NOT poison best_of for valid row 1
        self.assertAlmostEqual(scored[1]["score"], 100.0)
        self.assertTrue(scored[2]["score"] > 0.0)

        # Boolean values must not be treated as numeric 1.0 in scoring helpers
        self.assertEqual(rate_factor(True, 950_000.0), 0.0)
        self.assertEqual(linear_score(True, 1.0), 0.0)
        self.assertEqual(decade_score(True, 1.0), 0.0)
        self.assertEqual(decade_score(100.0, float("nan")), 0.0)

        with self.assertRaises(ValueError):
            score_rows([{"rps": 1000}], profile="unknown-profile")

    def test_pick_handles_corrupt_rps_and_breaks_ties_deterministically(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "1.kv").write_text("status_2xx=100\nrps=not-a-number\n")
            (tmppath / "2.kv").write_text("status_2xx=500\nrps=950000\np99_lat=100us\navg_lat=50us\n")
            (tmppath / "2.meta").write_text("cpu_usec=250000\n")
            (tmppath / "10.kv").write_text("status_2xx=500\nrps=950000\np99_lat=100us\navg_lat=50us\n")
            (tmppath / "10.meta").write_text("cpu_usec=250000\n")

            # Run 1 has corrupt rps (handled without crashing); runs 2 and 10 tie -> lowest run number (2) wins
            self.assertEqual(pick(tmpdir, "latency-1m"), 2)

    def test_kv_parser_robustness(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            f = tmppath / "test.kv"
            f.write_text("# Comment line\n  rps = 950000 \ncpu_usec= 12345\n\n# another comment\nstatus_2xx=950000\n", encoding="utf-8")
            res = _kv(f)
            self.assertEqual(res["rps"], "950000")
            self.assertEqual(res["cpu_usec"], "12345")
            self.assertEqual(res["status_2xx"], "950000")
            self.assertNotIn("#", res)

            # Non-existent path returns empty dict without throwing
            self.assertEqual(_kv(tmppath / "missing.kv"), {})

    def test_to_us_with_delimiters_and_negative_guards(self):
        self.assertAlmostEqual(to_us("1,500us"), 1500.0)
        self.assertAlmostEqual(to_us("1_000ms"), 1000000.0)
        self.assertIsNone(to_us(-10.0))
        self.assertIsNone(to_us("-50us"))

    def test_pick_non_directory_and_custom_weights(self):
        self.assertIsNone(pick("non_existent_dir_12345"))

        rows = [
            None,  # malformed row
            {"rps": 950_000, "cpu": 1.0, "p99": 200.0, "mean": 100.0},
        ]
        # Custom weights: 80% CPU, 10% p99, 10% mean
        scored = score_rows(rows, profile="latency-1m", weights=(0.8, 0.1, 0.1))
        self.assertAlmostEqual(scored[1]["score"], 100.0)

    def test_case_insensitive_units_and_variations(self):
        self.assertAlmostEqual(to_us("150 US"), 150.0)
        self.assertAlmostEqual(to_us("2.5 MS"), 2500.0)
        self.assertAlmostEqual(to_us("3 SEC"), 3000000.0)
        self.assertAlmostEqual(to_us("1.5 seconds"), 1500000.0)
        self.assertAlmostEqual(to_us("2 mins"), 120000000.0)
        self.assertAlmostEqual(to_us("500 NS"), 0.5)

    def test_normalize_weights(self):
        # Already normalized
        w = normalize_weights((0.5, 0.25, 0.25))
        self.assertAlmostEqual(w[0], 0.5)
        self.assertAlmostEqual(w[1], 0.25)
        self.assertAlmostEqual(w[2], 0.25)

        # Raw percentage integers (e.g. 50, 25, 25)
        w2 = normalize_weights((50.0, 25.0, 25.0))
        self.assertAlmostEqual(w2[0], 0.5)
        self.assertAlmostEqual(w2[1], 0.25)
        self.assertAlmostEqual(w2[2], 0.25)

        # Empty / invalid fallback
        self.assertEqual(normalize_weights(None), (0.5, 0.25, 0.25))
        self.assertEqual(normalize_weights((0, 0, 0)), (0.5, 0.25, 0.25))

    def test_format_score_summary(self):
        row = {
            "framework": "fastapi",
            "score": 87.54,
            "rateFactor": 1.0,
            "cpuScore": 0.85,
            "p99Score": 0.92,
            "meanScore": 0.88,
        }
        summary = format_score_summary(row)
        self.assertIn("fastapi: score=87.5", summary)
        self.assertIn("rateFactor=1.000", summary)
        self.assertIn("cpuScore=0.85", summary)
        self.assertEqual(format_score_summary(None), "invalid_row")

    def test_from_us_formatting(self):
        self.assertEqual(from_us(150.0, "us"), "150.0us")
        self.assertEqual(from_us(1500.0, "ms"), "1.50ms")
        self.assertEqual(from_us(2500000.0, "s"), "2.50s")
        self.assertEqual(from_us(None), "N/A")
        self.assertEqual(from_us(float("nan")), "N/A")
        self.assertEqual(from_us(-10.0), "N/A")

    def test_rank_rows(self):
        rows = [
            {"framework": "fw-b", "score": 80.0, "rps": 50000, "p99": 200},
            {"framework": "fw-a", "score": 92.5, "rps": 90000, "p99": 150},
            {"framework": "fw-c", "score": 80.0, "rps": 60000, "p99": 180},
        ]
        ranked = rank_rows(rows)
        self.assertEqual(ranked[0]["framework"], "fw-a")
        self.assertEqual(ranked[0]["rank"], 1)
        # fw-c beats fw-b on rps tie-break
        self.assertEqual(ranked[1]["framework"], "fw-c")
        self.assertEqual(ranked[1]["rank"], 2)
        self.assertEqual(ranked[2]["framework"], "fw-b")
        self.assertEqual(ranked[2]["rank"], 3)

    def test_compute_relative_deltas(self):
        rows = [
            {"framework": "baseline-app", "score": 80.0, "rps": 40000, "p99": 200},
            {"framework": "fast-app", "score": 100.0, "rps": 60000, "p99": 100},
        ]
        deltas = compute_relative_deltas(rows, "baseline-app")
        # baseline should have 0% deltas
        self.assertEqual(deltas[0]["deltaScorePct"], 0.0)
        self.assertEqual(deltas[0]["deltaRpsPct"], 0.0)
        self.assertEqual(deltas[0]["deltaP99Pct"], 0.0)
        # fast-app: score +25%, rps +50%, p99 -50%
        self.assertEqual(deltas[1]["deltaScorePct"], 25.0)
        self.assertEqual(deltas[1]["deltaRpsPct"], 50.0)
        self.assertEqual(deltas[1]["deltaP99Pct"], -50.0)

    def test_export_summary_json(self):
        rows = [
            {"framework": "fw-1", "score": 50.0},
            {"framework": "fw-2", "score": 75.0},
            {"framework": "fw-3", "score": 100.0},
        ]
        summary = export_summary_json(rows)
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["topFramework"], "fw-3")
        self.assertEqual(summary["maxScore"], 100.0)
        self.assertEqual(summary["medianScore"], 75.0)

        # Empty / invalid fallback
        empty_summary = export_summary_json([])
        self.assertEqual(empty_summary["count"], 0)
        self.assertIsNone(empty_summary["topFramework"])

    def test_compute_efficiency_ratio(self):
        self.assertEqual(compute_efficiency_ratio(12.5, 950_000), 76000.0)
        self.assertIsNone(compute_efficiency_ratio(None, 100))
        self.assertIsNone(compute_efficiency_ratio(10, None))
        self.assertIsNone(compute_efficiency_ratio(0, 100))
        self.assertIsNone(compute_efficiency_ratio(10, 0))
        self.assertIsNone(compute_efficiency_ratio(True, 100))
        self.assertIsNone(compute_efficiency_ratio(10, False))

    def test_filter_top_tier(self):
        rows = [
            {"framework": "fast", "score": 92.5, "p99": 150.0},
            {"framework": "mid", "score": 82.0, "p99": 450.0},
            {"framework": "slow", "score": 75.0, "p99": 600.0},
        ]
        # min_score = 80.0
        top = filter_top_tier(rows, min_score=80.0)
        self.assertEqual([r["framework"] for r in top], ["fast", "mid"])

        # min_score = 80.0, max_p99_us = 300.0
        strict = filter_top_tier(rows, min_score=80.0, max_p99_us=300.0)
        self.assertEqual([r["framework"] for r in strict], ["fast"])

        # Non-list safe fallback
        self.assertEqual(filter_top_tier(None), [])

    def test_format_markdown_leaderboard(self):
        rows = [
            {"rank": 1, "framework": "fast", "score": 95.0, "rps": 950000, "mean": 150.0, "p99": 300.0},
            {"rank": 2, "framework": "mid", "score": 85.0, "rps": 800000, "mean": 250.0, "p99": 600.0},
        ]
        md = format_markdown_leaderboard(rows, max_entries=1)
        self.assertIn("| Rank | Framework |", md)
        self.assertIn("| 1 | fast | 95.0 | 950,000 | 150.0µs | 300.0µs |", md)
        self.assertNotIn("mid", md)  # truncated by max_entries

        # Empty fallback
        empty_md = format_markdown_leaderboard([])
        self.assertIn("| Rank | Framework |", empty_md)


if __name__ == "__main__":
    unittest.main()
