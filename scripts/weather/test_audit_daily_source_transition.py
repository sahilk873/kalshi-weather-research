import unittest
from audit_daily_source_transition import audit


class DailySourceAuditTests(unittest.TestCase):
    def test_current_twc_rule_passes_and_old_metadata_fails_closed(self):
        payload = {"KXHIGHNY": {"markets": [{"ticker": "X", "event_ticker": "KXHIGHNY-26SEP13", "rules_primary": "CLINYC according to The Weather Company"}, {"ticker": "Y", "event_ticker": "KXHIGHNY-26AUG13", "rules_primary": "NWS"}]}}
        result = audit(payload)
        self.assertEqual(result["verified_rows"], 1)
        self.assertEqual(result["rejection_reasons"]["historical_source_metadata_not_retained"], 1)
        self.assertFalse(result["pass"])


if __name__ == "__main__":
    unittest.main()
