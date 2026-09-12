#!/usr/bin/env python3
"""Merge per-series files in data/series/ into the combined weather outputs.

Reads every data/series/<TICKER>.json (each holds {"series_ticker", "events"}
where events include nested markets), dedupes, and writes:
- data/kalshi_weather_series.json
- data/kalshi_weather_events.json
- data/kalshi_weather_markets.json
- data/kalshi_weather_markets.csv
- data/kalshi_weather_raw.json  (combined payload)

Usage: python3 scripts/merge_weather_outputs.py
"""

import csv
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERIES_DIR = ROOT / "data" / "series"
OUT = ROOT / "data"


def main():
    files = sorted(SERIES_DIR.glob("*.json"))
    series, events, markets, failures = [], [], [], []

    def ev_key(e):
        return e.get("event_ticker") or e.get("ticker") or e.get("id")

    def mk_key(m):
        return m.get("ticker") or m.get("id")

    seen_ev, seen_mk, seen_sr = set(), set(), set()
    for f in files:
        payload = json.loads(f.read_text())
        ticker = payload.get("series_ticker") or f.stem
        if payload.get("events") is None:
            failures.append({"series_ticker": ticker, "error": "no events key"})
            continue
        if ticker not in seen_sr:
            seen_sr.add(ticker)
            series.append({"ticker": ticker})
        for ev in payload["events"]:
            key = ev_key(ev)
            if key in seen_ev:
                continue
            seen_ev.add(key)
            events.append(ev)
            for m in ev.get("markets") or []:
                mkey = mk_key(m)
                if mkey in seen_mk:
                    continue
                seen_mk.add(mkey)
                markets.append(m)

    fields = _market_fields(markets)
    csv_path = OUT / "kalshi_weather_markets.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for m in markets:
            writer.writerow({k: m.get(k, "") for k in fields})

    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "category": "Climate and Weather",
        "source": "https://external-api.kalshi.com/trade-api/v2",
        "num_series": len(series),
        "num_series_failed": len(failures),
        "num_events": len(events),
        "num_markets": len(markets),
        "failures": failures,
        "series": series,
        "events": events,
        "markets": markets,
    }
    (OUT / "kalshi_weather_raw.json").write_text(json.dumps(payload, indent=2))
    (OUT / "kalshi_weather_series.json").write_text(json.dumps(series, indent=2))
    (OUT / "kalshi_weather_events.json").write_text(json.dumps(events, indent=2))
    (OUT / "kalshi_weather_markets.json").write_text(json.dumps(markets, indent=2))

    print("==== MERGE SUMMARY ====")
    print(f"series files read: {len(files)}")
    print(f"failures          : {failures or 'none'}")
    print(f"series            : {len(series)}")
    print(f"events            : {len(events)}")
    print(f"markets           : {len(markets)}")
    print(f"csv columns       : {len(fields)}")


def _market_fields(markets):
    fields = []
    for m in markets:
        for k in m:
            if k not in fields:
                fields.append(k)
    return fields


if __name__ == "__main__":
    main()