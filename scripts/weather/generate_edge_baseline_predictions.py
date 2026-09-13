"""Generate only PIT-valid NYC persistence predictions and manifests."""
from __future__ import annotations

import argparse, csv, json, math
from pathlib import Path

from prediction_manifest import build_manifest, write_manifest, read_index


def _probability(row: dict, sigma_f: float = 2.0) -> float | None:
    try:
        threshold = float(row["threshold_f"])
        features = json.loads(row["features_json"])
        latest = features.get("temperature_f")
        if latest in (None, "") and features.get("temperature_c") not in (None, ""):
            latest = float(features["temperature_c"]) * 9.0 / 5.0 + 32.0
        mean = float(latest)
        comparison = row["comparison"].strip().lower()
        if not math.isfinite(mean) or comparison not in {"above", "below"}:
            return None
        z = (threshold - mean) / (sigma_f * math.sqrt(2.0))
        cdf = 0.5 * (1.0 + math.erf(z))
        return max(0.0, min(1.0, 1.0 - cdf if comparison == "above" else cdf))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, ZeroDivisionError):
        return None


def generate(dataset: Path, contracts: Path, output: Path, manifest_dir: Path,
             code_commit: str = "HEAD", source_index: Path | None = None,
             observation_index: Path | None = None) -> dict:
    with dataset.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"version": "edge-first-persistence-v1", "input_rows": 0, "prediction_rows": 0, "manifest_rows": 0, "status": "not_evaluable", "reason": "empty_admitted_pit_dataset", "pass": False}
    with contracts.open(newline="") as handle:
        contract_rows = {row.get("market_ticker", ""): row for row in csv.DictReader(handle)}
    source_map = read_index(source_index, "source_run_id") if source_index else None
    observation_map = read_index(observation_index, "observation_id") if observation_index else None
    predictions, valid_rows, rejected = [], [], []
    for row in rows:
        ticker = row.get("market_ticker", "")
        if ticker not in contract_rows:
            rejected.append({"market_ticker": ticker, "reason": "missing_contract_terms"})
            continue
        if source_map is None or observation_map is None:
            rejected.append({"market_ticker": ticker, "reason": "missing_provenance_index"})
            continue
        if row.get("settlement_station_method", "").find("unverified") >= 0:
            rejected.append({"market_ticker": ticker, "reason": "unverified_settlement_station"}); continue
        probability = _probability(row)
        if probability is None or not row.get("source_run_ids") or not row.get("observation_ids"):
            rejected.append({"market_ticker": ticker, "reason": "missing_baseline_provenance"}); continue
        predictions.append({"market_ticker": row["market_ticker"], "target_time_utc": row["target_time_utc"], "decision_ts": row["decision_ts"], "model_version": "persistence_gaussian_v1", "prediction": f"{probability:.8f}"})
        valid_rows.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["market_ticker", "target_time_utc", "decision_ts", "model_version", "prediction"]); writer.writeheader(); writer.writerows(predictions)
    manifest_count = 0
    for row, pred in zip(valid_rows, predictions):
        manifest = build_manifest(decision_ts=pred["decision_ts"], feature_version="report2-pit-v1", model_version=pred["model_version"], calibrator_version="none", source_run_ids=json.loads(row["source_run_ids"]), observation_ids=json.loads(row["observation_ids"]), rules_hash=row["rules_hash"], code_commit=code_commit, prediction=float(pred["prediction"]), market_ticker=pred["market_ticker"], target_time_utc=pred["target_time_utc"])
        write_manifest(manifest_dir, manifest, contracts=contract_rows,
                       source_index=source_map, observation_index=observation_map)
        manifest_count += 1
    return {"version": "edge-first-persistence-v1", "input_rows": len(rows), "prediction_rows": len(predictions), "manifest_rows": manifest_count, "rejected_rows": len(rejected), "status": "complete" if predictions else "not_evaluable", "rejections": rejected, "pass": bool(predictions) and manifest_count == len(predictions)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); root = Path("data/weather_research/reports")
    parser.add_argument("--dataset", type=Path, default=root / "nyc_edge_first_dataset.csv"); parser.add_argument("--contracts", type=Path, default=Path("data/weather_research/kalshi_hourly/contracts.csv")); parser.add_argument("--output", type=Path, default=root / "nyc_edge_baseline_predictions.csv"); parser.add_argument("--manifest-dir", type=Path, default=Path("data/weather_research/predictions/model_version=persistence_gaussian_v1")); parser.add_argument("--status", type=Path, default=root / "nyc_edge_baseline_status.json"); parser.add_argument("--source-index", type=Path, default=root / "provenance_indexes" / "source_index.csv"); parser.add_argument("--observation-index", type=Path, default=root / "provenance_indexes" / "observation_index.csv")
    args = parser.parse_args(); result = generate(args.dataset, args.contracts, args.output, args.manifest_dir, source_index=args.source_index, observation_index=args.observation_index); args.status.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n"); print(json.dumps({"predictions": result.get("prediction_rows", 0), "manifests": result.get("manifest_rows", 0), "pass": result["pass"]}))


if __name__ == "__main__": main()
