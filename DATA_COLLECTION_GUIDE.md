# Data collection guide

Fast reference for extending this repository beyond the current four Kalshi
daily-temperature series. The canonical scope today is:

| City | Settlement station | Kalshi series |
| --- | --- | --- |
| Phoenix | KPHX / GHCN USW00023183 | `KXHIGHTPHX`, `KXLOWTPHX` |
| Las Vegas | KLAS / GHCN USW00023169 | `KXHIGHTLV`, `KXLOWTLV` |

The pipeline collects research data only. It does not contain a trading model
or order-placement logic.

## Start here

The bounded orchestrator is:

```bash
python3 scripts/weather/run_sample.py
```

It runs, in order, GHCN labels, settlement-station ASOS, solar features,
nearby-station discovery, nearby parsing, point-in-time state construction,
Kalshi metadata, public trades/candles, SQLite loading, and validation.
Use `--skip step_name ...` to avoid network collection. Offline rebuild:

```bash
python3 scripts/weather/run_sample.py --skip ghcn_daily iem_asos solar nearby_stations kalshi_meta kalshi_trades_candles
```

After any collection or parser change, run:

```bash
python3 scripts/weather/parse_nearby_asos.py
python3 scripts/weather/build_intraday_state.py
python3 scripts/weather/load_sqlite.py
python3 scripts/weather/validate.py
python3 scripts/weather/settlement_analysis.py
python3 -m py_compile scripts/weather/*.py
```

## Weather and settlement data

### Official daily labels: NCEI GHCN-Daily

- Script: `scripts/weather/ghcn_daily.py`.
- Source: `https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/`.
- Downloads each configured station's fixed-width `.dly` file, plus station
  and inventory catalogs, with caching and retries.
- Canonical output: `data/weather_research/ghcn/labels_daily.csv`.
- Raw files: `data/raw_ghcn/`.
- Output includes date, station, quality flags, tenths °C, converted °F,
  source, and `label_available_ts`.
- Full GHCN history is useful for labels and validation, but row-level release
  times are unavailable. The current label gate is conservative synthetic
  date + 36 hours; never use it before that timestamp.
- Incremental option: `--since YYYY-MM-DD`; this writes a suffixed output.

GHCN is a reconstruction/validation source. It is not automatically the legal
settlement source: event metadata currently shows an NWS CLI era and a later
Weather Company era.

### Intraday settlement-station observations: IEM ASOS/METAR

- Script: `scripts/weather/iem_asos.py`.
- Source:
  `https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py`.
- Default collection: `python3 scripts/weather/iem_asos.py --days 30`.
- Historical collection:
  `python3 scripts/weather/backfill_asos.py --start 2021-01-01 --end 2026-01-01`.
- Raw hourly/special observations remain under
  `data/weather_research/iem/raw/`; monthly backfills are isolated under
  `data/weather_research/iem_backfill/raw/`.
- Normalized output: `iem/asos_parsed.csv`; daily convenience aggregate:
  `iem/asos_daily.csv`.
- Raw METAR is preserved. Parsed fields include temperature, dewpoint,
  humidity, wind, gust, pressure, visibility, cloud layers, precipitation,
  weather codes, and remarks.
- Remarks include precise temperature/dewpoint groups, 6-hour and 24-hour
  extrema, precipitation, and pressure tendency where present.
- `valid_utc` is observation time. IEM does not provide the original
  dissemination timestamp, so do not treat ingestion time as publication time.

### NWS Daily Climate Reports

- Script: `scripts/weather/nws_cli_archive.py`.
- Source: IEM AFOS ZIP retrieval, using `CLIPHX` / `CLILAS`.
- Example:
  `python3 scripts/weather/nws_cli_archive.py --start 2026-09-05 --end 2026-09-11`.
- Raw ZIP/text products: `data/weather_research/nws_cli/raw/`.
- Normalized output: `nws_cli/daily_climate_cli.csv`, retaining multiple
  issuance/revision rows with observed `publication_time_utc`.
- The collector merges into the existing CSV; a narrow later request must not
  erase older retained products.
- IEM AFOS is only a rolling public window. It cannot reconstruct multi-year
  CLI history. Do not claim NWS-era point-in-time coverage beyond retained
  products.

### Nearby ASOS network

- Discovery: `scripts/weather/nearby_stations.py`; default radius is 75 km.
- Collection: `scripts/weather/collect_nearby_asos.py --days 30`.
- Parsing: `scripts/weather/parse_nearby_asos.py`.
- Raw files: `data/weather_research/nearby_asos/raw/`.
- Normalized file: `nearby_asos/nearby_asos_parsed.csv`.
- Current selected stations are PHX: SDL/CHD/FFZ and LV: HND/VGT/LSV.
- Keep nearby observations separate from the settlement station. They are
  predictors for spatial gradients and change detection, not labels.

### Solar features

- Script: `scripts/weather/solar.py`.
- Example:
  `python3 scripts/weather/solar.py --start 2026-08-01 --end 2026-09-11`.
- Output: `data/weather_research/solar/solar_features.csv`.
- Computes deterministic sunrise, sunset, solar noon, day length,
  declination, and equation-of-time values by city/date. Instantaneous
  elevation/azimuth features should be derived from the feature timestamp.

## Forecast collection

### HRRR and NBM filtered GRIB2

Two collectors exist:

- `scripts/weather/nomads_forecasts.py` downloads small NOMADS geographic
  subsets and records a manifest.
- `scripts/weather/model_archive.py` downloads bounded raw archive files
  from NOAA public S3.

NOMADS example:

```bash
python3 scripts/weather/nomads_forecasts.py --model hrrr --init 2026-09-10T12:00:00Z --leads 0 1 2
python3 scripts/weather/nomads_forecasts.py --model nbm --init 2026-09-11T00:00:00Z --leads 1
```

The NOMADS collector limits requests with `--max-requests`, applies PHX/LV
bounding boxes, refuses oversized downloads with `--max-bytes`, caches raw
GRIB2, and records initialization time, valid time, lead, coordinates, URL,
ingestion time, and SHA-256 in
`data/weather_research/forecasts/manifest.csv`.

Raw files are under `forecasts/raw/hrrr/` and `forecasts/raw/nbm/`.
Decoding is optional and requires eccodes/cfgrib or wgrib2. A raw GRIB file
without a decoder is still preserved evidence; values must not be fabricated.
`scripts/weather/asof_forecasts.py` provides filtering helpers. A forecast
is eligible only when `initialization_time_utc <= decision_time_utc`; also
respect valid time for the feature being used.

## Kalshi collection

### Public current metadata

- Script: `scripts/weather/kalshi_meta.py`.
- API base: `https://external-api.kalshi.com/trade-api/v2`.
- It discovers the configured series, paginates events, preserves raw series
  payloads under `data/series/`, and normalizes event/market metadata.
- Outputs:
  `data/weather_research/kalshi/events.csv`,
  `markets.csv`, and `contract_outcomes.csv`.
- Metadata includes event/market tickers, city, high/low type, local outcome
  date, settlement source/name/URL, bucket bounds, status/result, timestamps,
  quotes, volume, open interest, and liquidity.
- REST market metadata is public in the current API. Keep event-level
  settlement source attached to every downstream label.

Run:

```bash
python3 scripts/weather/kalshi_meta.py
```

### Public trades and candlesticks

- Script: `scripts/weather/kalshi_trades_candles.py`.
- Run bounded:
  `python3 scripts/weather/kalshi_trades_candles.py --max-events-per-series 2`.
- Uses market candlesticks at 1-minute, 60-minute, or 1440-minute intervals
  where available, and paginated public market trades.
- Raw responses are cached in
  `data/weather_research/kalshi/candles_raw/` and `trades_raw/`.
- Normalized outputs are `candlesticks_daily.csv`,
  `candlesticks_hourly.csv`, and `trades.csv`.
- These are event-time market records. Snapshot quotes in metadata are not
  historical executable order books. Never substitute a closing price for a
  bid/ask without documenting it.
- The API has a historical cutoff. For markets/trades before the cutoff,
  use the historical collector below rather than assuming live endpoints
  expose the full archive.

### Historical Kalshi markets, trades, and candles

- Script: `scripts/weather/kalshi_historical.py`.
- Output tree: `data/weather_research/kalshi_historical/`.
- It records `raw/cutoff.json`, paginated historical market/trade responses,
  historical candlesticks, and normalized `markets.csv`, `trades.csv`,
  and `candles.csv`.
- Example dry run:
  `python3 scripts/weather/kalshi_historical.py --start 2026-07-01 --end 2026-07-31 --dry-run`.
- Use `--series`, `--start`, `--end`, `--interval 1m|1h|1d`,
  `--max-markets`, and `--max-requests` to keep collection bounded.
- Raw responses are authoritative. The collector does not fabricate order
  books from candles.

The checked-in OpenAPI contract documents live versus historical cutoffs,
pagination cursors, and the historical endpoints. Recheck
`openapi.yaml` before expanding collection assumptions.

### Live WebSocket market data

- Script: `scripts/weather/collect_orderbook.py`.
- Endpoint:
  `wss://external-api-ws.kalshi.com/trade-api/ws/v2`.
- Dry run first:
  `python3 scripts/weather/collect_orderbook.py --dry-run`.
- Bounded collection:
  `python3 scripts/weather/collect_orderbook.py --run-seconds 3600`.
- Channels default to `orderbook_delta ticker trade`; limit with
  `--channels` and/or `--ticker`.
- Raw JSONL and collector state are written under
  `data/weather_research/kalshi/ws/`.
- The collector retains receive timestamps, reconnect state, raw envelopes,
  sequence-gap/duplicate diagnostics, and resubscribes after reconnects.
- Credentials are environment-only:
  `KALSHI_API_KEY` + `KALSHI_USER_ID`, or
  `KALSHI_WS_EXTRA_HEADERS` for access-key handshake headers. Never commit
  secrets.
- The checked-in AsyncAPI contract says the connection is authenticated,
  orderbook streams begin with a snapshot followed by deltas, and Kalshi
  sends ping frames that require pong handling.

## Point-in-time rules

1. Every observation uses its event timestamp in UTC.
2. Convert UTC to the owning city's IANA timezone before assigning an outcome
   date. Phoenix is `America/Phoenix`; Las Vegas is
   `America/Los_Angeles` and observes DST.
3. Never use final labels, later forecast runs, revised CLI products, or
   settlement results before their own recorded availability/publication time.
4. For GHCN, require `label_available_ts <= decision_time`; remember this is
   conservative synthetic metadata.
5. For forecasts, require initialization time no later than the decision time.
6. Preserve raw files, retrieval URLs, retrieval timestamps, and hashes before
   normalization.
7. Historical order books cannot be reconstructed from closing prices.

## SQLite and validation

`scripts/weather/load_sqlite.py` creates
`data/weather_research/kalshi_weather.sqlite` as a query layer over CSVs.
It includes stations, observations, nearby observations, daily results,
derived state, solar features, contract outcomes, Kalshi markets/prices,
NWS CLI products, station catalogs, and forecast manifests. Raw files remain
the source of truth.

`scripts/weather/validate.py` checks schemas, duplicates, METAR parsing,
bucket gaps/overlaps, local dates/DST, running extrema, CLI/GHCN agreement,
forecast timestamps and hashes, market joins, and settlement reconstruction.
`settlement_analysis.py` regenerates the human-readable settlement-source
analysis.

## Legacy and compatibility collectors

The root-level scripts predate the canonical `scripts/weather/` pipeline and
are useful for understanding older retained artifacts, but they are broader
than the current four-series scope:

- `scripts/pull_weather_markets.py` discovers weather series/events from the
  Kalshi REST API and writes broad raw/CSV outputs under `data/`.
- `scripts/pull_weather_resumable.py` performs a retryable, resumable broad
  series/event pull; `scripts/retry_weather_pull.py` retries and deduplicates
  those outputs.
- `scripts/merge_weather_outputs.py` combines per-series files from
  `data/series/`; `scripts/flatten_weather_csv.py` flattens nested event
  payloads; `scripts/analyze_phx_lv.py` creates the older
  `data/phx_lv_daily_temp_markets.csv` summary.

Prefer the scoped `scripts/weather/kalshi_meta.py`,
`kalshi_trades_candles.py`, and `kalshi_historical.py` for new work.
Treat the broad root-level outputs as raw/legacy snapshots: they contain
other cities and non-temperature products and are not automatically suitable
for point-in-time backtests.

## Adding a city, station, or market series

1. Add a city entry to `scripts/weather/stations.py` with a stable key,
   display name, IANA timezone, IEM network/station, GHCN ID, coordinates,
   Kalshi high/low series tickers, and NWS CLI site/issued-by code.
2. Add the city's IEM network GeoJSON and GHCN inventory/station lookup to the
   station-discovery workflow.
3. Add nearby ASOS sites to both
   `collect_nearby_asos.py` and `parse_nearby_asos.py`; document why each
   site is useful and record distance/direction/elevation.
4. Extend the NOMADS bounding box and variable selection only for the new
   location. Keep filtered GRIB requests bounded.
5. Confirm the new Kalshi series and event rules directly from API payloads.
   Do not infer settlement source, bucket geometry, rounding, or timezone
   from ticker names. Add the series to the intended mapping in
   `stations.py`.
6. Keep the new outputs partitioned by city/series where practical; do not
   mix different settlement sources into one label column.
7. Update `docs/data_dictionary.md`, `data_sources.md`, and validation
   expectations. Add a small fixture/sample before attempting a long
   backfill.
8. Run the offline rebuild and full validation commands above, then inspect
   raw payloads and the generated quality report.

Do not add hourly, precipitation, hurricane, snowfall, other-city strategies,
or execution logic without an explicit scope change.

## Known limitations

- Current retained Kalshi event history is a limited API window, not a
  guaranteed multi-year archive.
- IEM's public AFOS interface does not provide multi-year timestamped CLI
  history.
- The Weather Company settlement history is licensed and is not reproduced by
  GHCN or NWS data. Such labels must be called proxy labels.
- GRIB decoding is optional until eccodes/cfgrib or wgrib2 is installed.
- WebSocket collection requires credentials and has not been populated in the
  checked-in environment.
