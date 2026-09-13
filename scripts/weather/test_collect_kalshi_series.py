import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collect_kalshi_series import collect


class KalshiSeriesCollectorTests(unittest.TestCase):
    @patch("collect_kalshi_series._fetch_series")
    @patch("collect_kalshi_series._fetch_events")
    def test_preserves_series_and_event_provenance(self, fetch_events, fetch_series):
        fetch_series.return_value = {"series": {"ticker": "KXTEMPNYCH", "settlement_sources": [{"name": "TWC"}]}}
        fetch_events.return_value = [{"event_ticker": "KXTEMPNYCH-26SEP1200", "series_ticker": "KXTEMPNYCH",
                                      "title": "NYC temperature", "settlement_sources": [{"name": "TWC"}],
                                      "markets": [{"ticker": "KXTEMPNYCH-26SEP1200-B80", "yes_sub_title": "80° or above",
                                                    "status": "settled", "result": "yes"}]}]
        with tempfile.TemporaryDirectory() as tmp:
            events, markets = collect("KXTEMPNYCH", Path(tmp))
            self.assertEqual((events, markets), (1, 1))
            event_files = list((Path(tmp) / "raw").glob("event_*.json"))
            row = json.loads(event_files[0].read_text())
            self.assertEqual(row["event_ticker"], "KXTEMPNYCH-26SEP1200")
            self.assertEqual(len(list((Path(tmp) / "raw").glob("*.json"))), 2)
            self.assertEqual((Path(tmp) / "events.csv").read_text().count("KXTEMPNYCH"), 3)


if __name__ == "__main__":
    unittest.main()
