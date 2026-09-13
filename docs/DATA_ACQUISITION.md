# Auxiliary city data acquisition log

Last refreshed: 2026-09-12 UTC. This log records data that was actually
downloaded, not a promise that every report source is historically recoverable.

## Restored PHX/LV tier

The previously parked PHX/LV archive was restored from the local snapshot at
`/tmp/kalshi_phx_lv_removed_20260911` into
`data/weather_research/legacy_phx_lv/`, with its normalized tables copied into
the active legacy paths (`ghcn/`, `iem/`, `nearby_asos/`, `nws_cli/`,
`solar/`, and `kalshi/`). The active restoration contains 60,663 labels,
1,527 settlement-station observations, 5,172 nearby observations, 1,680
markets, 3,212 trades, 686 candles, and 1,680 contract outcomes. The source
snapshot remains preserved for provenance and can be compared byte-for-byte.

## Public sources refreshed

```text
python3 scripts/weather/ghcn_city_labels.py --cities nyc la austin
python3 scripts/weather/backfill_city_asos.py --start 2026-01-01 --end 2026-09-12 --cities nyc la austin
python3 scripts/weather/backfill_asos.py --start 2026-09-11 --end 2026-09-12 --cities phx lv
python3 scripts/weather/solar.py --cities phx lv --start 2020-12-31 --end 2026-09-12
python3 scripts/weather/build_intraday_state.py --parsed data/weather_research/iem_backfill/asos_parsed.csv --solar data/weather_research/solar/solar_features.csv --output data/weather_research/reports/phx_lv_intraday_state_backfill.csv
python3 scripts/weather/collect_city_nearby_asos.py --start 2026-01-01 --end 2026-09-12 --cities nyc la austin
python3 scripts/weather/parse_city_nearby_asos.py
python3 scripts/weather/nws_cli_city_archive.py --start 2026-09-01 --end 2026-09-12 --cities nyc la austin --chunk-days 3
python3 scripts/weather/gefs_ensemble.py --cities nyc los_angeles austin --models ncep_gefs025 ncep_gefs05 ncep_gefs_seamless --forecast-days 3
python3 scripts/weather/gefs_features.py --input data/weather_research/gefs/gefs_members.parquet --output data/weather_research/gefs/gefs_features.parquet
python3 scripts/weather/build_city_features.py --cities nyc la austin --start 2026-01-01 --end 2026-09-12
python3 scripts/weather/evaluate_nowcast.py
python3 scripts/weather/nomads_forecasts.py --model hrrr --init 2026-09-12T00:00:00Z --cities nyc la austin --leads 0 1 2 --max-requests 20
python3 scripts/weather/nomads_forecasts.py --model nbm --init 2026-09-11T00:00:00Z --cities nyc la austin --leads 1 2 --max-requests 20
python3 scripts/weather/nomads_forecasts.py --model hrrr --init 2026-09-12T00:00:00Z --cities phx klas --leads 0 1 2 --max-requests 10
python3 scripts/weather/nomads_forecasts.py --model nbm --init 2026-09-11T00:00:00Z --cities phx klas --leads 1 2 --max-requests 10
/tmp/kalshi-grib/bin/python scripts/weather/decode_point_forecasts.py --cities nyc la austin phx klas
python3 scripts/weather/canonicalize_city_asos.py
python3 scripts/weather/load_sqlite.py
python3 scripts/weather/data_quality_gates.py --output data/weather_research/reports/data_quality_gates.json
python3 scripts/weather/audit_artifact_inventory.py --output data/weather_research/reports/artifact_inventory.json
python3 scripts/weather/audit_city_daily_markets.py --output data/weather_research/reports/city_daily_market_audit.json
python3 scripts/weather/collect_awc_metar.py --ids KJFK KLGA KEWR --hours 2 --output data/weather_research/awc
python3 scripts/weather/build_city_market_schedule.py --markets data/weather_research/kalshi_historical_city/markets.csv --labels data/weather_research/ghcn_city/labels_daily.csv --schedule data/weather_research/reports/city_daily_market_schedule.csv --evaluation-labels data/weather_research/reports/city_daily_market_labels.csv --rejections data/weather_research/reports/city_daily_market_schedule_rejections.csv
python3 scripts/weather/build_climatology_forecasts.py --schedule data/weather_research/reports/city_daily_market_schedule.csv --labels data/weather_research/ghcn_city/labels_daily.csv --output data/weather_research/reports/city_climatology_forecasts.csv --rejections data/weather_research/reports/city_climatology_rejections.csv
python3 scripts/weather/build_persistence_forecasts.py --schedule data/weather_research/reports/city_daily_market_schedule.csv --labels data/weather_research/ghcn_city/labels_daily.csv --output data/weather_research/reports/city_persistence_forecasts.csv --rejections data/weather_research/reports/city_persistence_rejections.csv
python3 scripts/weather/evaluate_walk_forward.py --forecasts data/weather_research/reports/city_climatology_forecasts.csv --labels data/weather_research/reports/city_daily_market_labels.csv --output data/weather_research/reports/city_climatology_walk_forward.csv
python3 scripts/weather/evaluate_walk_forward.py --forecasts data/weather_research/reports/city_persistence_forecasts.csv --labels data/weather_research/reports/city_daily_market_labels.csv --output data/weather_research/reports/city_persistence_walk_forward.csv
python3 scripts/weather/evaluate_postprocessor_walk_forward.py --method bias --forecasts data/weather_research/reports/city_climatology_forecasts.csv --labels data/weather_research/reports/city_daily_market_labels.csv --output data/weather_research/reports/city_climatology_bias_walk_forward.csv
python3 scripts/weather/evaluate_postprocessor_walk_forward.py --method quantile --forecasts data/weather_research/reports/city_climatology_forecasts.csv --labels data/weather_research/reports/city_daily_market_labels.csv --output data/weather_research/reports/city_climatology_quantile_walk_forward.csv
python3 scripts/weather/evaluate_postprocessor_walk_forward.py --method emos --forecasts data/weather_research/reports/city_climatology_forecasts.csv --labels data/weather_research/reports/city_daily_market_labels.csv --output data/weather_research/reports/city_climatology_emos_walk_forward.csv
python3 scripts/weather/evaluate_postprocessor_walk_forward.py --method boosted --forecasts data/weather_research/reports/city_climatology_forecasts.csv --labels data/weather_research/reports/city_daily_market_labels.csv --output data/weather_research/reports/city_climatology_boosted_walk_forward.csv
python3 scripts/weather/evaluate_blend_walk_forward.py --forecasts data/weather_research/reports/city_climatology_forecasts.csv data/weather_research/reports/city_persistence_forecasts.csv --labels data/weather_research/reports/city_daily_market_labels.csv --output data/weather_research/reports/city_blend_walk_forward.csv --train-days 365 --test-days 30
python3 scripts/weather/build_city_market_schedule.py --markets data/weather_research/kalshi/markets.csv --labels data/weather_research/ghcn/labels_daily.csv --schedule data/weather_research/reports/phx_lv_market_schedule.csv --evaluation-labels data/weather_research/reports/phx_lv_market_labels.csv --rejections data/weather_research/reports/phx_lv_market_schedule_rejections.csv
python3 scripts/weather/build_climatology_forecasts.py --schedule data/weather_research/reports/phx_lv_market_schedule.csv --labels data/weather_research/ghcn/labels_daily.csv --output data/weather_research/reports/phx_lv_climatology_forecasts.csv --rejections data/weather_research/reports/phx_lv_climatology_rejections.csv
python3 scripts/weather/build_bucket_probabilities.py --markets data/weather_research/kalshi/markets.csv --forecasts data/weather_research/reports/phx_lv_climatology_forecasts.csv --output data/weather_research/reports/phx_lv_bucket_probabilities.csv
python3 scripts/weather/build_settled_market_labels.py --outcomes data/weather_research/kalshi/contract_outcomes.csv --labels data/weather_research/ghcn/labels_daily.csv --output data/weather_research/reports/phx_lv_settled_labels.csv --rejections data/weather_research/reports/phx_lv_settled_label_rejections.csv
python3 scripts/weather/evaluate_bucket_probabilities.py --probabilities data/weather_research/reports/phx_lv_bucket_probabilities.csv --labels data/weather_research/reports/phx_lv_settled_labels.csv --output data/weather_research/reports/phx_lv_bucket_skill.csv --rejections data/weather_research/reports/phx_lv_bucket_rejections.csv
python3 scripts/weather/build_nowcast_forecasts.py --state data/weather_research/derived_intraday_state_city/derived_intraday_state.csv --labels data/weather_research/ghcn_city/labels_daily.csv --output data/weather_research/reports/city_nowcast_forecasts.csv --evaluation-labels data/weather_research/reports/city_nowcast_labels.csv --rejections data/weather_research/reports/city_nowcast_rejections.csv
python3 scripts/weather/evaluate_walk_forward.py --forecasts data/weather_research/reports/city_nowcast_forecasts.csv --labels data/weather_research/reports/city_nowcast_labels.csv --output data/weather_research/reports/city_nowcast_walk_forward.csv --train-days 90 --test-days 30
python3 scripts/weather/build_sequence_windows.py --state data/weather_research/derived_intraday_state_city/derived_intraday_state.csv --labels data/weather_research/ghcn_city/labels_daily.csv --output data/weather_research/reports/city_sequence_windows.csv --rejections data/weather_research/reports/city_sequence_rejections.csv --window 12 --stride 3 --max-gap-minutes 120
python3 scripts/weather/probe_goes_cloud.py --date 2026-09-12 --hour 12 --output data/weather_research/reports/goes_cloud_availability.json
PYTHONPATH=/tmp/kalshi-goes-py python3 scripts/weather/extract_goes_cloud.py --input data/weather_research/goes/raw/g18_mcmipc_20260912T1201.nc data/weather_research/goes/raw/g18_mcmipc_20260912T1206.nc data/weather_research/goes/raw/g18_mcmipc_20260912T1211.nc --output data/weather_research/reports/goes_cloud_station_features.csv --stations phx klas
python3 scripts/weather/join_goes_cloud_state.py --asos data/weather_research/iem_backfill/asos_parsed.csv --cloud data/weather_research/reports/goes_cloud_station_features_20260911.csv --output data/weather_research/reports/goes_cloud_asos_state_20260911.csv --rejections data/weather_research/reports/goes_cloud_asos_rejections_20260911.csv
python3 scripts/weather/evaluate_goes_incremental.py --cloud data/weather_research/reports/goes_cloud_asos_state_20260911.csv --labels data/weather_research/ghcn/labels_daily.csv --output data/weather_research/reports/goes_incremental_rows_20260911.csv --rejections data/weather_research/reports/goes_incremental_rejections_20260911.csv
# CPC ONI climate regime index
python3 scripts/weather/cpc_indices.py --raw data/weather_research/cpc/oni.ascii.txt --output data/weather_research/cpc/oni.csv
# RTMA raw analysis objects (direct NOMADS archive; filtered endpoint unavailable)
curl -fsSL https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtma/prod/rtma2p5.20260912/rqirtma.2026091200.grb2 -o data/weather_research/rtma/raw/rqirtma.2026091200.grb2
```

The bounded core-market historical refresh used:

```bash
python3 scripts/weather/kalshi_historical.py \
  --series KXHIGHTPHX KXLOWTPHX KXHIGHTLV KXLOWTLV \
  --start 2026-07-04 --end 2026-09-11 --interval 1h \
  --max-markets 2000 --max-requests 5000
```

It retrieved 216 settled-market records, 72,658 trades, and 7,654 hourly
candles; responses and unavailable series remain preserved without synthesis.

The Kalshi historical collector was corrected to parse hourly event dates and
to merge, rather than overwrite, existing city archives. It then refreshed
metadata, public trades, and hourly candles through the API's reported
2026-07-14 cutoff for `KXTEMPNYCH`, `KXTEMPLAXH`, and `KXTEMPAUSH`.

The bounded authenticated NYC quote collector stores REST candles and trades
under `data/weather_research/kalshi_hourly/historical_quotes/`. Each response
is retained in `raw/` and indexed by `raw_manifest.jsonl` with endpoint,
retrieval timestamp, path, and SHA-256. A rerun never overwrites a changed
payload; it creates a receipt-suffixed raw path. These records are executable
quote/trade evidence only and do not reconstruct historical full-depth L2 or
source-publication clocks.
The collector also retains the paginated `/historical/markets` payloads and
writes `market_metadata.csv` with each market's open/close/settlement window,
result, and any source fields returned by the API. This metadata is kept
separate from the normalized NYC contract archive until event-level rules and
station provenance are reconciled.
Use `--metadata-only` for bounded cursor expansion when quote payloads are
already present; this archives market pages and metadata without re-fetching
candles/trades or applying per-market request sleeps.
The collector accepts `--series-ticker KXTEMPNYCH|KXTEMPLAXH|KXTEMPAUSH`;
NYC retains the established archive path, while LA and Austin use isolated
series-specific directories so their records cannot be mixed.
For larger bounded crawls, `collect_historical_nyc_quotes.py --workers N`
uses bounded parallel REST requests and sorts normalized outputs
deterministically; keep `N` conservative enough for the API rate limit. A
five-thousand-market test at `N=8` received HTTP 429 responses and was
stopped; the verified archive remains the bounded 1,652-market run (the
additional market was collected separately after the initial rate-limited
batch, with its raw candle/trade payloads indexed and hash-checked).
Use `--skip K --limit N --append` for resumable sequential batches; existing
candle keys `(market_ticker, end_period_ts)` and trade IDs are merged without
duplicate rows.
Per-market HTTP failures (including rate limits) are now written to
`historical_quotes/rejections.csv` and counted in the manifest; a failed
request cannot be mistaken for an empty but successful quote history.
`reconcile_historical_quote_raw.py` indexes payloads left by an interrupted
batch into `raw_quarantine_manifest.jsonl`; they remain hash-checked but are
never promoted to normalized executable evidence.
The archive quality gate cross-checks both `failed_markets` and the rejection
row count in that manifest.
Trade retrieval follows the API cursor until exhaustion, retaining each page
as its own immutable raw payload; the normalized trade table is deduplicated
by `trade_id` when batches are appended.

## Resulting coverage

- GHCN labels: 107,451 rows through 2026-09-10.
- GHCNh complete yearly station files cover 2020–2026;
  normalized observations now total 452,650 rows across PHX, LV, NYC, LA, and
  Austin (`ghcnh/observations_2020_2026.csv`). The expanded archive contains
  42 station-year files for 2020–2026, including the corrected Austin station.
- GHCNh local-day extrema: 12,210 station-day rows in
  `ghcnh/daily_extrema_2020_2026.csv`, with counts, extrema timestamps, and
  contributing raw hashes retained for each station/date.
- GHCNh/GHCN daily comparison: 7,326 overlapping station-days with per-city
  high/low error metrics in `reports/ghcnh_vs_ghcn_daily.json`.
- PHX/LV standard-time windows: 4,884 DST-safe station-day extrema rows in
  `ghcnh/settlement_window_extrema_2020_2026.csv` and SQLite, using the exact
  local-standard-time helper from `settlement_semantics.py`.
- Settlement-station ASOS: 20,736 auxiliary-city rows through 2026-09-11;
  the PHX/LV backfill contains 88,165 merged rows through 2026-09-11.
- Nearby ASOS: 137,550 rows through 2026-09-11.
- AWC current METAR snapshots: 197 normalized rows across NYC, Los Angeles,
  and Austin pulls, with separate observation-valid and local receipt
  timestamps; raw JSON is hashed and mirrored into SQLite `awc_metar`.
- GEFS member rows/features: the archive includes the prior 910,080 members
  plus the latest three-city refresh; current derived features total 2,544
  rows and each city/model response reports 30 observed temperature members.
- HRRR/NBM/GFS filtered raw files: 70 total, covering NYC/LA/Austin plus
  PHX/KLAS; HRRR leads 0–2, NBM leads 1–2, and GFS leads 0–2 across three
  recent 00Z cycles are
  retained where publicly available.
- Decoded point forecasts: 958 rows in `forecasts/model_forecasts_points.csv`,
  preserving raw-file hashes and GRIB message indices. The decoder runs in an
  isolated environment with `eccodes`; the project remains usable without it
  because raw GRIB files are retained.
- Kalshi city metadata/trades/candles: 75,040 / 612,998 / 32,076. The metadata
  archive now includes the six catalog daily HIGH/LOW series
  (`KXHIGHNY`, `KXLOWTNYC`, `KXHIGHLAX`, `KXLOWTLAX`, `KXHIGHAUS`, and
  `KXLOWTAUS`) in addition to the three hourly lines. Trades/candles remain a
  bounded public sample because the historical API cutoff is 2026-07-14. The
  latest bounded PHX/LV refresh added 216 settled-market records and 7,654
  hourly candle rows to the preserved city archive; the API returned
  historical coverage for `KXLOWTLV` in this window, while unavailable series
  were not synthesized.
- SQLite auxiliary tables mirror these files.
- The cross-source quality scan reports zero missing/invalid/future timestamps
  and zero forecast-manifest hash/path errors; it intentionally remains red
  on three duplicate ASOS keys (two AUS and one LAX re-delivery rows), which
  remain visible in the raw parse. `canonicalize_city_asos.py` now produces a
  separate 20,733-row deduplicated feature table with all three supersession
  decisions recorded; the canonical duplicate gate is green without deleting
  source evidence.
- The Open-Meteo historical GEFS requests for NYC, Los Angeles, and Austin,
  plus the bounded `single-runs` retry, were archived with hashes, but all 30
  ensemble member arrays are null for the requested 2026-01-01 through
  2026-09-10 window. The quality gate reports eight null historical responses
  as unavailable training data; they are retained as failed availability
  evidence, not used as forecasts. The `previous-runs` retry returned HTTP
  400 and is not treated as data. Historical deterministic GFS responses contain values but have
  retrieval-time provenance rather than original forecast-run timestamps, so
  they are not treated as point-in-time skill labels.
- The daily-market schedule adapter produced 4,143 event rows and 4,143
  matching GHCN proxy labels. Climatology and persistence evaluation produced
  zero deterministic timestamp/label rejections; the aggregate metrics are
  retained in `reports/city_baseline_skill_aggregate.csv`. This is a hurdle
  diagnostic only because the settlement source is not independently replayed.

## Still unavailable or not safely reconstructable

- Order-book readiness: `python3 scripts/weather/collect_orderbook.py
  --dry-run` passes and prints the configured WebSocket endpoint, channels,
  48 in-scope markets, and output directory. It does not connect; credentials
  are still required before any L2 JSONL can be captured.
- Kalshi Weather Index: `collect_weather_index.py` archived NYC’s public
  response (1,430 minute-series rows) and recorded explicit HTTP 400 results
  for the currently unsupported LA/Austin identifiers.

- NBM lead 0 and the attempted 2026-09-12 run returned HTTP 404; available
  2026-09-11 00Z leads 1–2 were collected. No missing NBM values were
  invented.
- GHCN's static `.dly` archive exposes final values but not observed
  publication timestamps; `label_available_ts` remains a conservative D+36h
  gate.
- IEM ASOS provides observation time, not dissemination/receipt time.
- IEM AFOS CLI is rolling and returned the existing 91 product versions; it
  cannot provide a multi-year historical CLI archive.
- Historical full-depth Kalshi order books are not exposed by the public
  historical API. Forward capture still requires authenticated WebSocket
  credentials; the repository now includes research-only capture/replay
  components but does not submit live orders.
- TWC settlement-era source payloads are licensed and were not fabricated from
  GHCN or hourly city lines.

## GHCNh bounded archive

GHCNh period-of-record station files are hundreds of megabytes. The bounded
collector captures a recent suffix while retaining the HTTP byte range, total
size, retrieval time, and SHA-256 in `ghcnh/manifest.json`:

```bash
python3 scripts/weather/collect_ghcnh_tail.py \
  --cities phx lv nyc la austin --tail-bytes 500000 \
  --output data/weather_research/ghcnh
```

The current manifest contains five partial station objects. They are not
silently promoted to normalized labels or treated as complete archives. In
addition, complete 2020–2026 yearly files are retained under
`ghcnh/by_year/<year>/` and merged into the normalized observation table.
The Austin auxiliary station was corrected to the registry station
`USW00013904`; the earlier `USW00013958` files remain preserved as a separate
raw/normalized station for auditability.

ECMWF collection/decoding uses the optional `ecmwf-opendata` and `eccodes`
packages; they are commented in `requirements.txt` because raw archival and
the rest of the pipeline must remain runnable without optional model tooling.

The current-year PSV files are also retained under
`ghcnh/by_year/2026/` with an integrity manifest generated by:

```bash
python3 scripts/weather/inventory_ghcnh_year.py --year 2026 \
  --input data/weather_research/ghcnh/by_year/2026 \
  --output data/weather_research/ghcnh/by_year/2026/manifest.json
```

Complete-year files can be normalized without touching settlement labels:

```bash
python3 scripts/weather/parse_ghcnh_year.py \
  --input data/weather_research/ghcnh/by_year/2026 \
  --output data/weather_research/ghcnh/observations_2026.csv \
  --rejections data/weather_research/ghcnh/parse_rejections_2026.csv
```
