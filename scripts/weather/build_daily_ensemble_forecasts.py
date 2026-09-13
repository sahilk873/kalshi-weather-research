"""Aggregate member-level hourly guidance into point-in-time daily forecasts.

The report requires the daily maximum to be computed inside each ensemble
member before estimating a distribution.  This module does that explicitly
for the auxiliary NYC/Los Angeles/Austin layer.  It uses a fixed local
standard-time offset (not the daylight-saving offset) and carries both the
forecast issue and source-receipt timestamps into the output.

The generated ``event_ticker`` values are research target identifiers, not
Kalshi contract identifiers.  A separate event/market metadata join is needed
before producing Kalshi bucket probabilities.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from city_focus import CITIES  # noqa: E402

CITY_ALIASES = {"nyc": "nyc", "new_york": "nyc", "la": "la", "los_angeles": "la", "los angeles": "la", "austin": "austin"}

OUTPUT_COLUMNS = [
    "event_ticker", "decision_time_utc", "forecast_issue_time",
    "source_receipt_time", "model_name", "model_version", "city",
    "temp_type", "outcome_local_date", "lead_hours", "mean_f", "stddev_f",
    "member_count",
]


def _utc(value: object) -> datetime:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"invalid UTC timestamp: {value!r}")
    return parsed.to_pydatetime()


def _standard_window(city_key: str, target: date) -> tuple[datetime, datetime]:
    city = CITIES[city_key]
    zone = ZoneInfo(city.timezone)
    # January is unambiguously standard time for all three focus cities.
    standard_offset = datetime(target.year, 1, 1, tzinfo=zone).utcoffset()
    if standard_offset is None:
        raise ValueError(f"timezone has no UTC offset: {city.timezone}")
    fixed = timezone(standard_offset)
    start = datetime.combine(target, time.min, tzinfo=fixed).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def _daily_member_extrema(members: pd.DataFrame, temp_type: str) -> pd.DataFrame:
    """Return one row per member and standard-time target date."""
    if temp_type not in {"high", "low"}:
        raise ValueError("temp_type must be 'high' or 'low'")
    required = {
        "forecast_run_time", "valid_time", "city_key", "model", "member_id",
        "variable", "value", "retrieved_at",
    }
    missing = required - set(members.columns)
    if missing:
        raise ValueError(f"member input missing required columns: {sorted(missing)}")
    frame = members.copy()
    frame = frame[frame["variable"].eq("temperature_2m")].copy()
    frame["forecast_run_time"] = pd.to_datetime(frame["forecast_run_time"], utc=True, errors="coerce")
    frame["valid_time"] = pd.to_datetime(frame["valid_time"], utc=True, errors="coerce")
    frame["retrieved_at"] = pd.to_datetime(frame["retrieved_at"], utc=True, errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["forecast_run_time", "valid_time", "retrieved_at", "value"])
    if frame.empty:
        return pd.DataFrame(columns=["city_key", "model", "forecast_run_time", "retrieved_at", "member_id", "outcome_local_date", "temp_type", "member_extreme_f"])
    records: list[dict] = []
    for key, group in frame.groupby(["city_key", "model", "forecast_run_time", "retrieved_at", "member_id"], sort=False):
        raw_city_key, model, run, receipt, member = key
        city_key = CITY_ALIASES.get(str(raw_city_key).strip().lower(), "")
        if city_key not in CITIES:
            continue
        # A standard-time window can end after midnight UTC.  Include both
        # neighboring UTC dates so an early-UTC observation is not silently
        # dropped from the preceding local-standard calendar day.
        candidate_dates = set()
        for value in group["valid_time"]:
            utc_date = value.date()
            candidate_dates.update((utc_date - timedelta(days=1), utc_date, utc_date + timedelta(days=1)))
        for target in sorted(candidate_dates):
            start, end = _standard_window(city_key, target)
            selected = group[(group["valid_time"] >= start) & (group["valid_time"] < end)]
            if selected.empty:
                continue
            records.append({
                "city_key": city_key, "model": model,
                "forecast_run_time": run, "retrieved_at": receipt,
                "member_id": member, "outcome_local_date": target.isoformat(),
                "temp_type": temp_type,
                "member_extreme_f": float(selected["value"].max() if temp_type == "high" else selected["value"].min()),
            })
    return pd.DataFrame.from_records(records)


def daily_member_maxima(members: pd.DataFrame) -> pd.DataFrame:
    """Return member-level daily highs in fixed local-standard time."""
    return _daily_member_extrema(members, "high")


def daily_member_minima(members: pd.DataFrame) -> pd.DataFrame:
    """Return member-level daily lows in fixed local-standard time."""
    return _daily_member_extrema(members, "low")


def summarize_member_maxima(maxima: pd.DataFrame) -> list[dict]:
    required = {"city_key", "model", "forecast_run_time", "retrieved_at", "outcome_local_date", "temp_type", "member_extreme_f"}
    missing = required - set(maxima.columns)
    if missing:
        raise ValueError(f"maxima input missing required columns: {sorted(missing)}")
    output: list[dict] = []
    group_fields = ["city_key", "model", "forecast_run_time", "retrieved_at", "outcome_local_date", "temp_type"]
    for key, group in maxima.groupby(group_fields, sort=True):
        city_key, model, issue, receipt, target_text, temp_type = key
        issue_dt, receipt_dt = _utc(issue), _utc(receipt)
        if receipt_dt < issue_dt:
            raise ValueError(f"source receipt precedes issue for {city_key} {target_text}")
        values = pd.to_numeric(group["member_extreme_f"], errors="coerce").dropna()
        if values.empty:
            continue
        target = date.fromisoformat(str(target_text))
        start, _ = _standard_window(city_key, target)
        # A forecast issued after the settlement window has started is not a
        # forward-looking daily forecast.  Drop it rather than emitting a
        # negative lead that could be mistaken for an eligible prediction.
        if start <= receipt_dt:
            continue
        sigma = float(values.std(ddof=0)) if len(values) > 1 else None
        output.append({
            "event_ticker": f"research_{city_key}_{target.isoformat()}",
            "decision_time_utc": receipt_dt.isoformat().replace("+00:00", "Z"),
            "forecast_issue_time": issue_dt.isoformat().replace("+00:00", "Z"),
            "source_receipt_time": receipt_dt.isoformat().replace("+00:00", "Z"),
            "model_name": str(model), "model_version": str(model), "city": city_key,
            "temp_type": temp_type, "outcome_local_date": target.isoformat(),
            "lead_hours": f"{(start - issue_dt).total_seconds() / 3600:g}",
            "mean_f": f"{float(values.mean()):.6f}",
            "stddev_f": "" if sigma is None or sigma <= 0 else f"{sigma:.6f}",
            "member_count": str(len(values)),
        })
    return output


def build(input_path: Path, output_path: Path) -> int:
    members = pd.read_parquet(input_path) if input_path.suffix.lower() == ".parquet" else pd.read_csv(input_path)
    maxima = daily_member_maxima(members)
    minima = daily_member_minima(members)
    rows = summarize_member_maxima(pd.concat([maxima, minima], ignore_index=True))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--members", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"wrote {build(args.members, args.output)} daily ensemble forecasts to {args.output}")


if __name__ == "__main__":
    main()
