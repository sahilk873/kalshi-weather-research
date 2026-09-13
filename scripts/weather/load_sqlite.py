"""Create and load a portable SQLite research database from generated CSVs.

Rows are idempotently replaced using documented natural keys. Raw payloads
remain files; SQLite is a query layer, not the source of truth.

Loaded tables mirror the normalized CSVs:
- stations (PHX/LAS settlement proxies)
- observations (settlement-station METAR rows, key station+valid_utc)
- ghcnh_observations (GHCNh yearly station rows with raw-file provenance)
- homr_station_history (HOMR identifiers, relocations, and remarks)
- ecmwf_point_features (decoded ECMWF point guidance with raw provenance)
- ecmwf_ensemble_points (member-level ECMWF point guidance)
- nearby_observations (six non-settlement sites, key station+valid_utc)
- daily_results (GHCN official labels, key station+date+source)
- derived_intraday_state (per-observation PIT features)
- solar_features (deterministic geometry per city+date)
- contract_outcomes (per-market bucket settlement outcome)
- kalshi_markets / kalshi_prices (metadata, excluded price/quantity so far)
- nws_cli_daily (revision-preserving CLI issuances)
- ghcn_stations_catalog / asos_stations_catalog (nearby inventories)
- model_forecasts (forecasts/manifest.csv provenance)
- city_observations, city_daily_labels, city_nws_cli, and city_kalshi_* are
  auxiliary NYC/Los Angeles/Austin research tables; they are not settlement
  certification for the hourly city lines.
- decision_features, prediction_manifests, paper_orders, paper_fills,
  paper_settlements, orderbook_events_live, and market_trade_events are the
  report-2 trading-state query schemas; they remain empty until provenance-
  complete predictions or prospective telemetry exists.

Empty CSV cell values are stored as NULL (not '') so range queries work.
"""
from __future__ import annotations
import argparse, csv, sqlite3, sys
from pathlib import Path
_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from common import ensure_runtime_dirs  # noqa: E402

DDL = """
CREATE TABLE IF NOT EXISTS stations(station_id TEXT PRIMARY KEY,icao TEXT,city TEXT,latitude REAL,longitude REAL,timezone TEXT,role TEXT);
CREATE TABLE IF NOT EXISTS observations(station TEXT,valid_utc TEXT,local_date TEXT,raw_metar TEXT,temperature_f REAL,dewpoint_f REAL,wind_kt REAL,wind_dir REAL,gust_kt REAL,pressure_hpa REAL,visibility_mi REAL,cloud1 TEXT,weather TEXT,PRIMARY KEY(station,valid_utc));
CREATE TABLE IF NOT EXISTS awc_metar(station TEXT,valid_utc TEXT,receipt_utc TEXT,temperature_c REAL,dewpoint_c REAL,wind_dir_degrees REAL,wind_speed_kt REAL,raw_metar TEXT,source_url TEXT,raw_sha256 TEXT,PRIMARY KEY(station,valid_utc,raw_sha256));
CREATE TABLE IF NOT EXISTS glmp_temperature_points(model TEXT,city TEXT,initialization_time_utc TEXT,valid_time_utc TEXT,lead_hours INTEGER,source_receipt_time TEXT,variable TEXT,value REAL,unit TEXT,grid_latitude REAL,grid_longitude REAL,raw_path TEXT,sha256 TEXT,message_index INTEGER,PRIMARY KEY(model,city,initialization_time_utc,lead_hours,raw_path,message_index));
CREATE TABLE IF NOT EXISTS ghcnh_observations(station TEXT,station_name TEXT,valid_utc TEXT,latitude REAL,longitude REAL,elevation_m REAL,temperature_f REAL,dewpoint_f REAL,temperature_quality_code TEXT,temperature_report_type TEXT,raw_path TEXT,sha256 TEXT,source_receipt_time TEXT,PRIMARY KEY(station,valid_utc,raw_path));
CREATE TABLE IF NOT EXISTS homr_station_history(city TEXT,station TEXT,record_type TEXT,id_type TEXT,identifier TEXT,begin_date TEXT,end_date TEXT,detail TEXT);
CREATE TABLE IF NOT EXISTS ghcnh_daily_extrema(station TEXT,local_date TEXT,timezone TEXT,observation_count INTEGER,tmax_f REAL,tmax_utc TEXT,tmin_f REAL,tmin_utc TEXT,raw_paths TEXT,raw_hashes TEXT,PRIMARY KEY(station,local_date));
CREATE TABLE IF NOT EXISTS settlement_window_extrema(city TEXT,outcome_local_date TEXT,window_start_utc TEXT,window_end_utc TEXT,observation_count INTEGER,tmax_f REAL,tmax_utc TEXT,tmin_f REAL,tmin_utc TEXT,raw_hashes TEXT,PRIMARY KEY(city,outcome_local_date));
CREATE TABLE IF NOT EXISTS ecmwf_point_features(model TEXT,city TEXT,initialization_time_utc TEXT,valid_time_utc TEXT,lead_hours INTEGER,source_receipt_time TEXT,variable TEXT,value REAL,unit TEXT,grid_latitude REAL,grid_longitude REAL,raw_path TEXT,sha256 TEXT,message_index INTEGER,PRIMARY KEY(model,city,initialization_time_utc,lead_hours,variable,raw_path,message_index));
CREATE TABLE IF NOT EXISTS ecmwf_ensemble_points(model TEXT,city TEXT,member_id TEXT,initialization_time_utc TEXT,valid_time_utc TEXT,lead_hours INTEGER,source_receipt_time TEXT,variable TEXT,value REAL,unit TEXT,grid_latitude REAL,grid_longitude REAL,raw_path TEXT,sha256 TEXT,message_index INTEGER,PRIMARY KEY(model,city,member_id,initialization_time_utc,lead_hours,variable,raw_path,message_index));
CREATE TABLE IF NOT EXISTS nearby_observations(station TEXT,valid_utc TEXT,city TEXT,local_date TEXT,raw_metar TEXT,temperature_f REAL,dewpoint_f REAL,wind_kt REAL,wind_dir REAL,gust_kt REAL,pressure_hpa REAL,visibility_mi REAL,cloud1 TEXT,weather TEXT,PRIMARY KEY(station,valid_utc));
CREATE TABLE IF NOT EXISTS daily_results(station TEXT,date TEXT,official_high_f REAL,official_low_f REAL,source TEXT,publication_time TEXT,PRIMARY KEY(station,date,source));
CREATE TABLE IF NOT EXISTS derived_intraday_state(station TEXT,valid_utc TEXT,local_date TEXT,current_temperature_f REAL,observed_high_so_far_f REAL,observed_low_so_far_f REAL,feature_asof_utc TEXT,PRIMARY KEY(station,valid_utc));
CREATE TABLE IF NOT EXISTS solar_features(city TEXT,date TEXT,lat REAL,lon REAL,solar_noon_utc TEXT,sunrise_utc TEXT,sunset_utc TEXT,sunrise_local TEXT,sunset_local TEXT,daylength_min REAL,declination_deg REAL,eqtime_min REAL,PRIMARY KEY(city,date));
CREATE TABLE IF NOT EXISTS contract_outcomes(outcome_local_date TEXT,city TEXT,temp_type TEXT,event_ticker TEXT,market_ticker TEXT PRIMARY KEY,bucket_floor_f REAL,bucket_ceil_f REAL,bucket_label TEXT,status TEXT,settled_yes TEXT,settlement_ts TEXT,settlement_source_name TEXT,settlement_source_url TEXT);
CREATE TABLE IF NOT EXISTS kalshi_markets(market_ticker TEXT PRIMARY KEY,event_ticker TEXT,city TEXT,temp_type TEXT,outcome_local_date TEXT,bucket_floor_f REAL,bucket_ceil_f REAL,status TEXT,result TEXT,open_time TEXT,close_time TEXT,settlement_ts TEXT);
CREATE TABLE IF NOT EXISTS kalshi_prices(trade_id TEXT PRIMARY KEY,market_ticker TEXT,created_time TEXT,yes_price REAL,no_price REAL,quantity REAL);
CREATE TABLE IF NOT EXISTS nws_cli_daily(city TEXT,station TEXT,pil TEXT,climate_date TEXT,official_daily_high_f REAL,official_daily_low_f REAL,publication_time_utc TEXT,revision_timestamp_utc TEXT,source TEXT,source_url TEXT,raw_filename TEXT,PRIMARY KEY(city,raw_filename));
CREATE TABLE IF NOT EXISTS ghcn_stations_catalog(city TEXT,distance_km REAL,station_id TEXT,name TEXT,state TEXT,lat REAL,lon REAL,elevation_m REAL,tmax_range TEXT,tmin_range TEXT,PRIMARY KEY(city,station_id));
CREATE TABLE IF NOT EXISTS asos_stations_catalog(city TEXT,distance_km REAL,sid TEXT,sname TEXT,state TEXT,lat REAL,lon REAL,elevation_m REAL,tzname TEXT,archive_begin TEXT,archive_end TEXT,ncei91 TEXT,online TEXT,PRIMARY KEY(city,sid));
CREATE TABLE IF NOT EXISTS model_forecasts(model TEXT,initialization_time_utc TEXT,valid_time_utc TEXT,lead_hours INTEGER,uri TEXT,raw_path TEXT,sha256 TEXT,ingested_at TEXT,available_time_utc TEXT,available_time_method TEXT,PRIMARY KEY(model,initialization_time_utc,lead_hours,uri));
CREATE TABLE IF NOT EXISTS model_forecast_points(model TEXT,city TEXT,initialization_time_utc TEXT,valid_time_utc TEXT,lead_hours INTEGER,source_receipt_time TEXT,variable TEXT,value REAL,unit TEXT,grid_latitude REAL,grid_longitude REAL,raw_path TEXT,sha256 TEXT,message_index INTEGER,PRIMARY KEY(model,city,initialization_time_utc,lead_hours,variable,raw_path,message_index));
CREATE TABLE IF NOT EXISTS rtma_point_features(city TEXT,variable TEXT,value REAL,unit TEXT,valid_time_utc TEXT,grid_latitude REAL,grid_longitude REAL,raw_path TEXT,sha256 TEXT,PRIMARY KEY(city,variable,valid_time_utc,raw_path));
CREATE TABLE IF NOT EXISTS cpc_oni(season TEXT,year INTEGER,nino34_3mo_mean_c REAL,oni_anomaly_c REAL,source_url TEXT,retrieved_at_utc TEXT,PRIMARY KEY(season,year));
CREATE TABLE IF NOT EXISTS gefs_members(forecast_run_time TEXT,valid_time TEXT,city TEXT,city_key TEXT,latitude REAL,longitude REAL,timezone TEXT,model TEXT,member_id TEXT,variable TEXT,value REAL,retrieved_at TEXT,PRIMARY KEY(forecast_run_time,valid_time,city_key,model,member_id,variable));
CREATE TABLE IF NOT EXISTS gefs_features(forecast_run_time TEXT,valid_time TEXT,city_key TEXT,model TEXT,city TEXT,variable TEXT,member_count INTEGER,ensemble_mean REAL,ensemble_spread REAL,p10 REAL,p25 REAL,median REAL,p75 REAL,p90 REAL,prob_ge_78 REAL,prob_ge_80 REAL,prob_ge_82 REAL,prob_ge_85 REAL,prob_ge_90 REAL,PRIMARY KEY(forecast_run_time,valid_time,city_key,model,variable));
CREATE TABLE IF NOT EXISTS gefs_calibration(model TEXT,run_time TEXT,valid_time TEXT,city_key TEXT,prediction REAL,actual REAL,error REAL,PRIMARY KEY(model,run_time,valid_time,city_key));
CREATE TABLE IF NOT EXISTS city_observations(station TEXT,valid_utc TEXT,city TEXT,local_date TEXT,raw_metar TEXT,temperature_f REAL,dewpoint_f REAL,wind_kt REAL,wind_dir REAL,gust_kt REAL,pressure_hpa REAL,visibility_mi REAL,cloud1 TEXT,weather TEXT,PRIMARY KEY(station,valid_utc));
CREATE TABLE IF NOT EXISTS city_daily_labels(station_id TEXT,city TEXT,date TEXT,source TEXT,tmax_f REAL,tmin_f REAL,label_available_ts TEXT,PRIMARY KEY(station_id,date,source));
CREATE TABLE IF NOT EXISTS city_nws_cli(city TEXT,station TEXT,pil TEXT,climate_date TEXT,official_daily_high_f REAL,official_daily_low_f REAL,publication_time_utc TEXT,source TEXT,source_url TEXT,raw_filename TEXT,PRIMARY KEY(city,raw_filename));
CREATE TABLE IF NOT EXISTS city_kalshi_markets(ticker TEXT PRIMARY KEY,event_ticker TEXT,series_ticker TEXT,city TEXT,variable TEXT,result TEXT,floor_strike REAL,cap_strike REAL,open_time TEXT,close_time TEXT,expiration_time TEXT,volume REAL,open_interest REAL);
CREATE TABLE IF NOT EXISTS city_kalshi_trades(ticker TEXT,trade_id TEXT,timestamp TEXT,price REAL,no_price REAL,size REAL,side TEXT,is_block_trade INTEGER,PRIMARY KEY(ticker,trade_id));
CREATE TABLE IF NOT EXISTS city_kalshi_candles(ticker TEXT,end_period_ts INTEGER,period_minutes INTEGER,volume REAL,open_interest REAL,price_open REAL,price_high REAL,price_low REAL,price_close REAL,yes_bid_close REAL,yes_ask_close REAL,PRIMARY KEY(ticker,end_period_ts,period_minutes));
CREATE TABLE IF NOT EXISTS kalshi_hourly_events(event_ticker TEXT PRIMARY KEY,series_ticker TEXT,title TEXT,sub_title TEXT,event_url TEXT,strike_date TEXT,settlement_sources TEXT,market_count INTEGER,retrieved_at_utc TEXT,raw_sha256 TEXT,raw_path TEXT);
CREATE TABLE IF NOT EXISTS kalshi_hourly_markets(ticker TEXT PRIMARY KEY,event_ticker TEXT,series_ticker TEXT,title TEXT,subtitle TEXT,yes_sub_title TEXT,no_sub_title TEXT,status TEXT,result TEXT,open_time TEXT,close_time TEXT,expiration_time TEXT,settlement_ts TEXT,yes_bid REAL,yes_ask REAL,last_price REAL,volume_fp REAL,open_interest_fp REAL,retrieved_at_utc TEXT,raw_sha256 TEXT,raw_path TEXT);
CREATE TABLE IF NOT EXISTS twc_kalshi_hourly(station TEXT,station_name TEXT,valid_utc TEXT,valid_local TEXT,local_date TEXT,local_hour INTEGER,temperature_c REAL,temperature_f REAL,status TEXT,retrieved_at_utc TEXT,raw_sha256 TEXT,raw_path TEXT,PRIMARY KEY(station,valid_utc,raw_path));
CREATE TABLE IF NOT EXISTS twc_kalshi_daily(station TEXT,city TEXT,cli_id TEXT,date TEXT,status TEXT,official_high_f REAL,official_low_f REAL,average_f REAL,retrieved_at_utc TEXT,raw_sha256 TEXT,raw_path TEXT,PRIMARY KEY(station,date,raw_path));
CREATE TABLE IF NOT EXISTS kalshi_hourly_contracts(event_ticker TEXT,market_ticker TEXT PRIMARY KEY,series_ticker TEXT,target_time_utc TEXT,target_local_text TEXT,threshold_f REAL,comparison TEXT,bucket_floor_f REAL,bucket_ceil_f REAL,status TEXT,result TEXT,open_time TEXT,close_time TEXT,settlement_ts TEXT,settlement_source_name TEXT,settlement_source_url TEXT,settlement_station TEXT,settlement_station_method TEXT,rules_hash TEXT,retrieved_at_utc TEXT,raw_sha256 TEXT,raw_path TEXT);
CREATE TABLE IF NOT EXISTS kalshi_hourly_twc_labels(market_ticker TEXT PRIMARY KEY,event_ticker TEXT,target_time_utc TEXT,threshold_f REAL,comparison TEXT,kalshi_result TEXT,source_temperature_f REAL,source_observed_yes TEXT,source_status TEXT,source_valid_utc TEXT,source_receipt_utc TEXT,label_available_ts TEXT,source_raw_sha256 TEXT,source_raw_path TEXT);
CREATE TABLE IF NOT EXISTS historical_quote_market_metadata(series_ticker TEXT,market_ticker TEXT,event_ticker TEXT,status TEXT,result TEXT,open_time TEXT,close_time TEXT,expiration_time TEXT,settlement_ts TEXT,settlement_source_name TEXT,settlement_source_url TEXT,settlement_station TEXT,retrieved_at_utc TEXT,PRIMARY KEY(series_ticker,market_ticker));
CREATE TABLE IF NOT EXISTS historical_quote_candles(series_ticker TEXT,market_ticker TEXT,event_ticker TEXT,period_interval INTEGER,end_period_ts TEXT,yes_bid_open REAL,yes_bid_high REAL,yes_bid_low REAL,yes_bid_close REAL,yes_ask_open REAL,yes_ask_high REAL,yes_ask_low REAL,yes_ask_close REAL,trade_open REAL,trade_high REAL,trade_low REAL,trade_close REAL,volume_fp REAL,open_interest_fp REAL,fetched_at TEXT,PRIMARY KEY(series_ticker,market_ticker,end_period_ts));
CREATE TABLE IF NOT EXISTS historical_quote_trades(series_ticker TEXT,trade_id TEXT,market_ticker TEXT,count_fp REAL,yes_price_dollars REAL,no_price_dollars REAL,taker_book_side TEXT,taker_outcome_side TEXT,created_time TEXT,is_block_trade TEXT,fetched_at TEXT,PRIMARY KEY(series_ticker,trade_id));
-- Report-2 trading-state schemas. These remain empty until valid manifests or
-- prospective market telemetry exists; no historical values are synthesized.
CREATE TABLE IF NOT EXISTS decision_features(market_ticker TEXT,decision_ts TEXT,target_ts TEXT,horizon_minutes INTEGER,feature_version TEXT,source_run_ids TEXT,observation_ids TEXT,features_json TEXT,PRIMARY KEY(market_ticker,decision_ts,feature_version));
CREATE TABLE IF NOT EXISTS prediction_manifests(record_id TEXT PRIMARY KEY,market_ticker TEXT,decision_ts TEXT,target_time_utc TEXT,feature_version TEXT,model_version TEXT,calibrator_version TEXT,rules_hash TEXT,code_commit TEXT,prediction REAL,manifest_path TEXT,source_run_ids TEXT,observation_ids TEXT);
CREATE TABLE IF NOT EXISTS paper_orders(record_id TEXT PRIMARY KEY,manifest_path TEXT,market_ticker TEXT,decision_ts TEXT,side TEXT,quantity REAL,price REAL,scenario TEXT,recorded_at_utc TEXT);
CREATE TABLE IF NOT EXISTS paper_fills(record_id TEXT PRIMARY KEY,manifest_path TEXT,market_ticker TEXT,decision_ts TEXT,side TEXT,quantity REAL,price REAL,fee REAL,scenario TEXT,recorded_at_utc TEXT);
CREATE TABLE IF NOT EXISTS paper_settlements(record_id TEXT PRIMARY KEY,manifest_path TEXT,market_ticker TEXT,settled_yes TEXT,net_payoff REAL,recorded_at_utc TEXT);
CREATE TABLE IF NOT EXISTS orderbook_events_live(market_ticker TEXT,sequence_no INTEGER,receive_ts TEXT,exchange_ts TEXT,event_type TEXT,side TEXT,yes_price REAL,quantity_delta REAL,raw_path TEXT,PRIMARY KEY(market_ticker,sequence_no));
CREATE TABLE IF NOT EXISTS market_trade_events(market_ticker TEXT,trade_id TEXT,trade_ts TEXT,yes_price REAL,quantity REAL,taker_side TEXT,ingested_ts TEXT,raw_path TEXT,PRIMARY KEY(market_ticker,trade_id));
CREATE TABLE IF NOT EXISTS live_market_quotes(market_ticker TEXT,event_ticker TEXT,open_time TEXT,close_time TEXT,received_ts TEXT,yes_bid REAL,yes_ask REAL,yes_bid_size REAL,yes_ask_size REAL,no_bid REAL,no_ask REAL,status TEXT,PRIMARY KEY(market_ticker,received_ts));
CREATE TABLE IF NOT EXISTS settlement_temperature(target_ts_utc TEXT,location_id TEXT,official_temp_f REAL,source TEXT,is_final INTEGER,retrieved_at TEXT,raw_hash TEXT,PRIMARY KEY(target_ts_utc,location_id,retrieved_at));
CREATE TABLE IF NOT EXISTS surface_observation(station_id TEXT,valid_ts TEXT,received_ts TEXT,source TEXT,temp_c REAL,dewpoint_c REAL,wind_speed_ms REAL,wind_dir_deg REAL,gust_ms REAL,pressure_hpa REAL,visibility_m REAL,cloud_fraction TEXT,precip_mm REAL,qc_flags TEXT,raw_metar TEXT,raw_payload_hash TEXT,PRIMARY KEY(station_id,valid_ts,source));
CREATE TABLE IF NOT EXISTS model_runs(model_run_id TEXT PRIMARY KEY,provider TEXT,model TEXT,model_version TEXT,init_ts TEXT,published_ts TEXT,published_ts_method TEXT,ingested_ts TEXT,grid_resolution_km REAL,raw_manifest_uri TEXT);
CREATE INDEX IF NOT EXISTS idx_obs_valid ON observations(valid_utc);
CREATE INDEX IF NOT EXISTS idx_obs_local_date ON observations(local_date);
CREATE INDEX IF NOT EXISTS idx_state_asof ON derived_intraday_state(feature_asof_utc);
CREATE INDEX IF NOT EXISTS idx_markets_outcome_date ON kalshi_markets(outcome_local_date);
CREATE INDEX IF NOT EXISTS idx_daily_results_date ON daily_results(date);
CREATE INDEX IF NOT EXISTS idx_contracts_outcome_date ON contract_outcomes(outcome_local_date);
CREATE INDEX IF NOT EXISTS idx_cli_climate_date ON nws_cli_daily(climate_date);
"""


def rows(path: Path):
    return csv.DictReader(open(path, newline="")) if path.exists() else []


def fv(row: dict, col: str):
    """Empty CSV cell -> None (NULL); keep other strings as-is."""
    v = row.get(col)
    return v if v not in (None, "") else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database", default=None)
    args = ap.parse_args()
    d = ensure_runtime_dirs()
    db = Path(args.database) if args.database else d["research"] / "kalshi_weather.sqlite"
    con = sqlite3.connect(db)
    # TWC source snapshots are immutable by raw_path. Recreate these derived
    # tables so older hash-keyed schemas cannot collapse identical receipts.
    con.execute("DROP TABLE IF EXISTS twc_kalshi_hourly")
    con.execute("DROP TABLE IF EXISTS twc_kalshi_daily")
    # HOMR can legitimately contain repeated administrative updates.  Older
    # databases used a natural-key primary key and silently collapsed those
    # records; recreate that table once so the portable layer preserves every
    # archived history row.
    homr_sql = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='homr_station_history'").fetchone()
    if homr_sql and "PRIMARY KEY" in homr_sql[0].upper():
        con.execute("DROP TABLE homr_station_history")
    ghcnh_sql = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='ghcnh_observations'").fetchone()
    if ghcnh_sql and len(con.execute("PRAGMA table_info(ghcnh_observations)").fetchall()) != 13:
        con.execute("DROP TABLE ghcnh_observations")
    model_sql = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='model_forecasts'").fetchone()
    if model_sql and len(con.execute("PRAGMA table_info(model_forecasts)").fetchall()) != 10:
        con.execute("DROP TABLE model_forecasts")
    contract_sql = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='kalshi_hourly_contracts'").fetchone()
    if contract_sql and len(con.execute("PRAGMA table_info(kalshi_hourly_contracts)").fetchall()) != 22:
        con.execute("DROP TABLE kalshi_hourly_contracts")
    con.executescript(DDL)
    # This is a rebuild of the portable query layer, so remove rows that are
    # no longer present in refreshed normalized files before inserting. Raw
    # source payloads remain untouched and authoritative.
    reload_tables = ("observations", "awc_metar", "glmp_temperature_points", "nearby_observations", "daily_results",
                     "derived_intraday_state", "solar_features", "contract_outcomes",
                     "kalshi_markets", "kalshi_prices", "nws_cli_daily",
                     "ghcn_stations_catalog", "asos_stations_catalog", "model_forecasts",
                     "model_forecast_points", "rtma_point_features", "cpc_oni",
                     "model_runs",
                     "gefs_members", "gefs_features", "gefs_calibration", "ghcnh_observations", "ghcnh_daily_extrema", "settlement_window_extrema", "homr_station_history", "ecmwf_point_features", "ecmwf_ensemble_points",
                     "city_observations", "city_daily_labels", "city_nws_cli",
                     "city_kalshi_markets", "city_kalshi_trades", "city_kalshi_candles",
                     "kalshi_hourly_events", "kalshi_hourly_markets",
                     "historical_quote_market_metadata", "historical_quote_candles", "historical_quote_trades")
    reload_tables += ("live_market_quotes",)
    reload_tables += ("twc_kalshi_hourly", "twc_kalshi_daily")
    reload_tables += ("kalshi_hourly_contracts",)
    reload_tables += ("kalshi_hourly_twc_labels",)
    for table in reload_tables:
        con.execute(f"DELETE FROM {table}")
    # The point decoder gained message_index to preserve multiple GRIB
    # messages with the same variable/lead. Recreate only this derived query
    # table when upgrading an older SQLite file; raw inputs remain untouched.
    point_columns = con.execute("PRAGMA table_info(model_forecast_points)").fetchall()
    if len(point_columns) != 14:
        con.execute("DROP TABLE model_forecast_points")
        con.execute("CREATE TABLE model_forecast_points(model TEXT,city TEXT,initialization_time_utc TEXT,valid_time_utc TEXT,lead_hours INTEGER,source_receipt_time TEXT,variable TEXT,value REAL,unit TEXT,grid_latitude REAL,grid_longitude REAL,raw_path TEXT,sha256 TEXT,message_index INTEGER,PRIMARY KEY(model,city,initialization_time_utc,lead_hours,variable,raw_path,message_index))")

    con.executemany(
        "INSERT OR REPLACE INTO stations VALUES(?,?,?,?,?,?,?)",
        [("USW00023183", "KPHX", "phx", 33.4278, -112.0036, "America/Phoenix", "settlement_proxy"),
         ("USW00023169", "KLAS", "lv", 36.0719, -115.1633, "America/Los_Angeles", "settlement_proxy")])

    con.executemany(
        "INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["station"], r["valid_utc"], r["local_date"], r["raw_metar"],
          fv(r, "tmpf"), fv(r, "dwpf"), fv(r, "sknt"), fv(r, "drct"),
          fv(r, "gust"), fv(r, "mslp"), fv(r, "vsby"), fv(r, "skyc1"),
          fv(r, "wxcodes"))
         for r in rows(d["iem_out"] / "asos_parsed.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO awc_metar VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(r["station"], r["valid_utc"], r["receipt_utc"], fv(r, "temperature_c"),
          fv(r, "dewpoint_c"), fv(r, "wind_dir_degrees"), fv(r, "wind_speed_kt"),
          r["raw_metar"], r["source_url"], r["raw_sha256"])
         for r in rows(d["research"] / "awc" / "metar.csv")])
    con.executemany(
        "INSERT OR REPLACE INTO glmp_temperature_points VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["model"], r["city"], r["initialization_time_utc"], r["valid_time_utc"],
          fv(r, "lead_hours"), r["source_receipt_time"], r["variable"], fv(r, "value"),
          r["unit"], fv(r, "grid_latitude"), fv(r, "grid_longitude"), r["raw_path"],
          r["sha256"], fv(r, "message_index"))
         for r in rows(d["research"] / "glmp" / "point_features.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO ghcnh_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["station"], r["station_name"], r["valid_utc"], fv(r, "latitude"),
          fv(r, "longitude"), fv(r, "elevation_m"), fv(r, "temperature_f"),
          fv(r, "dewpoint_f"), r["temperature_quality_code"],
          r["temperature_report_type"], r["raw_path"], r["sha256"], r["source_receipt_time"])
         for r in rows(d["research"] / "ghcnh" / "observations_2020_2026.csv")])

    con.executemany(
        "INSERT INTO homr_station_history VALUES(?,?,?,?,?,?,?,?)",
        [(r["city"], r["station"], r["record_type"], r["id_type"],
          r["identifier"], r["begin_date"], r["end_date"], r["detail"])
         for r in rows(d["research"] / "homr" / "station_history.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO ghcnh_daily_extrema VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(r["station"], r["local_date"], r["timezone"], fv(r, "observation_count"),
          fv(r, "tmax_f"), r["tmax_utc"], fv(r, "tmin_f"), r["tmin_utc"],
          r["raw_paths"], r["raw_hashes"])
         for r in rows(d["research"] / "ghcnh" / "daily_extrema_2020_2026.csv")])
    con.executemany(
        "INSERT OR REPLACE INTO settlement_window_extrema VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(r["city"], r["outcome_local_date"], r["window_start_utc"], r["window_end_utc"], fv(r, "observation_count"), fv(r, "tmax_f"), r["tmax_utc"], fv(r, "tmin_f"), r["tmin_utc"], r["raw_hashes"])
         for r in rows(d["research"] / "ghcnh" / "settlement_window_extrema_2020_2026.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO ecmwf_point_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["model"], r["city"], r["initialization_time_utc"], r["valid_time_utc"],
          fv(r, "lead_hours"), r["source_receipt_time"], r["variable"], fv(r, "value"),
          r["unit"], fv(r, "grid_latitude"), fv(r, "grid_longitude"), r["raw_path"],
          r["sha256"], fv(r, "message_index"))
         for r in rows(d["research"] / "ecmwf" / "point_features.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO ecmwf_ensemble_points VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["model"], r["city"], r["member_id"], r["initialization_time_utc"], r["valid_time_utc"], fv(r, "lead_hours"), r["source_receipt_time"], r["variable"], fv(r, "value"), r["unit"], fv(r, "grid_latitude"), fv(r, "grid_longitude"), r["raw_path"], r["sha256"], fv(r, "message_index")) for r in rows(d["research"] / "ecmwf" / "ensemble_points.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO nearby_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["station"], r["valid_utc"], r["city"], r["local_date"], r["raw_metar"],
          fv(r, "tmpf"), fv(r, "dwpf"), fv(r, "sknt"), fv(r, "drct"),
          fv(r, "gust"), fv(r, "mslp"), fv(r, "vsby"), fv(r, "skyc1"),
          fv(r, "wxcodes"))
         for r in rows(d["research"] / "nearby_asos" / "nearby_asos_parsed.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO daily_results VALUES(?,?,?,?,?,?)",
        [(r["station_id"], r["date"], fv(r, "tmax_f"), fv(r, "tmin_f"),
          r["source"], r["label_available_ts"])
         for r in rows(d["ghcn_out"] / "labels_daily.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO derived_intraday_state VALUES(?,?,?,?,?,?,?)",
        [(r["station"], r["valid_utc"], r["local_date"],
          fv(r, "current_temperature_f"), fv(r, "observed_high_so_far_f"),
          fv(r, "observed_low_so_far_f"), r["feature_asof_utc"])
         for r in rows(d["research"] / "derived_intraday_state.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO solar_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["city"], r["date"], fv(r, "lat"), fv(r, "lon"),
          r["solar_noon_utc"], r["sunrise_utc"], r["sunset_utc"],
          r["sunrise_local"], r["sunset_local"],
          fv(r, "daylength_min"), fv(r, "declination_deg"), fv(r, "eqtime_min"))
         for r in rows(d["solar_out"] / "solar_features.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO contract_outcomes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["outcome_local_date"], r["city"], r["temp_type"], r["event_ticker"],
          r["market_ticker"], fv(r, "bucket_floor_f"), fv(r, "bucket_ceil_f"),
          r["bucket_label"], r["status"], r["settled_yes"],
          r["settlement_ts"], r["settlement_source_name"], r["settlement_source_url"])
         for r in rows(d["kalshi_out"] / "contract_outcomes.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO kalshi_markets VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["market_ticker"], r["event_ticker"], r["city"], r["temp_type"],
          r["outcome_local_date"], fv(r, "bucket_floor_f"), fv(r, "bucket_ceil_f"),
          r["status"], r["result"], r["open_time"], r["close_time"],
          r["settlement_ts"])
         for r in rows(d["kalshi_out"] / "markets.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO kalshi_prices VALUES(?,?,?,?,?,?)",
        [(r["trade_id"], r["market_ticker"], r["created_time"],
          fv(r, "yes_price_dollars"), fv(r, "no_price_dollars"), fv(r, "count_fp"))
         for r in rows(d["kalshi_out"] / "trades.csv")])

    hourly = d["research"] / "kalshi_hourly"
    con.executemany(
        "INSERT OR REPLACE INTO kalshi_hourly_events VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        [(r.get("event_ticker", ""), r.get("series_ticker", ""), r.get("title", ""),
          r.get("sub_title", ""), r.get("event_url", ""), r.get("strike_date", ""),
          r.get("settlement_sources", ""), fv(r, "market_count"), r.get("retrieved_at_utc", ""),
          r.get("raw_sha256", ""), r.get("raw_path", ""))
         for r in rows(hourly / "events.csv")])
    con.executemany(
        "INSERT OR REPLACE INTO kalshi_hourly_markets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r.get("ticker", ""), r.get("event_ticker", ""), r.get("series_ticker", ""),
          r.get("title", ""), r.get("subtitle", ""), r.get("yes_sub_title", ""),
          r.get("no_sub_title", ""), r.get("status", ""), r.get("result", ""),
          r.get("open_time", ""), r.get("close_time", ""), r.get("expiration_time", ""),
          r.get("settlement_ts", ""), fv(r, "yes_bid"), fv(r, "yes_ask"), fv(r, "last_price"),
          fv(r, "volume_fp"), fv(r, "open_interest_fp"), r.get("retrieved_at_utc", ""),
          r.get("raw_sha256", ""), r.get("raw_path", ""))
         for r in rows(hourly / "markets.csv")])

    twc = d["research"] / "twc_kalshi"
    con.executemany("INSERT OR REPLACE INTO twc_kalshi_hourly VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(r.get("station", ""), r.get("station_name", ""), r.get("valid_utc", ""), r.get("valid_local", ""), r.get("local_date", ""), fv(r, "local_hour"), fv(r, "temperature_c"), fv(r, "temperature_f"), r.get("status", ""), r.get("retrieved_at_utc", ""), r.get("raw_sha256", ""), r.get("raw_path", "")) for r in rows(twc / "hourly.csv")])
    con.executemany("INSERT OR REPLACE INTO twc_kalshi_daily VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    [(r.get("station", ""), r.get("city", ""), r.get("cli_id", ""), r.get("date", ""), r.get("status", ""), fv(r, "official_high_f"), fv(r, "official_low_f"), fv(r, "average_f"), r.get("retrieved_at_utc", ""), r.get("raw_sha256", ""), r.get("raw_path", "")) for r in rows(twc / "daily.csv")])
    con.executemany("INSERT OR REPLACE INTO kalshi_hourly_contracts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(r.get("event_ticker", ""), r.get("market_ticker", ""), r.get("series_ticker", ""), r.get("target_time_utc", ""), r.get("target_local_text", ""), fv(r, "threshold_f"), r.get("comparison", ""), fv(r, "bucket_floor_f"), fv(r, "bucket_ceil_f"), r.get("status", ""), r.get("result", ""), r.get("open_time", ""), r.get("close_time", ""), r.get("settlement_ts", ""), r.get("settlement_source_name", ""), r.get("settlement_source_url", ""), r.get("settlement_station", ""), r.get("settlement_station_method", ""), r.get("rules_hash", ""), r.get("retrieved_at_utc", ""), r.get("raw_sha256", ""), r.get("raw_path", "")) for r in rows(hourly / "contracts.csv")])
    con.executemany("INSERT OR REPLACE INTO kalshi_hourly_twc_labels VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(r.get("market_ticker", ""), r.get("event_ticker", ""), r.get("target_time_utc", ""), fv(r, "threshold_f"), r.get("comparison", ""), r.get("kalshi_result", ""), fv(r, "source_temperature_f"), r.get("source_observed_yes", ""), r.get("source_status", ""), r.get("source_valid_utc", ""), r.get("source_receipt_utc", ""), r.get("label_available_ts", ""), r.get("source_raw_sha256", ""), r.get("source_raw_path", "")) for r in rows(hourly / "twc_labels.csv")])

    live_quotes = []
    active_probe = d["research"] / "kalshi_city" / "active_probe"
    for quote_path in sorted(active_probe.glob("quotes_*.csv")):
        with quote_path.open(newline="") as handle:
            live_quotes.extend(csv.DictReader(handle))
    con.executemany(
        "INSERT OR REPLACE INTO live_market_quotes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r.get("market_ticker", ""), r.get("event_ticker", ""), r.get("open_time", ""),
          r.get("close_time", ""), r.get("received_ts", ""), fv(r, "yes_bid"), fv(r, "yes_ask"),
          fv(r, "yes_bid_size"), fv(r, "yes_ask_size"), fv(r, "no_bid"), fv(r, "no_ask"),
          r.get("status", "")) for r in live_quotes])

    quote_archives = (("KXTEMPNYCH", hourly / "historical_quotes"),
                      ("KXTEMPLAXH", hourly / "kxtemplaxh" / "historical_quotes"),
                      ("KXTEMPAUSH", hourly / "kxtempaush" / "historical_quotes"))
    for series_ticker, quote_root in quote_archives:
        con.executemany(
            "INSERT OR REPLACE INTO historical_quote_market_metadata VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(series_ticker, r.get("market_ticker", ""), r.get("event_ticker", ""), r.get("status", ""),
              r.get("result", ""), r.get("open_time", ""), r.get("close_time", ""),
              r.get("expiration_time", ""), r.get("settlement_ts", ""),
              r.get("settlement_source_name", ""), r.get("settlement_source_url", ""),
              r.get("settlement_station", ""), r.get("retrieved_at_utc", ""))
             for r in rows(quote_root / "market_metadata.csv")])
        con.executemany(
            "INSERT OR REPLACE INTO historical_quote_candles VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(series_ticker, r.get("market_ticker", ""), r.get("event_ticker", ""), fv(r, "period_interval"),
              r.get("end_period_ts", ""), fv(r, "yes_bid_open"), fv(r, "yes_bid_high"), fv(r, "yes_bid_low"),
              fv(r, "yes_bid_close"), fv(r, "yes_ask_open"), fv(r, "yes_ask_high"), fv(r, "yes_ask_low"),
              fv(r, "yes_ask_close"), fv(r, "trade_open"), fv(r, "trade_high"), fv(r, "trade_low"),
              fv(r, "trade_close"), fv(r, "volume_fp"), fv(r, "open_interest_fp"), r.get("fetched_at", ""))
             for r in rows(quote_root / "candles_hourly.csv")])
        con.executemany(
            "INSERT OR REPLACE INTO historical_quote_trades VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            [(series_ticker, r.get("trade_id", ""), r.get("market_ticker", ""), fv(r, "count_fp"),
              fv(r, "yes_price_dollars"), fv(r, "no_price_dollars"), r.get("taker_book_side", ""),
              r.get("taker_outcome_side", ""), r.get("created_time", ""), r.get("is_block_trade", ""),
              r.get("fetched_at", "")) for r in rows(quote_root / "trades.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO nws_cli_daily VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        [(r["city"], r["station"], r["pil"], r["climate_date"],
          fv(r, "official_daily_high_f"), fv(r, "official_daily_low_f"),
          r["publication_time_utc"], r["revision_timestamp_utc"],
          r["source"], r["source_url"], r["raw_filename"])
         for r in rows(d["research"] / "nws_cli" / "daily_climate_cli.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO ghcn_stations_catalog VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(r["city"], fv(r, "distance_km"), r["station_id"], r["name"],
          r["state"], fv(r, "lat"), fv(r, "lon"), fv(r, "elevation_m"),
          r["tmax_range"], r["tmin_range"])
         for r in rows(d["stations_out"] / "ghcn_nearby_stations.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO asos_stations_catalog VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["city"], fv(r, "distance_km"), r["sid"], r["sname"],
          r["state"], fv(r, "lat"), fv(r, "lon"), fv(r, "elevation_m"),
          r["tzname"], r["archive_begin"], r["archive_end"], r["ncei91"],
          r["online"])
         for r in rows(d["stations_out"] / "asos_nearby_stations.csv")])

    con.executemany(
        "INSERT OR REPLACE INTO model_forecasts VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(r["model"], r["initialization_time_utc"], r["valid_time_utc"],
          fv(r, "lead_hours"), r["request_url"], r["raw_path"], r["sha256"],
         r["ingested_at_utc"], r.get("available_time_utc") or r.get("ingested_at_utc"), r.get("available_time_method") or "conservative_ingest")
         for r in rows(d["research"] / "forecasts" / "manifest.csv")])
    model_runs = d["research"] / "reports" / "model_runs.csv"
    con.executemany("INSERT OR REPLACE INTO model_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                    [tuple(r.get(k, "") for k in ("model_run_id", "provider", "model", "model_version", "init_ts", "published_ts", "published_ts_method", "ingested_ts", "grid_resolution_km", "raw_manifest_uri")) for r in rows(model_runs)])
    point_forecasts = d["research"] / "forecasts" / "model_forecasts_points.csv"
    con.executemany(
        "INSERT OR REPLACE INTO model_forecast_points VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["model"], r["city"], r["initialization_time_utc"], r["valid_time_utc"],
          fv(r, "lead_hours"), r["source_receipt_time"], r["variable"], fv(r, "value"),
          r["unit"], fv(r, "grid_latitude"), fv(r, "grid_longitude"), r["raw_path"], r["sha256"], fv(r, "message_index"))
         for r in rows(point_forecasts)])

    rtma_points = d["research"] / "rtma" / "rtma_point_features.csv"
    con.executemany(
        "INSERT OR REPLACE INTO rtma_point_features VALUES(?,?,?,?,?,?,?,?,?)",
        [(r["city"], r["variable"], fv(r, "value"), r["unit"],
          r["valid_time_utc"], fv(r, "grid_latitude"), fv(r, "grid_longitude"),
          r["raw_path"], r["sha256"])
         for r in rows(rtma_points)])
    con.executemany(
        "INSERT OR REPLACE INTO cpc_oni VALUES(?,?,?,?,?,?)",
        [(r["season"], fv(r, "year"), fv(r, "nino34_3mo_mean_c"), fv(r, "oni_anomaly_c"), r["source_url"], r["retrieved_at_utc"])
         for r in rows(d["research"] / "cpc" / "oni.csv")])

    # GEFS is stored in Parquet for analysis and mirrored here as a query layer.
    gefs_members = d["gefs"] / "gefs_members.parquet"
    if gefs_members.exists():
        import pyarrow.parquet as pq
        con.executemany("INSERT OR REPLACE INTO gefs_members VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        [tuple(r.get(k) for k in ("forecast_run_time", "valid_time", "city", "city_key", "latitude", "longitude", "timezone", "model", "member_id", "variable", "value", "retrieved_at"))
                         for r in pq.read_table(gefs_members).to_pylist()])
    gefs_features = d["gefs"] / "gefs_features.parquet"
    if gefs_features.exists():
        import pyarrow.parquet as pq
        feature_cols = ("forecast_run_time", "valid_time", "city_key", "model", "city", "variable", "member_count", "ensemble_mean", "ensemble_spread", "p10", "p25", "median", "p75", "p90", "prob_ge_78", "prob_ge_80", "prob_ge_82", "prob_ge_85", "prob_ge_90")
        con.executemany("INSERT OR REPLACE INTO gefs_features VALUES(" + ",".join("?" for _ in feature_cols) + ")",
                        [tuple(r.get(k) for k in feature_cols) for r in pq.read_table(gefs_features).to_pylist()])
    calibration = d["gefs_history"] / "calibration.csv"
    if calibration.exists():
        con.executemany("INSERT OR REPLACE INTO gefs_calibration VALUES(?,?,?,?,?,?,?)",
                        [tuple(r.get(k) for k in ("model", "run_time", "valid_time", "city_key", "prediction", "actual", "error"))
                         for r in rows(calibration)])

    # Prefer the auditable canonical table when duplicate ASOS re-deliveries
    # have been resolved; raw parsed observations remain available on disk.
    city_asos = d["research"] / "city_asos" / "asos_parsed_canonical.csv"
    if not city_asos.exists():
        city_asos = d["research"] / "city_asos" / "asos_parsed.csv"
    city_by_station = {"NYC": "nyc", "LAX": "la", "AUS": "austin"}
    con.executemany(
        "INSERT OR REPLACE INTO city_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["station"], r["valid_utc"], city_by_station.get(r["station"], r["station"]), r["local_date"], r["raw_metar"],
          fv(r, "tmpf"), fv(r, "dwpf"), fv(r, "sknt"), fv(r, "drct"), fv(r, "gust"),
          fv(r, "mslp"), fv(r, "vsby"), fv(r, "skyc1"), fv(r, "wxcodes"))
         for r in rows(city_asos)])
    city_labels = d["research"] / "ghcn_city" / "labels_daily.csv"
    con.executemany(
        "INSERT OR REPLACE INTO city_daily_labels VALUES(?,?,?,?,?,?,?)",
        [(r["station_id"], r["city"], r["date"], r["source"], fv(r, "tmax_f"),
          fv(r, "tmin_f"), r["label_available_ts"])
         for r in rows(city_labels)])
    city_cli = d["research"] / "city_nws_cli" / "daily_climate_cli.csv"
    con.executemany(
        "INSERT OR REPLACE INTO city_nws_cli VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(r["city"], r["station"], r["pil"], r["climate_date"],
          fv(r, "official_daily_high_f"), fv(r, "official_daily_low_f"),
          r["publication_time_utc"], r["source"], r["source_url"], r["raw_filename"])
         for r in rows(city_cli)])
    for name, table, fields, key_fields in (
        ("markets.csv", "city_kalshi_markets", ("ticker", "event_ticker", "series_ticker", "city", "variable", "result", "floor_strike", "cap_strike", "open_time", "close_time", "expiration_time", "volume", "open_interest"), None),
        ("trades.csv", "city_kalshi_trades", ("ticker", "trade_id", "timestamp", "price", "no_price", "size", "side", "is_block_trade"), None),
        ("candles.csv", "city_kalshi_candles", ("ticker", "end_period_ts", "period_minutes", "volume", "open_interest", "price_open", "price_high", "price_low", "price_close", "yes_bid_close", "yes_ask_close"), None),
    ):
        source = d["research"] / "kalshi_historical_city" / name
        placeholders = ",".join("?" for _ in fields)
        con.executemany(f"INSERT OR REPLACE INTO {table} VALUES({placeholders})",
                        [tuple(fv(r, field) for field in fields) for r in rows(source)])

    con.commit()
    tables = ["observations", "awc_metar", "glmp_temperature_points", "nearby_observations", "daily_results",
              "derived_intraday_state", "solar_features", "contract_outcomes",
              "kalshi_markets", "kalshi_prices", "nws_cli_daily",
              "ghcn_stations_catalog", "asos_stations_catalog",
              "model_forecasts", "model_forecast_points", "rtma_point_features", "cpc_oni", "gefs_members", "gefs_features",
              "gefs_calibration", "ghcnh_observations", "ghcnh_daily_extrema", "settlement_window_extrema", "homr_station_history", "ecmwf_point_features", "ecmwf_ensemble_points", "city_observations", "city_daily_labels",
              "city_nws_cli", "city_kalshi_markets", "city_kalshi_trades",
              "city_kalshi_candles", "kalshi_hourly_events", "kalshi_hourly_markets", "twc_kalshi_hourly", "twc_kalshi_daily", "kalshi_hourly_contracts", "kalshi_hourly_twc_labels", "historical_quote_market_metadata", "historical_quote_candles", "historical_quote_trades"]
    counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in tables}
    print(db)
    for t in tables:
        print(f"  {t:24} {counts[t]}")


if __name__ == "__main__":
    main()
