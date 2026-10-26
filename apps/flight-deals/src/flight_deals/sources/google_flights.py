"""Google Flights adapter built on the unofficial ``fast_flights`` package.

This is the only module allowed to import ``fast_flights``. Third-party fetch modes
(``integration=``, proxies, Bright Data, SearchApi, remote browsers) are never used.
Results are classified as ok / no_data / blocked / error; an empty or unparseable
answer is ``blocked``, never "no flights".
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from fast_flights import FlightQuery, FlightsNotFound, Passengers, create_query, get_flights

from flight_deals.domain.models import FlightSearch, PriceKind
from flight_deals.domain.timeutil import utc_now
from flight_deals.ports import Clock, SourceResult
from flight_deals.redact import redact_truncate
from flight_deals.sources._records import RecordFormatError, quotes_from_records
from flight_deals.sources._support import (
    Throttle,
    TimeoutRunner,
    TTLCache,
    WorkersExhaustedError,
    backoff_delay,
    call_with_timeout,
)

SOURCE_NAME = "google_flights"
LANGUAGE = "zh-TW"

FetchFn = Callable[[FlightSearch], Sequence[Any]]

# Exceptions that mean "the page did not have the shape we expected".
_PARSE_ERRORS: tuple[type[BaseException], ...] = (
    AttributeError,
    IndexError,
    KeyError,
    TypeError,
    ValueError,
    RecordFormatError,
)


def build_query(search: FlightSearch) -> Any:
    legs = [
        FlightQuery(
            date=search.pair.depart.isoformat(),
            from_airport=search.origin,
            to_airport=search.destination,
            max_stops=search.max_stops,
        )
    ]
    if search.pair.return_date is not None:
        legs.append(
            FlightQuery(
                date=search.pair.return_date.isoformat(),
                from_airport=search.destination,
                to_airport=search.origin,
                max_stops=search.max_stops,
            )
        )
    return create_query(
        flights=legs,
        seat="economy",
        trip="round-trip" if search.pair.return_date is not None else "one-way",
        passengers=Passengers(adults=search.adults),
        language=LANGUAGE,
        currency=search.currency,
    )


def fetch_live(search: FlightSearch) -> Sequence[Any]:
    """Real network call through fast_flights' own fetcher (no integration, no proxy)."""
    result: Sequence[Any] = get_flights(build_query(search))
    return result


def to_records(raw: Sequence[Any]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for item in raw:
        if dataclasses.is_dataclass(item) and not isinstance(item, type):
            records.append(dataclasses.asdict(item))
        elif isinstance(item, Mapping):
            records.append(item)
        else:
            raise RecordFormatError(f"unexpected result item type {type(item).__name__}")
    return records


class GoogleFlightsSource:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_attempts: int,
        backoff_base_seconds: float,
        throttle: Throttle,
        cache: TTLCache[tuple[object, ...], SourceResult],
        fetch: FetchFn = fetch_live,
        clock: Clock = utc_now,
        sleep: Callable[[float], None] = time.sleep,
        runner: TimeoutRunner | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._max_attempts = max(1, max_attempts)
        self._backoff = backoff_base_seconds
        self._throttle = throttle
        self._cache = cache
        self._fetch = fetch
        self._clock = clock
        self._sleep = sleep
        self._runner = runner

    @property
    def name(self) -> str:
        return SOURCE_NAME

    @property
    def price_kind(self) -> PriceKind:
        return "live"

    def search(self, query: FlightSearch) -> SourceResult:
        key = query.cache_key()
        cached = self._cache.get(key)
        if cached is not None:
            return replace(cached, attempts=0, from_cache=True)

        result: SourceResult | None = None
        attempts = 0
        for attempt in range(1, self._max_attempts + 1):
            if attempt > 1:
                self._sleep(backoff_delay(self._backoff, attempt - 1))
            self._throttle.wait()
            attempts += 1
            result = self._attempt(query, attempts)
            if result.status != "error":
                break
        assert result is not None
        if result.status in ("ok", "no_data"):
            self._cache.put(key, result)
        return result

    def _attempt(self, query: FlightSearch, attempts: int) -> SourceResult:
        fetched_at = self._clock()

        def failed(status: str, message: str) -> SourceResult:
            return SourceResult(
                source=SOURCE_NAME,
                status="blocked" if status == "blocked" else "error",
                fetched_at=fetched_at,
                error=redact_truncate(message),
                attempts=attempts,
            )

        try:
            raw = call_with_timeout(lambda: self._fetch(query), self._timeout, self._runner)
        except FlightsNotFound as exc:
            return SourceResult(
                source=SOURCE_NAME,
                status="no_data",
                fetched_at=fetched_at,
                error=redact_truncate(f"no flights found: {exc}"),
                attempts=attempts,
            )
        except WorkersExhaustedError as exc:
            return failed("error", str(exc))
        except TimeoutError as exc:
            return failed("error", f"timeout: {exc}")
        except _PARSE_ERRORS as exc:
            return failed("blocked", f"unparseable response ({type(exc).__name__}): {exc}")
        except Exception as exc:  # any other library/network failure is an error
            return failed("error", f"{type(exc).__name__}: {exc}")

        try:
            quotes = quotes_from_records(
                to_records(raw),
                source=SOURCE_NAME,
                price_kind="live",
                currency=query.currency,
                depart_date=query.pair.depart,
                return_date=query.pair.return_date,
                fetched_at=fetched_at,
            )
        except _PARSE_ERRORS as exc:
            return failed("blocked", f"unexpected result format ({type(exc).__name__}): {exc}")
        if not quotes:
            return failed("blocked", "empty result (blank page or no priced itineraries)")
        return SourceResult(
            source=SOURCE_NAME,
            status="ok",
            fetched_at=fetched_at,
            quotes=tuple(quotes),
            attempts=attempts,
        )
