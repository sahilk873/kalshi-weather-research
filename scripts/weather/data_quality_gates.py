"""Audit bitemporal and duplicate-key invariants for acquired city data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from common import parse_utc_iso
from prediction_manifest import manifest_key, read_index, validate_manifest


def _rows(path: Path) -> list[dict]:
    if not path.exists(): return []
    with path.open(newline="") as fh: return list(csv.DictReader(fh))


def _safe_research_path(research_root: Path, raw_path: str) -> Path | None:
    """Resolve a manifest path only when it remains inside research_root."""
    candidate = Path(str(raw_path or ""))
    if not str(raw_path).strip() or ".." in candidate.parts:
        return None
    root = research_root.resolve()
    # Existing archives historically store either a path relative to the
    # repository or one relative to research_root. Accept both only when the
    # resolved target remains inside the research root.
    direct = candidate.resolve()
    resolved = direct if direct.is_relative_to(root) else (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _daily_source_transition_audit(research_root: Path) -> dict:
    """Require a passing, non-empty audit of active daily TWC settlement rules.

    Historical rows without event-level source metadata are intentionally
    rejected by the producing audit; this gate only accepts a report when the
    retained active sample is fully verified and contains no rejected rows.
    """
    reports = sorted((research_root / "reports").glob("daily_source_transition_*.json"))
    path = reports[-1] if reports else None
    try:
        payload = json.loads(path.read_text()) if path else {}
    except (OSError, ValueError, TypeError):
        payload = {}
    verified = int(payload.get("verified_rows", 0) or 0)
    rejected = int(payload.get("rejected_rows", 0) or 0)
    return {
        "report": str(path) if path else "",
        "verified_rows": verified,
        "rejected_rows": rejected,
        "transition_effective_date": payload.get("transition_effective_date", ""),
        "pass": bool(payload.get("pass")) and verified > 0 and rejected == 0,
    }


def _orderbook_capture_audit(research_root: Path) -> dict:
    """Require the latest captured stream to be gap-free before execution use."""
    reports = sorted((research_root / "reports").glob("orderbook_capture_*.json"))
    path = reports[-1] if reports else None
    try:
        payload = json.loads(path.read_text()) if path else {}
    except (OSError, ValueError, TypeError):
        payload = {}
    gaps = int(payload.get("sequence_gaps", 0) or 0)
    resets = int(payload.get("sequence_resets", 0) or 0)
    invalid = int(payload.get("invalid_rows", 0) or 0)
    tickers = payload.get("market_tickers", []) if isinstance(payload.get("market_tickers", []), list) else []
    target_tickers = [ticker for ticker in tickers if str(ticker).startswith("KXTEMP")]
    return {
        "report": str(path) if path else "",
        "rows": int(payload.get("rows", 0) or 0),
        "snapshot_count": int(payload.get("snapshot_count", 0) or 0),
        "populated_snapshot_count": int(payload.get("populated_snapshot_count", 0) or 0),
        "sequence_gaps": gaps,
        "sequence_resets": resets,
        "invalid_rows": invalid,
        "full_depth_evidence": bool(payload.get("full_depth_evidence")),
        "target_strategy_tickers": target_tickers,
        "pass": bool(payload.get("full_depth_evidence")) and bool(target_tickers) and int(payload.get("rows", 0) or 0) > 0 and not any((gaps, resets, invalid)),
    }


def _orderbook_reconciliation_audit(research_root: Path) -> dict:
    """Require an explicit passing WebSocket-versus-REST comparison."""
    reports = sorted((research_root / "reports").glob("orderbook_reconciliation_*.json"))
    path = reports[-1] if reports else None
    try:
        payload = json.loads(path.read_text()) if path else {}
    except (OSError, ValueError, TypeError):
        payload = {}
    mismatches = payload.get("mismatches", [])
    if not isinstance(mismatches, list):
        mismatches = ["invalid_mismatch_list"]
    return {
        "report": str(path) if path else "",
        "websocket_levels": int(payload.get("websocket_levels", 0) or 0),
        "rest_levels": int(payload.get("rest_levels", 0) or 0),
        "mismatches": len(mismatches),
        "pass": bool(path) and bool(payload.get("pass")) and not mismatches,
    }


def _duplicate_count(rows: list[dict], fields: tuple[str, ...]) -> int:
    counts = Counter(tuple(row.get(field, "") for field in fields) for row in rows)
    return sum(count - 1 for count in counts.values() if count > 1)


def _timestamp_audit(rows: list[dict], fields: tuple[str, ...], as_of: datetime) -> dict:
    missing = invalid = future = 0
    for row in rows:
        value = next((row.get(field) for field in fields if row.get(field)), None)
        parsed = parse_utc_iso(value)
        if not value: missing += 1
        elif parsed is None: invalid += 1
        elif parsed > as_of: future += 1
    return {"rows": len(rows), "missing": missing, "invalid": invalid,
            "after_as_of": future,
            "pass": not any((missing, invalid, future))}


def _historical_forecast_audit(research_root: Path) -> dict:
    """Check archived Open-Meteo historical responses for usable values.

    A successful HTTP response can still contain only null member arrays when
    the requested historical ensemble is unavailable. Such a response is
    provenance evidence, but it is not a forecast training observation.
    """
    manifest_path = research_root / "gefs" / "historical_raw" / "manifest.csv"
    rows = _rows(manifest_path)
    missing = empty = invalid_json = invalid_path = 0
    quarantine = {}
    for item in _rows(research_root / "gefs" / "historical_raw" / "quarantine.csv"):
        candidate = Path(item.get("raw_path", ""))
        if item.get("raw_path") and not candidate.is_absolute() and ".." not in candidate.parts:
            quarantine[item["raw_path"]] = item
    quarantined = 0
    for row in rows:
        raw_path = row.get("raw_path", "")
        raw = _safe_research_path(research_root, raw_path)
        if raw is None:
            invalid_path += 1
            continue
        if not raw.exists():
            missing += 1
            continue
        try:
            payload = json.loads(raw.read_text())
        except (OSError, json.JSONDecodeError):
            invalid_json += 1
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("hourly") or {}, dict):
            invalid_json += 1
            continue
        hourly = payload.get("hourly") or {}
        values = [value for key, values in hourly.items() if key != "time"
                  for value in values if value is not None]
        if not values:
            empty += 1
            key = str(raw.relative_to(research_root)) if raw.is_relative_to(research_root) else row.get("raw_path", "")
            entry = quarantine.get(key)
            if entry and entry.get("reviewed") == "true" and entry.get("reason") and entry.get("sha256") == hashlib.sha256(raw.read_bytes()).hexdigest():
                quarantined += 1
    return {"rows": len(rows), "missing_raw_path": missing,
            "empty_payload": empty, "quarantined_empty": quarantined,
            "unquarantined_empty": empty - quarantined, "invalid_json": invalid_json,
            "invalid_path": invalid_path,
            "pass": bool(rows) and not any((missing, empty - quarantined, invalid_json, invalid_path))}


def _forecast_rejection_audit(research_root: Path, as_of: datetime) -> dict:
    """Validate explicit quarantine records for unavailable NOMADS requests."""
    rows = _rows(research_root / "forecasts" / "rejections.csv")
    required = ("model", "city", "initialization_time_utc", "valid_time_utc",
                "lead_hours", "request_url", "retrieved_at_utc", "reason")
    missing = invalid = future = 0
    for row in rows:
        missing += sum(not str(row.get(field, "")).strip() for field in required)
        stamp = parse_utc_iso(row.get("retrieved_at_utc", ""))
        if row.get("retrieved_at_utc") and stamp is None:
            invalid += 1
        elif stamp and stamp > as_of:
            future += 1
    return {"rows": len(rows), "missing_fields": missing,
            "invalid_retrieval_time": invalid, "future_retrieval_time": future,
            "pass": not any((missing, invalid, future))}


def _gefs_live_audit(research_root: Path, as_of: datetime) -> dict:
    """Validate the prospective GEFS archive and its observed denominator.

    The ensemble API does not guarantee a fixed member count.  The manifest's
    declared count is therefore checked against the raw response, and the
    observed counts are retained for downstream consumers instead of assuming
    a nominal 31-member ensemble.
    """
    rows = _rows(research_root / "gefs" / "manifest.csv")
    missing = hash_mismatch = invalid = future = member_mismatch = 0
    observed: Counter[str] = Counter()
    for row in rows:
        raw = Path(row.get("raw_path", ""))
        if not raw.exists():
            raw = research_root / row.get("raw_path", "")
        if not raw.exists():
            missing += 1
            continue
        expected_hash = row.get("sha256", "")
        if not expected_hash or hashlib.sha256(raw.read_bytes()).hexdigest() != expected_hash:
            hash_mismatch += 1
        receipt = parse_utc_iso(row.get("retrieved_at"))
        if receipt is None:
            invalid += 1
        elif receipt > as_of:
            future += 1
        try:
            payload = json.loads(raw.read_text())
            hourly = payload.get("hourly") or {}
            count = len([key for key in hourly if key.startswith("temperature_2m_member")])
            observed[str(count)] += 1
            if int(row.get("member_count", "-1")) != count:
                member_mismatch += 1
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            invalid += 1
    return {"rows": len(rows), "missing_raw_path": missing,
            "hash_mismatch": hash_mismatch, "invalid_rows": invalid,
            "future_receipts": future, "member_count_mismatch": member_mismatch,
            "observed_member_counts": dict(sorted(observed.items(), key=lambda item: int(item[0]))),
            "pass": bool(rows) and not any((missing, hash_mismatch, invalid, future, member_mismatch))}


def _rtma_audit(research_root: Path, as_of: datetime | None = None) -> dict:
    manifest = _rows(research_root / "rtma" / "manifest.csv")
    missing = mismatch = invalid_time = future_time = 0
    for row in manifest:
        path = Path(row.get("raw_path", ""))
        if not path.exists(): path = research_root / row.get("raw_path", "")
        if not path.exists(): missing += 1
        elif row.get("sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]: mismatch += 1
        stamp = parse_utc_iso(row.get("retrieved_at_utc"))
        if stamp is None: invalid_time += 1
        elif as_of and stamp > as_of: future_time += 1
    features = _rows(research_root / "rtma" / "rtma_point_features.csv")
    invalid = 0
    for row in features:
        try:
            value = float(row["value"]); variable = row["variable"]; unit = row["unit"]
            bounds = {"temperature_2m": (180, 350), "dewpoint_2m": (150, 350), "wind_u_10m": (-150, 150), "wind_v_10m": (-150, 150), "cloud_cover": (0, 100), "visibility": (0, 100000)}
            if variable not in bounds or unit not in {"K", "%", "m", "m/s"} or not (bounds[variable][0] <= value <= bounds[variable][1]): invalid += 1
        except (KeyError, TypeError, ValueError): invalid += 1
    valid = all(row.get("sha256") and row.get("valid_time_utc") for row in features)
    for row in features:
        stamp = parse_utc_iso(row.get("valid_time_utc"))
        if stamp is None: invalid_time += 1
        elif as_of and stamp > as_of: future_time += 1
    return {"manifest_rows": len(manifest), "feature_rows": len(features), "missing_raw_path": missing, "hash_mismatch": mismatch, "invalid_values": invalid, "invalid_timestamp": invalid_time, "future_timestamp": future_time, "pass": bool(manifest and features and valid) and not (missing or mismatch or invalid or invalid_time or future_time)}


def _city_asos_archive_audit(research_root: Path, as_of: datetime) -> dict:
    try:
        payload = json.loads((research_root / "city_asos" / "manifest.json").read_text())
        rows = payload.get("rows", [])
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        rows = []
    missing = mismatch = invalid = future = 0
    for row in rows:
        path = Path(row.get("raw_path", ""))
        if not path.exists(): path = research_root / row.get("raw_path", "")
        if not path.exists():
            missing += 1
        elif not row.get("sha256") or hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256"):
            mismatch += 1
        receipt = parse_utc_iso(row.get("retrieved_at_utc"))
        if receipt is None or not row.get("source_url"):
            invalid += 1
        elif receipt > as_of:
            future += 1
    return {"rows": len(rows), "missing_raw_path": missing, "hash_mismatch": mismatch,
            "invalid_manifest": invalid, "future_receipts": future,
            "pass": bool(rows) and not any((missing, mismatch, invalid, future))}


def _cpc_audit(research_root: Path) -> dict:
    rows = _rows(research_root / "cpc" / "oni.csv")
    required = {"season", "year", "nino34_3mo_mean_c", "oni_anomaly_c", "source_url", "retrieved_at_utc"}
    missing_fields = sorted(required - set(rows[0])) if rows else sorted(required)
    invalid = 0; missing_time = 0
    for row in rows:
        try:
            year = int(row["year"]); mean = float(row["nino34_3mo_mean_c"]); anomaly = float(row["oni_anomaly_c"])
            if not (1900 <= year <= 2200 and -5 <= anomaly <= 5 and 0 < mean < 40): invalid += 1
            if parse_utc_iso(row.get("retrieved_at_utc")) is None: missing_time += 1
        except (KeyError, TypeError, ValueError): invalid += 1
    return {"rows": len(rows), "missing_fields": missing_fields, "invalid_values": invalid, "invalid_retrieval_timestamp": missing_time, "pass": bool(rows) and not missing_fields and invalid == 0 and missing_time == 0}


def _ghcnh_audit(research_root: Path, as_of: datetime) -> dict:
    combined = research_root / "ghcnh" / "observations_2020_2026.csv"
    rows = _rows(combined if combined.exists() else research_root / "ghcnh" / "observations_2026.csv")
    require_receipt = combined.exists()
    missing_path = missing_hash = hash_mismatch = missing_receipt = invalid = future = invalid_receipt = future_receipt = 0
    checked: dict[str, str] = {}
    for row in rows:
        raw = Path(row.get("raw_path", ""))
        if not raw.exists():
            raw = research_root / row.get("raw_path", "")
        if not raw.exists():
            missing_path += 1
        else:
            key = str(raw)
            digest = checked.get(key)
            if digest is None:
                digest = hashlib.sha256(raw.read_bytes()).hexdigest()
                checked[key] = digest
            if not row.get("sha256"): missing_hash += 1
            elif row["sha256"] != digest: hash_mismatch += 1
        if require_receipt and not row.get("source_receipt_time"): missing_receipt += 1
        receipt = parse_utc_iso(row.get("source_receipt_time"))
        if require_receipt and receipt is None: invalid_receipt += 1
        elif require_receipt and receipt > as_of: future_receipt += 1
        stamp = parse_utc_iso(row.get("valid_utc"))
        if stamp is None: invalid += 1
        elif stamp > as_of: future += 1
        try:
            temperature = float(row["temperature_f"])
            if not -130 <= temperature <= 160: invalid += 1
        except (KeyError, TypeError, ValueError):
            invalid += 1
    duplicate = _duplicate_count(rows, ("station", "valid_utc", "raw_path"))
    return {"rows": len(rows), "source_files": len(checked), "missing_raw_path": missing_path,
            "missing_hash": missing_hash, "hash_mismatch": hash_mismatch, "missing_source_receipt_time": missing_receipt,
            "invalid_source_receipt_time": invalid_receipt, "future_source_receipt_time": future_receipt,
            "duplicate_key": duplicate, "invalid_values_or_timestamps": invalid,
            "future_timestamp": future, "pass": bool(rows) and not any((missing_path, missing_hash, hash_mismatch, missing_receipt, invalid_receipt, future_receipt, duplicate, invalid, future))}


def _ghcnh_daily_audit(research_root: Path) -> dict:
    rows = _rows(research_root / "ghcnh" / "daily_extrema_2020_2026.csv")
    invalid = duplicate = 0
    expected_stations = {"USW00023183", "USW00023169", "USW00094728", "USW00023174", "USW00013904"}
    station_set = {row.get("station", "") for row in rows}
    seen = set()
    for row in rows:
        key = (row.get("station", ""), row.get("local_date", ""))
        if key in seen: duplicate += 1
        seen.add(key)
        try:
            count = int(row["observation_count"]); high = float(row["tmax_f"]); low = float(row["tmin_f"])
            if count <= 0 or high < low or not (-130 <= low <= 160 and -130 <= high <= 160): invalid += 1
            if not row.get("timezone") or not row.get("tmax_utc") or not row.get("tmin_utc") or not row.get("raw_hashes"): invalid += 1
        except (KeyError, TypeError, ValueError): invalid += 1
    unexpected = sorted(station_set - expected_stations)
    missing_stations = sorted(expected_stations - station_set)
    return {"rows": len(rows), "duplicate_key": duplicate, "invalid_rows": invalid,
            "stations": sorted(station_set), "unexpected_stations": unexpected,
            "missing_stations": missing_stations,
            "pass": bool(rows) and not invalid and not duplicate and not unexpected and not missing_stations}


def _ghcnh_daily_compare_audit(research_root: Path) -> dict:
    path = research_root / "reports" / "ghcnh_vs_ghcn_daily.json"
    try:
        payload = json.loads(path.read_text())
        overlap = int(payload.get("overlap_station_days", 0))
        comparisons = payload.get("comparisons", [])
        invalid = 0
        for row in comparisons:
            if row.get("temp_type") not in {"high", "low"} or int(row.get("overlap_days", 0)) <= 0:
                invalid += 1
            for field in ("mean_delta_f", "mae_f", "max_abs_delta_f"):
                value = float(row[field])
                if value != value or value < 0 and field != "mean_delta_f": invalid += 1
        return {"overlap_station_days": overlap, "comparison_rows": len(comparisons),
                "invalid_rows": invalid, "pass": overlap > 0 and len(comparisons) >= 2 and invalid == 0}
    except (OSError, ValueError, TypeError, KeyError):
        return {"overlap_station_days": 0, "comparison_rows": 0, "invalid_rows": 1, "pass": False}


def _settlement_window_audit(research_root: Path) -> dict:
    rows = _rows(research_root / "ghcnh" / "settlement_window_extrema_2020_2026.csv")
    invalid = duplicate = 0; seen = set()
    for row in rows:
        key = (row.get("city", ""), row.get("outcome_local_date", ""))
        if key in seen: duplicate += 1
        seen.add(key)
        try:
            start = parse_utc_iso(row["window_start_utc"]); end = parse_utc_iso(row["window_end_utc"])
            count = int(row["observation_count"]); high = float(row["tmax_f"]); low = float(row["tmin_f"])
            if row["city"] not in {"phx", "lv"} or not start or not end or end <= start or count <= 0 or high < low or not row.get("raw_hashes"): invalid += 1
        except (KeyError, TypeError, ValueError): invalid += 1
    return {"rows": len(rows), "duplicate_key": duplicate, "invalid_rows": invalid,
            "pass": bool(rows) and not duplicate and not invalid}


def _weather_index_audit(research_root: Path, as_of: datetime) -> dict:
    try:
        rows = json.loads((research_root / "weather_index" / "manifest.json").read_text()).get("rows", [])
    except (OSError, ValueError, TypeError):
        rows = []
    invalid = missing = mismatch = future = 0
    for row in rows:
        stamp = parse_utc_iso(row.get("retrieved_at_utc"))
        if stamp is None or stamp > as_of: future += 1
        if row.get("status") == 200:
            path = Path(row.get("raw_path", ""))
            if not path.exists(): path = research_root / row.get("raw_path", "")
            if not path.exists(): missing += 1; continue
            if row.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest(): mismatch += 1
            try:
                payload = json.loads(path.read_text())
                if payload.get("city") != row.get("city") or not isinstance(payload.get("timeseries"), list) or not row.get("config_version"): invalid += 1
            except (OSError, ValueError, TypeError): invalid += 1
        elif not row.get("error"):
            invalid += 1
    return {"rows": len(rows), "successful": sum(r.get("status") == 200 for r in rows), "missing_raw_path": missing,
            "hash_mismatch": mismatch, "invalid_rows": invalid, "invalid_or_future_receipts": future,
            "pass": bool(rows) and not any((missing, mismatch, invalid, future))}


def _awc_metar_audit(research_root: Path, as_of: datetime) -> dict:
    """Validate an AWC snapshot while keeping observation and receipt clocks separate."""
    rows = _rows(research_root / "awc" / "metar.csv")
    missing = mismatch = invalid = future = 0
    try:
        payload = json.loads((research_root / "awc" / "manifest.json").read_text())
        manifests = payload.get("snapshots", []) or [payload.get("latest", payload)]
        for manifest in manifests:
            path = Path(manifest.get("raw_path", ""))
            if not path.exists(): path = research_root / manifest.get("raw_path", "")
            if not path.exists(): missing += 1
            elif manifest.get("raw_sha256") != hashlib.sha256(path.read_bytes()).hexdigest(): mismatch += 1
            receipt = parse_utc_iso(manifest.get("retrieved_at_utc"))
            if receipt is None: invalid += 1
            elif receipt > as_of: future += 1
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        missing += 1
    for row in rows:
        valid = parse_utc_iso(row.get("valid_utc")); receipt = parse_utc_iso(row.get("receipt_utc"))
        if not row.get("station") or valid is None or receipt is None: invalid += 1
        elif receipt > as_of: future += 1
    return {"rows": len(rows), "snapshots": len(manifests) if 'manifests' in locals() else 0, "missing_raw_path": missing, "hash_mismatch": mismatch,
            "invalid_rows": invalid, "future_receipts": future,
            "pass": bool(rows) and not any((missing, mismatch, invalid, future))}


def _lamp_audit(research_root: Path, as_of: datetime) -> dict:
    try:
        payload = json.loads((research_root / "lamp" / "manifest.json").read_text())
        manifests = payload.get("snapshots", []) or [payload.get("latest", payload)]
        missing = mismatch = invalid = future = 0
        for manifest in manifests:
            path = Path(manifest.get("raw_path", ""))
            if not path.exists(): path = research_root / manifest.get("raw_path", "")
            missing += int(not path.exists())
            mismatch += int(path.exists() and manifest.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest())
            receipt = parse_utc_iso(manifest.get("retrieved_at_utc"))
            invalid += int(receipt is None or not manifest.get("source_url"))
            future += int(receipt is not None and receipt > as_of)
        rows = len(manifests)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        rows = missing = 0; mismatch = invalid = future = 1
    return {"rows": rows, "missing_raw_path": missing, "hash_mismatch": mismatch,
            "invalid_manifest": invalid, "future_receipts": future,
            "pass": bool(rows) and not any((missing, mismatch, invalid, future))}


def _lamp_station_audit(research_root: Path, as_of: datetime) -> dict:
    rows = _rows(research_root / "lamp" / "station_forecasts.csv")
    invalid = future = hash_mismatch = 0
    checked: dict[str, str] = {}
    for row in rows:
        if not all(row.get(field) for field in ("station", "initialization_time_utc", "valid_time_utc", "field", "raw_path", "raw_sha256")):
            invalid += 1
        init = parse_utc_iso(row.get("initialization_time_utc")); valid = parse_utc_iso(row.get("valid_time_utc")); receipt = parse_utc_iso(row.get("retrieved_at_utc"))
        if init is None or valid is None or valid < init or receipt is None:
            invalid += 1
        elif receipt > as_of:
            future += 1
        path = Path(row.get("raw_path", ""))
        if not path.exists(): path = research_root / row.get("raw_path", "")
        if not path.exists():
            invalid += 1
        else:
            digest = checked.setdefault(str(path), hashlib.sha256(path.read_bytes()).hexdigest())
            if digest != row.get("raw_sha256"): hash_mismatch += 1
    return {"rows": len(rows), "invalid_rows": invalid, "future_receipts": future,
            "hash_mismatch": hash_mismatch, "source_files": len(checked),
            "pass": bool(rows) and not any((invalid, future, hash_mismatch))}


def _glmp_audit(research_root: Path, as_of: datetime) -> dict:
    """Validate the GLMP temperature GRIB2 snapshot history."""
    try:
        payload = json.loads((research_root / "glmp" / "manifest.json").read_text())
        manifests = payload.get("snapshots", []) or [payload.get("latest", payload)]
        missing = mismatch = invalid = future = 0
        for manifest in manifests:
            path = Path(manifest.get("raw_path", ""))
            if not path.exists(): path = research_root / manifest.get("raw_path", "")
            missing += int(not path.exists())
            mismatch += int(path.exists() and manifest.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest())
            receipt = parse_utc_iso(manifest.get("retrieved_at_utc"))
            invalid += int(receipt is None or not manifest.get("initialization_time_utc") or not manifest.get("source_url", "").endswith("fcsts_t.g.co.grib2"))
            if path.exists():
                try:
                    invalid += int(path.read_bytes()[:4] != b"GRIB")
                except OSError:
                    invalid += 1
            future += int(receipt is not None and receipt > as_of)
        rows = len(manifests)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        rows = missing = 0; mismatch = invalid = future = 1
    return {"rows": rows, "missing_raw_path": missing, "hash_mismatch": mismatch,
            "invalid_manifest": invalid, "future_receipts": future,
            "pass": bool(rows) and not any((missing, mismatch, invalid, future))}


def _glmp_point_audit(research_root: Path, as_of: datetime) -> dict:
    rows = _rows(research_root / "glmp" / "point_features.csv")
    missing = mismatch = invalid = future = 0; checked = {}
    for row in rows:
        path = Path(row.get("raw_path", ""))
        if not path.exists(): path = research_root / row.get("raw_path", "")
        if not path.exists(): missing += 1
        else:
            digest = checked.setdefault(str(path), hashlib.sha256(path.read_bytes()).hexdigest())
            mismatch += int(not row.get("sha256") or row["sha256"] != digest)
        init = parse_utc_iso(row.get("initialization_time_utc")); valid = parse_utc_iso(row.get("valid_time_utc")); receipt = parse_utc_iso(row.get("source_receipt_time"))
        try: value = float(row.get("value", "nan")); lead = int(row.get("lead_hours", "-1"))
        except (TypeError, ValueError): value = float("nan"); lead = -1
        invalid += int(init is None or valid is None or receipt is None or valid < init or lead < 0 or row.get("model") != "GLMP" or row.get("variable") != "temperature_2m" or row.get("unit") != "F" or not math.isfinite(value) or not -130 <= value <= 160)
        future += int(receipt is not None and receipt > as_of)
    duplicate = _duplicate_count(rows, ("model", "city", "initialization_time_utc", "lead_hours", "raw_path", "message_index"))
    return {"rows": len(rows), "source_files": len(checked), "missing_raw_path": missing, "hash_mismatch": mismatch, "invalid_rows": invalid, "future_receipts": future, "duplicate_key": duplicate, "pass": bool(rows) and not any((missing, mismatch, invalid, future, duplicate))}


def _kalshi_hourly_audit(research_root: Path, as_of: datetime) -> dict:
    """Validate the immutable KXTEMPNYCH metadata archive."""
    root = research_root / "kalshi_hourly"
    events = _rows(root / "events.csv"); markets = _rows(root / "markets.csv")
    missing = mismatch = invalid = future = 0; checked = set()
    for row in events:
        path = Path(row.get("raw_path", "")); path = path if path.exists() else research_root / row.get("raw_path", "")
        if not path.exists(): missing += 1
        else:
            checked.add(str(path)); mismatch += int(not row.get("raw_sha256") or hashlib.sha256(path.read_bytes()).hexdigest() != row.get("raw_sha256"))
        receipt = parse_utc_iso(row.get("retrieved_at_utc")); invalid += int(receipt is None or row.get("series_ticker") != "KXTEMPNYCH"); future += int(receipt is not None and receipt > as_of)
    for row in markets:
        invalid += int(not row.get("ticker") or not row.get("event_ticker") or row.get("series_ticker") != "KXTEMPNYCH")
        receipt = parse_utc_iso(row.get("retrieved_at_utc")); invalid += int(receipt is None); future += int(receipt is not None and receipt > as_of)
    duplicate_events = _duplicate_count(events, ("event_ticker",)); duplicate_markets = _duplicate_count(markets, ("ticker",))
    return {"events": len(events), "markets": len(markets), "source_files": len(checked), "missing_raw_path": missing,
            "hash_mismatch": mismatch, "invalid_rows": invalid, "future_receipts": future,
            "duplicate_events": duplicate_events, "duplicate_markets": duplicate_markets,
            "pass": bool(events and markets) and not any((missing, mismatch, invalid, future, duplicate_events, duplicate_markets))}


def _twc_kalshi_audit(research_root: Path, as_of: datetime) -> dict:
    root = research_root / "twc_kalshi"; hourly = _rows(root / "hourly.csv"); daily = _rows(root / "daily.csv")
    missing = mismatch = invalid = future = 0; checked = set()
    availability_metadata_missing = 0
    try:
        manifest = json.loads((root / "manifest.json").read_text())
        snapshots = manifest.get("snapshots", []) if isinstance(manifest, dict) else []
        availability_metadata_missing = sum(
            not isinstance(row, dict)
            or row.get("availability_basis") != "receipt_upper_bound"
            or row.get("source_publication_time_observed") is not False
            for row in snapshots
        )
    except (OSError, ValueError, TypeError):
        snapshots = []
        availability_metadata_missing = 1
    for row in hourly + daily:
        path = _safe_research_path(research_root, row.get("raw_path", ""))
        if path is None or not path.exists(): missing += 1
        else:
            checked.add(str(path)); mismatch += int(not row.get("raw_sha256") or hashlib.sha256(path.read_bytes()).hexdigest() != row.get("raw_sha256"))
        receipt = parse_utc_iso(row.get("retrieved_at_utc")); invalid += int(receipt is None); future += int(receipt is not None and receipt > as_of)
    for row in hourly:
        invalid += int(row.get("station") not in {"KNYC", "KLAX", "KAUS"} or parse_utc_iso(row.get("valid_utc")) is None)
        try: invalid += int(not -130 <= float(row.get("temperature_f", "nan")) <= 160)
        except (TypeError, ValueError): invalid += 1
    return {"hourly_rows": len(hourly), "daily_rows": len(daily), "source_files": len(checked), "missing_raw_path": missing, "hash_mismatch": mismatch, "invalid_rows": invalid, "future_receipts": future, "snapshots": len(snapshots), "availability_metadata_missing": availability_metadata_missing, "pass": bool(hourly and daily and snapshots) and not any((missing, mismatch, invalid, future, availability_metadata_missing))}


def _kalshi_hourly_contract_audit(research_root: Path, as_of: datetime) -> dict:
    rows = _rows(research_root / "kalshi_hourly" / "contracts.csv"); invalid = future = 0
    for row in rows:
        target = parse_utc_iso(row.get("target_time_utc")); receipt = parse_utc_iso(row.get("retrieved_at_utc"))
        invalid += int(row.get("series_ticker") != "KXTEMPNYCH" or not row.get("market_ticker") or target is None or receipt is None or not row.get("rules_hash") or row.get("comparison") not in {"above", "below"})
        future += int(receipt is not None and receipt > as_of)
    duplicate = _duplicate_count(rows, ("market_ticker",))
    return {"rows": len(rows), "invalid_rows": invalid, "future_receipts": future, "duplicate_market_ticker": duplicate, "pass": bool(rows) and not any((invalid, future, duplicate))}


def _kalshi_twc_label_audit(research_root: Path, as_of: datetime) -> dict:
    rows = _rows(research_root / "kalshi_hourly" / "twc_labels.csv"); matched = [r for r in rows if r.get("source_valid_utc")]
    invalid = future = 0; checked = set()
    for row in matched:
        path = Path(row.get("source_raw_path", "")); path = path if path.exists() else research_root / row.get("source_raw_path", "")
        if not path.exists(): invalid += 1
        else:
            checked.add(str(path)); invalid += int(not row.get("source_raw_sha256") or hashlib.sha256(path.read_bytes()).hexdigest() != row.get("source_raw_sha256"))
        target = parse_utc_iso(row.get("target_time_utc")); valid = parse_utc_iso(row.get("source_valid_utc")); receipt = parse_utc_iso(row.get("label_available_ts"))
        result = row.get("kalshi_result")
        consistency = result not in {"yes", "no"} or row.get("source_observed_yes") == ("true" if result == "yes" else "false")
        invalid += int(target is None or valid is None or receipt is None or _canonical_time(valid) != _canonical_time(target) or receipt < valid or row.get("source_observed_yes") not in {"true", "false"} or not consistency)
        future += int(receipt is not None and receipt > as_of)
    duplicate = _duplicate_count(rows, ("market_ticker",))
    return {"rows": len(rows), "matched": len(matched), "source_files": len(checked), "invalid_rows": invalid, "future_receipts": future, "duplicate_market_ticker": duplicate, "pass": bool(rows) and not any((invalid, future, duplicate))}


def _historical_nyc_quote_audit(research_root: Path, as_of: datetime,
                                quote_dir: Path | None = None,
                                expected_series: str = "KXTEMPNYCH") -> dict:
    """Verify immutable raw evidence behind a city quote archive."""
    root = quote_dir or (research_root / "kalshi_hourly" / "historical_quotes")
    try:
        manifest = json.loads((root / "manifest.json").read_text())
    except (OSError, ValueError, TypeError):
        manifest = {}
    candles = _rows(root / "candles_hourly.csv")
    trades = _rows(root / "trades.csv")
    metadata = _rows(root / "market_metadata.csv")
    failures = _rows(root / "rejections.csv")
    raw_manifest_path = root / "raw_manifest.jsonl"
    records = []
    if raw_manifest_path.exists():
        try:
            records = [json.loads(line) for line in raw_manifest_path.read_text().splitlines() if line.strip()]
        except (OSError, ValueError, TypeError):
            records = []
    quarantine_path = root / "raw_quarantine_manifest.jsonl"
    quarantine = []
    if quarantine_path.exists():
        try:
            quarantine = [json.loads(line) for line in quarantine_path.read_text().splitlines() if line.strip()]
        except (OSError, ValueError, TypeError):
            quarantine = []
    missing = mismatch = invalid = future = unsafe = quarantine_invalid = 0
    for record in records:
        if not isinstance(record, dict):
            invalid += 1
            continue
        path = _safe_research_path(research_root, record.get("raw_path", ""))
        if path is None or not path.exists():
            missing += 1
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            missing += 1
            continue
        expected = str(record.get("sha256", ""))
        # The collector hashes canonical JSON without the terminal newline;
        # raw files retain a newline for safe line-oriented inspection.
        canonical = path.read_bytes().rstrip(b"\n")
        canonical_digest = hashlib.sha256(canonical).hexdigest()
        mismatch += int(not expected or digest != expected and canonical_digest != expected)
        stamp = parse_utc_iso(record.get("retrieved_at_utc"))
        invalid += int(stamp is None or not record.get("endpoint"))
        future += int(stamp is not None and stamp > as_of)
        try:
            path.relative_to((root / "raw").resolve())
            inside_raw = True
        except ValueError:
            inside_raw = False
        unsafe += int(path.suffix != ".json" or not inside_raw)
    indexed_paths = {str(_safe_research_path(research_root, row.get("raw_path", ""))) for row in records}
    quarantine_paths = set()
    for record in quarantine:
        if not isinstance(record, dict) or record.get("status") != "quarantined":
            quarantine_invalid += 1
            continue
        path = _safe_research_path(research_root, record.get("raw_path", ""))
        if path is None or not path.exists():
            quarantine_invalid += 1
            continue
        quarantine_paths.add(str(path))
        expected = str(record.get("sha256", ""))
        actual = hashlib.sha256(path.read_bytes().rstrip(b"\n")).hexdigest()
        quarantine_invalid += int(not expected or actual != expected or not record.get("reason"))
    raw_files = {str(path.resolve()) for path in (root / "raw").glob("*.json")}
    indexed_resolved = {str(Path(path).resolve()) for path in indexed_paths if path != "None"}
    quarantine_resolved = {str(Path(path).resolve()) for path in quarantine_paths}
    unindexed = len(raw_files - indexed_resolved - quarantine_resolved)
    expected_raw = int(manifest.get("raw_payloads", 0) or 0)
    expected_failures = int(manifest.get("failed_markets", 0) or 0)
    metadata_duplicate = _duplicate_count(metadata, ("market_ticker",))
    candle_tickers = {row.get("market_ticker", "") for row in candles if row.get("market_ticker", "")}
    metadata_tickers = {row.get("market_ticker", "") for row in metadata if row.get("market_ticker", "")}
    metadata_missing = len(candle_tickers - metadata_tickers) if manifest.get("version", "").endswith("-v3") else 0
    return {"markets_processed": int(manifest.get("markets_processed", 0) or 0),
            "candle_rows": len(candles), "trade_rows": len(trades),
            "market_metadata_rows": len(metadata), "market_metadata_duplicate_tickers": metadata_duplicate,
            "market_metadata_missing_for_candles": metadata_missing,
            "raw_payloads": len(records), "expected_raw_payloads": expected_raw,
            "failed_markets": len(failures), "expected_failed_markets": expected_failures,
            "missing_raw_path": missing, "hash_mismatch": mismatch,
            "invalid_manifest_rows": invalid, "future_receipts": future,
            "unsafe_raw_path": unsafe,
            "quarantined_raw_files": len(quarantine_paths),
            "unindexed_raw_files": unindexed,
            "invalid_quarantine_rows": quarantine_invalid,
            "pass": bool(manifest) and manifest.get("series_ticker") == expected_series
            and manifest.get("version") in {"historical-nyc-quotes-v2", "historical-city-quotes-v2", "historical-nyc-quotes-v3", "historical-city-quotes-v3"}
            and len(candles) == int(manifest.get("candle_rows", -1))
            and len(trades) == int(manifest.get("trade_rows", -1))
            and expected_raw > 0 and len(records) == expected_raw
            and len(failures) == expected_failures
            and not any((missing, mismatch, invalid, future, unsafe, quarantine_invalid, unindexed,
                         metadata_duplicate, metadata_missing))}


def _canonical_time(value):
    return value.replace(microsecond=0)


def _homr_audit(research_root: Path, as_of: datetime) -> dict:
    # HOMR's manifest is JSON (unlike the CSV source manifests).
    try:
        payload = json.loads((research_root / "homr" / "manifest.json").read_text())
        manifest = payload.get("rows", [])
    except (OSError, ValueError, TypeError):
        manifest = []
    missing = mismatch = invalid_json = invalid_station = invalid_time = future = 0
    for row in manifest:
        path = Path(row.get("raw_path", ""))
        if not path.exists(): path = research_root / row.get("raw_path", "")
        if not path.exists():
            missing += 1; continue
        try:
            obj = json.loads(path.read_text())
            stations = obj.get("stationCollection", {}).get("stations", [])
            identifiers = {item.get("id") for item in (stations[0].get("identifiers", []) if len(stations) == 1 else [])}
            if len(stations) != 1 or row.get("station") not in identifiers:
                invalid_station += 1
        except (OSError, ValueError, TypeError, AttributeError):
            invalid_json += 1
        if not row.get("sha256") or hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256"):
            mismatch += 1
        stamp = parse_utc_iso(row.get("retrieved_at_utc"))
        if stamp is None: invalid_time += 1
        elif stamp > as_of: future += 1
    return {"rows": len(manifest), "missing_raw_path": missing, "hash_mismatch": mismatch,
            "invalid_json": invalid_json, "invalid_station": invalid_station,
            "invalid_retrieval_timestamp": invalid_time, "future_timestamp": future,
            "pass": bool(manifest) and not any((missing, mismatch, invalid_json, invalid_station, invalid_time, future))}


def _ecmwf_audit(research_root: Path, as_of: datetime) -> dict:
    try:
        manifest = json.loads((research_root / "ecmwf" / "manifest.json").read_text()).get("rows", [])
    except (OSError, ValueError, TypeError):
        manifest = []
    missing = mismatch = invalid_time = future = invalid_payload = 0
    for row in manifest:
        path = Path(row.get("raw_path", ""))
        if not path.exists(): path = research_root / row.get("raw_path", "")
        if not path.exists(): missing += 1; continue
        if not row.get("sha256") or hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256"): mismatch += 1
        if path.stat().st_size != int(row.get("bytes", -1)): mismatch += 1
        stamp = parse_utc_iso(row.get("retrieved_at_utc"))
        if stamp is None: invalid_time += 1
        elif stamp > as_of: future += 1
        if row.get("parameter") != "2t" or row.get("decoded") is not False: invalid_payload += 1
    return {"rows": len(manifest), "missing_raw_path": missing, "hash_or_size_mismatch": mismatch,
            "invalid_retrieval_timestamp": invalid_time, "future_timestamp": future,
            "invalid_request_metadata": invalid_payload,
            "pass": bool(manifest) and not any((missing, mismatch, invalid_time, future, invalid_payload))}


def _ecmwf_point_audit(research_root: Path, as_of: datetime) -> dict:
    rows = _rows(research_root / "ecmwf" / "point_features.csv")
    missing = mismatch = invalid = future = duplicate = 0
    checked: dict[str, str] = {}
    for row in rows:
        path = Path(row.get("raw_path", ""))
        if not path.exists(): path = research_root / row.get("raw_path", "")
        if not path.exists(): missing += 1
        else:
            key = str(path); digest = checked.get(key)
            if digest is None:
                digest = hashlib.sha256(path.read_bytes()).hexdigest(); checked[key] = digest
            if not row.get("sha256") or row["sha256"] != digest: mismatch += 1
        init = parse_utc_iso(row.get("initialization_time_utc")); valid = parse_utc_iso(row.get("valid_time_utc")); receipt = parse_utc_iso(row.get("source_receipt_time"))
        if init is None or valid is None or receipt is None or valid < init: invalid += 1
        if receipt and receipt > as_of: future += 1
        try:
            if row.get("model") != "ECMWF_IFS" or row.get("variable") != "temperature_2m" or row.get("unit") != "F" or not -130 <= float(row["value"]) <= 160 or row.get("city") not in {"phx","lv","nyc","la","austin"}: invalid += 1
        except (KeyError, TypeError, ValueError): invalid += 1
    duplicate = _duplicate_count(rows, ("model", "city", "initialization_time_utc", "lead_hours", "variable", "raw_path", "message_index"))
    return {"rows": len(rows), "source_files": len(checked), "missing_raw_path": missing, "hash_mismatch": mismatch, "invalid_values_or_timestamps": invalid, "future_receipt_timestamp": future, "duplicate_key": duplicate, "pass": bool(rows) and not any((missing, mismatch, invalid, future, duplicate))}


def _ecmwf_ensemble_audit(research_root: Path, as_of: datetime) -> dict:
    rows = _rows(research_root / "ecmwf" / "ensemble_points.csv")
    missing = mismatch = invalid = future = 0; checked = {}
    for row in rows:
        path = Path(row.get("raw_path", "")); path = path if path.exists() else research_root / row.get("raw_path", "")
        if not path.exists(): missing += 1
        else:
            key = str(path); digest = checked.get(key)
            if digest is None: digest = hashlib.sha256(path.read_bytes()).hexdigest(); checked[key] = digest
            if not row.get("sha256") or row["sha256"] != digest: mismatch += 1
        init=parse_utc_iso(row.get("initialization_time_utc")); valid=parse_utc_iso(row.get("valid_time_utc")); receipt=parse_utc_iso(row.get("source_receipt_time"))
        if init is None or valid is None or receipt is None or valid < init or not row.get("member_id"): invalid += 1
        if receipt and receipt > as_of: future += 1
        try:
            if row.get("model") != "ECMWF_IFS_ENFO" or row.get("variable") != "temperature_2m" or row.get("unit") != "F" or not -130 <= float(row["value"]) <= 160: invalid += 1
        except (KeyError, TypeError, ValueError): invalid += 1
    duplicate=_duplicate_count(rows,("model","city","member_id","initialization_time_utc","lead_hours","variable","raw_path","message_index"))
    return {"rows":len(rows),"source_files":len(checked),"missing_raw_path":missing,"hash_mismatch":mismatch,"invalid_values_or_timestamps":invalid,"future_receipt_timestamp":future,"duplicate_key":duplicate,"pass":bool(rows) and not any((missing,mismatch,invalid,future,duplicate))}


def _prediction_manifest_audit(research_root: Path, as_of: datetime) -> dict:
    """Validate immutable prediction manifests for PIT clock and provenance.

    Files under ``predictions/`` (recursively, so
    ``predictions/model_version=<version>/`` layouts are audited) are one
    report-2 manifest each. Missing PIT/provenance/rules/market fields,
    unparseable JSON, decision timestamps after the audit clock, id resolution
    failures against any supplied index, contract mismatches, content-hash /
    filename drift, duplicate logical manifests, and ``model_version=``
    directory mismatches all fail closed; an absent directory is also red
    until a model actually emits manifests.
    """
    pred_dir = research_root / "predictions"
    files = sorted(pred_dir.glob("**/*.json")) if pred_dir.is_dir() else []
    contracts_path = research_root / "kalshi_hourly" / "contracts.csv"
    contracts = read_index(contracts_path, "market_ticker") if contracts_path.exists() else None
    source_index = read_index(pred_dir / "source_index.csv", "source_run_id") if (pred_dir / "source_index.csv").exists() else None
    observation_index = read_index(pred_dir / "observation_index.csv", "observation_id") if (pred_dir / "observation_index.csv").exists() else None
    invalid_json = 0
    manifests: list[tuple[Path, dict]] = []
    hash_counts: dict = {}
    for path in files:
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            invalid_json += 1
            continue
        if not isinstance(payload, dict):
            invalid_json += 1
            continue
        manifests.append((path, payload))
        try:
            digest = manifest_key(payload)
        except (TypeError, ValueError):
            digest = None
        hash_counts[digest] = hash_counts.get(digest, 0) + 1
    invalid = future = decision_missing = hash_mismatch = mv_mismatch = 0
    for path, manifest in manifests:
        errors = validate_manifest(manifest, contracts=contracts, source_index=source_index, observation_index=observation_index)
        invalid += len(errors)
        stamp = parse_utc_iso(manifest.get("decision_ts"))
        if stamp is None:
            decision_missing += 1
        elif stamp > as_of:
            future += 1
        try:
            expected = f"manifest_{manifest_key(manifest)}.json"
        except (TypeError, ValueError):
            expected = ""
        if expected and path.name != expected:
            hash_mismatch += 1
        rel = path.relative_to(pred_dir)
        top = rel.parts[0] if len(rel.parts) > 1 else None
        if top is not None and top.startswith("model_version="):
            declared = str(manifest.get("model_version", ""))
            if declared != top.split("=", 1)[1]:
                mv_mismatch += 1
    duplicate = sum(count - 1 for count in hash_counts.values() if (count or 0) > 1)
    return {"files": len(files), "manifests": len(manifests),
            "invalid_json": invalid_json, "missing_or_invalid_fields": invalid,
            "missing_decision_ts": decision_missing, "future_decision": future,
            "hash_mismatch": hash_mismatch, "model_version_mismatch": mv_mismatch,
            "duplicate_manifests": duplicate,
            "pass": bool(manifests) and not any((invalid_json, invalid, decision_missing, future, hash_mismatch, mv_mismatch, duplicate))}


def _provenance_index_audit(research_root: Path) -> dict:
    """Audit the generated provenance indexes without promoting partial data."""
    directory = research_root / "reports" / "provenance_indexes"
    status_path = directory / "provenance_index_status.json"
    try:
        status = json.loads(status_path.read_text()) if status_path.exists() else {}
    except (OSError, ValueError, TypeError):
        status = {}
    source_rows = _rows(directory / "source_index.csv")
    observation_rows = _rows(directory / "observation_index.csv")
    rejected = int(status.get("rejected_rows", 0) or 0)
    hard_rejected = int(status.get("hard_rejected_rows", rejected) or 0)
    station_scope = status.get("station_scope")
    expected_scope = ["KAUS", "KLAX", "KNYC"]
    scope_valid = isinstance(station_scope, list) and sorted(str(item) for item in station_scope) == expected_scope
    missing_raw = hash_mismatch = invalid_path = 0
    for path in (directory / "source_index.csv", directory / "observation_index.csv"):
        for row in _rows(path):
            resolved = _safe_research_path(research_root, row.get("raw_path", ""))
            if resolved is None:
                invalid_path += 1
                continue
            if not resolved.exists():
                missing_raw += 1
            elif row.get("raw_sha256"):
                try:
                    if hashlib.sha256(resolved.read_bytes()).hexdigest() != row["raw_sha256"]:
                        hash_mismatch += 1
                except OSError:
                    missing_raw += 1
    return {"source_rows": len(source_rows), "observation_rows": len(observation_rows),
            "rejected_rows": rejected, "hard_rejected_rows": hard_rejected,
            "scoped_out_rows": int(status.get("scoped_out_rows", 0) or 0),
            "station_scope": station_scope, "station_scope_valid": scope_valid,
            "missing_raw_path": missing_raw, "invalid_path": invalid_path,
            "hash_mismatch": hash_mismatch,
            "status_present": bool(status),
            "pass": bool(source_rows and observation_rows) and scope_valid and hard_rejected == 0 and not any((missing_raw, invalid_path, hash_mismatch)) and bool(status.get("pass"))}


def _live_daily_diagnostic_audit(research_root: Path) -> dict:
    """Ensure diagnostic rows contain executable quote fields before review."""
    reports = research_root / "reports"
    current = reports / "live_daily_diagnostic_current.csv"
    dated = reports / "live_daily_diagnostic_predictions_20260913.csv"
    # Prefer the current receipt-aligned artifact when present; retain the
    # dated path for backwards-compatible audits of the earlier capture.
    rows = _rows(current if current.exists() else dated)
    fields = ("best_yes_bid_cents", "best_yes_ask_cents", "spread_cents", "top_depth")
    missing = 0
    for row in rows:
        try:
            values = [float(row.get(field, "nan")) for field in fields]
            if not all(math.isfinite(value) for value in values):
                missing += 1
        except (TypeError, ValueError):
            missing += 1
    return {"rows": len(rows), "missing_executable_quote_rows": missing,
            "pass": bool(rows) and missing == 0}


def _live_price_summary_audit(research_root: Path) -> dict:
    """Require the live price summary to remain explicitly non-trading."""
    path = research_root / "reports" / "live_price_comparison_summary.json"
    try:
        payload = json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError, TypeError):
        payload = {}
    safe = payload.get("status") == "diagnostic_only" and payload.get("settled_rows") == 0
    safe = safe and payload.get("realized_edge") is None and payload.get("net_pnl") is None
    return {"rows": int(payload.get("rows", 0) or 0), "status": payload.get("status", ""),
            "settled_rows": payload.get("settled_rows"), "pass": bool(payload) and safe}


def audit(research_root: Path, as_of: datetime | None = None) -> dict:
    as_of = as_of or datetime.now(timezone.utc)
    labels = _rows(research_root / "ghcn_city" / "labels_daily.csv")
    asos = _rows(research_root / "city_asos" / "asos_parsed.csv")
    asos_canonical = _rows(research_root / "city_asos" / "asos_parsed_canonical.csv")
    cli = _rows(research_root / "city_nws_cli" / "daily_climate_cli.csv")
    manifest = _rows(research_root / "forecasts" / "manifest.csv")
    report = {"as_of_utc": as_of.isoformat().replace("+00:00", "Z"), "checks": {}, "cities": {}}
    report["checks"]["labels_duplicate_key"] = {"value": _duplicate_count(labels, ("station_id", "date", "source")), "pass": _duplicate_count(labels, ("station_id", "date", "source")) == 0}
    raw_asos_duplicates = _duplicate_count(asos, ("station", "valid_utc"))
    canonical_duplicates = _duplicate_count(asos_canonical, ("station", "valid_utc"))
    resolution = _rows(research_root / "city_asos" / "asos_duplicate_resolution.csv")
    # Re-deliveries remain visible, but the canonicalized table is the join
    # surface. Pass only when every raw row has a recorded resolution and the
    # canonical natural key is unique.
    report["checks"]["asos_duplicate_key"] = {"raw_value": raw_asos_duplicates, "resolution_rows": len(resolution), "canonical_rows": len(asos_canonical), "pass": bool(asos_canonical) and canonical_duplicates == 0 and len(resolution) == len(asos)}
    report["checks"]["asos_canonical_duplicate_key"] = {"rows": len(asos_canonical), "value": canonical_duplicates, "pass": bool(asos_canonical) and canonical_duplicates == 0}
    report["checks"]["label_availability"] = _timestamp_audit(labels, ("label_available_ts",), as_of)
    report["checks"]["asos_event_time"] = _timestamp_audit(asos, ("valid_utc",), as_of)
    report["checks"]["cli_publication"] = _timestamp_audit(cli, ("publication_time_utc",), as_of)
    manifest_missing_hash = manifest_missing_path = hash_mismatch = 0
    manifest_missing_availability = manifest_invalid_availability = manifest_future_availability = 0
    for row in manifest:
        raw = research_root / "forecasts" / row.get("raw_path", "")
        if not row.get("sha256"): manifest_missing_hash += 1
        if not raw.exists(): manifest_missing_path += 1
        elif row.get("sha256") and hashlib.sha256(raw.read_bytes()).hexdigest() != row["sha256"]: hash_mismatch += 1
        availability = row.get("available_time_utc") or row.get("ingested_at_utc") or row.get("ingested_at")
        if not availability: manifest_missing_availability += 1
        elif parse_utc_iso(availability) is None: manifest_invalid_availability += 1
        elif parse_utc_iso(availability) > as_of: manifest_future_availability += 1
    report["checks"]["forecast_manifest"] = {"rows": len(manifest), "missing_hash": manifest_missing_hash, "missing_raw_path": manifest_missing_path, "hash_mismatch": hash_mismatch, "missing_availability_time": manifest_missing_availability, "invalid_availability_time": manifest_invalid_availability, "future_availability_time": manifest_future_availability, "pass": not any((manifest_missing_hash, manifest_missing_path, hash_mismatch, manifest_missing_availability, manifest_invalid_availability, manifest_future_availability))}
    report["checks"]["forecast_rejections"] = _forecast_rejection_audit(research_root, as_of)
    points = _rows(research_root / "forecasts" / "model_forecasts_points.csv")
    point_missing = point_mismatch = point_missing_hash = 0
    checked = {}
    for row in points:
        raw_text = row.get("raw_path", "")
        path = Path(raw_text)
        if not path.exists(): path = research_root / "forecasts" / raw_text
        if not path.exists(): point_missing += 1; continue
        digest = checked.setdefault(str(path), hashlib.sha256(path.read_bytes()).hexdigest())
        expected = row.get("sha256", "")
        if not expected: point_missing_hash += 1
        elif expected != digest: point_mismatch += 1
    report["checks"]["forecast_point_provenance"] = {"rows": len(points), "source_files": len(checked), "missing_raw_path": point_missing, "missing_hash": point_missing_hash, "hash_mismatch": point_mismatch, "pass": bool(points) and not any((point_missing, point_missing_hash, point_mismatch))}
    report["checks"]["historical_forecast_availability"] = _historical_forecast_audit(research_root)
    report["checks"]["gefs_live_archive"] = _gefs_live_audit(research_root, as_of)
    report["checks"]["rtma_archive"] = _rtma_audit(research_root, as_of)
    report["checks"]["city_asos_archive"] = _city_asos_archive_audit(research_root, as_of)
    report["checks"]["cpc_oni"] = _cpc_audit(research_root)
    report["checks"]["ghcnh_observations"] = _ghcnh_audit(research_root, as_of)
    report["checks"]["ghcnh_daily_extrema"] = _ghcnh_daily_audit(research_root)
    report["checks"]["ghcnh_daily_comparison"] = _ghcnh_daily_compare_audit(research_root)
    report["checks"]["settlement_window_extrema"] = _settlement_window_audit(research_root)
    report["checks"]["weather_index"] = _weather_index_audit(research_root, as_of)
    report["checks"]["awc_metar"] = _awc_metar_audit(research_root, as_of)
    report["checks"]["lamp_archive"] = _lamp_audit(research_root, as_of)
    report["checks"]["lamp_station_forecasts"] = _lamp_station_audit(research_root, as_of)
    report["checks"]["glmp_temperature_archive"] = _glmp_audit(research_root, as_of)
    report["checks"]["glmp_temperature_points"] = _glmp_point_audit(research_root, as_of)
    report["checks"]["kalshi_hourly_contract_archive"] = _kalshi_hourly_audit(research_root, as_of)
    report["checks"]["twc_kalshi_portal_archive"] = _twc_kalshi_audit(research_root, as_of)
    report["checks"]["orderbook_capture"] = _orderbook_capture_audit(research_root)
    report["checks"]["orderbook_rest_reconciliation"] = _orderbook_reconciliation_audit(research_root)
    report["checks"]["kalshi_hourly_contract_normalization"] = _kalshi_hourly_contract_audit(research_root, as_of)
    contracts = _rows(research_root / "kalshi_hourly" / "contracts.csv")
    unresolved_targets = sum("unverified" in row.get("settlement_station_method", "") or row.get("settlement_station_method") in {"", "unresolved"} for row in contracts)
    report["checks"]["settlement_target_resolution"] = {"rows": len(contracts), "unverified_or_unresolved_station": unresolved_targets, "pass": bool(contracts) and unresolved_targets == 0}
    transition_report = research_root / "reports" / "settlement_source_transition.json"
    try:
        transition = json.loads(transition_report.read_text()) if transition_report.exists() else {}
    except (OSError, ValueError, TypeError):
        transition = {}
    report["checks"]["settlement_source_transition"] = {
        "before_rows": transition.get("before_rows", 0),
        "after_rows": transition.get("after_rows", 0),
        "mismatches": len(transition.get("mismatches", [])) if isinstance(transition.get("mismatches", []), list) else 1,
        "notice_present": bool(transition.get("notice_present")),
        "pass": bool(transition.get("pass")),
    }
    report["checks"]["daily_settlement_source_transition"] = _daily_source_transition_audit(research_root)
    report["checks"]["kalshi_hourly_twc_labels"] = _kalshi_twc_label_audit(research_root, as_of)
    report["checks"]["homr_archive"] = _homr_audit(research_root, as_of)
    report["checks"]["ecmwf_archive"] = _ecmwf_audit(research_root, as_of)
    report["checks"]["ecmwf_point_features"] = _ecmwf_point_audit(research_root, as_of)
    report["checks"]["ecmwf_ensemble_points"] = _ecmwf_ensemble_audit(research_root, as_of)
    report["checks"]["prediction_manifest"] = _prediction_manifest_audit(research_root, as_of)
    report["checks"]["provenance_indexes"] = _provenance_index_audit(research_root)
    report["checks"]["live_daily_diagnostic"] = _live_daily_diagnostic_audit(research_root)
    report["checks"]["live_price_comparison_summary"] = _live_price_summary_audit(research_root)
    edge_status_path = research_root / "reports" / "nyc_edge_first_dataset_status.json"
    try:
        edge_status = json.loads(edge_status_path.read_text()) if edge_status_path.exists() else {}
    except (OSError, ValueError, TypeError):
        edge_status = {}
    report["checks"]["edge_first_nyc_dataset"] = {
        "accepted_rows": int(edge_status.get("accepted_rows", 0) or 0),
        "rejected_rows": int(edge_status.get("rejected_rows", 0) or 0),
        "rejection_reasons": edge_status.get("rejection_reasons", {}),
        "pass": bool(edge_status.get("pass")),
    }
    evaluation_path = research_root / "reports" / "edge_first_evaluation.json"
    try:
        evaluation = json.loads(evaluation_path.read_text()) if evaluation_path.exists() else {}
    except (OSError, ValueError, TypeError):
        evaluation = {}
    report["checks"]["edge_first_evaluation"] = {
        "rows": int(evaluation.get("rows", 0) or 0),
        "status": evaluation.get("status", "missing"),
        "metrics_present": evaluation.get("metrics") is not None,
        "pass": evaluation.get("status") == "ready_for_rolling_oos" and bool(evaluation.get("metrics")),
    }
    baseline_path = research_root / "reports" / "nyc_edge_baseline_status.json"
    try:
        baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    except (OSError, ValueError, TypeError):
        baseline = {}
    report["checks"]["edge_first_baseline"] = {
        "prediction_rows": int(baseline.get("prediction_rows", 0) or 0),
        "manifest_rows": int(baseline.get("manifest_rows", 0) or 0),
        "status": baseline.get("status", "missing"),
        "pass": bool(baseline.get("pass")),
    }
    probe_path = research_root / "kalshi_hourly" / "active_probe" / "latest.json"
    try:
        probe = json.loads(probe_path.read_text()) if probe_path.exists() else {}
    except (OSError, ValueError, TypeError):
        probe = {}
    report["checks"]["active_nyc_market_probe"] = {
        "active_market_count": int(probe.get("active_market_count", 0) or 0),
        "retrieved_at_utc": probe.get("retrieved_at_utc", ""),
        "pass": bool(probe.get("pass")),
    }
    report["checks"]["historical_nyc_quote_archive"] = _historical_nyc_quote_audit(research_root, as_of)
    report["checks"]["historical_nyc_quote_archive"]["full_depth_l2"] = False
    for series in ("KXTEMPLAXH", "KXTEMPAUSH"):
        city_root = research_root / "kalshi_hourly" / series.lower() / "historical_quotes"
        report["checks"][f"historical_{series.lower()}_quote_archive"] = _historical_nyc_quote_audit(research_root, as_of, city_root, series)
        report["checks"][f"historical_{series.lower()}_quote_archive"]["full_depth_l2"] = False
    for city in ("nyc", "la", "austin"):
        report["cities"][city] = {"labels": sum(row.get("city") == city for row in labels), "asos": sum(row.get("station") == {"nyc": "NYC", "la": "LAX", "austin": "AUS"}[city] for row in asos), "cli": sum(row.get("city") == city for row in cli)}
    report["pass"] = all(value.get("pass", True) for value in report["checks"].values())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "weather_research")
    parser.add_argument("--as-of", help="UTC ISO timestamp for the audit clock")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    as_of = parse_utc_iso(args.as_of) if args.as_of else None
    text = json.dumps(audit(args.research_root, as_of), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text)
    else: print(text, end="")


if __name__ == "__main__": main()
