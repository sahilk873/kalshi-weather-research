# Intraday Temperature Market History

This audit checks Kalshi's historical market tier for hourly/intraday
temperature series. It records availability only; these markets have not yet
been fully downloaded into the normalized research dataset.

## Confirmed availability

| City / series | Markets returned | Oldest date confirmed |
| --- | ---: | --- |
| Miami — `KXTEMPMIAH` | 135 | 2026-04-16 |
| Boston — `KXTEMPBOSH` | 222 | 2026-04-16 |
| Los Angeles — `KXTEMPLAXH` | 1,000+ | At least 2026-07-08 |
| Austin — `KXTEMPAUSH` | 1,000+ | At least 2026-07-08 |
| Washington, DC — `KXTEMPDCH` | 1,000+ | At least 2026-07-08 |
| Chicago — `KXTEMPCHIH` | 1,000+ | At least 2026-07-08 |
| NYC — `KXTEMPNYCH` | 1,000+ | At least 2026-07-08 |
| Coastal LA — `KXTEMPLAXHS` | 0 | No archived markets returned |
| Chicago Metro — `KXTEMPCHIHS` | 0 | No archived markets returned |
| NYC alternate lines — `KXTEMPNYCHS`, `KXHIGHNYD` | 0 | No archived markets returned |

The April 16 results establish that some intraday temperature markets extend
well before the July 2026 Phoenix/Las Vegas archive currently downloaded.
Series returning a pagination cursor may extend earlier than the displayed
minimum; exact minima require a slower resumable crawl because repeated probes
encountered API rate limiting.

## Full temperature-series catalog

The audit was expanded beyond intraday lines to all comparable recurring daily
temperature products found in the Climate and Weather series catalog.

### Daily high-temperature series

| City | Series | Oldest confirmed archived date |
| --- | --- | --- |
| Phoenix | `KXHIGHTPHX` | 2026-02-04 |
| Las Vegas | `KXHIGHTLV` | 2026-02-04 |
| Atlanta | `KXHIGHTATL` | 2026-02-04 |
| Minneapolis | `KXHIGHTMIN` | 2026-02-04 |
| Boston | `KXHIGHTBOS` | 2026-02-05 |
| Dallas | `KXHIGHTDAL` | 2026-02-11 |
| Houston | `KXHIGHTHOU` | 2026-02-11 |
| Oklahoma City | `KXHIGHTOKC` | 2026-02-11 |
| San Antonio | `KXHIGHTSATX` | 2026-02-11 |
| Austin | `KXHIGHAUS` | at least 2026-01-26 |
| Chicago | `KXHIGHCHI` | at least 2026-01-26 |
| Denver | `KXHIGHDEN` | at least 2026-01-26 |
| Los Angeles | `KXHIGHLAX` | at least 2026-01-26 |
| Miami | `KXHIGHMIA` | at least 2026-01-26 |
| New York City | `KXHIGHNY` | at least 2026-01-26 |
| Philadelphia | `KXHIGHPHIL` | at least 2026-01-26 |
| Seattle | `KXHIGHTSEA` | at least 2026-01-26 |
| San Francisco | `KXHIGHTSFO` | at least 2026-01-26 |
| New Orleans | `KXHIGHTNOLA` | at least 2026-01-26 |

An older/alternate Houston series, `KXHIGHHOU`, returned archived markets as
far back as 2024-11-20. It should be treated as a separate legacy contract
family until its rules and station are verified.

### Daily low-temperature series

| City | Series | Oldest confirmed archived date |
| --- | --- | --- |
| Phoenix | `KXLOWTPHX` | 2026-04-03 |
| Las Vegas | `KXLOWTLV` | 2026-04-03 |
| Atlanta | `KXLOWTATL` | 2026-04-03 |
| Boston | `KXLOWTBOS` | 2026-04-03 |
| Dallas | `KXLOWTDAL` | 2026-04-03 |
| Houston | `KXLOWTHOU` | 2026-04-03 |
| Washington, DC | `KXLOWTDC` | 2026-04-03 |
| Minnesota | `KXLOWTMIN` | 2026-04-03 |
| New Orleans | `KXLOWTNOLA` | 2026-04-03 |
| Oklahoma City | `KXLOWTOKC` | 2026-04-03 |
| Seattle | `KXLOWTSEA` | 2026-04-03 |

Other catalogued low-temperature aliases (Los Angeles, Miami, NYC, Chicago,
Denver, Philadelphia, San Francisco, San Diego, Austin, and international
cities) returned no archived markets in the initial probe or require separate
pagination/contract-family verification.

### Hourly/directional temperature series

`KXTEMPMIAH`, `KXTEMPLAXH`, `KXTEMPAUSH`, `KXTEMPDCH`, `KXTEMPCHIHS`,
`KXTEMPBOSH`, `KXTEMPNYCH`, `KXTEMPCHIH`, `KXTEMPLAXHS`, `KXTEMPNYCHS`, and
`KXHIGHNYD` are hourly or directional-temperature lines. The confirmed
availability for these is recorded in the first table; zero-result aliases are
not evidence that the line never traded.

## API and interpretation

The audit queried:

```text
GET https://external-api.kalshi.com/trade-api/v2/historical/markets
    ?series_ticker=<series>&limit=1000
```

Event tickers encode the local event date. The historical endpoint returns
archived market definitions and a cursor when more pages exist. Historical
trades and candlesticks must then be fetched per market using the corresponding
historical endpoints. These are hourly directional-temperature contracts, not
raw thermometer observations.

## Limitations and next step

- This is an availability audit, not a complete data backfill.
- A zero result can mean an alternate/retired line has no archived markets;
  it is not evidence that the product never traded.
- Exact oldest dates for cursor-bearing series remain unverified.
- Historical full order-book snapshots are not exposed by the public API.

Use `scripts/weather/kalshi_historical.py` with the discovered series tickers,
bounded request limits, and `--interval 1m` or `--interval 1h` to perform the
resumable backfill.

Reference: [Kalshi Historical Data API](https://docs.kalshi.com/getting_started/historical_data)

## Repository data coverage ledger

The following dates describe data actually stored in this checkout, not merely
what the API may be able to provide.

### Kalshi market metadata and outcomes

File: `data/weather_research/kalshi/markets.csv`

- 1,680 markets total (420 per PHX/LV daily high/low series)
- Outcome dates: 2026-07-05 through 2026-09-12
- Includes ticker, event, bucket bounds, status, result, timestamps, volume,
  open interest, and contemporaneous quote fields where returned

File: `data/weather_research/kalshi/events.csv`

- 789 events
- Earliest event dates by series range from 2026-01-14 through 2026-04-03;
  these older event records do not imply that all market payloads were locally
  downloaded.

File: `data/weather_research/kalshi/contract_outcomes.csv`

- 1,680 normalized bucket/outcome mappings for the same market set.

### Kalshi trades and candlesticks

Files: `data/weather_research/kalshi/{trades,candlesticks_hourly,candlesticks_daily}.csv`

- Trades: 3,212 records, timestamped 2026-09-10 through 2026-09-11.
- Hourly candles: 662 rows, covering the currently collected September 2026
  markets.
- Daily candles: 24 rows, covering the currently collected September 2026
  markets.

Historical-tier sample files:

Files: `data/weather_research/kalshi_historical/{markets,trades,candles}.csv`

- 32 archived market definitions (8 per PHX/LV daily high/low series)
- 8,315 archived trades
- 1,133 archived hourly candles
- Archived market dates: 2026-07-10 through 2026-07-11
- Raw API responses, including the cutoff response, are retained under
  `data/weather_research/kalshi_historical/raw/`.
- Verified historical cutoff at collection time:
  `2026-07-13T00:00:00Z`.

### Full order-book status

There are **no historical full order-book snapshots** in this repository.

- Historical Kalshi REST endpoints provide markets, trades, and candles, not
  prior book states.
- The order-book REST endpoint returns only the current book for a ticker.
- No authenticated live WebSocket book session was active during the recorded
  collection windows.
- Consequently, there is no date range for exact historical order-book data.
- Future exact books must be collected from WebSocket snapshots and deltas,
  with millisecond receive timestamps and sequence numbers.
- Trades/candles can support approximate execution modeling, but cannot recover
  unexecuted orders, cancellations, queue position, or historical depth.

### Weather data available for alignment

- Final daily GHCN labels: PHX 1933-06-01 onward; LAS 1948-09-06 onward.
- Dense PHX/LAS ASOS/METAR backfill: approximately 2021-01 through 2025-12,
  with a partial 2020-12-31 boundary record.
- Recent PHX/LAS ASOS sample: 2026-08-11 through 2026-09-10.
- Nearby ASOS network: approximately 2026-08-11 through 2026-09-10.
- NWS CLI products: a small set from 2025-12-30 and 2026-09-04 through
  2026-09-09.

These weather dates should not be confused with Kalshi quote availability:
final daily labels are labels only and must not be joined into earlier
intraday decisions.
