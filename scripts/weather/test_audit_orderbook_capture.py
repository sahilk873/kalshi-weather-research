import json
import tempfile
import unittest
from pathlib import Path

from audit_orderbook_capture import audit


class OrderbookAuditTests(unittest.TestCase):
    def test_audits_hash_depth_and_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.jsonl"
            rows = [
                {"received_ts": "2026-01-01T00:00:00Z", "message": {"type": "orderbook_snapshot", "seq": 1, "msg": {"market_ticker": "X", "yes_dollars_fp": [["0.40", "1"]], "no_dollars_fp": [["0.60", "1"]]}}},
                {"received_ts": "2026-01-01T00:00:01Z", "message": {"type": "orderbook_delta", "seq": 3, "msg": {"market_ticker": "X", "side": "yes", "price_dollars": "0.40", "delta_fp": "1"}}},
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            result = audit(path)
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["sequence_gaps"], 1)
        self.assertTrue(result["full_depth_evidence"])
        self.assertEqual(len(result["sha256"]), 64)

    def test_latest_connection_epoch_isolated_from_prior_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.jsonl"
            rows = [
                {"connection_epoch": 0, "received_ts": "2026-01-01T00:00:00Z", "message": {"type": "orderbook_snapshot", "seq": 10, "msg": {"market_ticker": "OLD", "yes_dollars_fp": [["0.40", "1"]], "no_dollars_fp": [["0.60", "1"]]}}},
                {"connection_epoch": 0, "received_ts": "2026-01-01T00:00:01Z", "message": {"type": "orderbook_delta", "seq": 1, "msg": {"market_ticker": "OLD", "side": "yes", "price_dollars": "0.40", "delta_fp": "1"}}},
                {"connection_epoch": 1, "received_ts": "2026-01-01T00:01:00Z", "message": {"type": "orderbook_snapshot", "seq": 1, "msg": {"market_ticker": "NEW", "yes_dollars_fp": [["0.40", "1"]], "no_dollars_fp": [["0.60", "1"]]}}},
                {"connection_epoch": 1, "received_ts": "2026-01-01T00:01:01Z", "message": {"type": "orderbook_delta", "seq": 2, "msg": {"market_ticker": "NEW", "side": "yes", "price_dollars": "0.40", "delta_fp": "1"}}},
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            result = audit(path)
        self.assertEqual(result["latest_connection_epoch"], 1)
        self.assertEqual(result["ignored_prior_session_rows"], 2)
        self.assertEqual(result["sequence_resets"], 0)
        self.assertTrue(result["full_depth_evidence"])

    def test_malformed_connection_epoch_is_not_fatal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.jsonl"
            path.write_text(json.dumps({"connection_epoch": "bad", "message": {"type": "error"}}) + "\n")
            result = audit(path)
        self.assertEqual(result["latest_connection_epoch"], 0)
        self.assertEqual(result["invalid_rows"], 0)


if __name__ == "__main__":
    unittest.main()
