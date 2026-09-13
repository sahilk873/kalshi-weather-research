import unittest
from generate_live_daily_diagnostic import generate


class LiveDailyDiagnosticTests(unittest.TestCase):
    def test_asof_probability_and_late_rejection(self):
        markets = {"KXHIGHNY": {"markets": [{"ticker": "KXHIGHNY-26SEP13-T85", "event_ticker": "KXHIGHNY-26SEP13", "cap_strike": 85, "strike_type": "less", "rules_primary": "CLINYC according to The Weather Company"}]}}
        forecasts = [{"model_name": "ncep_gefs025", "source_receipt_time": "2026-09-12T12:00:00Z", "outcome_local_date": "2026-09-13", "city": "nyc", "temp_type": "high", "mean_f": "80", "stddev_f": "2"}]
        accepted, rejected = generate(markets, forecasts, [{"market_ticker": "KXHIGHNY-26SEP13-T85", "received_ts": "2026-09-13T12:46:00Z", "best_yes_bid_cents": "40", "best_yes_ask_cents": "50", "spread_cents": "10", "top_depth": "12"}])
        self.assertEqual(len(accepted), 1); self.assertGreater(float(accepted[0]["probability"]), .98); self.assertFalse(rejected)
        self.assertEqual(float(accepted[0]["best_yes_ask_cents"]), 50.0)
        with_costs, _ = generate(markets, forecasts, [{"market_ticker": "KXHIGHNY-26SEP13-T85", "received_ts": "2026-09-13T12:46:00Z", "best_yes_bid_cents": "40", "best_yes_ask_cents": "50", "spread_cents": "10", "top_depth": "12"}], fee_rate=.1, slippage_cents=1.0)
        self.assertLess(float(with_costs[0]["yes_net_edge_conservative"]), float(with_costs[0]["yes_net_edge_optimistic"]))
        bad = {"KXHIGHNY": {"markets": [{"ticker": "X", "event_ticker": "KXHIGHNY-26SEP13", "cap_strike": 85, "strike_type": "less", "rules_primary": "wrong station"}]}}
        _, rejected = generate(bad, forecasts, [{"market_ticker": "X", "received_ts": "2026-09-13T12:46:00Z"}])
        self.assertEqual(rejected[0]["reason"], "settlement_rule_station_mismatch")
        accepted, rejected = generate(markets, forecasts, [{"market_ticker": "KXHIGHNY-26SEP13-T85", "received_ts": "2026-09-12T11:00:00Z"}])
        self.assertFalse(accepted); self.assertEqual(rejected[0]["reason"], "missing_forecast_asof_quote")
        accepted, rejected = generate(markets, forecasts, [{"market_ticker": "KXHIGHNY-26SEP13-T85", "received_ts": "2026-09-13T12:46:00Z"}])
        self.assertFalse(accepted); self.assertEqual(rejected[0]["reason"], "missing_executable_quote_fields")


if __name__ == "__main__":
    unittest.main()
