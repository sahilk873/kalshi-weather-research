"""Bounded pull of Kalshi market candlesticks and public trades.

For the four Phoenix/Las Vegas daily-temperature series, this fetches:
1. **Daily candlesticks** (period=1440 min) for every market in the most
   recent events per series (active + recently finalized) via:
       GET /series/{s}/markets/{m}/candlesticks?period_interval=1440&...
       (see openapi.yaml lines 117-189, public, no auth)
2. **Hourly candlesticks** for current-day active markets, to illustrate the
   granular price-series pipeline without large fetches.
3. **Public trade history** for a subset of markets, via:
       GET /markets/trades?ticker=...&min_ts=...&max_ts=...&limit=1000
       (see openapi.yaml lines 191-216, public, no auth)

For recently settled markets, the standard candlestick endpoint returns data
because settlement occurred after the historical cutoff (2026-07-13).

Rate-limiting: up to 200 ms sleep between calls. Each output row carries
fetched_at and request_ts for reproducibility.

Outputs (data/weather_research/kalshi/):
- candlesticks_hourly.csv
- candlesticks_daily.csv
- trades.csv
- candles_raw/<market_ticker>.json   (per-market cache)
- trades_raw/<market_ticker>.json

CLI:
  python3 scripts/weather/kalshi_trades_candles.py
  python3 scripts/weather/kalshi_trades_candles.py --max-events-per-series 2
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

# ruff: noqa: E402
import common  # noqa: E402
from common import ensure_runtime_dirs, http_get, http_get_json, utcnow  # noqa: E402
from stations import DEFAULT_CITIES, KALSHI_API_BASE, get_cities  # noqa: E402

CANDLES_DAILY_COLS = [
    "market_ticker", "event_ticker", "series_ticker", "period_interval",
    "end_period_ts", "date_utc",
    "yes_bid_open", "yes_bid_high", "yes_bid_low", "yes_bid_close",
    "yes_ask_open", "yes_ask_high", "yes_ask_low", "yes_ask_close",
    "trade_open", "trade_high", "trade_low", "trade_close", "trade_mean",
    "trade_previous", "trade_min", "trade_max",
    "volume_fp", "open_interest_fp", "fetched_at",
]
CANDLES_HOURLY_COLS = CANDLES_DAILY_COLS
TRADES_COLS = [
    "trade_id", "market_ticker", "count_fp", "yes_price_dollars",
    "no_price_dollars", "taker_book_side", "taker_outcome_side",
    "created_time", "is_block_trade", "fetched_at",
]
SLEEP = 0.20


def fetch_candlesticks(series_ticker: str, market_ticker: str,
                        start_ts: int, end_ts: int,
                        period_interval: int = 1440,
                        raw_dir: Path | None = None) -> dict:
    """Return JSON response for one market's candlesticks."""
    params = {
        "start_ts": start_ts, "end_ts": end_ts,
        "period_interval": period_interval,
        "include_latest_before_start": "false",
    }
    url = (f"{KALSHI_API_BASE}/series/{series_ticker}/markets/{market_ticker}"
           f"/candlesticks?{urlencode(params)}")
    data = http_get_json(url, timeout=60)
    if raw_dir:
        dest = raw_dir / f"{market_ticker}_p{period_interval}.json"
        dest.write_text(json.dumps(data, indent=2))
    return data


def fetch_trades_for_market(market_ticker: str,
                             min_ts: int, max_ts: int,
                             raw_dir: Path | None = None) -> list[dict]:
    trades: list[dict] = []
    cursor: str | None = None
    while True:
        params: dict = {
            "ticker": market_ticker,
            "min_ts": str(min_ts),
            "max_ts": str(max_ts),
            "limit": "1000",
        }
        if cursor:
            params["cursor"] = cursor
        url = f"{KALSHI_API_BASE}/markets/trades?{urlencode(params)}"
        data = http_get_json(url, timeout=60)
        trades.extend(data.get("trades") or [])
        cursor = data.get("cursor")
        if not cursor:
            break
        time.sleep(SLEEP)
    if raw_dir:
        dest = raw_dir / f"{market_ticker}_trades.json"
        dest.write_text(json.dumps(trades, indent=2))
    return trades


def parse_market_list(events_csv: Path) -> list[dict]:
    """Return markets from the normalized events/markets CSV."""
    markets = []
    with events_csv.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r["status"] not in ("active", "finalized"):
                continue
            markets.append(r)
    return markets


def parse_ts(t: str) -> int | None:
    if not t:
        return None
    try:
        return int(datetime.fromisoformat(t.replace("Z", "+00:00"))
                   .timestamp())
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cities", nargs="*", default=None)
    ap.add_argument("--max-events-per-series", type=int, default=3,
                    help="how many recent events per series to fetch")
    ap.add_argument("--hourly-hours", type=int, default=48,
                    help="hours of hourly candle history for active markets")
    args = ap.parse_args()

    dirs = ensure_runtime_dirs()
    cities = get_cities(args.cities or DEFAULT_CITIES)
    candles_dir = dirs["kalshi_out"] / "candles_raw"
    trades_dir = dirs["kalshi_out"] / "trades_raw"
    candles_dir.mkdir(parents=True, exist_ok=True)
    trades_dir.mkdir(parents=True, exist_ok=True)

    # Load already-fetched market metadata to know event_ticker, open/close
    events_csv = dirs["kalshi_out"] / "events.csv"
    markets_csv = dirs["kalshi_out"] / "markets.csv"
    if not markets_csv.exists():
        print("ERROR: data/weather_research/kalshi/markets.csv missing; "
              "run kalshi_meta.py first", file=sys.stderr)
        return 1
    all_markets = parse_market_list(markets_csv)
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())

    # Select up to N most recent events per series (by outcome_local_date desc)
    series_markets: dict[str, list[dict]] = {}
    for m in all_markets:
        series_markets.setdefault(m["series_ticker"], []).append(m)
    selected_markets: list[dict] = []
    for series, mlist in series_markets.items():
        by_event: dict[str, list[dict]] = {}
        for m in mlist:
            by_event.setdefault(m["event_ticker"], []).append(m)
        events_sorted = sorted(by_event.keys(), reverse=True)
        for ev in events_sorted[:args.max_events_per_series]:
            selected_markets.extend(by_event[ev])
    print(f"selected {len(selected_markets)} markets from "
          f"{args.max_events_per_series} most recent events per series")

    # --- daily candles ---
    daily_rows: list[dict] = []
    for i, m in enumerate(selected_markets, 1):
        s_ticker = m["series_ticker"]
        mk_ticker = m["market_ticker"]
        o = parse_ts(m.get("open_time")) or (now_ts - 14 * 86400)
        e = now_ts
        try:
            data = fetch_candlesticks(s_ticker, mk_ticker, o, e, 1440,
                                      raw_dir=candles_dir)
        except Exception as exc:
            print(f"[{i}/{len(selected_markets)}] FAIL candles {mk_ticker}: {exc}")
            time.sleep(SLEEP)
            continue
        for c in data.get("candlesticks") or []:
            daily_rows.append(_flatten_candle(m, c, 1440))
        print(f"[{i}/{len(selected_markets)}] candles {mk_ticker} "
              f"{len(data.get('candlesticks') or [])} candles")
        time.sleep(SLEEP)
    daily_csv = dirs["kalshi_out"] / "candlesticks_daily.csv"
    with daily_csv.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANDLES_DAILY_COLS)
        writer.writeheader()
        writer.writerows(daily_rows)
    print(f"wrote {daily_csv} ({len(daily_rows)} rows)")

    # --- hourly candles for active markets only ---
    hourly_rows: list[dict] = []
    active = [m for m in selected_markets if m["status"] == "active"]
    for i, m in enumerate(active, 1):
        s_ticker = m["series_ticker"]
        mk_ticker = m["market_ticker"]
        o = parse_ts(m.get("open_time")) or (now_ts - 86400)
        try:
            data = fetch_candlesticks(s_ticker, mk_ticker, o, now_ts, 60,
                                      raw_dir=candles_dir)
        except Exception as exc:
            print(f"[{i}/{len(active)}] FAIL hourly {mk_ticker}: {exc}")
            time.sleep(SLEEP)
            continue
        for c in data.get("candlesticks") or []:
            hourly_rows.append(_flatten_candle(m, c, 60))
        print(f"[{i}/{len(active)}] hourly {mk_ticker} "
              f"{len(data.get('candlesticks') or [])} candles")
        time.sleep(SLEEP)
    hourly_csv = dirs["kalshi_out"] / "candlesticks_hourly.csv"
    with hourly_csv.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANDLES_HOURLY_COLS)
        writer.writeheader()
        writer.writerows(hourly_rows)
    print(f"wrote {hourly_csv} ({len(hourly_rows)} rows)")

    # --- public trades for active + most-recent finalized event markets ---
    trade_rows: list[dict] = []
    for i, m in enumerate(selected_markets, 1):
        mk_ticker = m["market_ticker"]
        o = parse_ts(m.get("open_time")) or (now_ts - 14 * 86400)
        try:
            trades = fetch_trades_for_market(mk_ticker, o, now_ts, trades_dir)
        except Exception as exc:
            print(f"[{i}/{len(selected_markets)}] FAIL trades {mk_ticker}: {exc}")
            time.sleep(SLEEP)
            continue
        for t in trades:
            trade_rows.append({
                "trade_id": t.get("trade_id", ""),
                "market_ticker": mk_ticker,
                "count_fp": t.get("count_fp", ""),
                "yes_price_dollars": t.get("yes_price_dollars", ""),
                "no_price_dollars": t.get("no_price_dollars", ""),
                "taker_book_side": t.get("taker_book_side", ""),
                "taker_outcome_side": t.get("taker_outcome_side", ""),
                "created_time": t.get("created_time", ""),
                "is_block_trade": t.get("is_block_trade", ""),
                "fetched_at": utcnow(),
            })
        print(f"[{i}/{len(selected_markets)}] trades {mk_ticker} "
              f"{len(trades)} trades")
        time.sleep(SLEEP)
    trades_csv = dirs["kalshi_out"] / "trades.csv"
    with trades_csv.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=TRADES_COLS)
        writer.writeheader()
        writer.writerows(trade_rows)
    print(f"wrote {trades_csv} ({len(trade_rows)} rows)")
    print(f"fetched_at={utcnow()}")
    return 0


def _flatten_candle(meta: dict, c: dict, interval: int) -> dict:
    ts = c.get("end_period_ts", 0)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
    def fval(obj: dict | None, key: str) -> float | str:
        if obj is None:
            return ""
        v = obj.get(key)
        return float(v) if v not in (None, "", "null") else ""
    return {
        "market_ticker": meta.get("market_ticker", ""),
        "event_ticker": meta.get("event_ticker", ""),
        "series_ticker": meta.get("series_ticker", ""),
        "period_interval": interval,
        "end_period_ts": ts,
        "date_utc": dt.date().isoformat() if dt else "",
        "yes_bid_open": fval(c.get("yes_bid"), "open_dollars"),
        "yes_bid_high": fval(c.get("yes_bid"), "high_dollars"),
        "yes_bid_low": fval(c.get("yes_bid"), "low_dollars"),
        "yes_bid_close": fval(c.get("yes_bid"), "close_dollars"),
        "yes_ask_open": fval(c.get("yes_ask"), "open_dollars"),
        "yes_ask_high": fval(c.get("yes_ask"), "high_dollars"),
        "yes_ask_low": fval(c.get("yes_ask"), "low_dollars"),
        "yes_ask_close": fval(c.get("yes_ask"), "close_dollars"),
        "trade_open": fval(c.get("price"), "open_dollars"),
        "trade_high": fval(c.get("price"), "high_dollars"),
        "trade_low": fval(c.get("price"), "low_dollars"),
        "trade_close": fval(c.get("price"), "close_dollars"),
        "trade_mean": fval(c.get("price"), "mean_dollars"),
        "trade_previous": fval(c.get("price"), "previous_dollars"),
        "trade_min": fval(c.get("price"), "min_dollars"),
        "trade_max": fval(c.get("price"), "max_dollars"),
        "volume_fp": fval(c, "volume_fp"),
        "open_interest_fp": fval(c, "open_interest_fp"),
        "fetched_at": utcnow(),
    }


if __name__ == "__main__":
    raise SystemExit(main())