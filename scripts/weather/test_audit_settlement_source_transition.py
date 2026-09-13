import json
import tempfile
import unittest
from pathlib import Path

try:
    from audit_settlement_source_transition import audit
except ModuleNotFoundError:  # direct invocation from repository root
    from scripts.weather.audit_settlement_source_transition import audit


class SettlementSourceTransitionTests(unittest.TestCase):
    def test_audits_pre_transition_rows_and_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            series = root / "series.json"
            series.write_text(json.dumps({"series": {"last_updated_ts": "2026-09-09T00:00:00Z", "product_metadata": {"important_info": {"markdown": "Effective September 10th for the 11am - 12pm ET market, resolution will transition to Synoptic Data."}}}}))
            contracts = root / "contracts.csv"
            contracts.write_text("market_ticker,target_time_utc,settlement_source_name\nKXT-1,2026-09-10T14:00:00Z,The Weather Company\n")
            result = audit(series, contracts)
            self.assertTrue(result["pass"])
            self.assertEqual(result["before_rows"], 1)
            self.assertEqual(result["after_rows"], 0)

    def test_rejects_wrong_post_transition_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "series.json").write_text(json.dumps({"series": {"last_updated_ts": "2026-09-09T00:00:00Z", "product_metadata": {"important_info": {"markdown": "Effective September 10th for the 11am - 12pm ET market, transition to Synoptic Data"}}}}))
            contracts = root / "contracts.csv"
            contracts.write_text("market_ticker,target_time_utc,settlement_source_name\nKXT-2,2026-09-10T15:00:00Z,The Weather Company\n")
            self.assertFalse(audit(root / "series.json", contracts)["pass"])


if __name__ == "__main__":
    unittest.main()
