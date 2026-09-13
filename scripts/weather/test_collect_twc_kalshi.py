import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from collect_twc_kalshi import collect

class TWCPortalTests(unittest.TestCase):
    @patch("collect_twc_kalshi._fetch_json")
    def test_archives_knyc_and_daily_source_rows(self, fetch):
        hourly_payload = {"stations": [{"icaoId": "KNYC", "stationName": "New York City", "observations": [{"icaoId": "KNYC", "reportTimeUTC": "2026-09-12T20:00:00Z", "tempF": 80.0, "status": "settled"}]}]}
        daily_payload = {"date": "2026-09-12", "results": [{"station": {"icao": "KNYC", "city": "New York City", "cliId": "NYC"}, "status": "official", "avgTemp": 77.5, "data": {"maxTempF": 85, "minTempF": 70}}]}
        fetch.side_effect = [hourly_payload, daily_payload, hourly_payload, daily_payload]
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(collect(Path(tmp), "2026-09-07", "2026-09-12"), (1, 1))
            # A second receipt is retained as a distinct immutable source row.
            self.assertEqual(collect(Path(tmp), "2026-09-07", "2026-09-12"), (1, 1))
            self.assertTrue((Path(tmp) / "manifest.json").exists())
            self.assertIn("KNYC", (Path(tmp) / "hourly.csv").read_text())
            self.assertIn(",77.5,", (Path(tmp) / "daily.csv").read_text())
            self.assertEqual((Path(tmp) / "hourly.csv").read_text().count("KNYC"), 2)
            self.assertEqual((Path(tmp) / "daily.csv").read_text().count("KNYC"), 2)
            import json
            manifest = json.loads((Path(tmp) / "manifest.json").read_text())
            self.assertEqual(manifest["latest"]["availability_basis"], "receipt_upper_bound")
            self.assertFalse(manifest["latest"]["source_publication_time_observed"])
            self.assertTrue(all(row["availability_basis"] == "receipt_upper_bound" for row in manifest["snapshots"]))

if __name__ == "__main__": unittest.main()
