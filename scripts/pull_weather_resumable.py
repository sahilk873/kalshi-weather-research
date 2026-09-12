#!/usr/bin/env python3
"""Resumable pull of all weather events+markets from Kalshi's public API.

Design:
- One JSON file per series under data/series/<TICKER>.json so partial progress
  is never lost and reruns only fetch what's missing.
- Robust backoff for HTTP 429 and transient network/DNS errors.
- After all series are fetched, ``merge_weather_outputs.py`` rebuilds the
  combined kalshi_weather_* files.

No API key required (market-data endpoints are public).
"""

import json
import time
from pathlib import Path

import requests

BASE = "https://external-api.kalshi.com/trade-api/v2"
ROOT = Path(__file__).resolve().parent.parent
SERIES_DIR = ROOT / "data" / "series"
SERIES_INDEX = ROOT / "data" / "kalshi_weather_series.json"
SERIES_DIR.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "kalshi-weather-pull/1.0 (resumable)"}
SESSION = requests.Session()
SESSION.headers.update(UA)
SESSION.mount(
    "https://",
    requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4),
)


def get_json(url, params=None, max_retries=8):
    for attempt in range(max_retries):
        try:
            resp = SESSION.get(url, params=params, timeout=60)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", 5)) + 2
                print(f"    429 -> sleep {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                time.sleep(min(15, 4 * (attempt + 1)))
                continue
            resp.raise_for_status()
        except requests.RequestException as exc:
            wait = min(20, 4 * (attempt + 1))
            print(f"    net-error ({type(exc).__name__}) -> sleep {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"failed after {max_retries} retries: {url}")


def fetch_series(ticker):
    events, cursor = [], None
    while True:
        params = {
            "series_ticker": ticker,
            "with_nested_markets": "true",
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor
        data = get_json(f"{BASE}/events", params=params)
        events.extend(data.get("events") or [])
        cursor = data.get("cursor")
        if not cursor:
            break
        time.sleep(0.6)
    return events


def load_series_list():
    payload = json.loads(SERIES_INDEX.read_text())
    return [s.get("ticker") for s in payload]


def iterate_new_series(series):
    remaining = []
    for ticker in series:
        out = SERIES_DIR / f"{ticker}.json"
        if out.exists():
            continue
        remaining.append(ticker)
    return remaining


def main():
    all_series = load_series_list()
    pending = iterate_new_series(all_series)
    print(f"series total: {len(all_series)}, already saved: "
          f"{len(all_series) - len(pending)}, pending: {len(pending)}", flush=True)

    ok, failed = 0, []
    for i, ticker in enumerate(pending, 1):
        try:
            evs = fetch_series(ticker)
        except Exception as exc:  # noqa: BLE001
            failed.append({"series_ticker": ticker, "error": str(exc)})
            print(f"[{i}/{len(pending)}] FAIL {ticker}: {exc}", flush=True)
            time.sleep(5)
            continue
        (SERIES_DIR / f"{ticker}.json").write_text(
            json.dumps({"series_ticker": ticker, "events": evs})
        )
        ok += 1
        print(
            f"[{i}/{len(pending)}] OK {ticker}: {len(evs)} events "
            f"({ok} done, {len(failed)} failed so far)",
            flush=True,
        )
        time.sleep(0.5)

    print("\n==== RUN SUMMARY ====", flush=True)
    print(f"fetched now : {ok}", flush=True)
    print(f"still failed: {len(failed)}", flush=True)
    for f in failed:
        print(" ", f, flush=True)


if __name__ == "__main__":
    main()