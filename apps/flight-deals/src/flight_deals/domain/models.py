"""Domain data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol

TripType = Literal["round_trip", "one_way"]
DateMode = Literal["fixed", "flexible"]
WatchStatus = Literal["active", "paused", "stale", "expired"]
PriceKind = Literal["live", "cached"]
AsOfBasis = Literal["source_reported", "fetch_time"]
QueryStatus = Literal["ok", "no_data", "blocked", "error"]
AlertReason = Literal["below_budget", "drop_pct", "new_low"]
NotificationKind = Literal[
    "price_alert", "ops_source_failure", "test", "daily_digest", "command", "manual_digest"
]
# Kinds that are delivered once and never retried (ADR-0002 FD-7 Decisions 5 and 6).
SEND_ONCE_KINDS: frozenset[str] = frozenset({"command", "manual_digest"})
# Cabin values are snake_case in the domain; only sources/google_flights.py maps them to
# the price source's own strings (ADR-0002 FD-5 Decision 3).
Cabin = Literal["economy", "premium_economy", "business", "first"]
CABINS: tuple[Cabin, ...] = ("economy", "premium_economy", "business", "first")

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
    # Trip options (FD-5). Defaults are what every pre-FD-5 watch means.
    adults: int = 1
    children: int = 0
    cabin: Cabin = "economy"
    # Upper-case IATA codes, sorted and de-duplicated; empty = any airline.
    airlines: tuple[str, ...] = ()
    # Outbound departure window in whole hours (both set or both None, from < to).
    dep_hour_from: int | None = None
    dep_hour_to: int | None = None

    def search_shape(self) -> tuple[object, ...]:
        """Fields whose change makes old price history incomparable (bumps revision).

        Name, budget and notification switches are deliberately left out; airlines are
        compared as a set so the order they were ticked in never matters.
        """
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
            self.adults,
            self.children,
            self.cabin,
            tuple(sorted(set(self.airlines))),
            self.dep_hour_from,
            self.dep_hour_to,
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
    """One outbound query. Build it with ``search_for`` (the single construction point)."""

    origin: str
    destination: str
    pair: DatePair
    max_stops: int | None
    currency: str = "TWD"
    adults: int = 1
    children: int = 0
    cabin: Cabin = "economy"
    airlines: tuple[str, ...] = ()
    dep_hour_from: int | None = None
    dep_hour_to: int | None = None

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
            self.children,
            self.cabin,
            self.airlines,
            self.dep_hour_from,
            self.dep_hour_to,
        )


class SearchConditions(Protocol):
    """Query conditions shared by a watch and an exploration (ADR-0002 FD-6 Decision 2)."""

    @property
    def origin(self) -> str: ...

    @property
    def destination(self) -> str: ...

    @property
    def max_stops(self) -> int | None: ...

    @property
    def adults(self) -> int: ...

    @property
    def children(self) -> int: ...

    @property
    def cabin(self) -> Cabin: ...

    @property
    def airlines(self) -> tuple[str, ...]: ...

    @property
    def dep_hour_from(self) -> int | None: ...

    @property
    def dep_hour_to(self) -> int | None: ...


@dataclass(frozen=True)
class ExplorationSpec:
    """One month explored day by day (already validated; FD-6 Decision 2).

    ``trip_days`` is set for round trips only: each return is departure + trip_days.
    """

    origin: str
    destination: str
    trip_type: TripType
    year: int
    month: int
    trip_days: int | None
    max_stops: int | None
    adults: int = 1
    children: int = 0
    cabin: Cabin = "economy"
    airlines: tuple[str, ...] = ()
    dep_hour_from: int | None = None
    dep_hour_to: int | None = None
    currency: str = "TWD"

    @property
    def month_text(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def condition_key(self) -> str:
        """Equality key for reuse: airlines as a set, unset values written as "-"."""

        def part(value: int | None) -> str:
            return "-" if value is None else str(value)

        airlines = ",".join(sorted(set(self.airlines))) or "-"
        return "|".join(
            [
                "v1",
                self.origin,
                self.destination,
                self.trip_type,
                self.month_text,
                part(self.trip_days),
                part(self.max_stops),
                str(self.adults),
                str(self.children),
                self.cabin,
                airlines,
                part(self.dep_hour_from),
                part(self.dep_hour_to),
                self.currency,
            ]
        )


@dataclass(frozen=True)
class ComparisonTarget:
    """One destination of a comparison as query conditions (satisfies SearchConditions).

    Comparisons have no airline or departure-hour filter and always mean 1 adult
    (ADR-0002 FD-9 Decision 2)."""

    origin: str
    destination: str
    max_stops: int | None
    cabin: Cabin = "economy"
    adults: int = 1
    children: int = 0
    airlines: tuple[str, ...] = ()
    dep_hour_from: int | None = None
    dep_hour_to: int | None = None


@dataclass(frozen=True)
class ComparisonSpec:
    """One date pair compared across 2-8 destinations (already validated; FD-9).

    ``destinations`` keeps the input order (it decides ties); ``return_date`` is None
    exactly for one-way trips. Passengers are fixed at 1 adult.
    """

    origin: str
    destinations: tuple[str, ...]
    trip_type: TripType
    depart_date: date
    return_date: date | None
    max_stops: int | None
    cabin: Cabin = "economy"
    currency: str = "TWD"
    adults: int = 1
    children: int = 0

    @property
    def pair(self) -> DatePair:
        return DatePair(self.depart_date, self.return_date)

    def target(self, destination: str) -> ComparisonTarget:
        return ComparisonTarget(
            origin=self.origin,
            destination=destination,
            max_stops=self.max_stops,
            cabin=self.cabin,
            adults=self.adults,
            children=self.children,
        )

    def condition_key(self) -> str:
        """Equality key for reuse: destinations as a sorted set, unset values as "-"."""
        return "|".join(
            [
                "cmp1",
                self.origin,
                ",".join(sorted(set(self.destinations))),
                self.trip_type,
                self.depart_date.isoformat(),
                self.return_date.isoformat() if self.return_date else "-",
                "-" if self.max_stops is None else str(self.max_stops),
                str(self.adults),
                str(self.children),
                self.cabin,
                self.currency,
            ]
        )


def search_for(cond: SearchConditions, pair: DatePair, currency: str) -> FlightSearch:
    """The only place a ``FlightSearch`` is built (scans, explorations, comparisons, links)."""
    spec = cond
    return FlightSearch(
        origin=spec.origin,
        destination=spec.destination,
        pair=pair,
        max_stops=spec.max_stops,
        currency=currency,
        adults=spec.adults,
        children=spec.children,
        cabin=spec.cabin,
        airlines=tuple(sorted(set(spec.airlines))),
        dep_hour_from=spec.dep_hour_from,
        dep_hour_to=spec.dep_hour_to,
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
    # Local departure time "HH:MM" of the first segment; optional (FD-5 Decision 4).
    depart_time: str | None = None
