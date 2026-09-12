"""Shared helpers for the weather data foundation.

Stdlib only. Provides:
- project path layout (repo/data/weather_research)
- HTTP fetch with retries / backoff (urllib, no external deps)
- timezone helpers for Phoenix (no DST) and Las Vegas (DST)
- robust float / missing-value parsing shared by all modules
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data"
RESEARCH_DIR = DATA_ROOT / "weather_research"

USER_AGENT = "kalshi-weather-research/1.0 (github maintenance workspace)"


def ensure_runtime_dirs() -> dict[str, Path]:
    """Create (if needed) and return the standard output directory layout."""
    dirs = {
        "research": RESEARCH_DIR,
        "ghcn_raw": DATA_ROOT / "raw_ghcn",
        "ghcn_out": RESEARCH_DIR / "ghcn",
        "iem_out": RESEARCH_DIR / "iem",
        "solar_out": RESEARCH_DIR / "solar",
        "kalshi_out": RESEARCH_DIR / "kalshi",
        "stations_out": RESEARCH_DIR / "stations",
        "reports": RESEARCH_DIR / "reports",
        "gefs": RESEARCH_DIR / "gefs",
        "gefs_raw": RESEARCH_DIR / "gefs" / "raw",
        "gefs_history": RESEARCH_DIR / "gefs" / "historical_raw",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def http_get(url: str, timeout: int = 60, max_retries: int = 5,
             retry_base: float = 2.0) -> bytes:
    """GET a URL with bounded retries and exponential backoff.

    Raises the last exception after ``max_retries`` attempts.
    """
    headers = {"User-Agent": USER_AGENT}
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in (429, 500, 502, 503, 504):
                wait = retry_base * (2 ** attempt)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_exc = exc
            wait = retry_base * (2 ** attempt)
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def http_get_text(url: str, timeout: int = 60, max_retries: int = 5) -> str:
    return http_get(url, timeout=timeout, max_retries=max_retries).decode(
        "utf-8", errors="replace"
    )


def http_get_json(url: str, timeout: int = 60, max_retries: int = 5):
    return json.loads(http_get(url, timeout=timeout, max_retries=max_retries))


def to_float(value: object) -> float | None:
    """Parse a number from IEM/GHCN/Kalshi strings; None for missing."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s in ("", "M", "T", "null", "NA", "None", "-9999"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def local_date_of_utc(utc_dt, tz_name: str) -> str:
    """Map a UTC datetime to the local calendar date string (YYYY-MM-DD)."""
    return utc_dt.astimezone(ZoneInfo(tz_name)).date().isoformat()


def parse_utc_iso(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp to an aware UTC datetime.

    Accepts ``Z`` or ``+00:00`` suffixes and naive strings (assumed UTC).
    Returns None for empty/None or unparseable values. All modules that write
    timestamps use this so downstream joins see one canonical form.
    """
    if value is None or isinstance(value, bool):
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_iso(dt: datetime) -> str:
    """Render a datetime as canonical ``YYYY-MM-DDTHH:MM:SSZ`` UTC."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
