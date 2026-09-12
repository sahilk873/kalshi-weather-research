"""Solar geometry features (sunrise / sunset / daylight) for PHX and LAS.

These are *calculated geometry* values only -- deterministic functions of
date, latitude and longitude using the public NOAA solar calculation
(NWS/NOAA sunrise equation as published by NOAA GML, see data_sources.md).
They contain no observational data and therefore cannot be "fabricated";
they are standard planetary geometry. No solar-radiation measurements are
claimed or generated, because we do not have a credentialed radiation feed.

Features per local calendar date:
- solar_noon_utc, sunrise_utc, sunset_utc   (UTC ISO times)
- sunrise_local, sunset_local               (local wall-clock ISO times)
- daylength_min, declination_deg, eqtime_min

Output:
- data/weather_research/solar/solar_features.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

# ruff: noqa: E402
from common import ensure_runtime_dirs, utcnow  # noqa: E402
from stations import DEFAULT_CITIES, get_cities  # noqa: E402

REF_SOLAR_ZENITH = 90.833  # standard NOAA astronomical sunrise/sunset zenith


def _daily_fraction(d: date) -> float:
    gamma = 2.0 * math.pi / 365.0 * (d.timetuple().tm_yday - 1 + (12.0 - 12.0) / 24.0)
    return gamma


def _eqtime_decl(gamma: float) -> tuple[float, float]:
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    return eqtime, math.degrees(decl)


def _minutes_to_utc_dt(d: date, minutes: float) -> datetime:
    base = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return base + timedelta(minutes=minutes)


def solar_features(d: date, lat: float, lon: float):
    gamma = _daily_fraction(d)
    eqtime, decl = _eqtime_decl(gamma)
    ha_deg = math.degrees(math.acos(
        math.cos(math.radians(REF_SOLAR_ZENITH))
        / (math.cos(math.radians(lat)) * math.cos(math.radians(decl)))
        - math.tan(math.radians(lat)) * math.tan(math.radians(decl))
    ))
    # times in minutes relative to 00:00 UTC (NOAA formulation)
    noon_min = 720.0 - 4.0 * lon - eqtime
    rise_min = 720.0 - 4.0 * (lon + ha_deg) - eqtime
    set_min = 720.0 - 4.0 * (lon - ha_deg) - eqtime
    return {
        "solar_noon_utc": _minutes_to_utc_dt(d, noon_min)
        .isoformat().replace("+00:00", "Z"),
        "sunrise_utc": _minutes_to_utc_dt(d, rise_min)
        .isoformat().replace("+00:00", "Z"),
        "sunset_utc": _minutes_to_utc_dt(d, set_min)
        .isoformat().replace("+00:00", "Z"),
        "daylength_min": round(8.0 * ha_deg, 3),
        "declination_deg": round(decl, 5),
        "eqtime_min": round(eqtime, 4),
    }


def to_local(iso_utc: str, tz_name: str) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(tz_name)).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cities", nargs="*", default=None)
    ap.add_argument("--start", default=None,
                    help="start local date YYYY-MM-DD (default: 1933-01-01)")
    ap.add_argument("--end", default=None,
                    help="end local date YYYY-MM-DD (default: today UTC)")
    args = ap.parse_args()

    dirs = ensure_runtime_dirs()
    cities = get_cities(args.cities or DEFAULT_CITIES)

    end = (date.fromisoformat(args.end) if args.end
           else datetime.now(timezone.utc).date())
    start = date.fromisoformat(args.start) if args.start else date(1933, 1, 1)
    if end < start:
        raise SystemExit(f"--end {end} before --start {start}")

    col_names = [
        "city", "date", "lat", "lon",
        "solar_noon_utc", "sunrise_utc", "sunset_utc",
        "sunrise_local", "sunset_local",
        "daylength_min", "declination_deg", "eqtime_min",
    ]

    out = dirs["solar_out"] / "solar_features.csv"
    n = 0
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=col_names)
        writer.writeheader()
        cur = start
        while cur <= end:
            for city in cities:
                feats = solar_features(cur, city.lat, city.lon)
                row = {
                    "city": city.key,
                    "date": cur.isoformat(),
                    "lat": city.lat,
                    "lon": city.lon,
                    **feats,
                    "sunrise_local": to_local(feats["sunrise_utc"], city.tz_name),
                    "sunset_local": to_local(feats["sunset_utc"], city.tz_name),
                }
                writer.writerow(row)
                n += 1
            cur += timedelta(days=1)
    print(f"wrote {out} ({n} rows, {start}..{end})")
    print(f"fetched_at={utcnow()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())