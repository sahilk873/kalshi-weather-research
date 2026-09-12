# Repository Guidelines

## Purpose and Scope

This repository builds a point-in-time research foundation for a future
Kalshi weather trading bot. Scope is intentionally limited to four recurring
markets: Phoenix and Las Vegas daily high/low temperature ranges
(`KXHIGHTPHX`, `KXLOWTPHX`, `KXHIGHTLV`, `KXLOWTLV`). Do not add hourly,
precipitation, hurricane, snowfall, or other-city strategies without an
explicit scope change. This repository is not an execution system yet; model
and order-placement logic must not be introduced as part of data ingestion.

## Layout and Data Provenance

- `openapi.yaml` and `asyncapi.yaml` are the checked-in Kalshi REST/WebSocket
  contracts.
- `scripts/weather/` contains cached downloaders, parsers, validation, the
  point-in-time state builder, SQLite loader, and live order-book collector.
- `data/weather_research/` contains normalized CSV/JSONL data and the portable
  `kalshi_weather.sqlite` query layer; raw METAR, NWS, Kalshi, and model files
  must remain preserved.
- `docs/` contains the data dictionary and settlement evidence; `README.md`
  and `data_sources.md` document reproducibility and limitations.

Every observation needs event time, and every forecast needs initialization and
valid time. Never join finalized daily labels, revised climate products, later
forecast runs, or settlement results into an earlier feature timestamp.
Settlement source is event-specific: inspect Kalshi metadata because historical
events may cite NWS CLI while current events may cite The Weather Company.

## Development Commands

```bash
python3 scripts/weather/run_sample.py
python3 scripts/weather/build_intraday_state.py
python3 scripts/weather/validate.py
python3 scripts/weather/load_sqlite.py
python3 -m py_compile scripts/weather/*.py
ruby -e "require 'yaml'; %w[openapi.yaml asyncapi.yaml].each { |f| YAML.load_file(f) }"
```

Use caching and bounded date/event windows for downloads. Run
`collect_orderbook.py --dry-run` before credentialed collection. Secrets belong
in environment variables, never in files or commits. Historical order books
must not be fabricated from closing prices; retain raw WebSocket messages and
record gaps, reconnects, and sequence anomalies.

## Style, Validation, and Review

Use Python 3, four-space indentation, type hints where practical, and
lowercase `snake_case` filenames. Keep CSV schemas stable and update
`docs/data_dictionary.md` when fields change. Validate timezone/DST handling,
duplicate keys, missing periods, METAR parse rates, bucket gaps/overlaps, and
official-versus-sampled extrema. No automated test suite is currently shipped;
record exact commands and results in review notes. Before changing API specs,
download to `/tmp`, diff, review semantic changes, and preserve upstream
ordering. Git history is unavailable here, so use imperative commit messages
such as `Add point-in-time weather state builder`; keep PRs focused and never
merge them from this workspace.
