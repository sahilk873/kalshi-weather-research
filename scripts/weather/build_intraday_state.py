"""Build leakage-safe PHX/LV intraday state from timestamped ASOS records.

Each output row uses the observation at `valid_utc` and observations at or
before it only. Final daily labels are deliberately not read. Run after
iem_asos.py and solar.py.

Guarantees enforced here:
- Rows are processed strictly in `valid_utc` order per station/local date.
- Duplicate (station, valid_utc) observations from IEM are collapsed to the
  first occurrence so running values are consistent.
- Running extremes, deltas and solar clocks only use records at or before the
  current observation; `feature_asof_utc` equals the row's own `valid_utc`.
"""
from __future__ import annotations
import bisect, csv, sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from common import ensure_runtime_dirs, parse_utc_iso, to_float, utcnow  # noqa: E402
from stations import CITIES  # noqa: E402

COLS = [
    "station", "city", "valid_utc", "local_date",
    "current_temperature_f", "current_dew_point_f",
    "observed_high_so_far_f", "observed_low_so_far_f",
    "best_estimated_official_high_so_far_f", "best_estimated_official_low_so_far_f",
    "minutes_since_daily_high", "minutes_since_daily_low",
    "temperature_change_5m_f", "temperature_change_15m_f",
    "temperature_change_30m_f", "temperature_change_60m_f",
    "recent_temperature_acceleration_f_per_min2",
    "dewpoint_change_60m_f", "wind_speed_change_60m_kt",
    "wind_direction_change_60_deg", "cloud_change_60m",
    "minutes_since_sunrise", "minutes_until_sunset",
    "local_hour", "day_of_year", "feature_asof_utc",
]


def prior_value(rows, times, at, minutes, field):
    """Value of `field` from the last observation at-or-before `at - minutes`.

    Returns None when no such observation exists. Works for both numeric and
    string fields (cloud coverage), keeping the caller's leakage behaviour:
    only already-observed rows participate.
    """
    target = at - timedelta(minutes=minutes)
    i = bisect.bisect_right(times, target) - 1
    if i < 0:
        return None
    row = rows[i]
    v = row.get(field)
    if v in ("", None):
        return None
    f = to_float(v)
    return f if f is not None else v


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parsed", type=Path)
    parser.add_argument("--solar", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    dirs = ensure_runtime_dirs()
    parsed_path = args.parsed or (dirs["iem_out"] / "asos_parsed.csv")
    solar_path = args.solar or (dirs["solar_out"] / "solar_features.csv")

    solar = {}
    with solar_path.open() as fh:
        for r in csv.DictReader(fh):
            solar[(r["city"], r["date"])] = r

    raw = list(csv.DictReader(parsed_path.open()))
    by: dict[tuple[str, str], list[dict]] = {}
    for r in raw:
        city = ("phx" if r["station"] == "PHX"
                else "lv" if r["station"] == "LAS" else "")
        if not city:
            continue
        by.setdefault((city, r["local_date"]), []).append(r)

    out = []
    for (city, day), rows in sorted(by.items()):
        rows.sort(key=lambda r: r["valid_utc"])
        # Collapse IEM duplicate timestamps so `times`/`rows` stay aligned.
        deduped: list[dict] = []
        for r in rows:
            if deduped and deduped[-1]["valid_utc"] == r["valid_utc"]:
                continue
            deduped.append(r)
        rows = deduped
        times = [parse_utc_iso(r["valid_utc"]) for r in rows]
        tz = ZoneInfo(CITIES[city].tz_name)
        s = solar.get((city, day), {})
        sunrise = parse_utc_iso(s["sunrise_utc"]) if s.get("sunrise_utc") else None
        sunset = parse_utc_iso(s["sunset_utc"]) if s.get("sunset_utc") else None

        highs = []  # (temp_f, at) tuples already observed this local date
        lows = []
        for i, r in enumerate(rows):
            at = times[i]
            temp = to_float(r["tmpf"])
            dew = to_float(r["dwpf"])
            if temp is not None:
                highs.append((temp, at))
                lows.append((temp, at))
            hi = max(highs, key=lambda x: x[0]) if highs else (None, None)
            lo = min(lows, key=lambda x: x[0]) if lows else (None, None)

            def change(field, minutes):
                old = prior_value(rows, times, at, minutes, field)
                cur = to_float(r.get(field))
                return round(cur - old, 3) if cur is not None and old is not None else None

            c30 = change("tmpf", 30)
            c60 = change("tmpf", 60)
            prev_cloud = prior_value(rows, times, at, 60, "skyc1")
            cur_cloud = (r.get("skyc1") or "").strip()
            cloud_changed = (int(cur_cloud != prev_cloud)
                             if prev_cloud is not None else None)
            local = at.astimezone(tz)
            out.append({
                "station": r["station"], "city": city,
                "valid_utc": r["valid_utc"], "local_date": day,
                "current_temperature_f": temp,
                "current_dew_point_f": dew,
                "observed_high_so_far_f": hi[0],
                "observed_low_so_far_f": lo[0],
                "best_estimated_official_high_so_far_f": hi[0],
                "best_estimated_official_low_so_far_f": lo[0],
                "minutes_since_daily_high":
                    round((at - hi[1]).total_seconds() / 60, 2) if hi[1] else None,
                "minutes_since_daily_low":
                    round((at - lo[1]).total_seconds() / 60, 2) if lo[1] else None,
                "temperature_change_5m_f": change("tmpf", 5),
                "temperature_change_15m_f": change("tmpf", 15),
                "temperature_change_30m_f": c30,
                "temperature_change_60m_f": c60,
                "recent_temperature_acceleration_f_per_min2":
                    round((c30 - c60) / 30, 5) if c30 is not None and c60 is not None else None,
                "dewpoint_change_60m_f": change("dwpf", 60),
                "wind_speed_change_60m_kt": change("sknt", 60),
                "wind_direction_change_60_deg": change("drct", 60),
                "cloud_change_60m": cloud_changed,
                "minutes_since_sunrise":
                    round((at - sunrise).total_seconds() / 60, 2) if sunrise else None,
                "minutes_until_sunset":
                    round((sunset - at).total_seconds() / 60, 2) if sunset else None,
                "local_hour": local.hour,
                "day_of_year": local.timetuple().tm_yday,
                "feature_asof_utc": r["valid_utc"],
            })

    dest = args.output or (dirs["research"] / "derived_intraday_state.csv")
    with dest.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(out)
    print(f"wrote {dest} ({len(out)} as-of rows); fetched_at={utcnow()}")


if __name__ == "__main__":
    main()
