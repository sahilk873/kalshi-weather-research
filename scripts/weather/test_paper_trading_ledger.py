import json, tempfile, unittest
from pathlib import Path
from paper_trading_ledger import append_records, from_execution_rows, validate_manifest_file, validate_record

class PaperLedgerTest(unittest.TestCase):
    def test_execution_rows_create_order_and_fill(self):
        rows = from_execution_rows([{"market_ticker":"M", "scenario":"base", "decision_time_utc":"2026-09-12T12:00:00Z", "execution_candle_end":"2", "signal_yes_ask":".4", "fill_price":".5", "fee":".01", "settled_yes":"true", "one_contract_net_payoff":".49"}], "manifest.json")
        self.assertEqual({r["record_type"] for r in rows}, {"would_have_order", "simulated_fill"})
    def test_append_is_duplicate_safe_and_validates_reference(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"; rows = [{"record_id":"1", "record_type":"prediction", "recorded_at_utc":"2026-09-12T12:00:00Z", "manifest_path":"m.json", "market_ticker":"M"}]
            self.assertEqual(append_records(path, rows, {"m.json"}), 1)
            with self.assertRaises(ValueError): append_records(path, rows, {"m.json"})
            self.assertTrue(validate_record({"record_type":"prediction"}))

    def test_manifest_validation_contract(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            record = {"record_id":"1", "record_type":"prediction", "recorded_at_utc":"2026-09-12T12:00:00Z", "manifest_path":"m.json", "market_ticker":"M"}
            self.assertFalse(validate_record(record, {"m.json"}))

    def test_manifest_file_is_validated_before_telemetry(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "manifest.json"
            path.write_text(json.dumps({"prediction": 2}))
            errors = validate_manifest_file(path)
            self.assertTrue(errors)
            self.assertIn("missing or empty decision_ts", errors)

if __name__ == "__main__": unittest.main()
