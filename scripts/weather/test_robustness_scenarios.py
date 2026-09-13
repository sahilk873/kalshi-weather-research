import unittest
from robustness_scenarios import run

class RobustnessScenarioTests(unittest.TestCase):
    def test_delay_is_fail_closed_and_bias_changes_score(self):
        rows = [{"prediction": ".8", "outcome": "yes", "decision_time_utc": "2026-01-01T00:10:00Z", "source_receipt_time": "2026-01-01T00:00:00Z", "observation_age_minutes": "3", "threshold_distance_f": ".2", "spread": ".06", "volume": "5", "quote_jump": ".2"}, {"prediction": ".2", "outcome": "no", "decision_time_utc": "2026-01-01T00:10:00Z", "source_receipt_time": "2026-01-01T00:09:00Z", "observation_age_minutes": "20", "threshold_distance_f": "3", "spread": ".01", "volume": "100", "quote_jump": ".01"}]
        rows[0]["nwp_receipt_time"] = "2026-01-01T00:00:00Z"; rows[1]["nwp_receipt_time"] = "2026-01-01T00:09:00Z"
        result = run(rows, delays=(2, 20), outages=(5,), biases=(.05,))
        self.assertEqual(result["feed_delay_2m"]["scored"], 1)
        self.assertEqual(result["feed_delay_20m"]["scored"], 0)
        self.assertEqual(result["observation_outage_5m"]["scored"], 1)
        self.assertEqual(result["nwp_late_2m"]["scored"], 1)
        self.assertNotEqual(result["baseline"]["brier"], result["calibration_bias_+0.05"]["brier"])
        self.assertEqual(result["wide_spread"]["scored"], 1)

    def test_mixed_naive_and_aware_timestamps_fail_closed_without_crashing(self):
        rows = [{"prediction": ".5", "outcome": "yes", "decision_time_utc": "2026-01-01T00:10:00", "source_receipt_time": "2026-01-01T00:00:00Z"}]
        result = run(rows, delays=(2,), outages=(), biases=())
        self.assertEqual(result["feed_delay_2m"]["scored"], 1)
        self.assertEqual(result["feed_delay_2m"]["filtered_out"], 0)

if __name__ == "__main__": unittest.main()
