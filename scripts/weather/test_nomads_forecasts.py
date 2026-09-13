import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nomads_forecasts import record_rejection, url_for


class NomadsForecastsTest(unittest.TestCase):
    def test_gfs_url_is_point_in_time_and_filtered(self):
        url = url_for("gfs", datetime(2026, 9, 12, tzinfo=timezone.utc), 0, "phx")
        self.assertIn("filter_gfs_0p25.pl", url)
        self.assertIn("gfs.t00z.pgrb2.0p25.f000", url)
        self.assertIn("var_TMP=on", url)

    def test_failed_request_is_recorded_without_manifest_promotion(self):
        with TemporaryDirectory() as temp:
            with patch("nomads_forecasts.ROOT", Path(temp)):
                row = record_rejection("nbm", datetime(2026, 9, 13, tzinfo=timezone.utc), 1, "nyc", RuntimeError("unavailable"))
                self.assertIn("RuntimeError", row["reason"])
                text = (Path(temp) / "rejections.csv").read_text()
                self.assertIn("nbm,nyc", text)


if __name__ == "__main__":
    unittest.main()
