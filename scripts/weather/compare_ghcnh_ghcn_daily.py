"""Compare GHCNh sampled local-day extrema with GHCN daily labels."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

STATION_CITY = {"USW00023183": "phx", "USW00023169": "lv", "USW00094728": "nyc", "USW00023174": "la", "USW00013904": "austin"}


def compare(extrema: list[dict], labels: list[dict]) -> dict:
    left = {(STATION_CITY.get(r.get("station", ""), ""), r.get("local_date", "")): r for r in extrema}
    right = {(r.get("city", ""), r.get("date", "")): r for r in labels}
    deltas = defaultdict(list); overlap = 0
    for key, row in left.items():
        label = right.get(key)
        if not label:
            continue
        try:
            deltas[(key[0], "high")].append(float(row["tmax_f"]) - float(label["tmax_f"]))
            deltas[(key[0], "low")].append(float(row["tmin_f"]) - float(label["tmin_f"]))
            overlap += 1
        except (KeyError, TypeError, ValueError):
            continue
    rows = []
    for (city, temp_type), values in sorted(deltas.items()):
        absolute = [abs(v) for v in values]
        rows.append({"city": city, "temp_type": temp_type, "overlap_days": len(values),
                     "mean_delta_f": round(sum(values) / len(values), 4),
                     "mae_f": round(sum(absolute) / len(values), 4),
                     "max_abs_delta_f": round(max(absolute), 4)})
    return {"extrema_rows": len(extrema), "label_rows": len(labels), "overlap_station_days": overlap,
            "comparisons": rows}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--extrema", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    with args.extrema.open(newline="") as fh: extrema = list(csv.DictReader(fh))
    with args.labels.open(newline="") as fh: labels = list(csv.DictReader(fh))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(compare(extrema, labels), indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
