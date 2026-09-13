import unittest
from build_settled_market_labels import build

class SettledLabelsTest(unittest.TestCase):
    def test_one_yes_market_and_duplicate_guard(self):
        outcomes = [{"event_ticker": "E", "city": "phx", "outcome_local_date": "2025-01-01", "market_ticker": "M1", "settled_yes": "yes"}, {"event_ticker": "E", "city": "phx", "outcome_local_date": "2025-01-01", "market_ticker": "M2", "settled_yes": "yes"}]
        labels, rejected = build(outcomes, [{"city": "phx", "date": "2025-01-01", "label_available_ts": "2025-01-02T12:00:00Z"}])
        self.assertEqual(labels[0]["settled_market_ticker"], "M1"); self.assertEqual(rejected[0]["reason"], "multiple_settled_yes")

if __name__ == "__main__": unittest.main()
