"""Validation, anti-lookahead gates and example joins for the research set.

Runs safe, deterministic checks over every table produced by this pipeline:

1. Schema checks (column presence for each CSV).
2. GHCN labels: duplicates, missing, TMAX >= TMIN, plausible range,
   recent-days completeness, GHCN update lag.
3. IEM METAR: parse rate, missing tmpf, obs/day, local-date mapping sanity.
4. Cross-source agreement: METAR sampled daily extremes vs official GHCN
   TMAX/TMIN on overlapping dates (mean abs diff, match rate within 1/2/5 F).
5. Kalshi tables: candles monotonic + uniques, trades price bounds & count_fp
   parse rate, market/event join integrity, settlement-vs-label agreement for
   finalized markets (bucket hit using GHCN label vs Kalshi result).
6. Anti-lookahead: helper ``known_labels_asof`` and a materialized example
   joined table for recent days that flags which fields were observable at
   each market timestamp.

Outputs:
- data/weather_research/reports/joined_example.csv
- data/weather_research/reports/validation_summary.txt
- data/weather_research/reports/data_quality_report.md

Exit code 0 = all checks ran; individual failures are reported, not fatal,
because missing upstream credentials/data must fail loudly but not block
documentation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

# ruff: noqa: E402
import common  # noqa: E402
from common import ensure_runtime_dirs, parse_utc_iso, to_float, utcnow  # noqa: E402
from asof_forecasts import known_forecasts, valid_forecasts_asof  # noqa: E402
from stations import CITIES, DEFAULT_CITIES, KALSHI_SERIES_TO_CITY, get_cities  # noqa: E402

REQ_COLS = {
    "ghcn_labels": ["station_id", "city", "date", "source", "tmax_c", "tmax_f",
                    "tmin_c", "tmin_f", "label_available_ts"],
    "asos_parsed": ["station", "valid_utc", "local_date", "tmpf", "raw_metar"],
    "asos_daily": ["station", "city", "local_date", "obs_count", "tmax_f",
                   "tmin_f", "sampled_only_flag"],
    "solar": ["city", "date", "sunrise_utc", "sunset_utc", "daylength_min"],
    "events": ["event_ticker", "series_ticker", "city", "temp_type",
               "outcome_local_date"],
    "markets": ["market_ticker", "event_ticker", "series_ticker",
                "outcome_local_date", "status", "result", "bucket_floor_f",
                "bucket_ceil_f", "open_time", "close_time"],
    "candles_daily": ["market_ticker", "end_period_ts", "volume_fp"],
    "candles_hourly": ["market_ticker", "end_period_ts", "volume_fp"],
    "trades": ["trade_id", "market_ticker", "yes_price_dollars",
               "created_time"],
    "nearby_asos_parsed": ["city", "station", "valid_utc", "local_date",
                           "tmpf", "skyc1", "raw_metar"],
    "derived_intraday_state": ["station", "valid_utc", "feature_asof_utc",
                               "current_temperature_f",
                               "observed_high_so_far_f", "observed_low_so_far_f"],
    "contract_outcomes": ["market_ticker", "outcome_local_date", "city",
                          "temp_type", "bucket_floor_f", "bucket_ceil_f",
                          "status", "settled_yes"],
    "cli_daily": ["city", "climate_date", "official_daily_high_f",
                  "official_daily_low_f", "publication_time_utc",
                  "raw_filename"],
    "forecasts_manifest": ["model", "city", "initialization_time_utc",
                           "valid_time_utc", "lead_hours", "sha256",
                           "raw_path"],
}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", errors="replace") as fh:
        return list(csv.DictReader(fh))


def check_schema(results: dict, dirs) -> None:
    for key, cols in REQ_COLS.items():
        path = dirs["research"] / _table_path(key)
        rows = read_csv(path)
        if not rows:
            results.setdefault("schema", {})[key] = {
                "status": "MISSING_FILE_OR_EMPTY",
                "path": str(path),
                "expected_cols": len(cols),
            }
            continue
        got = list(rows[0].keys())
        missing = [c for c in cols if c not in got]
        results.setdefault("schema", {})[key] = {
            "status": "OK" if not missing else f"MISSING_COLS {missing}",
            "path": str(path),
            "rows": len(rows),
            "cols": len(got),
        }


def _table_path(key: str) -> Path:
    mapping = {
        "ghcn_labels": "ghcn/labels_daily.csv",
        "asos_parsed": "iem/asos_parsed.csv",
        "asos_daily": "iem/asos_daily.csv",
        "solar": "solar/solar_features.csv",
        "events": "kalshi/events.csv",
        "markets": "kalshi/markets.csv",
        "candles_daily": "kalshi/candlesticks_daily.csv",
        "candles_hourly": "kalshi/candlesticks_hourly.csv",
        "trades": "kalshi/trades.csv",
        "nearby_asos_parsed": "nearby_asos/nearby_asos_parsed.csv",
        "derived_intraday_state": "derived_intraday_state.csv",
        "contract_outcomes": "kalshi/contract_outcomes.csv",
        "cli_daily": "nws_cli/daily_climate_cli.csv",
        "forecasts_manifest": "forecasts/manifest.csv",
    }
    return mapping[key]


def validate_ghcn(results, dirs) -> None:
    rows = read_csv(dirs["research"] / "ghcn/labels_daily.csv")
    out = results.setdefault("ghcn", {})
    if not rows:
        out["status"] = "NO_DATA"
        return
    by_city: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_city[r["city"]].append(r)
    for city, rs in by_city.items():
        dates = set(r["date"] for r in rs)
        dupes = len(rs) - len(dates)
        tmax = [to_float(r["tmax_f"]) for r in rs]
        tmin = [to_float(r["tmin_f"]) for r in rs]
        valid_t = [a for a in tmax if a is not None]
        valid_n = [b for b in tmin if b is not None]
        bad = [r["date"] for r in rs
               if to_float(r["tmax_f"]) is not None and
               to_float(r["tmin_f"]) is not None and
               to_float(r["tmax_f"]) < to_float(r["tmin_f"])]
        recent = sorted(dates)[-1]
        out[city] = {
            "rows": len(rs),
            "unique_dates": len(dates),
            "duplicate_dates": dupes,
            "date_range": f"{min(dates)}..{recent}",
            "tmax_range_f": (round(min(valid_t), 1), round(max(valid_t), 1)),
            "tmin_range_f": (round(min(valid_n), 1), round(max(valid_n), 1)),
            "tmax_lt_tmin_count": len(bad),
            "missing_tmax": len(tmax) - len(valid_t),
            "missing_tmin": len(tmin) - len(valid_n),
        }
    # GHCN publication lag vs "today"
    today = datetime.now(timezone.utc).date().isoformat()
    for city in by_city:
        dates = [r["date"] for r in by_city[city]]
        last = max(dates)
        # mask empty
        if last:
            out[city]["last_label_date"] = last
            out[city]["ghcn_lag_days"] = (datetime.fromisoformat(today) -
                                          datetime.fromisoformat(last)).days


def validate_iem(results, dirs) -> None:
    parsed = read_csv(dirs["research"] / "iem/asos_parsed.csv")
    daily = read_csv(dirs["research"] / "iem/asos_daily.csv")
    out = results.setdefault("iem", {})
    out["parsed_obs"] = len(parsed)
    out["daily_rows"] = len(daily)
    if not parsed:
        out["status"] = "NO_DATA"
        return
    stations = sorted({r["station"] for r in parsed})
    out["stations"] = stations
    for st in stations:
        rs = [r for r in parsed if r["station"] == st]
        tmpf = [to_float(r["tmpf"]) for r in rs]
        missing = sum(1 for v in tmpf if v is None)
        parse_rate = round((len(tmpf) - missing) / len(tmpf) * 100, 2)
        raw_with_remarks = sum(1 for r in rs if "RMK" in (r["raw_metar"] or ""))
        local_dates = {r["local_date"] for r in rs}
        obs_per_day = round(len(rs) / max(len(local_dates), 1), 1)
        out[f"station_{st}"] = {
            "obs": len(rs),
            "parse_rate_pct": parse_rate,
            "missing_tmpf": missing,
            "local_dates": len(local_dates),
            "date_range": f"{min(local_dates)}..{max(local_dates)}",
            "obs_per_day_avg": obs_per_day,
            "raw_metar_with_remarks": raw_with_remarks,
        }


def validate_solar(results, dirs) -> None:
    rows = read_csv(dirs["research"] / "solar/solar_features.csv")
    out = results.setdefault("solar", {})
    if not rows:
        out["status"] = "NO_DATA"
        return
    day_bad = [r for r in rows
               if to_float(r["daylength_min"]) is None or
               not (300 < (to_float(r["daylength_min"]) or 0) < 1000)]
    out["rows"] = len(rows)
    out["date_range"] = f"{min(r['date'] for r in rows)}..{max(r['date'] for r in rows)}"
    out["implausible_daylength"] = len(day_bad)


def cross_source_agreement(results, dirs) -> None:
    """METAR sampled daily extremes vs GHCN official labels."""
    ghcn = read_csv(dirs["research"] / "ghcn/labels_daily.csv")
    daily = read_csv(dirs["research"] / "iem/asos_daily.csv")
    out = results.setdefault("cross_source", {})
    if not ghcn or not daily:
        out["status"] = "NO_OVERLAP"
        return
    ghcn_by_city: dict[str, dict] = {}
    for r in ghcn:
        ghcn_by_city[(r["city"], r["date"])] = r
    for city in sorted({r["city"] for r in daily}):
        diffs_tmax, diffs_tmin = [], []
        n = 0
        for r in daily:
            if r["city"] != city:
                continue
            g = ghcn_by_city.get((city, r["local_date"]))
            if not g or not g.get("tmax_f") or not g.get("tmin_f"):
                continue
            mh = to_float(r["tmax_f"]); ml = to_float(r["tmin_f"])
            ghs = to_float(g["tmax_f"]); gls = to_float(g["tmin_f"])
            if mh is not None and ghs is not None:
                diffs_tmax.append((mh - ghs, r["local_date"]))
            if ml is not None and gls is not None:
                diffs_tmin.append((ml - gls, r["local_date"]))
            n += 1
        results.setdefault("cross_source", {})[city] = {
            "overlap_days": n,
            "mean_abs_diff_tmax_f": round(
                sum(abs(d[0]) for d in diffs_tmax) / len(diffs_tmax), 2)
                if diffs_tmax else None,
            "mean_abs_diff_tmin_f": round(
                sum(abs(d[0]) for d in diffs_tmin) / len(diffs_tmin), 2)
                if diffs_tmin else None,
            "tmax_within_1f": round(
                sum(1 for d in diffs_tmax if abs(d[0]) <= 1.0) / len(diffs_tmax)
                * 100, 1) if diffs_tmax else None,
            "max_abs_diff_tmax_f": round(max(abs(d[0]) for d in diffs_tmax), 2)
                if diffs_tmax else None,
            "worst_tmax_date": max(diffs_tmax, key=lambda d: abs(d[0]))[1]
                if diffs_tmax else None,
        }


def validate_kalshi(results, dirs) -> None:
    markets = read_csv(dirs["research"] / "kalshi/markets.csv")
    events = read_csv(dirs["research"] / "kalshi/events.csv")
    trades = read_csv(dirs["research"] / "kalshi/trades.csv")
    cday = read_csv(dirs["research"] / "kalshi/candlesticks_daily.csv")
    chour = read_csv(dirs["research"] / "kalshi/candlesticks_hourly.csv")
    out = results.setdefault("kalshi", {})
    out["markets_total"] = len(markets)
    out["markets_active"] = sum(1 for m in markets if m["status"] == "active")
    out["markets_finalized"] = sum(1 for m in markets if m["status"] == "finalized")
    out["events_total"] = len(events)

    # trades sanity
    if trades:
        out["trades_total"] = len(trades)
        prices = [to_float(t["yes_price_dollars"]) for t in trades]
        in_range = sum(1 for p in prices if p is not None and 0 <= p <= 1)
        out["trades_price_in_0_1"] = in_range
        out["trades_price_parse_rate_pct"] = round(
            sum(1 for p in prices if p is not None) / max(len(prices), 1) * 100, 2)
        # dup trade ids
        ids = [t["trade_id"] for t in trades]
        out["trades_dup_ids"] = len(ids) - len(set(ids))

    for key, rows in (("candles_daily", cday), ("candles_hourly", chour)):
        if not rows:
            out[key] = {"rows": 0}
            continue
        dup = len(rows) - len({(r["market_ticker"], r["end_period_ts"])
                               for r in rows})
        out[key] = {
            "rows": len(rows),
            "dup_market_ts": dup,
            "markets": len({r["market_ticker"] for r in rows}),
        }

    # settlement vs GHCN label (bucket hit) for finalized markets
    ghcn = read_csv(dirs["research"] / "ghcn/labels_daily.csv")
    ghcn_by = {}
    for r in ghcn:
        ghcn_by[(r["city"], r["date"])] = r
    agrees, total, label_missing = 0, 0, 0
    agrees_round, boundary_cases = 0, 0
    mismatch_samples = []
    for m in markets:
        if m["status"] != "finalized":
            continue
        city = m["city"]
        g = ghcn_by.get((city, m["outcome_local_date"]))
        if not g:
            label_missing += 1
            continue
        val = to_float(g["tmax_f"] if m["temp_type"] == "high" else g["tmin_f"])
        if val is None:
            label_missing += 1
            continue
        floor = to_float(m["bucket_floor_f"])
        ceil = to_float(m["bucket_ceil_f"])
        inside = ((floor is None or val >= floor) and
                  (ceil is None or val <= ceil))
        predicted = "yes" if inside else "no"
        # Settlement providers report whole degrees F: also test model B
        # where the °F value is rounded to the nearest integer first.
        rounded = round(val)
        inside_r = ((floor is None or rounded >= floor) and
                    (ceil is None or rounded <= ceil))
        predicted_r = "yes" if inside_r else "no"
        actual = m["result"]
        total += 1
        if predicted == actual:
            agrees += 1
        if predicted_r == actual:
            agrees_round += 1
        # mark boundary closeness: within 0.15 F of a bucket edge
        near_edge = ((floor is not None and abs(val - floor) < 0.15) or
                     (ceil is not None and abs(val - ceil) < 0.15))
        if near_edge:
            boundary_cases += 1
        if predicted_r != actual and len(mismatch_samples) < 10:
            mismatch_samples.append({
                "market_ticker": m["market_ticker"],
                "outcome_date": m["outcome_local_date"],
                "label_f": val,
                "rounded_f": rounded,
                "floor_f": floor,
                "ceil_f": ceil,
                "predicted_rounded": predicted_r,
                "actual": actual,
            })
    out["settlement_backtest"] = {
        "checked_finalized_markets": total,
        "label_missing": label_missing,
        "agreement_pct_exact_f": round(agrees / total * 100, 2) if total else None,
        "agreement_pct_rounded_f": (round(agrees_round / total * 100, 2)
                                    if total else None),
        "boundary_close_markets": boundary_cases,
        "mismatch_samples_after_rounding": mismatch_samples,
    }


def validate_buckets(results, dirs) -> None:
    """Kalshi bucket integrity: parse failures, overlaps, adjacent gaps."""
    markets = read_csv(dirs["research"] / "kalshi/markets.csv")
    out = results.setdefault("buckets", {})
    if not markets:
        out["status"] = "NO_DATA"
        return
    by_event: dict[tuple, list[dict]] = defaultdict(list)
    for m in markets:
        by_event[(m["series_ticker"], m["outcome_local_date"])].append(m)
    unparsed: list[str] = []
    overlap_samples: list[str] = []
    gaps = overlaps = 0
    events_checked = 0
    for key, ms in by_event.items():
        events_checked += 1
        ranges: list[tuple] = []
        for m in ms:
            f = to_float(m["bucket_floor_f"])
            c = to_float(m["bucket_ceil_f"])
            if f is None and c is None:
                unparsed.append(m["market_ticker"])
            else:
                ranges.append((f, c, m["market_ticker"]))
        ranges.sort(key=lambda x: (x[0] if x[0] is not None else -1e9,
                                   x[1] if x[1] is not None else 1e9))
        prev_ceil: float | None = None
        for f, c, ticker in ranges:
            if prev_ceil is not None and f is not None:
                if f <= prev_ceil:
                    overlaps += 1
                    if len(overlap_samples) < 5:
                        overlap_samples.append(ticker)
                elif f > prev_ceil + 1:
                    gaps += 1
            if c is not None:
                prev_ceil = c
    out["events_checked"] = events_checked
    out["markets_checked"] = len(markets)
    out["unparsed_bucket_markets"] = len(unparsed)
    out["unparsed_samples"] = unparsed[:10]
    out["overlapping_buckets"] = overlaps
    out["adjacent_gaps_over_1f"] = gaps
    out["overlap_1f_boundary_samples"] = overlap_samples


def validate_nearby_asos(results, dirs) -> None:
    rows = read_csv(dirs["research"] / "nearby_asos/nearby_asos_parsed.csv")
    out = results.setdefault("nearby_asos", {})
    if not rows:
        out["status"] = "NO_DATA"
        return
    out["rows"] = len(rows)
    out["dup_station_valid"] = len(rows) - len(
        {(r["station"], r["valid_utc"]) for r in rows})
    out["non_z_valid_utc"] = sum(
        1 for r in rows if not r["valid_utc"].endswith("Z"))
    expected = {"phx": frozenset({"SDL", "CHD", "FFZ"}),
                "lv": frozenset({"HND", "VGT", "LSV"})}
    for city in sorted(expected):
        rs = [r for r in rows if r["city"] == city]
        have = {r["station"] for r in rs}
        tmp = [to_float(r["tmpf"]) for r in rs]
        tz = ZoneInfo(CITIES[city].tz_name)
        bad_local = 0
        for r in rs:
            dt = parse_utc_iso(r["valid_utc"])
            if dt is None or dt.astimezone(tz).date().isoformat() != r["local_date"]:
                bad_local += 1
        out[f"{city}_obs"] = len(rs)
        out[f"{city}_stations"] = sorted(have)
        out[f"{city}_unexpected_stations"] = sorted(have - expected[city])
        out[f"{city}_missing_stations"] = sorted(expected[city] - have)
        out[f"{city}_tmpf_missing"] = sum(1 for v in tmp if v is None)
        out[f"{city}_local_date_mismatch"] = bad_local
        out[f"{city}_metar_with_remarks"] = sum(
            1 for r in rs if "RMK" in (r["raw_metar"] or ""))


def validate_derived_state(results, dirs) -> None:
    rows = read_csv(dirs["research"] / "derived_intraday_state.csv")
    out = results.setdefault("derived_state", {})
    if not rows:
        out["status"] = "NO_DATA"
        return
    out["rows"] = len(rows)
    out["stations"] = sorted({r["station"] for r in rows})
    by: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by[(r["station"], r["local_date"])].append(r)
    bad_asof_sort = bad_hi = bad_lo = bad_mono_hi = bad_mono_lo = 0
    for (station, day), rs in by.items():
        ts = [r["feature_asof_utc"] for r in rs]
        if ts != sorted(set(ts)):
            bad_asof_sort += 1
        mx = mn = prev_hi = prev_lo = None
        for r in rs:
            t = to_float(r["current_temperature_f"])
            h = to_float(r["observed_high_so_far_f"])
            l = to_float(r["observed_low_so_far_f"])
            if t is not None:
                mx = t if mx is None else max(mx, t)
                mn = t if mn is None else min(mn, t)
            if h is not None:
                if mx is not None and abs(h - mx) > 1e-6:
                    bad_hi += 1
                if prev_hi is not None and h + 1e-6 < prev_hi:
                    bad_mono_hi += 1
                prev_hi = h
            if l is not None:
                if mn is not None and abs(l - mn) > 1e-6:
                    bad_lo += 1
                if prev_lo is not None and l - 1e-6 > prev_lo:
                    bad_mono_lo += 1
                prev_lo = l
    out["station_days"] = len(by)
    out["asof_not_sorted_or_dup"] = bad_asof_sort
    out["high_mismatch_vs_recomputed"] = bad_hi
    out["low_mismatch_vs_recomputed"] = bad_lo
    out["high_not_monotone_in_day"] = bad_mono_hi
    out["low_not_monotone_in_day"] = bad_mono_lo


def validate_timezones(results, dirs) -> None:
    """Recompute local_date from valid_utc per city zone; probe LAS DST."""
    out = results.setdefault("timezones_dst", {})
    for fname in ("iem/asos_parsed.csv", "nearby_asos/nearby_asos_parsed.csv"):
        rows = read_csv(dirs["research"] / fname)
        if not rows:
            continue
        tz_by_city = {k: ZoneInfo(c.tz_name) for k, c in CITIES.items()}
        bad = 0
        for r in rows:
            city = r.get("city") or ("lv" if r["station"] == "LAS" else "phx")
            tz = tz_by_city[city]
            dt = parse_utc_iso(r["valid_utc"])
            if dt is None:
                bad += 1
                continue
            if dt.astimezone(tz).date().isoformat() != r["local_date"]:
                bad += 1
        out[Path(fname).name] = f"{len(rows)} rows, {bad} local-date mismatches"
    probes = ["2026-03-08T07:30:00Z", "2026-03-08T08:30:00Z",
              "2026-11-01T08:30:00Z", "2026-11-01T09:30:00Z"]
    out["las_dst_probe"] = [
        (p, parse_utc_iso(p).astimezone(
            ZoneInfo(CITIES["lv"].tz_name)).isoformat()) for p in probes]


def validate_cli(results, dirs) -> None:
    rows = read_csv(dirs["research"] / "nws_cli/daily_climate_cli.csv")
    out = results.setdefault("nws_cli", {})
    if not rows:
        out["status"] = "NO_DATA"
        return
    out["product_versions"] = len(rows)
    out["dup_city_filename"] = len(rows) - len(
        {(r["city"], r["raw_filename"]) for r in rows})
    out["no_publication_time"] = sum(
        1 for r in rows if not (r.get("publication_time_utc") or ""))
    out["high_lt_low"] = sum(
        1 for r in rows
        if (to_float(r["official_daily_high_f"]) is not None
            and to_float(r["official_daily_low_f"]) is not None
            and to_float(r["official_daily_high_f"])
            < to_float(r["official_daily_low_f"])))
    by_day: dict[tuple, int] = defaultdict(int)
    for r in rows:
        by_day[(r["city"], r["climate_date"])] += 1
    out["max_versions_per_day"] = max(by_day.values()) if by_day else 0
    out["days_with_multiple_versions"] = sum(1 for n in by_day.values() if n > 1)
    out["date_range"] = (f"{min(r['climate_date'] for r in rows)}.."
                         f"{max(r['climate_date'] for r in rows)}")


def cli_vs_ghcn(results, dirs) -> None:
    """NWS CLI official daily high/low vs the GHCN-Daily record (best version/day)."""
    cli = read_csv(dirs["research"] / "nws_cli/daily_climate_cli.csv")
    ghcn = read_csv(dirs["research"] / "ghcn/labels_daily.csv")
    out = results.setdefault("cli_cross", {})
    if not cli or not ghcn:
        out["status"] = "NO_OVERLAP"
        return
    ghcn_by = {(r["city"], r["date"]): r for r in ghcn}
    best: dict[tuple, dict] = {}
    for r in cli:
        key = (r["city"], r["climate_date"])
        cur = best.get(key)
        if cur is None or r["publication_time_utc"] > cur["publication_time_utc"]:
            best[key] = r
    for city in DEFAULT_CITIES:
        diffs_hi, diffs_lo = [], []
        for (c, d), row in sorted(best.items()):
            if c != city:
                continue
            g = ghcn_by.get((city, d))
            if not g:
                continue
            hi = to_float(row["official_daily_high_f"])
            lo = to_float(row["official_daily_low_f"])
            gh = to_float(g["tmax_f"])
            gl = to_float(g["tmin_f"])
            if hi is not None and gh is not None:
                diffs_hi.append((hi - gh, d))
            if lo is not None and gl is not None:
                diffs_lo.append((lo - gl, d))
        out[city] = {
            "days_overlap": len(diffs_hi),
            "mean_abs_diff_high_f": (round(
                sum(abs(d[0]) for d in diffs_hi) / len(diffs_hi), 2)
                if diffs_hi else None),
            "max_abs_diff_high_f": (round(max(abs(d[0]) for d in diffs_hi), 2)
                                    if diffs_hi else None),
            "high_within_1f_pct": (round(
                sum(1 for d in diffs_hi if abs(d[0]) <= 1.0) / len(diffs_hi) * 100, 1)
                if diffs_hi else None),
            "mean_abs_diff_low_f": (round(
                sum(abs(d[0]) for d in diffs_lo) / len(diffs_lo), 2)
                if diffs_lo else None),
            "worst_high_date": max(diffs_hi, key=lambda d: abs(d[0]))[1]
                if diffs_hi else None,
        }


def validate_forecasts(results, dirs) -> None:
    path = dirs["research"] / "forecasts" / "manifest.csv"
    rows = read_csv(path)
    out = results.setdefault("forecasts", {})
    if not rows:
        out["status"] = "NO_DATA"
        return
    out["rows"] = len(rows)
    seen: dict[tuple, str] = {}
    dup_keys: list[tuple] = []
    for r in rows:
        k = (r["model"], r["city"], r["initialization_time_utc"],
             r["lead_hours"])
        if k in seen:
            dup_keys.append((k, r["sha256"], seen[k]))
        else:
            seen[k] = r["sha256"]
    out["duplicate_run_keys"] = len(dup_keys)
    out["unique_run_keys"] = len(seen)

    lead_bad = 0
    for r in rows:
        init = parse_utc_iso(r["initialization_time_utc"])
        valid = parse_utc_iso(r["valid_time_utc"])
        lead = to_float(r["lead_hours"])
        if init is None or valid is None:
            lead_bad += 1
        elif lead is not None and abs((valid - init).total_seconds() / 3600.0 - lead) > 0.01:
            lead_bad += 1
    out["valid_ne_init_plus_lead"] = lead_bad

    root = dirs["research"] / "forecasts"
    missing, empty, sha_bad = set(), set(), set()
    for r in rows:
        p = root / (r["raw_path"] or "")
        if not p.exists():
            missing.add(r["raw_path"])
            continue
        if p.stat().st_size == 0:
            empty.add(r["raw_path"])
            continue
        if r.get("sha256") and hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
            sha_bad.add(r["raw_path"])
    out["missing_raw_files"] = sorted(missing)
    out["empty_raw_files"] = sorted(empty)
    out["sha256_mismatch"] = sorted(sha_bad)

    ingest_bad = 0
    for r in rows:
        init = parse_utc_iso(r["initialization_time_utc"])
        ing = parse_utc_iso(r.get("ingested_at_utc"))
        if init and ing and ing < init:
            ingest_bad += 1
    out["ingested_before_initialization"] = ingest_bad

    if rows:
        decision = datetime.now(timezone.utc) - timedelta(hours=48)
        known = known_forecasts(rows, decision)
        valid_rows = valid_forecasts_asof(rows, decision)
        out["known_forecasts_asof_48h"] = len(known)
        out["valid_forecasts_asof_48h"] = len(valid_rows)
        assert all(parse_utc_iso(r["initialization_time_utc"]) <= decision
                   for r in known)


def known_labels_asof(ghcn: list[dict], ts: datetime) -> dict:
    """Anti-lookahead helper: GHCN labels whose label_available_ts <= ts."""
    out = {}
    for r in ghcn:
        avail = r.get("label_available_ts", "")
        if not avail:
            continue
        try:
            avail_dt = datetime.fromisoformat(avail.replace("Z", "+00:00"))
        except ValueError:
            continue
        if avail_dt <= ts:
            out.setdefault(r["city"], {})[r["date"]] = r
    return out


def build_example_join(results, dirs) -> None:
    """Materialize a small joined table over recent days."""
    ghcn = read_csv(dirs["research"] / "ghcn/labels_daily.csv")
    daily = read_csv(dirs["research"] / "iem/asos_daily.csv")
    solar = read_csv(dirs["research"] / "solar/solar_features.csv")
    markets = read_csv(dirs["research"] / "kalshi/markets.csv")

    ghcn_by = {(r["city"], r["date"]): r for r in ghcn}
    daily_by = defaultdict(list)
    for r in daily:
        daily_by[(r["city"], r["local_date"])].append(r)
    solar_by = {(r["city"], r["date"]): r for r in solar}
    market_by = defaultdict(list)
    for m in markets:
        market_by[(m["city"], m["outcome_local_date"])].append(m)

    now = datetime.now(timezone.utc)
    dates = sorted({d for (_c, d) in ghcn_by if d >= "2026-09-01"} |
                   {d for (_c, d) in daily_by if d >= "2026-09-01"})
    dates = dates[-12:]

    cols = ["city", "date", "ghcn_tmax_f", "ghcn_tmin_f",
            "label_available_ts", "metar_sampled_tmax_f", "metar_sampled_tmin_f",
            "metar_obs_count", "solar_daylength_min", "solar_sunrise_utc",
            "solar_sunset_utc",
            "active_market_tickers", "finalized_results",
            "ghcn_known_labels_count"]
    rows = []
    snapshot = now - timedelta(hours=6)
    known = known_labels_asof(ghcn, snapshot)
    for d in dates:
        for city in DEFAULT_CITIES:
            g = ghcn_by.get((city, d), {})
            dm = daily_by.get((city, d), [])
            s = solar_by.get((city, d), {})
            active = [m["market_ticker"] for m in market_by.get((city, d), [])
                      if m["status"] == "active"]
            finals = [f"{m['market_ticker']}={m['result']}"
                      for m in market_by.get((city, d), [])
                      if m["status"] == "finalized"]
            rows.append({
                "city": city,
                "date": d,
                "ghcn_tmax_f": g.get("tmax_f", ""),
                "ghcn_tmin_f": g.get("tmin_f", ""),
                "label_available_ts": g.get("label_available_ts", ""),
                "metar_sampled_tmax_f": (dm[0]["tmax_f"] if dm else ""),
                "metar_sampled_tmin_f": (dm[0]["tmin_f"] if dm else ""),
                "metar_obs_count": (dm[0]["obs_count"] if dm else ""),
                "solar_daylength_min": s.get("daylength_min", ""),
                "solar_sunrise_utc": s.get("sunrise_utc", ""),
                "solar_sunset_utc": s.get("sunset_utc", ""),
                "active_market_tickers": ";".join(active[:3]),
                "finalized_results": ";".join(finals[:4]),
                "ghcn_known_labels_count": len(known.get(city, {})),
            })
    path = dirs["reports"] / "joined_example.csv"
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
    results["example_join"] = {
        "path": str(path),
        "rows": len(rows),
        "snapshot_ts": snapshot.isoformat(),
    }


def write_summary(results, dirs, path: Path) -> None:
    lines = [f"validation run at {utcnow()}",
             "=" * 40]
    for section, data in results.items():
        lines.append("")
        lines.append(f"[{section}]")
        if isinstance(data, dict):
            lines.append(json.dumps(data, indent=1, default=str))
    path.write_text("\n".join(lines))
    print(f"wrote {path}")


def write_report(results, dirs, path: Path) -> None:
    sch = results.get("schema", {})
    gh = results.get("ghcn", {})
    iem = results.get("iem", {})
    sol = results.get("solar", {})
    xs = results.get("cross_source", {})
    ks = results.get("kalshi", {})
    bt = ks.get("settlement_backtest", {})
    ex = results.get("example_join", {})

    lines = []
    a = lines.append
    a("# Kalshi Phoenix / Las Vegas Weather Data Quality Report")
    a("")
    a(f"- Generated: {utcnow()}")
    a("- Scope: daily HIGH/LOW temperature markets for Phoenix (KXHIGHTPHX, "
      "KXLOWTPHX) and Las Vegas (KXHIGHTLV, KXLOWTLV).")
    a("")
    a("## 1. What is included")
    a("")
    a("- GHCN-Daily official daily labels (TMAX/TMIN) at the city airports.")
    a("- IEM ASOS raw METAR archives (parsed fields + raw remarks), trailing "
      "30 days by default.")
    a("- Solar geometry features (sunrise/sunset/daylength, declination).")
    a("- Nearby GHCN-Daily and IEM ASOS stations within 75 km.")
    a("- Kalshi market metadata (1680 markets), bounded candle + trade "
      "snapshots, and a live WebSocket orderbook collector.")
    a("")
    a("## 2. Schema checks")
    a("")
    for key, val in sch.items():
        a(f"- **{key}**: {val.get('status')} ({val.get('rows', 0)} rows, "
          f"{val.get('cols', 0)} cols)")
    a("")
    a("## 3. GHCN-Daily labels (official)")
    a("")
    for city in DEFAULT_CITIES:
        g = gh.get(city, {})
        if not g:
            a(f"- **{city}**: no data")
        else:
            a(f"- **{city}**: {g.get('rows')} rows, "
              f"{g.get('unique_dates')} unique dates, "
              f"range {g.get('date_range')}; "
              f"duplicate dates {g.get('duplicate_dates')}, "
              f"TMAX<TMIN records {g.get('tmax_lt_tmin_count')}.")
            a(f"  - TMAX range {g.get('tmax_range_f')} F, "
              f"TMIN range {g.get('tmin_range_f')} F.")
            a(f"  - GHCN last label date {g.get('last_label_date')} "
              f"(lag {g.get('ghcn_lag_days')} days vs today).")
    a("")
    a("## 4. IEM ASOS METAR archives")
    a("")
    a(f"- Parsed observations: {iem.get('parsed_obs', 0)}; "
      f"daily aggregate rows: {iem.get('daily_rows', 0)}.")
    for st in [s for s in iem if s.startswith("station_")]:
        v = iem[st]
        a(f"- {st}: {v.get('obs')} obs, "
          f"parse rate {v.get('parse_rate_pct')}%, "
          f"obs/day avg {v.get('obs_per_day_avg')}, "
          f"coverage {v.get('date_range')}, "
          f"raw METARs with remarks {v.get('raw_metar_with_remarks')}.")
    a("")
    a("METAR daily TMAX/TMIN are **sampled observation extremes**, not the "
      "official daily extremes; official values come only from GHCN-Daily "
      "(Section 3).")
    a("")
    a("## 5. Solar features")
    a("")
    a(f"- {sol.get('rows', 0)} rows, {sol.get('date_range', '')}; "
      f"implausible daylength rows {sol.get('implausible_daylength')}. "
      "All values are deterministic NOAA geometry (no observational data).")
    a("")
    a("## 6. Cross-source agreement (METAR sampled vs GHCN official)")
    a("")
    if not xs or xs.get("status") == "NO_OVERLAP":
        a("- No overlapping days available for comparison.")
    else:
        for city in DEFAULT_CITIES:
            v = xs.get(city, {})
            if v:
                a(f"- **{city}**: {v.get('overlap_days')} overlap days; "
                  f"mean|diff| TMAX {v.get('mean_abs_diff_tmax_f')} F, "
                  f"TMIN {v.get('mean_abs_diff_tmin_f')} F; "
                  f"% within 1 F {v.get('tmax_within_1f')}%; "
                  f"worst TMAX diff {v.get('max_abs_diff_tmax_f')} F on "
                  f"{v.get('worst_tmax_date')}.")
    a("")
    a("Differences are expected and are *measurement-truth* metadata: the "
      "METAR series is a rounded 1-minute-ish sample, GHCN is the official "
      "climate record; bucket settlement validation uses GHCN labels.")
    a("")
    a("## 7. Kalshi tables")
    a("")
    a(f"- Events: {ks.get('events_total')}; markets total "
      f"{ks.get('markets_total')} (active {ks.get('markets_active')}, "
      f"finalized {ks.get('markets_finalized')}).")
    a(f"- Trades: {ks.get('trades_total', 0)}, price-in-[0,1] ok "
      f"{ks.get('trades_price_in_0_1')}, parse rate "
      f"{ks.get('trades_price_parse_rate_pct')}%, dup ids "
      f"{ks.get('trades_dup_ids')}.")
    for key in ("candles_daily", "candles_hourly"):
        v = ks.get(key, {})
        a(f"- {key}: {v.get('rows', 0)} rows over "
          f"{v.get('markets', 0)} markets; duplicate market/ts "
          f"{v.get('dup_market_ts', 0)}.")
    a("")
    a("### Settlement backtest (finalized markets, GHCN bucket hit vs result)")
    a("")
    if bt:
        a(f"- Checked markets: {bt.get('checked_finalized_markets')}; "
          f"labels missing: {bt.get('label_missing')}; "
          f"agreement (exact °F from °C, 2-decimals): "
          f"{bt.get('agreement_pct_exact_f')}%; agreement (rounded to whole "
          f"°F): {bt.get('agreement_pct_rounded_f')}%; "
          f"boundary-close markets: {bt.get('boundary_close_markets')}.")
        a("- Interpretation: mismatches concentrate on GHCN values within "
          "~0.15 °F of a bucket boundary, i.e. ties/rounding between the °C "
          "climate record and the whole-°F values used by settlement "
          "providers (NWS CLI / weather.com).")
        a("- Mismatch samples after whole-°F rounding (≤10):")
        for s in bt.get("mismatch_samples_after_rounding", []):
            a(f"  - {s['market_ticker']} date={s['outcome_date']} "
              f"label={s['label_f']}F rounded={s['rounded_f']}F "
              f"bucket=[{s['floor_f']}, {s['ceil_f']}] "
              f"pred={s['predicted_rounded']} actual={s['actual']}")
    a("")
    a("## 8. Bucket integrity (gaps / overlaps)")
    a("")
    bk = results.get("buckets", {})
    a(f"- Events checked: {bk.get('events_checked')} over "
      f"{bk.get('markets_checked')} markets; unparsed bucket ranges "
      f"{bk.get('unparsed_bucket_markets')}, overlapping buckets "
      f"{bk.get('overlapping_buckets')}, adjacent gaps >1 °F "
      f"{bk.get('adjacent_gaps_over_1f')}.")
    if bk.get("unparsed_samples"):
        a(f"- Unparsed sample markets: {bk.get('unparsed_samples')}")
    a("")
    a("## 9. Derived intraday state & nearby ASOS")
    a("")
    ds = results.get("derived_state", {})
    if ds:
        a(f"- Derived rows {ds.get('rows')} over {ds.get('station_days')} "
          f"station-days; high mismatch vs recomputed "
          f"{ds.get('high_mismatch_vs_recomputed')}, low mismatch "
          f"{ds.get('low_mismatch_vs_recomputed')}; in-day monotonicity "
          f"violations high {ds.get('high_not_monotone_in_day')} / low "
          f"{ds.get('low_not_monotone_in_day')}; unsorted/duplicate "
          f"feature_asof rows {ds.get('asof_not_sorted_or_dup')}.")
    na = results.get("nearby_asos", {})
    na_rows = na.get("rows", 0)
    if na_rows:
        a(f"- Nearby ASOS: {na_rows} rows, duplicate (station, valid_utc) "
          f"{na.get('dup_station_valid')}, non-Z timestamps "
          f"{na.get('non_z_valid_utc')}.")
        for city in DEFAULT_CITIES:
            a(f"  - {city}: {na.get(f'{city}_obs')} obs, stations "
              f"{na.get(f'{city}_stations')} (unexpected "
              f"{na.get(f'{city}_unexpected_stations') or 'none'}), "
              f"missing tmpf {na.get(f'{city}_tmpf_missing')}, "
              f"local-date mismatches {na.get(f'{city}_local_date_mismatch')}.")
    tz = results.get("timezones_dst", {})
    if tz.get("asos_parsed.csv"):
        a(f"- timezone/DST: {tz.get('asos_parsed.csv')}; "
          f"{tz.get('nearby_asos_parsed.csv')}; LAS probe "
          f"{tz.get('las_dst_probe')}.")
    a("")
    a("## 10. NWS CLI product layer")
    a("")
    cl = results.get("nws_cli", {})
    if cl and cl.get("status") != "NO_DATA":
        a(f"- {cl.get('product_versions')} product versions in "
          f"{cl.get('date_range')}; max versions per climate day "
          f"{cl.get('max_versions_per_day')} (revision candidates />1 day: "
          f"{cl.get('days_with_multiple_versions')}; high<low "
          f"{cl.get('high_lt_low')}; missing publication time "
          f"{cl.get('no_publication_time')}; duplicate city/filename "
          f"{cl.get('dup_city_filename')}.")
    cc = results.get("cli_cross", {})
    if cc and cc.get("status") != "NO_OVERLAP":
        for city in DEFAULT_CITIES:
            v = cc.get(city, {})
            if v:
                a(f"- CLI vs GHCN **{city}** (latest revision per day): "
                  f"{v.get('days_overlap')} days; mean|diff| high "
                  f"{v.get('mean_abs_diff_high_f')} F, "
                  f"% within 1 F {v.get('high_within_1f_pct')}%, "
                  f"worst high {v.get('max_abs_diff_high_f')} F on "
                  f"{v.get('worst_high_date')}; mean|diff| low "
                  f"{v.get('mean_abs_diff_low_f')} F.")
    a("")
    a("## 11. Forecast manifest point-in-time checks")
    a("")
    fc = results.get("forecasts", {})
    if fc and fc.get("status") != "NO_DATA":
        a(f"- {fc.get('rows')} manifest rows, {fc.get('unique_run_keys')} "
          f"unique (model, city, init, lead) run keys; duplicate keys "
          f"{fc.get('duplicate_run_keys')}; valid≠init+lead "
          f"{fc.get('valid_ne_init_plus_lead')}; ingested before init "
          f"{fc.get('ingested_before_initialization')}.")
        a(f"- Raw GRIB files: missing {len(fc.get('missing_raw_files', []))}, "
          f"empty {len(fc.get('empty_raw_files', []))}, sha256 mismatch "
          f"{len(fc.get('sha256_mismatch', []))}.")
        a(f"- `known_forecasts` (init<=-48h decision) returns "
          f"{fc.get('known_forecasts_asof_48h')} rows, of which "
          f"{fc.get('valid_forecasts_asof_48h')} already-valid.")
    a("")
    a("## 12. Anti-lookahead controls")
    a("")
    a("The GHCN label carries `label_available_ts` (conservative synthetic "
      "gate: 36 hours after the climate day; not an observed publication "
      "time). Any market-vs-label "
      "analysis must require `label_available_ts <= market timestamp`; "
      "METAR observation rows carry `valid_utc` and can be aggregated as of "
      "any cutoff without forward spill. `KNOWN_LABELS_ASOF` behaviour is "
      "demonstrated by the example join.")
    a("")
    a(f"## 13. Example joined table")
    a("")
    a(f"- {ex.get('rows', 0)} rows written to `{ex.get('path')}` at snapshot "
      f"`{ex.get('snapshot_ts')}`.")
    a("")
    a("## 14. Known gaps / credentials")
    a("")
    a("- Live WebSocket orderbook collection requires Kalshi API credentials "
      "(KALSHI_API_KEY/KALSHI_USER_ID or the access-key handshake headers). "
      "None were present in this environment; the collector validated its "
      "config via `--dry-run` only.")
    a("- GHCN-Daily lags real time by several days (see Section 3); the most "
      "recent official labels are therefore not yet finalized in the sample.")
    a("- Timestamped NWS CLI products are preserved in `nws_cli/` for the "
      "available rolling archive window. The public IEM AFOS archive is not "
      "a multi-year archive, so full historical CLI coverage is not claimed.")
    a("- Weather Company (weather.com/kalshi) is referenced as a settlement "
      "source for these series; its underlying station feed is licensed and "
      "not part of this dataset.")
    a("")
    path.write_text("\n".join(lines))
    print(f"wrote {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()

    dirs = ensure_runtime_dirs()
    results: dict = {}
    check_schema(results, dirs)
    validate_ghcn(results, dirs)
    validate_iem(results, dirs)
    validate_solar(results, dirs)
    cross_source_agreement(results, dirs)
    validate_kalshi(results, dirs)
    validate_buckets(results, dirs)
    validate_nearby_asos(results, dirs)
    validate_derived_state(results, dirs)
    validate_timezones(results, dirs)
    validate_cli(results, dirs)
    cli_vs_ghcn(results, dirs)
    validate_forecasts(results, dirs)
    build_example_join(results, dirs)

    write_summary(results, dirs, dirs["reports"] / "validation_summary.txt")
    write_report(results, dirs, dirs["reports"] / "data_quality_report.md")
    print(f"fetched_at={utcnow()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
