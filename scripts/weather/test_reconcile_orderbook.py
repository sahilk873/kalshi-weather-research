import unittest

from reconcile_orderbook import reconcile


class ReconcileOrderbookTests(unittest.TestCase):
    def test_current_dollar_schema_matches_rest_fp_levels(self):
        ws = {"yes_dollars_fp": [["0.40", "2"]], "no_dollars_fp": [["0.60", "1"]]}
        rest = {"orderbook_fp": {"yes": [[40, 2]], "no": [[60, 1]]}}
        result = reconcile(ws, rest)
        self.assertTrue(result["pass"])
        self.assertEqual(result["websocket_levels"], 2)

    def test_quantity_mismatch_is_explicit(self):
        result = reconcile({"yes": [[40, 2]], "no": []}, {"yes": [[40, 1]], "no": []})
        self.assertFalse(result["pass"])
        self.assertEqual(result["mismatches"][0]["price_cents"], 40)

    def test_rest_dollars_schema_matches_websocket_fp(self):
        ws = {"yes_dollars_fp": [["0.40", "2"]], "no_dollars_fp": []}
        rest = {"orderbook_fp": {"yes_dollars": [["0.4000", "2.00"]], "no_dollars": []}}
        self.assertTrue(reconcile(ws, rest)["pass"])


if __name__ == "__main__":
    unittest.main()
