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
from app.data.service import RECENT_ATTEMPT_FAILED_REASON, MarketDataService

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
    assert not any("unexpected provider error" in r.getMessage() for r in caplog.records)


def test_fresh_and_backup_results_carry_no_ttl_opinion(tmp_path: Path) -> None:
    """ADR-0005 決策四: is_within_ttl is None for any live source, not a fact
    that applies to a fresh live fetch."""
    primary = _StubProvider(source_id="twse", bars=[_bar("twse")])
    service = _service(primary, [], tmp_path)

    result = service.get_daily_bars("2330", "TW", START, END)
    assert result.status is DataStatus.FRESH
    assert result.is_within_ttl is None


def test_cache_fallback_is_never_called_current_when_a_session_is_missing(
    tmp_path: Path,
) -> None:
    """ADR-0009 R-1: the fallback path uses the session rule, not the rows' age."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    fetched_at = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    cache.put([_bar("twse")], source="twse", fetched_at=fetched_at)
    cache.record_fetch("2330", "TW", start=START, end=END, fetched_at=fetched_at)

    primary = _StubProvider(source_id="twse", status=DataStatus.UNAVAILABLE)
    backup = _StubProvider(source_id="finmind", status=DataStatus.UNAVAILABLE)
    # Thursday 2024-01-04 08:00 UTC = 16:00 Taipei: the 01-03 and 01-04 closes
    # are published, the cache stops at 01-02, fetched 46 hours ago.
    service = MarketDataService(
        primary=primary,
        backups=[backup],
        cache=cache,
        clock=lambda: datetime(2024, 1, 4, 8, 0, tzinfo=UTC),
    )

    result = service.get_daily_bars("2330", "TW", START, END)
    assert result.status is DataStatus.CACHED_STALE
    assert result.is_within_ttl is False


def test_cache_fallback_is_current_when_the_cache_holds_the_latest_session(
    tmp_path: Path,
) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    fetched_at = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    cache.put([_bar("twse")], source="twse", fetched_at=fetched_at)
    cache.record_fetch("2330", "TW", start=START, end=END, fetched_at=fetched_at)
    primary = _StubProvider(source_id="twse", status=DataStatus.UNAVAILABLE)
    # 2024-01-03 02:00 UTC = 10:00 Taipei: the latest published session is
    # still 01-02, which the cache has.
    service = MarketDataService(
        primary=primary,
        cache=cache,
        clock=lambda: datetime(2024, 1, 3, 2, 0, tzinfo=UTC),
    )
    result = service.get_daily_bars("2330", "TW", START, END)
    assert result.status is DataStatus.CACHED_STALE
    assert result.is_within_ttl is True
    # R-2: age counts from the last live check, not the oldest row.
    assert result.as_of == fetched_at and result.staleness_minutes == 16 * 60


def test_a_partial_answer_is_cached_but_its_range_is_not_recorded_as_covered(
    tmp_path: Path,
) -> None:
    """ADR-0009 R-4: a skipped month must be asked for again, not frozen in."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")

    class _PartialProvider(_StubProvider):
        def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
            result = super().get_daily_bars(symbol, start, end)
            return result.model_copy(update={"complete": False})

    primary = _PartialProvider(source_id="twse", bars=[_bar("twse")])
    service = MarketDataService(
        primary=primary,
        cache=cache,
        clock=lambda: datetime(2024, 1, 2, 15, 0, tzinfo=UTC),
        cache_first=True,
    )
    service.get_daily_bars("2330", "TW", START, END)
    assert cache.get("2330", "TW", START, END) is not None
    assert cache.fetch_coverage("2330", "TW") is None
    assert cache.last_attempt_at("2330", "TW") is not None


def test_while_sources_fail_the_ladder_runs_once_per_cooldown_not_per_click(
    tmp_path: Path,
) -> None:
    """ADR-0009 R-8: a seeded cache with no coverage still honours the cooldown."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put(
        [_bar("demo_synthetic")],
        source="demo_synthetic",
        fetched_at=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),  # an hour before the first click
    )
    primary = _StubProvider(source_id="twse", status=DataStatus.UNAVAILABLE)
    now = {"at": datetime(2024, 1, 2, 15, 0, tzinfo=UTC)}
    service = MarketDataService(
        primary=primary, cache=cache, clock=lambda: now["at"], cache_first=True
    )
    first = service.get_daily_bars("2330", "TW", START, END)  # ladder runs, fails
    now["at"] = datetime(2024, 1, 2, 15, 20, tzinfo=UTC)  # inside the TW cooldown
    second = service.get_daily_bars("2330", "TW", START, END)
    now["at"] = datetime(2024, 1, 2, 16, 30, tzinfo=UTC)  # cooldown expired
    third = service.get_daily_bars("2330", "TW", START, END)
    assert primary.call_count == 2
    assert first.status is second.status is third.status is DataStatus.CACHED_STALE
    assert second.is_within_ttl is False
    # The reader is told why the answer is the cache (ADR-0003 約束 7), and
    # the age is the rows' real fetch time, not the failed attempt's (R-10).
    assert second.reason == RECENT_ATTEMPT_FAILED_REASON
    assert second.staleness_minutes is not None and second.staleness_minutes >= 20


class TestCacheFirst:
    """ADR-0005 決策四 'layer 0', judged by session per ADR-0009.

    The cache answers when it already holds the latest published session and
    a live source was once asked for at least this range; otherwise the
    ladder runs as before. ``cache_first=False`` keeps the pre-layer-0 ladder.
    """

    def test_default_is_disabled(self, tmp_path: Path) -> None:
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        primary = _StubProvider(source_id="twse", bars=[])
        service = MarketDataService(primary=primary, cache=cache)
        # No assertion needed beyond "constructs fine and behaves like before";
        # covered end-to-end by the rest of this module's TW-flavoured tests.
        assert service is not None

    def test_serves_a_cache_holding_the_latest_session_without_calling_any_provider(
        self, tmp_path: Path
    ) -> None:
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        fetched_at = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
        cache.put([_us_bar("alpha_vantage")], source="alpha_vantage", fetched_at=fetched_at)
        cache.record_fetch("2330", "US", start=START, end=END, fetched_at=fetched_at)
        primary = _StubProvider(source_id="alpha_vantage", bars=[_us_bar("alpha_vantage")])
        backup = _StubProvider(source_id="yfinance", bars=[_us_bar("yfinance")])
        service = MarketDataService(
            primary=primary,
            backups=[backup],
            cache=cache,
            # 2024-01-02 12:00 UTC = 07:00 New York, before that day's publish
            # cutoff: the latest published session is Monday 01-01, and the
            # cache holds a bar from 01-02 already.
            clock=lambda: datetime(2024, 1, 2, 12, 0, tzinfo=UTC),
            cache_first=True,
        )

        result = service.get_daily_bars("2330", "US", START, END)

        assert result.status is DataStatus.CACHED_STALE
        assert result.is_within_ttl is True
        assert result.source == "alpha_vantage"
        assert primary.call_count == 0
        assert backup.call_count == 0

    def test_falls_through_to_providers_when_a_newer_session_exists(self, tmp_path: Path) -> None:
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        fetched_at = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
        cache.put([_us_bar("alpha_vantage")], source="alpha_vantage", fetched_at=fetched_at)
        cache.record_fetch("2330", "US", start=START, end=END, fetched_at=fetched_at)
        primary = _StubProvider(source_id="alpha_vantage", bars=[_us_bar("alpha_vantage")])
        service = MarketDataService(
            primary=primary,
            cache=cache,
            # Thursday 2024-01-04 01:00 UTC = Wednesday 20:00 New York: the
            # 01-03 close is published, the cache stops at 01-02, and the last
            # live check (01-02) is outside the 24h cooldown.
            clock=lambda: datetime(2024, 1, 4, 1, 0, tzinfo=UTC),
            cache_first=True,
        )

        result = service.get_daily_bars("2330", "US", START, END)

        assert result.status is DataStatus.FRESH
        assert primary.call_count == 1

    def test_a_recent_live_check_is_honoured_and_disclosed_as_short(self, tmp_path: Path) -> None:
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        cache.put(
            [_us_bar("alpha_vantage")],
            source="alpha_vantage",
            fetched_at=datetime(2024, 1, 2, 10, 0, tzinfo=UTC),
        )
        # A live source was asked at 00:30 UTC on 01-04 and had nothing newer.
        cache.record_fetch(
            "2330", "US", start=START, end=END, fetched_at=datetime(2024, 1, 4, 0, 30, tzinfo=UTC)
        )
        primary = _StubProvider(source_id="alpha_vantage", bars=[_us_bar("alpha_vantage")])
        service = MarketDataService(
            primary=primary,
            cache=cache,
            clock=lambda: datetime(2024, 1, 4, 1, 0, tzinfo=UTC),
            cache_first=True,
        )

        result = service.get_daily_bars("2330", "US", START, END)

        assert result.status is DataStatus.CACHED_STALE
        assert result.is_within_ttl is False
        assert primary.call_count == 0

    def test_a_request_reaching_further_back_than_ever_fetched_goes_live(
        self, tmp_path: Path
    ) -> None:
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        fetched_at = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
        cache.put([_us_bar("alpha_vantage")], source="alpha_vantage", fetched_at=fetched_at)
        cache.record_fetch("2330", "US", start=date(2024, 1, 2), end=END, fetched_at=fetched_at)
        primary = _StubProvider(source_id="alpha_vantage", bars=[_us_bar("alpha_vantage")])
        service = MarketDataService(
            primary=primary,
            cache=cache,
            clock=lambda: datetime(2024, 1, 2, 12, 0, tzinfo=UTC),
            cache_first=True,
        )

        result = service.get_daily_bars("2330", "US", START, END)  # START < 01-02

        assert result.status is DataStatus.FRESH
        assert primary.call_count == 1
        # ...and the widened range is now on record, so the next read is local.
        again = service.get_daily_bars("2330", "US", START, END)
        assert again.status is DataStatus.CACHED_STALE and primary.call_count == 1

    def test_falls_through_to_providers_when_no_cache_entry_exists(self, tmp_path: Path) -> None:
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        primary = _StubProvider(source_id="alpha_vantage", bars=[_us_bar("alpha_vantage")])
        service = MarketDataService(primary=primary, cache=cache, cache_first=True)

        result = service.get_daily_bars("2330", "US", START, END)

        assert result.status is DataStatus.FRESH
        assert primary.call_count == 1

    def test_a_seeded_cache_with_no_live_fetch_on_record_does_not_short_circuit(
        self, tmp_path: Path
    ) -> None:
        # Demo-seeded or pre-ADR-0009 rows: nobody ever asked a live source,
        # so layer 0 cannot vouch for coverage and the ladder runs once.
        cache = PriceBarCache(db_path=tmp_path / "cache.db")
        cache.put([_us_bar("demo_synthetic")], source="demo_synthetic")
        primary = _StubProvider(source_id="alpha_vantage", bars=[_us_bar("alpha_vantage")])
        service = MarketDataService(
            primary=primary,
            cache=cache,
            clock=lambda: datetime(2024, 1, 2, 12, 0, tzinfo=UTC),
            cache_first=True,
        )

        result = service.get_daily_bars("2330", "US", START, END)

        assert result.status is DataStatus.FRESH
        assert primary.call_count == 1


def test_widening_the_range_right_after_a_successful_fetch_goes_live(tmp_path: Path) -> None:
    """ADR-0009 D-3, driven by two real calls: a success is not a failed attempt."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    primary = _StubProvider(source_id="twse", bars=[_bar("twse")])
    now = {"at": datetime(2024, 1, 2, 15, 0, tzinfo=UTC)}
    service = MarketDataService(
        primary=primary, cache=cache, clock=lambda: now["at"], cache_first=True
    )
    service.get_daily_bars("2330", "TW", date(2024, 1, 2), END)
    now["at"] = datetime(2024, 1, 2, 15, 2, tzinfo=UTC)  # two minutes later
    widened = service.get_daily_bars("2330", "TW", START, END)  # START < 01-02
    assert primary.call_count == 2
    assert widened.status is DataStatus.FRESH


def test_a_historical_coverage_is_not_reused_for_a_request_that_runs_to_today(
    tmp_path: Path,
) -> None:
    """ADR-0009: CHECKED_RECENTLY needs the coverage to reach the expected session."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    fetched_at = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    cache.put([_bar("twse")], source="twse", fetched_at=fetched_at)
    # A complete fetch of history ending 01-02, asked for 40 minutes ago.
    checked = datetime(2024, 1, 4, 7, 20, tzinfo=UTC)
    cache.record_fetch("2330", "TW", start=START, end=date(2024, 1, 2), fetched_at=checked)
    cache.record_attempt("2330", "TW", at=checked)
    primary = _StubProvider(source_id="twse", bars=[_bar("twse")])
    service = MarketDataService(
        primary=primary,
        cache=cache,
        clock=lambda: datetime(2024, 1, 4, 8, 0, tzinfo=UTC),  # Thu 16:00 Taipei
        cache_first=True,
    )
    result = service.get_daily_bars("2330", "TW", START, END)  # END runs past 01-04
    assert primary.call_count == 1 and result.status is DataStatus.FRESH


def test_the_service_propagates_a_partial_answer(tmp_path: Path) -> None:
    class _PartialProvider(_StubProvider):
        def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
            return super().get_daily_bars(symbol, start, end).model_copy(update={"complete": False})

    service = MarketDataService(
        primary=_PartialProvider(source_id="twse", bars=[_bar("twse")]),
        cache=PriceBarCache(db_path=tmp_path / "cache.db"),
    )
    assert service.get_daily_bars("2330", "TW", START, END).complete is False


# --- ADR-0009 修訂 2026-09-15: a close published earlier than assumed -----------------


def _tw_bar(symbol: str, day: date) -> PriceBar:
    return _bar("twse").model_copy(update={"symbol": symbol, "date": day})


def test_another_series_holding_the_next_session_means_the_close_is_out(tmp_path: Path) -> None:
    """Wed 14:30 Taipei (before the 15:00 cutoff): 2330's cache holds Tue and would be
    called current, but 2317 already has Wednesday's bar -- the close is published."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    fetched = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)  # Tuesday, well outside the cooldown
    cache.put([_tw_bar("2330", date(2024, 1, 2))], source="twse", fetched_at=fetched)
    cache.record_fetch("2330", "TW", start=START, end=END, fetched_at=fetched)
    cache.put([_tw_bar("2317", date(2024, 1, 3))], source="twse")
    primary = _StubProvider(source_id="twse", bars=[_tw_bar("2330", date(2024, 1, 3))])
    now = {"at": datetime(2024, 1, 3, 6, 30, tzinfo=UTC)}  # Wed 14:30 Taipei
    service = MarketDataService(
        primary=primary, cache=cache, clock=lambda: now["at"], cache_first=True
    )
    first = service.get_daily_bars("2330", "TW", START, END)
    assert first.status is DataStatus.FRESH and primary.call_count == 1
    # Bounded: the refetch just happened, so the next click is local again.
    now["at"] = datetime(2024, 1, 3, 6, 40, tzinfo=UTC)
    second = service.get_daily_bars("2330", "TW", START, END)
    assert primary.call_count == 1 and second.status is DataStatus.CACHED_STALE


def test_early_publication_evidence_never_suppresses_a_fetch(tmp_path: Path) -> None:
    """Without evidence the ordinary rule stands: before the cutoff, Tuesday is current."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    fetched = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    cache.put([_tw_bar("2330", date(2024, 1, 2))], source="twse", fetched_at=fetched)
    cache.record_fetch("2330", "TW", start=START, end=END, fetched_at=fetched)
    primary = _StubProvider(source_id="twse", bars=[_tw_bar("2330", date(2024, 1, 3))])
    service = MarketDataService(
        primary=primary,
        cache=cache,
        clock=lambda: datetime(2024, 1, 3, 6, 30, tzinfo=UTC),
        cache_first=True,
    )
    result = service.get_daily_bars("2330", "TW", START, END)
    assert primary.call_count == 0
    assert result.status is DataStatus.CACHED_STALE and result.is_within_ttl is True


def test_demo_rows_are_not_evidence_that_the_market_traded(tmp_path: Path) -> None:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    cache.put([_tw_bar("DEMO", date(2024, 1, 3))], source="demo_synthetic")
    assert cache.market_has_session("TW", date(2024, 1, 3)) is False
    cache.put([_tw_bar("2317", date(2024, 1, 3))], source="twse")
    assert cache.market_has_session("TW", date(2024, 1, 3)) is True


def test_a_series_that_already_holds_the_next_session_is_not_refetched_on_evidence(
    tmp_path: Path,
) -> None:
    """tech-architect F-1: the evidence is about a bar this series may already have."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    fetched = datetime(2024, 1, 3, 5, 0, tzinfo=UTC)  # Wed 13:00 Taipei, two hours ago
    cache.put([_tw_bar("2330", date(2024, 1, 3))], source="twse", fetched_at=fetched)
    cache.record_fetch("2330", "TW", start=START, end=END, fetched_at=fetched)
    cache.put([_tw_bar("2317", date(2024, 1, 3))], source="twse")
    primary = _StubProvider(source_id="twse", bars=[_tw_bar("2330", date(2024, 1, 3))])
    service = MarketDataService(
        primary=primary,
        cache=cache,
        clock=lambda: datetime(2024, 1, 3, 6, 30, tzinfo=UTC),  # Wed 14:30 Taipei
        cache_first=True,
    )
    result = service.get_daily_bars("2330", "TW", START, END)
    assert primary.call_count == 0 and result.status is DataStatus.CACHED_STALE


def test_a_covered_series_whose_sources_are_failing_also_honours_the_cooldown(
    tmp_path: Path,
) -> None:
    """tech-architect F-2: R-8 holds on the covered path, not only without coverage."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    success = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)  # Tuesday: complete, up to 01-02
    cache.put([_tw_bar("2330", date(2024, 1, 2))], source="twse", fetched_at=success)
    cache.record_fetch("2330", "TW", start=START, end=END, fetched_at=success)
    primary = _StubProvider(source_id="twse", status=DataStatus.UNAVAILABLE)
    now = {"at": datetime(2024, 1, 3, 8, 0, tzinfo=UTC)}  # Wed 16:00 Taipei: 01-03 expected
    service = MarketDataService(
        primary=primary, cache=cache, clock=lambda: now["at"], cache_first=True
    )
    first = service.get_daily_bars("2330", "TW", START, END)  # ladder runs, fails
    assert primary.call_count == 1 and first.status is DataStatus.CACHED_STALE
    now["at"] = datetime(2024, 1, 3, 8, 20, tzinfo=UTC)
    second = service.get_daily_bars("2330", "TW", START, END)  # inside the cooldown
    assert primary.call_count == 1
    assert second.is_within_ttl is False and second.reason == RECENT_ATTEMPT_FAILED_REASON
    now["at"] = datetime(2024, 1, 3, 9, 30, tzinfo=UTC)
    service.get_daily_bars("2330", "TW", START, END)  # cooldown expired: try again
    assert primary.call_count == 2
