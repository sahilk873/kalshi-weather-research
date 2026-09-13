"""Station and series configuration for the weather research set.

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

# Kalshi's broader temperature universe. These entries are collector metadata
# only: they do not assert that a local station, settlement source, or
# point-in-time label archive is configured for every city.
KALSHI_SERIES_CATALOG = {
    # Daily high/low series currently surfaced by Kalshi.
    "KXHIGHNY": ("nyc", "high", "daily"),
    "KXLOWTNYC": ("nyc", "low", "daily"),
    "KXHIGHLAX": ("la", "high", "daily"),
    "KXLOWTLAX": ("la", "low", "daily"),
    "KXHIGHCHI": ("chicago", "high", "daily"),
    "KXLOWTCHI": ("chicago", "low", "daily"),
    "KXHIGHMIA": ("miami", "high", "daily"),
    "KXLOWTMIA": ("miami", "low", "daily"),
    "KXHIGHAUS": ("austin", "high", "daily"),
    "KXLOWTAUS": ("austin", "low", "daily"),
    "KXHIGHTDAL": ("dallas", "high", "daily"),
    "KXLOWTDAL": ("dallas", "low", "daily"),
    "KXHIGHTHOU": ("houston", "high", "daily"),
    "KXLOWTHOU": ("houston", "low", "daily"),
    "KXHIGHTSATX": ("san_antonio", "high", "daily"),
    "KXLOWTSATX": ("san_antonio", "low", "daily"),
    "KXHIGHTOKC": ("oklahoma_city", "high", "daily"),
    "KXLOWTOKC": ("oklahoma_city", "low", "daily"),
    "KXHIGHTPHX": ("phx", "high", "daily"),
    "KXLOWTPHX": ("phx", "low", "daily"),
    "KXHIGHTLV": ("lv", "high", "daily"),
    "KXLOWTLV": ("lv", "low", "daily"),
    "KXHIGHTSFO": ("san_francisco", "high", "daily"),
    "KXLOWTSFO": ("san_francisco", "low", "daily"),
    "KXHIGHTSEA": ("seattle", "high", "daily"),
    "KXLOWTSEA": ("seattle", "low", "daily"),
    "KXHIGHDEN": ("denver", "high", "daily"),
    "KXLOWTDEN": ("denver", "low", "daily"),
    "KXHIGHTATL": ("atlanta", "high", "daily"),
    "KXLOWTATL": ("atlanta", "low", "daily"),
    "KXHIGHPHIL": ("philadelphia", "high", "daily"),
    "KXLOWTPHIL": ("philadelphia", "low", "daily"),
    "KXHIGHTDC": ("washington_dc", "high", "daily"),
    "KXLOWTDC": ("washington_dc", "low", "daily"),
    "KXHIGHTBOS": ("boston", "high", "daily"),
    "KXLOWTBOS": ("boston", "low", "daily"),
    "KXHIGHTMIN": ("minneapolis", "high", "daily"),
    "KXLOWTMIN": ("minneapolis", "low", "daily"),
    "KXHIGHTNOLA": ("new_orleans", "high", "daily"),
    "KXLOWTNOLA": ("new_orleans", "low", "daily"),
    "KXHIGHTEWR": ("newark", "high", "daily"),
    # Current hourly directional series.
    "KXTEMPNYCHS": ("nyc", "hourly" , "hourly"),
    "KXTEMPLAXHS": ("la", "hourly", "hourly"),
    "KXTEMPCHIHS": ("chicago", "hourly", "hourly"),
    "KXTEMPMIAH": ("miami", "hourly", "hourly"),
    # Older hourly families retained for historical collection.
    "KXTEMPNYCH": ("nyc", "hourly", "hourly"),
    "KXTEMPLAXH": ("la", "hourly", "hourly"),
    "KXTEMPCHIH": ("chicago", "hourly", "hourly"),
    "KXTEMPAUSH": ("austin", "hourly", "hourly"),
    "KXTEMPDCH": ("washington_dc", "hourly", "hourly"),
}

KALSHI_SEED_SERIES = tuple(KALSHI_SERIES_CATALOG)


def get_cities(names=DEFAULT_CITIES) -> list[City]:
    bad = [n for n in names if n not in CITIES]
    if bad:
        raise ValueError(f"unknown city keys: {bad}; known={sorted(CITIES)}")
    return [CITIES[n] for n in names]
