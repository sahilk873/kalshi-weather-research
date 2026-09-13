import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_daily_ensemble_forecasts import daily_member_maxima, daily_member_minima, summarize_member_maxima


class DailyEnsembleTests(unittest.TestCase):
    def test_member_maximum_uses_nyc_standard_time_window(self):
        rows = []
        for member, values in {"m1": (70.0, 72.0), "m2": (71.0, 73.0)}.items():
            for timestamp, value in zip(("2026-07-01T06:00:00Z", "2026-07-02T04:00:00Z"), values):
                rows.append({
                    "forecast_run_time": "2026-06-30T00:00:00Z", "valid_time": timestamp,
                    "city_key": "nyc", "model": "fixture", "member_id": member,
                    "variable": "temperature_2m", "value": value,
                    "retrieved_at": "2026-06-30T00:05:00Z",
                })
        maxima = daily_member_maxima(pd.DataFrame(rows))
        self.assertEqual(len(maxima), 2)
        self.assertEqual(sorted(maxima["member_extreme_f"].tolist()), [72.0, 73.0])
        self.assertEqual(set(maxima["outcome_local_date"]), {"2026-07-01"})
        minima = daily_member_minima(pd.DataFrame(rows))
        self.assertEqual(sorted(minima["member_extreme_f"].tolist()), [70.0, 71.0])
        self.assertEqual(set(minima["temp_type"]), {"low"})

    def test_summary_preserves_pit_times_and_distribution(self):
        maxima = pd.DataFrame([
            {"city_key": "austin", "model": "fixture", "forecast_run_time": "2026-01-01T00:00:00Z", "retrieved_at": "2026-01-01T00:10:00Z", "outcome_local_date": "2026-01-02", "temp_type": "high", "member_extreme_f": 80.0},
            {"city_key": "austin", "model": "fixture", "forecast_run_time": "2026-01-01T00:00:00Z", "retrieved_at": "2026-01-01T00:10:00Z", "outcome_local_date": "2026-01-02", "temp_type": "high", "member_extreme_f": 82.0},
        ])
        row = summarize_member_maxima(maxima)[0]
        self.assertEqual(row["decision_time_utc"], "2026-01-01T00:10:00Z")
        self.assertEqual(row["member_count"], "2")
        self.assertEqual(row["mean_f"], "81.000000")
        self.assertNotEqual(row["stddev_f"], "")
        self.assertEqual(row["city"], "austin")

    def test_los_angeles_alias_is_canonicalized(self):
        frame = pd.DataFrame([{
            "forecast_run_time": "2026-01-01T00:00:00Z", "valid_time": "2026-01-02T08:00:00Z",
            "city_key": "los_angeles", "model": "fixture", "member_id": "m1",
            "variable": "temperature_2m", "value": 60.0, "retrieved_at": "2026-01-01T00:10:00Z",
        }])
        self.assertEqual(set(daily_member_maxima(frame)["city_key"]), {"la"})

    def test_early_utc_observation_is_assigned_to_prior_standard_date(self):
        frame = pd.DataFrame([{
            "forecast_run_time": "2026-06-30T00:00:00Z", "valid_time": "2026-07-01T04:00:00Z",
            "city_key": "nyc", "model": "fixture", "member_id": "m1",
            "variable": "temperature_2m", "value": 75.0, "retrieved_at": "2026-06-30T00:10:00Z",
        }])
        maxima = daily_member_maxima(frame)
        self.assertEqual(set(maxima["outcome_local_date"]), {"2026-06-30"})

    def test_summary_drops_window_already_started(self):
        maxima = pd.DataFrame([{
            "city_key": "nyc", "model": "fixture", "forecast_run_time": "2026-07-01T06:00:00Z",
            "retrieved_at": "2026-07-01T06:00:00Z", "outcome_local_date": "2026-07-01",
            "temp_type": "high", "member_extreme_f": 80.0,
        }])
        self.assertEqual(summarize_member_maxima(maxima), [])


if __name__ == "__main__":
    unittest.main()
