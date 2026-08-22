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
* Win rate / profit factor are computed over **closing** (position-reducing)
  fills, which carry realized P&L.
* ``round_trip_win_rate`` / ``round_trip_payoff_ratio`` are the same segment
  measured over complete **holding round trips** instead of fills, and come
  from :mod:`app.backtest.episodes` (the only place that defines them). They sit
  beside the fill-layer pair rather than replacing it: the two answer different
  questions and their values legitimately differ, since a daily rebalance splits
  one holding period into many fills.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel, ConfigDict

from app.backtest.engine import BacktestResult, Trade
from app.backtest.episodes import RoundTripStats, attribute_round_trips
from app.backtest.splits import WalkForwardFold
from app.signals.risk import max_drawdown

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
    win_rate: float | None
    profit_factor: float | None
    num_trades: int
    num_closing_trades: int
    turnover: float | None
    # Round-trip (holding-period) layer. Separate from the fill-layer pair
    # above, never a replacement for it, and ``None`` where no round trip is
    # defined -- the Buy & Hold peer trades nothing, and a segment with no
    # completed round trip has no rate to report.
    round_trip_win_rate: float | None
    round_trip_payoff_ratio: float | None


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


def _trade_stats(trades: list[Trade]) -> tuple[float | None, float | None, int]:
    """Return ``(win_rate, profit_factor, num_closing_trades)``.

    Computed over closing fills (those carrying realized P&L). ``profit_factor``
    is gross profit / gross loss; ``None`` when there are no losses (undefined
    ratio) or no closing trades.
    """
    realized = [t.realized_pnl for t in trades if t.realized_pnl is not None]
    if not realized:
        return None, None, 0
    wins = [p for p in realized if p > 0]
    losses = [p for p in realized if p < 0]
    win_rate = len(wins) / len(realized)
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    return win_rate, profit_factor, len(realized)


def _metrics(
    *,
    label: str,
    dates: list[str],
    equity: np.ndarray,
    trades: list[Trade],
    periods_per_year: int,
    risk_free_rate: float,
    round_trip: RoundTripStats | None,
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

    win_rate, profit_factor, num_closing = _trade_stats(trades)
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
        num_closing_trades=num_closing,
        turnover=turnover,
        round_trip_win_rate=round_trip.round_trip_win_rate if round_trip else None,
        round_trip_payoff_ratio=round_trip.round_trip_payoff_ratio if round_trip else None,
    )


def _buy_and_hold_equity(close: np.ndarray, initial_cash: float) -> np.ndarray:
    """Passive fully-invested equity path (gross of cost) from the first close."""
    if close.size == 0 or close[0] <= 0:
        return np.empty(0, dtype="float64")
    return np.asarray(initial_cash * close / close[0], dtype="float64")


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
    end = len(result.equity_curve) if stop is None else stop
    dates = result.dates[start:end]
    equity = np.asarray(result.equity_curve[start:end], dtype="float64")
    close = np.asarray(result.close[start:end], dtype="float64")
    seg_start = result.dates[start] if dates else None
    seg_end = result.dates[end - 1] if dates else None
    trades = [
        t
        for t in result.trades
        if seg_start is not None and seg_start <= t.date <= (seg_end or "")
    ]

    # Round trips are attributed by bar index over the very same ``[start, end)``
    # bounds this segment was cut with -- the date filter above stays where it
    # is (it is the fill-layer's existing behaviour) but nothing new reads it.
    round_trips = attribute_round_trips(result, start=start, stop=end)

    strategy_metrics = _metrics(
        label=f"{label}:strategy",
        dates=dates,
        equity=equity,
        trades=trades,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
        round_trip=round_trips.stats,
    )
    bh_equity = _buy_and_hold_equity(close, result.initial_cash)
    bh_metrics = _metrics(
        label=f"{label}:buy_and_hold",
        dates=dates,
        equity=bh_equity,
        trades=[],
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
        round_trip=None,
    )
    return SegmentReport(strategy=strategy_metrics, buy_and_hold=bh_metrics)


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
    in_sample = build_segment_report(
        result,
        label="in_sample",
        start=folds[0].train_start,
        stop=folds[0].train_stop,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
    )
    out_of_sample = build_segment_report(
        result,
        label="out_of_sample",
        start=folds[0].test_start,
        stop=folds[-1].test_stop,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
    )
    return WalkForwardReport(in_sample=in_sample, out_of_sample=out_of_sample)
