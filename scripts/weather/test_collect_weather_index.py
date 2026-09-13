import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from collect_weather_index import collect

class Response:
    status=200
    def __enter__(self): return self
    def __exit__(self,*args): return None
    def read(self): return b'{"city":"nyc","timeseries":[{"t":1}]}'

class WeatherIndexTests(unittest.TestCase):
    def test_archives_hash_and_manifest(self):
        with tempfile.TemporaryDirectory() as d, patch("collect_weather_index.urlopen",return_value=Response()):
            result=collect(["nyc"],Path(d)); self.assertEqual(result["rows"],1); self.assertTrue((Path(d)/"nyc.json").exists()); self.assertEqual(json_load(Path(d)/"manifest.json")["rows"][0]["timeseries_rows"],1)

def json_load(path):
    import json
    return json.loads(path.read_text())

if __name__ == "__main__": unittest.main()
