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

import numpy as np
from pydantic import BaseModel, ConfigDict

from app.backtest.engine import BacktestResult, Trade
from app.backtest.episodes import RoundTripAttribution, attribute_round_trips
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
    bh_equity = _buy_and_hold_equity(close, result.initial_cash)
    bh_metrics = _metrics(
        label=f"{label}:buy_and_hold",
        dates=dates,
        equity=bh_equity,
        trades=[],
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
        round_trips=None,
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
