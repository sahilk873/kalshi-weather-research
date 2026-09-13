import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collect_ghcnh_tail import fetch_tail


class _Response:
    headers = {"Content-Range": "bytes 10-19/100", "Content-Length": "10"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b"0123456789"


class GhcnhTailTest(unittest.TestCase):
    @patch("collect_ghcnh_tail.urllib.request.urlopen", return_value=_Response())
    def test_records_partial_range_and_hash(self, open_url):
        with tempfile.TemporaryDirectory() as directory:
            row = fetch_tail("phx", "USW00023183", Path(directory), 10)
            self.assertTrue(row["partial"])
            self.assertEqual(row["byte_start"], 10)
            self.assertEqual(Path(row["raw_path"]).read_bytes(), b"0123456789")
            self.assertEqual(open_url.call_args.args[0].headers["Range"], "bytes=-10")


if __name__ == "__main__":
    unittest.main()
