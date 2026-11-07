"""Real cache_first ladders for the N-190 tests (ADR-0040 QB-7).

Everything between ``/today`` and the live source is production code: the
``PlaybookService`` and ``PlaybookStore``, both ``MarketDataService`` ladders
(``cache_first``, admission, gate wording and currency lookup, built through
:func:`tests.market_service_helpers.equity_service` / ``index_service``), the
``IndexSeriesService`` facade, one shared tmp ``PriceBarCache`` and the session
freshness policy. Only three things are stand-ins:

* the two live sources (:class:`FakeLive`) -- TWSE and the yfinance index feed
  -- whose ``available_through`` is "the last day the exchange has published";
* the clock, a fixed Asia/Taipei wall time set per step (:meth:`Rig.at`);
* what ``app.scheduler`` iterates (the position book) and ``date.today()`` in
  the two route modules, so the real ``refresh_market_data``, ``get_bars`` and
  ``get_signals`` run on the same ladders (:meth:`Rig.patch_consumers`).

Ported from the qa-automation probes ``test_n190.py`` and
``test_n190_sched.py`` (``[qa-1104]``, ``[qa-1105]``); no ``FakePriceService``.
Every database lives under ``tmp_path``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import pytest

import app.api.bars as bars_api
import app.api.signals as signals_api
import app.scheduler as scheduler
from app.data.cache import PriceBarCache
from app.data.interface import DataStatus, Market, MarketDataProvider, PriceBar, ProviderResult
from app.data.service import MarketDataService
from app.playbook.models import Directive, FastMarketState, PlaybookEvaluation, SettlementResult
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from app.services.index import IndexSeriesService
from tests.exit_idempotency_helpers import hold
from tests.market_service_helpers import equity_service, index_service
from tests.playbook_helpers import confirm_rule_set

TPE = ZoneInfo("Asia/Taipei")
_AS_OF = datetime(2026, 1, 1, tzinfo=UTC)

WED_BEFORE = date(2026, 8, 5)
MON = date(2026, 8, 10)
TUE = date(2026, 8, 11)  # 排程日
WED = date(2026, 8, 12)
THU = date(2026, 8, 13)  # 排程日
FRI = date(2026, 8, 14)
NEXT_MON = date(2026, 8, 17)
NEXT_TUE = date(2026, 8, 18)
NEXT_WED = date(2026, 8, 19)

#: Cost of every batch :func:`tests.exit_idempotency_helpers.hold` opens.
COST = Decimal("100")
#: A close that meets S1 (< 0.90 × cost) and nothing above it (S2 is 0.85).
S1_CLOSE = "88"
#: A close that meets no S/P rule at all.
QUIET_CLOSE = "100"

PriceFn = Callable[[str, date], Decimal]


def weekdays(start: date, last: date, holidays: frozenset[date] = frozenset()) -> list[date]:
    """Every Monday-Friday in ``[start, last]`` that is not in ``holidays``."""
    days: list[date] = []
    day = start
    while day <= last:
        if day.weekday() < 5 and day not in holidays:
            days.append(day)
        day += timedelta(days=1)
    return days


def flat(prices: dict[str, str]) -> PriceFn:
    """One constant close per symbol."""
    return lambda symbol, _day: Decimal(prices[symbol])


class FakeLive(MarketDataProvider):
    """A live source that has published every weekday up to ``available_through``."""

    source_id: ClassVar[str] = "live"

    def __init__(self, price: PriceFn, *, currency: str = "TWD") -> None:
        self.price = price
        self.currency = currency
        self.available_through = date(2026, 1, 1)
        self.holidays: frozenset[date] = frozenset()
        #: ADR-0009 R-8: the source is down; every call answers nothing.
        self.failing = False
        self.calls: list[tuple[str, date, date]] = []

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.calls.append((symbol, start, end))
        if self.failing:
            return ProviderResult(
                bars=[], status=DataStatus.UNAVAILABLE, as_of=_AS_OF, source=self.source_id
            )
        days = weekdays(start, min(end, self.available_through), self.holidays)
        bars = [
            PriceBar(
                symbol=symbol,
                market="TW",
                date=day,
                open=self.price(symbol, day),
                high=self.price(symbol, day),
                low=self.price(symbol, day),
                close=self.price(symbol, day),
                volume=1000,
                currency=self.currency,
                as_of=_AS_OF,
                source=self.source_id,
            )
            for day in days
        ]
        return ProviderResult(
            bars=bars,
            status=DataStatus.FRESH,
            as_of=_AS_OF,
            source=self.source_id,
            staleness_minutes=0,
            complete=True,
        )

    def calls_for(self, symbol: str) -> int:
        return sum(1 for called, _, _ in self.calls if called == symbol)


class TwseLive(FakeLive):
    source_id: ClassVar[str] = "twse"


class IndexLive(FakeLive):
    source_id: ClassVar[str] = "yfinance"


@dataclass(frozen=True)
class Load:
    """One ladder answer as a consumer received it."""

    tag: str
    symbol: str
    span_days: int
    status: str
    is_within_ttl: bool | None
    source: str
    last_bar: date | None
    live_calls: int


class SpyLadder:
    """A ``PriceService`` that records every answer of the ladder it wraps."""

    def __init__(
        self, inner: MarketDataService | IndexSeriesService, live: FakeLive, rig: Rig
    ) -> None:
        self.inner = inner
        self.live = live
        self.rig = rig

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        before = len(self.live.calls)
        result = self.inner.get_daily_bars(symbol, market, start, end)
        self.rig.loads.append(
            Load(
                tag=self.rig.tag,
                symbol=symbol,
                span_days=(end - start).days,
                status=result.status.value,
                is_within_ttl=result.is_within_ttl,
                source=result.source,
                last_bar=max((bar.date for bar in result.bars), default=None),
                live_calls=len(self.live.calls) - before,
            )
        )
        return result

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        return self.inner.get_cached_bars(symbol, market, start, end)


@dataclass
class Rig:
    store: PlaybookStore
    cache: PriceBarCache
    live: FakeLive
    index_live: FakeLive
    now: datetime = datetime(2026, 8, 10, 18, tzinfo=TPE)
    tag: str = "-"
    loads: list[Load] = field(default_factory=list)
    #: What ``app.scheduler.refresh_market_data`` sees in the position book.
    positions: list[str] = field(default_factory=list)
    equity: SpyLadder | None = None
    index: SpyLadder | None = None
    service: PlaybookService | None = None

    # --- wiring ------------------------------------------------------------------------

    @property
    def desk(self) -> PlaybookService:
        assert self.service is not None
        return self.service

    @property
    def equity_ladder(self) -> SpyLadder:
        assert self.equity is not None
        return self.equity

    @property
    def index_ladder(self) -> SpyLadder:
        assert self.index is not None
        return self.index

    def patch_consumers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Point the scheduler and the two route modules at this rig."""
        equity, index = self.equity_ladder, self.index_ladder
        monkeypatch.setattr(scheduler, "get_market_resolver", lambda: {"TW": equity, "US": equity})
        monkeypatch.setattr(scheduler, "get_index_resolver", lambda: {"TW": index, "US": index})
        monkeypatch.setattr(
            scheduler,
            "get_position_store",
            lambda: SimpleNamespace(
                list_all=lambda: [
                    SimpleNamespace(symbol=symbol, market="TW") for symbol in self.positions
                ]
            ),
        )
        rig = self

        class _Today(date):
            @classmethod
            def today(cls) -> _Today:
                day = rig.now.date()
                return cls(day.year, day.month, day.day)

        monkeypatch.setattr(bars_api, "date", _Today)
        monkeypatch.setattr(signals_api, "date", _Today)

    # --- the clock and the exchange --------------------------------------------------------

    def at(self, day: date, hh: int, mm: int = 0, *, published: date | None = None) -> None:
        """Set the clock; by default TWSE has published ``day`` once it is 15:00."""
        self.now = datetime.combine(day, time(hh, mm), tzinfo=TPE)
        through = day if hh >= 15 else day - timedelta(days=1)
        self.live.available_through = published or through
        self.index_live.available_through = published or through

    # --- consumers ----------------------------------------------------------------------

    def today(
        self, day: date, hh: int, mm: int = 0, *, published: date | None = None
    ) -> PlaybookEvaluation:
        self.at(day, hh, mm, published=published)
        self.tag = f"today {day} {hh:02d}:{mm:02d}"
        return self.desk.evaluate_today(today=day)

    def scheduler_refresh(
        self, day: date, hh: int, mm: int = 0, *, published: date | None = None
    ) -> int:
        self.at(day, hh, mm, published=published)
        self.tag = f"scheduler {day} {hh:02d}:{mm:02d}"
        return scheduler.refresh_market_data(today=day)

    def bars_page(self, symbol: str, day: date, hh: int, mm: int = 0) -> Any:
        self.at(day, hh, mm)
        self.tag = f"bars {symbol}"
        return bars_api.get_bars(symbol, {"TW": self.equity_ladder}, "TW", 540)

    def signals_page(
        self, symbol: str, day: date, hh: int, mm: int = 0, *, published: date | None = None
    ) -> Any:
        self.at(day, hh, mm, published=published)
        self.tag = f"signals {symbol}"
        index = self.index_ladder
        return signals_api.get_signals(
            symbol,
            {"TW": self.equity_ladder},
            {"TW": index, "US": index},
            "TW",
            signals_api.DEFAULT_LOOKBACK_DAYS,
        )

    def sector_reference(self, day: date, hh: int, window_days: int) -> float | None:
        self.at(day, hh)
        self.tag = f"sector {window_days}d"
        return scheduler.taiex_reference_return(day - timedelta(days=window_days), day)

    def prime(self, *, index: bool = True) -> None:
        """Monday evening: the real scheduler warmed every position, the index was read once."""
        self.scheduler_refresh(MON, 18, 30)
        if index:
            self.tag = "prime index"
            self.desk._load_index_bars(today=MON)
        self.forget()

    def warm(self, symbols: list[str], day: date, hh: int = 17) -> None:
        """An earlier visit on ``day`` (after the cutoff): the cache holds ``day``'s bars."""
        self.at(day, hh)
        self.tag = "warm"
        self.desk._load_symbol_bars(symbols, today=day)
        self.desk._load_index_bars(today=day)
        self.forget()

    def forget(self) -> None:
        """Drop what was recorded so far; the cache and the logs stay."""
        self.loads.clear()
        self.live.calls.clear()
        self.index_live.calls.clear()

    # --- what came back -------------------------------------------------------------------

    def loads_of(self, symbol: str, tag: str | None = None) -> list[Load]:
        return [
            load
            for load in self.loads
            if load.symbol == symbol and (tag is None or load.tag == tag)
        ]

    def last_load(self, symbol: str) -> Load:
        return self.loads_of(symbol)[-1]


def build(
    tmp_path: Path,
    prices: dict[str, str] | PriceFn,
    *,
    index_price: PriceFn | None = None,
    holidays: frozenset[date] = frozenset(),
) -> Rig:
    """A rig on ``tmp_path`` with the user's rule set confirmed and nothing loaded yet."""
    cache = PriceBarCache(db_path=tmp_path / "cache.db")
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    confirm_rule_set(store)
    live = TwseLive(flat(prices) if isinstance(prices, dict) else prices)
    live.holidays = holidays
    index_live = IndexLive(index_price or (lambda _symbol, _day: Decimal("20000")))
    index_live.holidays = holidays
    rig = Rig(store=store, cache=cache, live=live, index_live=index_live)

    def clock() -> datetime:
        return rig.now

    rig.equity = SpyLadder(
        equity_service(primary=live, cache=cache, cache_first=True, clock=clock), live, rig
    )
    rig.index = SpyLadder(
        IndexSeriesService(
            index_service(primary=index_live, cache=cache, cache_first=True, clock=clock)
        ),
        index_live,
        rig,
    )
    rig.service = PlaybookService(
        store=store,
        market_resolver={"TW": rig.equity},
        index_resolver={"TW": rig.index, "US": rig.index},
    )
    return rig


def hold_shares(rig: Rig, symbol: str, *batch_nos: int, shares: int = 100) -> None:
    for batch_no in batch_nos:
        hold(rig.store, symbol, batch_no, shares=shares)


def pending_sell(
    symbol: str,
    batch_no: int | None,
    *,
    rule_id: str = "S1",
    data_date: date,
    execution_date: date,
    shares: int = 100,
) -> Directive:
    return Directive(
        symbol=symbol,
        batch_no=batch_no,
        action="sell",
        shares=shares,
        rule_id=rule_id,  # type: ignore[arg-type]
        rule_summary="seed",
        data_date=data_date,
        execution_date=execution_date,
        reference_price=None,
        limit_low=None,
        limit_high=None,
        limit_note="",
        data_status="fresh",
        source="twse",
    )


def seed_pending(store: PlaybookStore, line: Directive) -> None:
    """Log ``line`` as an earlier evaluation would have, still awaiting its T+1."""
    store.record_directives(
        PlaybookEvaluation(
            data_date=line.data_date,
            execution_date=line.execution_date,
            mode="normal",
            mode_reason="seed",
            is_schedule_day=True,
            fast_market=FastMarketState(
                active=False, annualized_vol_20d=None, large_move_days=0, reason=None
            ),
            rules_version=1,
            params=store.active_params(line.data_date),
            directives=[line],
            effects=[],
            warnings=[],
            snapshot=[],
        )
    )


def settlement_of(evaluation: PlaybookEvaluation) -> SettlementResult:
    """The settlement of an authored ``/today`` -- never ``None`` there."""
    assert evaluation.settlement is not None
    return evaluation.settlement


def sells_of(evaluation: PlaybookEvaluation, symbol: str) -> list[tuple[int | None, str]]:
    return [
        (line.batch_no, line.rule_id)
        for line in evaluation.directives
        if line.symbol == symbol and line.action == "sell"
    ]
