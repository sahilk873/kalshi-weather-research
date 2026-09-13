"""Collect historical city Kalshi candles and trades through REST endpoints.

This is distinct from historical full-depth L2: REST candles/trades expose
executed activity and aggregate bid/ask values, not prior order-book depth.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from common import http_get_json
from stations import KALSHI_API_BASE


FIELDS = ["market_ticker", "event_ticker", "period_interval", "end_period_ts", "yes_bid_open", "yes_bid_high", "yes_bid_low", "yes_bid_close", "yes_ask_open", "yes_ask_high", "yes_ask_low", "yes_ask_close", "trade_open", "trade_high", "trade_low", "trade_close", "volume_fp", "open_interest_fp", "fetched_at"]
TRADE_FIELDS = ["trade_id", "market_ticker", "count_fp", "yes_price_dollars", "no_price_dollars", "taker_book_side", "taker_outcome_side", "created_time", "is_block_trade", "fetched_at"]
MARKET_METADATA_FIELDS = ["market_ticker", "event_ticker", "series_ticker", "status", "result", "open_time", "close_time", "expiration_time", "settlement_ts", "settlement_source_name", "settlement_source_url", "settlement_station", "retrieved_at_utc"]


def _ts(value: str) -> int | None:
    try: return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError): return None


def _write_immutable_raw(raw_dir: Path, stem: str, payload: dict, receipt: str,
                         endpoint: str, records: list[dict]) -> tuple[str, str]:
    """Persist a response without silently overwriting a prior payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    path = raw_dir / f"{stem}.json"
    if path.exists():
        try:
            existing_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            existing_digest = ""
        if existing_digest not in {digest, hashlib.sha256(encoded + b"\n").hexdigest()}:
            safe_receipt = receipt.replace(":", "").replace("-", "").replace(".", "")
            path = raw_dir / f"{stem}_retrieved_{safe_receipt}.json"
    if not path.exists():
        path.write_bytes(encoded + b"\n")
    records.append({"raw_path": str(path), "sha256": digest,
                    "retrieved_at_utc": receipt, "endpoint": endpoint})
    return str(path), digest


def _markets(series_ticker: str, limit: int, skip: int = 0,
             *, raw_dir: Path | None = None, receipt: str | None = None,
             raw_records: list[dict] | None = None) -> list[dict]:
    rows, cursor, page = [], "", 0
    target = max(0, skip) + limit
    while len(rows) < target:
        params = {"series_ticker": series_ticker, "limit": min(1000, target - len(rows))}
        if cursor: params["cursor"] = cursor
        endpoint = f"{KALSHI_API_BASE}/historical/markets?{urlencode(params)}"
        payload = http_get_json(endpoint, timeout=60)
        if raw_dir is not None and receipt is not None and raw_records is not None:
            _write_immutable_raw(raw_dir, f"historical_markets_page{page:04d}", payload,
                                 receipt, "/historical/markets", raw_records)
        rows.extend(payload.get("markets") or [])
        cursor = payload.get("cursor") or ""
        page += 1
        if not cursor: break
    return rows[max(0, skip):max(0, skip) + limit]


def _fetch_market(market: dict, raw_dir: Path, receipt: str) -> tuple[list[dict], list[dict], list[dict], dict | None]:
    """Fetch one market's aggregate quote/trade history."""
    ticker = market.get("ticker", "")
    start = _ts(market.get("open_time", ""))
    end = _ts(market.get("close_time", "")) or _ts(market.get("settlement_ts", ""))
    if not ticker or start is None or end is None or end < start:
        return [], [], [], {"market_ticker": ticker, "reason": "invalid_market_window"}
    raw_records: list[dict] = []
    params = {"period_interval": 60, "start_ts": start, "end_ts": end}
    try:
        candle_payload = http_get_json(f"{KALSHI_API_BASE}/historical/markets/{ticker}/candlesticks?{urlencode(params)}", timeout=60)
    except Exception as exc:
        return [], [], [], {"market_ticker": ticker, "reason": f"candle_fetch_failed:{type(exc).__name__}"}
    _write_immutable_raw(raw_dir, f"{ticker}_candles", candle_payload, receipt,
                         f"/historical/markets/{ticker}/candlesticks", raw_records)
    candles = []
    for item in candle_payload.get("candlesticks") or []:
        row = {"market_ticker": ticker, "event_ticker": market.get("event_ticker", ""), "period_interval": 60, "end_period_ts": item.get("end_period_ts", ""), "fetched_at": receipt}
        for side in ("yes_bid", "yes_ask"):
            for key in ("open", "high", "low", "close"):
                row[f"{side}_{key}"] = (item.get(side) or {}).get(f"{key}_dollars", (item.get(side) or {}).get(key, ""))
        for key in ("open", "high", "low", "close"):
            row[f"trade_{key}"] = (item.get("price") or {}).get(f"{key}_dollars", (item.get("price") or {}).get(key, ""))
        row["volume_fp"] = item.get("volume_fp", item.get("volume", "")); row["open_interest_fp"] = item.get("open_interest_fp", item.get("open_interest", "")); candles.append(row)
    trades = []
    cursor = ""
    page = 0
    while True:
        query = {"ticker": ticker, "min_ts": start, "max_ts": end, "limit": 1000}
        if cursor:
            query["cursor"] = cursor
        try:
            trade_payload = http_get_json(f"{KALSHI_API_BASE}/historical/trades?{urlencode(query)}", timeout=60)
        except Exception as exc:
            return candles, trades, raw_records, {"market_ticker": ticker, "reason": f"trade_fetch_failed_page_{page}:{type(exc).__name__}"}
        _write_immutable_raw(raw_dir, f"{ticker}_trades_page{page:04d}", trade_payload, receipt,
                             "/historical/trades", raw_records)
        trades.extend({"trade_id": trade.get("trade_id", ""), "market_ticker": ticker, "count_fp": trade.get("count_fp", ""), "yes_price_dollars": trade.get("yes_price_dollars", ""), "no_price_dollars": trade.get("no_price_dollars", ""), "taker_book_side": trade.get("taker_book_side", ""), "taker_outcome_side": trade.get("taker_outcome_side", ""), "created_time": trade.get("created_time", ""), "is_block_trade": trade.get("is_block_trade", ""), "fetched_at": receipt} for trade in (trade_payload.get("trades") or []))
        cursor = trade_payload.get("cursor") or ""
        if not cursor:
            break
        page += 1
    return candles, trades, raw_records, None


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _merge_rows(path: Path, rows: list[dict], key_fields: tuple[str, ...], append: bool) -> list[dict]:
    if not append or not path.exists():
        return rows
    existing = _rows(path)
    merged = {tuple(row.get(key, "") for key in key_fields): row for row in existing}
    merged.update({tuple(row.get(key, "") for key in key_fields): row for row in rows})
    return list(merged.values())


def collect(output_dir: Path, limit: int = 100, sleep_seconds: float = 0.1, workers: int = 1,
            skip: int = 0, append: bool = False, series_ticker: str = "KXTEMPNYCH",
            metadata_only: bool = False) -> dict:
    if not series_ticker.startswith("KXTEMP"):
        raise ValueError("series_ticker must be a Kalshi hourly temperature series")
    output_dir.mkdir(parents=True, exist_ok=True); raw_dir = output_dir / "raw"; raw_dir.mkdir(exist_ok=True)
    receipt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    candles, trades, raw_records, failures = [], [], [], []
    markets = _markets(series_ticker, limit, skip, raw_dir=raw_dir,
                       receipt=receipt, raw_records=raw_records)
    if metadata_only:
        results = [([], [], [], None) for _ in markets]
    elif workers <= 1:
        results = [_fetch_market(market, raw_dir, receipt) for market in markets]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_fetch_market, market, raw_dir, receipt) for market in markets]
            results = [future.result() for future in as_completed(futures)]
    for market_candles, market_trades, market_records, failure in results:
        candles.extend(market_candles); trades.extend(market_trades); raw_records.extend(market_records)
        if failure: failures.append(failure)
        if sleep_seconds and workers <= 1 and not metadata_only: time.sleep(sleep_seconds)
    candles.sort(key=lambda row: (row.get("market_ticker", ""), str(row.get("end_period_ts", ""))))
    trades.sort(key=lambda row: (row.get("market_ticker", ""), str(row.get("created_time", "")), row.get("trade_id", "")))
    raw_records.sort(key=lambda row: row.get("raw_path", ""))
    metadata = [{
        "market_ticker": market.get("ticker", ""),
        "event_ticker": market.get("event_ticker", ""),
        "series_ticker": market.get("series_ticker", series_ticker),
        "status": market.get("status", ""),
        "result": market.get("result", ""),
        "open_time": market.get("open_time", ""),
        "close_time": market.get("close_time", ""),
        "expiration_time": market.get("expiration_time", ""),
        "settlement_ts": market.get("settlement_ts", ""),
        "settlement_source_name": market.get("settlement_source_name", ""),
        "settlement_source_url": market.get("settlement_source_url", ""),
        "settlement_station": market.get("settlement_station", ""),
        "retrieved_at_utc": receipt,
    } for market in markets]
    metadata = _merge_rows(output_dir / "market_metadata.csv", metadata,
                           ("market_ticker",), append)
    candles = _merge_rows(output_dir / "candles_hourly.csv", candles,
                          ("market_ticker", "end_period_ts"), append)
    trades = _merge_rows(output_dir / "trades.csv", trades, ("trade_id",), append)
    for name, rows, fields in (("candles_hourly.csv", candles, FIELDS), ("trades.csv", trades, TRADE_FIELDS),
                               ("market_metadata.csv", metadata, MARKET_METADATA_FIELDS)):
        with (output_dir / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    raw_manifest = output_dir / "raw_manifest.jsonl"
    prior_raw = []
    if append and raw_manifest.exists():
        prior_raw = [line for line in raw_manifest.read_text().splitlines() if line.strip()]
    with raw_manifest.open("a") as handle:
        for record in raw_records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    failures_path = output_dir / "rejections.csv"
    prior_failures = _rows(failures_path) if append else []
    merged_failures = {row.get("market_ticker", ""): row for row in prior_failures}
    merged_failures.update({row.get("market_ticker", ""): row for row in failures})
    with failures_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["market_ticker", "reason"]); writer.writeheader(); writer.writerows(sorted(merged_failures.values(), key=lambda row: row.get("market_ticker", "")))
    market_tickers = {row.get("market_ticker", "") for row in candles + trades if row.get("market_ticker", "")}
    metadata_total = len(metadata)
    next_offset = skip + len(markets)
    coverage_denominator = max(metadata_total, next_offset)
    manifest = {"version": "historical-nyc-quotes-v3" if series_ticker == "KXTEMPNYCH" else "historical-city-quotes-v3", "series_ticker": series_ticker, "retrieved_at_utc": receipt, "requested_markets": limit, "market_offset": skip, "markets_requested_in_batch": len(markets), "metadata_only": metadata_only, "markets_processed": len(market_tickers), "candle_rows": len(candles), "trade_rows": len(trades), "market_metadata_rows": metadata_total, "metadata_coverage_fraction": (metadata_total / coverage_denominator if coverage_denominator else 0.0), "next_market_offset": next_offset, "raw_payloads": len(prior_raw) + len(raw_records), "failed_markets": len(merged_failures), "rejections_path": str(failures_path), "raw_manifest": str(raw_manifest), "endpoint": "historical REST; no prior L2 depth"}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--series-ticker", default="KXTEMPNYCH", choices=("KXTEMPNYCH", "KXTEMPLAXH", "KXTEMPAUSH")); parser.add_argument("--limit", type=int, default=100); parser.add_argument("--skip", type=int, default=0); parser.add_argument("--append", action="store_true"); parser.add_argument("--sleep", type=float, default=0.1); parser.add_argument("--workers", type=int, default=1); parser.add_argument("--metadata-only", action="store_true", help="archive market-list pages and metadata without fetching candles/trades"); parser.add_argument("--output-dir", type=Path, default=None); args = parser.parse_args(); output = args.output_dir or (Path("data/weather_research") / "kalshi_hourly" / "historical_quotes" if args.series_ticker == "KXTEMPNYCH" else Path("data/weather_research") / "kalshi_hourly" / args.series_ticker.lower() / "historical_quotes"); print(json.dumps(collect(output, args.limit, args.sleep, max(1, args.workers), max(0, args.skip), args.append, args.series_ticker, args.metadata_only), sort_keys=True))


if __name__ == "__main__": main()
