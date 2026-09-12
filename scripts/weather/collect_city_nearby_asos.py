"""Collect a compact nearby ASOS network for NYC, Los Angeles, and Austin.

Raw IEM CSV responses are retained by city/station/date window.  The network
is deliberately small and selected for spatial context around each market
station, rather than downloading every station in a state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
import sys

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from common import ensure_runtime_dirs, http_get_text, utcnow  # noqa: E402

BASE = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
# Settlement station first; remaining sites provide local gradients and
# airport-to-airport consistency checks.
NETWORK = {
    "nyc": ("NY_ASOS", "KNYC", ("KLGA", "KJFK", "KEWR", "KTEB", "KHPN")),
    "la": ("CA_ASOS", "KLAX", ("KHHR", "KBUR", "KVNY", "KSMO", "KLGB")),
    "austin": ("TX_ASOS", "KAUS", ("KEDC", "KGTU", "KHYI", "KATT", "KBAZ")),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cities", nargs="*", default=list(NETWORK))
    ap.add_argument("--start", help="UTC date, default: 30 days ago")
    ap.add_argument("--end", help="UTC date, default: today")
    args = ap.parse_args()
    bad = [c for c in args.cities if c not in NETWORK]
    if bad:
        raise SystemExit(f"unknown city {bad}; choose from {sorted(NETWORK)}")
    end = datetime.fromisoformat(args.end).date() if args.end else datetime.now(timezone.utc).date()
    start = datetime.fromisoformat(args.start).date() if args.start else end - timedelta(days=30)
    dirs = ensure_runtime_dirs()
    out = dirs["research"] / "city_nearby_asos" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for city in args.cities:
        network, settlement, nearby = NETWORK[city]
        for station in (settlement, *nearby):
            params = {
                "network": network, "station": station, "data": "all",
                "year1": start.year, "month1": start.month, "day1": start.day,
                "year2": end.year, "month2": end.month, "day2": end.day,
                "tz": "Etc/UTC", "format": "onlycomma", "report_type": ["3", "4"],
                "direct": "1",
            }
            dest = out / f"{city}_{station}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
            if not dest.exists() or dest.stat().st_size == 0:
                text = http_get_text(BASE + "?" + urlencode(params, doseq=True), timeout=300)
                if not text.startswith("station,valid,"):
                    raise RuntimeError(f"unexpected IEM response for {station}: {text[:100]!r}")
                dest.write_text(text)
            count += 1
    print(f"wrote/cached {count} nearby ASOS archives under {out}; fetched_at={utcnow()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
