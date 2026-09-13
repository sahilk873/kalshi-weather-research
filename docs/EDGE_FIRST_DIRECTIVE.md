# Edge-first implementation directive

Status: active, fail-closed (2026-09-13)

This sprint prioritizes only evidence that can support a genuine NYC
`KXTEMPNYCH` edge claim. A row enters the edge dataset only when its contract
source era and station mapping are verified, its target and decision clocks are
ordered, all feature sources were available by decision time, and its settled
label is present. Late, missing, proxy, or unverifiable rows are rejected with
an explicit reason.

## Current evidence

| Stage | Artifact | Result |
| --- | --- | --- |
| Contract/source era | `settlement_source_transition.json`, `settlement_target_audit.json`, `settlement_locations.json` | 15,883 pre-transition TWC rows; source-era and station registry audits pass for KNYC/Central Park using the supplied IEM/NWSCLI coordinates |
| Contract terms | `kalshi_hourly/terms/manifest.json` and archived `LOCALTEMPERATURE.pdf` files | Terms require listing-level station selection; the supplied registry reconciles KNYC to Central Park at 40.77900,-73.96925 with an explicit source caveat |
| PIT features/labels | `nyc_edge_first_dataset.csv`, `nyc_edge_first_rejections.csv` | 0 accepted / 15,883 rejected; 15,853 have late exact-station observations and 30 have late observations plus forecasts |
| Baseline predictions | `model_ladder.json` | M0–M5 inputs are inventoried, but no NYC prediction is promoted without an admitted PIT row |
| Persistence baseline | `generate_edge_baseline_predictions.py`, `nyc_edge_baseline_status.json` | 0 predictions / 0 manifests; runner stops on the empty admitted dataset, requires resolvable source/observation indexes, and defaults to `reports/provenance_indexes/` |
| Prospective market availability | `probe_active_nyc_market.py`, `kalshi_hourly/active_probe/latest.json` | Latest public API probe found 0 open KXTEMPNYCH markets; raw response and receipt hash are archived for the next poll |
| Historical executable inputs | `collect_historical_nyc_quotes.py`, `kalshi_hourly/historical_quotes/`, `kalshi/rest_orderbook/` | Historical REST acquisition currently loads 5,004 NYC metadata rows, 2,052 NYC candles, and 24,491 NYC trades (2,112 / 24,925 across the three city quote tables). Duplicate market-period rows remain visible in raw CSV and are deduplicated by the SQLite natural key. 6,442 additional NYC payloads from an interrupted/rate-limited crawl are explicitly quarantined and hash-checked. A read-only authenticated REST book matched one contemporaneous daily WebSocket snapshot (39 levels, zero mismatches). Neither endpoint reconstructs historical NYC hourly L2 depth or proves pre-decision quote availability. |
| Three-city event terms | `kalshi_hourly/kxtemp*_terms/contracts.csv`, `audit_intraday_city_readiness.py` | Public event crawl recovers NYC 3,806 events/15,883 markets, LA 1,524/15,418, and Austin 1,522/15,364 with exact target/source/station/rules provenance. Readiness is still red: zero pre-decision quote/observation alignments in each city, so these terms cannot by themselves support a price comparison. |
| LA/Austin historical quote inputs | `kalshi_hourly/kxtemplaxh/historical_quotes/`, `kalshi_hourly/kxtempaush/historical_quotes/` | Bounded probes pass immutable-raw and metadata gates: LA 30 markets / 30 candles / 393 trades / 61 payloads / 30 metadata rows; Austin 30 markets / 30 candles / 41 trades / 61 payloads / 30 metadata rows. These are quote/trade evidence, not settlement-publication clocks or full-depth L2 |
| OOS evaluation | `edge_first_evaluation.json`, `training_readiness.json`, deployment gate | `not_evaluable` with zero rows; evaluator additionally requires a pre-decision quote-availability clock before any rolling OOS metrics can run |
| Manifests/telemetry | `prediction_manifests`, paper ledger | No rows emitted without valid PIT predictions and immutable manifests |
| Provenance indexes | `build_provenance_indexes.py`, `reports/provenance_indexes/provenance_index_status.json` | 57 forecast source files and 98 exact KNYC/KLAX/KAUS observations indexed with raw hashes, raw paths, and availability clocks; 86 nearby-station rows are explicitly scoped out, 0 hard provenance rows rejected, and indexed raw files pass path/hash integrity checks. This is source readiness, not historical contract PIT evidence |

The absence of admitted rows is a data-availability result, not an edge
result. Proxy labels, in-sample scores, late forecasts, empty quote tables, and
unverified settlement coordinates are never promoted.

The data-quality gate audits the provenance-index artifact directly; the
provenance check now passes, while the separate NYC dataset and execution
gates remain red.

The live daily diagnostic is also audited for executable quote completeness;
the refreshed retained file has 22 complete rows and 14 explicit rejections
for missing bid/ask/depth fields. It remains uncalibrated and diagnostic-only,
so it cannot support an edge claim.

## Prospective input refresh

On 2026-09-13 UTC the live-input collectors completed a bounded refresh. AWC
returned 17 fresh NYC/Los Angeles/Austin METAR rows at
`2026-09-13T16:50:36Z` (197 rows retained in the normalized archive), and the
public TWC/Kalshi portal archive now contains 13,506 hourly and 1,110 daily rows
through the September 13 refresh (30 retained snapshots; latest receipt
`2026-09-13T16:14:17.178179Z`). These receipt clocks are conservative upper bounds, not proof of the
licensed source's publication time; rows must still pass the PIT latency and
decision-clock checks. The refresh did not create an admitted historical NYC
decision row, so no prediction or edge result is inferred from it.

The authenticated Kalshi WebSocket collector also captured 36 active daily
high/low tickers across NYC, Los Angeles, and Austin: the cumulative raw file
now contains 310 messages across bounded read-only sessions. Two additional
populated daily snapshots (PHX and NYC) were captured and reconciled against
REST; process-session sequence resets remain explicit and no KXTEMP target
ticker is present. The raw JSONL and
hash/coverage audit are retained under `data/weather_research/kalshi/ws/` and
`reports/orderbook_capture_20260913.json`. No hourly KXTEMP* market was open
in the same probe, so these daily books are not substituted into the strict
NYC hourly dataset.

The corresponding open-market discovery is archived at
`kalshi_city/active_probe/latest.json`: 36 daily contracts were open and zero
hourly KXTEMP contracts were open at the receipt time.

A later read-only probe at `2026-09-13T17:39:30Z` found 72 open daily
contracts (12 per city/side) and still zero NYC/LA/Austin hourly KXTEMP
contracts. This newer snapshot supersedes the earlier daily count but does not
change the hourly PIT gate.

A contemporaneous GEFS refresh retained 90,720 member rows (30 members per
city/model) and produced 94 daily ensemble distribution diagnostics with
receipt clocks. They remain forecast-input evidence only; no daily prediction,
settlement label, or edge claim is promoted from this single cycle.

For completeness, `generate_live_daily_diagnostic.py` joined 36 active daily
books to the latest GEFS025 run available before each captured quote and wrote
`reports/live_daily_diagnostic_predictions_20260913.csv`. The refreshed file
contains 22 quote-complete rows and 14 explicit quote-field rejections; the
accepted rows are uncalibrated and unlabeled, so the artifact is diagnostic-only
and does not create manifests, paper fills, edge, or P&L.

The latest public top-of-book snapshot was joined separately as
`reports/live_daily_diagnostic_current.csv`: 72/72 daily rows had executable
bid/ask fields and 0 quote-field rejections. This remains uncalibrated and
unsettled diagnostic evidence, outside the strict hourly sprint; no edge or P&L
is inferred.

The daily source-era audit at `reports/daily_source_transition_20260913.json`
validates all 36 active rows against the supplied August 14 NWS→TWC notice and
the registered CLINYC/CLILAX/CLIAUS products. Historical daily rows lacking
event-level source metadata remain rejected; no source era is inferred for
them.

## Sprint order

1. Acquire prospective KXTEMPNYCH contracts, exact source coordinates, and
   source observations with receipt clocks before target decisions.
2. Rebuild the strict dataset and require a non-zero admitted-row count.
3. Run climatology and persistence first, then only PIT-valid HRRR/NBM/GEFS.
4. Evaluate untouched rolling folds with weather and economic metrics,
   including fees, slippage, conservative fills, robustness, and
   multiple-testing correction.
5. Emit manifests and paper telemetry only for admitted predictions.

The dataset builder independently validates `label_available_ts` (or the
source receipt fallback) as eventual post-target label evidence and requires
the settlement observation timestamp to equal the contract target timestamp.
Labels are expected to arrive after the decision; they are never used as
features. Missing, pre-target, or mismatched label clocks are retained as
rejection codes, while late observations/forecasts remain decision-time
rejections and cannot be hidden behind a valid binary settlement result.

All advanced models, auxiliary-city strategies, GOES/ERA5 expansion, further
feature work, L2 enhancements, and production deployment are deferred until
this sequence has produced valid NYC evidence.

## Reproducible bounded refresh

Run the following from the repository root. The commands are read-only with
respect to Kalshi and fail closed when PIT evidence is missing:

```bash
python3 scripts/weather/collect_awc_metar.py --ids KNYC KLAX KAUS --hours 2
python3 scripts/weather/build_provenance_indexes.py \
  --forecasts data/weather_research/forecasts/model_forecasts_points.csv \
  --observations data/weather_research/awc/metar.csv \
  --station KNYC --station KLAX --station KAUS \
  --output-dir data/weather_research/reports/provenance_indexes
python3 scripts/weather/probe_active_nyc_market.py
python3 scripts/weather/run_intraday_capture.py --iterations 1
python3 scripts/weather/run_intraday_edge_pipeline.py
python3 scripts/weather/generate_edge_baseline_predictions.py
python3 scripts/weather/evaluate_edge_first.py
python3 scripts/weather/data_quality_gates.py \
  --output data/weather_research/reports/data_quality_gates.json
```

For an open hourly market only, provide credentials out-of-band, for example:

```bash
KALSHI_CREDENTIAL_FILE=/secure/path/kalshi_credentials.txt \
python3 scripts/weather/run_intraday_capture.py --iterations 1
```

The credential path is never committed, copied, or read unless hourly tickers
are present; the runner remains read-only.

The current run passes provenance integrity but produces zero admitted NYC PIT
rows and zero hourly predictions; those are expected blockers, not successful
model or trading results.
