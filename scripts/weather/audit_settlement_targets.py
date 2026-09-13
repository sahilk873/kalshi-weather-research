"""Audit event-level settlement source and target-resolution evidence."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def _official_coordinates(path: Path) -> dict:
    root = path.parent.parent
    output = {}
    for raw in sorted((root / "homr").glob("homr_*.json")):
        try:
            payload = json.loads(raw.read_text())
            station = payload["stationCollection"]["stations"][0]
            pairs = station.get("location", {}).get("latLonPairs", [])
            current = [pair for pair in pairs if pair.get("date", {}).get("endDate") == "Present"]
            if current:
                pair = current[0]
                output[raw.stem.removeprefix("homr_")] = {"latitude": float(pair["latitude_dec"]), "longitude": float(pair["longitude_dec"]), "source": pair.get("source", ""), "raw_path": str(raw)}
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            continue
    return output


def audit(path: Path) -> dict:
    if not path.exists():
        return {"version": "report2-settlement-target-audit-v1", "rows": 0, "pass": False, "reason": "contracts file missing"}
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    source_counts = Counter(row.get("settlement_source_name", "") or "missing" for row in rows)
    method_counts = Counter(row.get("settlement_station_method", "") or "missing" for row in rows)
    missing_target = sum(not row.get("target_time_utc") for row in rows)
    missing_source = sum(not row.get("settlement_source_name") for row in rows)
    missing_hash = sum(not row.get("rules_hash") for row in rows)
    unresolved = sum("unverified" in row.get("settlement_station_method", "") or row.get("settlement_station_method") in {"", "unresolved"} for row in rows)
    return {"version": "report2-settlement-target-audit-v1", "rows": len(rows),
            "source_counts": dict(sorted(source_counts.items())),
            "station_method_counts": dict(sorted(method_counts.items())),
            "missing_target_time": missing_target, "missing_source": missing_source,
            "missing_rules_hash": missing_hash, "unverified_or_unresolved_station": unresolved,
            "official_station_coordinate_candidates": _official_coordinates(path),
            "pass": bool(rows) and not any((missing_target, missing_source, missing_hash))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", type=Path, default=Path("data/weather_research/kalshi_hourly/contracts.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/reports/settlement_target_audit.json"))
    args = parser.parse_args()
    result = audit(args.contracts); args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"rows": result["rows"], "pass": result["pass"], "unverified_station": result.get("unverified_or_unresolved_station", 0)}))


if __name__ == "__main__": main()
