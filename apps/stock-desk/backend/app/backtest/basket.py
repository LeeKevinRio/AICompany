"""Generic point-in-time multi-asset basket backtester (ADR-0012 D-13, Options G1).

The engine does not know what a sector is (C-4: it may not import
``app.sectors``). It takes a *decision rule* -- a :data:`BasketStrategy` that
maps a :class:`~app.data.panel.PointInTimePanel` to target weights -- plus a
benchmark rule of the same shape, and turns every scheduled decision into one
non-overlapping sample.

Timing (methodology §5.1, the single version):

* decision at the close of ``t``: the strategy is handed ``panel.as_of(t)``
  and nothing else, so every input it can read was knowable at ``cutoff(t)``;
* entry at the **open of t+1**, the basket fixed to the decision of ``t``;
* a name whose t+1 open is at or above ``reference x 1.095`` could not have
  been bought (limit-up at the open) and is dropped from the basket; the
  reference is ``close - change`` of t+1 or, without ``change``, the previous
  close (flagged ``reference_fallback`` for disclosure);
* exit at the **close of t+H**; the next decision is at that same close, so
  samples never overlap (:class:`BasketSchedule` refuses overlapping dates);
* the basket pays one full round trip per sample (:func:`round_trip_cost`,
  from :class:`~app.backtest.costs.CostModel`, never a local rate); the
  benchmark is a comparator and is **never charged** (ADR-0012 D-9).

The benchmark goes through the very same execution rules (limit-up at the
open, dividend restoration) so both sides are measured the same way
(methodology §5.7 「同一種算法」); only the cost differs.

Results side: labels read prices after ``t`` through :class:`PriceBook`, which
is built from the whole panel and is never handed to a strategy. Together with
``basket.py``'s sibling ``sector_eval.py`` this is the only place in the
application that computes forward returns, excess returns or cost deductions
(ADR-0012 C-15; ``tests/test_c15_identifiers.py`` enforces it).

Dividend restoration is injected (:data:`AdjustmentFactor`): the engine
multiplies a holding return by whatever factor the caller supplies for events
inside the holding window. ``sector_eval`` supplies point-in-time factors; the
engine itself has no opinion about where they come from.

A diagnostic close(t) -> close(t+H) excess is computed beside every sample.
It is **not** a decision input (methodology §5.1): an edge that only shows up
there is an overnight gap the user could not have captured.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from types import MappingProxyType
from typing import Final, Literal

import numpy as np
import pandas as pd

from app.backtest.costs import CostModel
from app.backtest.engine import BacktestResult, Trade
from app.backtest.report import SegmentReport, build_segment_report
from app.data.panel import TAIPEI, MarketPanel, PointInTimePanel
from app.positions.models import InstrumentType, Market

#: Decides on a point-in-time view; returns target weights by symbol (may be empty).
BasketStrategy = Callable[[PointInTimePanel], Mapping[str, float]]

#: ``(symbol, after, through) -> factor`` for every event with an ex-date in
#: ``(after, through]``: the product of multiplicative restoration factors,
#: ``1.0`` when there is no event, ``None`` when an event has no usable factor.
AdjustmentFactor = Callable[[str, date, date], float | None]

OutcomeStatus = Literal[
    "held",
    "limit_up_open",
    "no_entry_price",
    "no_reference_price",
    "label_factor_unavailable",
]
SampleStatus = Literal["ok", "bars_gap", "empty_basket", "all_excluded", "empty_benchmark"]

#: Machine-readable disclosure codes (never user-facing text).
DISCLOSURE_REFERENCE_FALLBACK: Final = "reference_price_fallback_previous_close"
DISCLOSURE_EXIT_CARRIED: Final = "exit_price_carried_last_close"
DISCLOSURE_COST_UNVERIFIED: Final = "cost_model_unverified"
DISCLOSURE_BENCHMARK_COLUMN: Final = "buy_and_hold_column_is_equal_weight_benchmark"


def round_trip_cost(
    cost_model: CostModel, *, market: Market, instrument_type: InstrumentType
) -> float:
    """One full round trip (buy + sell) as a fraction of the entry notional.

    Read off :class:`CostModel` for a unit notional, so a rate is never
    written down twice; with the unverified defaults this is ~0.585%.
    """
    buy = cost_model.trade_cost(
        notional=1.0, side="buy", market=market, instrument_type=instrument_type
    )
    sell = cost_model.trade_cost(
        notional=1.0, side="sell", market=market, instrument_type=instrument_type
    )
    return buy + sell


@dataclass(frozen=True)
class BasketExecution:
    """Fill rules shared by the basket and its benchmark."""

    #: t+1 open >= reference x factor counts as not buyable (methodology §5.1).
    open_limit_up_factor: float = 1.095
    market: Market = "TW"
    instrument_type: InstrumentType = "stock"
    #: Restoration factors for ex-dates inside a holding window; ``None`` = raw prices.
    adjustment: AdjustmentFactor | None = None
    #: Starting equity of the synthetic run the standard report is built from.
    initial_equity: float = 1_000_000.0

    def __post_init__(self) -> None:
        if self.open_limit_up_factor <= 1.0:
            raise ValueError("open_limit_up_factor must exceed 1")
        if self.initial_equity <= 0.0:
            raise ValueError("initial_equity must be positive")


@dataclass(frozen=True)
class HoldingWindow:
    """One sample's dates: decide at ``decision_date`` close, hold ``entry``..``exit``."""

    decision_date: date
    entry_date: date
    exit_date: date
    #: Every calendar session from entry to exit, inclusive.
    sessions: tuple[date, ...]


@dataclass(frozen=True)
class BasketSchedule:
    """Decision dates on a trading calendar, ``holding_days`` apart at least.

    ``calendar`` is the trading calendar holding periods are counted on. A
    calendar session without bars is not silently skipped: the sample that
    spans it is reported as ``bars_gap`` (ADR-0012 D-2: a missed day is not
    back-filled).
    """

    decision_dates: tuple[date, ...]
    holding_days: int
    calendar: tuple[date, ...]

    def __post_init__(self) -> None:
        if self.holding_days < 1:
            raise ValueError("holding_days must be positive")
        if list(self.calendar) != sorted(set(self.calendar)):
            raise ValueError("calendar must be strictly increasing")
        positions = [self._position(day) for day in self.decision_dates]
        for earlier, later in zip(positions, positions[1:], strict=False):
            if later - earlier < self.holding_days:
                raise ValueError(
                    "decision dates overlap: the next decision must be at or after t+H "
                    "(methodology §5.1, non-overlapping samples)"
                )

    def _position(self, day: date) -> int:
        position = bisect_left(self.calendar, day)
        if position == len(self.calendar) or self.calendar[position] != day:
            raise ValueError(f"decision date {day.isoformat()} is not a calendar session")
        return position

    @classmethod
    def every_holding_period(
        cls,
        calendar: Sequence[date],
        *,
        holding_days: int,
        start: date,
        phase: int = 0,
        end: date | None = None,
    ) -> BasketSchedule:
        """``start``'s first session plus ``phase``, then every ``holding_days`` sessions.

        The grid is fixed by the calendar alone -- never by the data or by an
        outcome -- so a missing board skips one sample without shifting the rest.
        Only decisions whose exit session exists on the calendar are kept.
        """
        days = tuple(sorted(set(calendar)))
        first = bisect_left(days, start) + phase
        last_exit = len(days) - 1 if end is None else bisect_right(days, end) - 1
        decisions: list[date] = []
        position = first
        while position + holding_days <= last_exit:
            decisions.append(days[position])
            position += holding_days
        return cls(decision_dates=tuple(decisions), holding_days=holding_days, calendar=days)

    def window(self, decision_date: date) -> HoldingWindow | None:
        """The holding window of ``decision_date``; ``None`` past the calendar's end."""
        position = self._position(decision_date)
        if position + self.holding_days >= len(self.calendar):
            return None
        sessions = self.calendar[position + 1 : position + self.holding_days + 1]
        return HoldingWindow(
            decision_date=decision_date,
            entry_date=sessions[0],
            exit_date=sessions[-1],
            sessions=tuple(sessions),
        )


def _local_date(stamp: pd.Timestamp) -> date:
    local = stamp.tz_convert(TAIPEI) if stamp.tzinfo is not None else stamp
    return local.date()


@dataclass(frozen=True)
class PriceBook:
    """Results-side prices of the whole panel: ``sessions x symbols`` open/close/change.

    Built from ``panel.as_of(horizon)`` where the horizon is the latest date
    any run describes or was recorded on, so a label may read corrections
    written after the decision (ADR-0012 D-2: labels are the results side) and
    bars are resolved by exactly the rule the decision views use. It is never
    handed to a strategy.
    """

    sessions: tuple[date, ...]
    symbols: tuple[str, ...]
    open: np.ndarray
    close: np.ndarray
    change: np.ndarray

    @classmethod
    def from_panel(cls, panel: MarketPanel) -> PriceBook:
        runs = panel.frames.runs
        if runs.empty:
            empty = np.empty((0, 0), dtype="float64")
            return cls(sessions=(), symbols=(), open=empty, close=empty, change=empty)
        horizon = max(
            max(runs["session_date"]),
            max(_local_date(stamp) for stamp in runs["recorded_at"]),
        )
        view = panel.as_of(horizon)
        sessions = view.sessions
        bars = view.bars(sessions[0], sessions[-1]) if sessions else None
        symbols = tuple(sorted(set(bars["symbol"]))) if bars is not None else ()

        def matrix(field: str) -> np.ndarray:
            if not sessions:
                return np.empty((0, 0), dtype="float64")
            return view.field_matrix(field, sessions, symbols).to_numpy(dtype="float64")

        return cls(
            sessions=sessions,
            symbols=symbols,
            open=matrix("open"),
            close=matrix("close"),
            change=matrix("change"),
        )

    def row(self, day: date) -> int | None:
        position = bisect_left(self.sessions, day)
        if position < len(self.sessions) and self.sessions[position] == day:
            return position
        return None

    def column(self, symbol: str) -> int | None:
        position = bisect_left(self.symbols, symbol)
        if position < len(self.symbols) and self.symbols[position] == symbol:
            return position
        return None

    def has_sessions(self, days: Sequence[date]) -> bool:
        return all(self.row(day) is not None for day in days)

    def last_close(self, symbol: str, *, since: date, through: date) -> tuple[float, date] | None:
        """The last positive close of ``symbol`` in ``[since, through]`` and its session."""
        column = self.column(symbol)
        if column is None:
            return None
        start = bisect_left(self.sessions, since)
        stop = bisect_right(self.sessions, through)
        for row in range(stop - 1, start - 1, -1):
            value = float(self.close[row, column])
            if math.isfinite(value) and value > 0.0:
                return value, self.sessions[row]
        return None

    def value(self, matrix: np.ndarray, symbol: str, day: date) -> float:
        row, column = self.row(day), self.column(symbol)
        if row is None or column is None:
            return math.nan
        return float(matrix[row, column])


@dataclass(frozen=True)
class HoldingOutcome:
    """What holding one name through one window returned (results side)."""

    symbol: str
    status: OutcomeStatus
    entry_price: float | None
    reference_price: float | None
    reference_fallback: bool
    exit_price: float | None
    exit_carried: bool
    adjustment: float | None
    #: open(entry) -> close(exit) x adjustment - 1; None unless ``status == "held"``.
    forward_return: float | None
    #: Diagnostic close(t) -> close(exit) x adjustment(t, exit) - 1; not a decision input.
    close_to_close_return: float | None


def _adjust(execution: BasketExecution, symbol: str, after: date, through: date) -> float | None:
    if execution.adjustment is None:
        return 1.0
    return execution.adjustment(symbol, after, through)


def holding_outcome(
    book: PriceBook, window: HoldingWindow, symbol: str, execution: BasketExecution
) -> HoldingOutcome:
    """Enter at the t+1 open, exit at the t+H close, restore dividends in between."""
    entry = book.value(book.open, symbol, window.entry_date)
    close_entry = book.value(book.close, symbol, window.entry_date)
    change_entry = book.value(book.change, symbol, window.entry_date)

    reference: float | None = None
    fallback = False
    if math.isfinite(close_entry) and math.isfinite(change_entry):
        candidate = close_entry - change_entry
        reference = candidate if candidate > 0.0 else None
    if reference is None:
        previous = book.last_close(symbol, since=date.min, through=window.decision_date)
        if previous is not None:
            reference, fallback = previous[0], True

    exit_mark = book.last_close(symbol, since=window.entry_date, through=window.exit_date)
    carried = exit_mark is None or exit_mark[1] != window.exit_date
    decision_close = book.value(book.close, symbol, window.decision_date)

    diagnostic: float | None = None
    diag_mark = book.last_close(symbol, since=window.decision_date, through=window.exit_date)
    diag_factor = _adjust(execution, symbol, window.decision_date, window.exit_date)
    if (
        math.isfinite(decision_close)
        and decision_close > 0.0
        and diag_mark is not None
        and diag_factor is not None
    ):
        diagnostic = diag_mark[0] / decision_close * diag_factor - 1.0

    not_held = HoldingOutcome(
        symbol=symbol,
        status="no_entry_price",
        entry_price=entry if math.isfinite(entry) else None,
        reference_price=reference,
        reference_fallback=fallback,
        exit_price=exit_mark[0] if exit_mark is not None else None,
        exit_carried=carried,
        adjustment=None,
        forward_return=None,
        close_to_close_return=diagnostic,
    )
    if not math.isfinite(entry) or entry <= 0.0:
        return not_held
    if reference is None:
        return replace(not_held, status="no_reference_price")
    if entry >= reference * execution.open_limit_up_factor:
        return replace(not_held, status="limit_up_open")
    factor = _adjust(execution, symbol, window.entry_date, window.exit_date)
    if factor is None:
        return replace(not_held, status="label_factor_unavailable")
    # Bought at the open but never closed inside the window (an intraday halt
    # to the end): carried at the entry price, flagged ``exit_carried``.
    exit_price = exit_mark[0] if exit_mark is not None else entry
    return replace(
        not_held,
        status="held",
        exit_price=exit_price,
        adjustment=factor,
        forward_return=exit_price / entry * factor - 1.0,
    )


@dataclass(frozen=True)
class HoldingOutcomes:
    """Per-name outcomes of one window, looked up by symbol."""

    window: HoldingWindow
    by_symbol: Mapping[str, HoldingOutcome]

    def forward_returns(self, symbols: Sequence[str]) -> np.ndarray:
        """Forward returns of ``symbols`` in order; NaN where a name was not held."""
        values = [self.by_symbol[symbol].forward_return for symbol in symbols]
        return np.array([math.nan if v is None else v for v in values], dtype="float64")


def holding_outcomes(
    book: PriceBook,
    window: HoldingWindow,
    symbols: Sequence[str] | frozenset[str],
    execution: BasketExecution,
) -> HoldingOutcomes:
    by_symbol = {
        symbol: holding_outcome(book, window, symbol, execution) for symbol in sorted(symbols)
    }
    return HoldingOutcomes(window=window, by_symbol=MappingProxyType(by_symbol))


def normalise_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Long-only target weights scaled to sum to one; zero weights dropped."""
    for symbol, weight in weights.items():
        if not math.isfinite(weight) or weight < 0.0:
            raise ValueError(f"target weight of {symbol} must be finite and >= 0")
    kept = {symbol: float(weight) for symbol, weight in weights.items() if weight > 0.0}
    total = math.fsum(kept.values())
    if not kept:
        return {}
    return {symbol: kept[symbol] / total for symbol in sorted(kept)}


@dataclass(frozen=True)
class BasketFill:
    """Target weights, what could actually be held, and the resulting return."""

    requested: Mapping[str, float]
    held: Mapping[str, float]
    excluded: Mapping[str, OutcomeStatus]
    #: sum(held weight x forward return); None when nothing could be held.
    basket_return: float | None
    #: Diagnostic close(t) -> close(t+H) over every requested name with a price.
    close_to_close_return: float | None
    reference_fallback: frozenset[str]
    exit_carried: frozenset[str]


def fill_basket(outcomes: HoldingOutcomes, weights: Mapping[str, float]) -> BasketFill:
    """Drop what could not be bought, re-scale the rest to equal their target shares."""
    requested = normalise_weights(weights)
    excluded: dict[str, OutcomeStatus] = {}
    held_raw: dict[str, float] = {}
    for symbol, weight in requested.items():
        outcome = outcomes.by_symbol.get(symbol)
        if outcome is None:
            raise KeyError(f"no holding outcome computed for {symbol}")
        if outcome.status == "held":
            held_raw[symbol] = weight
        else:
            excluded[symbol] = outcome.status
    held = normalise_weights(held_raw)
    basket: float | None = None
    if held:
        basket = math.fsum(
            weight * float(outcomes.by_symbol[symbol].forward_return or 0.0)
            for symbol, weight in held.items()
        )
    diag_weights = normalise_weights(
        {
            symbol: weight
            for symbol, weight in requested.items()
            if outcomes.by_symbol[symbol].close_to_close_return is not None
        }
    )
    diagnostic = (
        math.fsum(
            weight * float(outcomes.by_symbol[symbol].close_to_close_return or 0.0)
            for symbol, weight in diag_weights.items()
        )
        if diag_weights
        else None
    )
    return BasketFill(
        requested=MappingProxyType(requested),
        held=MappingProxyType(held),
        excluded=MappingProxyType(excluded),
        basket_return=basket,
        close_to_close_return=diagnostic,
        reference_fallback=frozenset(
            symbol for symbol in held if outcomes.by_symbol[symbol].reference_fallback
        ),
        exit_carried=frozenset(
            symbol for symbol in held if outcomes.by_symbol[symbol].exit_carried
        ),
    )


@dataclass(frozen=True)
class BasketSample:
    """One non-overlapping sample: basket vs benchmark over the same window."""

    decision_date: date
    entry_date: date
    exit_date: date
    status: SampleStatus
    basket: BasketFill | None
    benchmark: BasketFill | None
    round_trip_cost: float
    #: basket - benchmark (no cost on either side).
    excess_gross: float | None
    #: basket - round_trip_cost - benchmark (the benchmark is never charged, D-9).
    excess_net: float | None
    #: Diagnostic close(t) -> close(t+H) excess, gross; never a decision input.
    diagnostic_excess_gross: float | None

    @property
    def valid(self) -> bool:
        return self.status == "ok"


def simulate_sample(
    book: PriceBook,
    window: HoldingWindow,
    weights: Mapping[str, float],
    benchmark_weights: Mapping[str, float],
    *,
    execution: BasketExecution,
    cost: float,
    outcomes: HoldingOutcomes | None = None,
) -> BasketSample:
    """Fill the basket and the benchmark of one decision and compare them.

    ``outcomes`` may be passed in when several baskets share one window (the
    evaluator fills every sector of a week from one set of outcomes); it must
    cover every requested name.
    """

    def empty(status: SampleStatus) -> BasketSample:
        return BasketSample(
            decision_date=window.decision_date,
            entry_date=window.entry_date,
            exit_date=window.exit_date,
            status=status,
            basket=None,
            benchmark=None,
            round_trip_cost=cost,
            excess_gross=None,
            excess_net=None,
            diagnostic_excess_gross=None,
        )

    if not book.has_sessions(window.sessions):
        return empty("bars_gap")
    if not normalise_weights(weights):
        return empty("empty_basket")
    if outcomes is None:
        outcomes = holding_outcomes(
            book, window, sorted(set(weights) | set(benchmark_weights)), execution
        )
    return compare_fills(
        window,
        fill_basket(outcomes, weights),
        fill_basket(outcomes, benchmark_weights),
        cost=cost,
    )


def compare_fills(
    window: HoldingWindow, basket: BasketFill, benchmark: BasketFill, *, cost: float
) -> BasketSample:
    """Excess of one filled basket over one filled benchmark (the one formula).

    ``excess_net`` charges the round trip to the basket only; the benchmark is
    a comparator and is never charged (ADR-0012 D-9).
    """
    status: SampleStatus = "ok"
    if basket.basket_return is None:
        status = "all_excluded"
    elif benchmark.basket_return is None:
        status = "empty_benchmark"
    excess_gross = excess_net = diagnostic = None
    if basket.basket_return is not None and benchmark.basket_return is not None:
        excess_gross = basket.basket_return - benchmark.basket_return
        excess_net = basket.basket_return - cost - benchmark.basket_return
        if basket.close_to_close_return is not None and benchmark.close_to_close_return is not None:
            diagnostic = basket.close_to_close_return - benchmark.close_to_close_return
    return BasketSample(
        decision_date=window.decision_date,
        entry_date=window.entry_date,
        exit_date=window.exit_date,
        status=status,
        basket=basket,
        benchmark=benchmark,
        round_trip_cost=cost,
        excess_gross=excess_gross,
        excess_net=excess_net,
        diagnostic_excess_gross=diagnostic,
    )


@dataclass(frozen=True)
class BasketResult:
    """Every sample plus the standard report of the strategy layer."""

    samples: tuple[BasketSample, ...]
    round_trip_cost: float
    #: ``CostModel.verified_on``; ``None`` = unverified rates (NE-3 downstream).
    cost_verified_on: str | None
    #: The synthetic daily run the report was measured on.
    run: BacktestResult
    #: Strategy metrics; the ``buy_and_hold`` column is the benchmark path held
    #: on the same windows, gross of cost (see :data:`DISCLOSURE_BENCHMARK_COLUMN`).
    report: SegmentReport
    #: Machine-readable disclosure codes; wording is the presenter's (risk-approved) job.
    disclosures: tuple[str, ...]

    @property
    def valid_samples(self) -> tuple[BasketSample, ...]:
        return tuple(sample for sample in self.samples if sample.valid)


def _nav(
    book: PriceBook,
    fill: BasketFill,
    outcomes: HoldingOutcomes,
    day: date,
    execution: BasketExecution,
) -> float:
    """Value on ``day`` of one unit put into ``fill`` at the entry open (restored)."""
    window = outcomes.window
    parts: list[float] = []
    for symbol, weight in fill.held.items():
        outcome = outcomes.by_symbol[symbol]
        entry = float(outcome.entry_price or 0.0)
        mark = book.last_close(symbol, since=window.entry_date, through=day)
        price = mark[0] if mark is not None else entry
        factor = _adjust(execution, symbol, window.entry_date, day) or 1.0
        parts.append(weight * price / entry * factor)
    return math.fsum(parts)


def assemble_result(
    book: PriceBook,
    samples: Sequence[BasketSample],
    outcomes: Mapping[date, HoldingOutcomes],
    *,
    calendar: Sequence[date],
    cost_model: CostModel,
    execution: BasketExecution,
) -> BasketResult:
    """Mark every sample to market daily and build the standard report.

    The strategy pays the buy leg at the entry open and the sell leg at the
    exit close and sits in cash between samples; the benchmark path is held on
    the same windows, never charged. Invalid samples leave both flat.
    """
    market, instrument = execution.market, execution.instrument_type
    buy_rate = cost_model.trade_cost(
        notional=1.0, side="buy", market=market, instrument_type=instrument
    )
    sell_rate = cost_model.trade_cost(
        notional=1.0, side="sell", market=market, instrument_type=instrument
    )
    cost = buy_rate + sell_rate
    ordered = sorted(samples, key=lambda sample: sample.decision_date)
    days = tuple(sorted(set(calendar)))
    if ordered:
        start = bisect_left(days, ordered[0].decision_date)
        stop = bisect_right(days, ordered[-1].exit_date)
        days = days[start:stop]
    else:
        days = ()
    position = {day: index for index, day in enumerate(days)}

    equity = [execution.initial_equity] * len(days)
    bench = [1.0] * len(days)
    weights = [0.0] * len(days)
    trades: list[Trade] = []
    cash = execution.initial_equity
    level = 1.0
    cursor = 0
    for sample in ordered:
        entry_index = position[sample.entry_date]
        exit_index = position[sample.exit_date]
        for index in range(cursor, entry_index):
            equity[index], bench[index] = cash, level
        cursor = entry_index
        window_outcomes = outcomes.get(sample.decision_date)
        if not sample.valid or window_outcomes is None:
            continue
        assert sample.basket is not None and sample.benchmark is not None
        units = cash * (1.0 - buy_rate)
        trades.append(
            Trade(
                date=sample.entry_date.isoformat(),
                bar_index=entry_index,
                side="buy",
                shares=units,
                price=1.0,
                notional=units,
                cost=cash * buy_rate,
                realized_pnl=None,
            )
        )
        bench_start = level
        for index in range(entry_index, exit_index + 1):
            day = days[index]
            nav = _nav(book, sample.basket, window_outcomes, day, execution)
            equity[index] = units * nav
            weights[index] = 1.0
            bench[index] = bench_start * _nav(
                book, sample.benchmark, window_outcomes, day, execution
            )
        exit_nav = _nav(book, sample.basket, window_outcomes, sample.exit_date, execution)
        proceeds = units * exit_nav
        closing_cash = proceeds * (1.0 - sell_rate)
        trades.append(
            Trade(
                date=sample.exit_date.isoformat(),
                bar_index=exit_index,
                side="sell",
                shares=-units,
                price=exit_nav,
                notional=proceeds,
                cost=proceeds * sell_rate,
                realized_pnl=closing_cash - cash,
            )
        )
        equity[exit_index] = closing_cash
        weights[exit_index] = 0.0
        cash = closing_cash
        level = bench[exit_index]
        cursor = exit_index + 1
    for index in range(cursor, len(days)):
        equity[index], bench[index] = cash, level

    run = BacktestResult(
        dates=[day.isoformat() for day in days],
        equity_curve=equity,
        close=bench,
        weights=weights,
        trades=trades,
        initial_cash=execution.initial_equity,
        market=market,
        instrument_type=instrument,
    )
    disclosures: list[str] = [DISCLOSURE_BENCHMARK_COLUMN]
    if cost_model.verified_on is None:
        disclosures.append(DISCLOSURE_COST_UNVERIFIED)
    valid = [sample for sample in ordered if sample.valid]
    if any(sample.basket and sample.basket.reference_fallback for sample in valid):
        disclosures.append(DISCLOSURE_REFERENCE_FALLBACK)
    if any(sample.basket and sample.basket.exit_carried for sample in valid):
        disclosures.append(DISCLOSURE_EXIT_CARRIED)
    return BasketResult(
        samples=tuple(ordered),
        round_trip_cost=cost,
        cost_verified_on=cost_model.verified_on,
        run=run,
        report=build_segment_report(run, label="basket"),
        disclosures=tuple(disclosures),
    )


def run_basket_backtest(
    panel: MarketPanel,
    strategy: BasketStrategy,
    *,
    schedule: BasketSchedule,
    cost_model: CostModel,
    execution: BasketExecution,
    benchmark: BasketStrategy,
) -> BasketResult:
    """Run ``strategy`` against ``benchmark`` on every scheduled decision (ADR-0012 D-13).

    The engine holds the whole panel; each rule only ever receives
    ``panel.as_of(t)`` -- a view that raises on any date after ``t``. The
    benchmark rule is required because the engine does not know the
    comparator's population (for the sector card it is ``C_M(t,L)``, which
    only the sector core can compute).
    """
    book = PriceBook.from_panel(panel)
    cost = round_trip_cost(
        cost_model, market=execution.market, instrument_type=execution.instrument_type
    )
    samples: list[BasketSample] = []
    outcomes: dict[date, HoldingOutcomes] = {}
    for decision in schedule.decision_dates:
        window = schedule.window(decision)
        if window is None:
            break
        view = panel.as_of(decision)
        weights = dict(strategy(view))
        benchmark_weights = dict(benchmark(view))
        if book.has_sessions(window.sessions) and normalise_weights(weights):
            outcomes[decision] = holding_outcomes(
                book, window, sorted(set(weights) | set(benchmark_weights)), execution
            )
        samples.append(
            simulate_sample(
                book,
                window,
                weights,
                benchmark_weights,
                execution=execution,
                cost=cost,
                outcomes=outcomes.get(decision),
            )
        )
    return assemble_result(
        book,
        samples,
        outcomes,
        calendar=schedule.calendar,
        cost_model=cost_model,
        execution=execution,
    )
