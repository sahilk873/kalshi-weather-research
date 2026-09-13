"""Archive bounded recent tails of public GHCNh station files.

GHCNh period-of-record files are very large.  This collector deliberately
uses HTTP Range requests, records the exact byte range and total size, and
never presents a partial response as a complete station archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-station"
STATIONS = {
    "phx": "USW00023183",
    "lv": "USW00023169",
    "nyc": "USW00094728",
    "la": "USW00023174",
    "austin": "USW00013958",
}


def fetch_tail(city: str, station: str, out_dir: Path, tail_bytes: int) -> dict:
    url = f"{BASE}/GHCNh_{station}_por.psv"
    request = urllib.request.Request(url, headers={"Range": f"bytes=-{tail_bytes}"})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
        content_range = response.headers.get("Content-Range", "")
        content_length = response.headers.get("Content-Length", "")
    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
    if not match or len(payload) != int(content_length or -1):
        raise RuntimeError(f"GHCNh server did not return a verifiable range: {content_range!r}")
    start, end, total = map(int, match.groups())
    path = out_dir / f"GHCNh_{station}_por.tail-{start}-{end}.psv"
    path.write_bytes(payload)
    return {
        "city": city,
        "station": station,
        "source_url": url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "byte_start": start,
        "byte_end": end,
        "total_bytes": total,
        # A suffix range is partial whenever it does not begin at byte zero;
        # reaching EOF is expected for a tail and does not make it complete.
        "partial": start > 0,
        "raw_path": str(path),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cities", nargs="*", default=list(STATIONS))
    parser.add_argument("--tail-bytes", type=int, default=2_000_000)
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/ghcnh"))
    args = parser.parse_args()
    if args.tail_bytes <= 0 or args.tail_bytes > 10_000_000:
        raise SystemExit("--tail-bytes must be between 1 and 10000000")
    unknown = sorted(set(args.cities) - set(STATIONS))
    if unknown:
        raise SystemExit(f"unknown cities: {unknown}")
    args.output.mkdir(parents=True, exist_ok=True)
    rows = [fetch_tail(city, STATIONS[city], args.output, args.tail_bytes) for city in args.cities]
    manifest = args.output / "manifest.json"
    manifest.write_text(json.dumps({"rows": rows}, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"manifest": str(manifest), "rows": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
