# Kalshi PHX/LV daily-temperature research dataset

This repository builds a point-in-time research foundation for exactly four
Kalshi series: `KXHIGHTPHX`, `KXLOWTPHX`, `KXHIGHTLV`, and `KXLOWTLV`. It does
not model, trade, or collect weather for other cities or weather products.

## Settlement facts — inspect per event, never assume a single era

| City | Kalshi series | airport / ICAO | NWS WFO / CLI | local timezone |
| --- | --- | --- | --- | --- |
| Phoenix | `KXHIGHTPHX`, `KXLOWTPHX` | Phoenix Sky Harbor, `KPHX` / GHCN `USW00023183` | Phoenix (`KPSR`), `CLIPHX` | `America/Phoenix` (MST year-round) |
| Las Vegas | `KXHIGHTLV`, `KXLOWTLV` | Harry Reid International, `KLAS` / GHCN `USW00023169` | Las Vegas (`KVEF`), `CLILAS` | `America/Los_Angeles` (PST/PDT) |

The binding source is stored in every row of `data/weather_research/kalshi/events.csv`.
Historical event payloads cite the NWS daily climate products above; current
payloads cite [The Weather Company](https://weather.com/kalshi). This is a
material rule change. NWS CLI and NOAA GHCN records are therefore excellent
reconstruction/label sources for the historical NWS era, but they are **not a
substitute for TWC settlement** for events whose `settlement_source_name` is
The Weather Company.

The actual market rule text is retained in the raw Kalshi series payloads.
For current contracts it says the final maximum/minimum reported by TWC is
binding, warns preliminary values can differ due to rounding/conversion, and
permits Kalshi to await a corrected non-materially-erroneous revision. Market
metadata records the contract's UTC `open_time`, last-trading `close_time`,
and `settlement_ts`.

Outcome dates are local civil calendar days. Phoenix does not observe DST;
Las Vegas does. Do not derive a Las Vegas outcome date by subtracting a fixed
eight hours: use `America/Los_Angeles`. Current contract rules close at 11:59
PM local; the API's close timestamp reflects the appropriate DST offset.

Buckets are mutually exclusive integer-Fahrenheit ranges exposed by Kalshi:
tails are `<= N` and `>= N`, and internal buckets are inclusive whole-degree
ranges such as 103–104. `markets.csv` parses those into nullable
`bucket_floor_f`/`bucket_ceil_f`. The current contract rule expresses a tail
as “less than 103°” while its displayed label is “102° or below”; use the
parsed ranges, not string comparisons. GHCN stores tenths °C, so validation
also tests nearest-whole-°F conversion. The supplied sample obtains 100%
agreement after that conversion; it does not prove TWC and NWS will always
agree.

NWS normally publishes an initial/final-looking CLI for yesterday shortly
after local midnight (examples: `CLIPHX` roughly 00:25Z, `CLILAS` roughly
08:30Z), but publication can be revised and the historical archive must be
timestamped. Treat publication time as data, not a fixed clock assumption.

## Data already collected

`data/weather_research/ghcn/labels_daily.csv` contains 32,175 Phoenix dates
(1933-06-01–2026-09-08) and 28,488 Las Vegas dates
(1948-09-06–2026-09-08). The file is a final-label dataset only; its
`label_available_ts` is a deliberately conservative synthetic gate (D+36h)
because GHCN does not publish row-level release times.

`data/weather_research/iem/raw/` preserves a 30-day raw IEM CSV archive;
`asos_parsed.csv` contains 1,527 source observations and parsed METAR fields
and remarks. `kalshi/` contains 789 events / 1,680 contracts plus a bounded
recent sample of 3,212 public trades and 662 hourly candles. The full current
coverage and quality checks are in
[`data_quality_report.md`](data/weather_research/reports/data_quality_report.md).

`data/weather_research/nws_cli/daily_climate_cli.csv` is the timestamped raw
NWS-CLI layer. It currently holds the available rolling IEM archive window
(observed here: climate dates 2025-12-30 and 2026-09-04–2026-09-09) and
preserves multiple issuance versions for the same climate date. IEM's
public AFOS interface currently retains only about seven days, so it cannot
backfill five years of CLI text by itself.

`data/weather_research/forecasts/manifest.csv` and `forecasts/raw/` retain
immutable filtered GRIB2 with init/valid time, ordered lead, coordinates,
request URL, and SHA-256 for a bounded sample (HRRR 2026-09-10 12Z `f000`,
NBM 2026-09-11 00Z `f001`, each PHX and KLAS).

## Reproduce or extend

```bash
python3 scripts/weather/run_sample.py

# Backfill 5 years of raw observations, retaining raw source CSVs.
python3 scripts/weather/iem_asos.py --start 2021-01-01 --end 2026-01-01

# Re-fetch all discoverable PHX/LV contract metadata.
python3 scripts/weather/kalshi_meta.py

# Larger historical Kalshi pull: retrieve only data exposed by the API.
python3 scripts/weather/kalshi_trades_candles.py --max-events-per-series 100
python3 scripts/weather/build_intraday_state.py
python3 scripts/weather/test_p0_semantics.py
python3 scripts/weather/collect_nearby_asos.py --days 30
python3 scripts/weather/load_sqlite.py

# Preserve all available raw/revised NWS CLI products in a date window.
python3 scripts/weather/nws_cli_archive.py --start 2026-09-05 --end 2026-09-11

# Archive point-in-time model-run GRIBs only after choosing bounded init/lead
# sets; the script rejects unexpectedly large global files by default.
python3 scripts/weather/model_archive.py --model hrrr --init 2026-09-10T00 --leads 0 1 2

# Refresh slow climate-regime covariates and validate all source provenance.
python3 scripts/weather/cpc_indices.py --raw data/weather_research/cpc/oni.ascii.txt --output data/weather_research/cpc/oni.csv
python3 scripts/weather/data_quality_gates.py --output data/weather_research/reports/data_quality_gates.json
python3 scripts/weather/audit_artifact_inventory.py --output data/weather_research/reports/artifact_inventory.json

# Decode a retained RTMA analysis object at the registered station points.
/tmp/kalshi-grib/bin/python scripts/weather/decode_rtma_point.py \
  --input data/weather_research/rtma/raw/rtma2p5.t00z.2dvaranl_ndfd.grb2_wexp \
  --output data/weather_research/rtma/rtma_point_features.csv

python3 scripts/weather/validate.py
```

`run_sample.py` is a bounded refresh of the active trailing PHX/LV tier. It
rewrites the active trailing CSVs from its selected windows; preserve larger
backfills and their raw payloads separately (for example,
`iem_backfill/` and `reports/phx_lv_intraday_state_backfill.csv`). Rebuild
SQLite afterward so its tables mirror the current normalized files.

### P0 semantics before model work

`scripts/weather/settlement_semantics.py` explicitly computes the NWS
local-standard-time settlement interval (including Las Vegas DST behavior) and
maps a single continuous temperature distribution to the event's complete,
mutually exclusive Kalshi bucket set. To materialize model output after a
future forecast postprocessor exists, provide a CSV with
`event_ticker`, `decision_time_utc`, `mean_f`, `stddev_f`,
`forecast_issue_time`, and `source_receipt_time`:

```bash
python3 scripts/weather/build_bucket_probabilities.py \
  --forecasts /path/to/point_in_time_distributions.csv
```

The command fails closed when the forecast was issued or received after its
declared decision timestamp, or when either timestamp is missing or unusable,
so no row can reach the research probabilities without a valid issue and
receipt at or before the decision time. It creates research probabilities
only; it does not estimate a trading edge or place orders.

The P1 skill evaluator is similarly input-driven and does not fabricate
values. See [`docs/REQUIREMENTS_MATRIX.md`](docs/REQUIREMENTS_MATRIX.md) for a
requirement-by-requirement evidence map, alongside the open-work tracker and
implemented-status log.
baseline forecasts. Once an intact point-in-time forecast CSV and label CSV
are available, run:

```bash
python3 scripts/weather/evaluate_forecast_skill.py \
  --forecasts /path/to/forecasts.csv \
  --labels /path/to/labels.csv \
  --output /path/to/skill_summary.csv \
  --rejections /path/to/skill_rejections.csv
```

It reports MAE and Gaussian CRPS by model/version, city, high/low type, lead,
and target month. Invalid or temporally unsafe rows are retained as rejection
records; P1 results remain diagnostic until the restored PHX/LV inputs are
joined to point-in-time NWP and authoritative settlement evidence.

The evaluator accepts the active auxiliary forecast-city keys `nyc`, `la`
(`los_angeles`), and `austin` as well as the legacy `phx`/`lv` keys. This does
not infer or change Kalshi settlement rules: NYC/LA/Austin contract metadata
and settlement stations must be supplied and audited separately.

To inspect the current NYC/Los Angeles/Austin input identity and provenance
without mutating data:

```bash
python3 scripts/weather/city_focus.py --research-root data/weather_research
```

The audit is read-only and warns when retained city market series are hourly
rather than verified daily settlement labels.

For the active auxiliary ensemble archive, daily maxima and minima are reduced
inside each member before the ensemble summary is calculated:

```bash
python3 scripts/weather/build_daily_ensemble_forecasts.py \
  --members data/weather_research/gefs/gefs_members.parquet \
  --output /tmp/daily_ensemble_forecasts.csv
```

This preserves forecast issue and receipt timestamps and uses fixed local
standard-time windows. The current archive is prospective-only and does not
overlap the checked-in labels, so it is not yet a skill result.

The deterministic hurdle-rate baseline can be built from the same schedule:

```bash
python3 scripts/weather/build_climatology_forecasts.py \
  --schedule /tmp/daily_ensemble_forecasts.csv \
  --labels data/weather_research/ghcn_city/labels_daily.csv \
  --output /tmp/climatology_forecasts.csv \
  --rejections /tmp/climatology_rejections.csv
```

It uses only prior, available same-month labels and fails closed when history
is unavailable.

To measure the observation-only nowcast baseline by local hour:

```bash
python3 scripts/weather/evaluate_nowcast.py
```

The output is a diagnostic for how quickly observed extrema converge to final
labels; it is not a claim of improvement over NWP.

For bucket-level probability scoring, provide one settled-market label per
event and evaluate the generated partition:

```bash
python3 scripts/weather/evaluate_bucket_probabilities.py \
  --probabilities /path/to/bucket_probabilities.csv \
  --labels /path/to/settled_market_labels.csv \
  --output /path/to/bucket_skill_summary.csv \
  --rejections /path/to/bucket_skill_rejections.csv
```

The collector requires credential configuration before it may connect:

```bash
python3 -m pip install websocket-client
export KALSHI_API_KEY=... KALSHI_USER_ID=...
python3 scripts/weather/collect_orderbook.py --run-seconds 3600
```

It writes received millisecond timestamps and raw WebSocket envelopes to
append-only JSONL files. It reconnects and re-subscribes; consumers must use
message sequence identifiers where Kalshi supplies them and detect gaps.

## Point-in-time contract

Never put `daily_climate` labels, finalized market results, later forecast
runs, or revised CLI products into features before their recorded publication
time. `valid_utc` means weather observation time; `received_ts` means local
ingestion; model data must have both initialization and valid time. The
included GHCN gate is safe but not precise; a serious NWS-era backtest should
backfill timestamped raw CLI text from IEM and replace it with the product
issuance timestamp. TWC-era settlement reproduction remains a licensed-source
gap and must be treated as such.

See [data_sources.md](data_sources.md),
[data dictionary](docs/data_dictionary.md), and the generated
[quality report](data/weather_research/reports/data_quality_report.md). The
source-specific conclusion is in [settlement evidence](docs/settlement_evidence.md)
and the fuller, reproducible [settlement analysis](docs/settlement_analysis.md).

The current research database is
`data/weather_research/kalshi_weather.sqlite`. It is an idempotent query layer
over immutable raw payloads and the normalized CSVs, populated by
`load_sqlite.py`.

### Open-Meteo GEFS ensemble layer

`gefs_ensemble.py` collects NYC, Los Angeles, Austin, Chicago, DC, Boston, and
Miami from the Open-Meteo ensemble endpoint. It defaults to `ncep_gefs025`; use
`--models ncep_gefs05 ncep_gefs_seamless` to test the alternatives. Raw JSON is
archived under `data/weather_research/gefs/raw/`; long-form member rows are
written to `gefs_members.parquet`, and `gefs_features.py` writes means, spread,
quantiles, and `P(T >= threshold)` columns.

```bash
python3 scripts/weather/gefs_ensemble.py --cities nyc dc --models ncep_gefs025
python3 scripts/weather/gefs_features.py
python3 scripts/weather/schedule_gefs.py --interval-minutes 60
python3 scripts/weather/gefs_historical.py --api historical --start 2025-01-01 --end 2025-01-02
python3 scripts/weather/load_sqlite.py
```

The collector requests Fahrenheit temperature units and preserves every
available member. `forecast_run_time` is the UTC retrieval timestamp when a
stable initialization timestamp is absent from the live response; the raw
payload and manifest remain authoritative. Check the manifest's member count
instead of assuming a model returned 31 members. In the 2026-09-12 collection,
all three model identifiers returned 30 `temperature_2m` members; no separate
control member was present in those responses, so this implementation does not
invent a 31st member. Historical API responses are
archived separately and can be joined to timestamped actuals with
`gefs_calibration.py`; they cannot recreate a historical live 31-member
archive.
### HRRR/NBM forecast backfill

Use `scripts/weather/nomads_forecasts.py` to poll NOAA NOMADS GRIB-filter
endpoints for small PHX/KLAS subsets. Raw GRIB2 files and `forecasts/manifest.csv`
preserve point-in-time provenance. Install `python-eccodes` (or `wgrib2`) to
decode; without a decoder the raw files remain authoritative. Before training,
apply `scripts/weather/pit.py:available_asof` (wrapped by
`asof_forecasts.py:known_forecasts`) and require both
`initialization_time_utc <= decision_time_utc` and
`source_receipt_time <= decision_time_utc`; missing timestamps fail closed.
For features whose valid time must already have occurred, restrict further with
`valid_forecasts_asof`.

GEFS coverage, historical counts, and the distinction between live members,
historical deterministic forecasts, NOMADS operational files, and the NOAA
retrospective archive are documented in
[`docs/gefs_data_coverage.md`](docs/gefs_data_coverage.md).
