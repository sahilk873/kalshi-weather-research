"""Create an integrity manifest for downloaded GHCNh yearly PSV files."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

STATIONS = {
    "phx": "USW00023183", "lv": "USW00023169", "nyc": "USW00094728",
    "la": "USW00023174", "austin": "USW00013958",
}
BASE = "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year"


def inventory(root: Path, year: int, cities: list[str]) -> dict:
    rows = []
    for city in cities:
        station = STATIONS[city]
        path = root / f"GHCNh_{station}_{year}.psv"
        if not path.exists():
            raise FileNotFoundError(path)
        data = path.read_bytes()
        rows.append({
            "city": city, "station": station, "year": year,
            "source_url": f"{BASE}/{year}/psv/{path.name}",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "bytes": len(data), "raw_path": str(path),
            "sha256": hashlib.sha256(data).hexdigest(), "complete_year_file": True,
        })
    return {"rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--cities", nargs="*", default=list(STATIONS))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    unknown = sorted(set(args.cities) - set(STATIONS))
    if unknown:
        raise SystemExit(f"unknown cities: {unknown}")
    args.output.write_text(json.dumps(inventory(args.input, args.year, args.cities), indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
