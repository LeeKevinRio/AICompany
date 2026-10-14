"""F-9b commit 5: the live rung's currency gate (W-c / W-c' fail-closed).

ADR-0024 D-2 (1)-(4), D-3, D-4 (index live refusal, TA6 R-72), D-7 (2);
C-1 (live exit), C-2, C-3, C-11, C-13 (3)(4)(5)(10), C-14, C-33, C-34 (b)(e),
C-35 (b) and the live checkpoint of (c); 風控 F9W-3, F9W-4 (a), F9W-6,
F9W-33 (a)(b)(c), F9W-38 (b), F9W-39.

The cache checkpoints are still observed only here; their gate is commit 6.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.cache import CacheReadResult, PriceBarCache
from app.data.gate_wording import (
    EQUITY_GATE_WORDING,
    UNIT_MISMATCH_REASON_TW,
    UNIT_MISMATCH_REASON_US,
    UNIT_MISSING_REASON_TW,
    UNIT_MISSING_REASON_US,
)
from app.data.interface import DataStatus, Market, MarketDataProvider, PriceBar, ProviderResult
from app.data.service import (
    CURRENCY_DIFFERS_LOG_PREFIX,
    RECENT_ATTEMPT_FAILED_REASON,
    CurrencyLookupError,
    MarketDataService,
    _combine_reasons,
    mixed_sources_reason,
)
from app.leverage.index_mapping import lookup_index_ref
from app.portfolio.valuation import SYMBOL_OR_UNIT_REJECTED, PositionValuator
from app.positions.models import MARKET_CURRENCY, Position
from app.services.index import (
    MARKET_BENCHMARK,
    NO_BARS_REASON,
    IndexProviderBridge,
    IndexSeriesService,
    IndexServiceResolver,
    LoadedBenchmark,
    LoadedIndexBars,
    load_index_bars,
    load_market_benchmark,
)
from app.services.market import PROVIDER_REASON_PREFIX, load_bars
from tests.f9b_helpers import AV_QUOTA_REASON
from tests.market_service_helpers import build_service, equity_service, index_service

SERVICE_LOGGER = "app.data.service"
NOW = datetime(2024, 1, 3, 8, 0, tzinfo=UTC)


def _bar(
    day: date,
    *,
    currency: str,
    source: str,
    symbol: str = "2330",
    market: Market = "TW",
    close: str = "10",
) -> PriceBar:
    bar = PriceBar(
        symbol=symbol,
        market=market,
        date=day,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1,
        currency="TWD",
        as_of=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
        source=source,
    )
    # ``PriceBar`` refuses a blank currency; a source can still declare one
    # (F-9c), so the value is set verbatim here.
    return bar.model_copy(update={"currency": currency})


class _Rung(MarketDataProvider):
    """A provider with a fixed answer; ``reason`` when it has no bars."""

    def __init__(self, source_id: str, bars: list[PriceBar], *, reason: str | None = None) -> None:
        self.source_id = source_id  # type: ignore[misc]
        self._bars = bars
        self._reason = reason
        self.asked: list[tuple[str, date, date]] = []

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.asked.append((symbol, start, end))
        window = [bar for bar in self._bars if start <= bar.date <= end]
        return ProviderResult(
            bars=window,
            status=DataStatus.FRESH if window else DataStatus.UNAVAILABLE,
            as_of=NOW,
            source=self.source_id if window else "none",
            staleness_minutes=0 if window else None,
            reason=None if window else self._reason,
        )


class _NamelessRung(MarketDataProvider):
    """A provider class that never declared ``source_id`` (C-14)."""

    def __init__(self, bars: list[PriceBar]) -> None:
        self._bars = bars

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        return ProviderResult(
            bars=self._bars, status=DataStatus.FRESH, as_of=NOW, source="nameless"
        )


class _CountingCache(PriceBarCache):
    """Counts every ``get`` so a test can say "the cache was not read"."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path=db_path)
        self.gets = 0

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


def _cache(tmp_path: Path) -> _CountingCache:
    return _CountingCache(tmp_path / "cache.db")


def _seed(cache: PriceBarCache, bars: list[PriceBar]) -> None:
    cache.put(bars, source=bars[0].source, fetched_at=datetime(2024, 1, 2, 7, 0, tzinfo=UTC))


def _records(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [
        (r.levelno, r.getMessage())
        for r in caplog.records
        if r.name == SERVICE_LOGGER and r.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)
    ]


def _field(message: str, name: str) -> str:
    return message.split(f" {name}=")[1].split(" ")[0]


TW_DAY = date(2024, 1, 2)
START, END = date(2024, 1, 1), date(2024, 1, 31)


def _tw(currency: str, source: str = "twse", day: date = TW_DAY) -> PriceBar:
    return _bar(day, currency=currency, source=source)


def _us(currency: str, source: str = "yfinance", day: date = TW_DAY) -> PriceBar:
    return _bar(day, currency=currency, source=source, symbol="AAPL", market="US")


# --- The approved constants (C-9, C-29) -----------------------------------------------

RULING_1 = Path(__file__).resolve().parents[4] / (
    "work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md"
)


def _approved_line(number: int) -> str:
    return RULING_1.read_text(encoding="utf-8").splitlines()[number - 1].removeprefix("> ")


@pytest.mark.parametrize(
    ("constant", "line"),
    [
        (UNIT_MISMATCH_REASON_US, 26),
        (UNIT_MISMATCH_REASON_TW, 29),
        (UNIT_MISSING_REASON_US, 32),
        (UNIT_MISSING_REASON_TW, 35),
    ],
)
def test_each_sentence_is_the_approved_wording_verbatim(constant: str, line: int) -> None:
    assert constant == _approved_line(line)
    assert constant.count("{provider}") == 1


def test_the_wording_table_names_each_market_once() -> None:
    assert dict(EQUITY_GATE_WORDING.unit_mismatch) == {
        "US": UNIT_MISMATCH_REASON_US,
        "TW": UNIT_MISMATCH_REASON_TW,
    }
    assert dict(EQUITY_GATE_WORDING.unit_missing) == {
        "US": UNIT_MISSING_REASON_US,
        "TW": UNIT_MISSING_REASON_TW,
    }


# --- C-1 live exit, C-2, C-3 -----------------------------------------------------------


@pytest.mark.parametrize(
    "bars",
    [
        pytest.param([_tw("USD")], id="all-bars"),
        pytest.param(
            [_tw("TWD", day=date(2024, 1, 2)), _tw("USD", day=date(2024, 1, 3))], id="one-bar"
        ),
    ],
)
def test_a_refused_rung_writes_nothing_and_filters_nothing(
    tmp_path: Path, bars: list[PriceBar]
) -> None:
    cache = _cache(tmp_path)
    service = equity_service(primary=_Rung("twse", bars), cache=cache, clock=lambda: NOW)

    result = service.get_daily_bars("2330", "TW", START, END)

    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []  # C-2: not the matching bars either
    assert result.rejection == "unit_mismatch"
    assert result.reason == UNIT_MISMATCH_REASON_TW.format(provider="twse")
    # C-3: nothing cached, no coverage, the attempt recorded as for any declined rung.
    assert cache.get("2330", "TW", START, END) is None
    assert cache.fetch_coverage("2330", "TW") is None
    assert cache.last_attempt_at("2330", "TW") == NOW


def test_a_matching_rung_is_served_as_before(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    service = equity_service(primary=_Rung("twse", [_tw("TWD")]), cache=cache, clock=lambda: NOW)

    result = service.get_daily_bars("2330", "TW", START, END)

    assert result.status is DataStatus.FRESH
    assert [bar.currency for bar in result.bars] == ["TWD"]
    assert result.rejection is None
    assert cache.get("2330", "TW", START, END) is not None


# --- C-13 (3)(4)(5)(10) through load_bars, exact ---------------------------------------


def _load(service: MarketDataService, *, symbol: str, market: Market) -> str | None:
    loaded = load_bars({market: service}, symbol=symbol, market=market, start=START, end=END)
    assert loaded.bars == []
    assert "在指定區間內沒有可用的日線資料" not in (loaded.reason or "")
    assert PROVIDER_REASON_PREFIX not in (loaded.reason or "")
    return loaded.reason


@pytest.mark.parametrize(
    ("market", "symbol", "bar", "source", "expected"),
    [
        pytest.param("US", "AAPL", _us("GBp"), "yfinance", UNIT_MISMATCH_REASON_US, id="US"),
        pytest.param("TW", "2330", _tw("USD"), "finmind", UNIT_MISMATCH_REASON_TW, id="TW"),
    ],
)
def test_c13_3_w_c_alone(
    tmp_path: Path, market: Market, symbol: str, bar: PriceBar, source: str, expected: str
) -> None:
    service = equity_service(primary=_Rung(source, [bar]), cache=_cache(tmp_path))
    assert _load(service, symbol=symbol, market=market) == expected.format(provider=source)


def test_c13_4_w_c_beside_the_alpha_vantage_sentence(tmp_path: Path) -> None:
    service = equity_service(
        primary=_Rung("alpha_vantage", [], reason=AV_QUOTA_REASON),
        backups=[_Rung("yfinance", [_us("GBp")])],
        cache=_cache(tmp_path),
    )
    assert _load(service, symbol="AAPL", market="US") == (
        AV_QUOTA_REASON.removesuffix("。")
        + "。 "
        + UNIT_MISMATCH_REASON_US.format(provider="yfinance")
    )


@pytest.mark.parametrize(
    ("market", "symbol", "bar", "expected"),
    [
        pytest.param("US", "AAPL", _us(""), UNIT_MISSING_REASON_US, id="US-empty"),
        pytest.param("TW", "2330", _tw("  "), UNIT_MISSING_REASON_TW, id="TW-blank"),
    ],
)
def test_c13_5_w_c_prime_alone(
    tmp_path: Path, market: Market, symbol: str, bar: PriceBar, expected: str
) -> None:
    service = equity_service(primary=_Rung("yfinance", [bar]), cache=_cache(tmp_path))
    result = service.get_daily_bars(symbol, market, START, END)
    assert result.rejection == "unit_missing"
    assert _load(service, symbol=symbol, market=market) == expected.format(provider="yfinance")


def test_c13_10_c33_w_c_beside_a_bad_cache_never_reads_it(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    _seed(cache, [_tw("USD", source="finmind", day=date(2024, 1, 1))])
    service = equity_service(primary=_Rung("twse", [_tw("USD")]), cache=cache, clock=lambda: NOW)
    cache.gets = 0

    result = service.get_daily_bars("2330", "TW", START, END)

    assert cache.gets == 0
    assert result.reason == UNIT_MISMATCH_REASON_TW.format(provider="twse")
    assert "本機快取" not in (result.reason or "")


# --- C-11, C-34 (e), F9W-4 (a) ---------------------------------------------------------


def _valuator(service: MarketDataService) -> PositionValuator:
    class _NoFx:
        def get_daily_rates(self, pair: str, start: date, end: date) -> object:
            raise AssertionError("a refused row asks no FX (F9W-18)")

    return PositionValuator(
        market_services={"TW": service, "US": service},
        fx_provider=_NoFx(),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )


def test_c11_w_c_with_a_good_cache_serves_no_cached_row(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    _seed(cache, [_tw("TWD", source="twse", day=date(2024, 1, 1))])
    service = equity_service(primary=_Rung("twse", [_tw("USD")]), cache=cache, clock=lambda: NOW)

    result = service.get_daily_bars("2330", "TW", START, END)
    valued = _valuator(service).value_position(
        Position(
            id=1,
            symbol="2330",
            market="TW",
            quantity=Decimal(1000),
            avg_cost=Decimal(500),
            currency="TWD",
            opened_at=date(2024, 1, 1),
            instrument_type="stock",
            note=None,
            created_at=NOW,
            updated_at=NOW,
        )
    )

    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []
    assert result.rejection == "unit_mismatch"
    assert valued.valuation.missing == [SYMBOL_OR_UNIT_REJECTED]


def test_c34_e_a_w_c_prime_rung_does_not_release_a_w_c(tmp_path: Path) -> None:
    """F9W-33 (c): W-c' may release a passing cache; a W-c anywhere on the call may not."""
    cache = _cache(tmp_path)
    _seed(cache, [_us("USD", source="alpha_vantage", day=date(2024, 1, 1))])
    service = equity_service(
        primary=_Rung("alpha_vantage", [_us("")]),
        backups=[_Rung("yfinance", [_us("GBp")])],
        cache=cache,
        clock=lambda: NOW,
    )

    result = service.get_daily_bars("AAPL", "US", START, END)

    assert result.bars == []
    assert result.rejection == "unit_mismatch"  # D-7 (2): mismatch outranks missing
    assert result.reason == _combine_reasons(
        [
            UNIT_MISSING_REASON_US.format(provider="alpha_vantage"),
            UNIT_MISMATCH_REASON_US.format(provider="yfinance"),
        ]
    )


# --- C-34 (b): W-c' and a passing cache, F9W-33 (a)(b) -----------------------------------


@pytest.mark.parametrize("ladder", ["one-rung", "two-rungs"])
def test_c34_b_w_c_prime_falls_back_to_the_cache_with_the_whole_reason(
    tmp_path: Path, ladder: str
) -> None:
    cache = _cache(tmp_path)
    _seed(cache, [_us("USD", source="alpha_vantage", day=date(2024, 1, 1))])
    refused = _Rung("yfinance", [_us("")])
    if ladder == "one-rung":
        service = equity_service(primary=refused, cache=cache, clock=lambda: NOW)
        layers = [UNIT_MISSING_REASON_US.format(provider="yfinance")]
    else:
        service = equity_service(
            primary=_Rung("alpha_vantage", [], reason=AV_QUOTA_REASON),
            backups=[refused],
            cache=cache,
            clock=lambda: NOW,
        )
        layers = [AV_QUOTA_REASON, UNIT_MISSING_REASON_US.format(provider="yfinance")]

    loaded = load_bars({"US": service}, symbol="AAPL", market="US", start=START, end=END)
    result = service.get_daily_bars("AAPL", "US", START, END)

    assert loaded.reason == _combine_reasons(layers)
    assert loaded.status is DataStatus.CACHED_STALE  # F9W-33 (b)
    assert [bar.currency for bar in loaded.bars] == ["USD"]
    assert result.rejection is None
    assert PROVIDER_REASON_PREFIX not in (loaded.reason or "")


# --- D-2 (2): after a W-c the next rung is asked for the whole range ---------------------


def _incremental_cache(tmp_path: Path) -> _CountingCache:
    cache = _cache(tmp_path)
    cache.put(
        [_tw("TWD", day=date(2023, 11, 30)), _tw("TWD", day=date(2023, 12, 29))],
        source="twse",
        fetched_at=datetime(2023, 12, 29, 8, 0, tzinfo=UTC),
    )
    cache.record_fetch(
        "2330",
        "TW",
        start=date(2023, 11, 1),
        end=date(2023, 12, 29),
        fetched_at=datetime(2023, 12, 29, 8, 0, tzinfo=UTC),
    )
    return cache


def test_after_a_w_c_the_next_rung_is_asked_for_the_whole_range(tmp_path: Path) -> None:
    cache = _incremental_cache(tmp_path)
    tail = [_tw("TWD", source="tpex", day=date(2024, 1, 3))]
    whole = [_tw("TWD", source="tpex", day=date(2023, 11, 30)), *tail]
    primary = _Rung("twse", [_tw("USD", day=date(2024, 1, 3))])
    backup = _Rung("tpex", whole)
    service = equity_service(
        primary=primary, backups=[backup], cache=cache, clock=lambda: NOW, cache_first=True
    )

    result = service.get_daily_bars("2330", "TW", date(2023, 11, 1), END)

    assert primary.asked[0][1] > date(2023, 11, 1)  # the primary was narrowed
    assert backup.asked == [("2330", date(2023, 11, 1), END)]
    assert result.status is DataStatus.BACKUP
    assert result.bars == whole  # the backup's own bars, no cached head read back
    assert result.rejection is None
    assert result.reason == mixed_sources_reason(whole)


def test_after_a_w_c_prime_the_next_rung_keeps_the_narrowed_range(tmp_path: Path) -> None:
    """D-2 (4): W-c' does not trigger D-2 (2)."""
    cache = _incremental_cache(tmp_path)
    primary = _Rung("twse", [_tw("  ", day=date(2024, 1, 3))])
    backup = _Rung("tpex", [_tw("TWD", source="tpex", day=date(2024, 1, 3))])
    service = equity_service(
        primary=primary, backups=[backup], cache=cache, clock=lambda: NOW, cache_first=True
    )

    result = service.get_daily_bars("2330", "TW", date(2023, 11, 1), END)

    assert backup.asked[0][1] == primary.asked[0][1] > date(2023, 11, 1)
    assert result.status is DataStatus.BACKUP
    assert result.rejection is None


def test_on_the_index_path_a_w_c_prime_also_asks_the_next_rung_for_the_whole_range(
    tmp_path: Path,
) -> None:
    """D-4: D-2 (2) holds for the index service, mismatch and missing alike."""
    cache = _incremental_cache(tmp_path)
    primary = _Rung("yfinance", [_tw("  ", day=date(2024, 1, 3))])
    whole = [
        _tw("TWD", source="yahoo", day=date(2023, 11, 30)),
        _tw("TWD", source="yahoo", day=date(2024, 1, 3)),
    ]
    backup = _Rung("yahoo", whole)
    service = build_service(
        primary=primary,
        backups=[backup],
        cache=cache,
        scope="index",
        clock=lambda: NOW,
        cache_first=True,
    )

    result = service.get_daily_bars("2330", "TW", date(2023, 11, 1), END)

    assert primary.asked[0][1] > date(2023, 11, 1)  # the primary was narrowed
    assert backup.asked == [("2330", date(2023, 11, 1), END)]
    assert result.bars == whole  # the backup's own bars, no cached head read back
    assert result.rejection is None


# --- C-14: {provider} is source_id or nothing --------------------------------------------


def test_c14_a_rung_without_a_source_id_states_no_w_c(tmp_path: Path) -> None:
    service = equity_service(primary=_NamelessRung([_tw("USD")]), cache=_cache(tmp_path))

    result = service.get_daily_bars("2330", "TW", START, END)

    assert result.bars == []
    assert result.rejection == "unit_mismatch"
    for template in (
        *EQUITY_GATE_WORDING.unit_mismatch.values(),
        *EQUITY_GATE_WORDING.unit_missing.values(),
    ):
        assert template.split("{provider}")[1] not in (result.reason or "")


# --- qa-reviewer non-blocking (1): every equity refusal states a sentence -----------------


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda: [_Rung("twse", [_tw("USD")])], id="W-c"),
        pytest.param(lambda: [_Rung("twse", [_tw(" ")])], id="W-c'"),
        pytest.param(
            lambda: [_Rung("twse", [], reason="來源暫不可用。"), _Rung("tpex", [_tw("JPY")])],
            id="W-c+other",
        ),
    ],
)
def test_every_equity_refusal_carries_a_non_blank_reason(
    tmp_path: Path, make: Callable[[], list[_Rung]]
) -> None:
    rungs = make()
    service = equity_service(primary=rungs[0], backups=rungs[1:], cache=_cache(tmp_path))
    result = service.get_daily_bars("2330", "TW", START, END)
    assert result.rejection is not None
    assert result.reason is not None and result.reason.strip()


# --- C-35 (b) and the live checkpoint of (c); F9W-39 --------------------------------------


@pytest.mark.parametrize("value", [None, "", "  "])
@pytest.mark.parametrize("missing_market", ["TW", "US"])
def test_c35_b_a_lookup_without_every_market_is_refused_at_construction(
    tmp_path: Path, value: str | None, missing_market: Market
) -> None:
    def lookup(market: Market) -> str | None:
        return value if market == missing_market else MARKET_CURRENCY[market]

    with pytest.raises(ValueError, match=missing_market):
        build_service(
            primary=_Rung("twse", []),
            cache=PriceBarCache(db_path=tmp_path / "c.db"),
            scope="equity",
            currency_for_market=lookup,
        )


class _FlipLookup:
    """Answers at construction, then forgets the market (C-35 (c))."""

    def __init__(self) -> None:
        self.forget = False

    def __call__(self, market: Market) -> str | None:
        return None if self.forget else MARKET_CURRENCY[market]


@pytest.mark.parametrize("scope", ["equity", "index"])
def test_c35_c_a_lookup_that_forgets_raises_at_the_live_checkpoint(
    tmp_path: Path, scope: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache(tmp_path)
    lookup = _FlipLookup()
    service = build_service(
        primary=_Rung("twse", [_tw("TWD")]),
        cache=cache,
        scope=scope,  # type: ignore[arg-type]
        currency_for_market=lookup,
        clock=lambda: NOW,
    )
    fetches: list[object] = []
    monkeypatch.setattr(cache, "record_fetch", lambda *a, **k: fetches.append(a))
    lookup.forget = True

    with pytest.raises(CurrencyLookupError):
        service.get_daily_bars("2330", "TW", START, END)
    with pytest.raises(CurrencyLookupError):
        load_bars({"TW": service}, symbol="2330", market="TW", start=START, end=END)
    assert cache.get("2330", "TW", START, END) is None
    assert fetches == []


# --- D-4 index live refusal (TA6 R-72), F9W-38 (b) ------------------------------------------


class _IndexSource:
    def __init__(self, currency: str) -> None:
        self.currency = currency
        self.asked = 0

    def get_index_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.asked += 1
        bar = _bar(
            date(2024, 1, 2), currency=self.currency, source="yfinance", symbol=symbol, market="US"
        )
        return ProviderResult(
            bars=[bar], status=DataStatus.BACKUP, as_of=NOW, source="yfinance", staleness_minutes=0
        )


class _Recording:
    """Keeps every answer the wrapped service gave, so a test can see the raw one."""

    def __init__(self, inner: MarketDataService) -> None:
        self._inner = inner
        self.answers: list[ProviderResult] = []

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        answer = self._inner.get_daily_bars(symbol, market, start, end)
        self.answers.append(answer)
        return answer

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        return self._inner.get_cached_bars(symbol, market, start, end)


def _benchmark_exit(
    resolver: IndexServiceResolver, start: date, end: date
) -> tuple[str, LoadedBenchmark | LoadedIndexBars]:
    loaded = load_market_benchmark(resolver, market="US", start=start, end=end)
    return MARKET_BENCHMARK["US"].series_symbol, loaded


def _index_exit(
    resolver: IndexServiceResolver, start: date, end: date
) -> tuple[str, LoadedBenchmark | LoadedIndexBars]:
    loaded = load_index_bars(resolver, etf_symbol="TQQQ", start=start, end=end)
    ref = lookup_index_ref("TQQQ")
    assert ref is not None and ref.series_symbol is not None
    return ref.series_symbol, loaded


def _series_of(exit_name: str) -> str:
    if exit_name == "benchmark":
        return MARKET_BENCHMARK["US"].series_symbol
    ref = lookup_index_ref("TQQQ")
    assert ref is not None and ref.series_symbol is not None and ref.series_market == "US"
    return ref.series_symbol


@pytest.mark.parametrize("exit_name", ["benchmark", "index"])
@pytest.mark.parametrize(("declared", "category"), [("TWD", "unit_mismatch"), ("", "unit_missing")])
def test_index_live_refusal_and_the_next_call_inside_the_cooldown(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    declared: str,
    category: str,
    exit_name: str,
) -> None:
    """TA6 R-72 and 風控 F9W-38 (b) (1)(2), through both ``index.py`` exits."""
    series = _series_of(exit_name)
    cache = _cache(tmp_path)
    # A passing cached row, old enough that layer 0 falls through to the ladder.
    cached_row = _bar(
        date(2023, 12, 1), currency="USD", source="yfinance", symbol=series, market="US"
    )
    cache.put([cached_row], source="yfinance", fetched_at=datetime(2023, 12, 1, 22, tzinfo=UTC))
    cache.record_fetch(
        series,
        "US",
        start=date(2023, 11, 1),
        end=date(2023, 12, 1),
        fetched_at=datetime(2023, 12, 1, 22, tzinfo=UTC),
    )
    source = _IndexSource(declared)
    clock = {"now": NOW}
    service = index_service(
        primary=IndexProviderBridge(source),
        cache=cache,
        clock=lambda: clock["now"],
        cache_first=True,
    )
    recording = _Recording(service)
    resolver: IndexServiceResolver = {"US": IndexSeriesService(recording)}
    start, end = date(2023, 11, 1), date(2024, 1, 2)
    load = _benchmark_exit if exit_name == "benchmark" else _index_exit

    # (1) the first call, through index.py.
    with caplog.at_level(logging.INFO, logger=SERVICE_LOGGER):
        _symbol, first = load(resolver, start, end)
    [raw] = recording.answers
    assert raw.bars == []
    assert raw.rejection == category
    assert raw.reason is None  # no other rung, and no sentence of the index path's own
    records = _records(caplog)
    assert [(level, _field(m, "layer"), _field(m, "scope")) for level, m in records] == [
        (logging.ERROR, "provider", "index")
    ]
    assert first.bars == [] and not first.available
    # The accepted residual sentence, verbatim (F9W-31, F9W-32): no new wording.
    assert first.reason == NO_BARS_REASON.format(series_symbol=series)
    published = json.dumps(first.meta(), ensure_ascii=False, default=str)
    assert "rejection" not in published
    assert SYMBOL_OR_UNIT_REJECTED not in published
    assert "代號或價格單位不採用" not in published
    # The refused live row never reached the cache.
    read = cache.get(series, "US", start, end)
    assert read is not None and [bar.date for bar in read.bars] == [date(2023, 12, 1)]

    # (2) the next call inside the cooldown: the cache through R-8, no new record.
    asked_before = source.asked
    caplog.clear()
    clock["now"] = NOW + timedelta(minutes=5)
    with caplog.at_level(logging.INFO, logger=SERVICE_LOGGER):
        _symbol, second = load(resolver, start, end)
    answer = recording.answers[-1]
    assert source.asked == asked_before
    assert [bar.date for bar in answer.bars] == [date(2023, 12, 1)]
    assert answer.reason == RECENT_ATTEMPT_FAILED_REASON
    assert answer.rejection is None
    assert second.reason == RECENT_ATTEMPT_FAILED_REASON
    assert _records(caplog) == []


def test_the_index_path_never_refers_to_the_gate_wording() -> None:
    """C-17 (grep half), F9W-9: no equity sentence on the index path."""
    root = Path(__file__).resolve().parents[1] / "app"
    text = (root / "services" / "index.py").read_text(encoding="utf-8")
    for name in (
        "gate_wording",
        "UNIT_MISMATCH_REASON",
        "UNIT_MISSING_REASON",
        "EQUITY_GATE_WORDING",
    ):
        assert name not in text
