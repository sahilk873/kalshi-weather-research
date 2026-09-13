import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collect_awc_metar import collect


class Response:
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self):
        return json.dumps([{"icaoId": "KJFK", "obsTime": 0,
                            "temp": 20, "dewp": 10, "wdir": 180,
                            "wspd": 8, "rawOb": "KJFK TEST"}]).encode()


class AWCMetarTests(unittest.TestCase):
    def test_duplicate_observation_key_is_retained_once(self):
        with tempfile.TemporaryDirectory() as directory, patch("collect_awc_metar.urlopen", return_value=Response()):
            collect(["KJFK"], Path(directory), hours=1)
            collect(["KJFK"], Path(directory), hours=1)
            with (Path(directory) / "metar.csv").open() as handle:
                self.assertEqual(len(list(__import__("csv").DictReader(handle))), 1)

    def test_preserves_raw_hash_and_separate_receipt(self):
        with tempfile.TemporaryDirectory() as directory, patch("collect_awc_metar.urlopen", return_value=Response()):
            result = collect(["KJFK"], Path(directory), hours=1)
            self.assertEqual(result["rows"], 1)
            with (Path(directory) / "metar.csv").open() as handle:
                row = list(__import__("csv").DictReader(handle))[0]
            self.assertEqual(row["valid_utc"], "1970-01-01T00:00:00Z")
            self.assertTrue(row["receipt_utc"])
            self.assertTrue(row["raw_path"].endswith(".json"))
            self.assertTrue((Path(directory) / result["raw_path"].split("/")[-1]).exists())


if __name__ == "__main__":
    unittest.main()
