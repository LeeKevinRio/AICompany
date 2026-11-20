"""``force_refresh_benchmark`` and the pass-through (ADR-0030 supplement 10 point 2, S-20a).

* the range: ``end`` is the Taipei date of the system clock, ``start`` is
  ``end`` minus ``lookback_days``; the series is ``MARKET_BENCHMARK[market]``;
* no ``now``, ``as_of``, ``start`` or ``end`` parameter (signature and AST);
* the newest-by-date bar is read back from the cache only after an ``ok``
  refresh; a structural gap (no benchmark, no service, no live refresh method,
  an empty read-back) is not ``ok``; every other exception propagates;
* ``IndexSeriesService.refresh_daily_bars_live`` passes through;
* the import graph: ``app.services`` does not reach ``app.forecast`` (K-2);
* integration (offline): after the refresh the recorder's own fetch asks no
  source again -- with and without a bar for T -- and the race of supplement 10
  point 1 (e) is pinned as the documented behaviour.

Every cache is a ``tmp_path`` file and every source is a fake.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.data.cache import PriceBarCache
from app.data.interface import DataStatus, Market, PriceBar, ProviderResult
from app.data.service import CurrencyLookupError, LiveRefreshOutcome
from app.forecast import recorder as recorder_module
from app.services import index as index_module
from app.services.index import (
    EMPTY_READBACK_REASON,
    LIVE_REFRESH_FAILED_REASON,
    MARKET_BENCHMARK,
    NO_BENCHMARK_FOR_REFRESH_REASON,
    NO_LIVE_REFRESH_METHOD_REASON,
    NO_SERVICE_FOR_REFRESH_REASON,
    ForcedBenchmarkRefresh,
    IndexSeriesService,
    IndexServiceResolver,
    force_refresh_benchmark,
    load_market_benchmark,
)
from tests.force_refresh_helpers import (
    AT_22_10,
    LOOKBACK_DAYS,
    START,
    Clock,
    FakeIndexSource,
    T,
    index_bar,
    seed,
    weekdays,
)
from tests.import_graph import APP_ROOT, reachable_app_modules
from tests.market_service_helpers import build_service, index_service, market_currency

TIME_PARAMS = {"now", "as_of", "start", "end", "T", "t", "clock", "today", "at", "when"}
YESTERDAY = datetime(2026, 11, 17, 14, 10, tzinfo=UTC)
AT_17_45 = datetime(2026, 11, 18, 9, 45, tzinfo=UTC)
ALL_DAYS = weekdays(START, T)


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> Clock:
    """The system clock ``force_refresh_benchmark`` reads, frozen at 22:10 Taipei on T."""
    clock = Clock(AT_22_10)
    monkeypatch.setattr(index_module, "_system_now", clock)
    return clock


class _Recording:
    """A service that records what it is asked and answers as told."""

    def __init__(
        self,
        outcome: LiveRefreshOutcome,
        bars: list[PriceBar],
        *,
        raises: BaseException | None = None,
    ) -> None:
        self._outcome = outcome
        self._bars = bars
        self._raises = raises
        self.refreshed: list[tuple[str, Market, date, date]] = []
        self.read: list[tuple[str, Market, date, date]] = []

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        raise AssertionError("the forced refresh never uses the ladder entry")

    def refresh_daily_bars_live(
        self, symbol: str, market: Market, start: date, end: date
    ) -> LiveRefreshOutcome:
        self.refreshed.append((symbol, market, start, end))
        if self._raises is not None:
            raise self._raises
        return self._outcome

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        self.read.append((symbol, market, start, end))
        return ProviderResult(
            bars=self._bars,
            status=DataStatus.CACHED_STALE if self._bars else DataStatus.UNAVAILABLE,
            as_of=AT_22_10,
            source="yfinance" if self._bars else "none",
        )


def _ok() -> LiveRefreshOutcome:
    return LiveRefreshOutcome(
        ok=True,
        source="yfinance",
        requested_at=AT_22_10,
        written_at=AT_22_10,
        live_bar_count=3,
        live_latest_date=T,
        complete=True,
        reason=None,
    )


def _resolver(service: object) -> IndexServiceResolver:
    resolver: Mapping[Market, Any] = {"TW": service, "US": service}
    return resolver


# --- the range and the series -------------------------------------------------------------------


def test_the_range_is_the_taipei_date_minus_the_lookback(frozen: Clock) -> None:
    bars = [index_bar(T, as_of=AT_22_10)]
    service = _Recording(_ok(), bars)
    refreshed = force_refresh_benchmark(_resolver(service), market="TW", lookback_days=531)
    expected = ("^TWII", "TW", T - timedelta(days=531), T)
    assert service.refreshed == [expected]
    assert service.read == [expected]
    assert MARKET_BENCHMARK["TW"].series_symbol == "^TWII"
    assert refreshed.ok and refreshed.latest_cached_bar == bars[0] and refreshed.reason is None


def test_the_end_is_the_taipei_date_not_the_utc_date(frozen: Clock) -> None:
    frozen.at = datetime(2026, 11, 18, 16, 30, tzinfo=UTC)  # 00:30 on 11-19 in Taipei
    service = _Recording(_ok(), [index_bar(T, as_of=AT_22_10)])
    force_refresh_benchmark(_resolver(service), market="TW", lookback_days=10)
    ((_, _, start, end),) = service.refreshed
    assert (start, end) == (date(2026, 11, 9), date(2026, 11, 19))


def test_the_newest_bar_by_date_is_returned(frozen: Clock) -> None:
    older = index_bar(T - timedelta(days=1), as_of=AT_22_10 + timedelta(hours=1))
    newest = index_bar(T, as_of=AT_22_10)
    service = _Recording(_ok(), [newest, older])  # out of order on purpose
    refreshed = force_refresh_benchmark(_resolver(service), market="TW", lookback_days=5)
    assert refreshed.latest_cached_bar == newest


def test_the_signature_has_no_time_parameter() -> None:
    params = inspect.signature(force_refresh_benchmark).parameters
    assert list(params) == ["resolver", "market", "lookback_days"]
    assert not set(params) & TIME_PARAMS
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in list(params.values())[1:])


def _parameter_names(source: str, name: str) -> set[str]:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            arguments = node.args
            return {
                a.arg
                for a in (
                    *arguments.posonlyargs,
                    *arguments.args,
                    *arguments.kwonlyargs,
                    *([arguments.vararg] if arguments.vararg else []),
                    *([arguments.kwarg] if arguments.kwarg else []),
                )
            }
    raise AssertionError(f"{name} not found")


def test_the_ast_of_the_function_has_no_time_parameter() -> None:
    source = (APP_ROOT / "services" / "index.py").read_text(encoding="utf-8")
    names = _parameter_names(source, "force_refresh_benchmark")
    assert names == {"resolver", "market", "lookback_days"}
    assert not names & TIME_PARAMS


def test_the_time_parameter_scan_has_teeth() -> None:
    for extra in ("now", "as_of", "start", "end"):
        source = f"def force_refresh_benchmark(resolver, *, market, lookback_days, {extra}): ...\n"
        assert _parameter_names(source, "force_refresh_benchmark") & TIME_PARAMS == {extra}


# --- structural gaps and exceptions -------------------------------------------------------------


def test_no_benchmark_asks_nothing(frozen: Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(index_module, "MARKET_BENCHMARK", {})
    service = _Recording(_ok(), [])
    refreshed = force_refresh_benchmark(_resolver(service), market="TW", lookback_days=5)
    assert not refreshed.ok and refreshed.latest_cached_bar is None
    assert refreshed.reason == NO_BENCHMARK_FOR_REFRESH_REASON
    assert refreshed.live == LiveRefreshOutcome.failed(NO_BENCHMARK_FOR_REFRESH_REASON)
    assert service.refreshed == [] and service.read == []


def test_no_service_asks_nothing(frozen: Clock) -> None:
    refreshed = force_refresh_benchmark({}, market="TW", lookback_days=5)
    assert not refreshed.ok and refreshed.reason == NO_SERVICE_FOR_REFRESH_REASON
    assert refreshed.live.ok is False


class _PriceServiceOnly:
    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        raise AssertionError("not asked")

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        raise AssertionError("not asked")


def test_a_service_without_the_live_refresh_method_asks_nothing(frozen: Clock) -> None:
    refreshed = force_refresh_benchmark(
        _resolver(_PriceServiceOnly()), market="TW", lookback_days=5
    )
    assert not refreshed.ok and refreshed.reason == NO_LIVE_REFRESH_METHOD_REASON


def test_a_failed_refresh_reads_nothing_back(frozen: Clock) -> None:
    service = _Recording(LiveRefreshOutcome.failed("source down"), [index_bar(T, as_of=YESTERDAY)])
    refreshed = force_refresh_benchmark(_resolver(service), market="TW", lookback_days=5)
    assert not refreshed.ok and refreshed.latest_cached_bar is None
    assert refreshed.reason == "source down"
    assert service.read == []  # the cache is never read as the answer
    silent = _Recording(LiveRefreshOutcome.failed(None), [])
    assert force_refresh_benchmark(_resolver(silent), market="TW", lookback_days=5).reason == (
        LIVE_REFRESH_FAILED_REASON
    )


def test_an_empty_read_back_is_not_ok(frozen: Clock) -> None:
    service = _Recording(_ok(), [])
    refreshed = force_refresh_benchmark(_resolver(service), market="TW", lookback_days=5)
    assert not refreshed.ok and refreshed.live.ok
    assert refreshed.latest_cached_bar is None and refreshed.reason == EMPTY_READBACK_REASON


@pytest.mark.parametrize(
    "error", [RuntimeError("boom"), CurrencyLookupError("no currency"), OSError("disk")]
)
def test_every_other_exception_propagates(frozen: Clock, error: Exception) -> None:
    service = _Recording(_ok(), [], raises=error)
    with pytest.raises(type(error)):
        force_refresh_benchmark(_resolver(service), market="TW", lookback_days=5)


def test_a_failing_read_back_propagates(frozen: Clock) -> None:
    class _BrokenRead(_Recording):
        def get_cached_bars(
            self, symbol: str, market: Market, start: date, end: date
        ) -> ProviderResult:
            raise RuntimeError("read failed")

    with pytest.raises(RuntimeError):
        force_refresh_benchmark(_resolver(_BrokenRead(_ok(), [])), market="TW", lookback_days=5)


def test_the_result_carries_no_label_or_prediction() -> None:
    fields = set(ForcedBenchmarkRefresh.__dataclass_fields__)
    assert fields == {"live", "latest_cached_bar", "reason"}
    assert set(LiveRefreshOutcome.__dataclass_fields__) == {
        "ok",
        "source",
        "requested_at",
        "written_at",
        "live_bar_count",
        "live_latest_date",
        "complete",
        "reason",
    }


# --- the pass-through ---------------------------------------------------------------------------


def test_the_index_facade_passes_the_refresh_through() -> None:
    outcome = _ok()
    inner = _Recording(outcome, [])
    facade = IndexSeriesService(inner)
    assert facade.refresh_daily_bars_live("^TWII", "TW", START, T) is outcome
    assert inner.refreshed == [("^TWII", "TW", START, T)]


def test_the_index_facade_over_a_service_without_the_method_is_not_ok() -> None:
    facade = IndexSeriesService(_PriceServiceOnly())
    assert facade.refresh_daily_bars_live("^TWII", "TW", START, T) == LiveRefreshOutcome.failed(
        NO_LIVE_REFRESH_METHOD_REASON
    )


# --- K-2: app.services does not reach app.forecast ----------------------------------------------


def _forecast_modules(modules: set[str]) -> set[str]:
    return {m for m in modules if m == "app.forecast" or m.startswith("app.forecast.")}


def test_k2_the_index_module_does_not_reach_the_forecast_core() -> None:
    assert _forecast_modules(reachable_app_modules(("app.services.index",))) == set()


def test_k2_no_services_module_reaches_the_forecast_core() -> None:
    roots = tuple(
        "app.services." + path.stem
        for path in sorted((APP_ROOT / "services").glob("*.py"))
        if path.stem != "__init__"
    )
    assert "app.services.index" in roots
    assert _forecast_modules(reachable_app_modules((*roots, "app.services"))) == set()


def test_k2_the_import_scan_has_teeth() -> None:
    # The scheduler does import the recorder, so the same walk sees the core from there.
    assert "app.forecast.recorder" in _forecast_modules(reachable_app_modules(("app.scheduler",)))


# --- integration (offline): after the refresh the recorder asks nothing again --------------------


def _real_resolver(
    tmp_path: Path, source: FakeIndexSource, clock: Clock
) -> tuple[IndexServiceResolver, PriceBarCache]:
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    service = index_service(primary=source, cache=cache, clock=clock, cache_first=True)
    facade = IndexSeriesService(service)
    return {"TW": facade, "US": facade}, cache


def _recorder_fetch(resolver: IndexServiceResolver, now: datetime) -> Any:
    """The recorder's own fetch (same loader, same range formula, same resolver)."""
    return recorder_module._fetch(load_market_benchmark, resolver, now, 60)


def test_c1_with_a_bar_for_t_the_recorder_asks_no_source_again(
    tmp_path: Path, frozen: Clock
) -> None:
    clock = Clock(AT_22_10)
    t_minus_1 = T - timedelta(days=1)
    source = FakeIndexSource(clock, ALL_DAYS, close="17100", before=lambda: clock.tick(1))
    resolver, cache = _real_resolver(tmp_path, source, clock)
    seed(cache, weekdays(START, t_minus_1), at=YESTERDAY, covered=(START, t_minus_1))
    t0 = AT_22_10

    refreshed = force_refresh_benchmark(
        resolver,
        market=recorder_module.MARKET,
        lookback_days=recorder_module.FETCH_CALENDAR_DAYS + recorder_module.FETCH_SLACK_DAYS,
    )
    assert refreshed.ok and refreshed.latest_cached_bar is not None
    assert refreshed.latest_cached_bar.date == T and refreshed.latest_cached_bar.as_of >= t0
    assert len(source.asked) == 1

    clock.tick(1)
    captured = _recorder_fetch(resolver, clock())
    assert len(source.asked) == 1  # no second live request
    snapshot = captured.snapshot
    assert snapshot is not None and snapshot.bars[-1].session_date == T
    assert snapshot.bars[-1].as_of >= t0
    assert captured.settling == ()


def test_c2_without_a_bar_for_t_the_recorder_asks_no_source_again(
    tmp_path: Path, frozen: Clock
) -> None:
    clock = Clock(AT_22_10)
    t_minus_1 = T - timedelta(days=1)
    # The source has no row for T (e.g. a null at the source, dropped by the adapter).
    source = FakeIndexSource(clock, weekdays(START, t_minus_1), before=lambda: clock.tick(1))
    resolver, cache = _real_resolver(tmp_path, source, clock)
    seed(cache, weekdays(START, t_minus_1), at=YESTERDAY, covered=(START, t_minus_1))
    t0 = AT_22_10

    refreshed = force_refresh_benchmark(
        resolver,
        market=recorder_module.MARKET,
        lookback_days=recorder_module.FETCH_CALENDAR_DAYS + recorder_module.FETCH_SLACK_DAYS,
    )
    # Supplement 10 point 1 (f): a success; the newest bar is T-1, re-stamped by this refresh.
    assert refreshed.ok and refreshed.live.live_latest_date == t_minus_1
    assert refreshed.latest_cached_bar is not None
    assert refreshed.latest_cached_bar.date == t_minus_1
    assert refreshed.latest_cached_bar.as_of >= t0

    clock.tick(1)
    captured = _recorder_fetch(resolver, clock())
    assert len(source.asked) == 1  # no second live request
    assert captured.snapshot is not None and captured.snapshot.bars[-1].session_date == t_minus_1


def test_c2_an_earlier_bar_for_t_stays_the_newest_and_keeps_its_old_stamp(
    tmp_path: Path, frozen: Clock
) -> None:
    # Supplement 10 point 1 (f), last item: the cache already held T from 17:45 and
    # this answer has no T, so the newest bar predates t0 (the scheduler then skips).
    clock = Clock(AT_22_10)
    t_minus_1 = T - timedelta(days=1)
    source = FakeIndexSource(clock, weekdays(START, t_minus_1))
    resolver, cache = _real_resolver(tmp_path, source, clock)
    seed(cache, weekdays(START, T), at=AT_17_45, covered=(START, T))
    refreshed = force_refresh_benchmark(resolver, market="TW", lookback_days=LOOKBACK_DAYS)
    assert refreshed.ok and refreshed.latest_cached_bar is not None
    assert refreshed.latest_cached_bar.date == T
    assert refreshed.latest_cached_bar.as_of == AT_17_45 < AT_22_10


def test_c3_the_race_is_the_documented_behaviour(tmp_path: Path, frozen: Clock) -> None:
    """Supplement 10 point 1 (e): last writer wins; an earlier request can rewrite ``as_of``.

    Pinned as a known limitation, not a requirement to fix: a request issued
    before t0 whose answer is written after the refresh leaves T's row stamped
    before t0, and the recorder reads that row.
    """
    clock = Clock(AT_22_10)
    source = FakeIndexSource(clock, ALL_DAYS, close="17100")
    resolver, cache = _real_resolver(tmp_path, source, clock)
    refreshed = force_refresh_benchmark(resolver, market="TW", lookback_days=LOOKBACK_DAYS)
    assert refreshed.latest_cached_bar is not None
    assert refreshed.latest_cached_bar.as_of == AT_22_10

    earlier = AT_22_10 - timedelta(seconds=2)  # another process's request, written later
    cache.put(
        [index_bar(T, as_of=earlier, close="17090")],
        source="yfinance",
        fetched_at=AT_22_10 + timedelta(seconds=3),
    )
    clock.tick(5)
    captured = _recorder_fetch(resolver, clock())
    assert len(source.asked) == 1
    assert captured.snapshot is not None
    last = captured.snapshot.bars[-1]
    assert (last.session_date, last.as_of, str(last.close)) == (T, earlier, "17090")


def test_the_lookup_that_cannot_answer_propagates_through_the_real_service(
    tmp_path: Path, frozen: Clock
) -> None:
    clock = Clock(AT_22_10)
    armed = {"on": False}

    def lookup(market: Market) -> str | None:
        return None if armed["on"] else market_currency(market)

    service = build_service(
        primary=FakeIndexSource(clock, ALL_DAYS),
        cache=PriceBarCache(db_path=tmp_path / "cache.db"),
        scope="index",
        currency_for_market=lookup,
        clock=clock,
        cache_first=True,
    )
    armed["on"] = True
    with pytest.raises(CurrencyLookupError):
        force_refresh_benchmark(
            {"TW": IndexSeriesService(service)}, market="TW", lookback_days=LOOKBACK_DAYS
        )
