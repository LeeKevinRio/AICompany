"""Adapter contract tests (C-4, C-6) using the recorded Google Flights fixture."""

from __future__ import annotations

import json
import threading
import time
from datetime import date
from typing import Any

import pytest
from fast_flights import FlightsNotFound
from fast_flights.model import (
    Airport,
    CarbonEmission,
    Flights,
    SimpleDatetime,
    SingleFlight,
)

from flight_deals.domain.models import DatePair, FlightSearch
from flight_deals.ports import SourceResult
from flight_deals.sources._support import Throttle, TTLCache, backoff_delay, call_with_timeout
from flight_deals.sources.fixture import FixtureSource
from flight_deals.sources.google_flights import GoogleFlightsSource, build_query
from tests.conftest import ROUNDTRIP_FIXTURE, FakeClock

SEARCH = FlightSearch(
    origin="TPE",
    destination="NRT",
    pair=DatePair(date(2026, 12, 10), date(2026, 12, 15)),
    max_stops=1,
)


def fixture_flights() -> list[Flights]:
    """Rebuild real fast_flights dataclasses from the recorded asdict() payload."""
    payload = json.loads(ROUNDTRIP_FIXTURE.read_text(encoding="utf-8"))
    flights: list[Flights] = []
    for record in payload["flights"]:
        segments = [
            SingleFlight(
                from_airport=Airport(**seg["from_airport"]),
                to_airport=Airport(**seg["to_airport"]),
                departure=SimpleDatetime(
                    date=tuple(seg["departure"]["date"]), time=tuple(seg["departure"]["time"])
                ),
                arrival=SimpleDatetime(
                    date=tuple(seg["arrival"]["date"]), time=tuple(seg["arrival"]["time"])
                ),
                duration=seg["duration"],
                plane_type=seg["plane_type"],
            )
            for seg in record["flights"]
        ]
        flights.append(
            Flights(
                type=record["type"],
                price=record["price"],
                airlines=record["airlines"],
                flights=segments,
                carbon=CarbonEmission(**record["carbon"]),
            )
        )
    return flights


class Recorder:
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, _search: FlightSearch) -> Any:
        self.calls += 1
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, BaseException):
            raise response
        return response


def make_source(
    fetch: Any, clock: FakeClock, *, attempts: int = 2, timeout: float = 5.0
) -> tuple[GoogleFlightsSource, list[float]]:
    sleeps: list[float] = []
    source = GoogleFlightsSource(
        timeout_seconds=timeout,
        max_attempts=attempts,
        backoff_base_seconds=2.0,
        throttle=Throttle(0.0, sleep=sleeps.append),
        cache=TTLCache(600.0),
        fetch=fetch,
        clock=clock,
        sleep=sleeps.append,
    )
    return source, sleeps


def assert_contract(result: SourceResult, source_name: str) -> None:
    assert result.status == "ok"
    assert result.quotes
    for quote in result.quotes:
        assert quote.source == source_name
        assert quote.price_kind == "live"
        assert isinstance(quote.amount_minor, int) and not isinstance(quote.amount_minor, bool)
        assert quote.amount_minor > 0
        assert quote.currency == "TWD"
        assert quote.as_of.tzinfo is not None and quote.fetched_at.tzinfo is not None
        assert quote.as_of_basis == "fetch_time"
        assert quote.depart_date == date(2026, 12, 10)
        assert quote.return_date == date(2026, 12, 15)


def test_google_flights_contract_on_recorded_fixture(clock: FakeClock) -> None:
    source, _ = make_source(Recorder(fixture_flights()), clock)
    result = source.search(SEARCH)
    assert_contract(result, "google_flights")
    cheapest = min(result.quotes, key=lambda q: q.amount_minor)
    assert cheapest.amount_minor == 1008800 and cheapest.carrier == "酷航"
    assert cheapest.stops == 0 and cheapest.duration_minutes == 185
    multi = [q for q in result.quotes if q.stops and q.stops > 0]
    assert multi, "fixture includes connecting itineraries"


def test_build_query_is_round_trip_with_two_legs_and_no_integration() -> None:
    query = build_query(SEARCH)
    assert query.get_trip_type() == "round-trip"
    assert len(query.flight_data) == 2
    assert query.currency == "TWD" and query.language == "zh-TW"


def test_flights_not_found_is_no_data(clock: FakeClock) -> None:
    source, _ = make_source(Recorder(FlightsNotFound("no flights found")), clock)
    result = source.search(SEARCH)
    assert result.status == "no_data" and not result.quotes


@pytest.mark.parametrize(
    "response",
    [[], IndexError("list index out of range"), AttributeError("'NoneType' has no 'text'")],
)
def test_blank_or_unparseable_is_blocked_not_no_data(clock: FakeClock, response: Any) -> None:
    fetch = Recorder(response)
    source, _ = make_source(fetch, clock)
    result = source.search(SEARCH)
    assert result.status == "blocked"
    assert not result.quotes
    assert fetch.calls == 1, "blocked responses are not hammered with retries"


def test_shape_change_in_records_is_blocked(clock: FakeClock) -> None:
    source, _ = make_source(Recorder([{"price": "12,000", "flights": []}]), clock)
    assert source.search(SEARCH).status == "blocked"


def test_network_error_retries_with_exponential_backoff(clock: FakeClock) -> None:
    fetch = Recorder(ConnectionError("reset"), ConnectionError("reset"), ConnectionError("reset"))
    source, sleeps = make_source(fetch, clock, attempts=3)
    result = source.search(SEARCH)
    assert result.status == "error" and result.attempts == 3 and fetch.calls == 3
    assert [s for s in sleeps if s > 0] == [2.0, 4.0]
    assert backoff_delay(2.0, 3) == 8.0


def test_error_then_success_recovers(clock: FakeClock) -> None:
    fetch = Recorder(ConnectionError("reset"), fixture_flights())
    source, _ = make_source(fetch, clock, attempts=2)
    result = source.search(SEARCH)
    assert result.status == "ok" and result.attempts == 2


def test_hard_timeout(clock: FakeClock) -> None:
    release = threading.Event()

    def slow(_search: FlightSearch) -> Any:
        release.wait(2)
        return fixture_flights()

    source, _ = make_source(slow, clock, attempts=1, timeout=0.05)
    started = time.monotonic()
    result = source.search(SEARCH)
    release.set()
    assert result.status == "error" and "timeout" in (result.error or "")
    assert time.monotonic() - started < 1.5


def test_ttl_cache_serves_repeat_queries_without_outbound_call(clock: FakeClock) -> None:
    fetch = Recorder(fixture_flights())
    source, _ = make_source(fetch, clock)
    first = source.search(SEARCH)
    second = source.search(SEARCH)
    assert fetch.calls == 1
    assert second.from_cache and second.attempts == 0 and second.quotes == first.quotes


def test_ttl_cache_expires() -> None:
    now = [0.0]
    cache: TTLCache[str, int] = TTLCache(10.0, clock=lambda: now[0])
    cache.put("a", 1)
    assert cache.get("a") == 1
    now[0] = 11.0
    assert cache.get("a") is None


def test_throttle_enforces_min_interval_with_jitter() -> None:
    now = [100.0]
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    throttle = Throttle(1.5, 1.0, sleep=fake_sleep, clock=lambda: now[0], rng=lambda: 0.5)
    throttle.wait()
    throttle.wait()
    assert sleeps == [2.0]


def test_call_with_timeout_returns_value() -> None:
    assert call_with_timeout(lambda: 42, 1.0) == 42


def test_fixture_source_contract(clock: FakeClock) -> None:
    source = FixtureSource(ROUNDTRIP_FIXTURE, clock=clock)
    result = source.search(SEARCH)
    assert_contract(result, "fixture")


def test_fixture_source_forced_blocked(clock: FakeClock) -> None:
    source = FixtureSource(ROUNDTRIP_FIXTURE, clock=clock, forced_status="blocked")
    result = source.search(SEARCH)
    assert result.status == "blocked" and not result.quotes
