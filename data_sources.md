# Source audit

| Dataset | Provider / URL | history, format, access | point-in-time use / limitation |
| --- | --- | --- | --- |
| Contract rules, events, markets, trades, candles | Kalshi Trade API, `https://external-api.kalshi.com/trade-api/v2`; checked-in OpenAPI | JSON, public endpoints observed; pagination and historical cutoff apply | Preserve API retrieval time. Trades/candles are usable only at their timestamps; do not substitute a close for executable quotes. Historical order-book replay is not exposed by this collection. |
| Live book / trade / ticker | Kalshi Market Data WebSocket, `wss://external-api-ws.kalshi.com/trade-api/ws/v2` | JSON WebSocket; authenticated connection required | Raw envelopes and receive ms are stored. Credentials absent in this run, so no live book was collected. |
| Binding settlement source | Per-event `settlement_sources` in Kalshi API | Older events: NWS CLI; current events: The Weather Company | Rule/source is event-specific. TWC is licensed; this project does not claim its historical point-in-time feed. |
| NWS Daily Climate Report | [PHX CLI](https://forecast.weather.gov/product.php?site=PSR&product=CLI&issuedby=PHX), [LAS CLI](https://forecast.weather.gov/product.php?site=VEF&product=CLI&issuedby=LAS), IEM AFOS retrieval | Text; public current product; IEM's public AFOS interface retains only a rolling ~7-day window | `nws_cli_archive.py` retains timestamped raw products and revisions for the available window; it merges into `daily_climate_cli.csv` instead of overwriting, so a narrower later run preserves earlier issuances. Observed retention: a request for 2021–2026 returned only the window-tail product (2025-12-30). It cannot manufacture a multi-year CLI archive; that requires an official long-term product archive/source agreement. |
| Final daily labels | NOAA NCEI GHCN-Daily `https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/` | Free fixed-width `.dly`; PHX 1933+, LAS 1948+ | Final quality-controlled labels, not intraday-safe on their own. Synthetic D+36h gate is conservative only. |
| Intraday observations | [IEM ASOS download](https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py) | Free CSV, hourly routine + specials and raw METAR, no key | Good event-time archive. Source lacks original dissemination timestamp; `valid_utc` is the available clock. |
| Station inventory | IEM network GeoJSON; NCEI station/inventory files | Free JSON/text | Used to select a compact 75-km ASOS network; 18 ASOS and 102 GHCN candidates found. |
| Nearby intraday ASOS | IEM ASOS downloader; `collect_nearby_asos.py` | Six raw station CSVs, trailing 30 days in this run | Three non-settlement stations per city: SDL/CHD/FFZ and HND/VGT/LSV. Raw data is ready for spatial-feature parsing. |
| HRRR | NOAA NOMADS / AWS Open Data HRRR archives | GRIB2; substantial volume; no auth normally | `nomads_forecasts.py` stores immutable filtered GRIB2 plus a manifest with init/valid time, lead, coordinates, URL, and SHA-256. Sample retained: 2026-09-10 12Z `f000` for PHX and KLAS under `forecasts/raw/hrrr/`, in `forecasts/manifest.csv`. Grid-point selection is documented in the manifest and `asof_forecasts.py`. |
| NBM | NOAA NCEP/NOMADS NBM archive | GRIB2; archive coverage/revisions vary | `nomads_forecasts.py` stores immutable filtered GRIB2 plus manifest. Sample retained: 2026-09-11 00Z `f001` for PHX and KLAS under `forecasts/raw/nbm/`, in `forecasts/manifest.csv`. Use archive availability, not today's blend. |
| NWS point forecast | NWS API / archived text products where available | JSON/text; archive completeness varies | Not downloaded; present API is not historical point-in-time evidence. |
| Solar features | deterministic NOAA solar geometry in `solar.py` | Computed locally | Point-in-time safe given timestamp/location; no forecast leakage. |

## NYC, Los Angeles, and Austin expansion

The city expansion keeps raw and normalized nearby-station data separate from
the legacy PHX/LAS layout:

| Dataset | Location | Current coverage | Output |
|---|---|---|---|
| Nearby ASOS/METAR | NYC: KNYC, KLGA, KJFK, KEWR, KTEB, KHPN; LA: KLAX, KHHR, KBUR, KVNY, KSMO, KLGB; Austin: KAUS, KEDC, KGTU, KHYI, KATT, KBAZ | 2026-08-12 through 2026-09-11 UTC | `data/weather_research/city_nearby_asos/raw/`, `nearby_asos_parsed.csv` |
| NWS CLI | NYC (`CLINYC`), LA (`CLILAX`), Austin (`CLIAUS`) via IEM AFOS | 2026-08-31 through 2026-09-11; 91 product versions | `data/weather_research/city_nws_cli/raw/`, `daily_climate_cli.csv` |

Run `collect_city_nearby_asos.py` and `parse_city_nearby_asos.py` to extend the
ASOS window. Run `nws_cli_city_archive.py` regularly because IEM AFOS is a
rolling public archive; older products must have been captured at the time.
The station IDs in IEM CSVs omit the leading `K` (for example `NYC` is
`KNYC`), while the raw METAR retains the source identifier.

No consumer weather API is used as a label substitute. Costs/rate limits can
change; this run observed free public access for NCEI/IEM/Kalshi public REST.
Backfills should use caching and courteous bounded requests.

## Active city focus (September 2026)

The active weather scope is NYC, Austin, and Los Angeles. Current outputs are
`ghcn_city/labels_daily.csv` (107,451 GHCN daily rows; NYC 1869+, LA 1944+,
Austin 1948+), `city_asos/asos_parsed.csv` (20,657 settlement-station METAR
rows from 2025-12-31 through 2026-09-10), `city_nearby_asos/` (16,589 rows,
2026-08-12 through 2026-09-11), `city_nws_cli/` (91 CLI product versions,
2026-08-31 through 2026-09-11), `solar_city/solar_features.csv` (762 rows),
and `derived_intraday_state_city/derived_intraday_state.csv` (20,654 rows).
The older PHX/LAS rows were removed from the active data directory.
# NOAA NOMADS forecast layer

`scripts/weather/nomads_forecasts.py` uses the official filtered endpoints
`filter_hrrr_2d.pl` and `filter_blend.pl`, requesting only PHX/KLAS bounding
boxes and selected variables. It stores immutable GRIB2 plus a manifest with
initialization, valid time, lead, coordinates, URL, and SHA-256. Run, for
example, `python3 scripts/weather/nomads_forecasts.py --model hrrr
--init 2026-09-10T12:00:00Z --leads 0 1 2`.

Decoding requires optional `python-eccodes` (preferred) or `wgrib2`; this
checkout does not assume either is installed. `asof_forecasts.py` filters
training inputs so initialization and valid times do not exceed the decision
timestamp. NOMADS retention and archived-run availability vary; failed or
missing runs are recorded by the downloader's exit status rather than filled.
