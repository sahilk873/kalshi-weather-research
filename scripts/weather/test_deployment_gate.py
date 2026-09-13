import unittest
from deployment_gate import evaluate


class DeploymentGateTests(unittest.TestCase):
    def test_missing_evidence_fails_closed(self):
        result = evaluate({})
        self.assertFalse(result["pass"])
        self.assertFalse(result["authorized"])
        self.assertIn("positive_oos_net_ev", result["failed_checks"])

    def test_complete_evidence_still_not_authorized(self):
        snapshot = {
            "positive_oos_net_ev": True, "positive_test_windows": 3,
            "brier_improvement": 0.02, "reliability_error": 0.03,
            "regime_independent": True, "probability_perturbation_robust": True,
            "slippage_robust": True, "fees_robust": True,
            "live_paper_matches_backtest": True, "outage_killswitch_tested": True,
            "contract_rules_verified": True,
        }
        result = evaluate(snapshot)
        self.assertTrue(result["pass"])
        self.assertFalse(result["authorized"])


if __name__ == "__main__": unittest.main()
