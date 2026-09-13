import tempfile
import unittest
import csv
import sqlite3
from pathlib import Path

from audit_artifact_inventory import inventory


class InventoryTest(unittest.TestCase):
    def test_quote_raw_manifest_counts_are_exposed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); quote = root / "kalshi_hourly" / "historical_quotes"; quote.mkdir(parents=True)
            (quote / "manifest.json").write_text('{"raw_payloads": 3, "failed_markets": 1}')
            (quote / "raw_quarantine_manifest.jsonl").write_text('{"status":"quarantined"}\n')
            result = inventory(root)
            self.assertEqual(result["nyc_historical_quote_raw_payloads"], 3)
            self.assertEqual(result["nyc_historical_quote_quarantined_payloads"], 1)
            self.assertEqual(result["nyc_historical_quote_failed_markets"], 1)

    def test_missing_files_are_zero(self):
        with tempfile.TemporaryDirectory() as d:
            result = inventory(Path(d))
            self.assertEqual(result["forecast_points"], 0)
            self.assertEqual(result["city_trades"], 0)
            self.assertEqual(inventory(Path(d))["sqlite_count_mismatches"], [])

    def test_count_drift_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / "forecasts").mkdir()
            (root / "forecasts" / "manifest.csv").write_text("model\nfoo\n")
            con = sqlite3.connect(root / "kalshi_weather.sqlite")
            con.execute("CREATE TABLE model_forecasts(x TEXT)")
            con.commit(); con.close()
            self.assertIn("forecast_manifest", inventory(root)["sqlite_count_mismatches"])

    def test_historical_candle_count_uses_market_period_key(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); quote = root / "kalshi_hourly" / "historical_quotes"; quote.mkdir(parents=True)
            (quote / "candles_hourly.csv").write_text(
                "market_ticker,end_period_ts,period_interval\nM,1,60\nM,1,60\nM,2,60\n"
            )
            self.assertEqual(inventory(root)["nyc_historical_quote_candles"], 2)


if __name__ == "__main__": unittest.main()
