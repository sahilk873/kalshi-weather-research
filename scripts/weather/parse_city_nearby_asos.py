"""Parse city-nearby ASOS archives while preserving raw METAR and remarks."""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from common import ensure_runtime_dirs, parse_utc_iso, to_float, utc_iso  # noqa: E402
from iem_asos import PARSED_COLUMNS, parse_remarks  # noqa: E402

ZONES = {"nyc": "America/New_York", "la": "America/Los_Angeles", "austin": "America/Chicago"}
NUMERIC = {"tmpf", "dwpf", "relh", "drct", "sknt", "gust", "p01i", "alti", "mslp", "vsby", "skyl1", "skyl2", "skyl3", "skyl4"}
FIELDS = ["station", "valid", "tmpf", "dwpf", "relh", "drct", "sknt", "gust", "p01i", "alti", "mslp", "vsby", "skyc1", "skyc2", "skyc3", "skyc4", "skyl1", "skyl2", "skyl3", "skyl4", "wxcodes", "snowdepth", "metar"]
REMARKS = [c for c in PARSED_COLUMNS if c.startswith("remark_")]
OUTPUT = ["city", "station", "valid_utc", "local_date", *FIELDS[2:-1], "raw_metar", *REMARKS]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", default=None)
    args = ap.parse_args()
    dirs = ensure_runtime_dirs()
    raw = Path(args.raw_dir) if args.raw_dir else dirs["research"] / "city_nearby_asos" / "raw"
    rows, seen = [], set()
    for path in sorted(raw.glob("*.csv")):
        city = path.name.split("_", 1)[0]
        if city not in ZONES:
            continue
        tz = ZoneInfo(ZONES[city])
        with path.open(newline="", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for rawrow in reader:
                dt = parse_utc_iso((rawrow.get("valid") or "").replace(" ", "T"))
                if dt is None:
                    continue
                station = (rawrow.get("station") or "").strip()
                key = (city, station, utc_iso(dt))
                if key in seen:
                    continue
                seen.add(key)
                row = {"city": city, "station": station, "valid_utc": utc_iso(dt), "local_date": dt.astimezone(tz).date().isoformat()}
                for f in FIELDS[2:-1]:
                    value = rawrow.get(f, "")
                    row[f] = to_float(value) if f in NUMERIC else value.strip()
                metar = (rawrow.get("metar") or "").strip()
                row["raw_metar"] = metar
                row.update(parse_remarks(metar))
                rows.append(row)
    rows.sort(key=lambda r: (r["city"], r["station"], r["valid_utc"]))
    outdir = dirs["research"] / "city_nearby_asos"
    outdir.mkdir(parents=True, exist_ok=True)
    outpath = outdir / "nearby_asos_parsed.csv"
    with outpath.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT)
        writer.writeheader(); writer.writerows(rows)
    print(f"wrote {outpath} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
