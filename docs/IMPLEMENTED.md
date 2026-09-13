# Implemented — current, directly evidenced work

This file records implemented artifacts and verification evidence. It does not
promote proxy labels, current-only forecasts, or diagnostic scores into
settlement truth or trading claims.

Snapshot: 2026-09-13. This file records only what the working tree and its
verification commands prove, not aspirational design. The current working
tree contains the implementation and acquisition changes listed below; no
claim here implies a commit or publication has been made.

`docs/OPENCODE_REVIEW.md` records the bounded OpenCode review findings and the
follow-up changes made directly in this checkout.

`docs/REQUIREMENTS_MATRIX.md` maps each report requirement to its current
artifact, verification command, and remaining blocker.

The active-market registry now includes the current NYC `KXTEMPNYCHS` and Los
Angeles `KXTEMPLAXHS` intraday series plus their older identifiers, and the
prospective capture runner subscribes to all of them when open.

### Next-move architecture additions

`scripts/weather/feature_store.py` provides the general long-form PIT feature
store keyed by city, contract, target time, and decision time. It requires an
explicit availability clock, supports exact/observed-receipt/latency-scenario
vintages, selects only revisions available by the decision clock, and writes
explicit rejection rows for missing or invalid provenance. Seven focused tests
cover boundary admission, revision selection, latency assumptions, chronology,
and contract isolation.

`collect_orderbook.py` now archives every WebSocket frame in an append-only raw
JSONL stream with exchange time (when supplied), local receive/processing
times, latency, channel, sequence, hash, and parse status. Sequence gaps,
duplicates, reconnects, parser failures, and recovery requests are health
events. `replay_orderbook.py` maintains subscription-scoped multi-market books,
quarantines unresolved gaps, and emits tamper-evident checkpoints. These
changes enable prospective reconstruction but do not create historical L2
coverage; no credentialed live capture was attempted during this update.

## Edge-first sprint status

Intraday event-term archives now cover all three requested lines through the
public events endpoint: NYC 3,806 events/15,883 markets, Los Angeles 1,524
events/15,418 markets, and Austin 1,522 events/15,364 markets. Normalized
contracts preserve exact strike times, event-level Weather Company settlement
source text, station mapping, rules hashes, receipt clocks, and raw payload
hashes. `audit_intraday_city_readiness.py` applies the same PIT eligibility
checks to every city; the current report is intentionally non-passing because
quote and observation receipts are after historical decisions.

`build_intraday_edge_dataset.py` is the city-generic fail-closed adapter over
the strict NYC builder. It produces separate LA and Austin datasets and
rejection ledgers with identical clock checks; current runs admit 0/15,418 LA
rows and 0/15,364 Austin rows.

`generate_intraday_baseline_predictions.py --city {nyc,la,austin}` routes each
admitted dataset through the persistence probability baseline and immutable
manifest writer. All three current runs emit 0 predictions and 0 manifests
because their admitted datasets are empty.

`run_intraday_edge_pipeline.py` runs readiness, dataset construction, and all
three baseline steps deterministically and writes
`reports/intraday_edge_pipeline_status.json`; the current combined status is
`pass: false` for the documented pre-decision availability reason.

`run_intraday_capture.py` is the prospective read-only capture runner. It
polls the active three-city hourly series, AWC METAR, and the public TWC/Kalshi
portal, and requests authenticated REST books only when hourly tickers are
actually open and a credential path is explicitly supplied. The latest run
captured zero hourly tickers and recorded `no_hourly_markets_open`; it did not
read the repository credential file or submit orders.

`docs/EDGE_FIRST_DIRECTIVE.md` is now the active execution order. The strict
`build_nyc_edge_dataset.py` adapter emits
`reports/nyc_edge_first_dataset.csv`,
`reports/nyc_edge_first_rejections.csv`, and a machine-readable status report.
The current run admits zero rows and rejects all 15,883 retained contracts
(15,853 `late_observations`, 30 `late_observations_and_forecasts`): exact
KNYC TWC receipts are retained, but their receipt clocks post-date the
historical decisions. This is an explicit
evidence failure; no proxy label,
late source, or unverifiable coordinate is treated as a valid edge example.
`evaluate_edge_first.py` adds the downstream fail-closed evaluation boundary;
the current report is `not_evaluable` with zero rows and no metrics.
The dataset boundary now preserves eventual post-target `label_available_ts`
evidence and rejects only missing, pre-target, or mismatched label clocks;
post-target publication is expected for final settlement labels and is never
joined into decision-time features.
`generate_edge_baseline_predictions.py` adds the first persistence baseline
boundary; it emits no predictions or manifests until valid PIT rows exist.
`probe_active_nyc_market.py` archives a prospective open-market API probe; the
latest response contains zero open KXTEMPNYCH markets, so no synthetic future
contract is created.
`collect_historical_nyc_quotes.py` uses the dedicated historical Kalshi REST
endpoints with each market's actual open/close window. A bounded run archived
2,052 NYC hourly candle rows and 24,491 trades with raw per-market responses;
metadata-only cursor coverage now reaches 5,004 NYC bounded tickers and every
candle ticker.
- `load_sqlite.py` now loads the bounded three-city REST archives into
  `historical_quote_market_metadata`, `historical_quote_candles`, and
  `historical_quote_trades`. The current query layer contains 5,064 metadata
  rows, 2,112 deduplicated candle rows, and 24,925 trade rows across NYC, Los Angeles, and
  Austin, with zero CSV/SQLite count mismatches.
This corrects the earlier assumption that only the crawl snapshot was
available; historical full-depth L2 remains unavailable from REST.
The archived `LOCALTEMPERATURE.pdf` terms were independently text-extracted
and searched for coordinate/station clauses; they describe listing-level
station selection but do not publish coordinates. The supplied
`settlement_locations.json` registry reconciles KNYC to Central Park at
40.77900,-73.96925, and the settlement-target gate now passes with that
explicit provenance.

## NYC hourly contract archive (report 2)

`collect_kalshi_series.py` archives the public `KXTEMPNYCH` series response and
cursor-crawled nested event/market payloads. Raw JSON is hash- and
receipt-stamped, while normalized `events.csv` and `markets.csv` preserve the
settlement-source metadata. The current archive has 3,806 events and 15,883
markets and is loaded into SQLite tables `kalshi_hourly_events` and
`kalshi_hourly_markets`.

The captured series metadata also records the announced source transition:
the `product_metadata.important_info` notice says NYC hourly resolution moves
from The Weather Company to Synoptic Data for the 11am–12pm ET market on
September 10, 2026. This is preserved as source evidence; no continuous
settlement value is inferred from airport observations.

`collect_twc_kalshi.py` now archives the linked public portal endpoints
(`/kalshi/api/metar` and `/kalshi/api/climate/primary`) and normalizes KNYC,
KLAX, and KAUS hourly observations plus daily station reports while retaining
raw payload hashes and receipt timestamps. The capture contains 13,506
target-station hourly rows and 1,110 daily rows across Jul 6–Sep 13, 2026 and
repeated receipts; rows append/deduplicate by immutable snapshot path. It is
loaded into SQLite and passes its dedicated provenance gate. The daily archive
contains 610 official rows and 167 explicit no-report rows.
Each manifest snapshot now records `availability_basis=receipt_upper_bound`
and `source_publication_time_observed=false`; PIT joins therefore treat the
receipt as a conservative upper bound rather than claiming source latency.

`parse_kalshi_hourly_contracts.py` normalizes all 15,883 archived NYC hourly
markets into explicit target time, threshold/operator, bucket bounds,
settlement-source, station identity/mapping method, rules-hash, and raw-provenance fields. Its SQLite table and
quality gate are synchronized with the CSV output.

`audit_settlement_source_transition.py` records and hashes the series notice
announcing the September 10, 2026 TWC-to-Synoptic change, applies the effective
UTC cutoff to every contract, and fails on source-era mismatches. The current
archive is entirely pre-transition (15,883 TWC rows, zero post-transition
rows), so the absence of Synoptic history is explicit rather than inferred.

`join_kalshi_twc_labels.py` creates a fail-closed exact-time label adapter from
the public KNYC portal observations to those contracts. It retains source
temperature, raw hash/path, observation status, and `label_available_ts`; the
after the July–September backfill, the current archive yields 15,883 exact
matches for 15,883 crawled markets rather than interpolating or substituting
ASOS. The portal is public evidence and does not claim a licensed final-TWC
export. Source-derived labels
use the contract's whole-degree bucket boundary (the portal reports tenths of a
degree), while preserving the raw decimal temperature for audit.

The same tracking now includes `deep-research-report (2).md`, focused on NYC
hourly temperature markets. Its current AWC observation path and the report's
statistical/trading controls are listed below; licensed TWC labels,
continuous low-latency capture, and unavailable historical model feeds remain
explicitly unclaimed.

## 1. New P0 semantics layer (untracked, present)

- `scripts/weather/settlement_semantics.py` — single source of truth for the
  NWS local-standard-time settlement window (PHX UTC-7 year-round; KLAS UTC-8
  all year, i.e. 01:00 PDT–00:59 PDT during DST) and whole-degree bucket
  geometry; `normal_bucket_probabilities` maps one continuous Gaussian to a
  gap-free, non-overlapping, open-tailed partition that sums to one and
  rejects gaps/overlaps/duplicate tickers.
- `scripts/weather/pit.py` — `available_asof` enforces both issue and receipt
  time ≤ decision time; missing timestamps fail closed.
- `scripts/weather/build_bucket_probabilities.py` — research transform (not a
  trading signal or order tool) producing `bucket_probabilities.csv`; rejects
  late/missing issue or receipt and inconsistent event metadata.
- `scripts/weather/test_p0_semantics.py` — 26 hand-written fixtures covering
  the KLAS DST window, partition coherence, fail-closed PIT gates, and the CLI.
- `scripts/weather/asof_forecasts.py` (modified) — `known_forecasts` /
  `valid_forecasts_asof` now delegate to `pit.available_asof` (issue + receipt)
  and fail closed on missing timestamps.

These gates are enforced (and only enforced) at the code level covered by
`test_p0_semantics.py`. `data_quality_gates.py` now provides the corresponding
read-only scan across the acquired city labels, ASOS, CLI, forecast manifest,
and historical-forecast raw responses. The latest scan found no
missing/invalid timestamps or manifest hash/path errors. Re-delivered ASOS
rows and eight null historical forecast responses remain preserved in raw
archives but are explicitly deduplicated or quarantined; conservative
publication-time assumptions keep P0 integrity partial.

Verification (exact):
- `python3 -m unittest test_p0_semantics` → **Ran 26 tests in 0.005s — OK**
- `python3 -m py_compile scripts/weather/*.py` → **passes (exit 0)**
- `ruby -e "require 'yaml'; %w[openapi.yaml asyncapi.yaml].each { |f| YAML.load_file(f) }"` → **passes (exit 0)**
- `python3 scripts/weather/data_quality_gates.py --output data/weather_research/reports/data_quality_gates.json` → **runs; raw ASOS re-deliveries and all eight null historical forecast responses are explicitly resolved/quarantined; `pass=false` for the empty edge-first dataset, baseline/evaluation/manifests, and inactive-market probe**

## 2. Pipeline components present as code (not all with data in-tree)

- Ingest/download: `iem_asos.py`, `backfill_asos.py`, `collect_nearby_asos.py`,
  `ghcn_daily.py`, `kalshi_meta.py`, `kalshi_trades_candles.py`,
  `kalshi_historical.py`, `nws_cli_archive.py`, `nomads_forecasts.py`,
  `model_archive.py`, `gefs_ensemble.py`, `gefs_historical.py`,
  `collect_orderbook.py`, `schedule_gefs.py`.
- Parse/derive: `parse_nearby_asos.py`, `build_intraday_state.py`,
  `solar.py`, `gefs_features.py`, `gefs_calibration.py`,
  `build_daily_ensemble_forecasts.py`, `build_climatology_forecasts.py`,
  `postprocess_station_bias.py`, `settlement_analysis.py` (regenerates
  `docs/settlement_analysis.md`).
- Validation/query: `validate.py` (writes reports), `load_sqlite.py`
  (rebuildable `data/weather_research/kalshi_weather.sqlite`), plus the P0
  layer in §1.
- Checked-in contracts: `openapi.yaml` (REST), `asyncapi.yaml` (WebSocket).

Each script compiles (`py_compile` above). The focused P0 and P1 suites are
separate from the data validator and do not prove full-data correctness.

Report-2 additions directly evidenced through 2026-09-13:

- `collect_awc_metar.py` captured current pulls (197 normalized rows spanning
  NYC, Los Angeles, and Austin aviation stations, including nearby stations)
  into raw JSON plus
  `awc/metar.csv`, preserving observation-valid and local receipt timestamps,
  raw snapshot paths, and SHA-256 snapshot history.
- `load_sqlite.py` mirrors that snapshot into `awc_metar`; the artifact
  inventory and data-quality gate report 197 normalized rows across the scoped
  stations with no hash or clock
  violations.
- `run_awc_poll.py` provides the report-2 one-minute polling boundary with a
  bounded `--iterations` mode for scheduled jobs and a continuous mode when
  set to zero; its defaults are the exact settlement stations KNYC, KLAX, and
  KAUS. It delegates every pull to the hashed collector and has cadence
  validation tests.
- `run_twc_poll.py` provides the matching hourly bounded/continuous polling
  boundary for exact KNYC/KLAX/KAUS portal observations and daily reports;
  it delegates persistence to `collect_twc_kalshi.py`, preserves receipt
  clocks, and has deterministic cadence/date tests.
- `build_decision_features.py` provides the report-2 PIT integration boundary
  for contracts, observations, and forecasts. It emits source IDs and feature
  JSON only when receipt clocks are available by decision time, and writes
  explicit rejection reasons otherwise; the current run used exact KNYC TWC
  rows, produced 15,883 late-clock rejections, and zero eligible rows without
  fabricating history.
  Contracts with a settlement station are filtered to that exact station;
  nearby observations cannot silently become primary settlement evidence.
  Its payload derives deterministic temporal slopes, running extrema,
  station-gradient summaries, forecast quantiles/spread/member counts, and
  forecast-minus-observation residuals when those source fields are present.
- `collect_lamp.py` discovers the latest NOAA NOMADS LAMP cycle and archived a
  663,658-byte `lmp.t1945z.lavtxt.ascii` bulletin with retrieval time, URL, and
  SHA-256; the archive gate passes. A station parser/GLMP decoder is not yet
  claimed.
- `parse_lamp.py` now parses the archived `lavtxt.ascii` bulletin into 19,812
  long-form station/field/valid-time rows, retaining initialization, receipt,
  raw path, and hash provenance. `lamp_station_forecasts` validates every row;
  the parser preserves categorical fields and does not invent missing TMP/DPT
  values when a bulletin omits them.
- `collect_glmp_temperature.py` archived the latest NOAA GLMP CONUS 2-m
  temperature GRIB2 object (15,853,194 bytes) with a hash/receipt manifest;
  the raw-object provenance gate passes. Point extraction remains gated on a
  pinned GRIB decoder environment.
- `decode_glmp_temperature.py` decoded the live GLMP object to 50 NYC, Los
  Angeles, and Austin hourly point rows with Celsius-to-Fahrenheit conversion,
  forecast leads, PIT timestamps, raw hashes, and normalized longitudes; the point provenance gate
  passes and SQLite mirrors the rows in `glmp_temperature_points`.
- `multiple_testing.py` provides a centered moving-block max-statistic
  reality-check-style comparison across candidate return streams.
- `risk_sizing.py` provides fee-aware fractional Kelly, shared event caps,
  moving-block drawdown tails, and recommendation-only outputs. OpenCode’s
  review found and the direct tests verify the fee-basis and duplicate-ticker
  fixes in `allocate_event`.

## 3. P1 baseline-study infrastructure

- `scripts/weather/evaluate_forecast_skill.py` accepts explicit forecast and
  label CSVs, requires issue/receipt/decision timestamps plus city, target date,
  lead, and model identity, and rejects invalid or temporally unsafe rows with
  deterministic reasons.
- It selects the earliest label strictly after the decision time and reports
  MAE and Gaussian CRPS grouped by model/version, city, high/low type, lead,
  and target month. It does not invent climatology, persistence, NBM, HRRR,
  GFS, or GEFS values.
- `scripts/weather/city_focus.py` registers the active auxiliary city layer
  (NYC, Los Angeles, Austin) and performs a read-only audit of label/CLI/ASOS/
  market row counts, duplicate keys, timestamps, and series IDs. It explicitly
  reports that the retained city Kalshi lines are hourly and are not verified
  daily settlement labels.
- `scripts/weather/audit_city_daily_markets.py` inventories the six daily
  NYC/LA/Austin catalog series, their event date ranges, resolution counts, and
  event-specific settlement-source names/URLs. The generated audit keeps
  `rules_reproduced=false` because Weather Company payloads are not available
  for independent replay.
- `scripts/weather/canonicalize_city_asos.py` creates an 81,847-row canonical
  ASOS feature table and an 81,851-row decision manifest. The four duplicate
  raw `(station, valid_utc)` keys are explicitly resolved as superseded
  re-deliveries; raw observations remain preserved. The quality gate confirms
  zero duplicate keys in the canonical table while keeping the raw-source
  duplicate count visible.
- `scripts/weather/test_city_focus.py` covers registry identity and missing-root
  behavior.
- `scripts/weather/build_daily_ensemble_forecasts.py` aggregates hourly
  member guidance into one daily maximum per ensemble member using each city's
  fixed local-standard-time window, then emits mean/spread/member count plus
  issue and receipt timestamps. It does not substitute hourly Kalshi series or
  invent historical forecast runs; generated identifiers are research targets.
- `scripts/weather/test_daily_ensemble_forecasts.py` covers standard-time
  windowing, member-level maxima/minima, distribution summaries, city aliases,
  and PIT timestamps.
- `scripts/weather/build_climatology_forecasts.py` creates a monthly
  climatology hurdle-rate forecast from only prior same-city/month labels that
  were available by the requested decision time. Target-day and future labels
  are excluded, and missing history is reported as a deterministic rejection.
- `scripts/weather/build_persistence_forecasts.py` creates a latest-prior-value
  hurdle forecast with a configurable trailing spread window and explicit
  rejection output when no prior label is available. It shares the forecast
  CSV contract used by the skill evaluator.
- `scripts/weather/build_city_market_schedule.py` converts the acquired daily
  NYC/LA/Austin market metadata into 4,143 event-level research schedules and
  joins GHCN proxy labels without future spill. `summarize_skill.py` aggregates
  the resulting monthly metrics with sample weighting. The generated baseline
  artifacts are under `data/weather_research/reports/`; both models have zero
  evaluator rejections. These are proxy-label hurdle results, not claims about
  Weather Company settlement accuracy or NWP skill.
- `scripts/weather/evaluate_walk_forward.py` applies 365-day training / 30-day
  chronological test folds to those diagnostics. The current run produces 48
  folds and 3,781 test predictions with zero evaluator rejections; fold outputs
  remain descriptive because the baselines are proxy-label models.
- `scripts/weather/evaluate_postprocessor_walk_forward.py` evaluates station
  bias, empirical quantile, and EMOS corrections with fold-specific as-of
  clocks, allowing prior labels to train later forecasts without test leakage.
  The current 3,781-test proxy run has zero evaluator rejections; bias is mixed
  by city/type, quantile worsens aggregate CRPS, and EMOS is unstable, so none
  is promoted.
- `scripts/weather/build_nowcast_forecasts.py` converts leakage-safe running
  ASOS extrema into observation-only Gaussian distributions using prior
  residuals by city/type/hour. The current run emits 41,084 forecasts; a
  90-day/30-day walk-forward diagnostic contains 26,896 test predictions with
  zero evaluator rejections (MAE/CRPS 1.663/1.368). It is deliberately not
  presented as an NWP-controlled gain.
- `scripts/weather/boosted_postprocess.py` provides an optional scikit-learn
  HistGradientBoosting conditional-quantile postprocessor. Its outer-fold
  diagnostic produced 3,781 test predictions with zero evaluator rejections,
  but MAE/CRPS 7.128/5.247 versus 6.469/4.575 for climatology, so it is not
  promoted.
- `scripts/weather/build_sequence_windows.py` creates 8,914 fixed 12-row,
  label-available-after-feature sequence windows from the city ASOS state;
  `probe_goes_cloud.py` records public GOES ABI availability without claiming
  cloud retrieval or skill. These are P4 data contracts, not trained-model
  results.
- `scripts/weather/test_climatology_forecasts.py` covers prior-label selection
  and fail-closed future-only history.
- `scripts/weather/postprocess_station_bias.py` implements a transparent,
  fallback-group station/model residual correction that only trains on labels
  available by each historical decision time. It preserves the original
  distribution spread and emits correction magnitude and training count.
- `scripts/weather/test_postprocess_station_bias.py` covers prior residual
  fitting and target/future-label exclusion.
- `scripts/weather/decode_point_forecasts.py` decodes the acquired HRRR/NBM
  files at each registered city point when `eccodes` is available, retaining
  source hashes and duplicate GRIB message indices. The current decode produced
  123 normalized point rows; raw GRIB remains authoritative.
- `scripts/weather/test_decode_point_forecasts.py` covers unit conversion and
  fail-closed handling of unknown GRIB fields.
- `scripts/weather/emos.py` implements a transparent Gaussian EMOS-style
  affine mean/spread postprocessor with PIT-safe training and fallback groups;
  `test_emos.py` covers fit/application and future-label exclusion. It is not
  presented as a measured skill improvement because the required historical
  forecast/label overlap is still absent.
- `scripts/weather/test_forecast_skill.py` covers valid aggregation, lead and
  month grouping, late/missing timestamps, target leakage, missing labels,
  malformed values, CRPS, and output files.
- `scripts/weather/evaluate_nowcast.py` evaluates running ASOS high/low
  extrema against final GHCN labels by city and local hour, requiring label
  availability strictly after each feature timestamp. The current acquisition
  produced 72 summary rows and 20,648 eligible state rows; this is an
  observation-only diagnostic, not an NWP-controlled skill claim.
- `scripts/weather/test_evaluate_nowcast.py` covers the feature-as-of gate and
  rejection of labels available before a feature.
- `scripts/weather/evaluate_bucket_probabilities.py` evaluates complete
  probability partitions with multiclass Brier score and log loss, requiring
  issue/receipt timestamps no later than decision and settlement labels after
  decision. `test_evaluate_bucket_probabilities.py` covers scoring and late
  forecast rejection.
- `scripts/weather/validation_controls.py` supplies chronological event-level
  walk-forward folds with an explicit embargo and probability reliability-bin
  summaries. `test_validation_controls.py` covers the split invariant and
  calibration aggregation; it does not imply a model result.
- `scripts/weather/quantile_postprocess.py` implements a PIT-safe empirical
  residual quantile postprocessor with p10/p50/p90 outputs, spread conversion,
  fallback groups, and training-count provenance. Its tests cover distribution
  construction and future-label exclusion; no outer-fold gain is claimed.
- `scripts/weather/blend_forecasts.py` implements a PIT-safe convex blend of
  forecast means and spreads, with inverse-error weights, mixture variance,
  and explicit member-weight provenance. `test_blend_forecasts.py` covers
  weight preference and no-training behavior; no economic or outer-fold gain
  is claimed.

Verification: `python3 scripts/weather/test_city_focus.py` (2 passed),
`python3 scripts/weather/test_daily_ensemble_forecasts.py` (5 passed),
`python3 scripts/weather/test_climatology_forecasts.py` (2 passed),
`python3 scripts/weather/test_postprocess_station_bias.py` (2 passed),
`python3 scripts/weather/test_decode_point_forecasts.py` (2 passed),
`python3 scripts/weather/test_forecast_skill.py` (7 passed),
`python3 -m py_compile scripts/weather/*.py` (exit 0). No P1 skill result is
claimed because the required point-in-time forecast/label joins have not been
run. A dry run of the generated 33-row current GEFS archive against the
checked-in labels produced 0 eligible predictions and 38 deterministic
`no_label_found` rejections because labels end on 2026-09-10 while forecasts
start on 2026-09-11. The evaluator accepts `nyc`, `la`/`los_angeles`, and `austin` as auxiliary
forecast cities, but their Kalshi settlement rules are not audited.

## 4. Data actually present in this checkout

- `data/weather_research/kalshi_weather.sqlite` (rebuilt after the acquisition
  pass) contains auxiliary-city tables: `city_observations` 81,847 rows,
  `city_daily_labels` 107,451, `city_nws_cli` 91,
  `city_kalshi_markets` 74,824, `city_kalshi_trades` 482,378,
  `city_kalshi_candles` 32,076, current `gefs_features` 2,544 (with the
  prior member archive plus the latest three-city refresh), plus
  `model_forecasts` 94 NOAA HRRR/NBM/GFS manifest rows,
  `model_forecast_points` 958 decoded rows, `forecast_rejections` 3 explicit
  NBM HTTP-404 rows, and `rtma_point_features` 30
  decoded rows. Rebuild with
  `python3 scripts/weather/load_sqlite.py` after source files change.
- The PHX/LV normalized tier has been restored from the parked archive into
  `data/weather_research/{ghcn,iem,solar,kalshi}` and preserved verbatim under
  `data/weather_research/legacy_phx_lv/`. It currently loads 60,663 daily
  labels, 1,527 ASOS observations, 1,680 markets, 3,212 trades, 662 hourly
  candles (plus 24 daily candles), and 1,680 contract outcomes into the SQLite
  query layer.
- `evaluate_blend_walk_forward.py` now provides a leakage-safe outer-fold
  blend diagnostic over the city climatology and persistence forecasts: 48
  non-overlapping folds and 3,781 predictions, weighted MAE/CRPS 5.697/4.064.
  The result remains diagnostic because it has no historical NWP constituent
  or authoritative Weather Company labels.
- `build_settled_market_labels.py` derives finalized-market labels from the
  normalized PHX/LV outcomes without fabricating prices or labels. The
  resulting PIT climatology probability artifact contains 1,680 coherent
  bucket rows; 264 finalized events pass point-in-time evaluation and every
  accepted partition sums to one.
- The filtered NOMADS archive now includes PHX and KLAS: 10 additional current
  HRRR/NBM GRIB2 files (leads 0–2 for HRRR and 1–2 for NBM) and 82 decoded
  nearest-grid-point rows, with manifest hashes and model timestamps retained.
- `extract_goes_cloud.py` now consumes three retained public G18 ABI MCMIPC
  NetCDF4 objects and emits a short temporal station-neighborhood cloud proxy
  series for PHX/KLAS
  (3×3 infrared C13 brightness temperature, DQF clear fraction, source hash,
  and coverage time). This is an extracted feature artifact, not yet a scored
  nowcast improvement.
- `join_goes_cloud_state.py` provides a fail-closed as-of join from GOES scans
  to ASOS observations, retaining cloud age, DQF quality, and raw source hash;
  the Sep 11 overlap currently produces six PHX/KLAS rows.
- `evaluate_goes_incremental.py` provides a research-only, transparent
  observation-baseline versus cloud-adjusted MAE diagnostic with separate
  summary and rejection outputs. The current Sep 11 run rejects all six rows
  because the available proxy labels end on Sep 10; this is an evidence gap,
  not a positive or negative skill result.
- Three current RTMA `rqirtma` GRIB2 objects and one variable-bearing 00Z
  analysis object are retained under `data/weather_research/rtma/` with a
  SHA-256 manifest. `decode_rtma_point.py` emits 30 nearest-grid-point values
  for the five registered stations; no values are inferred where decoding is
  unsupported.
- Added the public CPC ONI index collector and normalized 919 seasonal rows;
  SQLite now exposes them through `cpc_oni` with source URL and retrieval time.
- `data_quality_gates.py` now validates RTMA manifest hashes/feature timestamps
  and CPC ONI schema presence; both gates are green in the current report.
- The same quality gate now verifies every decoded forecast point against its
  source GRIB path and SHA-256; all 958 decoded points across 66 source files
  pass. The decoder ran in an isolated ecCodes environment; raw files remain
  authoritative and the decoded rows are still prospective/current guidance,
  not historical OOS evidence.
- RTMA quality checks also enforce variable-specific physical ranges (including
  Kelvin temperatures, percent cloud cover, and metre visibility); all 30
  current RTMA rows pass. Manifest retrieval and feature valid timestamps are
  also checked against the audit clock.
- CPC ONI quality checks now enforce finite year, sea-surface-temperature, and
  anomaly ranges plus valid UTC retrieval timestamps; all 919 current rows
  pass.
- `audit_artifact_inventory.py` emits a machine-readable count snapshot for the
  key CSV and SQLite artifacts, including the four-object RTMA manifest,
  and records its own UTC generation time to prevent stale snapshots and
  documentation counts from drifting.
- The inventory also compares forecast, RTMA, and CPC CSV counts to SQLite and
  emits `sqlite_count_mismatches`; missing SQLite tables are treated as zero so
  partial databases are reported as drift. The current list is empty.
- `load_sqlite.py` now performs a true rebuild of every loaded table, deleting
  rows absent from refreshed normalized files before upserting. A sample refresh
  followed by rebuild was verified to remove stale observation rows.
- `audit_artifact_inventory.py` now inventories the complete acquired source
  tier and compares canonical city ASOS plus deduplicated city-candle keys to
  their SQLite tables. The 2026-09-12 inventory reports zero
  `sqlite_count_mismatches` across observations, labels, markets, trades,
  candles, forecasts, RTMA, CPC, and auxiliary-city data.
- `collect_ghcnh_tail.py` archives bounded, SHA-256-verifiable GHCNh station
  suffixes for PHX, Las Vegas, NYC, Los Angeles, and Austin. The manifest
  records HTTP byte ranges and explicitly marks each object as partial; these
  five objects are source evidence, not a claimed full period-of-record
  replacement.
- Downloaded 2026 GHCNh by-year PSV files for all five stations (five complete
  yearly source objects, 24–31 MB each) and generated a hash/size manifest with
  `inventory_ghcnh_year.py`. These raw files remain separate from the legacy
  GHCN label table until a full schema-aware normalization pass is approved.
- `parse_ghcnh_year.py` now performs that schema-aware normalization for the
  complete 2020–2026 files: 452,650 temperature observations were emitted with
  Celsius-to-Fahrenheit conversion, UTC timestamps, quality/report fields, and
  raw-file SHA-256 provenance and manifest/file receipt timestamps. Malformed
  or temperature-missing rows are counted in the year-range rejection file.
- `compare_ghcnh_asos.py` cross-checks exact station/time keys against IEM
  ASOS. The current PHX/LV overlap has 1,464 numeric matches (MAE 0.0434°F);
  the auxiliary-city overlap has 13,776 matches (MAE 0.0467°F). These are
  source-consistency diagnostics, not settlement certification.
- `data_quality_gates.py` now validates GHCNh normalized rows, source hashes,
  UTC event times, plausible Fahrenheit ranges, and duplicate keys. The current
  gate is green for all 452,650 rows; hash computation is cached per raw file
  so the audit remains bounded.
- `build_ghcnh_daily_extrema.py` derives 12,210 station-local daily high/low
  diagnostics from the complete 2020–2026 archive, retaining observation
  counts, extrema timestamps, and all contributing raw hashes. The derived
  `ghcnh_daily_extrema` SQLite table and quality gate both pass; these are
  sampled observations rather than official CLI settlement labels.
- `compare_ghcnh_ghcn_daily.py` produces a read-only 7,326 station-day
  cross-source comparison and exposed the Austin station identity mismatch;
  the registry station `USW00013904` is now archived and used for Austin
  comparisons, while the prior `USW00013958` evidence remains preserved.
- `build_settlement_window_extrema.py` derives 4,884 PHX/LV extrema over the
  exact local-standard-time 24-hour windows (including Las Vegas DST), and
  loads them into `settlement_window_extrema` for oracle diagnostics.
- `collect_homr.py` archives NCEI HOMR `date=all` station-history JSON for the
  five registered stations (PHX, LV, NYC, LA, Austin), with response validation,
  retrieval timestamps, byte sizes, and SHA-256 manifest entries. These
  metadata records support station-move/instrumentation review and do not alter
  weather labels.
- `collect_ecmwf_open.py` archives a credential-free ECMWF IFS 00Z surface
  temperature forecast (steps 0–12h) with request metadata and SHA-256. The
  raw GRIB2 is retained and decoded with `eccodes` when available.
- `data_quality_gates.py` validates the ECMWF raw path, hash, byte size,
  retrieval clock, and request metadata; the current one-object archive passes.
- `decode_ecmwf_point.py` decodes the ECMWF GRIB2 with `eccodes` in the
  isolated runtime at the five registered points and emits 25 2-m temperature
  rows (steps 0–12h). `load_sqlite.py` rebuilds these in
  `ecmwf_point_features`; raw hash and receipt timestamps are retained.
- `data_quality_gates.py` now validates ECMWF point rows against their raw
  source hash, timestamp ordering/receipt clock, station scope, units, value
  ranges, and duplicate keys. The current 25-row point artifact passes.
- `decode_ecmwf_ensemble.py` decodes three ECMWF IFS perturbation members at
  0/3/6/9/12 hours for all five registered cities (75 rows) and loads them into
  `ecmwf_ensemble_points`. Member IDs, receipt timestamps, and raw hashes are
  retained; the ensemble quality gate is green.
- `summarize_ecmwf_ensemble.py` converts those member rows into 25 explicit
  city/lead distributions with member count, mean, spread, quantiles, and
  threshold probabilities. It does not impute unavailable members.
- `collect_era5.py` adds a credential-aware Copernicus ERA5 request contract:
  it records dataset/date/variables/area and refuses to run without
  `CDS_API_KEY`, so no reanalysis values are fabricated or mistaken for
  operational forecasts. Its fail-closed behavior is tested.
- `data_quality_gates.py` now validates the HOMR manifest, raw JSON hashes,
  retrieval timestamps, JSON shape, and GHCND station identity. All five HOMR
  objects pass this gate; internal NCDC IDs are not confused with GHCND IDs.
- `parse_homr.py` extracts HOMR identifiers, relocations, dated descriptions,
  coordinates, elevations, platforms, updates, and remarks into 457 auditable
  records, and `load_sqlite.py` rebuilds them in
  `homr_station_history` without mixing metadata into labels or forecasts.
- `build_intraday_state.py` now accepts explicit input/output paths, enabling a
  reproducible 88,165-row PHX/LV backfill state artifact without overwriting
  the active trailing state; solar geometry was expanded to 4,164 PHX/LV dates.
- Present auxiliary data: `gefs/gefs_members.parquet` + features + historical
  raw, and the city lines `city_asos/asos_parsed.csv` (20,736),
  `city_nearby_asos/nearby_asos_parsed.csv` (137,550),
  `city_nws_cli/daily_climate_cli.csv` (91), `ghcn_city/labels_daily.csv`
  (107,451), `solar_city/solar_features.csv` (762),
  `derived_intraday_state_city/derived_intraday_state.csv` (20,711),
  `kalshi_historical_city/{markets,trades,candles}.csv` (74,824 / 482,378 /
  19,255). The market metadata includes the six daily NYC/LA/Austin HIGH/LOW
  catalog series; trades/candles are a bounded sample. Note these are
  non-PHX/LV lines and thus outside the four-market
  AGENTS.md scope; flagged here for accuracy only.
- Documented historical evidence that is **not rerunnable in this tree**:
  `docs/settlement_analysis.md` (1,584-bucket reconstruction; 95.2% exact /
  100% whole-°F rounded agreement) and `docs/settlement_evidence.md`.

`collect_weather_index.py` archives Kalshi's public minute-resolution Weather
Index with configuration versions, retrieval timestamps, hashes, and explicit
unsupported-city failures; its `weather_index` quality gate passes.
`parse_weather_index.py` normalizes the successful NYC response into 1,430
timestamped Fahrenheit rows with contributor/status metadata and raw hashes.
- `orderbook_features.py` now provides a CLI that replays captured order-book
  JSONL through `replay_orderbook.Book` and emits timestamped microstructure
  CSV features for downstream research.
- `collect_orderbook.py` now supports Kalshi's RSA-PSS access-key handshake via
  a Git-ignored `KALSHI_CREDENTIAL_FILE`, signs each reconnect, and enforces a
  bounded `--run-seconds` shutdown. A read-only hourly NYC subscription was
  authenticated on 2026-09-13 but its archived ticker had empty depth. A
  separate active daily captures now audit 310 cumulative messages. They add
  REST-matched populated snapshots for PHX and NYC; process-session sequence
  resets remain explicit, and no KXTEMP target ticker has been captured. Daily
  books remain distinct from the
  strict NYC hourly edge dataset.
- `collect_historical_nyc_quotes.py` now writes each REST market-list,
  candle, and trade payload immutably and records endpoint, receipt timestamp,
  raw path, and SHA-256 in `kalshi_hourly/historical_quotes/raw_manifest.jsonl`.
  It also writes `market_metadata.csv` for the bounded market windows and
  source fields. Changed reruns receive receipt-suffixed paths instead of
  overwriting prior evidence. The current archive uses the v3 manifest
  contract; this still does not reconstruct historical L2 or source-publication
  clocks. Bounded parallel workers are available for rate-limited expansion,
  but an eight-worker 5,000-market test hit HTTP 429; the verified archive
  currently contains 5,004 NYC metadata rows, 2,052 candle rows, and 24,491
  trades before SQLite natural-key deduplication.
- The same collector is parameterized for `KXTEMPLAXH` and `KXTEMPAUSH` with
  isolated archives. Current bounded probes contain 30 markets each; LA has
  393 trades and Austin has 41, with 61 indexed raw payloads and 30 market
  metadata rows per city. Immutable raw and metadata gates pass; they remain
  auxiliary evidence only.
- `audit_artifact_inventory.py` now surfaces per-city indexed raw-payload,
  quarantined-payload, and failed-market counts alongside normalized rows, so
  the coverage ledger cannot hide provenance gaps.
- `evaluate_edge_first.py` now computes guarded binary Brier/CRPS, log loss,
  calibration error, realized signal edge, and net P&L by explicit OOS fold
  when rows carry pre-decision quote clocks, probability predictions, and
  model-fit end clocks. It also emits decile reliability bins and maximum bin
  calibration error. The current NYC artifact remains empty, so no metrics are
  emitted from production data.
- `generate_live_daily_diagnostic.py` provides a fail-closed bridge from
  active daily market metadata, captured quote receipts, and the latest
  pre-quote GEFS025 distribution to contract probabilities. The September 13
  refreshed run emitted 22 quote-complete but uncalibrated/unlabeled rows and
  14 explicit quote-field rejections; it intentionally
  writes no prediction manifests, paper telemetry, edge, or P&L result.
  Rows lacking finite bid, ask, spread, or depth are rejected explicitly by
  the generator and surfaced by the data-quality audit.
- `audit_daily_source_transition.py` applies the supplied August 14 daily
  NWS→TWC notice and validates active CLINYC/CLILAX/CLIAUS rule text. It
  verified 36 post-transition rows; historical daily rows without event-level
  source metadata remain explicitly rejected.
  The main data-quality audit machine-enforces a non-empty, rejection-free
  passing report for this source-era check.

## 5. Known provenance blockers

- **TWC settlement source is licensed and uncaptured.** Current-era
  (2026-08-14 onward) contracts settle to The Weather Company; this project
  has no point-in-time TWC feed, so TWC-era labels are GHCN proxy only.
- **NWS CLI archive is rolling-only.** IEM AFOS retains ~7 days; a multi-year
  request returned only the window tail (2025-12-30). Full NWS-era
  reproduction needs an official long-term product archive.
- **GHCN label gate is synthetic.** `label_available_ts` is D+36h, not an
  observed publication time; the two most recent finalized outcome dates have
  no label yet.
- **IEM ASOS has no dissemination timestamp.** `valid_utc` is observation
  time only; NWS/MADIS QC delays cannot be reconstructed.
- **No historical or continuous hourly L2 archive yet.** The collector is
  credentialed live-capable (RSA access-key signing, reconnect/backoff,
  bounded runs, and per-message flush). A read-only hourly NYC connection
  returned an empty archived snapshot, while a separate active daily capture
  produced 36 populated books and 174 deltas. A read-only REST snapshot for
  `KXHIGHTPHX-26SEP13-T108` matched its contemporaneous WebSocket snapshot
  (39 levels, zero mismatches); this is daily-market evidence only. Continuous
  hourly capture remains open, and no maker-fill or executable-edge claim is
  made for the hourly strategy.
- `replay_orderbook.py` now fails closed after a sequence gap: subsequent
  deltas are ignored until a new snapshot arrives, and fill simulation emits
  an explicit quarantine result instead of using incomplete depth.
- `reconcile_orderbook.py` provides a deterministic WebSocket-versus-REST
  level/quantity comparator with mismatch output; it is implemented and
  tested. `collect_rest_orderbook.py` archives authenticated REST responses
  with receipt timestamps and SHA-256 hashes, and the daily reconciliation
  artifact now passes for one ticker. The main data-quality gate still
  requires a populated, gap-free current WebSocket epoch for the target
  strategy.
- `paper_trading_ledger.py` now validates the referenced prediction manifest's
  full PIT schema (not merely the manifest path) before emitting any paper
  trading records; malformed, missing, or non-probabilistic manifests fail
  closed.
- **NWP archives are thin.** NOMADS operational retention is short (70 filtered
GRIB2 files retained); the live GEFS manifest is integrity-gated (33 receipts,
  30 observed temperature members per response), but member history is
  prospective-only and the
  Open-Meteo historical endpoint returns deterministic seamless forecasts, not
  members; a GRIB decoder is not assumed installed.
- **Kalshi historical window is limited** (earliest retained event dates
  2026-01-14 PHX / 2026-02-04 LV); no full multi-year event history in-tree.

## 6. Non-claims (keep as constraints, not assertions)

- **Not real-money ready.** No order placement or live trading exists.
  `simulate_candle_execution.py` is an offline research simulator only;
  `build_bucket_probabilities.py` is a research transform and does not place
orders.

`probe_active_city_markets.py` now also writes an immutable, receipt-stamped
CSV of public top-of-book bid/ask prices and displayed sizes for every open
market. These snapshots are usable for prospective executable-price joins but
are explicitly not historical full-depth L2 or maker-fill evidence.

The fresh 72-row snapshot was joined to the latest GEFS distributions by
`generate_live_daily_diagnostic.py`: 72 quote-complete daily probability/price
rows and 0 quote-field rejections were produced in
`reports/live_daily_diagnostic_current.csv`. The rows are uncalibrated,
unsettled diagnostics only; they do not create manifests, paper fills, or a
profitability claim.

`summarize_live_price_comparison.py` writes
`reports/live_price_comparison_summary.json`: the current 72-row snapshot has
27 positive candidate YES edges under each zero-cost scenario, but explicitly
reports `settled_rows=0`, `realized_edge=null`, `net_pnl=null`, and
`status=diagnostic_only`.

Its credential and market-scope fail-closed behavior is covered by
`test_run_intraday_capture.py`; the complete suite currently passes 301 tests
with one environment-dependent skip.
- The four-market PHX/LV dataset is present again as normalized CSVs and in
  SQLite, but authoritative settlement-source provenance and complete historical
  NWP/order-book coverage remain unresolved.

`robustness_scenarios.py` implements the report's stress-test harness for feed
delays, late NWP cycles, stale-observation outages, calibration shocks,
threshold proximity, and market-stress subsets. It emits Brier/log-loss and filtered/rejected counts,
normalizes naive timestamps as UTC, and fails closed on malformed fields. It
does not fabricate NYC outcomes; substantive scores remain data-gated.

`probability_calibration.py` adds the report's binary calibration layer with
Platt logistic scaling and isotonic regression. Both maps preserve probability
ordering; it requires callers to provide
the calibration partition explicitly, reports training-row counts, handles
small samples with an identity fallback, and uses bounded/backtracking
regularized optimization for stable Platt parameters.

## 7. Immutable prediction manifests (report 2)

`scripts/weather/prediction_manifest.py` implements the report-2 requirement
that every prediction be reproducible from an immutable manifest containing
`decision_ts`, `market_ticker` and `target_time_utc` (so the manifest joins its
contract), `feature_version`, `model_version`, `calibrator_version`,
`source_run_ids`, `observation_ids`, `rules_hash`, `code_commit`, and a
probability `prediction`. It is stdlib-only and:

- fails closed on missing/empty or unparseable PIT, provenance, id-list,
  market-identity, contract, or rules fields, on code commits that are not a
  7–40 hex git hash or `HEAD`, and on predictions that are not a finite number
  in `[0, 1]` (never writes a partial file);
- resolves `source_run_ids` / `observation_ids` against optional provenance
  indexes (CSVs or in-memory mappings): an id missing from a supplied index
  fails closed, and an index record whose receipt/issue/availability timestamp
  is present but after `decision_ts` also fails closed (metadata-absent rows
  still resolve by id);
- verifies `market_ticker`, `target_time_utc`, and `rules_hash` against a
  supplied contract index (e.g. `kalshi_hourly/contracts.csv`);
- serializes deterministic sorted-key JSON (`sort_keys=True`, newline
  terminated) so identical inputs reproduce identical bytes;
- writes immutably and idempotently: identical content at an existing path is
  a no-op, different content at an existing path raises, and new files are
  written atomically via `os.replace` with parents created only after
  validation, including nested `predictions/model_version=<v>/` layouts;
- provides a CLI that either builds one manifest from explicit flags or one
  manifest per row of an existing forecast CSV, optionally joined to a
  contract CSV and source/observation indexes, with repeatable
  `--source-run-ids` / `--observation-ids` and an
  `--organize-by-model-version` mode.

`data_quality_gates.py` now exposes a `prediction_manifest` check that
recursively audits every `predictions/**/*.json` file, revalidates each dict
with the module's fail-closed rules (including contract and optional
`predictions/source_index.csv` / `predictions/observation_index.csv` context),
rejects unparseable JSON or `decision_ts` after the audit clock, rederives
each file's content hash and flags filename drift, rejects duplicate logical
manifests, and rejects `model_version=<v>` directory mismatches. The check is
intentionally red until a model actually emits manifests.
`audit_artifact_inventory.py` counts prediction manifests recursively
(`predictions/**/*.json`) and pairs them with a `sqlite_prediction_manifests`
table (zero when absent), so drift is surfaced once prediction storage lands.
`test_prediction_manifest.py` covers validation, provenance resolution,
contract/code-commit checks, deterministic encoding, immutable/idempotent
writes, recursive gate fail-closed cases, the CLI, and inventory counts.

## 8. Operational readiness control (report 2)

`operational_readiness.py` is a deterministic, stdlib-only control-plane
evaluator for research and paper trading. It consumes a JSON health snapshot
and fails closed when feed/model ages, probability consistency, clock drift,
order-book sequence recovery, settlement-rule verification, calibration error,
or daily drawdown violate explicit thresholds. It emits stable reason codes and
never connects to Kalshi or submits orders. `test_operational_readiness.py`
covers healthy, missing/stale telemetry, threshold overrides, deterministic
reason ordering, and the CLI.

`paper_trading_ledger.py` adds the report-2 paper-trading artifact boundary.
It converts conservative candle-simulator rows into append-only
`would_have_order` and `simulated_fill` JSONL records keyed to a valid
prediction manifest, rejects duplicate IDs and missing manifest references,
and never submits orders. Settlement records can be appended through the same
validated schema when authoritative outcomes become available.

`build_provenance_indexes.py` creates the source-run and observation indexes
used by those manifests only from rows with real availability clocks, raw
paths, and hashes. The promoted exact-station index has 57 forecast source
files and 98 KNYC/KLAX/KAUS observations; 86 nearby-station rows are explicitly scoped
out and zero hard provenance rows are rejected. This clears provenance source
readiness but does not imply historical contract PIT coverage.

`run_paper_trading.py` wraps this ledger with bounded or continuous ingestion:
it validates the immutable manifest, reads refreshed execution rows, and appends
only unseen hypothetical records. It is transport-agnostic and has no broker or
order-placement capability.

`deployment_gate.py` evaluates the report's complete real-money checklist:
conservative OOS EV, rolling-window stability, calibration, regime and
perturbation robustness, fees/slippage, live-paper agreement, outage controls,
and contract-rule verification. Missing evidence fails closed, and even a
passing result carries `authorized=false`.

`audit_forecast_completeness.py` audits the report's required HRRR, NBM, LAMP,
and GEFS variables individually. The generated report lists every missing
field; it does not treat a nonzero row count as proof of a complete forecast
vector.

`audit_settlement_targets.py` separately audits event-level settlement source,
target timestamp, rules hash, and station-resolution evidence. Current
contracts pass source/target/hash and KNYC/Central Park registry resolution;
source-specific TWC display-coordinate differences remain explicit.

`live_schedule.py` provides the report-2 cadence contract as deterministic JSON:
active-contract discovery, continuous market streams, minute weather polling,
model-run detection, feature/inference/risk refresh, settlement retries, daily
QC, recalibration, challenger retraining, and monthly review. It is declarative
only; it does not launch jobs or authorize live trading.

The SQLite query layer now also creates the report-2 trading-state schemas:
`decision_features`, `prediction_manifests`, `paper_orders`, `paper_fills`,
`paper_settlements`, `orderbook_events_live`, and `market_trade_events`.
They are empty-safe and inventory-visible; no rows are synthesized without
valid manifests or prospective market telemetry.

The SQLite layer also exposes the report-2 canonical source schemas
`settlement_temperature`, `surface_observation`, and `model_runs`, including
separate valid/received/published clocks and raw provenance fields. They are
empty-safe and remain unpopulated where the required authoritative source or
publication timestamp is unavailable.

NOMADS forecast manifests now distinguish model initialization from availability
with `available_time_utc` and `available_time_method`; existing rows use their
recorded ingestion receipt as a conservative availability bound. The forecast
quality gate validates this clock and rejects missing, malformed, or future
availability timestamps.

`settlement_semantics.py` now exposes `GaussianTemperatureDistribution` with
`cdf`, `prob_above`, and inverse `quantile` accessors. The bucket probability
engine reuses this single monotone distribution, preserving coherent
gap-free probabilities across all active thresholds; it remains a transparent
baseline pending settlement-aligned calibration.

`build_model_runs.py` materializes 118 canonical NOAA/Open-Meteo/GLMP run
records into `reports/model_runs.csv` and SQLite, retaining initialization and
ingestion clocks while marking publication time as `unobserved` when it is not
supplied by the source.

`model_ladder.py` materializes `reports/model_ladder.json`, an explicit M0–M13
eligibility manifest with input row counts and missing-data reasons. It does
not claim model performance or permit training when a required artifact is
empty; the current PIT replay therefore leaves M6–M13 marked `data_missing`.
Its M4 readiness count excludes aviation-only LAMP fields and accepts only
temperature-bearing LAMP/GLMP rows.

`training_readiness.py` materializes a chronological, event-level
train/calibration/test plan with optional embargo. It reports `data_missing` or
`insufficient_history` instead of fabricating folds when target-date coverage
is absent.

`backfill_city_asos.py` now emits a manifest for all 99 cached monthly IEM
archives, including request interval, URL, SHA-256, raw path, and explicit
cached-file-mtime receipt method. The `city_asos_archive` gate verifies those
records without overstating dissemination-time provenance.
