import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validation_controls import reliability_bins, walk_forward_folds


class ValidationTests(unittest.TestCase):
    def test_folds_are_chronological_and_embargoed(self):
        rows = [{"outcome_local_date": f"2025-01-{day:02d}"} for day in range(1, 31)]
        folds = walk_forward_folds(rows, train_days=10, test_days=5, step_days=5, embargo_days=2)
        self.assertTrue(folds)
        for fold in folds:
            self.assertLess(fold["train_end"], fold["test_start"])
            self.assertGreaterEqual((__import__("datetime").date.fromisoformat(fold["test_start"]) - __import__("datetime").date.fromisoformat(fold["train_end"])).days, 3)

    def test_reliability_bins(self):
        rows = [{"probability": "0.1", "outcome": "0"}, {"probability": "0.9", "outcome": "1"}]
        bins = reliability_bins(rows, bins=2)
        self.assertEqual(bins[0]["count"], 1)
        self.assertEqual(bins[1]["event_rate"], 1.0)


if __name__ == "__main__": unittest.main()
