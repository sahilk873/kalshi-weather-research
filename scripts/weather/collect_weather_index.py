"""Archive Kalshi public Weather Index responses and explicit failures."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

BASE = "https://external-api.kalshi.com/trade-api/v2/live_data/weather"

def collect(cities: list[str], output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True); results=[]
    for city in cities:
        url=f"{BASE}/{city}"; row={"city":city,"source_url":url,"retrieved_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z")}
        try:
            with urlopen(url, timeout=60) as response: data=response.read(); status=response.status
            payload=json.loads(data); path=output/f"{city}.json"; path.write_bytes(data)
            row.update({"status":status,"raw_path":str(path),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"config_version":payload.get("config_version"),"timeseries_rows":len(payload.get("timeseries",[]))})
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            row.update({"status":getattr(exc,"code",None),"error":str(exc)})
        results.append(row)
    manifest=output/"manifest.json"; manifest.write_text(json.dumps({"rows":results},indent=2,sort_keys=True)+"\n"); return {"manifest":str(manifest),"rows":len(results)}

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--cities",nargs="+",default=["nyc","la","austin"]); p.add_argument("--output",type=Path,default=Path("data/weather_research/weather_index")); a=p.parse_args(); print(json.dumps(collect(a.cities,a.output),sort_keys=True))
if __name__ == "__main__": main()
