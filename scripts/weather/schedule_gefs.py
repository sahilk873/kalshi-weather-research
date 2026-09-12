"""Run the GEFS collector on a bounded repeating interval."""
from __future__ import annotations
import argparse
import time
from gefs_ensemble import CITY_LOCATIONS, collect, MODELS


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval-minutes", type=float, default=60)
    ap.add_argument("--cities", nargs="+", choices=sorted(CITY_LOCATIONS), default=list(CITY_LOCATIONS))
    ap.add_argument("--models", nargs="+", choices=MODELS, default=["ncep_gefs025"])
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    while True:
        collect(args.cities, args.models)
        if args.once:
            return
        time.sleep(max(args.interval_minutes, 1) * 60)


if __name__ == "__main__": main()
