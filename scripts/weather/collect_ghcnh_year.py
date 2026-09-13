"""Download complete, immutable GHCNh yearly station files with provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year"
STATIONS = {
    "phx": "USW00023183", "lv": "USW00023169", "nyc": "USW00094728",
    "la": "USW00023174", "austin": "USW00013904",
}


def fetch_year(city: str, station: str, year: int, output: Path) -> dict:
    url = f"{BASE}/{year}/psv/GHCNh_{station}_{year}.psv"
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"GHCNh_{station}_{year}.psv"
    with urllib.request.urlopen(url, timeout=300) as response:
        data = response.read()
    if not data.startswith(b"STATION"):
        raise RuntimeError(f"unexpected GHCNh payload for {url}")
    path.write_bytes(data)
    return {
        "city": city, "station": station, "year": year,
        "source_url": url, "raw_path": str(path), "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "complete_year_file": True,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--cities", nargs="*", default=list(STATIONS))
    p.add_argument("--output", type=Path, default=Path("data/weather_research/ghcnh/by_year"))
    args = p.parse_args()
    if not 1900 <= args.year <= 2100:
        raise SystemExit("year must be between 1900 and 2100")
    unknown = sorted(set(args.cities) - set(STATIONS))
    if unknown:
        raise SystemExit(f"unknown cities: {unknown}")
    year_dir = args.output / str(args.year)
    rows = [fetch_year(c, STATIONS[c], args.year, year_dir) for c in args.cities]
    manifest = year_dir / "manifest.json"
    manifest.write_text(json.dumps({"rows": rows}, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"manifest": str(manifest), "rows": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
