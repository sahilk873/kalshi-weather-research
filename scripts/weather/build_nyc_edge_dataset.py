"""Build the strict NYC PIT feature/label dataset for the edge-first sprint.

Rows are admitted only when the feature builder has already proven source
availability at decision time and an exact settlement label is present. Every
other contract is retained in the rejection CSV with a specific reason.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


OUTPUT_FIELDS = ["market_ticker", "event_ticker", "target_time_utc", "decision_ts", "threshold_f", "comparison", "rules_hash", "settlement_station_method", "kalshi_result", "source_temperature_f", "source_valid_utc", "label_available_ts", "features_json", "source_run_ids", "observation_ids"]


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _dt(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def build(contracts_path: Path, labels_path: Path, features_path: Path, feature_rejections_path: Path) -> tuple[list[dict], list[dict]]:
    contracts = {row.get("market_ticker", ""): row for row in _rows(contracts_path)}
    labels = {row.get("market_ticker", ""): row for row in _rows(labels_path)}
    features = {row.get("market_ticker", ""): row for row in _rows(features_path)}
    rejections = {row.get("market_ticker", ""): row.get("reason", "feature_rejected") for row in _rows(feature_rejections_path)}
    accepted: list[dict] = []
    rejected: list[dict] = []
    for ticker, contract in contracts.items():
        label = labels.get(ticker, {})
        feature = features.get(ticker, {})
        reason = ""
        reason_codes: list[str] = []
        if not feature:
            reason_codes.append(rejections.get(ticker, "no_valid_pit_features"))
        if not label.get("kalshi_result"):
            reason_codes.append("missing_settled_binary_label")
        decision = _dt(feature.get("decision_ts") or contract.get("decision_ts") or contract.get("close_time") or contract.get("open_time"))
        label_available = _dt(label.get("label_available_ts") or label.get("source_receipt_utc"))
        if label_available is None:
            reason_codes.append("missing_label_availability")
        elif decision is None:
            reason_codes.append("invalid_decision_clock")
        source_valid = _dt(label.get("source_valid_utc"))
        target = _dt(contract.get("target_time_utc"))
        if source_valid is None or target is None or source_valid != target:
            reason_codes.append("invalid_exact_settlement_time")
        elif label_available is not None and label_available < target:
            reason_codes.append("label_available_before_target")
        if "unverified" in contract.get("settlement_station_method", "") or contract.get("settlement_station_method", "") in {"", "unresolved"}:
            reason_codes.append("unverified_settlement_station")
        if reason_codes:
            reason = reason_codes[0]
            rejected.append({"market_ticker": ticker, "reason": reason, "reason_codes": ";".join(dict.fromkeys(reason_codes))})
            continue
        accepted.append({field: feature.get(field, "") for field in OUTPUT_FIELDS} | {"event_ticker": contract.get("event_ticker", ""), "target_time_utc": contract.get("target_time_utc", ""), "threshold_f": contract.get("threshold_f", ""), "comparison": contract.get("comparison", ""), "rules_hash": contract.get("rules_hash", ""), "settlement_station_method": contract.get("settlement_station_method", ""), "kalshi_result": label.get("kalshi_result", ""), "source_temperature_f": label.get("source_temperature_f", ""), "source_valid_utc": label.get("source_valid_utc", ""), "label_available_ts": label.get("label_available_ts", "")})
    return accepted, rejected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path("data/weather_research")
    parser.add_argument("--contracts", type=Path, default=root / "kalshi_hourly/contracts.csv")
    parser.add_argument("--labels", type=Path, default=root / "kalshi_hourly/twc_labels.csv")
    parser.add_argument("--features", type=Path, default=root / "reports/decision_features.csv")
    parser.add_argument("--feature-rejections", type=Path, default=root / "reports/decision_feature_rejections.csv")
    parser.add_argument("--output", type=Path, default=root / "reports/nyc_edge_first_dataset.csv")
    parser.add_argument("--rejections-output", type=Path, default=root / "reports/nyc_edge_first_rejections.csv")
    parser.add_argument("--status-output", type=Path, default=root / "reports/nyc_edge_first_dataset_status.json")
    args = parser.parse_args()
    accepted, rejected = build(args.contracts, args.labels, args.features, args.feature_rejections)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS); writer.writeheader(); writer.writerows(accepted)
    with args.rejections_output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["market_ticker", "reason", "reason_codes"]); writer.writeheader(); writer.writerows(rejected)
    status = {"version": "edge-first-nyc-dataset-v2", "contracts": len(accepted) + len(rejected), "accepted_rows": len(accepted), "rejected_rows": len(rejected), "non_empty": bool(accepted), "pass": bool(accepted), "rejection_reasons": {}, "rejection_reason_codes": {}}
    for row in rejected:
        status["rejection_reasons"][row["reason"]] = status["rejection_reasons"].get(row["reason"], 0) + 1
        for code in row.get("reason_codes", "").split(";"):
            if code:
                status["rejection_reason_codes"][code] = status["rejection_reason_codes"].get(code, 0) + 1
    args.status_output.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"accepted": len(accepted), "rejected": len(rejected), "pass": status["pass"]}))


if __name__ == "__main__":
    main()
