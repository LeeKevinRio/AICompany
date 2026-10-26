"""Domain data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

TripType = Literal["round_trip", "one_way"]
DateMode = Literal["fixed", "flexible"]
WatchStatus = Literal["active", "paused", "stale", "expired"]
PriceKind = Literal["live", "cached"]
AsOfBasis = Literal["source_reported", "fetch_time"]
QueryStatus = Literal["ok", "no_data", "blocked", "error"]
AlertReason = Literal["below_budget", "drop_pct", "new_low"]

SCANNABLE_STATUSES: frozenset[str] = frozenset({"active", "stale"})


@dataclass(frozen=True, order=True)
class DatePair:
    depart: date
    return_date: date | None = None

    def as_json(self) -> list[str | None]:
        return [
            self.depart.isoformat(),
            self.return_date.isoformat() if self.return_date else None,
        ]

    @classmethod
    def from_json(cls, value: list[str | None]) -> DatePair:
        depart, ret = value[0], value[1]
        if depart is None:
            raise ValueError("depart date missing")
        return cls(date.fromisoformat(depart), date.fromisoformat(ret) if ret else None)


@dataclass(frozen=True)
class WatchSpec:
    """User-editable watch settings (already validated)."""

    name: str
    origin: str
    destination: str
    trip_type: TripType
    date_mode: DateMode
    depart_date: date | None
    return_date: date | None
    window_start: date | None
    window_end: date | None
    min_trip_days: int | None
    max_trip_days: int | None
    max_stops: int | None
    budget_amount_minor: int | None
    currency: str = "TWD"
    notify_on_new_low: bool = True

    def search_shape(self) -> tuple[object, ...]:
        """Fields whose change makes old price history incomparable (bumps revision)."""
        return (
            self.origin,
            self.destination,
            self.trip_type,
            self.date_mode,
            self.depart_date,
            self.return_date,
            self.window_start,
            self.window_end,
            self.min_trip_days,
            self.max_trip_days,
            self.max_stops,
            self.currency,
        )


@dataclass(frozen=True)
class Watch:
    id: int
    spec: WatchSpec
    status: WatchStatus
    revision: int
    sample_offset: int
    last_scanned_at: datetime | None
    consecutive_failed_scans: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class FlightSearch:
    origin: str
    destination: str
    pair: DatePair
    max_stops: int | None
    currency: str = "TWD"
    adults: int = 1
    cabin: str = "economy"

    @property
    def trip_type(self) -> TripType:
        return "round_trip" if self.pair.return_date else "one_way"

    def cache_key(self) -> tuple[object, ...]:
        return (
            self.origin,
            self.destination,
            self.pair,
            self.max_stops,
            self.currency,
            self.adults,
            self.cabin,
        )


@dataclass(frozen=True)
class PriceQuote:
    source: str
    price_kind: PriceKind
    depart_date: date
    return_date: date | None
    amount_minor: int
    currency: str
    as_of: datetime
    as_of_basis: AsOfBasis
    fetched_at: datetime
    carrier: str | None
    stops: int | None
    duration_minutes: int | None
