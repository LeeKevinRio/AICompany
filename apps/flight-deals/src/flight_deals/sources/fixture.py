"""Offline fixture source for tests and development. Refused in production config.

It replays a recorded Google Flights response for whatever date pair is requested and
labels every quote with ``source="fixture"`` so it can never pass for real data.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from flight_deals.domain.models import FlightSearch, PriceKind, QueryStatus
from flight_deals.domain.timeutil import utc_now
from flight_deals.ports import Clock, SourceResult
from flight_deals.sources._records import RecordFormatError, quotes_from_records
from flight_deals.sources._support import Throttle, TTLCache

SOURCE_NAME = "fixture"


def load_fixture_records(path: Path) -> list[Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    flights = payload.get("flights") if isinstance(payload, dict) else None
    if not isinstance(flights, list):
        raise RecordFormatError("fixture has no 'flights' list")
    return flights


class FixtureSource:
    def __init__(
        self,
        path: Path,
        *,
        clock: Clock = utc_now,
        forced_status: QueryStatus | None = None,
        throttle: Throttle | None = None,
        cache: TTLCache[tuple[object, ...], SourceResult] | None = None,
    ) -> None:
        self._records = load_fixture_records(path)
        self._clock = clock
        self._forced_status = forced_status
        self._throttle = throttle or Throttle(0.0)
        self._cache = cache
        self.calls = 0

    @property
    def name(self) -> str:
        return SOURCE_NAME

    @property
    def price_kind(self) -> PriceKind:
        return "live"

    def search(self, query: FlightSearch) -> SourceResult:
        key = query.cache_key()
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                return replace(cached, attempts=0, from_cache=True)
        self._throttle.wait()
        self.calls += 1
        fetched_at = self._clock()
        if self._forced_status is not None and self._forced_status != "ok":
            return SourceResult(
                source=SOURCE_NAME,
                status=self._forced_status,
                fetched_at=fetched_at,
                error=f"fixture forced status {self._forced_status}",
            )
        quotes = quotes_from_records(
            self._records,
            source=SOURCE_NAME,
            price_kind="live",
            currency=query.currency,
            depart_date=query.pair.depart,
            return_date=query.pair.return_date,
            fetched_at=fetched_at,
        )
        status: QueryStatus = "ok" if quotes else "blocked"
        result = SourceResult(
            source=SOURCE_NAME,
            status=status,
            fetched_at=fetched_at,
            quotes=tuple(quotes),
            error=None if quotes else "fixture contains no priced itineraries",
        )
        if self._cache is not None and status == "ok":
            self._cache.put(key, result)
        return result
