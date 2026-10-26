"""Opt-in real-network smoke test. Deselected by default; run manually:

    uv run pytest -q -m live tests/test_live_smoke.py

It sends exactly one query to Google Flights through fast_flights (no retries).
"""

from __future__ import annotations

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
