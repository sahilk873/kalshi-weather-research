"""Capture prospective hourly market, station, and quote evidence.

The runner is read-only and records a fail-closed status when no hourly market
is open. It never turns a later receipt into historical PIT evidence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from collect_rest_orderbook import collect_rest_orderbooks
from probe_active_city_markets import probe
from run_awc_poll import run as run_awc
from run_twc_poll import run as run_twc


def capture(root: Path, *, credential_file: Path | None = None,
            iterations: int = 1, interval_seconds: int = 60) -> dict:
    probe_dir = root / "kalshi_city" / "active_probe"
    active = probe(probe_dir)
    awc = run_awc(["KNYC", "KLAX", "KAUS"], root / "awc", hours=2,
                  interval_seconds=interval_seconds, iterations=iterations)
    twc = run_twc(root / "twc_kalshi", stations=["KNYC", "KLAX", "KAUS"],
                  interval_seconds=interval_seconds, iterations=iterations)
    hourly = [ticker for ticker in active.get("open_tickers", [])
              if ticker.startswith(("KXTEMPNYCHS-", "KXTEMPNYCH-", "KXTEMPLAXHS-", "KXTEMPLAXH-", "KXTEMPAUSH-"))]
    books = None
    if hourly:
        if credential_file is None:
            return {"version": "intraday-capture-v1", "pass": False,
                    "reason": "hourly_markets_open_but_credential_file_not_supplied",
                    "hourly_tickers": hourly, "active": active,
                    "awc_pulls": len(awc), "twc_pulls": len(twc),
                    "quote_snapshot": active.get("quote_path")}
        books = collect_rest_orderbooks(hourly, credential_file=credential_file,
                                        output_dir=root / "kalshi" / "rest_orderbook")
    return {"version": "intraday-capture-v1", "pass": bool(hourly and books),
            "reason": "captured_hourly_books" if hourly else "no_hourly_markets_open",
            "hourly_tickers": hourly, "active": active, "awc_pulls": len(awc),
            "twc_pulls": len(twc), "quote_snapshot": active.get("quote_path"),
            "orderbook_manifest": books.get("manifest_path") if books else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/weather_research"))
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--credential-file", type=Path,
                        default=Path(os.environ["KALSHI_CREDENTIAL_FILE"]) if os.environ.get("KALSHI_CREDENTIAL_FILE") else None)
    parser.add_argument("--output", type=Path,
                        default=Path("data/weather_research/reports/intraday_capture_status.json"))
    args = parser.parse_args()
    result = capture(args.root, credential_file=args.credential_file,
                     iterations=args.iterations, interval_seconds=args.interval_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"hourly_open": len(result["hourly_tickers"]),
                      "pass": result["pass"], "reason": result["reason"]}))


if __name__ == "__main__":
    main()
