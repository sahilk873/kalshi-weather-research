"""Build auditable local-day extrema from normalized GHCNh observations."""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

STATION_ZONES = {
    "USW00023183": "America/Phoenix", "USW00023169": "America/Los_Angeles",
    "USW00094728": "America/New_York", "USW00023174": "America/Los_Angeles",
    "USW00013904": "America/Chicago",
}
OUT_FIELDS = ["station", "local_date", "timezone", "observation_count",
              "tmax_f", "tmax_utc", "tmin_f", "tmin_utc", "raw_paths", "raw_hashes"]


def build(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        station = row.get("station", "")
        zone_name = STATION_ZONES.get(station)
        try:
            temp = float(row.get("temperature_f", ""))
            dt = datetime.fromisoformat(row["valid_utc"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            continue
        if not zone_name or dt.tzinfo is None:
            continue
        local_date = dt.astimezone(ZoneInfo(zone_name)).date().isoformat()
        groups[(station, local_date)].append({**row, "_temp": temp, "_dt": dt})
    output = []
    for (station, local_date), values in sorted(groups.items()):
        zone_name = STATION_ZONES[station]
        high = max(values, key=lambda r: (r["_temp"], r["_dt"]))
        low = min(values, key=lambda r: (r["_temp"], r["_dt"]))
        output.append({
            "station": station, "local_date": local_date, "timezone": zone_name,
            "observation_count": str(len(values)), "tmax_f": f"{high['_temp']:.3f}",
            "tmax_utc": high["valid_utc"], "tmin_f": f"{low['_temp']:.3f}",
            "tmin_utc": low["valid_utc"],
            "raw_paths": "|".join(sorted({r.get("raw_path", "") for r in values})),
            "raw_hashes": "|".join(sorted({r.get("sha256", "") for r in values})),
        })
    return output


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    with args.input.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    output = build(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
        writer.writeheader(); writer.writerows(output)
    print(f"wrote {args.output} ({len(output)} rows)")


if __name__ == "__main__":
    main()
