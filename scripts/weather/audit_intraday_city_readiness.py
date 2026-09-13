"""Audit whether NYC, Los Angeles, and Austin intraday lines are backtest-ready."""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timezone
from pathlib import Path

CITIES = {
    "nyc": ("KXTEMPNYCH", "KNYC", "kalshi_hourly/historical_quotes"),
    "la": ("KXTEMPLAXH", "KLAX", "kalshi_hourly/kxtemplaxh/historical_quotes"),
    "austin": ("KXTEMPAUSH", "KAUS", "kalshi_hourly/kxtempaush/historical_quotes"),
}

def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))

def parse(value: str) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None

def audit(root: Path) -> dict:
    twc = rows(root / "twc_kalshi/hourly.csv")
    result = {"version": "intraday-city-readiness-v1", "cities": {}, "pass": True}
    for city, (series, station, relative) in CITIES.items():
        base = root / relative
        terms_base = root / "kalshi_hourly" / f"{series.lower()}_terms"
        markets = rows(terms_base / "contracts.csv") or rows(base / "market_metadata.csv")
        candles, trades = rows(base / "candles_hourly.csv"), rows(base / "trades.csv")
        station_rows = [row for row in twc if row.get("station") == station]
        missing_target = sum(not row.get("target_time_utc") for row in markets)
        missing_source = sum(not row.get("settlement_source_name") for row in markets)
        exact_open = 0
        pre_receipt = 0
        by_time = {row.get("valid_utc"): row for row in station_rows}
        for market in markets:
            observation = by_time.get(market.get("open_time", ""))
            if not observation:
                continue
            exact_open += 1
            receipt, decision = parse(observation.get("retrieved_at_utc", "")), parse(market.get("open_time", ""))
            if receipt and decision and receipt <= decision:
                pre_receipt += 1
        eligible = exact_open and pre_receipt and not missing_target and not missing_source
        result["cities"][city] = {"series_ticker": series, "station": station,
            "terms_source": str(terms_base / "contracts.csv") if (terms_base / "contracts.csv").exists() else str(base / "market_metadata.csv"),
            "market_rows": len(markets), "candle_rows": len(candles), "trade_rows": len(trades),
            "twc_station_rows": len(station_rows), "missing_target_time": missing_target,
            "missing_settlement_source": missing_source, "exact_open_time_matches": exact_open,
            "pre_decision_receipts": pre_receipt, "eligible_for_backtest": bool(eligible),
            "reason": "eligible" if eligible else "missing_event_terms_or_pre_decision_alignment"}
        result["pass"] = result["pass"] and bool(eligible)
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/weather_research"))
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/reports/intraday_city_readiness.json"))
    args = parser.parse_args(); report = audit(args.root); args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n"); print(json.dumps(report, sort_keys=True))

if __name__ == "__main__": main()
