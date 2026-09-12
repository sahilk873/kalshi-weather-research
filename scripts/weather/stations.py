"""Station and series configuration for the Phoenix / Las Vegas research set.

Only the four Kalshi daily temperature series are in scope:
  KXHIGHTPHX  Phoenix daily high (Fahrenheit buckets)
  KXLOWTPHX   Phoenix daily low
  KXHIGHTLV   Las Vegas daily high
  KXLOWTLV    Las Vegas daily low

Data-source station identity:
- GHCN-Daily (NCEI) station IDs, same stations NWS uses for the city airports
  that Kalshi's climate products reference.
- IEM ASOS networks: AZ_ASOS / NV_ASOS; local METAR sites KPHX / KLAS.
- IEM network GeoJSON links ASOS sid <-> ncei91 GHCN id.
"""

from __future__ import annotations

from dataclasses import dataclass

# Public NCEI GHCN-Daily static files
GHCN_DAILY_BASE = "https://www.ncei.noaa.gov/pub/data/ghcn/daily"
GHCN_ALL_URL = f"{GHCN_DAILY_BASE}/all"           # per-station .dly files
GHCN_STATIONS_URL = f"{GHCN_DAILY_BASE}/ghcnd-stations.txt"
GHCN_INVENTORY_URL = f"{GHCN_DAILY_BASE}/ghcnd-inventory.txt"

# Iowa Environmental Mesonet (IEM) ASOS archive
IEM_ASOS_DOWNLOAD = (
    "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
)
IEM_NETWORK_GEOJSON = (
    "https://mesonet.agron.iastate.edu/geojson/network/{network}.geojson"
)

# Kalshi public trade API v2 (see checked-in openapi.yaml, source docs.kalshi.com)
KALSHI_API_BASE = "https://external-api.kalshi.com/trade-api/v2"

# Kalshi WebSocket endpoint from checked-in asyncapi.yaml
KALSHI_WS_URL = "wss://external-api-ws.kalshi.com/trade-api/ws/v2"


@dataclass(frozen=True)
class City:
    key: str
    city: str
    tz_name: str            # IANA zone used for the local outcome date
    iem_network: str
    iem_sid: str            # ASOS station
    ghcn_id: str            # GHCN-Daily station (matches IEM ncei91)
    lat: float
    lon: float
    kalshi_high_series: str
    kalshi_low_series: str
    # strike_date is UTC midnight-ish expressed in *standard* time:
    # PHX = 07:00Z, LAS = 08:00Z, i.e. one day after the local outcome date.
    strike_utc_hour: int
    nws_cli_site: str       # NWS site for the CLI climate product
    nws_cli_issuedby: str


CITIES = {
    "phx": City(
        key="phx",
        city="Phoenix",
        tz_name="America/Phoenix",
        iem_network="AZ_ASOS",
        iem_sid="PHX",
        ghcn_id="USW00023183",
        lat=33.4278,
        lon=-112.0036,
        kalshi_high_series="KXHIGHTPHX",
        kalshi_low_series="KXLOWTPHX",
        strike_utc_hour=7,
        nws_cli_site="PSR",
        nws_cli_issuedby="PHX",
    ),
    "lv": City(
        key="lv",
        city="Las Vegas",
        tz_name="America/Los_Angeles",
        iem_network="NV_ASOS",
        iem_sid="LAS",
        ghcn_id="USW00023169",
        lat=36.0719,
        lon=-115.1633,
        kalshi_high_series="KXHIGHTLV",
        kalshi_low_series="KXLOWTLV",
        strike_utc_hour=8,
        nws_cli_site="VEF",
        nws_cli_issuedby="LAS",
    ),
}

KALSHI_SERIES_TO_CITY = {
    c.kalshi_high_series: c
    for c in CITIES.values()
}
KALSHI_SERIES_TO_CITY.update(
    {c.kalshi_low_series: c for c in CITIES.values()}
)

# Map series ticker -> 'high' | 'low'
SERIES_TEMP_TYPE = {
    c.kalshi_high_series: "high"
    for c in CITIES.values()
}
SERIES_TEMP_TYPE.update(
    {c.kalshi_low_series: "low" for c in CITIES.values()}
)

DEFAULT_CITIES = ("phx", "lv")


def get_cities(names=DEFAULT_CITIES) -> list[City]:
    bad = [n for n in names if n not in CITIES]
    if bad:
        raise ValueError(f"unknown city keys: {bad}; known={sorted(CITIES)}")
    return [CITIES[n] for n in names]