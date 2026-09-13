import tempfile, unittest, json
from pathlib import Path
from build_model_runs import build

class ModelRunTests(unittest.TestCase):
    def test_materializes_unobserved_publication_method(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'forecasts').mkdir(); (root/'forecasts'/'manifest.csv').write_text('model,initialization_time_utc,ingested_at_utc,raw_path,request_url\nhrrr,2026-01-01T00:00:00Z,2026-01-01T01:00:00Z,x,u\n')
            rows=build(root); self.assertEqual(len(rows),1); self.assertEqual(rows[0]['published_ts_method'],'unobserved')
if __name__ == '__main__': unittest.main()
