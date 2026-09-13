import tempfile,unittest
from pathlib import Path
from summarize_ecmwf_ensemble import summarize
class EcmwfSummaryTest(unittest.TestCase):
 def test_member_count_and_probability(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); (p/'i.csv').write_text('model,city,initialization_time_utc,valid_time_utc,lead_hours,variable,value,raw_path,sha256\nM,phx,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,0,temperature_2m,70,x,h\nM,phx,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,0,temperature_2m,90,x,h\n'); out=p/'o.csv'; self.assertEqual(summarize(p/'i.csv',out),1); self.assertIn(',0.5,',out.read_text())
if __name__=='__main__': unittest.main()
