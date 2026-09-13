import tempfile
import unittest
from pathlib import Path
from audit_forecast_completeness import audit


class ForecastCompletenessTests(unittest.TestCase):
    def test_missing_fields_are_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); path = root / "forecasts"; path.mkdir()
            (path / "model_forecasts_points.csv").write_text("model,variable,value\nhrrr,temperature_2m,1\n")
            result = audit(root)
            hrrr = next(item for item in result["models"] if item["model"] == "hrrr")
            self.assertFalse(hrrr["complete"])
            self.assertIn("cin", hrrr["missing_fields"])


if __name__ == "__main__": unittest.main()
