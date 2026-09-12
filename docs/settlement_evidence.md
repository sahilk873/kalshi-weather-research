# Settlement reconstruction evidence

## What the contract payloads prove

The Kalshi event metadata presently contains three source labels for these
four series. Of 1,632 finalized buckets, 960 cite an NWS climatological
report (480 Phoenix / 480 Las Vegas) and 672 cite The Weather Company. The
remaining 48 currently-active buckets cite The Weather Company. The event
record, rather than its ticker, determines the legal source.

The NWS-source event labels name `CLIPHX` (NWS Phoenix/`KPSR`) and `CLILAS`
(NWS Las Vegas/`KVEF`). Their corresponding airport METAR stations are KPHX
and KLAS, and their NCEI GHCN identifiers are USW00023183 and USW00023169.

## Public reconstruction test

For finalized contracts with an available GHCN label, there are 1,584 bucket
comparisons. Direct comparison of GHCN's tenths-Celsius conversion to integer
bucket edges agrees with Kalshi 95.2%; conversion to nearest whole Fahrenheit
agrees 100.0%. The 4.8% direct discrepancies are all rounding-edge cases.
This establishes strong observed agreement between airport GHCN daily extremes
and recorded Kalshi outcomes in the current retained event history.

It is not proof that GHCN is legally interchangeable with each settlement
feed. In particular, The Weather Company is a separately named source, its
historical values are not publicly archived here, and the public IEM AFOS
text archive retains only a rolling ~7-day window of raw CLI products
(observed: a 2021–2026 request returned only the window-tail product).
TWC-era backtests may use the observed GHCN calibration proxy only if they
are explicitly labelled **proxy settlement**, with sensitivity tests around
integer boundaries.

## Practical backtest policy

1. For an event with an NWS source, use timestamped CLI text as the preferred
   legal label; use rounded GHCN only when that text is unavailable and tag it
   `label_provenance=ghcn_proxy`.
2. For an event with The Weather Company source, do not call a GHCN value the
   official settlement value. Store its observed Kalshi bucket result as the
   legal outcome and retain GHCN as an explanatory/reconstruction proxy.
3. Exclude or separately report events whose source cannot be reproduced.
4. Use observed METAR extremes only as intraday information. In the current
   29-day overlap, mean absolute official-minus-sampled-high difference is
   1.34 F in PHX and 0.90 F in LV; sampled METAR max/min is not a label.

## Where the numbers come from

Every figure above is derived from the retained normalized tables by the
reproducible generator in
[`docs/settlement_analysis.md`](settlement_analysis.md)
(`python3 scripts/weather/settlement_analysis.py`), with the same
bucket-hit logic implemented in `scripts/weather/validate.py`. The retained
event history is a limited window (Phoenix series begin 2026-02-04, Las
Vegas 2026-01-14; NWS source through outcome date 2026-08-13, The Weather
Company from 2026-08-14). Unexplained label disagreement should be raised
as a data problem, not silently merged away.
