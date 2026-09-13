"""Parse NOAA LAMP ``lavtxt.ascii`` station blocks into long rows.

The parser is deliberately schema-preserving: numeric guidance is parsed as a
float when possible, while categorical aviation fields remain strings. Raw
path and hash are copied from the acquisition manifest so each row remains
reproducible and point-in-time checks can use the cycle/receipt clocks.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIELDS = ["station", "initialization_time_utc", "valid_time_utc", "field",
          "value", "raw_path", "raw_sha256", "retrieved_at_utc"]
HEADER = re.compile(r"^\s*([A-Z0-9]{4})\s+.*?\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d{4})\s+UTC\s*$")


def parse(text: str, raw_path: str = "", raw_sha256: str = "",
          retrieved_at_utc: str = "") -> list[dict]:
    station = init = ""
    hours: list[str] = []
    rows: list[dict] = []
    for line in text.splitlines():
        header = HEADER.match(line)
        if header:
            station, day, hhmm = header.groups()
            init_dt = datetime.strptime(f"{day} {hhmm}", "%m/%d/%Y %H%M").replace(tzinfo=timezone.utc)
            init = init_dt.isoformat().replace("+00:00", "Z")
            hours = []
            continue
        if not station:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        if parts[0] == "UTC":
            hours = parts[1:]
            continue
        if not hours or parts[0] in {"1", "2"}:
            continue
        field, values = parts[0], parts[1:]
        for index, value in enumerate(values[:len(hours)]):
            base_dt = datetime.fromisoformat(init.replace("Z", "+00:00"))
            valid_dt = base_dt.replace(hour=int(hours[index]))
            if valid_dt < base_dt:
                valid_dt += timedelta(days=1)
            try:
                normalized = float(value)
            except ValueError:
                normalized = value
            rows.append({"station": station, "initialization_time_utc": init,
                         "valid_time_utc": valid_dt.isoformat().replace("+00:00", "Z"),
                         "field": field, "value": normalized, "raw_path": raw_path,
                         "raw_sha256": raw_sha256, "retrieved_at_utc": retrieved_at_utc})
    return rows


def parse_file(raw_path: Path, manifest_path: Path | None = None) -> list[dict]:
    metadata = {}
    if manifest_path and manifest_path.exists():
        payload = json.loads(manifest_path.read_text())
        for item in payload.get("snapshots", []):
            if item.get("raw_path") == str(raw_path):
                metadata = item
        if not metadata and payload.get("latest", {}).get("raw_path") == str(raw_path):
            metadata = payload["latest"]
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    return parse(raw_path.read_text(errors="replace"), str(raw_path),
                 metadata.get("sha256", digest), metadata.get("retrieved_at_utc", ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=Path("data/weather_research/lamp/manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/lamp/station_forecasts.csv"))
    args = parser.parse_args()
    raw = args.raw or Path(json.loads(args.manifest.read_text())["latest"]["raw_path"])
    rows = parse_file(raw, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    print(f"wrote {len(rows)} LAMP station-field rows")


if __name__ == "__main__":
    main()
