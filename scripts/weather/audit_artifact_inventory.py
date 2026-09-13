"""Emit current row counts for the documented research artifacts."""
from __future__ import annotations
import argparse, csv, json, sqlite3
from datetime import datetime, timezone
from pathlib import Path

FILES = {
    # Core PHX/LV and auxiliary-city normalized sources.
    "ghcn_labels": "ghcn/labels_daily.csv",
    "ghcnh_observations_2020_2026": "ghcnh/observations_2020_2026.csv",
    "ghcnh_daily_extrema_2020_2026": "ghcnh/daily_extrema_2020_2026.csv",
    "settlement_window_extrema_2020_2026": "ghcnh/settlement_window_extrema_2020_2026.csv",
    "ghcn_city_labels": "ghcn_city/labels_daily.csv",
    "asos": "iem/asos_parsed.csv",
    "city_asos": "city_asos/asos_parsed_canonical.csv",
    "nearby_asos": "nearby_asos/nearby_asos_parsed.csv",
    "city_nearby_asos": "city_nearby_asos/nearby_asos_parsed.csv",
    "phx_lv_asos_backfill": "iem_backfill/asos_parsed.csv",
    "solar_phx_lv": "solar/solar_features.csv",
    "solar_city": "solar_city/solar_features.csv",
    "intraday_state_backfill": "reports/phx_lv_intraday_state_backfill.csv",
    "intraday_state": "derived_intraday_state.csv",
    "city_intraday_state": "derived_intraday_state_city/derived_intraday_state.csv",
    "nws_cli": "nws_cli/daily_climate_cli.csv",
    "city_nws_cli": "city_nws_cli/daily_climate_cli.csv",
    "forecast_manifest": "forecasts/manifest.csv",
    "forecast_points": "forecasts/model_forecasts_points.csv",
    "forecast_rejections": "forecasts/rejections.csv",
    "ecmwf_points": "ecmwf/point_features.csv",
    "ecmwf_ensemble_points": "ecmwf/ensemble_points.csv",
    "ecmwf_ensemble_summaries": "ecmwf/ensemble_summaries.csv",
    "rtma_points": "rtma/rtma_point_features.csv",
    "rtma_manifest": "rtma/manifest.csv",
    "cpc_oni": "cpc/oni.csv",
    "homr_station_history": "homr/station_history.csv",
    "kalshi_markets": "kalshi/markets.csv",
    "kalshi_outcomes": "kalshi/contract_outcomes.csv",
    "kalshi_trades": "kalshi/trades.csv",
    "kalshi_hourly_candles": "kalshi/candlesticks_hourly.csv",
    "kalshi_daily_candles": "kalshi/candlesticks_daily.csv",
    "city_markets": "kalshi_historical_city/markets.csv",
    "city_trades": "kalshi_historical_city/trades.csv",
    "city_candles": "kalshi_historical_city/candles.csv",
    "awc_metar": "awc/metar.csv",
    "kalshi_hourly_events": "kalshi_hourly/events.csv",
    "kalshi_hourly_markets": "kalshi_hourly/markets.csv",
    "twc_kalshi_hourly": "twc_kalshi/hourly.csv",
    "twc_kalshi_daily": "twc_kalshi/daily.csv",
    "kalshi_hourly_contracts": "kalshi_hourly/contracts.csv",
    "kalshi_hourly_twc_labels": "kalshi_hourly/twc_labels.csv",
}

UNIQUE_KEYS = {
    "city_candles": ("ticker", "end_period_ts", "period_minutes"),
    "nyc_historical_quote_candles": ("market_ticker", "end_period_ts", "period_interval"),
    "la_historical_quote_candles": ("market_ticker", "end_period_ts", "period_interval"),
    "austin_historical_quote_candles": ("market_ticker", "end_period_ts", "period_interval"),
}

def count(path: Path, key: tuple[str, ...] | None = None) -> int:
    if not path.exists(): return 0
    with path.open(newline="") as fh:
        rows = csv.DictReader(fh)
        if key is None:
            return sum(1 for _ in rows)
        return len({tuple(row.get(column, "") for column in key) for row in rows})

def file_count(directory: Path, suffix: str) -> int:
    return len(list(directory.glob(f"*{suffix}"))) if directory.exists() else 0


def quote_manifest_counts(directory: Path) -> tuple[int, int, int]:
    """Return indexed raw payloads, quarantined payloads, and failed markets."""
    indexed = quarantined = failed = 0
    manifest = directory / "manifest.json"
    try:
        payload = json.loads(manifest.read_text())
        indexed = int(payload.get("raw_payloads", 0) or 0)
        failed = int(payload.get("failed_markets", 0) or 0)
    except (OSError, ValueError, TypeError):
        pass
    quarantine = directory / "raw_quarantine_manifest.jsonl"
    if quarantine.exists():
        quarantined = sum(1 for line in quarantine.read_text().splitlines() if line.strip())
    return indexed, quarantined, failed

def parquet_count(path: Path) -> int:
    try:
        import pyarrow.parquet as pq
        return pq.read_metadata(path).num_rows if path.exists() else 0
    except (ImportError, OSError):
        return 0

def inventory(root: Path) -> dict:
    result = {name: count(root / rel, UNIQUE_KEYS.get(name)) for name, rel in FILES.items()}
    result["ghcnh_vs_ghcn_daily_report"] = int((root / "reports" / "ghcnh_vs_ghcn_daily.json").exists())
    result["weather_index_manifest"] = int((root / "weather_index" / "manifest.json").exists())
    result["weather_index_nyc_timeseries"] = count(root / "weather_index" / "nyc_timeseries.csv")
    result["live_schedule"] = int((root / "reports" / "live_schedule.json").exists())
    result["lamp_manifest"] = int((root / "lamp" / "manifest.json").exists())
    result["lamp_station_forecasts"] = count(root / "lamp" / "station_forecasts.csv")
    result["gefs_historical_quarantine"] = count(root / "gefs" / "historical_raw" / "quarantine.csv")
    result["glmp_temperature_manifest"] = int((root / "glmp" / "manifest.json").exists())
    result["glmp_temperature_points"] = count(root / "glmp" / "point_features.csv")
    result["decision_features"] = count(root / "reports" / "decision_features.csv")
    result["decision_feature_rejections"] = count(root / "reports" / "decision_feature_rejections.csv")
    result["model_runs"] = count(root / "reports" / "model_runs.csv")
    result["model_ladder"] = int((root / "reports" / "model_ladder.json").exists())
    result["training_readiness"] = int((root / "reports" / "training_readiness.json").exists())
    result["deployment_gate"] = int((root / "reports" / "deployment_gate.json").exists())
    result["forecast_completeness"] = int((root / "reports" / "forecast_completeness.json").exists())
    result["settlement_target_audit"] = int((root / "reports" / "settlement_target_audit.json").exists())
    result["settlement_source_transition"] = int((root / "reports" / "settlement_source_transition.json").exists())
    result["kalshi_contract_terms"] = file_count(root / "kalshi_hourly" / "terms", ".pdf")
    result["nyc_edge_first_dataset"] = count(root / "reports" / "nyc_edge_first_dataset.csv")
    result["nyc_edge_first_rejections"] = count(root / "reports" / "nyc_edge_first_rejections.csv")
    result["edge_first_evaluation"] = int((root / "reports" / "edge_first_evaluation.json").exists())
    result["edge_baseline_predictions"] = count(root / "reports" / "nyc_edge_baseline_predictions.csv")
    result["edge_baseline_status"] = int((root / "reports" / "nyc_edge_baseline_status.json").exists())
    result["live_daily_diagnostic_predictions"] = count(root / "reports" / "live_daily_diagnostic_predictions_20260913.csv")
    result["live_daily_diagnostic_rejections"] = count(root / "reports" / "live_daily_diagnostic_rejections_20260913.csv")
    result["live_price_comparison_summary"] = int((root / "reports" / "live_price_comparison_summary.json").exists())
    result["active_nyc_market_probe"] = int((root / "kalshi_hourly" / "active_probe" / "latest.json").exists())
    result["active_city_market_probe"] = int((root / "kalshi_city" / "active_probe" / "latest.json").exists())
    result["active_quote_snapshots"] = file_count(root / "kalshi_city" / "active_probe", "quotes_*.csv")
    result["intraday_city_readiness"] = int((root / "reports" / "intraday_city_readiness.json").exists())
    result["intraday_capture_status"] = int((root / "reports" / "intraday_capture_status.json").exists())
    result["intraday_edge_pipeline_status"] = int((root / "reports" / "intraday_edge_pipeline_status.json").exists())
    result["settlement_locations"] = int((root / "settlement_locations.json").exists())
    quote_archives = [(root / "kalshi_hourly" / "historical_quotes", "nyc"),
                      (root / "kalshi_hourly" / "kxtemplaxh" / "historical_quotes", "la"),
                      (root / "kalshi_hourly" / "kxtempaush" / "historical_quotes", "austin")]
    for quote_root, prefix in quote_archives:
        result[f"{prefix}_historical_quote_candles"] = count(quote_root / "candles_hourly.csv", UNIQUE_KEYS[f"{prefix}_historical_quote_candles"])
        result[f"{prefix}_historical_quote_trades"] = count(quote_root / "trades.csv")
        result[f"{prefix}_historical_quote_market_metadata"] = count(quote_root / "market_metadata.csv")
        indexed, quarantined, failed = quote_manifest_counts(quote_root)
        result[f"{prefix}_historical_quote_raw_payloads"] = indexed
        result[f"{prefix}_historical_quote_quarantined_payloads"] = quarantined
        result[f"{prefix}_historical_quote_failed_markets"] = failed
    result["historical_quote_market_metadata"] = sum(result[f"{prefix}_historical_quote_market_metadata"] for _, prefix in quote_archives)
    result["historical_quote_candles"] = sum(result[f"{prefix}_historical_quote_candles"] for _, prefix in quote_archives)
    result["historical_quote_trades"] = sum(result[f"{prefix}_historical_quote_trades"] for _, prefix in quote_archives)
    result["orderbook_capture_audits"] = len(list((root / "reports").glob("orderbook_capture_*.json"))) if (root / "reports").exists() else 0
    result["daily_source_transition_audits"] = len(list((root / "reports").glob("daily_source_transition_*.json"))) if (root / "reports").exists() else 0
    result["gefs_feature_rows"] = parquet_count(root / "gefs" / "gefs_features.parquet")
    ghcnh_manifest = root / "ghcnh" / "manifest.json"
    if ghcnh_manifest.exists():
        try:
            payload = json.loads(ghcnh_manifest.read_text())
            result["ghcnh_tail_objects"] = len(payload.get("rows", []))
            result["ghcnh_partial_objects"] = sum(bool(row.get("partial")) for row in payload.get("rows", []))
        except (OSError, ValueError, TypeError):
            result["ghcnh_tail_objects"] = 0
            result["ghcnh_partial_objects"] = 0
    year_manifests = sorted((root / "ghcnh" / "by_year").glob("*/manifest.json"))
    result["ghcnh_year_objects"] = 0
    for manifest in year_manifests:
        try:
            result["ghcnh_year_objects"] += len(json.loads(manifest.read_text()).get("rows", []))
        except (OSError, ValueError, TypeError):
            continue
    homr_manifest = root / "homr" / "manifest.json"
    try:
        result["homr_station_objects"] = len(json.loads(homr_manifest.read_text()).get("rows", []))
    except (OSError, ValueError, TypeError):
        result["homr_station_objects"] = 0
    ecmwf_manifest = root / "ecmwf" / "manifest.json"
    try:
        result["ecmwf_forecast_objects"] = len(json.loads(ecmwf_manifest.read_text()).get("rows", []))
    except (OSError, ValueError, TypeError):
        result["ecmwf_forecast_objects"] = 0
    prediction_dir = root / "predictions"
    result["prediction_manifests"] = 0
    if prediction_dir.is_dir():
        for path in sorted(prediction_dir.glob("**/*.json")):
            try:
                if isinstance(json.loads(path.read_text()), dict):
                    result["prediction_manifests"] += 1
            except (OSError, ValueError, TypeError):
                continue
    db = root / "kalshi_weather.sqlite"
    if db.exists():
        con = sqlite3.connect(db)
        for table in (
            "observations", "awc_metar", "glmp_temperature_points", "nearby_observations", "daily_results", "derived_intraday_state",
            "solar_features", "nws_cli_daily", "city_observations", "city_daily_labels",
            "city_nws_cli", "city_kalshi_markets", "city_kalshi_trades", "city_kalshi_candles",
            "kalshi_markets", "contract_outcomes", "kalshi_prices", "model_forecasts",
            "model_forecast_points", "rtma_point_features", "cpc_oni", "ghcnh_observations",
            "ghcnh_daily_extrema", "settlement_window_extrema", "homr_station_history", "ecmwf_point_features",
            "ecmwf_ensemble_points", "kalshi_hourly_events", "kalshi_hourly_markets", "twc_kalshi_hourly", "twc_kalshi_daily", "kalshi_hourly_contracts", "kalshi_hourly_twc_labels",
            "historical_quote_market_metadata", "historical_quote_candles", "historical_quote_trades",
            "prediction_manifests", "decision_features", "paper_orders", "paper_fills", "paper_settlements", "orderbook_events_live", "market_trade_events", "settlement_temperature", "surface_observation", "model_runs",
            "live_market_quotes",
        ):
            try:
                result["sqlite_" + table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                result["sqlite_" + table] = 0
        con.close()
    pairs = {
        "asos": "sqlite_observations", "awc_metar": "sqlite_awc_metar", "glmp_temperature_points": "sqlite_glmp_temperature_points", "nearby_asos": "sqlite_nearby_observations",
        "ghcn_labels": "sqlite_daily_results", "intraday_state": "sqlite_derived_intraday_state",
        "ghcnh_observations_2020_2026": "sqlite_ghcnh_observations",
        "ghcnh_daily_extrema_2020_2026": "sqlite_ghcnh_daily_extrema",
        "settlement_window_extrema_2020_2026": "sqlite_settlement_window_extrema",
        "homr_station_history": "sqlite_homr_station_history",
        "solar_phx_lv": "sqlite_solar_features", "nws_cli": "sqlite_nws_cli_daily",
        "city_asos": "sqlite_city_observations", "ghcn_city_labels": "sqlite_city_daily_labels",
        "city_nws_cli": "sqlite_city_nws_cli", "city_markets": "sqlite_city_kalshi_markets",
        "city_trades": "sqlite_city_kalshi_trades", "city_candles": "sqlite_city_kalshi_candles",
        "kalshi_markets": "sqlite_kalshi_markets", "kalshi_outcomes": "sqlite_contract_outcomes",
        "kalshi_trades": "sqlite_kalshi_prices", "forecast_manifest": "sqlite_model_forecasts",
        "forecast_points": "sqlite_model_forecast_points", "ecmwf_points": "sqlite_ecmwf_point_features", "ecmwf_ensemble_points": "sqlite_ecmwf_ensemble_points", "rtma_points": "sqlite_rtma_point_features",
        "cpc_oni": "sqlite_cpc_oni",
        "model_runs": "sqlite_model_runs",
        "kalshi_hourly_events": "sqlite_kalshi_hourly_events",
        "kalshi_hourly_markets": "sqlite_kalshi_hourly_markets",
        "twc_kalshi_hourly": "sqlite_twc_kalshi_hourly",
        "twc_kalshi_daily": "sqlite_twc_kalshi_daily",
        "kalshi_hourly_contracts": "sqlite_kalshi_hourly_contracts",
        "kalshi_hourly_twc_labels": "sqlite_kalshi_hourly_twc_labels",
        "historical_quote_market_metadata": "sqlite_historical_quote_market_metadata",
        "historical_quote_candles": "sqlite_historical_quote_candles",
        "historical_quote_trades": "sqlite_historical_quote_trades",
        "prediction_manifests": "sqlite_prediction_manifests",
    }
    result["sqlite_count_mismatches"] = [name for name, table_count in pairs.items() if table_count in result and result[name] != result[table_count]]
    return result

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--research-root", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "weather_research"); p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    data = {"generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "counts": inventory(a.research_root)}; a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n"); print(json.dumps(data, sort_keys=True))
if __name__ == "__main__": main()
