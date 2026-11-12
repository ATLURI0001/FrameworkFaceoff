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
    rate_factor,
    decade_score,
    linear_score,
    score_rows,
    pick,
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


if __name__ == "__main__":
    unittest.main()
