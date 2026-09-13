import json
import tempfile
import unittest
from pathlib import Path

from reconcile_historical_quote_raw import reconcile


class RawReconciliationTests(unittest.TestCase):
    def test_orphan_payload_is_quarantined_not_promoted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); raw = root / "raw"; raw.mkdir()
            (root / "raw_manifest.jsonl").write_text("")
            (raw / "orphan.json").write_text('{"trades": []}\n')
            result = reconcile(root)
            self.assertEqual(result["quarantined"], 1)
            rows = [json.loads(line) for line in (root / "raw_quarantine_manifest.jsonl").read_text().splitlines()]
            self.assertEqual(rows[0]["status"], "quarantined")
            self.assertEqual(rows[0]["reason"], "interrupted_rate_limited_batch")
            self.assertEqual(reconcile(root)["quarantined"], 1)


if __name__ == "__main__":
    unittest.main()
