import json, tempfile, unittest
from pathlib import Path
from operational_readiness import evaluate

def healthy():
    return {"feed_age_seconds": {"awc": 2, "nearby": 4}, "model_run_age_seconds": {"hrrr": 100},
            "probability_consistent": True, "clock_drift_seconds": 0.4,
            "orderbook_sequence_gap_resolved": True, "settlement_rules_verified": True,
            "calibration_error": 0.03, "daily_drawdown": 0.01}

class OperationalReadinessTest(unittest.TestCase):
    def test_healthy_snapshot_allows_research_trading(self):
        result = evaluate(healthy()); self.assertTrue(result["allow_trading"]); self.assertEqual(result["reason_codes"], [])
    def test_missing_and_stale_telemetry_fails_closed(self):
        snap = healthy(); snap.pop("feed_age_seconds"); snap["probability_consistent"] = False; snap["daily_drawdown"] = 0.2
        result = evaluate(snap); self.assertFalse(result["allow_trading"]); self.assertIn("missing_feed_age", result["reason_codes"]); self.assertIn("drawdown_limit", result["reason_codes"])
    def test_reason_order_is_deterministic(self):
        self.assertEqual(evaluate({}), evaluate({}))
    def test_threshold_override(self):
        snap = healthy(); snap["feed_age_seconds"]["awc"] = 10
        self.assertFalse(evaluate(snap, {"max_feed_age_seconds": 5})["allow_trading"])
    def test_cli_writes_json(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); inp = root / "snapshot.json"; out = root / "out.json"; inp.write_text(json.dumps(healthy()))
            import subprocess, sys
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("operational_readiness.py")), str(inp), "--output", str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr); self.assertTrue(json.loads(out.read_text())["allow_trading"])

if __name__ == "__main__": unittest.main()
