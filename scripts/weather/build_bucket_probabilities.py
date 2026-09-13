"""Derive coherent Kalshi bucket probabilities from supplied continuous forecasts.

This is a research transform, not a trading signal or order-placement tool.
Its input is a point-in-time distribution table produced by a forecast model;
the script rejects rows not received by their declared decision time.

Required forecast CSV fields:
``event_ticker,decision_time_utc,mean_f,stddev_f,forecast_issue_time,source_receipt_time``.
Optional ``model_name`` and ``model_version`` values are carried into output.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

from common import ensure_runtime_dirs, utc_iso  # noqa: E402
from pit import available_asof  # noqa: E402
from settlement_semantics import (bucket_from_market, normal_bucket_probabilities,
                                  settlement_standard_time_window)  # noqa: E402

REQUIRED_FORECAST_COLUMNS = {
    "event_ticker", "decision_time_utc", "mean_f", "stddev_f",
    "forecast_issue_time", "source_receipt_time",
}
OUTPUT_COLUMNS = [
    "event_ticker", "market_ticker", "city", "temp_type", "outcome_local_date",
    "decision_time_utc", "target_standard_time_window_start_utc",
    "target_standard_time_window_end_utc", "forecast_issue_time",
    "source_receipt_time", "model_name", "model_version", "mean_f", "stddev_f",
    "bucket_floor_f", "bucket_ceil_f", "bucket_probability",
]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def build_rows(markets: list[dict], forecasts: list[dict]) -> list[dict]:
    if not forecasts:
        return []
    missing = REQUIRED_FORECAST_COLUMNS - set(forecasts[0])
    if missing:
        raise ValueError(f"forecast input missing required columns: {sorted(missing)}")
    by_event: dict[str, list[dict]] = defaultdict(list)
    for market in markets:
        if market.get("event_ticker"):
            by_event[market["event_ticker"]].append(market)
    output = []
    for forecast in forecasts:
        if not available_asof(
            forecast, forecast["decision_time_utc"],
            issue_fields=("forecast_issue_time",), receipt_fields=("source_receipt_time",),
        ):
            raise ValueError(
                f"{forecast['event_ticker']}: forecast issue/receipt time is after decision time"
            )
        event_markets = by_event.get(forecast["event_ticker"], [])
        if not event_markets:
            raise ValueError(f"unknown event_ticker {forecast['event_ticker']!r}")
        city = event_markets[0].get("city", "")
        outcome_date = event_markets[0].get("outcome_local_date", "")
        if not city or not outcome_date:
            raise ValueError(f"{forecast['event_ticker']}: missing city or outcome_local_date")
        if any(m.get("city") != city or m.get("outcome_local_date") != outcome_date
               for m in event_markets):
            raise ValueError(f"{forecast['event_ticker']}: inconsistent event metadata")
        for market in event_markets:
            if market.get("temp_type", "") not in ("high", "low"):
                raise ValueError(
                    f"{forecast['event_ticker']}: temp_type must be 'high' or 'low', "
                    f"got {market.get('temp_type')!r}"
                )
        probabilities = normal_bucket_probabilities(
            [bucket_from_market(m) for m in event_markets],
            mean_f=float(forecast["mean_f"]), stddev_f=float(forecast["stddev_f"]),
        )
        window = settlement_standard_time_window(city, outcome_date)
        for market in event_markets:
            output.append({
                "event_ticker": forecast["event_ticker"],
                "market_ticker": market["market_ticker"], "city": city,
                "temp_type": market.get("temp_type", ""),
                "outcome_local_date": outcome_date,
                "decision_time_utc": forecast["decision_time_utc"],
                "target_standard_time_window_start_utc": utc_iso(window.start_utc),
                "target_standard_time_window_end_utc": utc_iso(window.end_utc),
                "forecast_issue_time": forecast["forecast_issue_time"],
                "source_receipt_time": forecast["source_receipt_time"],
                "model_name": forecast.get("model_name", ""),
                "model_version": forecast.get("model_version", ""),
                "mean_f": forecast["mean_f"], "stddev_f": forecast["stddev_f"],
                "bucket_floor_f": market.get("bucket_floor_f", ""),
                "bucket_ceil_f": market.get("bucket_ceil_f", ""),
                "bucket_probability": f"{probabilities[market['market_ticker']]:.12f}",
            })
    return output


def render(markets_path: Path, forecasts_path: Path, output_path: Path) -> int:
    """Read normalized market/forecast CSVs and write the bucket-probability CSV."""
    rows = build_rows(read_csv(markets_path), read_csv(forecasts_path))
    with output_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    dirs = ensure_runtime_dirs()
    parser.add_argument("--markets", type=Path, default=dirs["kalshi_out"] / "markets.csv")
    parser.add_argument("--forecasts", type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        default=dirs["research"] / "bucket_probabilities.csv")
    args = parser.parse_args()
    written = render(args.markets, args.forecasts, args.output)
    print(f"wrote {written} coherent bucket probability rows to {args.output}")


if __name__ == "__main__":
    main()
