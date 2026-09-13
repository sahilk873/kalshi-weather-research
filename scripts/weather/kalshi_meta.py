"""Normalize Kalshi temperature market metadata.

The default is a fresh bounded pull of the configured PHX/LV series using the
public trade-API v2 (no auth required for market data / events / candlesticks /
trades). ``--discover-temperature-series`` refreshes the broader climate
temperature universe from ``GET /series`` before fetching events:
    https://external-api.kalshi.com/trade-api/v2/events?series_ticker=...

For each active event (local outcome date), all mutually exclusive bucket
markets are included; finalized / past events are also included for
historical coverage.

Outputs:
- data/weather_research/kalshi/events.csv     (one row per event)
- data/weather_research/kalshi/markets.csv    (one row per market)
- data/weather_research/kalshi/contract_outcomes.csv (one row per bucket,
  with a settled_yes label for finalized contracts)

Key fields for research joins:
- outcome_local_date  (YYYY-MM-DD) derived from event_ticker / title.
  Kalshi event tickers encode the date as e.g. KXHIGHTPHX-26SEP10 → 2026-09-10.
- bucket_floor_f / bucket_ceil_f parsed from yes_sub_title or title.
- Calibration / book-price fields: last_price, yes_bid/ask, mid_price,
  implied_probability, volume_24h, open_interest, spread.
- Anti-lookahead: open_time, close_time, settlement_ts / result (label);
  any value used to join to the weather label must respect label_available_ts
  from the GHCN daily labels CSV. See data_dictionary.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

# ruff: noqa: E402
import common  # noqa: E402
from common import ensure_runtime_dirs, http_get_json, utcnow  # noqa: E402
from stations import (CITIES, DEFAULT_CITIES, KALSHI_API_BASE,  # noqa: E402
                      KALSHI_SERIES_CATALOG, KALSHI_SERIES_TO_CITY,
                      SERIES_TEMP_TYPE, get_cities)

EVENT_COLS = [
    "event_ticker", "series_ticker", "city", "temp_type",
    "outcome_local_date", "title", "sub_title",
    "settlement_source_name", "settlement_source_url",
    "strike_date_utc", "num_markets",
]

MARKET_COLS = [
    "market_ticker", "event_ticker", "series_ticker", "city", "temp_type",
    "outcome_local_date", "title", "yes_sub_title", "no_sub_title",
    "status", "result",
    "bucket_floor_f", "bucket_ceil_f", "bucket_label",
    "last_price", "yes_bid", "yes_ask", "no_bid", "no_ask",
    "mid_price", "implied_probability",
    "volume_24h_fp", "open_interest_fp", "liquidity_dollars",
    "spread",
    "open_time", "close_time", "expiration_time",
    "settlement_ts",
]

OUTCOME_COLS = [
    "outcome_local_date", "city", "temp_type", "event_ticker",
    "market_ticker", "bucket_floor_f", "bucket_ceil_f", "bucket_label",
    "status", "settled_yes", "settlement_ts", "settlement_source_name",
    "settlement_source_url",
]


def fetch_events(series_ticker: str) -> list[dict]:
    events, cursor = [], None
    while True:
        params: dict = {
            "series_ticker": series_ticker,
            "with_nested_markets": "true",
            "limit": "200",
        }
        if cursor:
            params["cursor"] = cursor
        url = f"{KALSHI_API_BASE}/events?{urlencode(params)}"
        data = http_get_json(url, timeout=60)
        events.extend(data.get("events") or [])
        cursor = data.get("cursor")
        if not cursor:
            break
    return events


def fetch_temperature_series(output_path: Path) -> list[str]:
    """Discover temperature series and persist the complete API response.

    The series endpoint is the source of discovery. The local seed catalog is
    still used as a fallback because an API response can be temporarily
    incomplete or a newly launched series can have an unexpected title.
    """
    url = f"{KALSHI_API_BASE}/series?include_product_metadata=true"
    payload = http_get_json(url, timeout=60)
    records = payload.get("series") or []
    output_path.write_text(json.dumps({
        "request_url": url,
        "retrieved_at": utcnow(),
        "series": records,
    }, indent=2) + "\n")
    tickers = {
        str(row.get("ticker", "")) for row in records
        if is_temperature_series(row)
    }
    return sorted(tickers | set(KALSHI_SERIES_CATALOG))


def is_temperature_series(record: dict) -> bool:
    """Recognize climate temperature templates without parsing market IDs."""
    category = str(record.get("category", ""))
    categories = {str(x) for x in (record.get("categories") or [])}
    title = str(record.get("title", "")).lower()
    ticker = str(record.get("ticker", ""))
    climate = category == "Climate and Weather" or "Climate and Weather" in categories
    return climate and ("temperature" in title or ticker.startswith(("KXHIGH", "KXLOWT", "KXTEMP")))


def series_context(series_ticker: str):
    """Return the metadata needed by row extraction for any catalog series."""
    info = KALSHI_SERIES_CATALOG.get(series_ticker)
    if info:
        city_key, temp_type, _frequency = info
    else:
        city_key = "unknown"
        temp_type = "hourly" if series_ticker.startswith("KXTEMP") else (
            "high" if series_ticker.startswith("KXHIGH") else
            "low" if series_ticker.startswith("KXLOWT") else ""
        )
    configured = CITIES.get(city_key)
    tz_name = configured.tz_name if configured else "UTC"
    return SimpleNamespace(key=city_key, tz_name=tz_name)


def parse_date_from_ticker(event_ticker: str) -> str | None:
    # KXHIGHTPHX-26SEP10
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})$", event_ticker)
    if not m:
        return None
    yy, mon, dd = m.group(1), m.group(2), int(m.group(3))
    month_map = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
                 "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
                 "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"}
    if mon not in month_map:
        return None
    return f"20{yy}-{month_map[mon]}-{dd:02d}"


def outcome_date_from_strike(event: dict, city) -> str:
    """Fallback reference only: Kalshi strike timestamps encode local
    midnight of the day following the outcome date, but the exact offset has
    not been verified per series, so this is never written as truth. It is
    only used to warn when the ticker date is missing."""
    strike = event.get("strike_date") or ""
    try:
        dt = datetime.fromisoformat(strike.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return ""
    return dt.astimezone(ZoneInfo(city.tz_name)).date().isoformat()


def parse_bucket(yes_sub: str | None, title: str | None) -> tuple:
    s = (yes_sub or "").strip()
    m = re.match(r"([\d.]+)°\s*to\s*([\d.]+)°", s)
    if m:
        return float(m.group(1)), float(m.group(2)), s
    m = re.match(r"([\d.]+)°\s*or below", s)
    if m:
        return None, float(m.group(1)), s
    m = re.match(r"([\d.]+)°\s*or above", s)
    if m:
        return float(m.group(1)), None, s
    # NOTE: tails beyond a single "N° or below" / "N° or above" pairing
    # (e.g. "less than 103°") are left unparsed on purpose: the exact
    # bookend arithmetic is series version-specific and has not been
    # verified; validate.py reports any unparsed bucket for review.
    # fallback: try title
    t = (title or "")
    m = re.search(r"([\d.]+)\s*to\s*([\d.]+)", t)
    if m:
        return float(m.group(1)), float(m.group(2)), s or t
    # number-first titles win when they come first (e.g. "Low of 73 or below")
    m = re.search(r"([\d.]+)\s*(?:°)?\s*(?:or below|or less|below)", t)
    if m:
        return None, float(m.group(1)), s or t
    m = re.search(r"([\d.]+)\s*(?:°)?\s*(?:or above|or more|above)", t)
    if m:
        return float(m.group(1)), None, s or t
    # keyword-first ordering, e.g. "below 73 degrees"
    m = re.search(r"(?:below|or less)\s*([\d.]+)", t)
    if m:
        return None, float(m.group(1)), s or t
    m = re.search(r"(?:above|or more)\s*([\d.]+)", t)
    if m:
        return float(m.group(1)), None, s or t
    return None, None, s or t


def _price(value: object) -> object:
    """Return a price float or '' ; never raises on foreign payloads."""
    if value in (None, "", "None", "null"):
        return ""
    if isinstance(value, str):
        if not re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", value.strip()):
            return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    return f


def extract_rows(events: list[dict], city) -> tuple[list[dict], list[dict]]:
    event_rows, market_rows = [], []
    for ev in events:
        ticker = ev.get("event_ticker", "")
        outcome_date = parse_date_from_ticker(ticker)
        if not outcome_date:
            strike_hint = outcome_date_from_strike(ev, city)
            print(f"  WARNING: cannot parse outcome date from ticker "
                  f"{ticker!r} (strike={strike_hint!r}); leaving "
                  f"outcome_local_date blank for review",
                  file=sys.stderr)
        city_key = city.key
        series_ticker = ev.get("series_ticker", "")
        temp_type = SERIES_TEMP_TYPE.get(series_ticker, "")
        if not temp_type:
            temp_type = KALSHI_SERIES_CATALOG.get(series_ticker, ("", "", ""))[1]
        srcs = ev.get("settlement_sources") or []
        src_name = srcs[0].get("name", "") if srcs else ""
        src_url = srcs[0].get("url", "") if srcs else ""
        event_rows.append({
            "event_ticker": ticker,
            "series_ticker": ev.get("series_ticker", ""),
            "city": city_key,
            "temp_type": temp_type,
            "outcome_local_date": outcome_date,
            "title": ev.get("title", ""),
            "sub_title": ev.get("sub_title", ""),
            "settlement_source_name": src_name,
            "settlement_source_url": src_url,
            "strike_date_utc": ev.get("strike_date", ""),
            "num_markets": len(ev.get("markets") or []),
        })
        for m in ev.get("markets") or []:
            floor, ceil, label = parse_bucket(
                m.get("yes_sub_title"), m.get("title"))
            last = _price(m.get("last_price_dollars"))
            yb = _price(m.get("yes_bid_dollars"))
            ya = _price(m.get("yes_ask_dollars"))
            mid = round((yb + ya) / 2, 4) if isinstance(yb, float) and isinstance(ya, float) else ""
            implied = round(last, 4) if isinstance(last, float) else mid if mid else ""
            spread = round(ya - yb, 4) if isinstance(ya, float) and isinstance(yb, float) else ""
            market_rows.append({
                "market_ticker": m.get("ticker", ""),
                "event_ticker": ticker,
                "series_ticker": ev.get("series_ticker", ""),
                "city": city_key,
                "temp_type": temp_type,
                "outcome_local_date": outcome_date,
                "title": ev.get("title", ""),
                "yes_sub_title": m.get("yes_sub_title", ""),
                "no_sub_title": m.get("no_sub_title", ""),
                "status": m.get("status", ""),
                "result": m.get("result", ""),
                "bucket_floor_f": floor,
                "bucket_ceil_f": ceil,
                "bucket_label": label,
                "last_price": last,
                "yes_bid": yb,
                "yes_ask": ya,
                "no_bid": _price(m.get("no_bid_dollars")),
                "no_ask": _price(m.get("no_ask_dollars")),
                "mid_price": mid,
                "implied_probability": implied,
                "volume_24h_fp": _price(m.get("volume_24h_fp")),
                "open_interest_fp": _price(m.get("open_interest_fp")),
                "liquidity_dollars": _price(m.get("liquidity_dollars")),
                "spread": spread,
                "open_time": m.get("open_time", ""),
                "close_time": m.get("close_time", ""),
                "expiration_time": m.get("expiration_time", ""),
                "settlement_ts": m.get("settlement_ts", ""),
            })
    return event_rows, market_rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cities", nargs="*", default=None)
    ap.add_argument("--series", nargs="*", default=None,
                    help="explicit series tickers; overrides --cities")
    ap.add_argument("--discover-temperature-series", action="store_true",
                    help="discover climate temperature series via /series")
    args = ap.parse_args()

    dirs = ensure_runtime_dirs()
    if args.series:
        series_tickers = args.series
    elif args.discover_temperature_series:
        series_tickers = fetch_temperature_series(
            dirs["kalshi_out"] / "series_catalog.json")
    else:
        cities = get_cities(args.cities or DEFAULT_CITIES)
        series_tickers = [
            series_ticker
            for city in cities
            for series_ticker in
            (city.kalshi_high_series, city.kalshi_low_series)
        ]
    unknown = sorted(set(series_tickers) - set(KALSHI_SERIES_CATALOG)
                     - set(SERIES_TEMP_TYPE))
    if unknown and not args.discover_temperature_series:
        ap.error(f"unknown series: {unknown}; use --discover-temperature-series")
    all_events, all_markets = [], []
    for series_ticker in series_tickers:
        city = series_context(series_ticker)
        print(f"[{city.key}] fetching {series_ticker} events...")
        evs = fetch_events(series_ticker)
        ev_rows, mk_rows = extract_rows(evs, city)
        all_events.extend(ev_rows)
        all_markets.extend(mk_rows)
        print(f"  {series_ticker}: {len(evs)} events, "
              f"{len(mk_rows)} markets")

    out_events = dirs["kalshi_out"] / "events.csv"
    with out_events.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EVENT_COLS)
        writer.writeheader()
        writer.writerows(all_events)
    print(f"wrote {out_events} ({len(all_events)} rows)")

    out_markets = dirs["kalshi_out"] / "markets.csv"
    with out_markets.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MARKET_COLS)
        writer.writeheader()
        writer.writerows(all_markets)
    print(f"wrote {out_markets} ({len(all_markets)} rows)")

    source_by_event = {r["event_ticker"]: r for r in all_events}
    outcome_rows = []
    for m in all_markets:
        ev = source_by_event.get(m["event_ticker"], {})
        outcome_rows.append({
            "outcome_local_date": m["outcome_local_date"],
            "city": m["city"], "temp_type": m["temp_type"],
            "event_ticker": m["event_ticker"], "market_ticker": m["market_ticker"],
            "bucket_floor_f": m["bucket_floor_f"], "bucket_ceil_f": m["bucket_ceil_f"],
            "bucket_label": m["bucket_label"], "status": m["status"],
            "settled_yes": ("yes" if m["result"] == "yes" else
                            "no" if m["status"] == "finalized" else ""),
            "settlement_ts": m["settlement_ts"],
            "settlement_source_name": ev.get("settlement_source_name", ""),
            "settlement_source_url": ev.get("settlement_source_url", ""),
        })
    out_outcomes = dirs["kalshi_out"] / "contract_outcomes.csv"
    with out_outcomes.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTCOME_COLS)
        writer.writeheader()
        writer.writerows(outcome_rows)
    print(f"wrote {out_outcomes} ({len(outcome_rows)} rows)")

    active = sum(1 for m in all_markets if m["status"] == "active")
    finalized = sum(1 for m in all_markets if m["status"] == "finalized")
    print(f"markets: {len(all_markets)} total, {active} active, "
          f"{finalized} finalized")
    print(f"fetched_at={utcnow()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
