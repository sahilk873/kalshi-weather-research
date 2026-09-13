import unittest
from simulate_candle_execution import simulate, summarize

class CandleExecutionTests(unittest.TestCase):
    def test_uses_prior_signal_and_next_fill_scenarios(self):
        probabilities = [{"market_ticker": "M", "decision_time_utc": "2026-01-01T00:01:00Z", "bucket_probability": "0.8"}]
        candles = [{"market_ticker": "M", "end_period_ts": "2026-01-01T00:00:00Z", "yes_ask_close": "0.50", "yes_bid_close": "0.48"}, {"market_ticker": "M", "end_period_ts": "2026-01-01T00:02:00Z", "yes_ask_open": "0.55", "yes_ask_close": "0.60", "yes_ask_high": "0.70"}]
        rows = simulate(probabilities, candles, [{"market_ticker": "M", "settled_yes": "yes"}], fee_rate=0.01)
        self.assertEqual({r["scenario"] for r in rows}, {"conservative", "base", "optimistic"})
        self.assertEqual(rows[0]["signal_candle_end"], 1767225600)
        self.assertLess(float(next(r for r in rows if r["scenario"] == "conservative")["fill_price"]), 1)
        self.assertEqual(summarize(rows)["optimistic"]["rows"], 1)
        self.assertIn("max_drawdown", summarize(rows)["optimistic"])
        self.assertIn("sharpe_per_trade", summarize(rows)["optimistic"])

    def test_fill_rate_uses_original_signal_denominator(self):
        rows = [{"scenario": "base", "market_ticker": "M", "decision_time_utc": "t",
                 "one_contract_net_payoff": "0.1", "fill_price": "0.5"}]
        self.assertEqual(summarize(rows, signal_count=2)["base"]["fill_rate"], 0.5)
        with self.assertRaises(ValueError):
            summarize(rows, signal_count=-1)

if __name__ == "__main__": unittest.main()
