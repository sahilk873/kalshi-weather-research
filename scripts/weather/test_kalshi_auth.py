import os
import tempfile
import unittest
from pathlib import Path

from kalshi_auth import parse_credential_file, sign_access_request


class KalshiAuthTests(unittest.TestCase):
    def test_parse_credential_file(self):
        text = "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\nAPI KEY ID: key-123\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.txt"
            path.write_text(text)
            key_id, pem = parse_credential_file(path)
        self.assertEqual(key_id, "key-123")
        self.assertIn("BEGIN PRIVATE KEY", pem)

    def test_rsa_pss_headers_with_fixture_key(self):
        pem = os.environ.get("KALSHI_TEST_PRIVATE_KEY")
        if not pem:
            self.skipTest("set KALSHI_TEST_PRIVATE_KEY for cryptography integration test")
        headers = sign_access_request("key-123", pem, timestamp_ms=1700000000000)
        self.assertEqual(headers["KALSHI-ACCESS-KEY"], "key-123")
        self.assertEqual(headers["KALSHI-ACCESS-TIMESTAMP"], "1700000000000")
        self.assertTrue(headers["KALSHI-ACCESS-SIGNATURE"])


if __name__ == "__main__":
    unittest.main()
