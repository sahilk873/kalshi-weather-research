#!/usr/bin/env python3
"""Flatten all weather events+markets into one analysis-friendly CSV.

One row per market, joining series / event / market text and price fields,
plus derived columns (implied probability, mid price).
Output: data/kalshi_weather_markets_flattened.csv
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data"

def _load_series_meta():
    path = Path("/tmp/kalshi-series-meta.json")
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = data.get("series") or []
    return {s.get("ticker"): s for s in data}


SERIES_BY_TICKER = _load_series_meta()


def s(series_ticker):
    return SERIES_BY_TICKER.get(series_ticker) or {}


def fmt_list(v):
    if isinstance(v, list):
        return "|".join(str(x) for x in v)
    return v


def num(v):
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return ""


COLUMNS = [
    "market_ticker", "market_title", "market_subtitle",
    "yes_sub_title", "no_sub_title",
    "market_status", "market_type", "strike_type",
    "event_ticker", "event_title", "event_sub_title",
    "event_category", "strike_date", "strike_period", "settlement_sources",
    "series_ticker", "series_title", "series_tags",
    "last_price_dollars", "yes_bid_dollars", "yes_ask_dollars",
    "yes_bid_size_fp", "yes_ask_size_fp",
    "no_bid_dollars", "no_ask_dollars",
    "previous_price_dollars", "previous_yes_bid_dollars", "previous_yes_ask_dollars",
    "mid_price_dollars", "implied_probability",
    "open_interest_fp", "liquidity_dollars",
    "volume_fp", "volume_24h_fp", "notional_value_dollars",
    "open_time", "close_time", "created_time",
    "expiration_time", "expected_expiration_time", "latest_expiration_time",
    "occurrence_datetime", "settlement_ts", "settlement_value_dollars", "result",
    "floor_strike", "expiration_value", "can_close_early",
    "price_ranges", "price_level_structure",
    "rules_primary", "rules_secondary",
]

SUBSET = [
    "market_ticker", "market_title", "yes_sub_title", "no_sub_title",
    "market_status", "market_type", "event_ticker", "event_title",
    "event_sub_title", "event_category", "series_ticker", "series_title",
    "series_tags", "last_price_dollars", "yes_bid_dollars", "yes_ask_dollars",
    "no_bid_dollars", "no_ask_dollars", "mid_price_dollars",
    "implied_probability", "open_interest_fp", "liquidity_dollars",
    "volume_24h_fp", "open_time", "close_time", "expiration_time",
    "occurrence_datetime", "settlement_ts", "settlement_value_dollars", "result",
]


def build_row(ev, m):
    sr = s(ev.get("series_ticker"))
    row = {
        "market_ticker": m.get("ticker"),
        "market_title": m.get("title"),
        "market_subtitle": m.get("subtitle"),
        "yes_sub_title": m.get("yes_sub_title"),
        "no_sub_title": m.get("no_sub_title"),
        "market_status": m.get("status"),
        "market_type": m.get("market_type"),
        "strike_type": m.get("strike_type"),
        "event_ticker": ev.get("event_ticker"),
        "event_title": ev.get("title"),
        "event_sub_title": ev.get("sub_title"),
        "event_category": ev.get("category"),
        "strike_date": ev.get("strike_date"),
        "strike_period": ev.get("strike_period"),
        "settlement_sources": fmt_list(ev.get("settlement_sources")),
        "series_ticker": ev.get("series_ticker"),
        "series_title": sr.get("title"),
        "series_tags": fmt_list(sr.get("tags")),
        "last_price_dollars": num(m.get("last_price_dollars")),
        "yes_bid_dollars": num(m.get("yes_bid_dollars")),
        "yes_ask_dollars": num(m.get("yes_ask_dollars")),
        "yes_bid_size_fp": num(m.get("yes_bid_size_fp")),
        "yes_ask_size_fp": num(m.get("yes_ask_size_fp")),
        "no_bid_dollars": num(m.get("no_bid_dollars")),
        "no_ask_dollars": num(m.get("no_ask_dollars")),
        "previous_price_dollars": num(m.get("previous_price_dollars")),
        "previous_yes_bid_dollars": num(m.get("previous_yes_bid_dollars")),
        "previous_yes_ask_dollars": num(m.get("previous_yes_ask_dollars")),
        "open_interest_fp": num(m.get("open_interest_fp")),
        "liquidity_dollars": num(m.get("liquidity_dollars")),
        "volume_fp": num(m.get("volume_fp")),
        "volume_24h_fp": num(m.get("volume_24h_fp")),
        "notional_value_dollars": num(m.get("notional_value_dollars")),
        "open_time": m.get("open_time"),
        "close_time": m.get("close_time"),
        "created_time": m.get("created_time"),
        "expiration_time": m.get("expiration_time"),
        "expected_expiration_time": m.get("expected_expiration_time"),
        "latest_expiration_time": m.get("latest_expiration_time"),
        "occurrence_datetime": m.get("occurrence_datetime"),
        "settlement_ts": m.get("settlement_ts"),
        "settlement_value_dollars": num(m.get("settlement_value_dollars")),
        "result": m.get("result"),
        "floor_strike": num(m.get("floor_strike")),
        "expiration_value": num(m.get("expiration_value")),
        "can_close_early": m.get("can_close_early"),
        "price_ranges": fmt_list(m.get("price_ranges")),
        "price_level_structure": fmt_list(m.get("price_level_structure")),
        "rules_primary": m.get("rules_primary"),
        "rules_secondary": m.get("rules_secondary"),
    }
    bid, ask = row["yes_bid_dollars"], row["yes_ask_dollars"]
    mid = ""
    if bid != "" and ask != "":
        mid = round((bid + ask) / 2, 2)
    row["mid_price_dollars"] = mid
    if row["last_price_dollars"] != "":
        row["implied_probability"] = round(float(row["last_price_dollars"]), 4)
    elif mid != "":
        row["implied_probability"] = round(float(mid), 4)
    else:
        row["implied_probability"] = ""
    return row


def main():
    events = json.loads((OUT / "kalshi_weather_events.json").read_text())

    out_path = OUT / "kalshi_weather_markets_flattened.csv"
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        n = 0
        for ev in events:
            for m in ev.get("markets") or []:
                writer.writerow(build_row(ev, m))
                n += 1

    print(f"rows written: {n}")
    print(f"file: {out_path}")
    print("columns:", COLUMNS)


if __name__ == "__main__":
    main()