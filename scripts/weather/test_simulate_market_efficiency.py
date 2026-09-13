import unittest
from simulate_market_efficiency import analyze, summarize

class EfficiencyTests(unittest.TestCase):
    def test_uses_only_candle_at_or_before_decision(self):
        rows=analyze([{"market_ticker":"M","event_ticker":"E","city":"phx","temp_type":"high","decision_time_utc":"2026-01-01T01:00:00Z","bucket_probability":"0.60"}], [{"market_ticker":"M","end_period_ts":"1767225600","yes_ask_close":"0.40"},{"market_ticker":"M","end_period_ts":"1767232800","yes_ask_close":"0.90"}], [{"market_ticker":"M","settled_yes":"yes"}])
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]["yes_ask"],"0.40000000"); self.assertEqual(rows[0]["gross_edge"],"0.20000000")
        summary=summarize(rows); self.assertEqual(summary["settled_candidates"],1); self.assertAlmostEqual(summary["one_contract_net_payoff"],.6)

if __name__ == "__main__": unittest.main()
