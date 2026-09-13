"""Run the AWC METAR collector on a bounded or continuous cadence.

The runner intentionally delegates persistence and hashing to
``collect_awc_metar``.  ``--iterations`` makes scheduled jobs reproducible in
tests and cron; zero means continue until interrupted.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from collect_awc_metar import collect


def run(ids: list[str], output: Path, hours: int = 2, interval_seconds: int = 60,
        iterations: int = 1, sleep=time.sleep) -> list[dict]:
    if not ids:
        raise ValueError("at least one station id is required")
    if hours <= 0 or interval_seconds <= 0 or iterations < 0:
        raise ValueError("hours and interval must be positive; iterations cannot be negative")
    results: list[dict] = []
    count = 0
    while iterations == 0 or count < iterations:
        results.append(collect(ids, output, hours))
        count += 1
        if iterations == 0 or count < iterations:
            sleep(interval_seconds)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="+", default=["KNYC", "KLAX", "KAUS"])
    parser.add_argument("--hours", type=int, default=2)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--iterations", type=int, default=1,
                        help="number of pulls; 0 runs continuously")
    parser.add_argument("--output", type=Path, default=Path("data/weather_research/awc"))
    args = parser.parse_args()
    for result in run(args.ids, args.output, args.hours, args.interval_seconds, args.iterations):
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
