"""Backfill authoritative GHCN-Daily TMAX/TMIN labels for NYC, LA, and Austin.

This is deliberately separate from ``ghcn_daily.py`` so the former PHX/LAS
dataset and its station configuration are not changed.  Values are NOAA
NCEI GHCN-Daily final labels in Fahrenheit; ``label_available_ts`` is a
conservative D+36h gate because the static .dly files do not expose a
per-record publication timestamp.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

from common import http_get, utcnow  # noqa: E402
from ghcn_daily import COLUMNS, fetch_stations_meta, parse_dly, pivoted, station_meta  # noqa: E402
from stations import GHCN_ALL_URL  # noqa: E402

CITY_STATIONS = {
    # KNYC / Central Park is the canonical NYC climate station.
    "nyc": ("New York City", "USW00094728"),
    "la": ("Los Angeles", "USW00023174"),
    "austin": ("Austin", "USW00013904"),
}


def fetch_dly(ghcn_id: str, raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"{ghcn_id}.dly"
    if not dest.exists() or dest.stat().st_size == 0:
        dest.write_bytes(http_get(f"{GHCN_ALL_URL}/{ghcn_id}.dly", timeout=180))
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cities", nargs="*", default=list(CITY_STATIONS),
                    choices=sorted(CITY_STATIONS))
    ap.add_argument("--since", help="optional inclusive YYYY-MM-DD filter")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[2] / "data" / "weather_research" / "ghcn_city"
    raw = root / "raw"
    root.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    meta_path = fetch_stations_meta(raw)
    rows = []
    station_city = {}
    for key in args.cities:
        city, station = CITY_STATIONS[key]
        path = fetch_dly(station, raw)
        parsed = parse_dly(path)
        if args.since:
            parsed = [r for r in parsed if r["date"] >= args.since]
        rows.extend(parsed)
        station_city[station] = key
        print(f"{key}: {station_meta(meta_path, station)}; parsed={len(parsed)}")
    output = root / (f"labels_daily_since_{args.since}.csv" if args.since else "labels_daily.csv")
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(pivoted(rows, station_city))
    print(f"wrote {output} rows={sum(1 for _ in output.open()) - 1} fetched_at={utcnow()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
