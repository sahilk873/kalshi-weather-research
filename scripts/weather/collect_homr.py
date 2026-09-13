"""Archive NCEI HOMR station histories for the registered stations."""
from __future__ import annotations
import argparse, hashlib, json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATIONS = {"phx":"USW00023183", "lv":"USW00023169", "nyc":"USW00094728", "la":"USW00023174", "austin":"USW00013958"}
BASE = "https://www.ncei.noaa.gov/access/homr/services/station/search"


def collect(city: str, station: str, output: Path) -> dict:
    query = urllib.parse.urlencode({"qid": f"GHCND:{station}", "date": "all"})
    url = f"{BASE}?{query}"
    with urllib.request.urlopen(url, timeout=120) as response:
        payload = response.read()
    parsed = json.loads(payload)
    if not isinstance(parsed.get("stationCollection", {}).get("stations"), list):
        raise ValueError(f"unexpected HOMR response for {station}")
    path = output / f"homr_{station}.json"
    path.write_bytes(payload)
    return {"city": city, "station": station, "source_url": url,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "bytes": len(payload), "raw_path": str(path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "station_records": len(parsed["stationCollection"]["stations"])}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--cities", nargs="*", default=list(STATIONS)); p.add_argument("--output", type=Path, required=True); a=p.parse_args()
    unknown=sorted(set(a.cities)-set(STATIONS))
    if unknown: raise SystemExit(f"unknown cities: {unknown}")
    a.output.mkdir(parents=True, exist_ok=True)
    rows=[collect(city, STATIONS[city], a.output) for city in a.cities]
    manifest=a.output/"manifest.json"; manifest.write_text(json.dumps({"rows":rows},indent=2,sort_keys=True)+"\n"); print(manifest)


if __name__ == "__main__": main()
