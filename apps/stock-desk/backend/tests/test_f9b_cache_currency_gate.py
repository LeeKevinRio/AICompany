"""F-9b commit 6: the cache gate and T-15 (layer 0 steps 4-5, fallback, cache-only, read-back).

ADR-0024 D-2 (5)(a) steps 4 and 5, (b), (c), (d), D-4 (index cache gate);
C-1 (six exits), C-13 (7)(8)(9), C-17 (index cache part), C-19 (cache refusals),
C-30, C-31 (F-9b form), C-32, C-34 (b)(c)(d), C-35 (c) at layer 0;
TA5 section 2 tests 2, 3, 4, 8; 風控 F9W-22, F9W-31 (b)(c), F9W-33 (a),
F9W-35 (a)(c), F9W-37.

D-2 (5)(a) steps 1-3 read the D-9 marker and are F-9b2's.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.data import gate_wording
from app.data.cache import CacheReadResult, PriceBarCache
from app.data.gate_wording import (
    CACHE_UNIT_REJECTED_REASON,
    UNIT_MISSING_REASON_US,
)
from app.data.interface import DataStatus, Market, MarketDataProvider, PriceBar, ProviderResult
from app.data.service import (
    CURRENCY_DIFFERS_LOG_PREFIX,
    MERGE_READBACK_FAILED_REASON,
    RECENT_ATTEMPT_FAILED_REASON,
    CurrencyLookupError,
    MarketDataService,
    _combine_reasons,
    mixed_sources_reason,
)
from app.portfolio.valuation import SYMBOL_OR_UNIT_REJECTED, PositionValuator, PriceMode
from app.positions.models import MARKET_CURRENCY, Position
from app.services.index import (
    IndexProviderBridge,
    IndexSeriesService,
    IndexServiceResolver,
    load_market_benchmark,
)
from app.services.market import PROVIDER_REASON_PREFIX, load_bars
from tests.f9b_helpers import AV_QUOTA_REASON
from tests.market_service_helpers import build_service, equity_service, index_service

SERVICE_LOGGER = "app.data.service"
NOW = datetime(2024, 1, 3, 8, 0, tzinfo=UTC)
START, END = date(2023, 11, 1), date(2024, 1, 2)
YF_DOWN = "yfinance 連線逾時或發生錯誤，暫不可用。"

RULING_2 = Path(__file__).resolve().parents[4] / (
    "work/reviews/2026-10-12-F-9-第二批字面逐字審-F9W-17至F9W-29-風控.md"
)


def _bar(
    day: date,
    currency: str,
    *,
    source: str = "alpha_vantage",
    symbol: str = "AAPL",
    close: str = "100",
) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        market="US",
        date=day,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1,
        currency="USD",
        as_of=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
        source=source,
    ).model_copy(update={"currency": currency})


DAYS = [date(2023, 12, 28), date(2023, 12, 29), date(2024, 1, 2)]


class _Rung(MarketDataProvider):
    def __init__(
        self,
        source_id: str,
        bars: list[PriceBar],
        *,
        reason: str | None = None,
        before: Callable[[], None] = lambda: None,
    ) -> None:
        self.source_id = source_id  # type: ignore[misc]
        self._bars = bars
        self._reason = reason
        self._before = before
        self.asked: list[tuple[str, date, date]] = []

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.asked.append((symbol, start, end))
        self._before()
        window = [bar for bar in self._bars if start <= bar.date <= end]
        return ProviderResult(
            bars=window,
            status=DataStatus.FRESH if window else DataStatus.UNAVAILABLE,
            as_of=NOW,
            source=self.source_id if window else "none",
            staleness_minutes=0 if window else None,
            reason=None if window else self._reason,
        )


class _Cache(PriceBarCache):
    """Counts reads and attempt writes."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path=db_path)
        self.gets = 0
        self.attempts = 0

    def get(
        self,
        symbol: str,
        market: Market,
        start: date,
        end: date,
        *,
        now: datetime | None = None,
    ) -> CacheReadResult | None:
        self.gets += 1
        return super().get(symbol, market, start, end, now=now)

    def record_attempt(self, symbol: str, market: Market, *, at: datetime | None = None) -> None:
        self.attempts += 1
        super().record_attempt(symbol, market, at=at)


def _seed(
    cache: PriceBarCache,
    bars: list[PriceBar],
    *,
    fetched_at: datetime = datetime(2024, 1, 2, 22, 0, tzinfo=UTC),
    coverage: tuple[date, date] | None = (START, END),
    symbol: str = "AAPL",
) -> None:
    cache.put(bars, source=bars[0].source, fetched_at=fetched_at)
    if coverage is not None:
        cache.record_fetch(symbol, "US", start=coverage[0], end=coverage[1], fetched_at=fetched_at)


def _records(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [
        (r.levelno, r.getMessage())
        for r in caplog.records
        if r.name == SERVICE_LOGGER and r.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)
    ]


def _field(message: str, name: str) -> str:
    return message.split(f" {name}=")[1].split(" ")[0]


def _layers(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [_field(message, "layer") for _, message in _records(caplog)]


def _service(
    cache: PriceBarCache,
    rungs: list[_Rung],
    *,
    clock: Callable[[], datetime] = lambda: NOW,
    cache_first: bool = True,
) -> MarketDataService:
    return equity_service(
        primary=rungs[0], backups=rungs[1:], cache=cache, clock=clock, cache_first=cache_first
    )


def _bad() -> list[PriceBar]:
    return [_bar(day, "GBp") for day in DAYS]


def _good(source: str = "alpha_vantage", close: str = "100") -> list[PriceBar]:
    return [_bar(day, "USD", source=source, close=close) for day in DAYS]


# --- T-15 (C-9, C-29) -----------------------------------------------------------------


def test_t15_is_the_approved_sentence_verbatim() -> None:
    line = RULING_2.read_text(encoding="utf-8").splitlines()[39].removeprefix("> ")
    assert CACHE_UNIT_REJECTED_REASON == line
    assert gate_wording.EQUITY_GATE_WORDING.cache_unit_rejected is CACHE_UNIT_REJECTED_REASON


# --- Layer 0, step 4 inside the R-8 cooldown: C-13 (7), C-31, gate before R-8 ----------


@pytest.mark.parametrize("coverage", [(START, END), None], ids=["covered", "no-coverage"])
def test_layer0_refused_inside_the_cooldown_states_t15_alone_and_asks_nobody(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, coverage: tuple[date, date] | None
) -> None:
    cache = _Cache(tmp_path / "c.db")
    _seed(cache, _bad(), coverage=coverage)
    cache.record_attempt("AAPL", "US", at=NOW - timedelta(hours=1))  # failed, recent
    cache.attempts = 0
    rung = _Rung("alpha_vantage", _good())
    service = _service(cache, [rung])

    with caplog.at_level(logging.INFO, logger=SERVICE_LOGGER):
        loaded = load_bars({"US": service}, symbol="AAPL", market="US", start=START, end=END)
    result = service.get_daily_bars("AAPL", "US", START, END)

    assert loaded.reason == CACHE_UNIT_REJECTED_REASON  # C-13 (7), exact
    assert loaded.bars == []
    assert result.rejection == "cache_unit_rejected"
    assert rung.asked == []
    # Without the gate R-8 would have served these rows with RECENT_ATTEMPT_FAILED_REASON.
    assert RECENT_ATTEMPT_FAILED_REASON not in (loaded.reason or "")
    assert cache.attempts == 0  # C-31 (F-9b form): no new record_attempt call site
    assert _layers(caplog)[0] == "layer0_cache"


# --- Layer 0, step 4 outside the cooldown: C-13 (8), C-32, TA5 test 2 order ---------------


def test_layer0_refused_outside_the_cooldown_runs_the_whole_ladder_then_t15(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cache = _Cache(tmp_path / "c.db")
    _seed(cache, _bad())
    primary = _Rung("alpha_vantage", [], reason=AV_QUOTA_REASON)
    backup = _Rung("yfinance", [], reason=YF_DOWN)
    service = _service(cache, [primary, backup])
    assert service._incremental_start("AAPL", "US", START, END) > START  # would have narrowed

    with caplog.at_level(logging.INFO, logger=SERVICE_LOGGER):
        loaded = load_bars({"US": service}, symbol="AAPL", market="US", start=START, end=END)

    assert loaded.reason == _combine_reasons([AV_QUOTA_REASON, YF_DOWN, CACHE_UNIT_REJECTED_REASON])
    assert primary.asked[0][1] == START  # step 4: fetch_start == start
    assert backup.asked[0][1] == START
    assert _layers(caplog) == ["layer0_cache", "fallback_cache"]
    assert cache.attempts == 1  # the ladder's own attempt, nothing more (C-31)


@pytest.mark.parametrize("ladder", ["primary-answers", "backup-answers"])
@pytest.mark.parametrize("orphan", [False, True], ids=["all-returned", "orphan-row"])
def test_layer0_refused_outside_the_cooldown_self_repairs_from_the_live_rung(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, orphan: bool, ladder: str
) -> None:
    """C-32 (TA5 R-63, TA6 R-75): the reply is exactly what the source returned.

    TA6 R-75 suggested: also when the primary fails and the backup answers,
    and the successful reply never carries T-15.
    """
    cache = _Cache(tmp_path / "c.db")
    stale = _bad()
    if orphan:
        # A bad row on a day the source does not return.
        stale.append(_bar(date(2023, 12, 27), "GBp"))
    _seed(cache, stale)
    fresh = _good(source="yfinance", close="101")
    rung = _Rung("yfinance", fresh)
    rungs = [rung]
    if ladder == "backup-answers":
        rungs = [_Rung("alpha_vantage", [], reason=AV_QUOTA_REASON), rung]
    clock = {"now": NOW}
    service = _service(cache, rungs, clock=lambda: clock["now"])

    with caplog.at_level(logging.INFO, logger=SERVICE_LOGGER):
        first = service.get_daily_bars("AAPL", "US", START, END)

    assert [r.asked for r in rungs] == [[("AAPL", START, END)]] * len(rungs)
    assert first.status is (DataStatus.FRESH if len(rungs) == 1 else DataStatus.BACKUP)
    assert first.bars == fresh  # dates and values, bar for bar
    assert CACHE_UNIT_REJECTED_REASON not in (first.reason or "")
    assert date(2023, 12, 27) not in {bar.date for bar in first.bars}
    assert first.rejection is None
    assert _layers(caplog) == ["layer0_cache"]
    valued = _valuator(service, "live").value_position(_position())
    assert valued.valuation.price is not None
    assert valued.valuation.price.value == Decimal("101")

    clock["now"] = NOW + timedelta(minutes=5)
    rung.asked.clear()
    second = service.get_daily_bars("AAPL", "US", START, END)
    if orphan:
        # 壞處 5 例外 (R-63): the orphan still refuses layer 0; the last ask was a
        # success, so R-8 does not hold and the ladder runs again.
        assert rung.asked == [("AAPL", START, END)]
        assert second.bars == fresh
    else:
        # The refused rows were overwritten: layer 0 serves the next request.
        assert rung.asked == []
        assert [bar.close for bar in second.bars] == [Decimal("101")] * 3


# --- Fallback: C-13 (9), C-34 (b) with a splice, C-34 (d) --------------------------------


def test_c13_9_w_c_prime_and_a_refused_cache(tmp_path: Path) -> None:
    cache = _Cache(tmp_path / "c.db")
    _seed(cache, _bad())
    service = _service(cache, [_Rung("yfinance", [_bar(DAYS[-1], "")])], cache_first=False)

    loaded = load_bars({"US": service}, symbol="AAPL", market="US", start=START, end=END)
    result = service.get_daily_bars("AAPL", "US", START, END)

    assert loaded.reason == (
        UNIT_MISSING_REASON_US.format(provider="yfinance").removesuffix("。")
        + "。 "
        + CACHE_UNIT_REJECTED_REASON
    )
    assert result.rejection == "unit_missing"  # D-7 (2): W-c' outranks the cache gate


def test_c34_b_a_spliced_cache_keeps_its_disclosure_after_the_w_c_prime(tmp_path: Path) -> None:
    """TA5 R-66, 風控 F9W-37 (a)(b): W-c' whole, then the splice sentence, nothing between."""
    cache = _Cache(tmp_path / "c.db")
    head = [_bar(DAYS[0], "USD", source="alpha_vantage")]
    tail = [_bar(day, "USD", source="yfinance") for day in DAYS[1:]]
    cache.put(head, source="alpha_vantage", fetched_at=datetime(2024, 1, 1, tzinfo=UTC))
    cache.put(tail, source="yfinance", fetched_at=datetime(2024, 1, 2, tzinfo=UTC))
    service = _service(cache, [_Rung("yfinance", [_bar(DAYS[-1], " ")])], cache_first=False)

    loaded = load_bars({"US": service}, symbol="AAPL", market="US", start=START, end=END)

    w_c_prime = UNIT_MISSING_REASON_US.format(provider="yfinance")
    splice = mixed_sources_reason(head + tail)
    assert splice is not None
    assert loaded.reason == _combine_reasons([w_c_prime, splice])
    assert loaded.status is DataStatus.CACHED_STALE
    assert loaded.reason is not None and w_c_prime in loaded.reason
    assert loaded.reason.index(splice) > loaded.reason.index(w_c_prime) + len(w_c_prime) - 1
    assert PROVIDER_REASON_PREFIX not in loaded.reason


def test_c34_d_the_next_call_inside_the_cooldown_serves_a_passing_cache_normally(
    tmp_path: Path,
) -> None:
    """T-17's shape (F9W-24): the gate stands before R-8 and lets a passing cache through."""
    cache = _Cache(tmp_path / "c.db")
    # Short of the latest session, so layer 0 falls through (REFETCH) on the first call.
    _seed(
        cache,
        _good()[:2],
        fetched_at=datetime(2023, 12, 29, 22, tzinfo=UTC),
        coverage=(START, DAYS[1]),
    )
    rung = _Rung("yfinance", [_bar(DAYS[-1], "")])
    clock = {"now": NOW}
    service = _service(cache, [rung], clock=lambda: clock["now"])
    first = service.get_daily_bars("AAPL", "US", START, END)
    assert first.status is DataStatus.CACHED_STALE  # W-c' + passing cache, C-34 (b)

    clock["now"] = NOW + timedelta(minutes=5)
    rung.asked.clear()
    second = service.get_daily_bars("AAPL", "US", START, END)
    valued = _valuator(service, "live").value_position(_position())

    assert rung.asked == []
    assert second.reason == RECENT_ATTEMPT_FAILED_REASON
    assert second.rejection is None
    assert valued.valuation.status == "ok"
    assert SYMBOL_OR_UNIT_REJECTED not in valued.valuation.missing


# --- Read-back: D-2 (5)(d), C-30, C-34 (c) ------------------------------------------------


def _racing_service(
    tmp_path: Path, backup_bars: list[PriceBar]
) -> tuple[_Cache, _Rung, _Rung, MarketDataService]:
    """Layer 0 reads a passing head; another writer drops a bad row before the read-back."""
    cache = _Cache(tmp_path / "c.db")
    _seed(
        cache,
        [_bar(day, "USD") for day in DAYS[:2]],
        fetched_at=datetime(2023, 12, 29, 22, tzinfo=UTC),
        coverage=(START, DAYS[1]),
    )

    def race() -> None:
        cache.put([_bar(date(2023, 12, 1), "GBp", source="other")], source="other")

    primary = _Rung("alpha_vantage", [_bar(DAYS[-1], "USD")], before=race)
    backup = _Rung("yfinance", backup_bars, reason=YF_DOWN)
    return cache, primary, backup, _service(cache, [primary, backup])


def test_a_refused_read_back_and_a_failing_ladder_state_t15_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cache, primary, backup, service = _racing_service(tmp_path, [])

    with caplog.at_level(logging.INFO, logger=SERVICE_LOGGER):
        result = service.get_daily_bars("AAPL", "US", START, END)
    reads_after = cache.gets

    assert primary.asked[0][1] > START  # the primary was narrowed (incremental)
    assert backup.asked == [("AAPL", START, END)]  # later rungs ask for the whole range
    assert result.bars == []
    assert result.rejection == "cache_unit_rejected"
    assert result.reason == _combine_reasons([CACHE_UNIT_REJECTED_REASON, YF_DOWN])
    assert (result.reason or "").count(CACHE_UNIT_REJECTED_REASON) == 1  # C-30
    assert MERGE_READBACK_FAILED_REASON not in (result.reason or "")
    assert _layers(caplog) == ["incremental_readback"]  # the fallback did not read again
    assert reads_after == 2  # layer 0 and the read-back only


def test_a_refused_read_back_then_a_whole_range_success_states_no_t15(tmp_path: Path) -> None:
    whole = [_bar(day, "USD", source="yfinance", close="102") for day in DAYS]
    _cache, _primary, backup, service = _racing_service(tmp_path, whole)

    result = service.get_daily_bars("AAPL", "US", START, END)
    valued = _valuator(service, "live").value_position(_position())

    assert backup.asked == [("AAPL", START, END)]
    assert result.bars == whole
    assert result.rejection is None
    assert CACHE_UNIT_REJECTED_REASON not in (result.reason or "")  # C-30, C-34 (c)
    assert valued.valuation.status == "ok"


# --- Cache-only: D-2 (5)(c) ----------------------------------------------------------------


def test_the_cache_only_read_refuses_with_t15_and_writes_nothing(tmp_path: Path) -> None:
    cache = _Cache(tmp_path / "c.db")
    _seed(cache, _bad())
    cache.attempts = 0
    service = _service(cache, [_Rung("alpha_vantage", _good())])

    result = service.get_cached_bars("AAPL", "US", START, END)

    assert result.bars == []
    assert result.status is DataStatus.UNAVAILABLE
    assert result.reason == CACHE_UNIT_REJECTED_REASON
    assert result.rejection == "cache_unit_rejected"
    assert cache.attempts == 0


# --- C-19: the valuator's token for a refused cache, live and cache-only --------------------


def _position() -> Position:
    return Position(
        id=1,
        symbol="AAPL",
        market="US",
        quantity=Decimal(10),
        avg_cost=Decimal(90),
        currency="USD",
        opened_at=date(2023, 12, 1),
        instrument_type="stock",
        note=None,
        created_at=NOW,
        updated_at=NOW,
    )


class _CountingFx:
    def __init__(self) -> None:
        self.calls = 0

    def get_daily_rates(self, pair: str, start: date, end: date) -> object:
        from app.data.providers.fx import FxRate, FxRateResult

        self.calls += 1
        return FxRateResult(
            rates=[FxRate(pair=pair, date=end, rate=Decimal("31"), as_of=NOW, source="fx")],
            status=DataStatus.FRESH,
            as_of=NOW,
            source="fx",
        )


def _valuator(
    service: MarketDataService, mode: PriceMode, fx: _CountingFx | None = None
) -> PositionValuator:
    return PositionValuator(
        market_services={"US": service},
        fx_provider=fx or _CountingFx(),  # type: ignore[arg-type]
        clock=lambda: NOW,
        price_mode=mode,
    )


@pytest.mark.parametrize("mode", ["live", "cache_only"])
def test_c19_a_refused_cache_gives_the_refused_answer_token(
    tmp_path: Path, mode: PriceMode
) -> None:
    cache = _Cache(tmp_path / "c.db")
    _seed(cache, _bad())
    cache.record_attempt("AAPL", "US", at=NOW - timedelta(hours=1))
    fx = _CountingFx()
    service = _service(cache, [_Rung("alpha_vantage", _good())])

    valuation = _valuator(service, mode, fx).value_position(_position()).valuation

    assert valuation.missing == [SYMBOL_OR_UNIT_REJECTED]
    assert valuation.fx is None and valuation.fx_open is None
    assert fx.calls == 0


# --- C-35 (c) at layer 0 --------------------------------------------------------------------


def test_c35_c_a_lookup_that_forgets_raises_at_layer_0(tmp_path: Path) -> None:
    cache = _Cache(tmp_path / "c.db")
    _seed(cache, _good())
    state = {"forget": False}

    def lookup(market: Market) -> str | None:
        return None if state["forget"] else MARKET_CURRENCY[market]

    rung = _Rung("alpha_vantage", _good())
    service = build_service(
        primary=rung,
        cache=cache,
        scope="equity",
        currency_for_market=lookup,
        clock=lambda: NOW,
        cache_first=True,
    )
    fetches: list[object] = []
    cache.record_fetch = lambda *a, **k: fetches.append(a)  # type: ignore[method-assign]
    state["forget"] = True

    with pytest.raises(CurrencyLookupError):
        service.get_daily_bars("AAPL", "US", START, END)
    assert rung.asked == []
    assert fetches == []


# --- Index cache gate: TA5 section 2 tests 2, 3, 4; F9W-31 (b)(c), F9W-35 (a)(c) -------------


def _index_bar(day: date, currency: str, close: str = "4700") -> PriceBar:
    return _bar(day, currency, source="yfinance", symbol="^GSPC", close=close)


class _IndexSource:
    def __init__(self, bars: list[PriceBar]) -> None:
        self.bars = bars
        self.asked: list[tuple[str, date, date]] = []

    def get_index_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.asked.append((symbol, start, end))
        window = [bar for bar in self.bars if start <= bar.date <= end]
        return ProviderResult(
            bars=window,
            status=DataStatus.BACKUP if window else DataStatus.UNAVAILABLE,
            as_of=NOW,
            source="yfinance" if window else "none",
            staleness_minutes=0 if window else None,
        )


def _index(
    tmp_path: Path, source: _IndexSource, stale: list[PriceBar]
) -> tuple[_Cache, MarketDataService]:
    cache = _Cache(tmp_path / "i.db")
    _seed(cache, stale, symbol="^GSPC")
    service = index_service(
        primary=IndexProviderBridge(source), cache=cache, clock=lambda: NOW, cache_first=True
    )
    return cache, service


def _equity_constants() -> list[str]:
    return [
        value
        for name, value in vars(gate_wording).items()
        if name.endswith("_REASON") or name.endswith(("_US", "_TW"))
        if isinstance(value, str)
    ]


def _assert_no_equity_wording(reason: str | None) -> None:
    for constant in _equity_constants():
        head = constant.split("{provider}")[-1]
        assert head not in (reason or "")


def test_index_test2_the_ladder_fails_and_both_cache_reads_are_recorded(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = _IndexSource([])
    _cache, service = _index(tmp_path, source, [_index_bar(day, "TWD") for day in DAYS])

    with caplog.at_level(logging.INFO, logger=SERVICE_LOGGER):
        result = service.get_daily_bars("^GSPC", "US", START, END)

    records = _records(caplog)
    assert [(level, _field(m, "layer"), _field(m, "scope")) for level, m in records] == [
        (logging.ERROR, "layer0_cache", "index"),
        (logging.ERROR, "fallback_cache", "index"),
    ]
    assert result.bars == []
    assert result.rejection == "cache_unit_rejected"
    _assert_no_equity_wording(result.reason)


@pytest.mark.parametrize("orphan", [False, True], ids=["all-returned", "orphan-row"])
def test_index_test3_self_repair_serves_only_the_live_rows(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, orphan: bool
) -> None:
    """F9W-35 (a): bar for bar what the source returned; one layer-0 ERROR; start == start."""
    stale = [_index_bar(day, "TWD") for day in DAYS]
    if orphan:
        stale.append(_index_bar(date(2023, 12, 27), "TWD"))
    live = [_index_bar(day, "USD", close="4800") for day in DAYS]
    source = _IndexSource(live)
    _cache, service = _index(tmp_path, source, stale)
    resolver: IndexServiceResolver = {"US": IndexSeriesService(service)}

    with caplog.at_level(logging.INFO, logger=SERVICE_LOGGER):
        result = service.get_daily_bars("^GSPC", "US", START, END)

    assert source.asked == [("^GSPC", START, END)]
    assert result.bars == live
    assert date(2023, 12, 27) not in {bar.date for bar in result.bars}
    records = _records(caplog)
    assert [(level, _field(m, "layer"), _field(m, "scope")) for level, m in records] == [
        (logging.ERROR, "layer0_cache", "index")
    ]
    if not orphan:
        # The consumer reads the repaired series, never the refused rows.
        benchmark = load_market_benchmark(resolver, market="US", start=START, end=END)
        assert [bar.close for bar in benchmark.bars] == [Decimal("4800")] * 3


def test_index_test4_inside_the_cooldown_no_source_and_no_reason(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = _IndexSource([_index_bar(day, "USD") for day in DAYS])
    cache, service = _index(tmp_path, source, [_index_bar(day, "TWD") for day in DAYS])
    cache.record_attempt("^GSPC", "US", at=NOW - timedelta(hours=1))

    with caplog.at_level(logging.INFO, logger=SERVICE_LOGGER):
        result = service.get_daily_bars("^GSPC", "US", START, END)

    assert source.asked == []
    assert result.reason is None
    assert result.bars == []
    assert result.rejection == "cache_unit_rejected"
    assert len(_records(caplog)) == 1


def test_index_cache_only_read_refuses_without_wording(tmp_path: Path) -> None:
    source = _IndexSource([])
    _cache, service = _index(tmp_path, source, [_index_bar(day, "TWD") for day in DAYS])

    result = service.get_cached_bars("^GSPC", "US", START, END)

    assert result.bars == [] and result.reason is None
    assert result.rejection == "cache_unit_rejected"


# --- TA5 section 2 test 8: no reader wording in any record --------------------------------


def test_test8_no_user_facing_constant_is_part_of_any_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=SERVICE_LOGGER)
    cache = _Cache(tmp_path / "a.db")
    _seed(cache, _bad())
    service = _service(cache, [_Rung("yfinance", [_bar(DAYS[-1], "")])])
    service.get_daily_bars("AAPL", "US", START, END)
    service.get_cached_bars("AAPL", "US", START, END)
    _cache_i, index = _index(tmp_path, _IndexSource([]), [_index_bar(day, "TWD") for day in DAYS])
    index.get_daily_bars("^GSPC", "US", START, END)

    messages = [message for _, message in _records(caplog)]
    assert len(messages) >= 4
    for constant in _equity_constants():
        for fragment in constant.split("{provider}"):
            if fragment.strip():
                for message in messages:
                    assert fragment not in message


# --- qa-reviewer non-blocking (1): every equity cache refusal states a sentence -------------


@pytest.mark.parametrize("path", ["layer0-cooldown", "fallback", "cache_only"])
def test_every_equity_cache_refusal_carries_a_non_blank_reason(tmp_path: Path, path: str) -> None:
    cache = _Cache(tmp_path / "c.db")
    _seed(cache, _bad())
    if path == "layer0-cooldown":
        cache.record_attempt("AAPL", "US", at=NOW - timedelta(hours=1))
    service = _service(
        cache, [_Rung("alpha_vantage", [], reason=None)], cache_first=path != "fallback"
    )
    result = (
        service.get_cached_bars("AAPL", "US", START, END)
        if path == "cache_only"
        else service.get_daily_bars("AAPL", "US", START, END)
    )
    assert result.rejection is not None
    assert result.reason is not None and result.reason.strip()
