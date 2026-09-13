import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from collect_homr import collect


class _Response:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps({"stationCollection": {"stations": [{}]}}).encode()


class HomrTest(unittest.TestCase):
    @patch("collect_homr.urllib.request.urlopen", return_value=_Response())
    def test_archives_valid_history_and_hash(self, opener):
        with tempfile.TemporaryDirectory() as d:
            row=collect("phx", "USW00023183", Path(d))
            self.assertEqual(row["station_records"], 1)
            self.assertEqual(len(row["sha256"]), 64)
            self.assertIn("date=all", opener.call_args.args[0])


if __name__ == "__main__": unittest.main()
