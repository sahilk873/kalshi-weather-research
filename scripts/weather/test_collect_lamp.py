import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collect_lamp import collect


class LAMPTests(unittest.TestCase):
    def test_discovers_latest_cycle_and_hashes_payload(self):
        responses = {
            "https://nomads.ncep.noaa.gov/pub/data/nccf/com/lmp/prod/": b'<a href="lmp.20260911/">x</a><a href="lmp.20260912/">x</a>',
            "https://nomads.ncep.noaa.gov/pub/data/nccf/com/lmp/prod/lmp.20260912/": b'<a href="lmp.t1900z.lavtxt.ascii">x</a><a href="lmp.t1930z.lavtxt.ascii">x</a>',
            "https://nomads.ncep.noaa.gov/pub/data/nccf/com/lmp/prod/lmp.20260912/lmp.t1930z.lavtxt.ascii": b'LAMP TEST',
        }
        with tempfile.TemporaryDirectory() as directory, patch("collect_lamp._get", side_effect=lambda url: responses[url]):
            result = collect(Path(directory))
            self.assertEqual(result["cycle_file"], "lmp.t1930z.lavtxt.ascii")
            self.assertTrue((Path(directory) / result["cycle_file"]).exists())


if __name__ == "__main__":
    unittest.main()
