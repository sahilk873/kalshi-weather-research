import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_nowcast_forecasts import build, evaluation_labels


class NowcastTest(unittest.TestCase):
    def test_prior_available_residuals_drive_future_state(self):
        labels = [{"city": "nyc", "date": "2025-01-01", "tmax_f": "80", "tmin_f": "60", "label_available_ts": "2025-01-02T12:00:00Z"}, {"city": "nyc", "date": "2025-01-02", "tmax_f": "81", "tmin_f": "61", "label_available_ts": "2025-01-03T12:00:00Z"}, {"city": "nyc", "date": "2025-01-03", "tmax_f": "82", "tmin_f": "62", "label_available_ts": "2025-01-04T12:00:00Z"}]
        state = []
        for i in range(10):
            state.append({"city": "nyc", "local_date": "2025-01-01", "local_hour": "12", "feature_asof_utc": f"2025-01-01T{12+i%2:02d}:00:00Z", "observed_high_so_far_f": "75", "observed_low_so_far_f": "58"})
        state.append({"city": "nyc", "local_date": "2025-01-03", "local_hour": "12", "feature_asof_utc": "2025-01-04T11:00:00Z", "observed_high_so_far_f": "76", "observed_low_so_far_f": "59"})
        rows, _ = build(state, labels, min_training=1)
        self.assertTrue(rows)
        self.assertEqual(rows[-1]["city"], "nyc")
        self.assertEqual(len(evaluation_labels(rows, labels)), len(rows))


if __name__ == "__main__": unittest.main()
