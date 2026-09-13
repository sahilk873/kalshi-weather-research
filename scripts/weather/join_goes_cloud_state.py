"""Join GOES station features to ASOS observations with an as-of clock."""
from __future__ import annotations
import argparse, csv
from datetime import datetime, timezone
from pathlib import Path

STATION_CITY = {"PHX": "phx", "LAS": "klas"}

def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def build(asos: list[dict], cloud: list[dict], max_age_minutes: float = 180.0) -> tuple[list[dict], list[dict]]:
    by_station = {}
    for row in cloud:
        station = row.get("station", ""); by_station.setdefault(station, []).append(row)
    for rows in by_station.values(): rows.sort(key=lambda r: _ts(r["time_coverage_start"]))
    running = {}; output, rejected = [], []
    for row in sorted(asos, key=lambda r: (r.get("station", ""), r.get("valid_utc", ""))):
        station = row.get("station", ""); city = STATION_CITY.get(station)
        if not city: continue
        try: observed = float(row.get("tmpf", "")); when = _ts(row["valid_utc"])
        except (KeyError, TypeError, ValueError): rejected.append({"station": station, "valid_utc": row.get("valid_utc", ""), "reason": "invalid_asos"}); continue
        key = (station, row.get("local_date", "")); hi, lo = running.get(key, (observed, observed)); hi, lo = max(hi, observed), min(lo, observed); running[key] = (hi, lo)
        candidates = [r for r in by_station.get(city, []) if _ts(r["time_coverage_start"]) <= when]
        if not candidates: continue
        latest = candidates[-1]; age = (when - _ts(latest["time_coverage_start"])).total_seconds() / 60
        if age > max_age_minutes: continue
        output.append({"station": station, "city": city, "valid_utc": row["valid_utc"], "local_date": row.get("local_date", ""), "current_temperature_f": f"{observed:.6f}", "observed_high_so_far_f": f"{hi:.6f}", "observed_low_so_far_f": f"{lo:.6f}", "cloud_time_utc": latest["time_coverage_start"], "cloud_age_minutes": f"{age:.3f}", "cloud_source_file": latest["source_file"], "cloud_source_sha256": latest["source_sha256"], "ir_brightness_temperature_k_mean": latest["ir_brightness_temperature_k_mean"], "dqf_clear_fraction": latest["dqf_clear_fraction"]})
    return output, rejected

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--asos", type=Path, required=True); p.add_argument("--cloud", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--rejections", type=Path); p.add_argument("--max-age-minutes", type=float, default=180); a = p.parse_args()
    with a.asos.open(newline="") as f: asos = list(csv.DictReader(f))
    with a.cloud.open(newline="") as f: cloud = list(csv.DictReader(f))
    rows, rejected = build(asos, cloud, a.max_age_minutes); a.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["station", "city", "valid_utc"]
    with a.output.open("w", newline="") as f: w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    if a.rejections:
        with a.rejections.open("w", newline="") as f: w = csv.DictWriter(f, fieldnames=["station", "valid_utc", "reason"]); w.writeheader(); w.writerows(rejected)
    print(f"wrote {len(rows)} cloud-joined ASOS rows; rejected={len(rejected)}")

if __name__ == "__main__": main()
