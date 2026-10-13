"""Standard backtest report: every field the backtest-protocol requires.

Produces CAGR, annualized volatility, Sharpe, Sortino, max drawdown (with peak
and trough dates), win rate, profit factor, trade count and turnover -- always
alongside a same-period **Buy & Hold** benchmark, and with in-sample and
out-of-sample segments reported **separately** (never blended). Nothing here
selects parameters; it only measures a run that was already produced.

Conventions:

* Returns are simple period returns of the equity curve.
* Sharpe/Sortino use ``risk_free_rate`` per period (default 0), annualized by
  ``sqrt(periods_per_year)``. Sortino's downside deviation is
  ``sqrt(mean(min(r - rf, 0)^2))``.
* CAGR uses ``(end/start)^(periods_per_year / n_periods) - 1``.
* Turnover = total absolute traded notional / mean equity over the segment.
* Buy & Hold is shown gross of transaction cost, as a pure passive price
  benchmark (documented so it is never mistaken for a costed strategy).
* Win rate / profit factor are computed over complete **holding round trips**
  (C8 fix). The engine rebalances to a target weight every bar, so a single
  holding period emits a long tail of tiny position-reducing fills; rating those
  as trades polluted both statistics (measured: up to 21pp of win rate and 50%
  of the derived risk cap). Round trips are supplied by
  :mod:`app.backtest.episodes` -- the only module that defines extraction and
  attribution -- and this module never re-derives them.
* ``win_rate`` is therefore the round-trip win rate: by construction it equals
  ``round_trip_win_rate`` (both read the very same
  :class:`~app.backtest.episodes.RoundTripStats`).
* ``profit_factor`` is round-trip gross profit / gross loss: the numerator sums
  ``realized_pnl`` over winning round trips (``realized_pnl > 0``), the
  denominator sums ``-realized_pnl`` over losing ones (``realized_pnl < 0``).
* ``num_closing_trades`` keeps its original fill-layer meaning -- the count of
  closing fills carrying realized P&L. It states a settlement count, which was
  never the polluted claim, and it is the honest witness of how many fills the
  round trips above were folded from.
* ``num_round_trips`` is the denominator ``win_rate`` was measured over -- the
  same ``RoundTripStats.n``, never recounted. It ships because the two counts
  already on the display surface (``num_trades`` / ``num_closing_trades``) are
  7-15x larger than it, so a reader judging sample size from the visible counts
  would overrate the win rate's reliability (C8-6). ``None`` means no round-trip
  attribution exists for this column at all (the Buy & Hold peer trades
  nothing); ``0`` means attribution ran and found no complete round trip, which
  is the case that explains a ``win_rate`` of ``None`` beside a non-zero
  settlement count.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from app.backtest.display_params import N_MIN_DISPLAY, N_WORST
from app.backtest.engine import BacktestResult, Trade
from app.backtest.episodes import (
    Episode,
    RoundTripAttribution,
    attribute_round_trips,
    episode_returns,
    extract_episodes,
    held_mask,
    holding_bars,
    in_market_ratio,
    longest_losing_streak,
    lowest_return_episodes,
    mean_win_loss_returns,
)
from app.backtest.splits import WalkForwardFold
from app.signals.risk import drawdown_series, max_drawdown

TRADING_DAYS_PER_YEAR = 252


class PerformanceMetrics(BaseModel):
    """The standard metric block for one segment of one run."""

    model_config = ConfigDict(frozen=True)

    label: str
    start_date: str | None
    end_date: str | None
    observations: int
    start_equity: float | None
    end_equity: float | None
    total_return: float | None
    cagr: float | None
    annualized_volatility: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float | None
    max_drawdown_peak_date: str | None
    max_drawdown_trough_date: str | None
    # Round-trip layer (C8 fix): ``win_rate`` is the round-trip win rate and
    # always equals ``round_trip_win_rate`` below -- both read the same
    # ``RoundTripStats``. ``profit_factor`` is round-trip gross profit / gross
    # loss. Both are ``None`` where no completed round trip exists.
    win_rate: float | None
    profit_factor: float | None
    num_trades: int
    # Fill-layer count, original meaning kept: closing fills carrying realized
    # P&L. A settlement count, not a trade-quality statistic.
    num_closing_trades: int
    turnover: float | None
    # The C5 round-trip pair, kept for the display contract that reads it.
    # ``round_trip_win_rate`` duplicates ``win_rate`` since the C8 fix;
    # ``round_trip_payoff_ratio`` is b (mean winning return / mean absolute
    # losing return), a different ratio from ``profit_factor``. ``None`` where
    # no round trip is defined -- the Buy & Hold peer trades nothing, and a
    # segment with no completed round trip has no rate to report.
    round_trip_win_rate: float | None
    round_trip_payoff_ratio: float | None
    # C8-6: the denominator behind ``win_rate``/``round_trip_win_rate``, read
    # off the same ``RoundTripStats`` (``n``) rather than recounted. ``None``
    # where that object does not exist (Buy & Hold, empty segment); ``0`` where
    # it exists and holds no complete round trip.
    num_round_trips: int | None


class SegmentReport(BaseModel):
    """A strategy segment paired with its Buy & Hold benchmark over the same span."""

    model_config = ConfigDict(frozen=True)

    strategy: PerformanceMetrics
    buy_and_hold: PerformanceMetrics


class WalkForwardReport(BaseModel):
    """In-sample and out-of-sample reports kept strictly separate.

    ``out_of_sample`` is the honest performance measure -- the segments whose
    dates never informed any parameter choice.
    """

    model_config = ConfigDict(frozen=True)

    in_sample: SegmentReport
    out_of_sample: SegmentReport


class SegmentCurves(BaseModel):
    """The per-bar series the metric block of the same segment was measured on.

    Not a second measurement: these are the exact arrays
    :func:`build_segment_report` reduces to :class:`PerformanceMetrics`, cut with
    the same slicer and benchmarked with the same Buy & Hold path, so a chart
    drawn from them cannot disagree with the table beside it. Consequently
    ``strategy[0]`` / ``strategy[-1]`` are the segment's ``start_equity`` /
    ``end_equity``, and ``min(drawdown)`` is its ``max_drawdown``.

    All four arrays are equal length -- the segment's ``observations`` -- except
    in the one degenerate case where the Buy & Hold path is undefined (a
    non-positive first close), which is also the case where the report's Buy &
    Hold column reports nothing; ``buy_and_hold`` is then empty rather than
    padded with a value that was never computed.
    """

    model_config = ConfigDict(frozen=True)

    dates: list[str]
    #: Strategy equity per bar, in currency -- same scale as ``start_equity``.
    strategy: list[float]
    #: Passive equity per bar, gross of cost, from the segment's first close.
    buy_and_hold: list[float]
    #: Strategy equity against its running peak within the segment (``<= 0``).
    drawdown: list[float]


class CurveTrade(BaseModel):
    """One fill, reduced to what a chart marker needs."""

    model_config = ConfigDict(frozen=True)

    date: str
    side: str  # "buy" or "sell"
    price: float


class WalkForwardCurves(BaseModel):
    """The two reported segments as drawable series, plus their fill markers.

    The chart peer of :class:`WalkForwardReport`: same run, same segment bounds,
    same Buy & Hold definition. ``split_date`` is the first out-of-sample bar --
    where a reader must stop trusting the curve as evidence of anything but
    fitting -- and equals ``out_of_sample.dates[0]`` whenever that segment has a
    bar at all.
    """

    model_config = ConfigDict(frozen=True)

    in_sample: SegmentCurves
    out_of_sample: SegmentCurves
    split_date: str | None
    #: Fills landing inside either segment, selected by ``bar_index`` (the
    #: geometry's own unit) rather than by date string, in chronological order.
    trades: list[CurveTrade]


def _returns(equity: np.ndarray) -> np.ndarray:
    if equity.size < 2:
        return np.empty(0, dtype="float64")
    return np.asarray(equity[1:] / equity[:-1] - 1.0, dtype="float64")


def _cagr(start: float, end: float, n_periods: int, periods_per_year: int) -> float | None:
    if start <= 0 or n_periods < 1:
        return None
    years = n_periods / periods_per_year
    if years <= 0:
        return None
    return float((end / start) ** (1.0 / years) - 1.0)


def _sharpe(returns: np.ndarray, rf: float, periods_per_year: int) -> float | None:
    if returns.size < 2:
        return None
    excess = returns - rf
    std = float(np.std(excess, ddof=1))
    if std == 0.0:
        return None
    return float(np.mean(excess)) / std * math.sqrt(periods_per_year)


def _sortino(returns: np.ndarray, rf: float, periods_per_year: int) -> float | None:
    if returns.size < 2:
        return None
    excess = returns - rf
    downside = np.minimum(excess, 0.0)
    downside_dev = math.sqrt(float(np.mean(downside**2)))
    if downside_dev == 0.0:
        return None
    return float(np.mean(excess)) / downside_dev * math.sqrt(periods_per_year)


def _trade_stats(round_trips: RoundTripAttribution | None) -> tuple[float | None, float | None]:
    """Return ``(win_rate, profit_factor)`` over complete holding round trips.

    C8 fix: the statistical unit is the round trip, never the fill. Round trips
    are supplied by :mod:`app.backtest.episodes`; nothing here extracts or
    attributes them a second time.

    * ``win_rate`` is ``stats.round_trip_win_rate`` itself -- the same value the
      ``round_trip_win_rate`` field reports, taken from the same object so the
      two cannot drift apart.
    * ``profit_factor`` = round-trip gross profit / gross loss. Numerator: sum
      of ``realized_pnl`` over round trips with ``realized_pnl > 0``.
      Denominator: sum of ``-realized_pnl`` over round trips with
      ``realized_pnl < 0``. ``None`` when there is no losing round trip
      (undefined ratio) or no round trips at all.
    """
    if round_trips is None or not round_trips.episodes:
        return None, None
    win_rate = round_trips.stats.round_trip_win_rate
    gross_profit = sum(e.realized_pnl for e in round_trips.episodes if e.realized_pnl > 0)
    gross_loss = -sum(e.realized_pnl for e in round_trips.episodes if e.realized_pnl < 0)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    return win_rate, profit_factor


def _num_closing_fills(trades: list[Trade]) -> int:
    """Count closing fills (those carrying realized P&L) -- original meaning."""
    return sum(1 for t in trades if t.realized_pnl is not None)


def _metrics(
    *,
    label: str,
    dates: list[str],
    equity: np.ndarray,
    trades: list[Trade],
    periods_per_year: int,
    risk_free_rate: float,
    round_trips: RoundTripAttribution | None,
) -> PerformanceMetrics:
    n = int(equity.size)
    if n == 0:
        return PerformanceMetrics(
            label=label,
            start_date=None,
            end_date=None,
            observations=0,
            start_equity=None,
            end_equity=None,
            total_return=None,
            cagr=None,
            annualized_volatility=None,
            sharpe=None,
            sortino=None,
            max_drawdown=None,
            max_drawdown_peak_date=None,
            max_drawdown_trough_date=None,
            win_rate=None,
            profit_factor=None,
            num_trades=len(trades),
            num_closing_trades=0,
            turnover=None,
            round_trip_win_rate=None,
            round_trip_payoff_ratio=None,
            num_round_trips=None,
        )

    start_equity = float(equity[0])
    end_equity = float(equity[-1])
    returns = _returns(equity)
    total_return = end_equity / start_equity - 1.0 if start_equity > 0 else None

    ann_vol: float | None = None
    if returns.size >= 2:
        ann_vol = float(np.std(returns, ddof=1)) * math.sqrt(periods_per_year)

    dd_value: float | None = None
    dd_peak: str | None = None
    dd_trough: str | None = None
    if n >= 2:
        dd = max_drawdown(equity.tolist())
        if dd is not None:
            worst, peak_i, trough_i = dd
            dd_value, dd_peak, dd_trough = worst, dates[peak_i], dates[trough_i]

    win_rate, profit_factor = _trade_stats(round_trips)
    stats = round_trips.stats if round_trips is not None else None
    mean_equity = float(np.mean(equity))
    traded_notional = sum(abs(t.notional) for t in trades)
    turnover = traded_notional / mean_equity if mean_equity > 0 else None

    return PerformanceMetrics(
        label=label,
        start_date=dates[0],
        end_date=dates[-1],
        observations=n,
        start_equity=start_equity,
        end_equity=end_equity,
        total_return=total_return,
        cagr=_cagr(start_equity, end_equity, n - 1, periods_per_year),
        annualized_volatility=ann_vol,
        sharpe=_sharpe(returns, risk_free_rate, periods_per_year),
        sortino=_sortino(returns, risk_free_rate, periods_per_year),
        max_drawdown=dd_value,
        max_drawdown_peak_date=dd_peak,
        max_drawdown_trough_date=dd_trough,
        win_rate=win_rate,
        profit_factor=profit_factor,
        num_trades=len(trades),
        num_closing_trades=_num_closing_fills(trades),
        turnover=turnover,
        round_trip_win_rate=stats.round_trip_win_rate if stats else None,
        round_trip_payoff_ratio=stats.round_trip_payoff_ratio if stats else None,
        # Same ``stats`` object the two rates above came from, so the displayed
        # sample size cannot describe a different set of round trips than the
        # win rate it sits beside (C8-7).
        num_round_trips=stats.n if stats is not None else None,
    )


def _buy_and_hold_equity(close: np.ndarray, initial_cash: float) -> np.ndarray:
    """Passive fully-invested equity path (gross of cost) from the first close."""
    if close.size == 0 or close[0] <= 0:
        return np.empty(0, dtype="float64")
    return np.asarray(initial_cash * close / close[0], dtype="float64")


@dataclass(frozen=True)
class _SegmentSeries:
    """One segment's raw arrays: what both the metrics and the curves read.

    Sliced and benchmarked in exactly one place so the chart and the table can
    never be drawn from two different definitions of "this segment".
    """

    stop: int
    dates: list[str]
    equity: np.ndarray
    close: np.ndarray
    buy_and_hold: np.ndarray


def _segment_series(result: BacktestResult, *, start: int, stop: int | None) -> _SegmentSeries:
    end = len(result.equity_curve) if stop is None else stop
    close = np.asarray(result.close[start:end], dtype="float64")
    return _SegmentSeries(
        stop=end,
        dates=result.dates[start:end],
        equity=np.asarray(result.equity_curve[start:end], dtype="float64"),
        close=close,
        buy_and_hold=_buy_and_hold_equity(close, result.initial_cash),
    )


def build_segment_report(
    result: BacktestResult,
    *,
    label: str = "full",
    start: int = 0,
    stop: int | None = None,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    risk_free_rate: float = 0.0,
) -> SegmentReport:
    """Report metrics for ``result`` over ``[start, stop)`` with a Buy & Hold peer."""
    series = _segment_series(result, start=start, stop=stop)
    end = series.stop
    dates = series.dates
    equity = series.equity
    seg_start = result.dates[start] if dates else None
    seg_end = result.dates[end - 1] if dates else None
    trades = [
        t for t in result.trades if seg_start is not None and seg_start <= t.date <= (seg_end or "")
    ]

    # Round trips are attributed by bar index over the very same ``[start, end)``
    # bounds this segment was cut with. The date filter above keeps feeding the
    # fill-count and turnover fields only; since the C8 fix no rate statistic
    # reads it.
    round_trips = attribute_round_trips(result, start=start, stop=end)

    strategy_metrics = _metrics(
        label=f"{label}:strategy",
        dates=dates,
        equity=equity,
        trades=trades,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
        round_trips=round_trips,
    )
    bh_metrics = _metrics(
        label=f"{label}:buy_and_hold",
        dates=dates,
        equity=series.buy_and_hold,
        trades=[],
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
        round_trips=None,
    )
    return SegmentReport(strategy=strategy_metrics, buy_and_hold=bh_metrics)


def build_segment_curves(
    result: BacktestResult, *, start: int = 0, stop: int | None = None
) -> SegmentCurves:
    """The drawable series for ``result`` over ``[start, stop)``.

    Shares :func:`_segment_series` with :func:`build_segment_report`, so the
    curve is literally the path the metrics were reduced from; the drawdown
    comes from :func:`~app.signals.risk.drawdown_series`, the same definition
    ``max_drawdown`` minimises.
    """
    series = _segment_series(result, start=start, stop=stop)
    return SegmentCurves(
        dates=series.dates,
        strategy=[float(x) for x in series.equity],
        buy_and_hold=[float(x) for x in series.buy_and_hold],
        drawdown=drawdown_series(series.equity.tolist()),
    )


def _walk_forward_bounds(
    folds: list[WalkForwardFold],
) -> tuple[tuple[int, int], tuple[int, int]]:
    """``(in_sample, out_of_sample)`` bar bounds ``[start, stop)`` for ``folds``.

    The single definition of the two reported segments: the initial training
    block, and the contiguous stitch of every fold's test window. Both the
    report and the curves read it, so they cannot describe different spans.
    """
    if not folds:
        raise ValueError("walk-forward segmentation needs at least one fold")
    return (
        (folds[0].train_start, folds[0].train_stop),
        (folds[0].test_start, folds[-1].test_stop),
    )


def walk_forward_curves(result: BacktestResult, folds: list[WalkForwardFold]) -> WalkForwardCurves:
    """The chart peer of :func:`walk_forward_report` over the same segments.

    Fills are selected by ``bar_index`` against the same bounds the segments
    were cut with -- comparing date strings would re-derive the geometry from
    its own description (see :class:`~app.backtest.engine.Trade`).
    """
    (is_start, is_stop), (oos_start, oos_stop) = _walk_forward_bounds(folds)
    out_of_sample = build_segment_curves(result, start=oos_start, stop=oos_stop)
    trades = [
        CurveTrade(date=t.date, side=t.side, price=t.price)
        for t in result.trades
        if is_start <= t.bar_index < is_stop or oos_start <= t.bar_index < oos_stop
    ]
    return WalkForwardCurves(
        in_sample=build_segment_curves(result, start=is_start, stop=is_stop),
        out_of_sample=out_of_sample,
        split_date=out_of_sample.dates[0] if out_of_sample.dates else None,
        trades=trades,
    )


def walk_forward_report(
    result: BacktestResult,
    folds: list[WalkForwardFold],
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    risk_free_rate: float = 0.0,
) -> WalkForwardReport:
    """Report a run split into in-sample and out-of-sample, kept separate.

    The out-of-sample segment is the contiguous, non-overlapping stitch of every
    fold's test window (``[first test_start, last test_stop)``) -- the region no
    parameter choice was allowed to see. The in-sample segment is the initial
    training block (``[first train_start, first train_stop)``). Reporting them
    apart is the protocol's honesty requirement: OOS is the number that counts.
    """
    if not folds:
        raise ValueError("walk_forward_report needs at least one fold")
    (is_start, is_stop), (oos_start, oos_stop) = _walk_forward_bounds(folds)
    in_sample = build_segment_report(
        result,
        label="in_sample",
        start=is_start,
        stop=is_stop,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
    )
    out_of_sample = build_segment_report(
        result,
        label="out_of_sample",
        start=oos_start,
        stop=oos_stop,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
    )
    return WalkForwardReport(in_sample=in_sample, out_of_sample=out_of_sample)


# --------------------------------------------------------------------------
# F-11: the round-trip detail block (PRD FR-1..FR-10, FR-17; tech-architect
# F11-A-4, A-5, A-12, A-13, A-36, A-38, A-41..A-43, A-54).
#
# A sibling of :class:`WalkForwardReport`, never a field of it: the metric
# models above are also read by the basket backtester and the research store
# (F11-A-8), so nothing here widens them. Every round-trip fact comes from
# :mod:`app.backtest.episodes`; this section only attributes by bar index over
# the same ``_walk_forward_bounds``, looks dates up from ``result.dates`` and
# makes the three disclosure decisions the front end must not make itself
# (sample flag, empty-state code, Buy & Hold in-market value). It is
# strategy-agnostic on purpose -- the warm-up length arrives as an argument,
# because this module is shared with callers that have no strategy at all
# (F11-A-41).
# --------------------------------------------------------------------------

#: Why a segment has no complete round trip to list, decided from counts alone.
RoundTripEmptyState = Literal["no_position", "excluded_only"]


class RoundTripRow(BaseModel):
    """One complete round trip of a segment, as the detail list shows it.

    Exactly five facts (F11-A-21): no price, no fill breakdown, no free text and
    no index column. Both dates are looked up from the run's own bar index, and
    every number is net of the run's cost model (PRD D-3).
    """

    model_config = ConfigDict(frozen=True)

    entry_date: str
    exit_date: str
    #: ``exit_idx - entry_idx``, in daily bars (PRD D-4).
    holding_bars: int
    #: Realized P&L over the equity of the bar before the entry (PRD D-3).
    return_on_entry_equity: float
    realized_pnl: float


class LosingStreak(BaseModel):
    """The longest run of consecutive losing round trips in one segment (D-11).

    ``length == 0`` when the segment has round trips but none of them lost; the
    two dates are then ``None``. The earliest streak is the one reported when
    several are equally long.
    """

    model_config = ConfigDict(frozen=True)

    length: int
    #: Entry date of the streak's first round trip.
    start_date: str | None
    #: Exit date of the streak's last round trip.
    end_date: str | None


class SegmentRoundTripDetail(BaseModel):
    """Everything the detail block states about one segment.

    The list, ``num_round_trips``, both side counts and both exclusion counts
    are read off **one** :func:`~app.backtest.episodes.attribute_round_trips`
    call over the segment's bounds (F11-A-42); the metric table's own
    ``num_round_trips`` equals it because both attribute the same window.
    """

    model_config = ConfigDict(frozen=True)

    #: ``RoundTripStats.n`` of the segment -- the size of ``round_trips``.
    num_round_trips: int
    num_winning_round_trips: int
    num_losing_round_trips: int
    #: Every complete round trip of the segment, earliest entry first.
    round_trips: list[RoundTripRow]
    #: The ``N_WORST`` lowest-return round trips, lowest first (D-10).
    lowest_return_round_trips: list[RoundTripRow]
    #: Mean return of the winning / losing round trips; ``None`` when that side
    #: is empty. ``mean_winning_return / -mean_losing_return`` is the report's
    #: ``round_trip_payoff_ratio`` bit for bit.
    mean_winning_return: float | None
    mean_losing_return: float | None
    #: ``None`` exactly when the segment has no complete round trip.
    longest_losing_streak: LosingStreak | None
    #: Closed round trips overlapping the segment without being contained by it.
    excluded_boundary_trips: int
    #: A round trip still open on the run's last bar that opened before the
    #: segment's end (0 or 1).
    open_trip_at_end: int
    #: Share of the segment's return intervals spent holding shares (D-12).
    in_market_ratio: float | None
    #: The Buy & Hold peer's in-market share: ``1.0`` by definition (fully
    #: invested from the segment's first close), ``None`` when that path is
    #: undefined or the segment has no return interval. Not a measurement.
    buy_and_hold_in_market_ratio: float | None
    #: Return intervals of the segment inside the strategy's warm-up, where it
    #: structurally holds nothing; 0 on the out-of-sample segment.
    warmup_flat_intervals: int
    #: ``num_round_trips < N_MIN_DISPLAY``. Disclosure only -- it enters no
    #: computation and refuses nothing.
    below_display_minimum: bool
    #: ``None`` when the segment has a round trip to list.
    empty_state: RoundTripEmptyState | None


class RoundTripCoverage(BaseModel):
    """Run-level geometry facts only: dates and bar counts (F11-A-36, A-38, A-48).

    No round trip, P&L, ratio or trade count of the unattributed tail is
    carried here: a figure for the tail would read as its performance.
    """

    model_config = ConfigDict(frozen=True)

    #: ``result.dates[-1]`` of the very run reported on; ``None`` only for a
    #: run with no bar at all, which the API never reports on.
    last_bar_date: str | None
    #: Bars after the out-of-sample segment that belong to no segment (r).
    unattributed_tail_bars: int
    #: First of those bars; ``None`` exactly when there is none.
    unattributed_tail_start_date: str | None


class WalkForwardRoundTripDetail(BaseModel):
    """The two reported segments' round-trip detail plus the run's coverage."""

    model_config = ConfigDict(frozen=True)

    in_sample: SegmentRoundTripDetail
    out_of_sample: SegmentRoundTripDetail
    coverage: RoundTripCoverage


def round_trip_empty_state(attribution: RoundTripAttribution) -> RoundTripEmptyState | None:
    """Which empty-state sentence a segment shows, from its attribution counts alone.

    Exhaustive and mutually exclusive (F11-A-54):

    * a complete round trip exists (``n > 0``) -> ``None``;
    * ``n == 0`` and nothing was excluded either -> ``"no_position"``;
    * ``n == 0`` and at least one boundary or open round trip was excluded ->
      ``"excluded_only"``.

    The signature takes the attribution and nothing else, so neither the
    in-market reading, the weights, the fills nor the coverage can leak into
    the decision. It never raises.
    """
    if attribution.stats.n > 0:
        return None
    excluded = attribution.excluded_boundary_trips + attribution.open_trip_at_end
    return "excluded_only" if excluded > 0 else "no_position"


def _round_trip_row(result: BacktestResult, episode: Episode) -> RoundTripRow:
    return RoundTripRow(
        entry_date=result.dates[episode.entry_idx],
        exit_date=result.dates[episode.exit_idx],
        holding_bars=holding_bars(episode),
        return_on_entry_equity=episode.return_on_entry_equity,
        realized_pnl=episode.realized_pnl,
    )


def _warmup_flat_intervals(*, start: int, stop: int, warmup_bars: int) -> int:
    """``|[start, stop - 1) ∩ [0, warmup_bars - 1)|``: intervals no position can exist in."""
    return max(0, min(stop - 1, warmup_bars - 1) - max(start, 0))


def _segment_round_trip_detail(
    result: BacktestResult,
    *,
    start: int,
    stop: int,
    held: tuple[bool, ...],
    warmup_bars: int,
) -> SegmentRoundTripDetail:
    # One attribution call feeds the list, n, both side counts and both
    # exclusion counts (F11-A-42).
    attribution = attribute_round_trips(result, start=start, stop=stop)
    episodes = attribution.episodes
    stats = attribution.stats
    mean_win, mean_loss = mean_win_loss_returns(episode_returns(episodes))
    streak = longest_losing_streak(episodes)
    series = _segment_series(result, start=start, stop=stop)
    has_interval = series.stop - start - 1 >= 1
    return SegmentRoundTripDetail(
        num_round_trips=stats.n,
        num_winning_round_trips=stats.n_win,
        num_losing_round_trips=stats.n_loss,
        round_trips=[_round_trip_row(result, episode) for episode in episodes],
        lowest_return_round_trips=[
            _round_trip_row(result, episode)
            for episode in lowest_return_episodes(episodes, N_WORST)
        ],
        mean_winning_return=mean_win,
        mean_losing_return=mean_loss,
        longest_losing_streak=(
            None
            if streak is None
            else LosingStreak(
                length=len(streak),
                start_date=result.dates[streak[0].entry_idx] if streak else None,
                end_date=result.dates[streak[-1].exit_idx] if streak else None,
            )
        ),
        excluded_boundary_trips=attribution.excluded_boundary_trips,
        open_trip_at_end=attribution.open_trip_at_end,
        in_market_ratio=in_market_ratio(held, start=start, stop=series.stop),
        # By definition, not measured (F11-A-13(b), A-41): the same path the
        # report's Buy & Hold column is reduced from decides whether it exists.
        buy_and_hold_in_market_ratio=(
            1.0 if series.buy_and_hold.size > 0 and has_interval else None
        ),
        warmup_flat_intervals=_warmup_flat_intervals(
            start=start, stop=series.stop, warmup_bars=warmup_bars
        ),
        below_display_minimum=stats.n < N_MIN_DISPLAY,
        empty_state=round_trip_empty_state(attribution),
    )


def walk_forward_round_trip_detail(
    result: BacktestResult, folds: list[WalkForwardFold], *, warmup_bars: int
) -> WalkForwardRoundTripDetail:
    """The round-trip detail of the two reported segments, plus the run's coverage.

    Same segments as :func:`walk_forward_report` (``_walk_forward_bounds`` of the
    same ``folds``), so every count here describes the window the metric table
    beside it was measured on. ``warmup_bars`` is the strategy's warm-up length,
    supplied by the caller. Total over every input :func:`walk_forward_report`
    accepts (F11-A-43): it raises only where that function raises (no fold).
    """
    if not folds:
        raise ValueError("walk_forward_round_trip_detail needs at least one fold")
    (is_start, is_stop), (oos_start, oos_stop) = _walk_forward_bounds(folds)
    bars = len(result.dates)
    held = held_mask(extract_episodes(result), bars)
    tail = max(bars - oos_stop, 0)
    return WalkForwardRoundTripDetail(
        in_sample=_segment_round_trip_detail(
            result, start=is_start, stop=is_stop, held=held, warmup_bars=warmup_bars
        ),
        out_of_sample=_segment_round_trip_detail(
            result, start=oos_start, stop=oos_stop, held=held, warmup_bars=warmup_bars
        ),
        coverage=RoundTripCoverage(
            last_bar_date=result.dates[-1] if result.dates else None,
            unattributed_tail_bars=tail,
            unattributed_tail_start_date=result.dates[oos_stop] if tail > 0 else None,
        ),
    )
