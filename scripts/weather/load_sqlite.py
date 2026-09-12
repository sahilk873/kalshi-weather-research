"""Create and load a portable SQLite research database from generated CSVs.

Rows are idempotently replaced using documented natural keys. Raw payloads
remain files; SQLite is a query layer, not the source of truth.

Loaded tables mirror the normalized CSVs:
- stations (PHX/LAS settlement proxies)
- observations (settlement-station METAR rows, key station+valid_utc)
- nearby_observations (six non-settlement sites, key station+valid_utc)
- daily_results (GHCN official labels, key station+date+source)
- derived_intraday_state (per-observation PIT features)
- solar_features (deterministic geometry per city+date)
- contract_outcomes (per-market bucket settlement outcome)
- kalshi_markets / kalshi_prices (metadata, excluded price/quantity so far)
- nws_cli_daily (revision-preserving CLI issuances)
- ghcn_stations_catalog / asos_stations_catalog (nearby inventories)
- model_forecasts (forecasts/manifest.csv provenance)

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
CREATE TABLE IF NOT EXISTS model_forecasts(model TEXT,initialization_time_utc TEXT,valid_time_utc TEXT,lead_hours INTEGER,uri TEXT,raw_path TEXT,sha256 TEXT,ingested_at TEXT,PRIMARY KEY(model,initialization_time_utc,lead_hours,uri));
CREATE TABLE IF NOT EXISTS gefs_members(forecast_run_time TEXT,valid_time TEXT,city TEXT,city_key TEXT,latitude REAL,longitude REAL,timezone TEXT,model TEXT,member_id TEXT,variable TEXT,value REAL,retrieved_at TEXT,PRIMARY KEY(forecast_run_time,valid_time,city_key,model,member_id,variable));
CREATE TABLE IF NOT EXISTS gefs_features(forecast_run_time TEXT,valid_time TEXT,city_key TEXT,model TEXT,city TEXT,variable TEXT,member_count INTEGER,ensemble_mean REAL,ensemble_spread REAL,p10 REAL,p25 REAL,median REAL,p75 REAL,p90 REAL,prob_ge_78 REAL,prob_ge_80 REAL,prob_ge_82 REAL,prob_ge_85 REAL,prob_ge_90 REAL,PRIMARY KEY(forecast_run_time,valid_time,city_key,model,variable));
CREATE TABLE IF NOT EXISTS gefs_calibration(model TEXT,run_time TEXT,valid_time TEXT,city_key TEXT,prediction REAL,actual REAL,error REAL,PRIMARY KEY(model,run_time,valid_time,city_key));
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
    con.executescript(DDL)

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
        "INSERT OR REPLACE INTO model_forecasts VALUES(?,?,?,?,?,?,?,?)",
        [(r["model"], r["initialization_time_utc"], r["valid_time_utc"],
          fv(r, "lead_hours"), r["request_url"], r["raw_path"], r["sha256"],
         r["ingested_at_utc"])
         for r in rows(d["research"] / "forecasts" / "manifest.csv")])

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

    con.commit()
    tables = ["observations", "nearby_observations", "daily_results",
              "derived_intraday_state", "solar_features", "contract_outcomes",
              "kalshi_markets", "kalshi_prices", "nws_cli_daily",
              "ghcn_stations_catalog", "asos_stations_catalog",
              "model_forecasts", "gefs_members", "gefs_features",
              "gefs_calibration"]
    counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in tables}
    print(db)
    for t in tables:
        print(f"  {t:24} {counts[t]}")


if __name__ == "__main__":
    main()
