import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collect_contract_terms import collect


class ContractTermsTests(unittest.TestCase):
    def test_archives_and_hashes_referenced_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            series = root / "series.json"
            series.write_text(json.dumps({"series": {"ticker": "KXTEMPNYCH", "contract_url": "https://example/contract", "contract_terms_url": "https://example/terms"}}))
            class Response:
                headers = {"Content-Type": "application/pdf"}
                def __enter__(self): return self
                def __exit__(self, *_): return False
                def read(self): return b"pdf-bytes"
            with patch("collect_contract_terms.urlopen", return_value=Response()):
                result = collect(series, root / "terms")
            self.assertEqual(len(result["files"]), 2)
            self.assertTrue(all(row["status"] == "ok" for row in result["files"]))
            self.assertTrue(all(Path(row["path"]).exists() for row in result["files"]))


if __name__ == "__main__":
    unittest.main()
