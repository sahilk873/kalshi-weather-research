# Local Data Inventory

This is a snapshot of the generated data currently present in the local
workspace. Generated data is intentionally excluded from GitHub by
`.gitignore`; rerun the scripts to reproduce it.

## Weather observations and labels

| Dataset | Coverage and amount | Locations |
| --- | --- | --- |
| GHCN-Daily labels (`ghcn_city/labels_daily.csv`) | 107,451 daily rows; NYC 1869-01-01–2026-09-10, Los Angeles 1944-08-01–2026-09-10, Austin 1948-03-01–2026-09-10 | USW00094728, USW00023174, USW00013904 |
| Settlement ASOS/METAR (`city_asos/asos_parsed.csv`) | 20,657 observations; 2025-12-31–2026-09-10 | KNYC 7,138; KAUS 6,777; KLAX 6,742 |
| Nearby ASOS/METAR (`city_nearby_asos/nearby_asos_parsed.csv`) | 16,589 observations; 2026-08-11–2026-09-11 | 18 stations: NYC area KNYC/KLGA/KJFK/KEWR/KTEB/KHPN; LA KLAX/KHHR/KBUR/KVNY/KSMO/KLGB; Austin KAUS/KEDC/KGTU/KHYI/KATT/KBAZ |
| NWS CLI (`city_nws_cli/daily_climate_cli.csv`) | 91 product versions; 2026-08-31–2026-09-11 | CLINYC 23; CLILAX 26; CLIAUS 42 |
| Solar (`solar_city/solar_features.csv`) | 762 daily rows, 254 per city; 2025-12-31–2026-09-10 | NYC, Austin, Los Angeles |
| Derived intraday state (`derived_intraday_state_city/derived_intraday_state.csv`) | 20,654 rows; 2025-12-31–2026-09-10 | NYC 7,138; Austin 6,775; LA 6,741 |

ASOS files preserve raw monthly downloads and raw METAR text. Parsed fields
include temperature, dew point, wind, pressure, visibility, clouds,
precipitation/weather codes, and ASOS remark groups. Derived state is built
from observations only; final daily labels are not used as intraday features.

## Forecasts

`gefs/historical_raw/predictions.csv` contains 340,272 ensemble forecast rows
from the historical GEFS/Open-Meteo archive probe. The rows cover NYC, Los
Angeles, Austin, Chicago, and Washington, DC. `gefs/manifest.csv` has 22 raw
request records and `gefs/historical_raw/manifest.csv` has 10 historical request
records. Raw JSON responses are retained. HRRR/NBM filtered GRIB2 samples are
not currently decoded into a structured table.

## Kalshi temperature markets

| Dataset | Amount and coverage |
| --- | --- |
| Historical market definitions | 51,009: NYC `KXTEMPNYCH` 48,985 (at least 2026-04-01–2026-07-12), Austin `KXTEMPAUSH` 1,012 (at least July 8–12), LA `KXTEMPLAXH` 1,012 (at least July 8–12) |
| Historical trades | 16,597 records from the bounded 200-market-per-city backfill; timestamps through 2026-07-12 |
| Historical hourly candles | 1,200 rows from the bounded trade/candle backfill |
| Raw historical API responses | Preserved under `kalshi_historical_city/raw/`, including paginated market, trade, candle, and cutoff responses |

No historical full order-book snapshots are present. Kalshi's public historical
tier exposes markets, trades, and candles, while the order-book REST endpoint
returns the current book only. Exact future books require authenticated
WebSocket snapshot/delta collection.

## Reproduction and expansion

- GHCN labels: `scripts/weather/ghcn_city_labels.py`
- ASOS settlement stations: `scripts/weather/backfill_city_asos.py`
- Nearby ASOS: `collect_city_nearby_asos.py`, `parse_city_nearby_asos.py`
- NWS CLI: `nws_cli_city_archive.py`
- Solar/state: `build_city_features.py`
- Kalshi markets/trades/candles: `kalshi_historical.py`
- GEFS: `gefs_historical.py`, `gefs_ensemble.py`

The most expandable sources are GHCN, IEM ASOS, Kalshi historical pagination,
and archived GEFS. NWS CLI history is constrained by rolling public retention;
historical order books cannot be reconstructed retrospectively.

