#!/usr/bin/env python3
"""Retry failed weather series and merge with the existing pull.

Loads data/kalshi_weather_raw.json, refetches any failed series, merges the
results, and rewrites all output files with a corrected summary.
"""

import json
import time
from pathlib import Path

import requests

BASE = "https://external-api.kalshi.com/trade-api/v2"
OUT_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_PATH = OUT_DIR / "kalshi_weather_raw.json"

UA = {"User-Agent": "kalshi-weather-pull/1.0 (retry)"}
SESSION = requests.Session()
SESSION.headers.update(UA)


def get_json(url, params=None):
    for attempt in range(6):
        try:
            resp = SESSION.get(url, params=params, timeout=90)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code >= 500:
                time.sleep(3 * (attempt + 1))
                continue
            resp.raise_for_status()
        except requests.RequestException:
            if attempt == 5:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"failed after retries: {url}")


def fetch_series(series_ticker):
    events, cursor = [], None
    while True:
        params = {
            "series_ticker": series_ticker,
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
        time.sleep(0.5)
    return events


def dedup(items, keyfn):
    seen, out = set(), []
    for it in items:
        key = keyfn(it)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def main():
    payload = json.loads(RAW_PATH.read_text())

    pending = {f["series_ticker"] for f in payload["failures"]}
    print("retrying series:", sorted(pending))

    new_events, new_markets = [], []
    still_failing = []
    for ticker in sorted(pending):
        try:
            evs = fetch_series(ticker)
        except Exception as exc:  # noqa: BLE001
            still_failing.append({"series_ticker": ticker, "error": str(exc)})
            print(f"  FAIL {ticker}: {exc}")
            continue
        new_events.extend(evs)
        for ev in evs:
            new_markets.extend(ev.get("markets") or [])
        print(f"  OK {ticker}: {len(evs)} events")
        time.sleep(0.5)

    def ev_key(e):
        return e.get("event_ticker") or e.get("ticker") or e.get("id")

    def mk_key(m):
        return m.get("ticker") or m.get("id")

    all_events = dedup(payload["events"] + new_events, ev_key)
    all_markets = dedup(payload["markets"] + new_markets, mk_key)

    payload["events"] = all_events
    payload["markets"] = all_markets
    payload["num_events"] = len(all_events)
    payload["num_markets"] = len(all_markets)
    payload["failures"] = still_failing
    payload["num_series_failed"] = len(still_failing)
    payload["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    RAW_PATH.write_text(json.dumps(payload, indent=2))
    (OUT_DIR / "kalshi_weather_events.json").write_text(
        json.dumps(all_events, indent=2)
    )
    (OUT_DIR / "kalshi_weather_markets.json").write_text(
        json.dumps(all_markets, indent=2)
    )

    print("\n==== SUMMARY ====")
    print(f"events  : {len(all_events)}")
    print(f"markets : {len(all_markets)}")
    print(f"failures: {still_failing or 'none'}")


if __name__ == "__main__":
    main()