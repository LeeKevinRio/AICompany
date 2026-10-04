"""Pinned reproductions for ADR-0019 (proposed): daily-bar coverage and fetch time.

ADR-0019 (日線 coverage 判定與取得時間單一基準, partially superseding ADR-0009
D-3 / D-5) is not yet approved, so the fix has not started. These are its two
mandatory regression tests, written against the behaviour the ADR requires and
marked ``xfail(strict=True)`` so the suite stays green while the bugs stay
pinned:

* ``T-1`` -- coverage hole: a disjoint historical fetch replaces the coverage
  while the newer rows stay cached; layer 0 checks only ``covered_start`` and
  serves a series with a multi-year hole as "local cache, holds the latest
  session" (ADR-0019 D-1).
* ``T-4`` -- P4 overclaimed freshness: an overlapping historical fetch widens
  the coverage and moves ``last_fetched_at`` forward although the latest bars
  were not re-fetched, so the badge reports minutes since the historical fetch
  instead of since the tail was last obtained (ADR-0019 D-2).

Removing the xfail markers: only after CEO approves ADR-0019 and the D-1
(``coverage_reaches`` used by all three ``judge()`` consumers) and D-2
(``tail_fetched_at`` column) changes land. ``strict=True`` turns an unexpected
pass into a failure, so the marker cannot silently outlive the fix: delete it
in the same change that makes the test pass, and in T-4 add the
``tail_fetched_at == T0`` assertion once the field exists.

Everything here is offline: a fake provider, a fake clock and a ``tmp_path``
database; nothing touches ``backend/data/*.db``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.cache import PriceBarCache
from app.data.interface import DataStatus, MarketDataProvider, PriceBar, ProviderResult
from app.data.service import MarketDataService

SYMBOL = "2330"


class _Clock:
    """A settable clock; the service reads it, the test moves it."""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


def _weekday_bars(start: date, end: date, *, as_of: datetime, source: str) -> list[PriceBar]:
    """One bar per weekday in ``[start, end]`` -- the grid the gap check is measured on."""
    bars: list[PriceBar] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            bars.append(
                PriceBar(
                    symbol=SYMBOL,
                    market="TW",
                    date=day,
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100"),
                    volume=1000,
                    currency="TWD",
                    as_of=as_of,
                    source=source,
                )
            )
        day += timedelta(days=1)
    return bars


class _WeekdayProvider(MarketDataProvider):
    """Answers any range in full with weekday bars and records what it was asked."""

    source_id = "fake_twse"

    def __init__(self, clock: _Clock) -> None:
        self._clock = clock
        self.calls: list[tuple[date, date]] = []

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        now = self._clock()
        self.calls.append((start, end))
        return ProviderResult(
            bars=_weekday_bars(start, end, as_of=now, source=self.source_id),
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
            staleness_minutes=0,
            complete=True,
        )


def _max_gap_days(bars: list[PriceBar]) -> int:
    dates = sorted(bar.date for bar in bars)
    return max(((b - a).days for a, b in zip(dates, dates[1:], strict=False)), default=0)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "ADR-0019 pending: T-1 coverage hole -- layer 0 checks only covered_start, "
        "so a disjoint historical record_fetch makes a holed series look current; "
        "fixed by D-1 coverage_reaches (covered_end >= expected)"
    ),
)
def test_t1_a_disjoint_historical_fetch_does_not_let_layer_zero_serve_a_holed_series(
    tmp_path: Path,
) -> None:
    """ADR-0019 T-1 (dev-lead L-10c reproduction)."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    # Precondition: rows for 2024-04..2026-09-30 and the matching coverage.
    recent_at = datetime(2026, 9, 30, 8, 0, tzinfo=UTC)  # Wed 16:00 Taipei
    cache.put(
        _weekday_bars(date(2024, 4, 1), date(2026, 9, 30), as_of=recent_at, source="fake_twse"),
        source="fake_twse",
        fetched_at=recent_at,
    )
    cache.record_fetch(
        SYMBOL, "TW", start=date(2024, 4, 1), end=date(2026, 9, 30), fetched_at=recent_at
    )
    cache.record_attempt(SYMBOL, "TW", at=recent_at)
    # A backtest of 2020-01-02..2022-12-30: disjoint, so it replaces the coverage
    # while the 2024..2026 rows stay cached.
    history_at = datetime(2026, 10, 1, 7, 0, tzinfo=UTC)
    cache.put(
        _weekday_bars(date(2020, 1, 2), date(2022, 12, 30), as_of=history_at, source="fake_twse"),
        source="fake_twse",
        fetched_at=history_at,
    )
    cache.record_fetch(
        SYMBOL, "TW", start=date(2020, 1, 2), end=date(2022, 12, 30), fetched_at=history_at
    )
    cache.record_attempt(SYMBOL, "TW", at=history_at)

    clock = _Clock(datetime(2026, 10, 1, 8, 0, tzinfo=UTC))  # Thu 16:00 Taipei
    provider = _WeekdayProvider(clock)
    service = MarketDataService(primary=provider, cache=cache, clock=clock, cache_first=True)

    result = service.get_daily_bars(SYMBOL, "TW", date(2022, 6, 1), date(2026, 9, 30))

    gap = _max_gap_days(result.bars)
    coverage = cache.fetch_coverage(SYMBOL, "TW")
    observed = (
        f"calls={provider.calls} status={result.status.value} "
        f"is_within_ttl={result.is_within_ttl} bars={len(result.bars)} "
        f"max_gap_days={gap} coverage={coverage}"
    )
    assert provider.calls, observed
    assert provider.calls[0][0] == date(2022, 6, 1), observed
    assert not (result.status is DataStatus.CACHED_STALE and result.is_within_ttl), observed
    assert gap <= 3, observed
    assert coverage is not None, observed
    assert (coverage.covered_start, coverage.covered_end) == (
        date(2020, 1, 2),
        date(2026, 9, 30),
    ), observed


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "ADR-0019 pending: T-4 P4 overclaimed freshness -- an overlapping historical "
        "fetch moves last_fetched_at, which is also the staleness basis; fixed by D-2 "
        "tail_fetched_at (field not yet present, its == T0 assertion waits for D-2)"
    ),
)
def test_t4_an_overlapping_historical_fetch_does_not_refresh_the_tail_fetch_time(
    tmp_path: Path,
) -> None:
    """ADR-0019 T-4 (dev-lead L-10c S2)."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    t0 = datetime(2026, 9, 30, 7, 30, tzinfo=UTC)  # Wed 15:30 Taipei, after the cutoff
    clock = _Clock(t0)
    provider = _WeekdayProvider(clock)
    service = MarketDataService(primary=provider, cache=cache, clock=clock, cache_first=True)
    page_start, page_end = date(2025, 4, 1), date(2026, 9, 30)

    # T0: the stock page fetches [A, latest] live -- the tail is obtained now.
    first = service.get_daily_bars(SYMBOL, "TW", page_start, page_end)
    assert first.status is DataStatus.FRESH

    # T0+180: a backtest over an overlapping historical range widens the coverage
    # but does not re-fetch the latest bars.
    clock.at = t0 + timedelta(minutes=180)
    service.get_daily_bars(SYMBOL, "TW", date(2023, 1, 2), date(2025, 6, 30))
    assert len(provider.calls) == 2

    # T0+185: the stock page again.
    clock.at = t0 + timedelta(minutes=185)
    result = service.get_daily_bars(SYMBOL, "TW", page_start, page_end)

    coverage = cache.fetch_coverage(SYMBOL, "TW")
    observed = (
        f"calls={provider.calls} status={result.status.value} "
        f"staleness_minutes={result.staleness_minutes} as_of={result.as_of.isoformat()} "
        f"coverage={coverage}"
    )
    assert result.status is DataStatus.CACHED_STALE, observed
    assert result.staleness_minutes == 185, observed
    assert result.as_of == t0, observed
    assert coverage is not None, observed
    assert coverage.last_fetched_at == t0 + timedelta(minutes=180), observed
    # Once ADR-0019 D-2 lands: assert coverage.tail_fetched_at == t0
