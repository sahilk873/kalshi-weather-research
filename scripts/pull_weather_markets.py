#!/usr/bin/env python3
"""Pull all weather-related predictions (events + markets) from the Kalshi public API.

Source of truth: https://docs.kalshi.com (trade-api/v2).
- Categories provided by GET /search/tags_by_categories: "Climate and Weather".
- Series for that category: GET /series?category=Climate%20and%20Weather
- Events + nested markets per series: GET /events?series_ticker=<T>&with_nested_markets=true
"""

import json
import time
from pathlib import Path

import requests

BASE = "https://external-api.kalshi.com/trade-api/v2"
CATEGORY = "Climate and Weather"
OUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "kalshi-weather-pull/1.0 (research)"}
SESSION = requests.Session()
SESSION.headers.update(UA)


def get_json(url, params=None):
    for attempt in range(4):
        resp = SESSION.get(url, params=params, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code >= 500:
            time.sleep(2 * (attempt + 1))
            continue
        resp.raise_for_status()
    raise RuntimeError(f"failed after retries: {url}")


def fetch_all(fetch_page):
    """Generic cursor pager. fetch_page(cursor) -> (items, next_cursor)"""
    items, cursor = [], None
    while True:
        page, cursor = fetch_page(cursor)
        items.extend(page)
        if not cursor:
            break
        time.sleep(0.25)
    return items


def main():
    series_resp = get_json(f"{BASE}/series", params={"category": CATEGORY})
    series = series_resp.get("series") or []

    seen, series_list = set(), []
    for s in series:
        if s.get("ticker") in seen:
            continue
        seen.add(s.get("ticker"))
        series_list.append(s)

    events, markets = [], []
    failures = []
    for i, s in enumerate(series_list, 1):
        ticker = s["ticker"]
        try:
            evs = fetch_all(
                lambda cursor, t=ticker: _fetch_events_page(t, cursor)
            )
        except Exception as exc:  # noqa: BLE001
            failures.append({"series_ticker": ticker, "error": str(exc)})
            print(f"[{i}/{len(series_list)}] FAIL {ticker}: {exc}")
            continue
        events.extend(evs)
        for ev in evs:
            markets.extend(ev.get("markets") or [])
        print(
            f"[{i}/{len(series_list)}] {ticker}: {len(evs)} events, "
            f"{sum(len(ev.get('markets') or []) for ev in evs)} markets"
        )
        time.sleep(0.15)

    seen_ids, dedup_markets, dedup_events = set(), [], []
    for m in markets:
        key = m.get("ticker") or m.get("id")
        if key in seen_ids:
            continue
        seen_ids.add(key)
        dedup_markets.append(m)
    seen_ids = set()
    for ev in events:
        key = ev.get("event_ticker") or ev.get("ticker") or ev.get("id")
        if key in seen_ids:
            continue
        seen_ids.add(key)
        dedup_events.append(ev)

    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "category": CATEGORY,
        "source": f"{BASE}",
        "num_series": len(series_list),
        "num_series_failed": len(failures),
        "num_events": len(dedup_events),
        "num_markets": len(dedup_markets),
        "failures": failures,
        "series": series_list,
        "events": dedup_events,
        "markets": dedup_markets,
    }

    raw_path = OUT_DIR / "kalshi_weather_raw.json"
    raw_path.write_text(json.dumps(payload, indent=2))
    (OUT_DIR / "kalshi_weather_series.json").write_text(
        json.dumps(series_list, indent=2)
    )
    (OUT_DIR / "kalshi_weather_events.json").write_text(
        json.dumps(dedup_events, indent=2)
    )
    (OUT_DIR / "kalshi_weather_markets.json").write_text(
        json.dumps(dedup_markets, indent=2)
    )

    print("\n==== SUMMARY ====")
    print(f"series fetched : {len(series_list)}")
    print(f"series failed  : {len(failures)}")
    print(f"events         : {len(dedup_events)}")
    print(f"markets        : {len(dedup_markets)}")
    print(f"output dir     : {OUT_DIR}")
    if failures:
        print("failures:")
        for f in failures:
            print(" ", f)


def _fetch_events_page(series_ticker, cursor):
    params = {
        "series_ticker": series_ticker,
        "with_nested_markets": "true",
        "limit": 200,
    }
    if cursor:
        params["cursor"] = cursor
    data = get_json(f"{BASE}/events", params=params)
    events = data.get("events") or []
    next_cursor = data.get("cursor")
    return events, next_cursor


if __name__ == "__main__":
    main()