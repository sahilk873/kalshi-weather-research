"""Build fail-closed point-in-time features for hourly market decisions.

This is a source join, not a model: each feature row is emitted only when a
source observation/forecast has a valid target time and its receipt clock is no
later than the market decision. Missing or late inputs are written to a
rejection file so coverage cannot be mistaken for successful backtesting.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ["market_ticker", "decision_ts", "target_ts", "horizon_minutes",
          "feature_version", "source_run_ids", "observation_ids", "features_json"]


def _number(row: dict, *keys: str) -> float | None:
    for key in keys:
        try:
            value = row.get(key, "")
            if value not in (None, ""):
                number = float(value)
                if math.isfinite(number):
                    return number
        except (TypeError, ValueError):
            pass
    return None


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position); upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _solar_features(stamp: datetime, latitude: float, longitude: float) -> dict[str, float]:
    """Approximate solar geometry using a UTC declination/hour-angle model."""
    day = stamp.timetuple().tm_yday
    declination = math.radians(23.44) * math.sin(math.radians(360.0 * (284 + day) / 365.0))
    lat = math.radians(latitude)
    utc_hour = stamp.hour + stamp.minute / 60.0 + stamp.second / 3600.0
    solar_hour = utc_hour + longitude / 15.0
    hour_angle = math.radians(15.0 * (solar_hour - 12.0))
    elevation = math.degrees(math.asin(math.sin(lat) * math.sin(declination) + math.cos(lat) * math.cos(declination) * math.cos(hour_angle)))
    azimuth = (math.degrees(math.atan2(math.sin(hour_angle), math.cos(hour_angle) * math.sin(lat) - math.tan(declination) * math.cos(lat))) + 180.0) % 360.0
    cos_hour = max(-1.0, min(1.0, -math.tan(lat) * math.tan(declination)))
    daylight_hours = math.degrees(math.acos(cos_hour)) / 15.0
    sunrise_utc = 12.0 - daylight_hours - longitude / 15.0
    sunset_utc = 12.0 + daylight_hours - longitude / 15.0
    return {"solar_elevation_deg": elevation, "solar_azimuth_deg": azimuth,
            "minutes_since_sunrise": (utc_hour - sunrise_utc) * 60.0,
            "minutes_until_sunset": (sunset_utc - utc_hour) * 60.0}


def _derived_features(observations: list[dict], forecasts: list[dict], *, target: datetime | None = None,
                      latitude: float | None = None, longitude: float | None = None) -> dict:
    """Return deterministic, JSON-safe feature families from PIT candidates."""
    features: dict = {"observation_count": len(observations), "forecast_count": len(forecasts)}
    if target is not None and latitude is not None and longitude is not None:
        features.update(_solar_features(target, latitude, longitude))
    timed = [(row, _dt(row.get("valid_utc", ""))) for row in observations]
    timed = sorted(((row, stamp) for row, stamp in timed if stamp is not None), key=lambda pair: pair[1])
    temperatures = [(stamp, _number(row, "temperature_f", "temp_f", "temperature_c")) for row, stamp in timed]
    temperatures = [(stamp, value) for stamp, value in temperatures if value is not None]
    if temperatures:
        values = [value for _, value in temperatures]
        features.update({"running_max_temperature": max(values), "running_min_temperature": min(values),
                         "temperature_latest": values[-1], "temperature_range": max(values) - min(values)})
        latest_ts, latest = temperatures[-1]
        for minutes in (5, 15, 30, 60, 120):
            prior = [(stamp, value) for stamp, value in temperatures
                     if (latest_ts - stamp).total_seconds() >= minutes * 60]
            if prior:
                features[f"temperature_slope_{minutes}m"] = (latest - prior[-1][1]) / minutes
        if len(temperatures) >= 3:
            features["temperature_slope_acceleration"] = (temperatures[-1][1] - temperatures[-2][1]) - (temperatures[-2][1] - temperatures[-3][1])
    # Preserve physically meaningful covariates when present in source rows.
    latest_row = timed[-1][0] if timed else {}
    for key in ("pressure_msl", "pressure_hpa", "dewpoint_f", "dew_point_f", "wind_speed_10m",
                "wind_direction_10m", "wind_gusts_10m", "cloud_cover", "cloud_cover_low",
                "cloud_cover_mid", "cloud_cover_high", "shortwave_radiation", "direct_radiation",
                "diffuse_radiation", "cape", "cin", "temperature_925hpa", "temperature_850hpa",
                "temperature_700hpa", "wind_850hpa", "geopotential_height_500hpa"):
        value = _number(latest_row, key)
        if value is not None:
            features[key] = value
    # Preserve station-level spatial structure when multiple stations are present.
    station_values = [_number(row, "temperature_f", "temp_f", "temperature_c") for row in observations]
    station_values = [value for value in station_values if value is not None]
    if len(station_values) >= 2:
        features["spatial_temperature_gradient_range"] = max(station_values) - min(station_values)
        features["spatial_temperature_gradient_mean"] = sum(station_values) / len(station_values)
    forecast_values = [_number(row, "value", "temperature_f", "temperature_c") for row in forecasts]
    forecast_values = [value for value in forecast_values if value is not None]
    if forecast_values:
        mean = sum(forecast_values) / len(forecast_values)
        variance = sum((value - mean) ** 2 for value in forecast_values) / len(forecast_values)
        features.update({"forecast_mean": mean, "forecast_std": math.sqrt(variance),
                         "forecast_min": min(forecast_values), "forecast_max": max(forecast_values),
                         "forecast_iqr": (_quantile(forecast_values, .75) or 0) - (_quantile(forecast_values, .25) or 0),
                         "forecast_q10": _quantile(forecast_values, .10), "forecast_q50": _quantile(forecast_values, .50),
                         "forecast_q90": _quantile(forecast_values, .90), "forecast_member_count": len(forecast_values)})
        if temperatures:
            features["forecast_minus_observed_latest"] = mean - temperatures[-1][1]
    return features


def _dt(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def build(contracts: list[dict], observations: list[dict], forecasts: list[dict],
          feature_version: str = "report2-pit-v1") -> tuple[list[dict], list[dict]]:
    obs_by_station: dict[str, list[dict]] = {}
    for row in observations:
        obs_by_station.setdefault(row.get("station", ""), []).append(row)
    for rows in obs_by_station.values():
        rows.sort(key=lambda row: _dt(row.get("valid_utc", "")) or datetime.min.replace(tzinfo=timezone.utc))
    fc_by_target: dict[str, list[dict]] = {}
    for row in forecasts:
        fc_by_target.setdefault(row.get("valid_time_utc", row.get("valid_time", "")), []).append(row)
    output, rejected = [], []
    for contract in contracts:
        market = contract.get("market_ticker", contract.get("ticker", ""))
        # Event-level crawls may omit a separate decision clock; close_time is
        # the conservative last permissible receipt boundary in that case.
        decision = _dt(contract.get("decision_ts") or contract.get("close_time") or contract.get("open_time", "")); target = contract.get("target_time_utc", "")
        target_dt = _dt(target)
        if not market or decision is None or target_dt is None:
            rejected.append({"market_ticker": market, "reason": "invalid_decision_or_target"}); continue
        # A settlement station is an exact source identity, not a hint.  When
        # contract metadata supplies one, only that station may populate the
        # primary observation features.  Other stations must never be silently
        # substituted for an unavailable settlement observation.
        settlement_station = str(contract.get("settlement_station", "")).strip()
        source_station_rows = obs_by_station.get(settlement_station, []) if settlement_station else [row for rows in obs_by_station.values() for row in rows]
        eligible_obs = []
        candidate_obs = []
        eligible_obs.extend(row for row in source_station_rows if (_dt(row.get("valid_utc", "")) or datetime.max.replace(tzinfo=timezone.utc)) <= target_dt)
        candidate_obs.extend(row for row in source_station_rows
                             if (_dt(row.get("valid_utc", "")) or datetime.max.replace(tzinfo=timezone.utc)) <= target_dt
                             and (_dt(row.get("receipt_utc", row.get("retrieved_at_utc", ""))) or datetime.max.replace(tzinfo=timezone.utc)) <= decision)
        eligible_fc = list(fc_by_target.get(target, []))
        candidate_fc = [row for row in eligible_fc if (_dt(row.get("source_receipt_time", row.get("retrieved_at_utc", ""))) or datetime.max.replace(tzinfo=timezone.utc)) <= decision]
        if not candidate_obs and not candidate_fc:
            late_obs = bool(eligible_obs)
            late_fc = bool(eligible_fc)
            if settlement_station and not source_station_rows:
                reason = "missing_exact_settlement_station_observations"
            elif late_obs and late_fc:
                reason = "late_observations_and_forecasts"
            elif late_obs:
                reason = "late_observations"
            elif late_fc:
                reason = "late_forecasts"
            else:
                reason = "missing_observations_and_forecasts"
            rejected.append({"market_ticker": market, "reason": reason}); continue
        def _coordinate(*keys: str) -> float | None:
            for key in keys:
                try:
                    value = float(contract.get(key, ""))
                    if math.isfinite(value): return value
                except (TypeError, ValueError):
                    pass
            return None
        features = _derived_features(candidate_obs, candidate_fc, target=target_dt,
                                     latitude=_coordinate("latitude", "settlement_lat"),
                                     longitude=_coordinate("longitude", "settlement_lon"))
        if candidate_obs:
            latest = max(candidate_obs, key=lambda row: _dt(row.get("valid_utc", "")) or datetime.min.replace(tzinfo=timezone.utc))
            for key in ("temperature_c", "temperature_f", "dewpoint_c", "dewpoint_f", "wind_speed_kt"):
                if latest.get(key, "") not in (None, ""):
                    features[key] = latest[key]
        if candidate_fc:
            features["forecast_values"] = [{"city": row.get("city", row.get("city_key", "")), "value": row.get("value", ""), "lead_hours": row.get("lead_hours", "")} for row in candidate_fc]
        source_runs = sorted({
            ":".join(part for part in (row.get("model", ""), row.get("city", row.get("city_key", "")), row.get("initialization_time_utc", row.get("forecast_run_time", "")), row.get("sha256", row.get("raw_sha256", ""))) if part)
            for row in candidate_fc if row.get("initialization_time_utc", row.get("forecast_run_time", ""))
        })
        obs_ids = sorted({f"{row.get('station','')}:{row.get('valid_utc','')}:{row.get('raw_sha256', '')}" for row in candidate_obs})
        output.append({"market_ticker": market, "decision_ts": decision.isoformat().replace("+00:00", "Z"), "target_ts": target, "horizon_minutes": round((target_dt - decision).total_seconds() / 60), "feature_version": feature_version, "source_run_ids": json.dumps(source_runs), "observation_ids": json.dumps(obs_ids), "features_json": json.dumps(features, sort_keys=True, separators=(",", ":"))})
    return output, rejected


def _read(path: Path) -> list[dict]:
    with path.open(newline="") as handle: return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--forecasts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rejections", type=Path, required=True)
    args = parser.parse_args()
    rows, rejected = build(_read(args.contracts), _read(args.observations), _read(args.forecasts))
    args.output.parent.mkdir(parents=True, exist_ok=True); args.rejections.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle: csv.DictWriter(handle, fieldnames=FIELDS).writeheader(); csv.DictWriter(handle, fieldnames=FIELDS).writerows(rows)
    with args.rejections.open("w", newline="") as handle: csv.DictWriter(handle, fieldnames=["market_ticker", "reason"]).writeheader(); csv.DictWriter(handle, fieldnames=["market_ticker", "reason"]).writerows(rejected)
    print(f"features={len(rows)} rejected={len(rejected)}")


if __name__ == "__main__": main()
