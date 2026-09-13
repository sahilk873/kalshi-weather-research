"""Decode filtered HRRR/NBM GRIB2 files at the registered city point.

The raw GRIB2 files and manifest remain authoritative.  This optional decoder
uses ``eccodes`` when installed and writes one nearest-grid-point row per
selected variable.  It never replaces raw files and records the model issue,
source receipt, valid time, and source hash in the normalized output.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import sys
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from city_focus import CITIES  # noqa: E402

CITY_COORDS = {"nyc": (40.7789, -73.9692), "la": (33.9382, -118.3886), "austin": (30.1945, -97.6699), "phx": (33.4343, -112.0116), "klas": (36.0719, -115.1633), "lv": (36.0719, -115.1633)}
ALIASES = {"los_angeles": "la", "los angeles": "la", "la": "la", "nyc": "nyc", "austin": "austin", "phx": "phx", "klas": "klas", "lv": "klas"}
VARIABLES = {
    "2t": ("temperature_2m", "K", "F"), "2d": ("dewpoint_2m", "K", "F"),
    "10si": ("wind_speed_10m", "m/s", "mph"), "10wdir": ("wind_direction_10m", "degree", "degree"),
    "10u": ("wind_u_10m", "m/s", "mph"), "10v": ("wind_v_10m", "m/s", "mph"),
    "tcc": ("cloud_cover", "fraction", "fraction"), "tp": ("total_precipitation", "m", "m"),
    "gust": ("wind_gusts_10m", "m/s", "mph"), "10fg": ("wind_gusts_10m", "m/s", "mph"),
    "prmsl": ("pressure_msl", "Pa", "hPa"), "pres": ("pressure_surface", "Pa", "hPa"), "sp": ("pressure_surface", "Pa", "hPa"),
    "dswrf": ("shortwave_radiation", "W/m2", "W/m2"), "sdswrf": ("shortwave_radiation", "W/m2", "W/m2"),
    "cape": ("cape", "J/kg", "J/kg"), "cin": ("cin", "J/kg", "J/kg"),
    "hgt": ("geopotential_height_500hpa", "gpm", "gpm"), "gh": ("geopotential_height_pressure_level", "gpm", "gpm"),
    "t": ("temperature_pressure_level", "K", "F"),
    "u": ("wind_u_pressure_level", "m/s", "mph"), "v": ("wind_v_pressure_level", "m/s", "mph"),
}


def convert_value(short_name: str, value: float) -> tuple[float, str, str] | None:
    spec = VARIABLES.get(short_name)
    if spec is None:
        return None
    variable, source_unit, output_unit = spec
    if short_name in {"2t", "2d", "t"}:
        value = (value - 273.15) * 9 / 5 + 32
    elif short_name in {"10si", "10u", "10v", "u", "v"}:
        value *= 2.2369362920544
    elif short_name in {"gust", "10fg"}:
        value *= 2.2369362920544
    elif short_name in {"prmsl", "pres", "sp"}:
        value /= 100.0
    return float(value), source_unit, output_unit


def decode(manifest_path: Path, research_root: Path, output_path: Path, cities: set[str] | None = None) -> int:
    try:
        from eccodes import codes_get, codes_grib_find_nearest, codes_grib_new_from_file, codes_release
    except ImportError as exc:
        raise RuntimeError("eccodes is required for GRIB decoding; raw files remain usable without it") from exc
    with manifest_path.open(newline="") as fh:
        manifest = list(csv.DictReader(fh))
    rows: list[dict] = []
    for meta in manifest:
        canonical = ALIASES.get(str(meta.get("city", "")).lower(), str(meta.get("city", "")).lower())
        if cities and canonical not in cities:
            continue
        coords = CITY_COORDS.get(canonical)
        if coords is None:
            continue
        path = research_root / meta["raw_path"]
        if not path.exists():
            path = research_root / "forecasts" / meta["raw_path"]
        if not path.exists():
            raise FileNotFoundError(path)
        expected = meta.get("sha256", "")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected and actual != expected:
            raise ValueError(f"raw hash mismatch: {path}")
        with path.open("rb") as fh:
            message_index = 0
            while (gid := codes_grib_new_from_file(fh)) is not None:
                message_index += 1
                try:
                    short = codes_get(gid, "shortName")
                    if short not in VARIABLES:
                        continue
                    nearest = codes_grib_find_nearest(gid, *coords)[0]
                    converted = convert_value(short, float(nearest["value"]))
                    if converted is None:
                        continue
                    value, source_unit, output_unit = converted
                    try:
                        level = int(codes_get(gid, "level") or 0)
                    except (TypeError, ValueError):
                        level = 0
                    variable_name = VARIABLES[short][0]
                    if short == "t" and level in {700, 850, 925}:
                        variable_name = f"temperature_{level}hpa"
                    elif short == "gh" and level == 500:
                        variable_name = "geopotential_height_500hpa"
                    elif short in {"u", "v"} and level == 850:
                        variable_name = f"wind_{'u' if short == 'u' else 'v'}_850hpa"
                    rows.append({
                        "model": meta["model"], "city": canonical,
                        "initialization_time_utc": meta["initialization_time_utc"],
                        "valid_time_utc": meta["valid_time_utc"], "lead_hours": meta["lead_hours"],
                        "source_receipt_time": meta["ingested_at_utc"], "variable": variable_name,
                        "value": f"{value:.8f}", "unit": output_unit,
                        "grid_latitude": f"{nearest['lat']:.8f}", "grid_longitude": f"{nearest['lon']:.8f}",
                        "raw_path": meta["raw_path"], "sha256": actual, "message_index": message_index,
                    })
                finally:
                    codes_release(gid)
    # Derive wind speed from decoded vector components when the source GRIB
    # exposes U/V but no scalar 10-m speed message.
    grouped = {}
    for row in rows:
        key = tuple(row.get(field, "") for field in ("model", "city", "initialization_time_utc", "valid_time_utc"))
        grouped.setdefault(key, []).append(row)
    for values in grouped.values():
        by_variable = {row["variable"]: row for row in values}
        if "wind_speed_10m" not in by_variable and {"wind_u_10m", "wind_v_10m"} <= by_variable.keys():
            u = float(by_variable["wind_u_10m"]["value"]); v = float(by_variable["wind_v_10m"]["value"])
            source = by_variable["wind_u_10m"]
            values.append({**source, "variable": "wind_speed_10m", "value": f"{math.hypot(u, v):.8f}", "unit": "mph"})
        if "wind_850hpa" not in by_variable and {"wind_u_850hpa", "wind_v_850hpa"} <= by_variable.keys():
            u = float(by_variable["wind_u_850hpa"]["value"]); v = float(by_variable["wind_v_850hpa"]["value"])
            source = by_variable["wind_u_850hpa"]
            values.append({**source, "variable": "wind_850hpa", "value": f"{math.hypot(u, v):.8f}", "unit": "mph"})
    rows = [row for values in grouped.values() for row in values]
    fields = ["model", "city", "initialization_time_utc", "valid_time_utc", "lead_hours", "source_receipt_time", "variable", "value", "unit", "grid_latitude", "grid_longitude", "raw_path", "sha256", "message_index"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[2] / "data" / "weather_research"
    parser.add_argument("--manifest", type=Path, default=root / "forecasts" / "manifest.csv")
    parser.add_argument("--research-root", type=Path, default=root)
    parser.add_argument("--output", type=Path, default=root / "forecasts" / "model_forecasts_points.csv")
    parser.add_argument("--cities", nargs="*", choices=sorted(CITY_COORDS))
    args = parser.parse_args()
    print(f"wrote {decode(args.manifest, args.research_root, args.output, set(args.cities) if args.cities else None)} decoded forecast rows")


if __name__ == "__main__":
    main()
