"""Collect current AWC METAR observations with separate valid/receipt times."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://aviationweather.gov/api/data/metar"
FIELDS = ["station", "valid_utc", "receipt_utc", "temperature_c",
          "dewpoint_c", "wind_dir_degrees", "wind_speed_kt", "raw_metar",
          "source_url", "raw_sha256", "raw_path"]


def collect(ids: list[str], output: Path, hours: int = 2) -> dict:
    if not ids or hours <= 0:
        raise ValueError("at least one station id and positive hours are required")
    query = urlencode({"ids": ",".join(sorted(set(ids))), "format": "json", "hours": hours})
    url = f"{BASE}?{query}"
    request = Request(url, headers={"User-Agent": "kalshi-weather-research/1.0"})
    with urlopen(request, timeout=60) as response:
        raw = response.read()
    receipt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = json.loads(raw)
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / f"metar_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    raw_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    rows = []
    for item in payload if isinstance(payload, list) else payload.get("data", []):
        if not isinstance(item, dict):
            continue
        obs = item.get("obsTime")
        if obs is None:
            obs = item.get("reportTime")
        valid = datetime.fromtimestamp(float(obs), timezone.utc).isoformat().replace("+00:00", "Z") if isinstance(obs, (int, float)) else str(obs or "")
        rows.append({"station": str(item.get("icaoId", "")), "valid_utc": valid,
                     "receipt_utc": receipt, "temperature_c": item.get("temp", ""),
                     "dewpoint_c": item.get("dewp", ""), "wind_dir_degrees": item.get("wdir", ""),
                     "wind_speed_kt": item.get("wspd", ""),
                     "raw_metar": item.get("rawOb", item.get("raw_text", "")),
                     "source_url": url, "raw_sha256": digest, "raw_path": str(raw_path)})
    csv_path = output / "metar.csv"
    existing = []
    if csv_path.exists():
        with csv_path.open(newline="") as handle:
            existing = list(csv.DictReader(handle))
    manifest_path = output / "manifest.json"
    raw_paths_by_hash: dict[str, str] = {}
    if manifest_path.exists():
        try:
            old_manifest = json.loads(manifest_path.read_text())
            snapshots = old_manifest.get("snapshots", []) if isinstance(old_manifest, dict) else []
            for snapshot in snapshots:
                if snapshot.get("raw_sha256") and snapshot.get("raw_path"):
                    raw_paths_by_hash[str(snapshot["raw_sha256"])] = str(snapshot["raw_path"])
        except (OSError, ValueError, TypeError):
            raw_paths_by_hash = {}
    for row in existing:
        if not row.get("raw_path") and row.get("raw_sha256") in raw_paths_by_hash:
            row["raw_path"] = raw_paths_by_hash[row["raw_sha256"]]
    merged = sorted(existing + rows, key=lambda row: (row.get("receipt_utc", ""), row.get("station", ""), row.get("valid_utc", "")))
    dedup = {}
    for row in merged:
        key = (row.get("station", ""), row.get("valid_utc", ""), row.get("raw_sha256", ""))
        # Preserve the earliest receipt when an upstream payload repeats an
        # identical observation; raw snapshots remain in manifest history.
        dedup.setdefault(key, row)
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(dedup.values())
    snapshot = {"retrieved_at_utc": receipt, "source_url": url,
                "raw_path": str(raw_path), "raw_sha256": digest,
                "requested_ids": sorted(set(ids)), "rows": len(rows)}
    history = []
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text())
            history = old.get("snapshots", [])
            if not history and old.get("retrieved_at_utc"):
                history = [old]
        except (OSError, ValueError, TypeError):
            history = []
    history.append(snapshot)
    manifest = {"snapshots": history, "latest": snapshot}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="+", default=["KNYC", "KLAX", "KAUS"])
    parser.add_argument("--hours", type=int, default=2)
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/awc"))
    args = parser.parse_args()
    print(json.dumps(collect(args.ids, args.output, args.hours), sort_keys=True))


if __name__ == "__main__":
    main()
