import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from probe_active_city_markets import SERIES, probe


class ActiveCityProbeTests(unittest.TestCase):
    def test_registry_includes_current_and_legacy_intraday_lines(self):
        self.assertTrue({
            "KXHIGHNY", "KXLOWTNYC", "KXTEMPNYCHS", "KXTEMPNYCH",
            "KXHIGHLAX", "KXLOWTLAX", "KXTEMPLAXHS", "KXTEMPLAXH",
            "KXHIGHAUS", "KXLOWTAUS", "KXTEMPAUSH",
        } <= set(SERIES))

    def test_archives_hashed_multi_city_counts(self):
        def fake(url, timeout=60):
            ticker = url.split("series_ticker=")[1].split("&")[0]
            return {"markets": [{"ticker": ticker + "-X"}]} if ticker == "KXHIGHNY" else {"markets": []}
        with tempfile.TemporaryDirectory() as directory, patch("probe_active_city_markets.http_get_json", side_effect=fake):
            result = probe(Path(directory), ("KXTEMPNYCH", "KXHIGHNY"))
            self.assertEqual(result["hourly_open_count"], 0)
            self.assertEqual(result["daily_open_count"], 1)
            self.assertEqual(len(result["raw_sha256"]), 64)
            self.assertTrue(Path(directory, "latest.json").exists())
            quote_path = Path(result["quote_path"])
            self.assertTrue(quote_path.exists())
            self.assertIn("yes_ask", quote_path.read_text().splitlines()[0])


if __name__ == "__main__":
    unittest.main()
