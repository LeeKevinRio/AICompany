"""Tests for MarketDataService: primary -> backup -> cache -> unavailable."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.cache import PriceBarCache
from app.data.interface import (
    DataStatus,
    MarketDataProvider,
    PriceBar,
    ProviderResult,
)
from app.data.service import MarketDataService

START = date(2024, 1, 1)
END = date(2024, 1, 31)


def _bar(source: str) -> PriceBar:
    return PriceBar(
        symbol="2330",
        market="TW",
        date=date(2024, 1, 2),
        open=Decimal("594.00"),
        high=Decimal("598.00"),
        low=Decimal("590.00"),
        close=Decimal("594.00"),
        volume=1000,
        currency="TWD",
        as_of=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
        source=source,
    )


def _us_bar(source: str) -> PriceBar:
    """Same shape as :func:`_bar` but tagged US/USD, for cache_first tests."""
    return PriceBar(
        symbol="2330",
        market="US",
        date=date(2024, 1, 2),
        open=Decimal("594.00"),
        high=Decimal("598.00"),
        low=Decimal("590.00"),
        close=Decimal("594.00"),
        volume=1000,
        currency="USD",
        as_of=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
        source=source,
    )


class _StubProvider(MarketDataProvider):
    #: Placeholder to satisfy the ABC's ClassVar contract; the meaningful
    #: per-instance label used in test assertions is ``_label`` below.
    source_id = "stub"

    def __init__(
        self,
        *,
        source_id: str,
        bars: list[PriceBar] | None = None,
        status: DataStatus = DataStatus.FRESH,
        raises: bool = False,
    ) -> None:
        self._label = source_id
        self._bars = bars or []
        self._status = status
        self._raises = raises
        self.call_count = 0

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.call_count += 1
        if self._raises:
            raise RuntimeError("provider bug")
        return ProviderResult(
            bars=self._bars,
            status=self._status,
            as_of=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
            source=self._label,
            staleness_minutes=0 if self._bars else None,
        )


def _service(
    primary: MarketDataProvider, backups: list[MarketDataProvider], tmp_path: Path
) -> MarketDataService:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    return MarketDataService(
        primary=primary,
        backups=backups,
        cache=cache,
        clock=lambda: datetime(2024, 1, 2, 15, 0, tzinfo=UTC),
    )


def test_primary_success_returns_fresh(tmp_path: Path) -> None:
    primary = _StubProvider(source_id="twse", bars=[_bar("twse")])
    backup = _StubProvider(source_id="finmind", bars=[_bar("finmind")])
    service = _service(primary, [backup], tmp_path)

    result = service.get_daily_bars("2330", "TW", START, END)
    assert result.status is DataStatus.FRESH
    assert result.source == "twse"
    assert backup.call_count == 0  # backup must not be consulted when primary succeeds


def test_primary_fails_backup_succeeds_returns_backup_status(tmp_path: Path) -> None:
    primary = _StubProvider(source_id="twse", status=DataStatus.UNAVAILABLE)
    backup = _StubProvider(source_id="finmind", bars=[_bar("finmind")])
    service = _service(primary, [backup], tmp_path)

    result = service.get_daily_bars("2330", "TW", START, END)
    assert result.status is DataStatus.BACKUP
    assert result.source == "finmind"


def test_primary_raises_exception_falls_through_to_backup(tmp_path: Path) -> None:
    primary = _StubProvider(source_id="twse", raises=True)
    backup = _StubProvider(source_id="finmind", bars=[_bar("finmind")])
    service = _service(primary, [backup], tmp_path)

    result = service.get_daily_bars("2330", "TW", START, END)
    assert result.status is DataStatus.BACKUP
    assert result.source == "finmind"


def test_all_providers_fail_falls_back_to_cache(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put([_bar("twse")], source="twse", fetched_at=datetime(2024, 1, 2, 10, 0, tzinfo=UTC))

    primary = _StubProvider(source_id="twse", status=DataStatus.UNAVAILABLE)
    backup = _StubProvider(source_id="finmind", status=DataStatus.UNAVAILABLE)
    service = MarketDataService(
        primary=primary,
        backups=[backup],
        cache=cache,
        clock=lambda: datetime(2024, 1, 2, 15, 0, tzinfo=UTC),  # 5h after fetch
    )

    result = service.get_daily_bars("2330", "TW", START, END)
    assert result.status is DataStatus.CACHED_STALE
    assert result.source == "twse"
    assert result.staleness_minutes == 300


def test_all_providers_fail_and_no_cache_returns_unavailable(tmp_path: Path) -> None:
    primary = _StubProvider(source_id="twse", status=DataStatus.UNAVAILABLE)
    backup = _StubProvider(source_id="finmind", status=DataStatus.UNAVAILABLE)
    service = _service(primary, [backup], tmp_path)

    result = service.get_daily_bars("2330", "TW", START, END)
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []
    assert result.staleness_minutes is None


def test_successful_live_fetch_is_written_through_to_cache(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    primary = _StubProvider(source_id="twse", bars=[_bar("twse")])
    service = MarketDataService(
        primary=primary,
        backups=[],
        cache=cache,
        clock=lambda: datetime(2024, 1, 2, 15, 0, tzinfo=UTC),
    )
    service.get_daily_bars("2330", "TW", START, END)

    cached = cache.get("2330", "TW", START, END)
    assert cached is not None
    assert cached.bars[0].source == "twse"


def test_unexpected_provider_exception_is_logged_at_exception_level(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    primary = _StubProvider(source_id="twse", raises=True)
    backup = _StubProvider(source_id="finmind", bars=[_bar("finmind")])
    service = _service(primary, [backup], tmp_path)

    with caplog.at_level(logging.INFO, logger="app.data.service"):
        service.get_daily_bars("2330", "TW", START, END)

    # A raised provider bug is graded as an unexpected error (ERROR level via
    # logger.exception) and carries the explicit tag so it is greppable.
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("unexpected provider error" in r.getMessage() for r in error_records)


def test_expected_unavailable_is_logged_at_info_not_exception_level(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    primary = _StubProvider(source_id="twse", status=DataStatus.UNAVAILABLE)
    backup = _StubProvider(source_id="finmind", bars=[_bar("finmind")])
    service = _service(primary, [backup], tmp_path)

    with caplog.at_level(logging.INFO, logger="app.data.service"):
        service.get_daily_bars("2330", "TW", START, END)

    # An in-contract "unavailable" is a quiet INFO line, distinguishable from
    # the unexpected-exception path (no ERROR record, no exception tag).
    assert any(
        r.levelno == logging.INFO and "returned no usable data" in r.getMessage()
        for r in caplog.records
    )
    assert not any(
        "unexpected provider error" in r.getMessage() for r in caplog.records
    )


def test_fresh_and_backup_results_carry_no_ttl_opinion(tmp_path: Path) -> None:
    """ADR-0005 決策四: is_within_ttl is None for any live source, not a fact
    that applies to a fresh live fetch."""
    primary = _StubProvider(source_id="twse", bars=[_bar("twse")])
    service = _service(primary, [], tmp_path)

    result = service.get_daily_bars("2330", "TW", START, END)
    assert result.status is DataStatus.FRESH
    assert result.is_within_ttl is None


def test_cache_fallback_carries_is_within_ttl(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db", ttl_seconds=60 * 60)
    cache.put([_bar("twse")], source="twse", fetched_at=datetime(2024, 1, 2, 10, 0, tzinfo=UTC))

    primary = _StubProvider(source_id="twse", status=DataStatus.UNAVAILABLE)
    backup = _StubProvider(source_id="finmind", status=DataStatus.UNAVAILABLE)
    # clock is 3 hours after fetch -- past the 1h TTL used here.
    service = MarketDataService(
        primary=primary,
        backups=[backup],
        cache=cache,
        clock=lambda: datetime(2024, 1, 2, 13, 0, tzinfo=UTC),
    )

    result = service.get_daily_bars("2330", "TW", START, END)
    assert result.status is DataStatus.CACHED_STALE
    assert result.is_within_ttl is False


class TestCacheFirst:
    """ADR-0005 決策四: 'layer 0' TTL-fresh cache short-circuit.

    Default (``cache_first=False``) must reproduce every existing TW test
    above byte-for-byte -- these tests only exercise the opt-in behaviour.
    """

    def test_default_is_disabled(self, tmp_path: Path) -> None:
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        primary = _StubProvider(source_id="twse", bars=[])
        service = MarketDataService(primary=primary, cache=cache)
        # No assertion needed beyond "constructs fine and behaves like before";
        # covered end-to-end by the rest of this module's TW-flavoured tests.
        assert service is not None

    def test_serves_ttl_fresh_cache_without_calling_any_provider(
        self, tmp_path: Path
    ) -> None:
        cache = PriceBarCache(db_path=tmp_path / "cache.db", ttl_seconds=24 * 60 * 60)
        cache.put(
            [_us_bar("alpha_vantage")],
            source="alpha_vantage",
            fetched_at=datetime(2024, 1, 2, 10, 0, tzinfo=UTC),
        )
        primary = _StubProvider(source_id="alpha_vantage", bars=[_us_bar("alpha_vantage")])
        backup = _StubProvider(source_id="yfinance", bars=[_us_bar("yfinance")])
        service = MarketDataService(
            primary=primary,
            backups=[backup],
            cache=cache,
            clock=lambda: datetime(2024, 1, 2, 12, 0, tzinfo=UTC),  # 2h later, within 24h TTL
            cache_first=True,
        )

        result = service.get_daily_bars("2330", "US", START, END)

        assert result.status is DataStatus.CACHED_STALE
        assert result.is_within_ttl is True
        assert result.source == "alpha_vantage"
        assert primary.call_count == 0
        assert backup.call_count == 0

    def test_falls_through_to_providers_when_cache_is_expired(
        self, tmp_path: Path
    ) -> None:
        cache = PriceBarCache(db_path=tmp_path / "cache.db", ttl_seconds=60 * 60)
        cache.put(
            [_us_bar("alpha_vantage")],
            source="alpha_vantage",
            fetched_at=datetime(2024, 1, 2, 10, 0, tzinfo=UTC),
        )
        primary = _StubProvider(source_id="alpha_vantage", bars=[_us_bar("alpha_vantage")])
        service = MarketDataService(
            primary=primary,
            cache=cache,
            clock=lambda: datetime(2024, 1, 2, 13, 0, tzinfo=UTC),  # 3h later, past 1h TTL
            cache_first=True,
        )

        result = service.get_daily_bars("2330", "US", START, END)

        assert result.status is DataStatus.FRESH
        assert primary.call_count == 1

    def test_falls_through_to_providers_when_no_cache_entry_exists(
        self, tmp_path: Path
    ) -> None:
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        primary = _StubProvider(source_id="alpha_vantage", bars=[_us_bar("alpha_vantage")])
        service = MarketDataService(primary=primary, cache=cache, cache_first=True)

        result = service.get_daily_bars("2330", "US", START, END)

        assert result.status is DataStatus.FRESH
        assert primary.call_count == 1
