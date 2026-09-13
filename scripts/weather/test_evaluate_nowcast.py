import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_nowcast import evaluate


class NowcastTests(unittest.TestCase):
    def test_feature_asof_precedes_label_availability(self):
        state = [{"city": "nyc", "local_date": "2025-07-01", "feature_asof_utc": "2025-07-01T12:00:00Z", "local_hour": "8", "observed_high_so_far_f": "80", "observed_low_so_far_f": "60"}]
        labels = [{"city": "nyc", "date": "2025-07-01", "label_available_ts": "2025-07-02T12:00:00Z", "tmax_f": "90", "tmin_f": "55"}]
        summary, rejected = evaluate(state, labels)
        self.assertEqual(summary[0]["mae_high_f"], "10.000000")
        self.assertEqual(summary[0]["mae_low_f"], "5.000000")
        self.assertEqual(rejected, [])

    def test_label_available_before_feature_is_rejected(self):
        state = [{"city": "austin", "local_date": "2025-07-01", "feature_asof_utc": "2025-07-02T12:00:00Z", "local_hour": "8", "observed_high_so_far_f": "80", "observed_low_so_far_f": "60"}]
        labels = [{"city": "austin", "date": "2025-07-01", "label_available_ts": "2025-07-02T00:00:00Z", "tmax_f": "90", "tmin_f": "55"}]
        summary, rejected = evaluate(state, labels)
        self.assertEqual(summary, [])
        self.assertEqual(rejected[0]["reason"], "label_not_available_asof")


if __name__ == "__main__": unittest.main()
