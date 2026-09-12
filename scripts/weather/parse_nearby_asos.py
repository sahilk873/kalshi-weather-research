"""Normalize the small nearby-ASOS network raw archives for PHX and LV.

Reads every raw IEM CSV under ``data/weather_research/nearby_asos/raw`` and
writes a single normalized table. This module mirrors the settlement-station
parser (``iem_asos.py``) conventions:

- ``valid_utc`` is stored as canonical ``YYYY-MM-DDTHH:MM:SSZ`` UTC.
- ``local_date`` uses the owning city's IANA zone (America/Phoenix /
  America/Los_Angeles) so it lines up with Kalshi local outcome dates.
- Temperatures/winds/pressures are floats (or empty); ``M``/``T``/empty are
  missing, never zero.
- Standard ASOS remark groups (precise T/dew point, 6/24h extrema, pressure
  tendency) are extracted from the raw METAR with the same parser used for the
  settlement stations.

Output:
- data/weather_research/nearby_asos/nearby_asos_parsed.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

# ruff: noqa: E402
import common  # noqa: E402
from common import ensure_runtime_dirs, parse_utc_iso, to_float, utc_iso, utcnow  # noqa: E402
from iem_asos import PARSED_COLUMNS, parse_remarks  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

# city prefix -> (city key, IANA zone) for the raw filename, and the exact set
# of non-settlement stations expected for that city.
CITY_TZ = {
    "phx": ("phx", "America/Phoenix"),
    "lv": ("lv", "America/Los_Angeles"),
}
CITY_STATIONS = {
    "phx": frozenset({"SDL", "CHD", "FFZ"}),
    "lv": frozenset({"HND", "VGT", "LSV"}),
}

INPUT_FIELDS = [
    "station", "valid", "tmpf", "dwpf", "relh", "drct", "sknt", "gust",
    "p01i", "alti", "mslp", "vsby",
    "skyc1", "skyc2", "skyc3", "skyc4",
    "skyl1", "skyl2", "skyl3", "skyl4",
    "wxcodes", "snowdepth", "metar",
]

REMARK_COLS = [c for c in PARSED_COLUMNS if c.startswith("remark_")]
REQUIRED_INPUT = [
    "station", "valid", "tmpf", "dwpf", "drct", "sknt", "gust",
    "p01i", "alti", "mslp", "vsby",
    "skyc1", "skyc2", "skyc3", "skyc4",
    "skyl1", "skyl2", "skyl3", "skyl4",
    "wxcodes", "metar",
]

OUTPUT_FIELDS = [
    "city", "station", "valid_utc", "local_date",
    "tmpf", "dwpf", "relh", "drct", "sknt", "gust",
    "p01i", "alti", "mslp", "vsby",
    "skyc1", "skyc2", "skyc3", "skyc4",
    "skyl1", "skyl2", "skyl3", "skyl4",
    "wxcodes", "snowdepth", "raw_metar",
] + REMARK_COLS

_NUMERIC = [
    "tmpf", "dwpf", "relh", "drct", "sknt", "gust",
    "p01i", "alti", "mslp", "vsby", "skyl1", "skyl2", "skyl3", "skyl4",
]


def parse_one(city: str, tz: ZoneInfo, raw: dict[str, str],
              fieldmap: dict[str, str]) -> dict | None:
    """Normalize one IEM CSV row; None when `valid` cannot be parsed."""
    valid_s = (raw.get(fieldmap.get("valid", "valid")) or "").strip()
    if not valid_s:
        return None
    utc_dt = parse_utc_iso(valid_s.replace(" ", "T"))
    if utc_dt is None:
        return None
    metar = (raw.get(fieldmap.get("metar", "metar")) or "").strip()
    row: dict = {
        "city": city,
        "station": (raw.get(fieldmap.get("station", "station")) or "").strip(),
        "valid_utc": utc_iso(utc_dt),
        "local_date": utc_dt.astimezone(tz).date().isoformat(),
    }
    for f in OUTPUT_FIELDS:
        if f in row:
            continue
        src = fieldmap.get(f)
        if f in _NUMERIC:
            row[f] = to_float(raw.get(src)) if src else None
        else:
            row[f] = (raw.get(src) or "").strip() if src is not None else ""
    row["raw_metar"] = metar
    # Missing remark columns start as null; parse_remarks fills them from the
    # raw METAR, leaving groups that are absent from the message as null.
    row.update(parse_remarks(metar))
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", default=None,
                    help="raw nearby-ASOS directory (default: standard layout)")
    args = ap.parse_args()

    dirs = ensure_runtime_dirs()
    raw_dir = Path(args.raw_dir) if args.raw_dir else \
        dirs["research"] / "nearby_asos" / "raw"
    if not raw_dir.is_dir():
        print(f"no raw nearby ASOS directory at {raw_dir}; "
              "run collect_nearby_asos.py first", file=sys.stderr)
        return 1
    out_path = dirs["research"] / "nearby_asos" / "nearby_asos_parsed.csv"

    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    flagged_stations: set[tuple[str, str]] = set()
    for path in sorted(raw_dir.glob("*.csv")):
        prefix = path.name.split("_", 1)[0]
        if prefix not in CITY_TZ:
            raise SystemExit(f"unknown city prefix {prefix!r} in {path.name!r}")
        city, tz_name = CITY_TZ[prefix]
        tz = ZoneInfo(tz_name)
        with path.open(newline="", errors="replace") as fh:
            reader = csv.DictReader(fh)
            missing = [f for f in REQUIRED_INPUT if f not in reader.fieldnames]
            if missing:
                raise SystemExit(f"missing columns {missing} in {path.name!r}")
            fieldmap = {k.strip().lower(): k for k in (reader.fieldnames or [])}
            for raw in reader:
                row = parse_one(city, tz, raw, fieldmap)
                if row is None:
                    continue
                key = (row["station"], row["valid_utc"])
                if key in seen:
                    continue
                seen.add(key)
                expected = CITY_STATIONS[city]
                if row["station"] not in expected:
                    flagged_stations.add((city, row["station"]))
                rows.append(row)

    rows.sort(key=lambda r: (r["city"], r["station"], r["valid_utc"]))
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {out_path} ({len(rows)} rows); fetched_at={utcnow()}")
    for city, station in sorted(flagged_stations):
        print(f"warning: unexpected station {station!r} under city {city!r} "
              f"(expected {sorted(CITY_STATIONS[city])})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
