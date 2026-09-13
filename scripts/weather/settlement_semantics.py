"""Settlement-time and bucket semantics for the four PHX/LV daily contracts.

This module encodes the P0 contract/oracle rules needed before any forecast
model is evaluated.  It is intentionally independent of a particular weather
provider: event metadata remains the authority for the settlement source and
station, while these helpers provide the local-standard-time day and the
published whole-degree bucket geometry.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import erf, sqrt, isfinite
from typing import Iterable, Mapping

from stations import CITIES


@dataclass(frozen=True)
class StandardTimeWindow:
    """A settlement day expressed in UTC and the civil timezone used for display."""

    city: str
    outcome_local_date: str
    start_utc: datetime
    end_utc: datetime
    standard_utc_offset_hours: int


@dataclass(frozen=True)
class TemperatureBucket:
    """An inclusive published whole-degree range; ``None`` denotes an open tail."""

    market_ticker: str
    floor_f: int | None
    ceil_f: int | None

@dataclass(frozen=True)
class GaussianTemperatureDistribution:
    """Reusable monotone Gaussian CDF for all active contract thresholds."""
    mean_f: float
    stddev_f: float

    def __post_init__(self) -> None:
        if not isfinite(self.mean_f) or not isfinite(self.stddev_f) or self.stddev_f <= 0:
            raise ValueError("mean_f must be finite and stddev_f must be positive")

    def cdf(self, temp_f: float) -> float:
        return 0.5 * (1.0 + erf((float(temp_f) - self.mean_f) / (self.stddev_f * sqrt(2.0))))

    def prob_above(self, threshold_f: float) -> float:
        return 1.0 - self.cdf(threshold_f)

    def quantile(self, probability: float) -> float:
        if not 0.0 <= probability <= 1.0:
            raise ValueError("probability must be in [0, 1]")
        if probability == 0: return float("-inf")
        if probability == 1: return float("inf")
        lo, hi = self.mean_f - 12 * self.stddev_f, self.mean_f + 12 * self.stddev_f
        for _ in range(80):
            mid = (lo + hi) / 2
            if self.cdf(mid) < probability: lo = mid
            else: hi = mid
        return (lo + hi) / 2


def settlement_standard_time_window(city: str, outcome_local_date: str) -> StandardTimeWindow:
    """Return the exact 24-hour NWS local-standard-time window in UTC.

    Phoenix is MST (UTC-7) throughout the year.  Las Vegas uses PST (UTC-8)
    for this settlement clock even during PDT; e.g. on a summer date the UTC
    interval appears as 01:00 PDT through 00:59 PDT on the following civil
    date.  This is intentionally *not* a civil-midnight ``ZoneInfo`` window.
    """
    if city not in CITIES:
        raise ValueError(f"unknown city {city!r}; expected one of {sorted(CITIES)}")
    try:
        day = date.fromisoformat(outcome_local_date)
    except ValueError as exc:
        raise ValueError("outcome_local_date must be YYYY-MM-DD") from exc
    offset_hours = -7 if city == "phx" else -8
    standard_tz = timezone(timedelta(hours=offset_hours))
    start = datetime.combine(day, datetime.min.time(), tzinfo=standard_tz)
    return StandardTimeWindow(
        city=city,
        outcome_local_date=outcome_local_date,
        start_utc=start.astimezone(timezone.utc),
        end_utc=(start + timedelta(days=1)).astimezone(timezone.utc),
        standard_utc_offset_hours=offset_hours,
    )


def bucket_from_market(row: Mapping[str, object]) -> TemperatureBucket:
    """Build a typed bucket from normalized Kalshi market metadata."""
    def optional_int(value: object) -> int | None:
        if value in (None, ""):
            return None
        numeric = float(str(value))
        if not numeric.is_integer():
            raise ValueError(f"bucket boundary must be a whole Fahrenheit value: {value!r}")
        return int(numeric)

    bucket = TemperatureBucket(
        market_ticker=str(row.get("market_ticker") or ""),
        floor_f=optional_int(row.get("bucket_floor_f")),
        ceil_f=optional_int(row.get("bucket_ceil_f")),
    )
    if not bucket.market_ticker:
        raise ValueError("market_ticker is required")
    if bucket.floor_f is None and bucket.ceil_f is None:
        raise ValueError(f"{bucket.market_ticker}: bucket cannot have two open boundaries")
    if (bucket.floor_f is not None and bucket.ceil_f is not None
            and bucket.floor_f > bucket.ceil_f):
        raise ValueError(f"{bucket.market_ticker}: floor exceeds ceiling")
    return bucket


def normal_bucket_probabilities(
    buckets: Iterable[TemperatureBucket], mean_f: float, stddev_f: float,
) -> dict[str, float]:
    """Map one continuous Gaussian forecast to coherent published buckets.

    The settlement providers publish whole Fahrenheit values.  Therefore an
    internal inclusive bucket ``L..U`` corresponds to latent temperatures in
    ``[L-0.5, U+0.5)`` under nearest-integer reporting.  Continuous normal
    forecasts assign zero mass to the half-degree ties.  The supplied bucket
    set must be a gap-free, non-overlapping partition with open tails.
    """
    if stddev_f <= 0:
        raise ValueError("stddev_f must be positive")
    ordered = sorted(buckets, key=lambda b: float("-inf") if b.floor_f is None else b.floor_f)
    if not ordered:
        raise ValueError("at least one bucket is required")
    _assert_partition(ordered)

    distribution = GaussianTemperatureDistribution(mean_f, stddev_f)

    probabilities: dict[str, float] = {}
    for bucket in ordered:
        lo = 0.0 if bucket.floor_f is None else distribution.cdf(bucket.floor_f - 0.5)
        hi = 1.0 if bucket.ceil_f is None else distribution.cdf(bucket.ceil_f + 0.5)
        probabilities[bucket.market_ticker] = max(0.0, hi - lo)
    total = sum(probabilities.values())
    if abs(total - 1.0) > 1e-12:
        raise AssertionError(f"bucket probabilities must sum to one, got {total}")
    return probabilities


def _assert_partition(buckets: list[TemperatureBucket]) -> None:
    if buckets[0].floor_f is not None or buckets[-1].ceil_f is not None:
        raise ValueError("bucket set must include both open tails")
    seen: set[str] = set()
    for index, bucket in enumerate(buckets):
        if bucket.market_ticker in seen:
            raise ValueError(f"duplicate market ticker {bucket.market_ticker}")
        seen.add(bucket.market_ticker)
        if index == 0:
            continue
        prior = buckets[index - 1]
        if prior.ceil_f is None or bucket.floor_f is None:
            raise ValueError("only first/last buckets may be open-tailed")
        if bucket.floor_f != prior.ceil_f + 1:
            raise ValueError(
                f"bucket partition gap/overlap between {prior.market_ticker} and {bucket.market_ticker}"
            )
