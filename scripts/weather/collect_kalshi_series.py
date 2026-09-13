"""Archive and normalize one Kalshi series, including hourly NYC terms.

The full API payloads are immutable evidence.  Normalized rows retain receipt
time and a hash of the exact payload so settlement rules can be re-audited
without relying on inferred ticker conventions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from common import http_get_json
from stations import KALSHI_API_BASE

EVENT_FIELDS = [
    "event_ticker", "series_ticker", "title", "sub_title", "event_url",
    "strike_date", "settlement_sources", "market_count", "retrieved_at_utc",
    "raw_sha256", "raw_path",
]
MARKET_FIELDS = [
    "ticker", "event_ticker", "series_ticker", "title", "subtitle",
    "yes_sub_title", "no_sub_title", "status", "result", "open_time",
    "close_time", "expiration_time", "settlement_ts", "yes_bid",
    "yes_ask", "last_price", "volume_fp", "open_interest_fp",
    "retrieved_at_utc", "raw_sha256", "raw_path",
]

_LAST_CRAWL = {"pages": 0, "cursor_complete": False}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash_payload(payload: object) -> tuple[bytes, str]:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return body, hashlib.sha256(body).hexdigest()


def _write_raw(path: Path, payload: object) -> str:
    body, digest = _hash_payload(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return digest


def _fetch_series(series: str) -> dict:
    return http_get_json(f"{KALSHI_API_BASE}/series/{series}", timeout=60)


def _fetch_events(series: str, limit: int = 200) -> list[dict]:
    global _LAST_CRAWL
    events: list[dict] = []
    cursor = ""
    pages = 0
    while True:
        pages += 1
        params = {"series_ticker": series, "with_nested_markets": "true", "limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        payload = http_get_json(f"{KALSHI_API_BASE}/events?{urlencode(params)}", timeout=60)
        events.extend(payload.get("events") or [])
        cursor = payload.get("cursor") or ""
        if not cursor:
            _LAST_CRAWL = {"pages": pages, "cursor_complete": True}
            return events


def _value(row: dict, *keys: str):
    for key in keys:
        if key in row:
            return row.get(key)
    return ""


def collect(series: str, output_dir: Path) -> tuple[int, int]:
    receipt = _now()
    raw_dir = output_dir / "raw"
    series_payload = _fetch_series(series)
    series_raw = raw_dir / f"series_{series}_{receipt.replace(':', '').replace('-', '')}.json"
    series_hash = _write_raw(series_raw, series_payload)
    events = _fetch_events(series)
    event_rows: list[dict] = []
    market_rows: list[dict] = []
    for idx, event in enumerate(events):
        event_body, event_hash = _hash_payload(event)
        event_raw = raw_dir / f"event_{idx:05d}_{event.get('event_ticker', series)}_{receipt.replace(':', '').replace('-', '')}.json"
        event_raw.parent.mkdir(parents=True, exist_ok=True)
        event_raw.write_bytes(event_body)
        sources = event.get("settlement_sources") or []
        event_rows.append({
            "event_ticker": event.get("event_ticker", ""), "series_ticker": event.get("series_ticker", series),
            "title": event.get("title", ""), "sub_title": event.get("sub_title", ""),
            "event_url": event.get("event_url", ""), "strike_date": event.get("strike_date", ""),
            "settlement_sources": json.dumps(sources, sort_keys=True, separators=(",", ":")),
            "market_count": len(event.get("markets") or []), "retrieved_at_utc": receipt,
            "raw_sha256": event_hash, "raw_path": str(event_raw),
        })
        for market in event.get("markets") or []:
            market_rows.append({
                "ticker": market.get("ticker", ""), "event_ticker": event.get("event_ticker", ""),
                "series_ticker": event.get("series_ticker", series), "title": market.get("title", ""),
                "subtitle": market.get("subtitle", ""), "yes_sub_title": market.get("yes_sub_title", ""),
                "no_sub_title": market.get("no_sub_title", ""), "status": market.get("status", ""),
                "result": market.get("result", ""), "open_time": market.get("open_time", ""),
                "close_time": market.get("close_time", ""), "expiration_time": market.get("expiration_time", ""),
                "settlement_ts": market.get("settlement_ts", ""),
                "yes_bid": _value(market, "yes_bid_dollars", "yes_bid"),
                "yes_ask": _value(market, "yes_ask_dollars", "yes_ask"),
                "last_price": _value(market, "last_price_dollars", "last_price"),
                "volume_fp": _value(market, "volume_fp", "volume"),
                "open_interest_fp": _value(market, "open_interest_fp", "open_interest"),
                "retrieved_at_utc": receipt, "raw_sha256": event_hash, "raw_path": str(event_raw),
            })
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "series.json").open("w") as handle:
        json.dump({"retrieved_at_utc": receipt, "raw_sha256": series_hash,
                   "raw_path": str(series_raw), "series": series_payload.get("series", series_payload)},
                  handle, indent=2, sort_keys=True)
    manifest_path = output_dir / "manifest.json"
    manifest = {"snapshots": []}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, ValueError):
            manifest = {"snapshots": []}
    manifest.setdefault("snapshots", []).append({
        "retrieved_at_utc": receipt, "series": series,
        "series_raw_path": str(series_raw), "series_sha256": series_hash,
        "event_count": len(event_rows), "market_count": len(market_rows),
        "cursor_complete": bool(_LAST_CRAWL.get("cursor_complete")),
        "crawl_pages": int(_LAST_CRAWL.get("pages", 0)),
        "oldest_strike_date": min((row["strike_date"] for row in event_rows if row["strike_date"]), default=""),
        "newest_strike_date": max((row["strike_date"] for row in event_rows if row["strike_date"]), default=""),
    })
    manifest["latest"] = manifest["snapshots"][-1]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    for name, rows, fields in (("events.csv", event_rows, EVENT_FIELDS), ("markets.csv", market_rows, MARKET_FIELDS)):
        with (output_dir / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return len(event_rows), len(market_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", default="KXTEMPNYCH")
    parser.add_argument("--output-dir", type=Path, default=Path("data/weather_research/kalshi_hourly"))
    args = parser.parse_args()
    events, markets = collect(args.series, args.output_dir)
    print(f"archived {args.series}: {events} events, {markets} markets")


if __name__ == "__main__":
    main()
