# Repository reproduction runbook

This runbook is for a new agent or researcher starting from a fresh clone.
It explains what is in Git, how to recreate the local data layer, and which
claims the resulting data can and cannot support.

## 1. Clone and identify the checkout

```bash
git clone https://github.com/sahilk873/kalshi-weather-research.git
cd kalshi-weather-research
git status --short --branch
git log -1 --oneline
```

The repository contains Python code, tests, API specifications, schemas, and
documentation. The generated `data/` directory is intentionally not tracked;
a clone does not contain the downloaded raw payloads, normalized CSVs, SQLite
database, caches, or live WebSocket JSONL. Recreate them locally as described
below. Do not expect checkout-time row counts in the documentation to appear
without obtaining the same source windows again.

## 2. Prepare Python

Python 3.10+ is recommended. Create an isolated environment and install the
small required dependency set:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The required packages are used by the authenticated WebSocket collector.
Most public collectors use the Python standard library. GRIB decoding is
optional and requires compatible `eccodes`/`cfgrib` packages or `wgrib2`.

Run the cheap code checks before downloading anything:

```bash
python -m py_compile scripts/weather/*.py
python -m unittest discover -s scripts/weather -p 'test_*.py'
```

## 3. Recreate the bounded sample dataset

The supported first pass is the cached PHX/LV sample orchestrator:

```bash
python scripts/weather/run_sample.py
```

It collects or rebuilds, in dependency order:

1. GHCN-Daily labels
2. trailing settlement-station ASOS/METAR
3. solar features
4. nearby-station discovery and ASOS
5. point-in-time intraday state
6. Kalshi event and market metadata
7. bounded public trades and candles
8. the SQLite query layer
9. validation reports

All supported downloaders cache raw responses. Re-running the command is
normally safe and cheaper than the initial run. To rebuild only from existing
raw/normalized files:

```bash
python scripts/weather/run_sample.py \
  --skip ghcn_daily iem_asos solar nearby_stations \
  kalshi_meta kalshi_trades_candles
```

If a source is unavailable, keep the partial raw artifacts and record the
date window, URL, retrieval timestamp, and error. Do not fill missing rows
with synthetic observations or prices.

## 4. Rebuild and inspect the local artifacts

After collection, run the deterministic rebuild and validation sequence:

```bash
python scripts/weather/parse_nearby_asos.py
python scripts/weather/build_intraday_state.py
python scripts/weather/load_sqlite.py
python scripts/weather/validate.py
python scripts/weather/settlement_analysis.py
```

Important locations are:

| Artifact | Location | Role |
| --- | --- | --- |
| Raw source downloads | `data/raw_*` and `data/weather_research/**/raw/` | immutable provenance inputs |
| Normalized research tables | `data/weather_research/` | CSV research layer |
| SQLite query layer | `data/weather_research/kalshi_weather.sqlite` | rebuilt convenience database |
| Quality reports | `data/weather_research/reports/` | validation and rejection evidence |
| Forecast manifest | `data/weather_research/forecasts/manifest.csv` | init/valid time, URL, receipt, hash |
| WebSocket capture | `data/weather_research/kalshi/ws/` | raw live messages and recovery state |

The raw files remain the source of truth. SQLite must be regenerated after
changing or replacing normalized CSVs; never rely on a stale database.

## 5. Extend collection with bounded windows

Use explicit, small windows first. Expand only after inspecting the output
and the quality report.

```bash
# Historical ASOS, isolated from the active trailing sample
python scripts/weather/backfill_asos.py \
  --start 2021-01-01 --end 2026-01-01

# Nearby predictor stations
python scripts/weather/collect_nearby_asos.py --days 30
python scripts/weather/parse_nearby_asos.py

# NWS CLI products retained by the rolling IEM AFOS service
python scripts/weather/nws_cli_archive.py \
  --start 2026-09-05 --end 2026-09-11

# Public Kalshi metadata and bounded market history
python scripts/weather/kalshi_meta.py
python scripts/weather/kalshi_trades_candles.py --max-events-per-series 2
python scripts/weather/kalshi_historical.py \
  --start 2026-07-01 --end 2026-07-31 --dry-run

# Bounded point-in-time forecast requests
python scripts/weather/nomads_forecasts.py \
  --model hrrr --init 2026-09-10T12:00:00Z --leads 0 1 2
```

For a long backfill, partition by month or year, preserve each raw response,
and use a manifest. Avoid unbounded API pagination, global GRIB downloads,
and narrow refreshes that overwrite older retained history.

## 6. Optional authenticated WebSocket capture

Run the dry-run before connecting:

```bash
python scripts/weather/collect_orderbook.py --dry-run
```

Credentials must be supplied through environment variables or a local ignored
credential file. Never paste a private key, API key, or token into the
repository.

```bash
export KALSHI_API_KEY='...'
export KALSHI_USER_ID='...'
python scripts/weather/collect_orderbook.py --run-seconds 600
```

The collector writes raw JSONL and state under
`data/weather_research/kalshi/ws/`. Preserve reconnects, sequence gaps, and
duplicates. A gap-affected order book must be resnapshotted or quarantined;
candles and trades cannot reconstruct historical queue position or unexecuted
depth.

## 7. Point-in-time and settlement safeguards

The active scope is exactly four daily temperature series:
`KXHIGHTPHX`, `KXLOWTPHX`, `KXHIGHTLV`, and `KXLOWTLV`. Do not add other
cities, hourly/precipitation products, or execution logic without an explicit
scope change.

Before using a row in a feature or backtest:

- use the observation event timestamp, not ingestion time;
- assign outcome dates in the station's IANA timezone;
- require forecast initialization and valid times to be usable at the
  decision timestamp;
- require labels and revised NWS products to be available by the decision
  timestamp;
- read the event-level Kalshi settlement source and station/rule metadata;
- keep NWS/GHCN labels separate from Weather Company settlement labels and
  call proxy labels proxies;
- treat missing bids/asks, post-close blanks, and candle gaps as missing;
- never fabricate an order book from closing prices.

Run the hard checks and inspect their outputs before reporting coverage or
trading readiness:

```bash
python scripts/weather/data_quality_gates.py \
  --output data/weather_research/reports/data_quality_gates.json
python scripts/weather/audit_artifact_inventory.py \
  --output data/weather_research/reports/artifact_inventory.json
python scripts/weather/audit_orderbook_capture.py \
  --input data/weather_research/kalshi/ws/orderbook_YYYYMMDD.jsonl \
  --output data/weather_research/reports/orderbook_audit.json
python scripts/weather/operational_readiness.py \
  data/weather_research/reports/readiness_snapshot.json \
  --output data/weather_research/reports/operational_readiness.json
```

Passing unit tests or a parser smoke test is narrow evidence. It does not
prove complete historical coverage, executable historical prices, settlement
equivalence across source eras, or real-money readiness.

## 8. Handoff checklist

Before handing the checkout to another agent, record:

```bash
git status --short --branch
python -m unittest discover -s scripts/weather -p 'test_*.py'
python -m py_compile scripts/weather/*.py
```

Also record the collection date in UTC, source windows, counts, skipped or
failed requests, raw-artifact locations, validation report paths, and whether
any values are synthetic, proxy, missing, or unavailable. Keep generated data
local or publish it through a separately documented artifact channel; it is
not part of the GitHub clone contract.
