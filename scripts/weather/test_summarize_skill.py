import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from summarize_skill import summarize


class SkillSummaryTest(unittest.TestCase):
    def test_metrics_are_sample_weighted(self):
        rows = [{"model_name": "m", "model_version": "v", "city": "nyc", "temp_type": "high", "lead_hours": "24", "eligible_predictions": "1", "mae_f": "2", "crps_predictions": "1", "crps_f": "1"}, {"model_name": "m", "model_version": "v", "city": "nyc", "temp_type": "high", "lead_hours": "24", "eligible_predictions": "3", "mae_f": "4", "crps_predictions": "3", "crps_f": "3"}]
        result = summarize(rows)[0]
        self.assertEqual(result["eligible_predictions"], "4")
        self.assertEqual(result["weighted_mae_f"], "3.500000")
        self.assertEqual(result["weighted_crps_f"], "2.500000")


if __name__ == "__main__": unittest.main()
