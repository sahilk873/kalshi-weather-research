import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from data_quality_gates import _city_asos_archive_audit, _cpc_audit, _ecmwf_ensemble_audit, _ecmwf_point_audit, _gefs_live_audit, _ghcnh_audit, _ghcnh_daily_audit, _historical_forecast_audit, _homr_audit, _live_daily_diagnostic_audit, _live_price_summary_audit, _orderbook_capture_audit, _orderbook_reconciliation_audit, _rtma_audit, _twc_kalshi_audit, _weather_index_audit, audit


class SourceGateTest(unittest.TestCase):
    def test_live_price_summary_must_remain_unsettled(self):
        with tempfile.TemporaryDirectory() as d:
            reports = Path(d) / "reports"; reports.mkdir()
            (reports / "live_price_comparison_summary.json").write_text('{"status":"diagnostic_only","rows":2,"settled_rows":0,"realized_edge":null,"net_pnl":null}')
            self.assertTrue(_live_price_summary_audit(Path(d))["pass"])
            (reports / "live_price_comparison_summary.json").write_text('{"status":"evaluated","rows":2,"settled_rows":2,"net_pnl":1}')
            self.assertFalse(_live_price_summary_audit(Path(d))["pass"])

    def test_live_daily_diagnostic_rejects_missing_quote_fields(self):
        with tempfile.TemporaryDirectory() as d:
            reports = Path(d) / "reports"; reports.mkdir()
            (reports / "live_daily_diagnostic_predictions_20260913.csv").write_text("best_yes_bid_cents,best_yes_ask_cents,spread_cents,top_depth\n40,50,10,\n")
            result = _live_daily_diagnostic_audit(Path(d))
            self.assertFalse(result["pass"]); self.assertEqual(result["missing_executable_quote_rows"], 1)

    def test_orderbook_rest_reconciliation_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "reports"
            root.mkdir()
            self.assertFalse(_orderbook_reconciliation_audit(Path(d))["pass"])
            (root / "orderbook_reconciliation_20260913.json").write_text('{"pass": true, "websocket_levels": 2, "rest_levels": 2, "mismatches": []}')
            self.assertTrue(_orderbook_reconciliation_audit(Path(d))["pass"])

    def test_orderbook_capture_gate_rejects_sequence_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            reports = Path(d) / "reports"
            reports.mkdir()
            report = reports / "orderbook_capture_20260913.json"
            report.write_text('{"rows": 2, "full_depth_evidence": true, "sequence_gaps": 1, "sequence_resets": 0, "invalid_rows": 0}')
            result = _orderbook_capture_audit(Path(d))
            self.assertFalse(result["pass"])
            report.write_text('{"rows": 2, "full_depth_evidence": true, "sequence_gaps": 0, "sequence_resets": 0, "invalid_rows": 0, "market_tickers": ["KXTEMPNYCH-test"]}')
            self.assertTrue(_orderbook_capture_audit(Path(d))["pass"])

    def test_twc_manifest_requires_availability_semantics(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "twc_kalshi"
            root.mkdir(parents=True)
            (root / "manifest.json").write_text('{"snapshots": [{"retrieved_at_utc": "2026-01-01T00:00:00Z"}]}')
            result = _twc_kalshi_audit(Path(d), datetime(2026, 1, 2, tzinfo=timezone.utc))
            self.assertEqual(result["availability_metadata_missing"], 1)
            self.assertFalse(result["pass"])

    def test_historical_forecast_manifest_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "gefs" / "historical_raw"
            root.mkdir(parents=True)
            (root / "manifest.csv").write_text("raw_path\n../outside.json\n")
            result = _historical_forecast_audit(Path(d))
            self.assertEqual(result["invalid_path"], 1)
            self.assertFalse(result["pass"])

    def test_historical_forecast_manifest_rejects_non_object_payload(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "gefs" / "historical_raw"
            root.mkdir(parents=True)
            (root / "bad.json").write_text("[]")
            (root / "manifest.csv").write_text("raw_path\ngefs/historical_raw/bad.json\n")
            result = _historical_forecast_audit(Path(d))
            self.assertEqual(result["invalid_json"], 1)
            self.assertFalse(result["pass"])

    def test_empty_optional_sources_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            result = audit(Path(d))
            self.assertFalse(result["checks"]["rtma_archive"]["pass"])
            self.assertFalse(result["checks"]["cpc_oni"]["pass"])

    def test_rtma_impossible_temperature_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "rtma"; (root / "raw").mkdir(parents=True)
            raw = root / "raw" / "x.grb2"; raw.write_bytes(b"raw")
            import hashlib
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            (root / "manifest.csv").write_text("model,valid_time_utc,source_url,raw_path,sha256,retrieved_at_utc\nrtma,2026-01-01T00:00:00Z,x," + str(raw) + "," + digest + ",2026-01-01T00:01:00Z\n")
            (root / "rtma_point_features.csv").write_text("city,variable,value,unit,valid_time_utc,grid_latitude,grid_longitude,raw_path,sha256\nphx,temperature_2m,999,K,2026-01-01T00:00:00Z,33,-112," + str(raw) + "," + digest + "\n")
            self.assertFalse(_rtma_audit(Path(d))["pass"])

    def test_cpc_impossible_anomaly_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "cpc"; root.mkdir()
            (root / "oni.csv").write_text("season,year,nino34_3mo_mean_c,oni_anomaly_c,source_url,retrieved_at_utc\nDJF,2020,27,99,x,2020-01-01T00:00:00Z\n")
            self.assertFalse(_cpc_audit(Path(d))["pass"])

    def test_cpc_invalid_retrieval_time_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "cpc"; root.mkdir()
            (root / "oni.csv").write_text("season,year,nino34_3mo_mean_c,oni_anomaly_c,source_url,retrieved_at_utc\nDJF,2020,27,0,x,not-a-time\n")
            self.assertFalse(_cpc_audit(Path(d))["pass"])

    def test_rtma_future_timestamp_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "rtma"; (root / "raw").mkdir(parents=True)
            raw = root / "raw" / "x.grb2"; raw.write_bytes(b"raw")
            import hashlib
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            (root / "manifest.csv").write_text("model,valid_time_utc,source_url,raw_path,sha256,retrieved_at_utc\nrtma,2026-01-01T00:00:00Z,x," + str(raw) + "," + digest + ",2026-01-02T00:00:00Z\n")
            (root / "rtma_point_features.csv").write_text("city,variable,value,unit,valid_time_utc,grid_latitude,grid_longitude,raw_path,sha256\nphx,temperature_2m,300,K,2026-01-02T00:00:00Z,33,-112," + str(raw) + "," + digest + "\n")
            self.assertFalse(_rtma_audit(Path(d), datetime(2026, 1, 1, tzinfo=timezone.utc))["pass"])

    def test_ghcnh_hash_and_range_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "ghcnh"; root.mkdir()
            raw = root / "source.psv"; raw.write_bytes(b"source")
            import hashlib
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            (root / "observations_2026.csv").write_text(
                "station,station_name,valid_utc,latitude,longitude,elevation_m,temperature_f,dewpoint_f,temperature_quality_code,temperature_report_type,raw_path,sha256\n"
                f"USW00023183,PHX,2026-01-01T00:00:00Z,33,-112,339,70,50,1,FM15,{raw},{digest}\n")
            self.assertTrue(_ghcnh_audit(Path(d), datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])

    def test_homr_missing_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(_homr_audit(Path(d), datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])

    def test_ghcnh_daily_unregistered_station_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "ghcnh"; root.mkdir()
            (root / "daily_extrema_2020_2026.csv").write_text(
                "station,local_date,timezone,observation_count,tmax_f,tmax_utc,tmin_f,tmin_utc,raw_paths,raw_hashes\n"
                "USW00013958,2026-01-01,America/Chicago,1,70,2026-01-01T18:00:00Z,30,2026-01-01T06:00:00Z,x,h\n")
            self.assertFalse(_ghcnh_daily_audit(Path(d))["pass"])

    def test_ghcnh_future_receipt_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "ghcnh"; root.mkdir()
            raw = root / "source.psv"; raw.write_bytes(b"source")
            import hashlib
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            (root / "observations_2020_2026.csv").write_text(
                "station,station_name,valid_utc,latitude,longitude,elevation_m,temperature_f,dewpoint_f,temperature_quality_code,temperature_report_type,raw_path,sha256,source_receipt_time\n"
                f"USW00023183,PHX,2026-01-01T00:00:00Z,33,-112,339,70,50,1,FM15,{raw},{digest},2026-02-01T00:00:00Z\n")
            self.assertFalse(_ghcnh_audit(Path(d), datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])

    def test_ecmwf_points_empty_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(_ecmwf_point_audit(Path(d), datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])

    def test_weather_index_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "weather_index"; root.mkdir()
            raw = root / "nyc.json"; raw.write_text('{"city":"nyc","timeseries":[],"config_version":"v"}')
            (root / "manifest.json").write_text('{"rows":[{"city":"nyc","status":200,"raw_path":"' + str(raw) + '","sha256":"bad","config_version":"v","retrieved_at_utc":"2026-01-01T00:00:00Z"}]}')
            self.assertFalse(_weather_index_audit(Path(d), datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])

    def test_ecmwf_ensemble_tampered_hash_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "ecmwf"; root.mkdir()
            raw = root / "x.grib2"; raw.write_bytes(b"raw")
            (root / "ensemble_points.csv").write_text(
                "model,city,member_id,initialization_time_utc,valid_time_utc,lead_hours,source_receipt_time,variable,value,unit,grid_latitude,grid_longitude,raw_path,sha256,message_index\n"
                f"ECMWF_IFS_ENFO,phx,1,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,0,2026-01-01T00:01:00Z,temperature_2m,80,F,33,-112,{raw},bad,1\n")
            self.assertFalse(_ecmwf_ensemble_audit(Path(d), datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])

    def test_gefs_live_archive_records_observed_members(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "gefs"; (root / "raw").mkdir(parents=True)
            raw = root / "raw" / "x.json"
            raw.write_text('{"hourly":{"time":["2026-01-01T00:00"],"temperature_2m_member01":[70],"temperature_2m_member02":[71]}}')
            import hashlib
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            (root / "manifest.csv").write_text(
                "model,city_key,request_url,raw_path,sha256,retrieved_at,member_count\n"
                f"ncep_gefs025,nyc,x,{raw},{digest},2026-01-01T00:01:00Z,2\n")
            result = _gefs_live_audit(Path(d), datetime(2026, 1, 2, tzinfo=timezone.utc))
            self.assertTrue(result["pass"])
            self.assertEqual(result["observed_member_counts"], {"2": 1})

    def test_gefs_live_member_count_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "gefs"; (root / "raw").mkdir(parents=True)
            raw = root / "raw" / "x.json"; raw.write_text('{"hourly":{"temperature_2m_member01":[70]}}')
            import hashlib
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            (root / "manifest.csv").write_text(
                "model,city_key,request_url,raw_path,sha256,retrieved_at,member_count\n"
                f"ncep_gefs025,nyc,x,{raw},{digest},2026-01-01T00:01:00Z,31\n")
            self.assertFalse(_gefs_live_audit(Path(d), datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])

    def test_city_asos_manifest_hash_is_checked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "city_asos"; root.mkdir(parents=True)
            raw = root / "raw.csv"; raw.write_text("station,valid\nNYC,2026-01-01 00:00\n")
            import hashlib, json
            (root / "manifest.json").write_text(json.dumps({"rows": [{"city": "nyc", "station": "NYC", "raw_path": str(raw), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(), "source_url": "https://example.test", "retrieved_at_utc": "2026-01-01T00:01:00Z"}]}))
            self.assertTrue(_city_asos_archive_audit(Path(d), datetime(2026, 1, 2, tzinfo=timezone.utc))["pass"])


if __name__ == "__main__": unittest.main()
