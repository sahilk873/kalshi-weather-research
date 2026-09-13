"""Orchestrated bounded sample run of the Phoenix/Las Vegas data foundation.

Runs the pipeline in dependency order with caching everywhere:

    1. ghcn_daily        official GHCN-Daily label history (full, cached)
    2. iem_asos          trailing-30-day raw METAR + parsed fields + remarks
    3. solar             NOAA solar geometry over the METAR window
    4. nearby_stations   GHCN + IEM station inventories within 75 km
    5. collect_nearby_asos bounded nearby ASOS raw archives
    6. parse_nearby_asos nearby ASOS METAR normalization (stdlib, cached)
    7. build_intraday_state  point-in-time derived state, offline
    8. kalshi_meta       Kalshi events/markets metadata for the 4 series
    9. kalshi_trades_candles   bounded candle + public trade snapshots
   10. load_sqlite       recreate the portable SQLite query layer, offline
   11. validate          schema checks, cross-source agreement,
                         settlement backtest, anti-lookahead join, report

Incremental: every script caches raw downloads and only refetches what it
needs; rerunning this is cheap and safe.

Usage:
    python3 scripts/weather/run_sample.py
    python3 scripts/weather/run_sample.py --skip iem_asos kalshi_trades_candles
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

STEPS = [
    ("ghcn_daily", ["ghcn_daily.py"]),
    ("iem_asos", ["iem_asos.py", "--days", "30"]),
    ("solar", ["solar.py", "--start", None, "--end", None]),
    ("nearby_stations", ["nearby_stations.py"]),
    ("collect_nearby_asos", ["collect_nearby_asos.py", "--days", "30"]),
    ("parse_nearby_asos", ["parse_nearby_asos.py"]),
    ("build_intraday_state", ["build_intraday_state.py"]),
    ("kalshi_meta", ["kalshi_meta.py"]),
    ("kalshi_trades_candles", ["kalshi_trades_candles.py",
                               "--max-events-per-series", "2"]),
    ("load_sqlite", ["load_sqlite.py"]),
    ("validate", ["validate.py"]),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip", nargs="*", default=[],
                    help="step names to skip")
    args = ap.parse_args()

    today = datetime.now(timezone.utc).date()
    solar_start = (today - timedelta(days=45)).isoformat()
    solar_end = today.isoformat()

    steps = [(name, cmd) for name, cmd in STEPS if name not in args.skip]
    failed = []
    for name, cmd in steps:
        resolved = [str(SCRIPTS / c) if isinstance(c, str) and c.endswith(".py") else c
                    for c in cmd]
        resolved = [solar_start if s is None and name == "solar"
                    and cmd[1] == "--start" else s
                    for s in resolved]
        # solar args are positional after --start/--end placeholders
        if name == "solar":
            resolved = [str(SCRIPTS / "solar.py"), "--start",
                        solar_start, "--end", solar_end]
        print(f"\n=== STEP: {name} ===", flush=True)
        proc = subprocess.run([sys.executable] + resolved,
                              cwd=str(ROOT))
        if proc.returncode != 0:
            failed.append(name)
            print(f"### STEP {name} FAILED (rc={proc.returncode})",
                  file=sys.stderr, flush=True)

    print("\n==== RUN SUMMARY ====")
    done = [n for n, _ in steps if n not in failed]
    print("completed:", ", ".join(done))
    if failed:
        print("failed   :", ", ".join(failed))
        return 1
    print("all steps OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
