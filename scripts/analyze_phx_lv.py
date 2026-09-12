#!/usr/bin/env python3
"""Pull Phoenix + Las Vegas daily high/low temperature markets from the
already-fetched per-series data and produce a clean analysis CSV + summary.

No hourly temperature markets exist for Phoenix or Las Vegas on Kalshi
(series list confirms this).
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data"
SERIES_DIR = ROOT / "series"

TARGET = {
    "KXHIGHTPHX": ("Phoenix", "Daily High"),
    "KXLOWTPHX":  ("Phoenix", "Daily Low"),
    "KXHIGHTLV":  ("Las Vegas", "Daily High"),
    "KXLOWTLV":   ("Las Vegas", "Daily Low"),
}

COLS = [
    "series_ticker", "city", "temp_type", "event_ticker", "event_date",
    "market_ticker", "market_title", "temperature_bucket",
    "yes_bid", "yes_ask", "no_bid", "no_ask",
    "last_price", "mid_price", "implied_probability",
    "volume_24h", "open_interest", "liquidity", "spread",
    "market_status", "close_time",
]


def parse_bucket(title, yes_sub):
    """Extract a numeric bucket description from the market title/sub."""
    if yes_sub:
        return yes_sub.strip()
    return (title or "").split("?")[0].split(" be ")[-1] if title else ""


def mid(bid, ask):
    try:
        return round((bid + ask) / 2, 2)
    except TypeError:
        return None


def row(ev, m):
    city, temp_type = TARGET.get(ev.get("series_ticker"), ("?", "?"))
    yb = float(m.get("yes_bid_dollars") or 0)
    ya = float(m.get("yes_ask_dollars") or 1)
    nb = float(m.get("no_bid_dollars") or 0)
    na = float(m.get("no_ask_dollars") or 1)
    midp = mid(yb, ya)
    lp = m.get("last_price_dollars")
    lp_f = float(lp) if lp is not None else None
    implied = None
    if lp_f is not None:
        implied = round(lp_f, 4)
    elif midp is not None:
        implied = round(midp, 4)
    strike_date = ev.get("strike_date") or ""
    event_date = strike_date[:10] if strike_date else ev.get("event_ticker", "")
    return {
        "series_ticker":      ev.get("series_ticker"),
        "city":               city,
        "temp_type":          temp_type,
        "event_ticker":       ev.get("event_ticker"),
        "event_date":         event_date,
        "market_ticker":      m.get("ticker"),
        "market_title":       m.get("title"),
        "temperature_bucket": parse_bucket(m.get("title"), m.get("yes_sub_title")),
        "yes_bid":            yb,
        "yes_ask":            ya,
        "no_bid":             nb,
        "no_ask":             na,
        "last_price":         lp_f if lp_f is not None else "",
        "mid_price":          midp if midp is not None else "",
        "implied_probability":implied if implied is not None else "",
        "volume_24h":         float(m.get("volume_24h_fp") or 0),
        "open_interest":      float(m.get("open_interest_fp") or 0),
        "liquidity":          float(m.get("liquidity_dollars") or 0),
        "spread":             round(ya - yb, 2) if ya and yb else "",
        "market_status":      m.get("status"),
        "close_time":         m.get("close_time"),
    }


def main():
    rows = []
    for ticker, (city, temp_type) in TARGET.items():
        fp = SERIES_DIR / f"{ticker}.json"
        if not fp.exists():
            print(f"missing file: {fp}")
            continue
        data = json.loads(fp.read_text())
        for ev in data.get("events") or []:
            for m in ev.get("markets") or []:
                rows.append(row(ev, m))

    out_path = ROOT / "phx_lv_daily_temp_markets.csv"
    with out_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} rows -> {out_path}")

    active = [r for r in rows if r["market_status"] in ("active", "initialized")]
    print(f"active/init rows: {len(active)}")

    # --- summary table: upcoming days, buckets with bid/ask ---
    from collections import defaultdict
    by_event = defaultdict(list)
    for r in rows:
        if r["market_status"] == "active":
            by_event[(r["series_ticker"], r["event_ticker"])].append(r)

    print("\n=== UPCOMING ACTIVE MARKETS (closest dates) ===")
    for ticker in TARGET:
        city, temp_type = TARGET[ticker]
        events = sorted(
            [(k, v) for k, v in by_event.items() if k[0] == ticker],
            key=lambda x: x[0][1]
        )[:3]
        if not events:
            print(f"\n{city} {temp_type} ({ticker}): no active events")
            continue
        print(f"\n--- {city} {temp_type} ({ticker}) ---")
        for (st, et), mkt in events:
            print(f"  Event: {et}")
            for r in sorted(mkt, key=lambda x: x["temperature_bucket"]):
                print(
                    f"    {r['temperature_bucket']:>20s}  "
                    f"yb={r['yes_bid']:.2f} ya={r['yes_ask']:.2f}  "
                    f"mid={r['mid_price']}  P={r['implied_probability']}"
                )

    print("\nNOTE: No hourly temperature markets exist for Phoenix or Las Vegas.")
    print("Hourly directional temperature series exist only for: LA, Austin, Boston, Miami, Chicago, NYC, DC.")


if __name__ == "__main__":
    main()