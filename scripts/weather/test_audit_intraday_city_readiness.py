import tempfile, unittest
from pathlib import Path
from audit_intraday_city_readiness import audit

class IntradayReadinessTests(unittest.TestCase):
    def test_all_cities_fail_without_event_terms(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "twc_kalshi").mkdir(parents=True)
            (root / "twc_kalshi" / "hourly.csv").write_text("station,valid_utc,retrieved_at_utc\nKNYC,2026-01-01T00:00:00Z,2026-01-01T00:01:00Z\n")
            for path in ("kalshi_hourly/historical_quotes", "kalshi_hourly/kxtemplaxh/historical_quotes", "kalshi_hourly/kxtempaush/historical_quotes"):
                base = root / path; base.mkdir(parents=True)
                (base / "market_metadata.csv").write_text("market_ticker,event_ticker,open_time,settlement_source_name\nM,E,2026-01-01T00:00:00Z,\n")
                (base / "candles_hourly.csv").write_text("market_ticker\nM\n")
                (base / "trades.csv").write_text("trade_id\n")
            report = audit(root)
            self.assertFalse(report["pass"])
            self.assertFalse(report["cities"]["nyc"]["eligible_for_backtest"])

if __name__ == "__main__": unittest.main()
