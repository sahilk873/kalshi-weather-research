"""Collect and normalize Open-Meteo NOAA GEFS ensemble forecasts.

Raw responses are immutable evidence. ``gefs_members.parquet`` keeps one row
per forecast run, city, model, member, variable, and valid time; this module
never collapses members to a mean.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from common import ensure_runtime_dirs, http_get, utcnow  # noqa: E402

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
MODELS = ("ncep_gefs025", "ncep_gefs05", "ncep_gefs_seamless")
VARIABLES = (
    "temperature_2m", "dew_point_2m", "relative_humidity_2m",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
    "cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
    "pressure_msl", "surface_pressure", "shortwave_radiation",
    "direct_radiation", "diffuse_radiation", "cape", "convective_inhibition",
)
CITY_LOCATIONS = {
    "nyc": ("NYC", 40.7128, -74.0060, "America/New_York"),
    "los_angeles": ("Los Angeles", 34.0522, -118.2437, "America/Los_Angeles"),
    "austin": ("Austin", 30.2672, -97.7431, "America/Chicago"),
    "chicago": ("Chicago", 41.8781, -87.6298, "America/Chicago"),
    "dc": ("DC", 38.9072, -77.0369, "America/New_York"),
    "boston": ("Boston", 42.3601, -71.0589, "America/New_York"),
    "miami": ("Miami", 25.7617, -80.1918, "America/New_York"),
}


def request_url(city_key: str, model: str, forecast_days: int = 3) -> str:
    _, lat, lon, _ = CITY_LOCATIONS[city_key]
    query = {"latitude": lat, "longitude": lon, "hourly": ",".join(VARIABLES),
             "models": model, "forecast_days": forecast_days, "timezone": "UTC",
             "temperature_unit": "fahrenheit", "wind_speed_unit": "mph"}
    return ENSEMBLE_URL + "?" + urlencode(query)


def _member_columns(hourly: dict, variable: str) -> list[tuple[str, list]]:
    prefix = variable + "_member"
    return sorted((k, v) for k, v in hourly.items() if k.startswith(prefix))


def parse_response(payload: dict, city_key: str, model: str, retrieved_at: str) -> list[dict]:
    """Parse member-suffixed hourly arrays into long rows."""
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    label, lat, lon, tz_name = CITY_LOCATIONS[city_key]
    rows: list[dict] = []
    for variable in VARIABLES:
        for member_key, values in _member_columns(hourly, variable):
            member_id = member_key.removeprefix(variable + "_")
            for i, valid_time in enumerate(times):
                value = values[i] if i < len(values) else None
                if value is None:
                    continue
                valid = str(valid_time)
                if len(valid) == 16:
                    valid += ":00Z"
                canonical_variable = "cin" if variable == "convective_inhibition" else variable
                rows.append({"forecast_run_time": retrieved_at, "valid_time": valid,
                             "city": label, "city_key": city_key, "latitude": lat,
                             "longitude": lon, "timezone": tz_name, "model": model,
                             "member_id": member_id, "variable": canonical_variable,
                             "value": float(value), "retrieved_at": retrieved_at})
    return rows


def _write_parquet(rows: list[dict], path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.Table.from_pylist(rows)
    if path.exists():
        old = pq.read_table(path)
        # pyarrow may infer string columns differently across independent
        # batches; normalize them before concatenation.
        for column in table.column_names:
            if pa.types.is_string(old[column].type) or pa.types.is_large_string(old[column].type):
                old = old.set_column(old.schema.get_field_index(column), column,
                                     old[column].cast(pa.string()))
                table = table.set_column(table.schema.get_field_index(column), column,
                                         table[column].cast(pa.string()))
        table = pa.concat_tables([old, table], promote_options="default")
        frame = table.to_pandas().drop_duplicates(
            ["forecast_run_time", "valid_time", "city_key", "model", "member_id", "variable"]
        )
        table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, path, compression="zstd")


def collect(cities: list[str], models: list[str], forecast_days: int = 3) -> int:
    dirs = ensure_runtime_dirs()
    all_rows: list[dict] = []
    manifest_path = dirs["gefs"] / "manifest.csv"
    fields = ["model", "city_key", "request_url", "raw_path", "sha256", "retrieved_at", "member_count"]
    with manifest_path.open("a", newline="") as mf:
        writer = csv.DictWriter(mf, fieldnames=fields)
        if manifest_path.stat().st_size == 0:
            writer.writeheader()
        for city_key in cities:
            for model in models:
                url = request_url(city_key, model, forecast_days)
                retrieved = utcnow()
                body = http_get(url)
                digest = hashlib.sha256(body).hexdigest()
                stamp = retrieved.replace(":", "").replace("-", "")
                raw = dirs["gefs_raw"] / model / city_key / f"{stamp}_{digest[:12]}.json"
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_bytes(body)
                rows = parse_response(json.loads(body), city_key, model, retrieved)
                all_rows.extend(rows)
                members = len({r["member_id"] for r in rows if r["variable"] == "temperature_2m"})
                writer.writerow({"model": model, "city_key": city_key, "request_url": url,
                                 "raw_path": str(raw.relative_to(dirs["research"])), "sha256": digest,
                                 "retrieved_at": retrieved, "member_count": members})
                print(f"{city_key} {model}: {members} temperature members, {len(rows)} rows")
    if all_rows:
        _write_parquet(all_rows, dirs["gefs"] / "gefs_members.parquet")
    return len(all_rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cities", nargs="+", choices=sorted(CITY_LOCATIONS), default=list(CITY_LOCATIONS))
    ap.add_argument("--models", nargs="+", choices=MODELS, default=["ncep_gefs025"])
    ap.add_argument("--forecast-days", type=int, default=3)
    args = ap.parse_args()
    print(f"wrote {collect(args.cities, args.models, args.forecast_days)} member rows")


if __name__ == "__main__":
    main()
