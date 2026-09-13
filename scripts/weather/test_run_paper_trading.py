import json
import tempfile
import unittest
from pathlib import Path
from run_paper_trading import ingest_once


VALID = {
    "decision_ts": "2026-09-12T12:00:00Z", "feature_version": "f1",
    "model_version": "m1", "calibrator_version": "c1",
    "source_run_ids": ["run"], "observation_ids": ["obs"],
    "rules_hash": "rules", "code_commit": "HEAD", "prediction": 0.6,
    "market_ticker": "M", "target_time_utc": "2026-09-12T13:00:00Z",
}


class PaperRunnerTests(unittest.TestCase):
    def test_ingest_validates_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); manifest = root / "manifest.json"; manifest.write_text(json.dumps(VALID))
            execution = root / "execution.csv"
            execution.write_text("market_ticker,scenario,decision_time_utc,execution_candle_end,signal_yes_ask,fill_price,fee,settled_yes,one_contract_net_payoff\nM,base,2026-09-12T12:00:00Z,2,.4,.5,.01,true,.49\n")
            ledger = root / "ledger.jsonl"
            self.assertEqual(ingest_once(execution, manifest, ledger), 2)
            self.assertEqual(ingest_once(execution, manifest, ledger), 0)
            self.assertEqual(len(ledger.read_text().splitlines()), 2)


if __name__ == "__main__": unittest.main()
