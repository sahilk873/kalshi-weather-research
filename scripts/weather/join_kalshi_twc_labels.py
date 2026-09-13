"""Join public TWC portal observations to exact city hourly contracts.

Only exact UTC target-time matches are accepted. Missing observations remain
unlabeled; this adapter never substitutes ASOS or interpolates temperatures.
"""
from __future__ import annotations

import argparse, csv
from datetime import datetime
import math
from pathlib import Path

FIELDS = ["market_ticker", "event_ticker", "target_time_utc", "threshold_f", "comparison", "kalshi_result", "source_temperature_f", "source_observed_yes", "source_status", "source_valid_utc", "source_receipt_utc", "label_available_ts", "source_raw_sha256", "source_raw_path"]
SERIES_STATION = {"KXTEMPNYCH": "KNYC", "KXTEMPLAXH": "KLAX", "KXTEMPAUSH": "KAUS"}

def _time(value: str):
    try: return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError): return None

def _canonical(value: str) -> str:
    stamp = _time(value)
    return stamp.isoformat().replace("+00:00", "Z") if stamp else ""

def _whole_degree(value: float) -> int:
    """Convert the portal's one-decimal Fahrenheit reading to a contract degree."""
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)

def join(contracts: list[dict], observations: list[dict]) -> list[dict]:
    by_time: dict[str, list[dict]] = {}
    for row in observations:
        if _time(row.get("valid_utc", "")) is None: continue
        by_time.setdefault((row.get("station", ""), _canonical(row["valid_utc"])), []).append(row)
    output = []
    for contract in contracts:
        target = contract.get("target_time_utc", ""); station = SERIES_STATION.get(contract.get("series_ticker", ""), "KNYC"); candidates = by_time.get((station, _canonical(target)), [])
        # Select the most recently received exact observation, preserving its
        # availability clock and raw snapshot identity.
        candidates = sorted(candidates, key=lambda row: _time(row.get("retrieved_at_utc", "")) or datetime.min.replace(tzinfo=_time(target).tzinfo if _time(target) else None))
        source = candidates[-1] if candidates else {}
        try:
            threshold = float(contract.get("bucket_floor_f", "") or contract.get("bucket_ceil_f", "") or contract.get("threshold_f", ""))
            temperature = float(source.get("temperature_f", ""))
            degree = _whole_degree(temperature)
            observed = degree >= threshold if contract.get("comparison") == "above" else degree <= threshold if contract.get("comparison") == "below" else None
        except (TypeError, ValueError): threshold = ""; temperature = ""; observed = None
        output.append({"market_ticker": contract.get("market_ticker", ""), "event_ticker": contract.get("event_ticker", ""), "target_time_utc": target, "threshold_f": contract.get("threshold_f", ""), "comparison": contract.get("comparison", ""), "kalshi_result": contract.get("result", ""), "source_temperature_f": temperature, "source_observed_yes": "" if observed is None else str(observed).lower(), "source_status": source.get("status", ""), "source_valid_utc": source.get("valid_utc", ""), "source_receipt_utc": source.get("retrieved_at_utc", ""), "label_available_ts": source.get("retrieved_at_utc", ""), "source_raw_sha256": source.get("raw_sha256", ""), "source_raw_path": source.get("raw_path", "")})
    return output

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); root = Path("data/weather_research"); parser.add_argument("--contracts", type=Path, default=root / "kalshi_hourly/contracts.csv"); parser.add_argument("--observations", type=Path, default=root / "twc_kalshi/hourly.csv"); parser.add_argument("--output", type=Path, default=root / "kalshi_hourly/twc_labels.csv"); args = parser.parse_args()
    with args.contracts.open(newline="") as handle: contracts = list(csv.DictReader(handle))
    with args.observations.open(newline="") as handle: observations = list(csv.DictReader(handle))
    rows = join(contracts, observations); args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle: writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    matched = sum(bool(row["source_valid_utc"]) for row in rows); print(f"wrote {len(rows)} contract labels ({matched} exact source matches)")

if __name__ == "__main__": main()
