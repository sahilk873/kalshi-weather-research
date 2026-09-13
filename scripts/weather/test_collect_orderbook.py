import json
import tempfile
import unittest
from pathlib import Path

from collect_orderbook import Collector, exchange_timestamp


class _WebSocket:
    def __init__(self):
        self.sent = []

    def send(self, value):
        self.sent.append(json.loads(value))


class CollectOrderbookTests(unittest.TestCase):
    def test_exchange_timestamp_prefers_explicit_event_time(self):
        value, milliseconds = exchange_timestamp({"msg": {"ts_ms": 1669149841000}})
        self.assertEqual(milliseconds, 1669149841000)
        self.assertEqual(value, "2022-11-22T20:44:01Z")
        self.assertEqual(exchange_timestamp({"msg": {"settled_ts": 123}}), (None, None))

    def test_raw_frames_gap_health_resnapshot_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            collector = Collector(["orderbook_delta"], ["A"], output, 0,
                                  checkpoint_every=1)
            collector.connection_epoch = 1
            collector.replay.connection_epoch = 1
            for sink in collector.sinks.values():
                sink.set_connection_epoch(1)
            ws = _WebSocket()
            collector._on_message(ws, json.dumps({
                "type": "subscribed", "msg": {"channel": "orderbook_delta", "sid": 9}}))
            collector._on_message(ws, json.dumps({
                "type": "orderbook_snapshot", "sid": 9, "seq": 1,
                "msg": {"market_ticker": "A", "yes": [[40, 2]], "no": [],
                        "ts_ms": 1669149841000}}))
            collector._on_message(ws, json.dumps({
                "type": "orderbook_delta", "sid": 9, "seq": 3,
                "msg": {"market_ticker": "A", "side": "yes", "price": 40,
                        "delta": 1, "ts_ms": 1669149841001}}))

            raw_rows = [json.loads(line) for path in output.glob("raw_*.jsonl")
                        for line in path.read_text().splitlines()]
            self.assertEqual(len(raw_rows), 3)
            self.assertIn('"seq": 3', raw_rows[-1]["raw_json"])
            self.assertEqual(raw_rows[-1]["sequence_id"], 3)
            self.assertIsNotNone(raw_rows[-1]["received_at"])
            self.assertEqual(raw_rows[-1]["exchange_timestamp_ms"], 1669149841001)
            self.assertTrue(collector.replay.books["A"].quarantined)
            self.assertEqual(ws.sent[-1]["params"]["action"], "get_snapshot")
            health = [json.loads(line) for path in output.glob("health_*.jsonl")
                      for line in path.read_text().splitlines()]
            self.assertIn("sequence_gap", {row["event"] for row in health})
            checkpoints = [json.loads(line) for path in output.glob("checkpoints_*.jsonl")
                           for line in path.read_text().splitlines()]
            self.assertGreaterEqual(len(checkpoints), 2)
            self.assertTrue(all(row.get("state_sha256") for row in checkpoints))

    def test_malformed_frame_is_preserved_and_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            collector = Collector([], [], output, 0)
            collector._on_message(_WebSocket(), "not-json")
            raw = json.loads(next(output.glob("raw_*.jsonl")).read_text())
            self.assertEqual(raw["raw_json"], "not-json")
            self.assertTrue(raw["parse_error"])
            health = json.loads(next(output.glob("health_*.jsonl")).read_text())
            self.assertEqual(health["event"], "parser_failure")


if __name__ == "__main__":
    unittest.main()
