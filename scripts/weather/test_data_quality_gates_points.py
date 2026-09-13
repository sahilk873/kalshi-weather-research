import tempfile
import unittest
from pathlib import Path

from data_quality_gates import audit


class ForecastPointGateTest(unittest.TestCase):
    def test_empty_point_artifact_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            result = audit(Path(d))
            self.assertFalse(result["checks"]["forecast_point_provenance"]["pass"])


if __name__ == "__main__": unittest.main()
