import unittest
from replay_orderbook import Book
from orderbook_features import features

class MicrostructureTests(unittest.TestCase):
    def test_spread_depth_imbalance_and_time(self):
        b=Book(); b.apply({"type":"orderbook_snapshot","yes":[[40,3]],"no":[[55,1]]})
        f=features(b,"2026-01-01T00:00:00Z","2026-01-01T01:00:00Z")
        self.assertEqual(f["best_yes_bid_cents"],40); self.assertEqual(f["best_yes_ask_cents"],45); self.assertEqual(f["spread_cents"],5); self.assertAlmostEqual(f["imbalance"],.5); self.assertEqual(f["minutes_to_close"],60)

if __name__ == "__main__": unittest.main()
