import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_climatology_forecasts import build_rows


class ClimatologyTests(unittest.TestCase):
    def test_uses_only_prior_available_same_month_labels(self):
        schedules = [{"event_ticker": "research_nyc_2026-07-10", "decision_time_utc": "2026-07-10T12:00:00Z", "city": "nyc", "temp_type": "high", "outcome_local_date": "2026-07-10", "lead_hours": "12"}]
        labels = [
            {"city": "nyc", "date": "2024-07-10", "tmax_f": "80", "tmin_f": "60", "label_available_ts": "2024-07-11T12:00:00Z"},
            {"city": "nyc", "date": "2025-07-10", "tmax_f": "90", "tmin_f": "70", "label_available_ts": "2025-07-11T12:00:00Z"},
            {"city": "nyc", "date": "2026-07-10", "tmax_f": "999", "tmin_f": "999", "label_available_ts": "2026-07-11T12:00:00Z"},
            {"city": "nyc", "date": "2025-01-10", "tmax_f": "40", "tmin_f": "30", "label_available_ts": "2025-01-11T12:00:00Z"},
        ]
        rows, rejected = build_rows(schedules, labels)
        self.assertEqual(len(rejected), 0)
        self.assertEqual(rows[0]["mean_f"], "85.000000")
        self.assertEqual(rows[0]["training_rows"], "2")

    def test_future_only_labels_fail_closed(self):
        schedule = [{"event_ticker": "x", "decision_time_utc": "2026-01-01T00:00:00Z", "city": "austin", "temp_type": "low", "outcome_local_date": "2026-01-02", "lead_hours": "1"}]
        labels = [{"city": "austin", "date": "2025-01-02", "tmax_f": "70", "tmin_f": "30", "label_available_ts": "2026-01-02T12:00:00Z"}]
        rows, rejected = build_rows(schedule, labels)
        self.assertEqual(rows, [])
        self.assertEqual(rejected[0]["reason"], "no_prior_available_labels")


if __name__ == "__main__":
    unittest.main()
