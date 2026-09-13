import unittest
from datetime import date, timedelta
from training_readiness import plan


class TrainingReadinessTests(unittest.TestCase):
    def test_empty_data_is_fail_closed(self):
        result = plan([])
        self.assertEqual(result["status"], "data_missing")
        self.assertFalse(result["folds"])

    def test_short_history_is_not_called_ready(self):
        rows = [{"market_ticker": "M", "target_time_utc": (date(2026, 1, 1) + timedelta(days=i)).isoformat() + "T00:00:00Z"} for i in range(8)]
        self.assertEqual(plan(rows, train_days=5, calibration_days=2, test_days=2)["status"], "insufficient_history")

    def test_partitions_are_chronological_and_disjoint(self):
        rows = [{"market_ticker": "M", "target_time_utc": (date(2026, 1, 1) + timedelta(days=i)).isoformat() + "T00:00:00Z"} for i in range(12)]
        result = plan(rows, train_days=5, calibration_days=2, test_days=2)
        self.assertEqual(result["status"], "ready")
        fold = result["folds"][0]
        self.assertLess(fold["train_end"], fold["calibration_start"])
        self.assertLess(fold["calibration_end"], fold["test_start"])


if __name__ == "__main__":
    unittest.main()
