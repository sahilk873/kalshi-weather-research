import json, tempfile, unittest
from pathlib import Path
from parse_weather_index import parse

class ParseWeatherIndexTests(unittest.TestCase):
    def test_converts_millisecond_timestamp_and_keeps_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"nyc.json"; path.write_text(json.dumps({"city":"nyc","config_version":"v1","timeseries":[{"t":0,"v":70.125,"contributors":8,"status":"normal"}]}))
            rows=parse(path,{"city":"nyc","retrieved_at_utc":"2026-01-01T00:00:00Z","sha256":"h"})
            self.assertEqual(rows[0]["timestamp_utc"],"1970-01-01T00:00:00Z"); self.assertEqual(rows[0]["source_receipt_time"],"2026-01-01T00:00:00Z")

if __name__ == "__main__": unittest.main()
