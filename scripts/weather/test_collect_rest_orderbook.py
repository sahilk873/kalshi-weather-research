import json
import unittest
from pathlib import Path

from collect_rest_orderbook import collect_rest_orderbooks


class _Response:
    def __init__(self, body: bytes):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.body


class CollectRestOrderbookTests(unittest.TestCase):
    def test_collect_archives_hash_and_receipt(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            credential = tmp_path / "cred.txt"
            credential.write_text("API KEY ID: test\n-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n")
            import collect_rest_orderbook
            original_parse = collect_rest_orderbook.parse_credential_file
            original_sign = collect_rest_orderbook.sign_access_request
            collect_rest_orderbook.parse_credential_file = lambda _: ("key", "pem")
            collect_rest_orderbook.sign_access_request = lambda *a, **k: {"X": "signed"}
            try:
                body = b'{"orderbook_fp":{"yes":[[42,3]],"no":[]}}'
                seen = {}
                def opener(request, timeout):
                    seen["url"] = request.full_url
                    seen["headers"] = dict(request.header_items())
                    return _Response(body)
                result = collect_rest_orderbooks(["KXTEMPNYCH-TEST"], credential_file=credential,
                                                 output_dir=tmp_path / "out", opener=opener)
                raw = Path(result["rows"][0]["path"])
                self.assertEqual(raw.read_bytes(), body)
                self.assertTrue(result["rows"][0]["sha256"])
                self.assertEqual(result["availability_basis"], "receipt_upper_bound")
                self.assertIn("orderbook", seen["url"])
                self.assertEqual(json.loads(Path(result["manifest_path"]).read_text())["rows"][0]["ticker"], "KXTEMPNYCH-TEST")
            finally:
                collect_rest_orderbook.parse_credential_file = original_parse
                collect_rest_orderbook.sign_access_request = original_sign


if __name__ == "__main__":
    unittest.main()
