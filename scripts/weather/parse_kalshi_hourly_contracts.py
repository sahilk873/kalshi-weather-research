"""Normalize archived KXTEMP city contracts without inferring settlement rules."""
from __future__ import annotations

import argparse, csv, hashlib, json, re
from pathlib import Path
from settlement_locations import SETTLEMENT_LOCATIONS

FIELDS = ["event_ticker", "market_ticker", "series_ticker", "target_time_utc", "target_local_text", "threshold_f", "comparison", "bucket_floor_f", "bucket_ceil_f", "status", "result", "open_time", "close_time", "settlement_ts", "settlement_source_name", "settlement_source_url", "settlement_station", "settlement_station_method", "rules_hash", "retrieved_at_utc", "raw_sha256", "raw_path"]

SERIES_STATION = {"KXTEMPNYCH": "KNYC", "KXTEMPLAXH": "KLAX", "KXTEMPAUSH": "KAUS"}

def _number(value):
    try: return float(value)
    except (TypeError, ValueError): return ""

def _bounds(text: str):
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*°?\s*to\s*(-?\d+(?:\.\d+)?)", text or "")
    if match: return float(match.group(1)), float(match.group(2))
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*°?\s*or\s*(?:below|less)", text or "", re.I)
    if match: return "", float(match.group(1))
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*°?\s*or\s*(?:above|more)", text or "", re.I)
    if match: return float(match.group(1)), ""
    return "", ""

def _threshold(ticker: str, title: str):
    match = re.search(r"-T(-?\d+(?:\.\d+)?)$", ticker or "")
    value = float(match.group(1)) if match else None
    if value is None:
        match = re.search(r"(?:above|below)\s+(-?\d+(?:\.\d+)?)", title or "", re.I)
        value = float(match.group(1)) if match else ""
    comparison = "above" if re.search(r"\babove\b|\bor above\b", title or "", re.I) else "below" if re.search(r"\bbelow\b|\bor below\b", title or "", re.I) else ""
    return "" if value is None else value, comparison

def parse(events: list[dict], markets: list[dict], series: dict) -> list[dict]:
    event_by_ticker = {row.get("event_ticker", ""): row for row in events}
    series_sources = series.get("settlement_sources", []) or []
    def event_source(event: dict) -> dict:
        sources = event.get("settlement_sources") or series_sources or [{}]
        if isinstance(sources, str):
            try: sources = json.loads(sources)
            except (TypeError, ValueError): sources = series_sources or [{}]
        return sources[0] if isinstance(sources[0], dict) else {}
    def event_rules_hash(event: dict) -> str:
        event_sources = event.get("settlement_sources") or series_sources
        if isinstance(event_sources, str):
            try: event_sources = json.loads(event_sources)
            except (TypeError, ValueError): event_sources = series_sources
        material = {"contract_terms_url": series.get("contract_terms_url", ""),
                    "contract_url": series.get("contract_url", ""),
                    "settlement_sources": event_sources,
                    "last_updated_ts": series.get("last_updated_ts", "")}
        return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = []
    for market in markets:
        event = event_by_ticker.get(market.get("event_ticker", ""), {}); source = event_source(event); threshold, comparison = _threshold(market.get("ticker", ""), market.get("title", "")); floor, ceil = _bounds(market.get("yes_sub_title", "") or market.get("subtitle", ""))
        series_ticker = market.get("series_ticker", "") or series.get("ticker", "") or market.get("event_ticker", "").split("-", 1)[0]
        station = SERIES_STATION.get(series_ticker, "")
        result.append({"event_ticker": market.get("event_ticker", ""), "market_ticker": market.get("ticker", ""), "series_ticker": series_ticker, "target_time_utc": event.get("strike_date", ""), "target_local_text": event.get("sub_title", ""), "threshold_f": threshold, "comparison": comparison, "bucket_floor_f": floor, "bucket_ceil_f": ceil, "status": market.get("status", ""), "result": market.get("result", ""), "open_time": market.get("open_time", ""), "close_time": market.get("close_time", ""), "settlement_ts": market.get("settlement_ts", ""), "settlement_source_name": source.get("name", ""), "settlement_source_url": source.get("url", ""), "settlement_station": station, "settlement_station_method": "user_supplied_listing_coordinate_registry" if station in SETTLEMENT_LOCATIONS else "unresolved", "rules_hash": event_rules_hash(event), "retrieved_at_utc": market.get("retrieved_at_utc", ""), "raw_sha256": market.get("raw_sha256", ""), "raw_path": market.get("raw_path", "")})
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); root = Path("data/weather_research/kalshi_hourly"); parser.add_argument("--input-dir", type=Path, default=root); parser.add_argument("--output", type=Path, default=root / "contracts.csv"); args = parser.parse_args()
    with (args.input_dir / "events.csv").open(newline="") as h: events = list(csv.DictReader(h))
    with (args.input_dir / "markets.csv").open(newline="") as h: markets = list(csv.DictReader(h))
    series_payload = json.loads((args.input_dir / "series.json").read_text()); series = series_payload.get("series", series_payload)
    rows = parse(events, markets, series); args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as h: writer = csv.DictWriter(h, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    print(f"wrote {len(rows)} normalized hourly contracts")

if __name__ == "__main__": main()
