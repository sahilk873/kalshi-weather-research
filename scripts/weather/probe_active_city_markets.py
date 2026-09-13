"""Archive open Kalshi temperature markets for NYC, Los Angeles, and Austin."""
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

# Current NYC intraday listings use KXTEMPNYCHS. Keep the older ticker for
# historical archive compatibility.
# Current intraday listings use the ``*HS`` tickers; older identifiers remain
# in the registry so historical archives continue to be probed as well.
SERIES = ("KXTEMPNYCHS", "KXTEMPNYCH", "KXTEMPLAXHS", "KXTEMPLAXH", "KXTEMPAUSH", "KXHIGHNY", "KXLOWTNYC",
          "KXHIGHLAX", "KXLOWTLAX", "KXHIGHAUS", "KXLOWTAUS")


def probe(output_dir: Path, series: tuple[str, ...] = SERIES) -> dict:
    receipt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payloads: dict[str, dict] = {}
    for ticker in series:
        url = f"{KALSHI_API_BASE}/markets?{urlencode({'series_ticker': ticker, 'status': 'open', 'limit': '100'})}"
        payloads[ticker] = http_get_json(url, timeout=60)
    body = json.dumps(payloads, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(body).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = output_dir / f"active_{receipt.replace(':', '').replace('-', '')}.json"
    raw.write_bytes(body)
    quote_path = output_dir / f"quotes_{receipt.replace(':', '').replace('-', '')}.csv"
    quote_fields = ["market_ticker", "event_ticker", "open_time", "close_time",
                    "received_ts", "yes_bid", "yes_ask", "yes_bid_size",
                    "yes_ask_size", "no_bid", "no_ask", "status"]
    with quote_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=quote_fields)
        writer.writeheader()
        for payload in payloads.values():
            for market in payload.get("markets") or []:
                writer.writerow({"market_ticker": market.get("ticker", ""),
                                 "event_ticker": market.get("event_ticker", ""),
                                 "open_time": market.get("open_time", ""),
                                 "close_time": market.get("close_time", ""),
                                 "received_ts": receipt,
                                 "yes_bid": market.get("yes_bid_dollars", ""),
                                 "yes_ask": market.get("yes_ask_dollars", ""),
                                 "yes_bid_size": market.get("yes_bid_size_fp", ""),
                                 "yes_ask_size": market.get("yes_ask_size_fp", ""),
                                 "no_bid": market.get("no_bid_dollars", ""),
                                 "no_ask": market.get("no_ask_dollars", ""),
                                 "status": market.get("status", "")})
    counts = {ticker: len(payload.get("markets") or []) for ticker, payload in payloads.items()}
    tickers = sorted(m.get("ticker") for payload in payloads.values() for m in (payload.get("markets") or []) if m.get("ticker"))
    result = {"version": "active-city-market-probe-v1", "series": list(series),
              "retrieved_at_utc": receipt, "raw_path": str(raw), "raw_sha256": digest,
              "quote_path": str(quote_path),
              "open_counts": counts, "open_tickers": tickers,
              "hourly_open_count": sum(counts[s] for s in series if s.startswith("KXTEMP")),
              "daily_open_count": sum(counts[s] for s in series if not s.startswith("KXTEMP")),
              "pass": bool(tickers)}
    (output_dir / "latest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/weather_research/kalshi_city/active_probe"))
    args = parser.parse_args()
    result = probe(args.output_dir)
    print(json.dumps({"hourly_open_count": result["hourly_open_count"], "daily_open_count": result["daily_open_count"], "pass": result["pass"]}, sort_keys=True))


if __name__ == "__main__":
    main()
