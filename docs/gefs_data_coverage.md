# GEFS data coverage and historical limits

The current archive was populated on 2026-09-12.

## Member-level ensemble archive

The Open-Meteo Ensemble API provides individual member arrays for
`ncep_gefs025`, `ncep_gefs05`, and `ncep_gefs_seamless`. The seven requested
cities are stored in `gefs/gefs_members.parquet`, with raw responses and
SHA-256 manifests under `gefs/raw/`. The current archive contains 599,040
member-variable rows and 1,536 temperature distribution-feature rows. The
responses observed in this run contained 30 temperature members (`member01`
through `member30`) per city/model response. Every probability uses the
recorded available-member count as its denominator.

The API's member history is short: its historical/past-days capability is not
a multi-year archive of real-time perturbed members. Scheduled collection is
therefore required to build future training history. The live collector uses
`ncep_gefs025` by default and keeps the other two identifiers available for
comparison.

## Older history

`gefs/historical_raw/` contains seven-city `ncep_gfs_seamless` historical
forecast responses from 2021-03-01 through 2026-09-11, with 340,272 hourly
prediction rows. These are deterministic/seamless historical forecast values,
not reconstructed GEFS members, and must not be used as a member distribution.
The historical endpoint returned null values for the requested GEFS member
arrays on the tested older dates; null members were excluded rather than
fabricated.

NOAA NOMADS is the authoritative operational GEFS source for fresh GRIB2
files, but its operational server retains only a short rolling window. NOAA's
GEFSv12 retrospective archive is useful historical ensemble context, but it is
not an archive of the real-time forecasts: it covers 2000-2019 and typically
has five members, with occasional 11-member runs. It is therefore not merged
into the 30-member live contract.

## Reproduce

```bash
python3 scripts/weather/gefs_ensemble.py \
  --cities nyc los_angeles austin chicago dc boston miami \
  --models ncep_gefs025 ncep_gefs05 ncep_gefs_seamless --forecast-days 3
python3 scripts/weather/gefs_features.py
python3 scripts/weather/gefs_historical.py --api historical \
  --cities nyc los_angeles austin chicago dc boston miami \
  --start 2021-03-01 --end 2026-09-11 --model ncep_gfs_seamless
python3 scripts/weather/load_sqlite.py
```

Historical and previous-runs products are useful for forecast-error
calibration at fixed lead times, but they do not provide the full historical
live ensemble required for exact distribution reconstruction. Calibration
must join predictions to actuals using valid time and retain run provenance.
