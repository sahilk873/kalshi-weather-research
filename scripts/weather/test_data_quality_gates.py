import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_quality_gates import _daily_source_transition_audit, _forecast_rejection_audit, _historical_nyc_quote_audit, _provenance_index_audit, audit


class DataQualityTests(unittest.TestCase):
    def test_forecast_rejection_ledger_requires_reason_and_receipt(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); (root / "forecasts").mkdir()
            header = "model,city,initialization_time_utc,valid_time_utc,lead_hours,request_url,retrieved_at_utc,reason\n"
            good = header + "nbm,nyc,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,0,https://example.test,2026-01-01T00:01:00Z,http_404\n"
            path = root / "forecasts" / "rejections.csv"; path.write_text(good)
            self.assertTrue(_forecast_rejection_audit(root, datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])
            path.write_text(header + "nbm,nyc,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,0,https://example.test,2026-01-01T00:01:00Z,\n")
            self.assertFalse(_forecast_rejection_audit(root, datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])
    def test_historical_quote_gate_requires_hashed_raw_manifest(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); quote = root / "kalshi_hourly" / "historical_quotes"; raw = quote / "raw"; raw.mkdir(parents=True)
            payload = b'{"candlesticks":[]}\n'; path = raw / "x.json"; path.write_bytes(payload)
            import hashlib, json
            digest = hashlib.sha256(payload.rstrip(b"\n")).hexdigest()
            (quote / "candles_hourly.csv").write_text("x\n")
            (quote / "trades.csv").write_text("x\n")
            (quote / "manifest.json").write_text(json.dumps({"version": "historical-nyc-quotes-v2", "series_ticker": "KXTEMPNYCH", "markets_processed": 1, "candle_rows": 0, "trade_rows": 0, "raw_payloads": 1}))
            (quote / "raw_manifest.jsonl").write_text(json.dumps({"raw_path": str(path), "sha256": digest, "retrieved_at_utc": "2026-01-01T00:00:00Z", "endpoint": "/historical/trades"}) + "\n")
            self.assertTrue(_historical_nyc_quote_audit(root, datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])
            path.write_text("tampered\n")
            self.assertFalse(_historical_nyc_quote_audit(root, datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])

    def test_v3_quote_gate_requires_market_metadata_for_candles(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); quote = root / "kalshi_hourly" / "historical_quotes"; raw = quote / "raw"; raw.mkdir(parents=True)
            payload = b'{"markets":[]}'
            path = raw / "x.json"; path.write_bytes(payload)
            import hashlib, json
            digest = hashlib.sha256(payload).hexdigest()
            (quote / "candles_hourly.csv").write_text("market_ticker,end_period_ts\nM,1\n")
            (quote / "trades.csv").write_text("trade_id\n")
            (quote / "market_metadata.csv").write_text("market_ticker\n")
            (quote / "manifest.json").write_text(json.dumps({"version": "historical-nyc-quotes-v3", "series_ticker": "KXTEMPNYCH", "markets_processed": 1, "candle_rows": 1, "trade_rows": 0, "raw_payloads": 1, "failed_markets": 0}))
            (quote / "raw_manifest.jsonl").write_text(json.dumps({"raw_path": str(path), "sha256": digest, "retrieved_at_utc": "2026-01-01T00:00:00Z", "endpoint": "/historical/markets"}) + "\n")
            result = _historical_nyc_quote_audit(root, datetime(2026, 1, 2, tzinfo=timezone.utc))
            self.assertFalse(result["pass"])
            self.assertEqual(result["market_metadata_missing_for_candles"], 1)

    def test_provenance_indexes_fail_when_observation_index_is_empty(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); directory = root / "reports" / "provenance_indexes"; directory.mkdir(parents=True)
            (directory / "source_index.csv").write_text("source_run_id\nr\n")
            (directory / "observation_index.csv").write_text("observation_id\n")
            (directory / "provenance_index_status.json").write_text('{"pass": false, "rejected_rows": 1}')
            result = _provenance_index_audit(root)
            self.assertFalse(result["pass"]); self.assertEqual(result["source_rows"], 1)

    def test_provenance_index_requires_exact_station_scope(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); directory = root / "reports" / "provenance_indexes"; directory.mkdir(parents=True)
            (directory / "source_index.csv").write_text("source_run_id\nr\n")
            (directory / "observation_index.csv").write_text("observation_id\no\n")
            (directory / "provenance_index_status.json").write_text('{"pass": true, "hard_rejected_rows": 0, "station_scope": ["KNYC"]}')
            result = _provenance_index_audit(root)
            self.assertFalse(result["pass"]); self.assertFalse(result["station_scope_valid"])

    def test_daily_source_transition_requires_verified_non_empty_report(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "reports").mkdir()
            report = root / "reports" / "daily_source_transition_20260913.json"
            report.write_text('{"pass": true, "verified_rows": 2, "rejected_rows": 0, "transition_effective_date": "2026-08-14"}')
            result = _daily_source_transition_audit(root)
            self.assertTrue(result["pass"])
            self.assertEqual(result["verified_rows"], 2)
            report.write_text('{"pass": true, "verified_rows": 2, "rejected_rows": 1}')
            self.assertFalse(_daily_source_transition_audit(root)["pass"])

    def test_duplicate_and_missing_timestamp_gates_are_visible(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); (root / "ghcn_city").mkdir(); (root / "city_asos").mkdir(); (root / "city_nws_cli").mkdir(); (root / "forecasts").mkdir(); (root / "gefs" / "historical_raw").mkdir(parents=True)
            (root / "ghcn_city" / "labels_daily.csv").write_text("station_id,city,date,source,label_available_ts\nS,nyc,2025-01-01,x,\nS,nyc,2025-01-01,x,\n")
            (root / "city_asos" / "asos_parsed.csv").write_text("station,valid_utc,local_date\nNYC,2025-01-01T00:00:00Z,2024-12-31\n")
            (root / "city_nws_cli" / "daily_climate_cli.csv").write_text("city,publication_time_utc\nnyc,2025-01-01T00:00:00Z\n")
            (root / "forecasts" / "manifest.csv").write_text("model,raw_path,sha256\nhr,missing.grib,abc\n")
            (root / "gefs" / "historical_raw" / "manifest.csv").write_text("raw_path\ngefs/historical_raw/null.json\n")
            (root / "gefs" / "historical_raw" / "null.json").write_text('{"hourly":{"time":["2025-01-01T00:00"],"temperature_2m_member01":[null]}}')
            result = audit(root, datetime(2025, 1, 2, tzinfo=timezone.utc))
            self.assertFalse(result["pass"])
            self.assertEqual(result["checks"]["labels_duplicate_key"]["value"], 1)
            self.assertEqual(result["checks"]["label_availability"]["missing"], 2)
            self.assertEqual(result["checks"]["forecast_manifest"]["missing_raw_path"], 1)
            self.assertEqual(result["checks"]["historical_forecast_availability"]["empty_payload"], 1)


if __name__ == "__main__": unittest.main()
