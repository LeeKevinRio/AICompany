"""Opt-in real-network smoke test. Deselected by default; run manually:

    uv run pytest -q -m live tests/test_live_smoke.py

Each test sends exactly one query to Google Flights through fast_flights (no retries).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from flight_deals.domain.models import DatePair, FlightSearch
from flight_deals.sources._support import Throttle, TTLCache
from flight_deals.sources.google_flights import GoogleFlightsSource


@pytest.mark.live
def test_google_flights_one_real_query() -> None:
    depart = (datetime.now(UTC) + timedelta(days=45)).date()
    source = GoogleFlightsSource(
        timeout_seconds=30.0,
        max_attempts=1,
        backoff_base_seconds=0.0,
        throttle=Throttle(0.0),
        cache=TTLCache(0.0),
    )
    result = source.search(
        FlightSearch(origin="TPE", destination="NRT", pair=DatePair(depart), max_stops=None)
    )
    print(
        f"status={result.status} attempts={result.attempts} quotes={len(result.quotes)} "
        f"error={result.error}"
    )
    assert result.status == "ok", result.error
    cheapest = min(result.quotes, key=lambda q: q.amount_minor)
    print(f"cheapest={cheapest.amount_minor} {cheapest.currency} carrier={cheapest.carrier}")
    assert cheapest.currency == "TWD" and cheapest.amount_minor > 0
    assert cheapest.source == "google_flights" and cheapest.price_kind == "live"


@pytest.mark.live
@pytest.mark.parametrize("city", ["TYO", "OSA"])
def test_google_flights_city_code_query(city: str) -> None:  # FD-2 FR-D3: city codes
    depart = (datetime.now(UTC) + timedelta(days=45)).date()
    source = GoogleFlightsSource(
        timeout_seconds=30.0,
        max_attempts=1,
        backoff_base_seconds=0.0,
        throttle=Throttle(2.0),
        cache=TTLCache(0.0),
    )
    result = source.search(
        FlightSearch(origin="TPE", destination=city, pair=DatePair(depart), max_stops=1)
    )
    print(f"{city}: status={result.status} quotes={len(result.quotes)} error={result.error}")
    assert result.status == "ok", result.error


@pytest.mark.live
@pytest.mark.parametrize("airline", ["BR", "IT", "7C"])  # full-service, LCC, digit code
def test_google_flights_airline_filter(airline: str) -> None:  # FD-5 C-41
    depart = (datetime.now(UTC) + timedelta(days=45)).date()
    destination = "ICN" if airline == "7C" else "NRT"
    source = GoogleFlightsSource(
        timeout_seconds=30.0,
        max_attempts=1,
        backoff_base_seconds=0.0,
        throttle=Throttle(2.0),
        cache=TTLCache(0.0),
    )
    search = replace(
        FlightSearch(origin="TPE", destination=destination, pair=DatePair(depart), max_stops=0),
        airlines=(airline,),
    )
    result = source.search(search)
    carriers = sorted({q.carrier or "?" for q in result.quotes})
    print(f"{airline}: status={result.status} quotes={len(result.quotes)} carriers={carriers}")
    assert result.status in ("ok", "no_data"), result.error
