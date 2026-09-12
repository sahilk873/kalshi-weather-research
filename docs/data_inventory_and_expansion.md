# Weather Trading Data Inventory

This document records data actually present in the repository and the most
useful paths for expanding it.

## Current research focus

The active focus is now Kalshi's NYC hourly temperature line (`KXTEMPNYCH`),
with Austin (`KXTEMPAUSH`) and Los Angeles (`KXTEMPLAXH`) as comparison
markets. Previous PHX/LAS weather and market data artifacts were removed from
the working dataset and placed in `/tmp/kalshi_phx_lv_removed_20260911`.

## Current inventory

| Dataset | Stored amount and coverage | Can we collect more? |
| --- | --- | --- |
| GHCN/NCEI daily labels | 60,663 rows: PHX 1933-06-01–2026-09-08; LAS 1948-09-06–2026-09-08 | Yes, labels already span the available station history. They are final labels only, not intraday features. |
| PHX/LAS ASOS/METAR sample | 1,527 rows, 2026-08-11–2026-09-10 | Yes, but this is only the recent sample. |
| PHX/LAS ASOS/METAR backfill | 88,118 rows, approximately 2021–2025, with a partial 2020-12-31 boundary | Yes. IEM provides older public ASOS/METAR history; backfill 2020 and 2026 gaps in bounded monthly jobs. |
| Parsed ASOS remarks | Included in the 89,645 settlement-station rows | Yes. Raw METAR is retained; original dissemination timestamps are generally unavailable. |
| Nearby ASOS | 5,172 rows, roughly 2026-08-11–2026-09-10; SDL/CHD/FFZ and HND/VGT/LSV | Yes. IEM can backfill selected nearby stations over the same historical window. |
| NWS CLI reports | 26 records, mainly 2025-12-30 and 2026-09-04–09-09 | Limited. IEM's AFOS archive is rolling; a long historical CLI archive requires NWS/NCEI source access or a licensed archive. |
| Solar geometry | 84 daily PHX/LV rows, 2026-08-01–09-11 | Yes. Compute deterministically for every observation date/timestamp. |
| Derived intraday state | 1,527 rows for 2026-08-11–09-10 | Yes. Rebuild after expanding ASOS observations. |
| HRRR/NBM forecasts | 5 filtered GRIB2 files: HRRR 3, NBM 2; initializations 2026-09-10–09-11 | Yes. NOMADS filtered endpoints support bounded recent/archive polling. A GRIB decoder is still needed for structured variables. |
| Kalshi live-tier metadata | 789 events, 1,680 markets, dates 2026-07-05–09-12 | Yes, through live and historical endpoints. |
| Kalshi live-tier trades | 3,212 trades, concentrated 2026-09-10–09-11 | Yes, subject to endpoint retention and cutoff. |
| Kalshi live-tier candles | 662 hourly and 24 daily rows | Yes. Request 1-minute/hourly/daily candles per market. |
| Kalshi historical-tier sample | 32 markets, 8,315 trades, 1,133 hourly candles; market dates 2026-07-10–07-11 | Yes. The historical extractor can paginate all four MVP series and other city series. |
| Historical full order books | 0 snapshots | Not through the public historical API. Exact books require Kalshi data access or forward WebSocket collection. |

## Highest-value expansions

1. Complete Kalshi historical pagination for every PHX/LV market, then extend
   to other daily high/low and hourly temperature series.
2. Backfill ASOS/METAR for the 2020 boundary and January–July 2026 gap.
3. Download HRRR and NBM runs for each available archive date using small
   PHX/KLAS filters and install `python-eccodes` or `wgrib2` for decoding.
4. Recompute derived intraday state and solar features from the expanded
   observations.
5. Start authenticated WebSocket order-book collection immediately; this is
   the only reliable way to build exact future book history.

## Point-in-time cautions

- GHCN daily values are labels and must not enter earlier intraday features.
- ASOS `valid_utc` is observation time; original public dissemination time is
  usually unavailable and must be flagged.
- Forecast joins must enforce `initialization_time_utc <= decision_time_utc`.
- Kalshi trades/candles describe executed or aggregated activity, not the full
  historical queue or unexecuted depth.

Reproduction scripts are under `scripts/weather/`; primary outputs are under
`data/weather_research/`.

## New NYC/Austin/Los Angeles outputs

- `data/weather_research/kalshi_historical_city/markets.csv`: 51,009 market
  definitions (48,985 NYC; 1,012 Austin; 1,012 Los Angeles). NYC metadata now
  reaches at least 2026-04-01; Austin and Los Angeles reach at least
  2026-07-08. Raw paginated responses are retained alongside the CSV.
- `data/weather_research/kalshi_historical_city/trades.csv`: 16,597 trades
  from the bounded 200-market-per-city backfill.
- `data/weather_research/kalshi_historical_city/candles.csv`: 1,200 hourly
  candles from the bounded trade/candle backfill.
- `data/weather_research/city_asos/asos_parsed.csv`: 20,657 parsed NYC/AUS/LAX
  ASOS observations, January 2026 through September 10, 2026, with raw
  monthly files and METAR fields preserved.

The market metadata crawl can continue through remaining cursors to establish
the exact oldest NYC date. Trades and candles should then be expanded only for
the selected historical window to control request volume.

## Geographic coverage and expansion

### Current settlement locations

| Location | Settlement station | ICAO | Coordinates | Time zone | Current role |
| --- | --- | --- | --- | --- | --- |
| Phoenix, AZ | Phoenix Sky Harbor | `KPHX` / IEM `PHX` | 33.4278, -112.0036 | America/Phoenix | Kalshi high/low settlement and ASOS source |
| Las Vegas, NV | Harry Reid International | `KLAS` / IEM `LAS` | 36.0719, -115.1633 | America/Los_Angeles | Kalshi high/low settlement and ASOS source |

### Nearby weather network

The compact nearby network currently collected is:

- Phoenix: `KSDL` Scottsdale, `KCHD` Chandler, `KFFZ` Falcon Field
- Las Vegas: `KHND` Henderson, `KVGT` North Las Vegas, `KLSV` Nellis

These stations are useful for spatial gradients, wind/cloud regime changes,
and detecting approaching weather changes. IEM can provide additional ASOS or
AWOS sites, but expansion should be limited to stations with reliable temporal
coverage and meaningful distance/direction from the settlement airport.

### Kalshi cities available for future weather research

The catalog audit found daily high/low products for many additional US cities,
including Austin, Atlanta, Boston, Chicago, Dallas, Denver, Houston,
Minneapolis, Miami, New Orleans, New York City, Oklahoma City, Philadelphia,
San Antonio, San Diego, San Francisco, Seattle, and Washington, DC. It also
contains international temperature products for cities such as London, Paris,
Toronto, Mexico City, Seoul, Tokyo, Beijing, Amsterdam, Brussels, Frankfurt,
Berlin, Geneva, Istanbul, Dubai, Mumbai, and Hong Kong.

Hourly/directional products were found for Miami, Los Angeles, Austin,
Washington, DC, Chicago, Boston, and NYC, with alternate coastal/metro lines.
These markets can be inventoried and backfilled independently, but their
settlement stations and rules must be verified before combining them with the
PHX/LV dataset.

### Forecast geographic scope

The NOMADS downloader currently requests small filtered bounding boxes around
PHX and KLAS rather than full CONUS files. Each manifest row stores the target
station coordinates and request URL. Additional cities are technically
possible by adding validated grid points and boxes, but should not be added to
the MVP until their market settlement source and station identity are known.

### City expansion: nearby stations and CLI

For the NYC, Los Angeles, and Austin research lines, a compact nearby ASOS
network is available in `data/weather_research/city_nearby_asos/`. It contains
18 raw IEM archives and 16,589 parsed observations for 2026-08-12 through
2026-09-11. The selected stations are KNYC/KLGA/KJFK/KEWR/KTEB/KHPN, a Los
Angeles group of KLAX/KHHR/KBUR/KVNY/KSMO/KLGB, and an Austin group of
KAUS/KEDC/KGTU/KHYI/KATT/KBAZ. These are suitable for spatial gradients, but
are not substitutes for verifying each market's settlement station.

NWS CLI products are stored separately in
`data/weather_research/city_nws_cli/`: 91 raw/parsed product versions,
covering 2026-08-31 through 2026-09-11 (NYC 23, Los Angeles 26, Austin 42).
IEM AFOS retention is rolling, so this dataset can only be extended
prospectively unless an independent long-term CLI archive is obtained.
