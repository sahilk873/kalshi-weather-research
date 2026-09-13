import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_persistence_forecasts import build_rows


class PersistenceTest(unittest.TestCase):
    def test_latest_prior_value_is_used_and_future_label_is_excluded(self):
        labels = [
            {"city": "nyc", "date": "2026-09-09", "tmax_f": "80", "tmin_f": "60", "label_available_ts": "2026-09-10T12:00:00Z"},
            {"city": "nyc", "date": "2026-09-10", "tmax_f": "90", "tmin_f": "65", "label_available_ts": "2026-09-11T12:00:00Z"},
        ]
        schedules = [{"event_ticker": "E", "decision_time_utc": "2026-09-10T15:00:00Z", "city": "nyc", "temp_type": "high", "outcome_local_date": "2026-09-11", "lead_hours": "24"}]
        rows, rejected = build_rows(schedules, labels, window=30)
        self.assertFalse(rejected)
        self.assertEqual(rows[0]["mean_f"], "80.000000")
        self.assertEqual(rows[0]["training_rows"], "1")


if __name__ == "__main__": unittest.main()
