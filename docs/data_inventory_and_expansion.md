# Weather Trading Data Inventory

This document records data actually present in the repository and the most
useful paths for expanding it.

## Current research focus

The active focus remains Kalshi's four in-scope PHX/LV daily temperature
markets, with NYC (`KXTEMPNYCH`), Austin (`KXTEMPAUSH`) and Los Angeles
(`KXTEMPLAXH`) as auxiliary comparison lines. The previously parked PHX/LV
archive has been restored under `data/weather_research/legacy_phx_lv/` and its
normalized tables are active under `data/weather_research/{ghcn,iem,solar,kalshi}`.

## Current inventory

| Dataset | Stored amount and coverage | Can we collect more? |
| --- | --- | --- |
| GHCN/NCEI daily labels | 107,451 NYC/LA/Austin rows through 2026-09-10; final station labels with conservative D+36h availability | Yes, future daily labels arrive only after publication; this archive is now refreshed. |
| NYC/LA/Austin ASOS/METAR | 20,736 parsed rows, 2026-01-01–2026-09-11; raw monthly responses retained | Yes, but dissemination timestamps are unavailable. |
| PHX/LAS ASOS/METAR backfill | 88,165 merged rows, 2020-12-31–2026-09-11, with a fresh subset retained separately | Yes. IEM provides older public ASOS/METAR history; rerun in bounded monthly jobs. |
| PHX/LAS restored normalized tier | 60,663 GHCN labels, 1,527 ASOS observations, 1,680 markets, 3,212 trades, 662 hourly and 24 daily candles, 1,680 contract outcomes | Yes. Extend the public IEM/Kalshi windows; current archive is bounded and settlement-source evidence remains mixed. |
| Parsed ASOS remarks | Included in the 88,165 PHX/LAS backfill rows | Yes. Raw METAR is retained; original dissemination timestamps are generally unavailable. |
| Nearby ASOS | 137,550 parsed rows, 2026-01-01–2026-09-11 across 18 NYC/LA/Austin stations | Yes. IEM can be rerun prospectively. |
| NWS CLI reports | 91 NYC/LA/Austin product versions, mostly 2026-08-31–09-11 | Limited. IEM's AFOS archive is rolling; a long historical CLI archive requires NWS/NCEI source access or a licensed archive. |
| Solar geometry | 4,164 daily PHX/LV rows, 2020-12-31–2026-09-12 | Yes. Compute deterministically for every observation date/timestamp. |
| Derived intraday state | 1,527 active trailing rows plus 88,165 PHX/LV backfill rows in the report artifact | Yes. Rebuild after expanding ASOS observations. |
| HRRR/NBM/GFS forecasts | 94 manifest rows across NYC/LA/Austin plus PHX/KLAS, with 958 decoded nearest-grid-point rows across 66 source files; 3 unavailable NBM f000 requests are recorded in `forecasts/rejections.csv` (HTTP 404) | NOAA guidance can be polled prospectively; historical retention remains short and some runs/leads return 404. |
| RTMA analysis | 4 archived objects (3 hourly `rqirtma` plus one 00Z variable-bearing analysis), yielding 30 nearest-grid-point values | Raw objects and hashes are archived; the filtered CGI returned HTTP 500, so direct archive retrieval is used. |
| CPC ONI climate regime | 919 seasonal rows from 1950–2026 with Niño 3.4 mean and anomaly | Public slow-moving regime covariate; not used as a contemporaneous observation or settlement label. |
| Kalshi live-tier metadata | 789 events, 1,680 markets, dates 2026-07-05–09-12 | Yes, through live and historical endpoints. |
| Kalshi live-tier trades | 3,212 trades, concentrated 2026-09-10–09-11 | Yes, subject to endpoint retention and cutoff. |
| Kalshi live-tier candles | 662 hourly and 24 daily rows | Yes. Request 1-minute/hourly/daily candles per market. |
| Kalshi historical city tier | 74,824 market definitions, 482,378 public trades, 19,255 hourly candles; cutoff 2026-07-14 | No older full-depth books through public historical APIs; metadata/trades/candles can be refreshed until cutoff. Six daily NYC/LA/Austin HIGH/LOW catalog series are now included. |
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

- `data/weather_research/kalshi_historical_city/markets.csv`: 74,824 market
  definitions, including the public historical cutoff through 2026-07-13 and
  the six auxiliary daily HIGH/LOW series.
  Raw paginated responses are retained alongside the CSV.
- `data/weather_research/kalshi_historical_city/trades.csv`: 482,378 public
  trades; `candles.csv`: 19,255 hourly candles. These are not L2 books and
  include bounded samples for the auxiliary daily series.
- `data/weather_research/city_asos/asos_parsed.csv`: 20,736 parsed NYC/AUS/LAX
  ASOS observations through 2026-09-11, with raw monthly files and METAR
  fields preserved.

The Kalshi public historical cutoff is recorded by the collector and is not a
substitute for a forward WebSocket order-book archive.

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
18 raw IEM archives and 137,550 parsed observations for 2026-01-01 through
2026-09-11. The selected stations are KNYC/KLGA/KJFK/KEWR/KTEB/KHPN, a Los
Angeles group of KLAX/KHHR/KBUR/KVNY/KSMO/KLGB, and an Austin group of
KAUS/KEDC/KGTU/KHYI/KATT/KBAZ. These are suitable for spatial gradients, but
are not substitutes for verifying each market's settlement station.

NWS CLI products are stored separately in
`data/weather_research/city_nws_cli/`: 91 raw/parsed product versions,
covering 2026-08-31 through 2026-09-11 (NYC 23, Los Angeles 26, Austin 42).
IEM AFOS retention is rolling, so this dataset can only be extended
prospectively unless an independent long-term CLI archive is obtained.
