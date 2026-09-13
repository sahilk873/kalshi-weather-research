"""Archive the public Weather Company/Kalshi climate portal payloads.

The portal is a source-of-record evidence surface linked from Kalshi.  Raw
JSON is retained; normalized hourly observations and daily climate reports are
explicitly labelled as preliminary/official and never substituted silently for
contract outcomes.
"""
from __future__ import annotations

import argparse, csv, hashlib, json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://weather.com/kalshi"
TARGET_STATIONS = {"KNYC", "KLAX", "KAUS"}
HOURLY_FIELDS = ["station", "station_name", "valid_utc", "valid_local", "local_date", "local_hour", "temperature_c", "temperature_f", "status", "retrieved_at_utc", "raw_sha256", "raw_path"]
DAILY_FIELDS = ["station", "city", "cli_id", "date", "status", "official_high_f", "official_low_f", "average_f", "retrieved_at_utc", "raw_sha256", "raw_path"]

def _get(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "kalshi-weather-research/1.0"})
    with urlopen(req, timeout=60) as response:
        return response.read()

def _fetch_json(url: str) -> object:
    return json.loads(_get(url))

def _archive(root: Path, kind: str, payload: object, receipt: str) -> tuple[Path, str]:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(body).hexdigest()
    path = root / "raw" / f"{kind}_{receipt.replace(':', '').replace('-', '')}.json"
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(body)
    return path, digest

def _merge_csv(path: Path, rows: list[dict], fields: list[str], key_fields: tuple[str, ...]) -> None:
    existing = []
    if path.exists():
        with path.open(newline="") as handle: existing = list(csv.DictReader(handle))
    merged = {tuple(row.get(field, "") for field in key_fields): row for row in existing}
    merged.update({tuple(row.get(field, "") for field in key_fields): row for row in rows})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(merged.values())

def _first_value(*values: object) -> object:
    return next((value for value in values if value not in (None, "")), "")

def collect(root: Path, week_start: str, climate_date: str, target_stations: set[str] = TARGET_STATIONS) -> tuple[int, int]:
    receipt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    hourly_url = f"{BASE}/api/metar?{urlencode({'primary': 'true', 'weekStart': week_start})}"
    climate_url = f"{BASE}/api/climate/primary?{urlencode({'date': climate_date})}"
    hourly = _fetch_json(hourly_url); daily = _fetch_json(climate_url)
    hp, hh = _archive(root, "metar", hourly, receipt); dp, dh = _archive(root, "climate", daily, receipt)
    hrows = []
    for station in hourly.get("stations", []):
        if station.get("icaoId") not in target_stations: continue
        for obs in station.get("observations", []):
            hrows.append({"station": obs.get("icaoId", station.get("icaoId", "")), "station_name": obs.get("stationName", station.get("stationName", "")), "valid_utc": obs.get("reportTimeUTC", ""), "valid_local": obs.get("reportTimeLocal", ""), "local_date": obs.get("localDate", ""), "local_hour": obs.get("localHour", ""), "temperature_c": obs.get("tempC", ""), "temperature_f": obs.get("tempF", ""), "status": obs.get("status", ""), "retrieved_at_utc": receipt, "raw_sha256": hh, "raw_path": str(hp)})
    drows = []
    for result in daily.get("results", []):
        station = result.get("station", {}); data = result.get("data") or {}
        drows.append({"station": station.get("icao", ""), "city": station.get("city", ""), "cli_id": station.get("cliId", ""), "date": daily.get("date", climate_date), "status": result.get("status", ""), "official_high_f": _first_value(data.get("maxTempF"), data.get("maxTemp")), "official_low_f": _first_value(data.get("minTempF"), data.get("minTemp")), "average_f": _first_value(data.get("avgTempF"), data.get("avgTemp"), result.get("avgTemp")), "retrieved_at_utc": receipt, "raw_sha256": dh, "raw_path": str(dp)})
    root.mkdir(parents=True, exist_ok=True)
    _merge_csv(root / "hourly.csv", hrows, HOURLY_FIELDS, ("station", "valid_utc", "raw_path"))
    _merge_csv(root / "daily.csv", drows, DAILY_FIELDS, ("station", "date", "raw_path"))
    manifest_path = root / "manifest.json"; manifest = {"snapshots": []}
    if manifest_path.exists():
        try: manifest = json.loads(manifest_path.read_text())
        except (OSError, ValueError): pass
    # Migrate older manifests so every retained snapshot carries the same
    # explicit availability semantics; missing publication clocks are never
    # inferred from the receipt timestamp.
    for snapshot in manifest.get("snapshots", []):
        if isinstance(snapshot, dict):
            snapshot.setdefault("availability_basis", "receipt_upper_bound")
            snapshot.setdefault("source_publication_time_observed", False)
    manifest.setdefault("snapshots", []).append({"retrieved_at_utc": receipt, "week_start": week_start, "climate_date": climate_date, "hourly_raw_path": str(hp), "hourly_sha256": hh, "climate_raw_path": str(dp), "climate_sha256": dh,
                                                   "availability_basis": "receipt_upper_bound",
                                                   "source_publication_time_observed": False})
    manifest["latest"] = manifest["snapshots"][-1]; manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return len(hrows), len(drows)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); today = date.today()
    parser.add_argument("--week-start", default=(today - timedelta(days=today.weekday())).isoformat()); parser.add_argument("--date", default=today.isoformat()); parser.add_argument("--output-dir", type=Path, default=Path("data/weather_research/twc_kalshi")); parser.add_argument("--stations", nargs="*", default=sorted(TARGET_STATIONS)); args = parser.parse_args()
    h, d = collect(args.output_dir, args.week_start, args.date, set(args.stations)); print(f"archived Weather Company portal: {h} target-station hourly rows, {d} daily rows")

if __name__ == "__main__": main()
