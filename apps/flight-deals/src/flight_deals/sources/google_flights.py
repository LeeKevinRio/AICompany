"""Google Flights adapter built on the unofficial ``fast_flights`` package.

This is the only module allowed to import ``fast_flights``, and only its query builder
and HTML fetcher are used; the page is parsed by ``sources.google_payload`` so that one
unpriced itinerary no longer discards the whole answer (ADR-0002 FD-3 Decision 1).
Third-party fetch modes (``integration=``, ``fetch_integration=``, proxies, Bright Data,
SearchApi, remote browsers) are never used. Results are classified as ok / no_data /
blocked / error; an empty or unparseable answer is ``blocked``, never "no flights".
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from urllib.parse import urlencode

from fast_flights import FlightQuery, Passengers, create_query, fetch_flights_html

from flight_deals.domain.models import (
    Cabin,
    FlightSearch,
    PriceKind,
    PriceQuote,
    QueryStatus,
    ReturnLeg,
    SegmentRef,
    quote_rank_key,
)
from flight_deals.domain.timeutil import utc_now
from flight_deals.ports import Clock, ParseStats, ReturnLegResult, SourceResult
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
from flight_deals.sources.google_payload import (
    PayloadErrorStatus,
    PayloadFormatError,
    extract_payload,
    parse_payload,
)

log = logging.getLogger(__name__)

SOURCE_NAME = "google_flights"
LANGUAGE = "zh-TW"
# The payload layout in sources/google_payload.py was verified against this release.
# Tests compare it with the installed version; on upgrade, rerun the live smoke test
# and re-record tests/fixtures/payload_TPE_SHA.json before changing it.
VERIFIED_FAST_FLIGHTS_VERSION = "3.1.0"

FetchFn = Callable[[FlightSearch], str]

NO_STATS = ParseStats(itineraries=0, priced=0, unpriced=0, malformed=0)
# Sub-reason of ``no_data`` when neither result section is embedded in the page. Seen
# live 2026-10-28 for round trip + business + several passengers: the browser loads
# the results later, the server-rendered page carries none. Not a source failure.
NO_EMBEDDED_RESULTS = "no_embedded_results"


# Domain cabin names -> fast_flights seat strings (the only place this mapping lives).
SEAT_BY_CABIN: dict[Cabin, str] = {
    "economy": "economy",
    "premium_economy": "premium-economy",
    "business": "business",
    "first": "first",
}
# Browser search page for a ``?tfs=`` query (same base fast_flights' Query.url() uses).
BOOKING_BASE_URL = "https://www.google.com/travel/flights/search"


def _leg(search: FlightSearch, date: str, origin: str, destination: str, *, outbound: bool) -> Any:
    # Airlines and max stops apply to both legs; the departure window only to the
    # outbound leg (ADR-0002 FD-5 Decision 3). An empty airline list is never sent.
    return FlightQuery(
        date=date,
        from_airport=origin,
        to_airport=destination,
        max_stops=search.max_stops,
        airlines=list(search.airlines) if search.airlines else None,
        earliest_departure_hour=search.dep_hour_from if outbound else None,
        latest_departure_hour=search.dep_hour_to if outbound else None,
    )


def build_query(search: FlightSearch) -> Any:
    legs = [
        _leg(
            search,
            search.pair.depart.isoformat(),
            search.origin,
            search.destination,
            outbound=True,
        )
    ]
    if search.pair.return_date is not None:
        legs.append(
            _leg(
                search,
                search.pair.return_date.isoformat(),
                search.destination,
                search.origin,
                outbound=False,
            )
        )
    return create_query(
        flights=legs,
        seat=SEAT_BY_CABIN[search.cabin],  # type: ignore[arg-type]
        trip="round-trip" if search.pair.return_date is not None else "one-way",
        passengers=Passengers(adults=search.adults, children=search.children),
        language=LANGUAGE,
        currency=search.currency,
    )


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _string_field(number: int, value: bytes) -> bytes:
    return _varint(number << 3 | 2) + _varint(len(value)) + value


def selected_flight_bytes(refs: tuple[SegmentRef, ...]) -> bytes:
    """FlightData field 4, one per segment. fast_flights' proto has no such field; it was
    read from a browser URL (2026-11-04), so this is tied to its version like the rest."""
    return b"".join(
        _string_field(
            4,
            _string_field(1, ref.origin.encode())
            + _string_field(2, ref.depart_date.encode())
            + _string_field(3, ref.destination.encode())
            + _string_field(5, ref.code.encode())
            + _string_field(6, ref.number.encode()),
        )
        for ref in refs
    )


def build_return_query(search: FlightSearch, refs: tuple[SegmentRef, ...]) -> Any:
    """The same query with the outbound flight selected: Google then lists return flights."""
    query = build_query(search)
    query.flight_data[0].MergeFromString(selected_flight_bytes(refs))
    return query


def fetch_return_page(search: FlightSearch, refs: tuple[SegmentRef, ...]) -> str:
    html: str = fetch_flights_html(build_return_query(search, refs))
    return html


def ticket_mark_applies(search: FlightSearch) -> bool:
    """The separate-tickets mark was only verified for one adult in economy, round trip."""
    return (
        search.pair.return_date is not None
        and search.adults == 1
        and search.children == 0
        and search.cabin == "economy"
    )


class GoogleFlightsLinkBuilder:
    """``ports.BookingLinkBuilder``: exact Google Flights URL from the query's ``tfs``.

    Pure encoding through fast_flights' query builder; nothing is fetched. The URL is
    tied to ``VERIFIED_FAST_FLIGHTS_VERSION`` (golden test) and never stored.
    """

    def url(self, search: FlightSearch) -> str | None:
        params = build_query(search).params()
        return (
            BOOKING_BASE_URL
            + "?"
            + urlencode({"tfs": params["tfs"], "hl": params["hl"], "curr": params["curr"]})
        )


def fetch_live(search: FlightSearch) -> str:
    """Real network call through fast_flights' own fetcher (no integration, no proxy)."""
    html: str = fetch_flights_html(build_query(search))
    return html


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
        fetch_return: Callable[[FlightSearch, tuple[SegmentRef, ...]], str] = fetch_return_page,
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
        self._fetch_return = fetch_return
        self._clock = clock
        self._sleep = sleep
        self._runner = runner

    @property
    def name(self) -> str:
        return SOURCE_NAME

    @property
    def price_kind(self) -> PriceKind:
        return "live"

    @property
    def source_name(self) -> str:
        return SOURCE_NAME

    def return_leg(self, search: FlightSearch, quote: PriceQuote) -> ReturnLegResult:
        """One request, no retry and no cache; failures only hide the return flight.

        Picks the cheapest return flight whose total equals ``quote`` and whose marks match
        it, so the flight shown cannot contradict the labels on the price (FD-16 R4).
        """
        return_date = search.pair.return_date
        if return_date is None or not quote.segment_refs or quote.split_ticket is None:
            return ReturnLegResult("no_match")
        self._throttle.wait()
        fetched_at = self._clock()
        try:
            html = call_with_timeout(
                lambda: self._fetch_return(search, quote.segment_refs),
                self._timeout,
                self._runner,
            )
            page = parse_payload(extract_payload(html))
        except PayloadErrorStatus:
            return ReturnLegResult("no_embedded", 1)
        except PayloadFormatError:
            return ReturnLegResult("blocked", 1)
        except Exception as exc:  # any network or library failure while fetching
            log.warning("return leg lookup failed: %s", type(exc).__name__)
            return ReturnLegResult("error", 1)
        if page.no_results:
            return ReturnLegResult("no_embedded", 1)
        try:
            # A return flight's first segment leaves on the return date.
            options = quotes_from_records(
                page.records,
                source=SOURCE_NAME,
                price_kind="live",
                currency=quote.currency,
                depart_date=return_date,
                return_date=return_date,
                fetched_at=fetched_at,
            )
        except RecordFormatError:
            return ReturnLegResult("blocked", 1)
        matches = [
            option
            for option in options
            if option.amount_minor == quote.amount_minor
            and option.split_ticket is quote.split_ticket
            and option.overhead_bin_excluded is quote.overhead_bin_excluded
            and option.flight_numbers
        ]
        if not matches:
            return ReturnLegResult("no_match", 1)
        best = min(matches, key=quote_rank_key)
        leg = ReturnLeg(
            carrier=best.carrier,
            stops=best.stops,
            depart_time=best.depart_time,
            duration_minutes=best.duration_minutes,
            flight_numbers=best.flight_numbers,
            arrive_time=best.arrive_time,
            arrive_day_offset=best.arrive_day_offset,
            route_airports=best.route_airports,
        )
        return ReturnLegResult("ok", 1, leg)

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

        def result(
            status: QueryStatus,
            message: str | None,
            stats: ParseStats,
            quotes: tuple[PriceQuote, ...] = (),
            reason: str | None = None,
        ) -> SourceResult:
            return SourceResult(
                source=SOURCE_NAME,
                status=status,
                fetched_at=fetched_at,
                quotes=quotes,
                error=redact_truncate(message) if message else None,
                attempts=attempts,
                extra={"reason": reason} if reason else {},
                parse_stats=stats,
            )

        def error(message: str) -> SourceResult:
            return SourceResult(
                source=SOURCE_NAME,
                status="error",
                fetched_at=fetched_at,
                error=redact_truncate(message),
                attempts=attempts,
            )

        # Only the network call runs under the hard timeout; parsing happens below.
        try:
            html = call_with_timeout(lambda: self._fetch(query), self._timeout, self._runner)
        except WorkersExhaustedError as exc:
            return error(str(exc))
        except TimeoutError as exc:
            return error(f"timeout: {exc}")
        except Exception as exc:  # any library/network failure while fetching is an error
            return error(f"{type(exc).__name__}: {exc}")

        # Status table: ADR-0002 FD-3 Decision 2.
        try:
            page = parse_payload(extract_payload(html))
        except PayloadErrorStatus:
            return result("no_data", "no flights found (error status page)", NO_STATS)
        except PayloadFormatError as exc:
            return result("blocked", f"unparseable response: {exc}", NO_STATS)
        stats = page.stats
        if page.no_results:
            return result(
                "no_data",
                "no result section embedded in the page",
                stats,
                reason=NO_EMBEDDED_RESULTS,
            )
        if stats.priced == 0:
            if stats.malformed > 0:
                return result(
                    "blocked",
                    f"no priced itineraries; {stats.malformed} of {stats.itineraries}"
                    " have an unrecognised format",
                    stats,
                )
            if stats.itineraries == 0:
                return result("blocked", "empty itinerary list (blank or changed page)", stats)
            # all_unpriced: listed flights exist but none has a price. Not a failure.
            return result("no_data", None, stats)

        try:
            quotes = quotes_from_records(
                page.records,
                source=SOURCE_NAME,
                price_kind="live",
                currency=query.currency,
                depart_date=query.pair.depart,
                return_date=query.pair.return_date,
                fetched_at=fetched_at,
            )
        except RecordFormatError as exc:
            return result("blocked", f"unexpected result format: {exc}", stats)
        if not quotes:
            return result("blocked", "no priced itineraries after conversion", stats)
        if query.pair.return_date is None and any(q.split_ticket for q in quotes):
            log.warning("one-way result carries a separate-tickets mark; ignored")
        if not ticket_mark_applies(query):
            quotes = [replace(q, split_ticket=None) for q in quotes]
        return result("ok", None, stats, tuple(quotes))
