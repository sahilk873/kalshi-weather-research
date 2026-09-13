# OpenCode implementation review

Review date: 2026-09-12

## Latest bounded review

OpenCode was asked to review the expanded artifact-inventory basis (canonical
city ASOS and unique city-candle keys). The non-interactive process produced no
final PASS/FAIL within the bounded window and was stopped; it is not treated as
independent approval. Direct verification is authoritative: the inventory
reports zero `sqlite_count_mismatches`, the focused tests pass, and the full
suite passes (96 tests).

OpenCode was also asked to review `collect_ghcnh_tail.py`. It read the
collector and test but produced no final PASS/FAIL within the bounded window;
the process was stopped and is not treated as independent approval. Direct
checks passed: five live GHCNh suffixes have valid `Content-Range` metadata,
matching byte lengths, SHA-256 hashes, and `partial=true` manifest flags; the
collector test and full suite pass (97 tests).

The follow-up review read both GHCNh collectors and their manifests. It
verified the five yearly files and five tails on disk, and confirmed that no
normalization path consumes them as labels. Its root-level pytest probe found
the repository's pre-existing direct-import convention does not collect these
tests from the repository root; running from `scripts/weather` and the
documented `unittest discover` command passes (98 tests). No data-integrity
failure was found before the bounded process was stopped.

The parser review likewise read `parse_ghcnh_year.py`, its test, and the live
artifacts, but did not produce a final PASS/FAIL before the bounded process
was stopped. Direct evidence is stronger here: the parser consumed all 42
complete 2020–2026 station-year files, emitted 452,650 rows, attached
64-character hashes and receipt timestamps to every row, and passed the full
115-test suite.

The GHCNh quality-gate integration was independently checked after a bounded
run exposed an eager `setdefault` hash computation. That issue was fixed by
caching each raw-file digest explicitly. The regenerated gate completes in
about 1.2 seconds and is green for 452,650 rows; the full suite passes 115
tests.

OpenCode reviewed `collect_homr.py` and the five live manifests, confirming
URL encoding, response structure, byte sizes, and SHA-256 matches. It did not
return a final PASS/FAIL before the bounded process was stopped; direct
verification and the 102-test suite remain authoritative.

The follow-up review read `parse_homr.py` and `load_sqlite.py` and inspected a
live HOMR payload. It confirmed the expected nested identifier/relocation/
remark structures and that metadata is isolated in `homr_station_history`.
No final PASS/FAIL was returned before the bounded process was stopped; direct
rebuild and inventory checks pass with 133 rows and zero mismatches.

The HOMR quality-gate review read the new `homr_archive` check and its tests;
OpenCode first used an incorrect repository-relative path, then read the
correct `scripts/weather` files, but produced no final verdict in the bounded
window. Direct verification is green for all five manifests: hashes, JSON
shape, GHCND identity, and retrieval timestamps all pass.

OpenCode was also asked to review the ECMWF collector and `ecmwf_archive` gate,
but produced no final verdict within the bounded window and was stopped. Direct
verification is authoritative: the one raw IFS object has matching hash/size,
valid retrieval time and request metadata, and remains explicitly marked
`decoded=false`.

The ECMWF point-decoder/SQLite review inspected the raw GRIB2, 25 decoded rows,
and loader schema. OpenCode produced no final verdict within the bounded
window; direct verification caught and fixed a 15-placeholder/14-column loader
error, then rebuilt successfully with 25 rows and 106 passing tests.

OpenCode also inspected the `ecmwf_point_features` quality gate and its tests;
the bounded process did not return a final verdict before stopping. Direct
verification is green: 25 rows have linked raw hashes, ordered init/valid/
receipt timestamps, valid station/unit/range fields, and no duplicate keys.

The ensemble follow-up review read `decode_ecmwf_ensemble.py`, loader, and
quality gate, but did not return a final verdict before the bounded process was
stopped. Direct verification is authoritative: 75 member rows load into
SQLite, all hashes/timestamps/member IDs validate, and the full 110-test suite
passes.

OpenCode inspected `summarize_ecmwf_ensemble.py`, its test, and the 25-row
output, but produced no final verdict within the bounded window. Direct checks
confirm each summary uses the available three-member denominator, carries the
raw path/hash, and performs no imputation; the full 111-test suite passes.

The final bounded ensemble-path review inspected decoder, summarizer, loader,
quality gates, and the tampered-hash regression. It produced no final verdict
before stopping; direct verification remains authoritative: 75 member rows and
25 summaries are present, the ensemble gate is green, and 115 tests pass.

OpenCode read `collect_era5.py` and its fail-closed test. It did not return a
final verdict within the bounded window and was stopped; direct verification
shows the request specification is explicit and missing `CDS_API_KEY` raises
before any output is created. ERA5 remains credential-blocked by design.

An additional bounded OpenCode review of the research trading modules returned
an infrastructure error before findings. Direct review identified one safety
issue in `replay_orderbook.py`: unknown delta sides could previously be
interpreted as NO. The simulator now raises on unknown sides, with regression
coverage; the full 129-test suite passes.

A bounded review was attempted for the complete-year GHCNh collector and
parser after adding 2024–2025 archives. The local OpenCode service returned an
unexpected-server-error before producing findings; direct verification is
authoritative: the collector records URL, byte count, SHA-256, retrieval time,
and complete-file status; recursive parsing preserves repeated administrative
rows; SQLite contains all 452,650 normalized observations; and the full test
suite passes.

That review identified and corrected one schema mapping issue: HOMR elevation
records use `elevationMeters` (not `elevation_m`). The parser now preserves
those values, the regression test covers the mapping, and the rebuilt table
contains 457 records.

The SQLite integration was then reviewed locally: `ghcnh_observations` is
cleared and rebuilt with the other normalized tables, uses a provenance-aware
natural key, and matches all 452,650 CSV rows. The documented full suite now
passes 115 tests and the artifact inventory reports no mismatches.

OpenCode reviewed `deep-research-report (1).md`, the current tracker, source
files, and acquired NYC/Los Angeles/Austin artifacts without editing the tree.
The review identified five material gaps:

1. Daily auxiliary city settlement semantics were not audited.
2. The retained city market archive omitted daily HIGH/LOW series.
3. No authenticated historical L2 order-book data existed.
4. No point-in-time NWP/label overlap existed for a skill study.
5. Historical GEFS requests could return null member arrays without being
   flagged as unavailable.

Actions completed after review:

- Added the six daily auxiliary series to `kalshi_historical.py`, fixed missing
  `series_ticker` normalization, and acquired public metadata plus bounded
  trades/candles.
- Added `audit_city_daily_markets.py` and generated
  `reports/city_daily_market_audit.json`. It records NWS/Weather Company source
  metadata and intentionally leaves `rules_reproduced=false`.
- Added historical null-payload detection to `data_quality_gates.py`.
- Added `canonicalize_city_asos.py`, a deterministic ASOS re-delivery resolver,
  and wired its duplicate-free output into SQLite while preserving raw rows.
- Added `build_persistence_forecasts.py`, a point-in-time latest-prior-value
  baseline with explicit no-history rejections.
- Added `build_city_market_schedule.py` and `summarize_skill.py`; the current
  public daily-market catalog yields 4,143 PIT-gated proxy-label schedules and
  weighted climatology/persistence hurdle metrics with zero evaluator
  rejections.
- Added `evaluate_postprocessor_walk_forward.py` and corrected the bias,
  quantile, and EMOS training gates to use a later fold as-of clock. This
  caught and fixed a day-ahead training bug that had rejected every valid
  future-target training row.
- Added `build_nowcast_forecasts.py` as an observation-only probabilistic
  nowcast and verified its output through the existing evaluator. It remains a
  prerequisite diagnostic until an NWP-controlled comparison is available.
- Added the optional `boosted_postprocess.py`; its fold evaluation was run and
  rejected on CRPS/complexity grounds, with the artifact retained for audit.
- Added P4 sequence-window and GOES availability contracts; no deep runtime or
  satellite imagery is present, so neither is represented as a model result.

A follow-up OpenCode review verified canonicalization is deterministic under
input reversal, the canonical table has zero duplicate keys, the resolution
manifest has 20,733 retained and 3 superseded rows, and the focused tests pass.
Its final temporary-fixture check was not run because the local tool rejected
external `/tmp` writes; the repository tests and direct checkout checks remain
the authoritative evidence.

Evidence commands:

```bash
python3 -m unittest discover scripts/weather -p 'test_*.py'
python3 scripts/weather/canonicalize_city_asos.py
python3 scripts/weather/load_sqlite.py
python3 scripts/weather/audit_city_daily_markets.py \
  --output data/weather_research/reports/city_daily_market_audit.json
python3 scripts/weather/data_quality_gates.py \
  --output data/weather_research/reports/data_quality_gates.json
```

The review did not waive the remaining external gates: licensed Weather
Company payloads, historical forecast-run archives, and authenticated forward
order-book capture are still required for their respective claims.

The final contract pass tightened the P4 artifacts: sequence windows now parse
timestamps as datetimes and enforce an optional maximum inter-observation gap;
the regenerated artifact uses a 120-minute gate (8,914 windows, 9
rejections). GOES listing probes now retry transient failures and follow S3
continuation tokens (up to five pages), avoiding the prior 20-object
truncation.

An additional bounded forecast-availability probe tested Open-Meteo
`previous-runs` and `single-runs` for NYC, Los Angeles, and Austin over
2026-01-01 through 2026-09-10. `previous-runs` returned HTTP 400; the three
`single-runs` responses were archived with SHA-256 hashes but contained null
values for all 30 members. They are explicitly counted as unavailable by
`data_quality_gates.py` (eight null responses total) and are not consumed by
any forecast or evaluation output.

The bucket-probability review confirmed all four PHX/LV series are now accepted
by the schedule adapter, that label generation uses only normalized
`settled_yes` outcomes, and that the 1,680-row probability artifact is built
from complete event partitions with PIT issue/receipt checks. The evaluator
accepted 264 finalized events; the remaining 16 events are explicitly rejected
because labels are not available by the decision clock or have inconsistent
settlement rows.

The in-scope NWP pass added bounded current NOMADS collection for PHX and KLAS:
six HRRR and four NBM filtered files were downloaded and hashed, and the
isolated `eccodes` decoder produced 82 nearest-grid-point rows. The manifest
gate remains green (25 rows, zero hash/path errors); this is current guidance,
not historical daily skill evidence.

The GOES feature pass was reviewed against the public NetCDF metadata and
projection contract. Three retained G18 MCMIPC objects yield a short temporal
series of 3×3 C13 infrared brightness-temperature means and DQF clear
fractions for both PHX and KLAS, with the raw SHA-256 carried into each row.
The artifact is intentionally marked as a feature-only sample; no incremental
forecast skill is claimed.

The ASOS backfill review caught and fixed a destructive rerun behavior:
`backfill_asos.py` now merges by `(station, valid_utc)` and preserves existing
rows while adding bounded refreshes. A Sep 11–12 PHX/LAS refresh was rerun
against the restored archive and produced 88,165 merged observations, with the
fresh subset retained separately for the GOES overlap.

The bounded GOES incremental evaluator was then added with focused tests. It
emits per-row, grouped-summary, and fail-closed rejection CSVs. The Sep 11 run
rejects all six overlap rows because proxy labels end Sep 10, so no incremental
skill result is reported.

The deterministic NWP follow-up added GFS support to the NOMADS collector and
verified the filtered URL and decoder path. A bounded 00Z collection now holds
15 GFS files (leads 0–2 for NYC, Los Angeles, Austin, Phoenix, and KLAS), with
manifest hashes and 768 total decoded forecast points across all models.

The RTMA integration review found and corrected a longitude-convention issue:
ecCodes may return 0–360° longitudes, so `decode_rtma_point.py` now normalizes
values above 180° to −180–180° before writing the feature CSV and SQLite rows.

The provenance follow-up added a decoded-point gate. It checks every point row
against its raw GRIB path and SHA-256; the historical review checkpoint had 768 rows across 73 source
files pass with no missing paths or hash mismatches.

The RTMA gate was extended with variable-specific range checks (Kelvin
temperature/dewpoint, wind components, percent cloud, and metre visibility).
All 30 decoded RTMA rows pass the range and provenance checks.

The CPC gate was extended with finite year, sea-surface-temperature, and ONI
anomaly range checks; the 919-row normalized index passes with zero invalid
values.

The CPC provenance gate now also parses every retrieval timestamp as UTC; the
current 919 rows pass with zero invalid timestamps.

The RTMA archive gate now parses manifest retrieval and feature valid times and
rejects timestamps after the audit clock. The current archive has zero invalid
or future timestamps.

The artifact inventory was extended to count the four RTMA manifest rows in
addition to the 30 decoded point rows; the generated JSON and SQLite counts
remain aligned.

The inventory now emits `sqlite_count_mismatches` for the forecast, RTMA, and
CPC pairs; the current generated snapshot reports an empty mismatch list.

The inventory was hardened for partial SQLite files: absent expected tables are
treated as zero and surfaced as count drift rather than raising an operational
error. A regression fixture confirms mismatched counts are reported.

The end-to-end sample exposed stale-row retention in SQLite; `load_sqlite.py`
now clears loaded tables before reloading current normalized files. Rebuild
counts match the restored tier (1,527 observations, 5,172 nearby rows, and
1,527 derived state rows).

The complete `run_sample.py` (including bounded Kalshi metadata, candles, and
trades) was rerun after adding the nearby collection step; all 11 steps passed.
The larger restored tier was then reloaded and its inventory mismatch list
remained empty.

`test_run_sample.py` now asserts that nearby raw collection precedes parsing,
protecting the dependency order that made the full sample run succeed.

The complete sample was rerun with all 11 steps enabled; nearby collection,
Kalshi metadata, candles, trades, SQLite rebuild, and validation all completed
successfully. The expanded restored tier was reloaded afterward and verified by
the artifact inventory.

On 2026-09-12, an additional bounded OpenCode review was attempted against the
report and current tree. OpenCode returned `UnknownError` / `Unexpected server
error` before producing findings, so no OpenCode conclusion is treated as
evidence. Direct checks remain authoritative. In the same pass, the public
historical Kalshi refresh retrieved 216 settled-market records, 72,658 trades,
and 7,654 hourly candles; the request returned historical coverage only where
the API exposed it, and no missing series were filled in.

The report-2 risk review then completed successfully. OpenCode identified two
real `allocate_event` issues: contract counts were recomputed from gross
rather than fee-adjusted prices, and duplicate/blank tickers could select the
wrong candidate row. Both were fixed using row identity and net-price
recomputation; regression coverage now includes fee-bearing duplicate-ticker
candidates. OpenCode found no correctness issue in the centered moving-block
max-statistic comparison in `multiple_testing.py`.

For the report-2 collectors, OpenCode found that the first implementation
overwrote `awc/metar.csv` and both manifests on every poll, losing receipt-time
history. The collectors now append deduplicated AWC rows and immutable
snapshot-manifest entries; LAMP cycle files remain preserved by filename. AWC
now has 9 rows across two pulls and both provenance gates pass.

OpenCode separately reviewed `collect_glmp_temperature.py` against report 2
and found three issues: non-GRIB responses could be archived as valid,
run-time provenance was missing, and daily rollover could fail when the newest
directory had no temperature cycle. The collector now checks the GRIB magic
header, records parsed initialization time, searches prior available
directories, and the GLMP provenance gate validates those invariants. The live
GLMP snapshot passes with a 15,853,194-byte payload.

An additional read-only OpenCode review of the new NYC series archive and
SQLite integration was started, but produced no verdict before interruption.
It is therefore not counted as approval; direct unit tests, compilation,
SQLite row counts, and the new contract provenance gate are the evidence for
this change.

OpenCode then reviewed `collect_twc_kalshi.py` and found one concrete schema
bug: the portal's running daily `avgTemp` is at the result level when `data`
is null, so the first parser dropped it. The parser now falls back to
`result.avgTemp`, and the regression test covers that live payload shape.

A bounded OpenCode review of `simulate_candle_execution.py` was started but did
not return a final verdict before the session was interrupted. Direct tests
cover the no-lookahead candle ordering and all three fill scenarios.

OpenCode reviewed `robustness_scenarios.py` and identified mixed naive/aware
timestamps as a crash path, plus under-reported scenario exclusions. The
timestamp parser now treats naive values as UTC, and each filtered scenario
reports `filtered_out` separately; regression coverage verifies the fix.

The follow-up collector review found that content-hash-only CSV keys still
collapsed identical payloads from separate receipts, and that null daily
fields bypassed fallback values. Keys now include `raw_path`, SQLite TWC tables
use the same snapshot identity, and non-null fallback selection is explicit.
The repeated-pull test now asserts both receipt rows are retained.

OpenCode's probability-calibration review caught an undamped Newton divergence
on small separable samples. Platt fitting now uses bounded parameters,
regularization, and backtracking line search; a separable-sample regression
test and random finite-value stress check pass.

The follow-up beta-calibration review found unconstrained coefficients could
invert the probability ordering. Beta now enforces `a >= 0` and `b <= 0`; Platt
also clamps its slope non-negative. Full calibration tests and adversarial
finite/monotonicity checks pass on the current file.

OpenCode reviewed `parse_kalshi_hourly_contracts.py` and its SQLite/inventory/
quality-gate integration and returned PASS. It verified all 15,883 contracts
have parsed thresholds/operators, target times, source/rules hashes, matching
raw provenance, and zero CSV/SQLite count mismatches.

OpenCode reviewed `join_kalshi_twc_labels.py` and found that comparing the
portal's one-decimal temperature directly with `X.99` ticker thresholds could
disagree with whole-degree Kalshi settlements in 53 rows. The join now uses the
parsed whole-degree bucket boundary while retaining the raw decimal reading;
the label quality gate also enforces source/Kalshi result consistency. The
regression suite and current 2,482-match archive pass.

On 2026-09-12 the report-2 immutable-prediction-manifest requirement was
implemented from the report's "every prediction should be reproducible from an
immutable manifest" spec, following the fail-closed, deterministic, and
non-destructive conventions from prior audits. `prediction_manifest.py` writes
sorted-key JSON manifests with market identity, `decision_ts`, feature/model/
calibrator versions, source-run and observation IDs, `rules_hash`,
`code_commit`, and a probability in `[0,1]`; it resolves supplied provenance
indexes, checks PIT clocks and contract rules, supports partitioned model
paths, rederives content hashes, and rejects duplicate logical manifests.
Conflicting rewrites raise and new files are written atomically. The focused
suite covers these invariants and the CLI; the full discovered suite passes
(235 tests). The `prediction_manifest` check remains intentionally red until a
real forecast is aligned to a KXTEMPNYCH contract with source indexes, and
`audit_artifact_inventory.py` counts the recursive prediction tier while
preserving the current empty SQLite mismatch list.

The first OpenCode monitoring implementation attempt stalled before producing
an artifact. The specified control was then implemented directly as
`operational_readiness.py`: it is pure, deterministic, fail-closed, and
research/paper-trading-only. Focused tests cover every kill-switch category and
the CLI; no order-placement behavior was added.

The paper-trading ledger was then implemented directly after the OpenCode
review process stalled. `paper_trading_ledger.py` is append-only JSONL,
manifest-referenced, duplicate-safe, and restricted to hypothetical order,
fill, and settlement records; it has no network or order-placement path.

On 2026-09-12 a bounded OpenCode read-only review of the new GEFS live archive
gate failed with an upstream server error before producing findings. Direct
verification covered the requested invariants instead: all 31 manifest rows
resolve to existing raw JSON, hashes and receipt clocks pass, and each raw
response reports exactly 30 `temperature_2m_member*` arrays matching its
declared denominator. Focused regression tests cover a passing archive and a
member-count mismatch; no nominal 31-member assumption is used.

The follow-up bounded OpenCode review of `run_awc_poll.py` timed out before
returning findings. Direct review and its focused tests verify bounded sleeps,
continuous zero-iteration mode, fail-closed cadence validation, and delegation
of every pull to the existing hashed collector.

The bounded OpenCode review of `build_decision_features.py` likewise produced
no response before timeout. Direct review plus tests verified UTC parsing,
receipt-before-decision filtering, explicit late-source rejection, stable JSON
serialization, and no fabricated feature rows.

The report-2 ladder audit identified a naming/order mismatch and omitted M12/M13;
`model_ladder.py` now exactly enumerates M0–M13. Its eligibility manifest remains
data-readiness evidence only, and does not promote a model without PIT rows and
rolling out-of-sample evaluation.

The same audit identified that the original feature join did not expose the
report's derived temporal/distribution fields, and that no explicit partition
artifact existed. `build_decision_features.py` now derives those fields under
the existing receipt cutoff, while `training_readiness.py` emits a fail-closed
chronological train/calibration/test plan. Both changes were covered by the
full 231-test suite.

The execution audit also identified missing economic summary fields. The
candle simulator now reports conservative/base/optimistic payoff risk metrics
and YES/NO cost-adjusted edge/trigger fields; the market-efficiency analyzer
accepts fee, slippage-reserve, and minimum-edge parameters while remaining
research-only.

The deployment-readiness audit also required an explicit promotion gate. The
new `deployment_gate.py` checks all report-2 evidence categories, fails closed
when any are absent, and always reports `authorized=false`; it is not a broker
or trading authorization mechanism.
The GEFS acquisition review found that Open-Meteo exposes convective inhibition
as `convective_inhibition`, not `cin`. The collector now normalizes that
supported field to canonical `cin`; a bounded NYC refresh added the field to
the long-form archive, and the completeness audit now reports GEFS complete.
The NOAA point decoder was also extended for pressure, radiation, CAPE, CIN,
and gust fields and derives scalar wind speed from U/V components; the
normalized point table at that historical checkpoint contained 768 rows with raw hashes preserved. A raw
GRIB inspection then identified `sp` and `sdswrf` aliases; those are now mapped
to surface pressure and shortwave radiation without mislabeling them as MSL
pressure.

The contract-resolution audit found that event payloads carry settlement
sources that may differ from series metadata. `parse_kalshi_hourly_contracts.py`
now uses each event's source and derives its rules hash from that event source,
falling back to series metadata only when the event omits it.
The model-readiness review also corrected M4: aviation-only LAMP bulletins are
not treated as temperature guidance; readiness now counts only TMP/DPT or GLMP
temperature rows.

The source-era follow-up added `audit_settlement_source_transition.py`, which
hashes and parses the captured transition notice (including the local ET market
start converted to UTC) and checks the effective TWC-to-Synoptic cutoff against
each contract. It reports 15,883 pre-transition rows, zero post-transition
rows, and zero mismatches. A bounded OpenCode review reached the relevant files
but timed out before returning a report; direct review found and fixed the
original hard-coded-cutoff issue. That checkpoint had 237 tests; the current
the earlier review checkpoint passed 294 tests with one environment-dependent skip;
the current full suite passes 298 tests with one skip after the forecast-rejection
ledger test was added.
# 2026-09-13 bounded review: authenticated order-book path

OpenCode was run with a bounded read-only review scope over
`kalshi_auth.py`, `collect_orderbook.py`, `replay_orderbook.py`,
`orderbook_features.py`, and `audit_orderbook_capture.py`. It inspected the
implementation and the checked-in AsyncAPI schema but timed out before
returning findings. Direct verification therefore remains authoritative:
the RSA handshake connected successfully, the current dollar-priced snapshot
schema is covered by replay tests, and the cumulative capture is explicitly
audited for sequence resets/gaps. The complete Python test suite now passes
(298 tests, one environment-dependent skip; the older OpenCode checkpoint was
294 tests).
# 2026-09-13 bounded review: live daily diagnostic probabilities

OpenCode read `generate_live_daily_diagnostic.py` and its tests within a
bounded review but timed out before returning a final finding. The
initial direct artifact inspection caught a real issue: `between` contracts
were incorrectly priced as one-sided thresholds. The implementation now uses
whole-degree half-degree continuity bounds for less, greater, and between
contracts; the current regenerated artifact has 22 quote-complete rows and 14
explicit quote-field rejections. Direct unit tests and the full suite are
authoritative.

# 2026-09-13 bounded review: order-book gap safety

A bounded OpenCode review of the execution path identified that
`replay_orderbook.py` counted sequence gaps but still applied later deltas and
simulated fills. Direct review confirmed the issue and changed replay to
quarantine the book after a gap until a verified snapshot arrives;
`buy_yes` now raises `OrderBookQuarantined`, and the CLI emits an explicit
quarantined result. New tests cover both gap rejection and resnapshot recovery.
## 2026-09-13 bounded follow-up

An additional read-only OpenCode review was attempted for the live quote,
prospective capture, diagnostic, and SQLite changes. The local OpenCode
backend returned `Unexpected server error` (`err_30e9aa08`) before producing a
review. No edits or claims rely on that attempt; direct tests, compilation,
SQLite rebuild, and quality gates remain the authoritative verification.
