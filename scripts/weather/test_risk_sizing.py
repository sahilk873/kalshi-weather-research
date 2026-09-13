import unittest
from risk_sizing import allocate_event, block_bootstrap, size

class RiskSizingTests(unittest.TestCase):
    def test_loss_cap_binds(self):
        result=size(.8,.4,1000,fraction=1,max_loss_fraction=.01,max_allocation_fraction=.5)
        self.assertLessEqual(result["allocation_dollars"],10.0); self.assertGreater(result["kelly_fraction"],0)
    def test_negative_edge_zeroes_size(self):
        self.assertEqual(size(.4,.6,1000)["contracts"],0)
    def test_event_cap_is_shared_across_buckets(self):
        result=allocate_event([{"market_ticker":"A","probability":.7,"price":.4},{"market_ticker":"B","probability":.6,"price":.4}],1000,.01)
        self.assertLessEqual(sum(r["allocation_dollars"] for r in result),10.0)
    def test_invalid_fee_fails_closed(self):
        with self.assertRaises(ValueError): size(.6, .5, 1000, fee_rate=-.1)
    def test_event_recompute_uses_fee_adjusted_price_and_row_identity(self):
        result = allocate_event([
            {"market_ticker": "", "probability": .9, "price": .2, "fee_rate": .1},
            {"market_ticker": "", "probability": .8, "price": .4, "fee_rate": .1},
        ], 1000, .001)
        for row, price in zip(result, (.22, .44)):
            self.assertAlmostEqual(row["allocation_dollars"], row["contracts"] * price)
            self.assertAlmostEqual(row["position_loss_dollars"], row["allocation_dollars"])
    def test_block_bootstrap_is_reproducible_and_reports_tails(self):
        result = block_bootstrap([.1, -.05, .02, -.01], simulations=50, block_size=2, seed=7)
        repeat = block_bootstrap([.1, -.05, .02, -.01], simulations=50, block_size=2, seed=7)
        self.assertEqual(result, repeat)
        self.assertEqual(result["observations"], 4)
        self.assertGreaterEqual(result["max_drawdown_p95"], 0)

if __name__ == "__main__": unittest.main()
