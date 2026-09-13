import unittest
from replay_orderbook import Book, OrderBookQuarantined, ReplayState, buy_yes

class ReplayTests(unittest.TestCase):
    def test_snapshot_delta_gap_quarantines_fills(self):
        b=Book(); b.apply({"type":"orderbook_snapshot","seq":1,"yes":[[40,2]],"no":[[55,3],[50,2]]}); b.apply({"type":"orderbook_delta","seq":3,"side":"no","price":55,"delta":1})
        self.assertEqual(b.gaps,1); self.assertTrue(b.quarantined)
        with self.assertRaises(OrderBookQuarantined): buy_yes(b,5,0.01)

    def test_resnapshot_clears_quarantine(self):
        b=Book(); b.apply({"type":"orderbook_snapshot","seq":1,"yes":[],"no":[[55,3]]}); b.apply({"type":"orderbook_delta","seq":3,"side":"no","price":55,"delta":1})
        b.apply({"type":"orderbook_snapshot","seq":4,"yes":[],"no":[[55,5]]})
        fill=buy_yes(b,5,0.01)
        self.assertFalse(b.quarantined); self.assertEqual(fill["filled"],5); self.assertEqual(fill["remaining"],0)

    def test_unknown_delta_side_fails_closed(self):
        b=Book()
        with self.assertRaises(ValueError): b.apply({"type":"orderbook_delta","side":"bid","price":50,"delta":1})

    def test_current_dollar_schema_is_normalized(self):
        b = Book()
        b.apply({"type": "orderbook_snapshot", "seq": 1, "msg": {
            "market_ticker": "KXHIGHNY-X", "yes_dollars_fp": [["0.4200", "3.00"]],
            "no_dollars_fp": [["0.5700", "2.00"]]}})
        self.assertEqual(b.yes, {42: 3.0})
        self.assertEqual(b.no, {57: 2.0})
        b.apply({"type": "orderbook_delta", "seq": 2, "msg": {
            "side": "yes", "price_dollars": "0.4200", "delta_fp": "-1.00"}})
        self.assertEqual(b.yes, {42: 2.0})

    def test_subscription_sequence_can_interleave_markets(self):
        replay = ReplayState()
        replay.apply_record({"connection_epoch": 1, "message": {
            "type": "orderbook_snapshot", "sid": 7, "seq": 1,
            "msg": {"market_ticker": "A", "yes": [[40, 1]], "no": []}}})
        replay.apply_record({"connection_epoch": 1, "message": {
            "type": "orderbook_snapshot", "sid": 7, "seq": 2,
            "msg": {"market_ticker": "B", "yes": [[41, 2]], "no": []}}})
        replay.apply_record({"connection_epoch": 1, "message": {
            "type": "orderbook_delta", "sid": 7, "seq": 3,
            "msg": {"market_ticker": "A", "side": "yes", "price": 40,
                    "delta": 1}}})
        self.assertEqual(replay.sequence_gaps, 0)
        self.assertEqual(replay.books["A"].yes, {40: 2.0})
        self.assertEqual(replay.books["B"].yes, {41: 2.0})

    def test_checkpoint_round_trip_is_deterministic_and_tamper_evident(self):
        replay = ReplayState()
        replay.apply_record({"connection_epoch": 2, "raw_json":
            '{"type":"orderbook_snapshot","sid":4,"seq":1,"msg":{"market_ticker":"A","yes":[[40,2]],"no":[]}}'})
        checkpoint = replay.checkpoint()
        restored = ReplayState.from_checkpoint(checkpoint)
        self.assertEqual(restored.checkpoint(), checkpoint)
        checkpoint["books"]["A"]["yes"][0][1] = 999
        with self.assertRaises(ValueError):
            ReplayState.from_checkpoint(checkpoint)

    def test_new_ticker_delta_after_gap_is_quarantined(self):
        replay = ReplayState()
        replay.apply_record({"connection_epoch": 1, "message": {
            "type": "orderbook_snapshot", "sid": 7, "seq": 1,
            "msg": {"market_ticker": "A", "yes": [], "no": []}}})
        replay.apply_record({"connection_epoch": 1, "message": {
            "type": "orderbook_delta", "sid": 7, "seq": 3,
            "msg": {"market_ticker": "B", "side": "yes", "price": 40,
                    "delta": 2}}})
        self.assertTrue(replay.books["A"].quarantined)
        self.assertTrue(replay.books["B"].quarantined)
        self.assertEqual(replay.books["B"].yes, {})

if __name__ == "__main__": unittest.main()
