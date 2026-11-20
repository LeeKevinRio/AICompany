"""Offline fixtures for the forced index refresh (ADR-0030 supplement 10 point 2).

A fake live index source that stamps each bar with the time of the request (as
the yfinance adapter does), a settable clock, bar and cache seeders and a dump
of the cache's three tables for the equivalence tests. Every cache is a
``tmp_path`` file; nothing reaches the network.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import ClassVar

from app.data.cache import PriceBarCache
from app.data.interface import DataStatus, Market, MarketDataProvider, PriceBar, ProviderResult

SYMBOL = "^TWII"
MARKET: Market = "TW"
#: Wednesday 2026-11-18, the session T of most scenarios.
T = date(2026, 11, 18)
#: 22:10 Taipei on T (the first scheduled run).
AT_22_10 = datetime(2026, 11, 18, 14, 10, tzinfo=UTC)
#: The recorder's range length (FETCH_CALENDAR_DAYS + FETCH_SLACK_DAYS).
LOOKBACK_DAYS = 531
START = T - timedelta(days=LOOKBACK_DAYS)
END = T
#: The three tables the cache keeps.
CACHE_TABLES = ("price_bars_cache", "price_bars_fetch_log", "price_bars_attempt_log")


class Clock:
    """A settable clock; ``tick`` moves it forward."""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def tick(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)


def weekdays(first: date, last: date) -> list[date]:
    days: list[date] = []
    day = first
    while day <= last:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def index_bar(
    day: date,
    *,
    as_of: datetime,
    currency: str = "TWD",
    source: str = "yfinance",
    close: str = "17000",
) -> PriceBar:
    return PriceBar(
        symbol=SYMBOL,
        market=MARKET,
        date=day,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=0,
        currency=currency,
        as_of=as_of,
        source=source,
    )


class FakeIndexSource(MarketDataProvider):
    """A live index source: answers the days it holds, each bar stamped with the request time."""

    source_id: ClassVar[str] = "yfinance"

    def __init__(
        self,
        clock: Callable[[], datetime],
        days: Iterable[date],
        *,
        currency: str = "TWD",
        complete: bool = True,
        unavailable: bool = False,
        raises: bool = False,
        close: str = "17000",
        source: str = "yfinance",
        before: Callable[[], None] = lambda: None,
    ) -> None:
        self._clock = clock
        self._days = sorted(days)
        self._currency = currency
        self._complete = complete
        self._unavailable = unavailable
        self._raises = raises
        self._close = close
        self._source = source
        self._before = before
        self.asked: list[tuple[str, date, date]] = []

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.asked.append((symbol, start, end))
        requested = self._clock()
        self._before()
        if self._raises:
            raise RuntimeError("adapter bug")
        bars = [
            index_bar(
                day,
                as_of=requested,
                currency=self._currency,
                source=self._source,
                close=self._close,
            )
            for day in self._days
            if start <= day <= end
        ]
        if self._unavailable or not bars:
            return ProviderResult(
                bars=[],
                status=DataStatus.UNAVAILABLE,
                as_of=requested,
                source="none",
                staleness_minutes=None,
                reason="yfinance 連線逾時或發生錯誤，暫不可用。",
            )
        return ProviderResult(
            bars=bars,
            status=DataStatus.BACKUP,
            as_of=requested,
            source=self._source,
            staleness_minutes=0,
            complete=self._complete,
        )


def seed(
    cache: PriceBarCache,
    days: Iterable[date],
    *,
    at: datetime,
    currency: str = "TWD",
    close: str = "16000",
    covered: tuple[date, date] | None = None,
    attempted: datetime | None = None,
) -> None:
    """Write cached bars stamped ``at``; optionally a coverage row and an attempt row."""
    bars = [index_bar(day, as_of=at, currency=currency, close=close) for day in days]
    cache.put(bars, source="yfinance", fetched_at=at)
    if covered is not None:
        cache.record_fetch(SYMBOL, MARKET, start=covered[0], end=covered[1], fetched_at=at)
    if attempted is not None:
        cache.record_attempt(SYMBOL, MARKET, at=attempted)


def dump_tables(db_path: Path) -> dict[str, list[tuple[object, ...]]]:
    """Every row of the cache's three tables, ordered, every column."""
    with closing(sqlite3.connect(db_path)) as conn:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3").fetchall()
            for table in CACHE_TABLES
        }
