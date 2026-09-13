"""Probe and archive the public active KXTEMPNYCHS market response."""
from __future__ import annotations

import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from common import http_get_json
from stations import KALSHI_API_BASE


def probe(output_dir: Path) -> dict:
    receipt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    series_ticker = "KXTEMPNYCHS"
    url = f"{KALSHI_API_BASE}/markets?{urlencode({'series_ticker': series_ticker, 'status': 'open', 'limit': '100'})}"
    payload = http_get_json(url, timeout=60)
    events_url = f"{KALSHI_API_BASE}/events?{urlencode({'series_ticker': series_ticker, 'status': 'open', 'with_nested_markets': 'true', 'limit': '100'})}"
    events_payload = http_get_json(events_url, timeout=60)
    combined = {"markets": payload, "events": events_payload}
    body = json.dumps(combined, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(body).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = output_dir / f"active_{receipt.replace(':', '').replace('-', '')}.json"
    raw.write_bytes(body)
    result = {"version": "active-nyc-market-probe-v1", "series_ticker": series_ticker, "status_filter": "open", "retrieved_at_utc": receipt, "raw_path": str(raw), "raw_sha256": digest, "active_market_count": len(payload.get("markets") or []), "active_event_count": len(events_payload.get("events") or []), "market_cursor": payload.get("cursor") or "", "event_cursor": events_payload.get("cursor") or "", "pass": bool(payload.get("markets") or events_payload.get("events"))}
    (output_dir / "latest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output-dir", type=Path, default=Path("data/weather_research/kalshi_hourly/active_probe")); args = parser.parse_args(); result = probe(args.output_dir); print(json.dumps({"active_market_count": result["active_market_count"], "pass": result["pass"]}))


if __name__ == "__main__": main()
