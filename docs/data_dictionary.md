# Data dictionary and storage contract

Large backfills should be partitioned Parquet by `city/year/month` while raw
HTTP, CSV, METAR, GRIB, and WebSocket payloads remain immutable alongside
their normalized outputs. Live JSONL can later be ingested into PostgreSQL or
TimescaleDB; do not discard raw source messages.

| Dataset | Key / essential fields | Time semantics |
| --- | --- | --- |
| `stations` | station ID, ICAO, city, coordinates, elevation, timezone, role | static reference |
| `ghcn/labels_daily.csv` | station/date, `tmax_f`, `tmin_f`, flags, source, `label_available_ts` | final labels only; availability is conservative synthetic, not source publication |
| `iem/asos_parsed.csv` | station, `valid_utc`, `raw_metar`, temperature/dewpoint, wind, visibility, pressure, clouds/weather/precipitation, precise/6h/24h remark groups | `valid_utc` is observation event time; raw METAR is preserved |
| `nearby_asos/nearby_asos_parsed.csv` | city, station, `valid_utc`, `local_date`, tmpf/dwpf/relh, wind (drct/sknt/gust), p01i, alti/mslp, vsby, sky layers, wxcodes, ice/snow/peak/feel follow IEM 39-column naming, `remark_*` (precise temps, 1/2/4h extrema), `raw_metar` | six deliberately selected nearby stations (PHX: SDL/CHD/FFZ, LAS: HND/VGT/LSV); `valid_utc` uses canonical `Z`; deduplicated on (station, `valid_utc`) because IEM re-delivers rows |
| `iem/asos_daily.csv` | station/local date, sampled extrema and times, coverage count | a convenience aggregate; never label it official |
| `solar/solar_features.csv` | city/date, sunrise/sunset UTC/local, day length, declination | deterministic local-calendar values; calculate instantaneous angles at a feature timestamp |
| `kalshi/events.csv` | event/series/city/high-low/outcome date, settlement source URL, source rules | API retrieval snapshot; settlement source must remain joined to event |
| `kalshi/markets.csv` | ticker, bucket bounds, status/result, open/close/settlement timestamps, quotes/OI/volume | API-snapshot quotes are not historical book states |
| `kalshi/trades.csv` | trade ID, ticker, created timestamp, price, count, taker sides | event time is Kalshi `created_time` |
| `kalshi/candlesticks_*.csv` | ticker, interval, period end, OHLC, bid/ask, OI, volume | period end must be no later than decision time |
| `kalshi/ws/*.jsonl` | `received_ts`, `received_ts_ms`, raw message | ingestion/receive time plus exchange message timestamps where supplied |
| `forecasts/manifest.csv` + `forecasts/raw/{model}` | model, city/grid point, initialization time, valid time, lead, request URL, retrieval time, SHA-256; immutable filtered GRIB2 | require both init and valid time; never choose a later run; decode only when a GRIB decoder is installed |
| `derived_intraday_state.csv` | timestamp, observation extrema, reconstructed extrema, 5/15/30/60m deltas, acceleration, dewpoint/wind/cloud changes, solar clocks | built strictly from rows public by timestamp; final labels are not read. Deduplicated before groupby (IEM can re-deliver identical rows); rows without a present temperature are kept with empty per-time deltas |
| `nws_cli/daily_climate_cli.csv` | city, climate date, climatological high/low, spatial source, publication timestamp, raw filename | product revisions preserved across rows; join climate dates honoring publication time to avoid lookahead |
| `kalshi/contract_outcomes.csv` | outcome date, city, temp type, bucket bounds + label, status, settled yes/no, settlement source+URL | derived view of events × markets; settled label strictly separate from any pre-settlement feature |
| `kalshi_weather.sqlite` | normalized query tables: stations catalogs (GHCN-adjacent + ASOS), observations, labels, intraday state, solar, kalshi events/markets/prices/contract outcomes, nearby observations, NWS CLI daily, forecast manifest | `INSERT OR REPLACE` on natural keys; raw files remain authoritative; rebuild by deleting the file and rerunning `load_sqlite.py` |
| `gefs/gefs_members.parquet` | forecast/valid time, city coordinates/timezone, model, member ID, variable, value | long-form member rows; raw Open-Meteo JSON remains under `gefs/raw/`; run time is retrieval time when initialization is not exposed; observed smoke-test responses returned 30 members |
| `gefs/gefs_features.parquet` | ensemble mean/spread, p10/p25/median/p75/p90, member count, threshold probabilities | computed from `temperature_2m`; `prob_ge_K` is members with temperature >= K divided by available members |
| `gefs/historical_raw/` | historical, previous-runs, and single-runs JSON, manifest, predictions, calibration | point-in-time forecast provenance; actual/error joins require separately timestamped observations |

The implemented state builder precomputes one row per observation with its own
`feature_asof_utc`: all running values use records at or before that exact
timestamp. The raw METAR parser exposes
precise `T` temperatures and standard 1/2/4 extrema remarks for a more
faithful official-extreme reconstruction.
# Forecast provenance

`forecasts/manifest.csv` columns: `model`, `city`,
`initialization_time_utc`, `valid_time_utc`, `lead_hours`, station latitude
and longitude, `request_url`, `raw_path`, `sha256`, and `ingested_at_utc`.
The corresponding filtered GRIB2 is retained under `forecasts/raw/{model}`.
Use `known_forecasts` for prediction features and `valid_forecasts_asof` only
when joining fields whose valid time must already have occurred.
