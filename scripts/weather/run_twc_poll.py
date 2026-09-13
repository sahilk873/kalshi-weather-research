"""Run the public TWC/Kalshi portal collector on a bounded cadence.

The runner keeps the collector's immutable raw snapshots and receipt clocks
intact.  ``--iterations`` makes a prospective capture reproducible in cron or
tests; zero continues until interrupted.  This is source evidence only and
never backfills an earlier decision clock.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from collect_twc_kalshi import TARGET_STATIONS, collect


def _week_start(day: date) -> str:
    return (day - timedelta(days=day.weekday())).isoformat()


def run(output: Path, *, week_start: str | None = None, climate_date: str | None = None,
        stations: list[str] | None = None, interval_seconds: int = 3600,
        iterations: int = 1, today: Callable[[], date] = date.today,
        sleep=time.sleep) -> list[tuple[int, int]]:
    if interval_seconds <= 0 or iterations < 0:
        raise ValueError("interval must be positive; iterations cannot be negative")
    selected = set(sorted(TARGET_STATIONS) if stations is None else stations)
    if not selected:
        raise ValueError("at least one target station is required")
    results: list[tuple[int, int]] = []
    count = 0
    while iterations == 0 or count < iterations:
        day = today()
        results.append(collect(output, week_start or _week_start(day), climate_date or day.isoformat(), selected))
        count += 1
        if iterations == 0 or count < iterations:
            sleep(interval_seconds)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week-start")
    parser.add_argument("--date", dest="climate_date")
    parser.add_argument("--stations", nargs="*", default=sorted(TARGET_STATIONS))
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument("--iterations", type=int, default=1,
                        help="number of pulls; 0 runs continuously")
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/twc_kalshi"))
    args = parser.parse_args()
    for result in run(args.output, week_start=args.week_start, climate_date=args.climate_date,
                      stations=args.stations, interval_seconds=args.interval_seconds,
                      iterations=args.iterations):
        print(json.dumps({"hourly_rows": result[0], "daily_rows": result[1]}, sort_keys=True))


if __name__ == "__main__":
    main()
