"""Event-driven, point-in-time daily backtester.

Backtest-protocol rule 1 (no look-ahead) is enforced *structurally*, not by
convention: on day ``t`` the strategy is handed a **copy of the history sliced
at ``iloc[: t + 1]``** -- the current bar and everything before it, nothing
after. A strategy that tries to index tomorrow's bar simply finds it absent, so
future leakage is impossible by construction rather than by reviewer diligence
(the look-ahead detection tests exploit exactly this).

Timing convention (a single, explicit rule):

* At the close of day ``t`` the strategy sees closes up to and including ``t``
  and returns a **target weight** = desired fraction of current equity held in
  the asset.
* The portfolio rebalances to that weight at day ``t``'s close, paying costs.
* The resulting position then earns day ``t+1``'s price move. A weight decided
  on day ``t`` therefore never earns day ``t``'s own (already-realized) move --
  the classic same-bar look-ahead trap.

Cash may go slightly negative when a fully-invested target is combined with
costs; this is modelled honestly (a tiny financing drag) rather than hidden by
clipping. Average cost tracking includes buy-side fees so that, whenever the
book returns flat, cumulative realized P&L equals the change in equity exactly
(an invariant the golden test pins).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from app.backtest.costs import CostModel
from app.positions.models import InstrumentType, Market
from app.signals.frame import CLOSE

#: A strategy maps a point-in-time history window to a target weight (fraction of
#: equity in the asset). It must read only the rows it is given.
Strategy = Callable[[pd.DataFrame], float]


@dataclass(frozen=True)
class Trade:
    """One executed rebalance fill.

    ``bar_index`` is the position of the fill in the run's own bar sequence, so
    ``dates[bar_index] == date`` always holds. It is required (no default)
    because every consumer that has to place a fill inside a window -- the
    walk-forward geometry above all -- must do so by index: comparing date
    *strings* against a segment's endpoints re-derives the geometry from the
    report and drifts the moment a calendar gap or a rebuilt bar set appears.
    """

    date: str
    bar_index: int
    side: str  # "buy" or "sell"
    shares: float
    price: float
    notional: float
    cost: float
    realized_pnl: float | None  # populated on position-reducing fills only


@dataclass
class BacktestResult:
    """Outputs of a single backtest run over one asset.

    ``equity_curve`` is the end-of-day equity per bar (same length/index as the
    input frame); ``weights`` is the post-rebalance target weight per day.
    """

    dates: list[str]
    equity_curve: list[float]
    close: list[float]
    weights: list[float]
    trades: list[Trade] = field(default_factory=list)
    initial_cash: float = 0.0
    market: Market = "TW"
    instrument_type: InstrumentType = "stock"

    @property
    def equity_series(self) -> pd.Series:
        """Equity curve as a date-indexed Series (for the reporting layer)."""
        return pd.Series(
            self.equity_curve,
            index=pd.DatetimeIndex([pd.Timestamp(d) for d in self.dates], name="date"),
        )

    @property
    def close_series(self) -> pd.Series:
        """Close path as a date-indexed Series (for the Buy & Hold benchmark)."""
        return pd.Series(
            self.close,
            index=pd.DatetimeIndex([pd.Timestamp(d) for d in self.dates], name="date"),
        )


def run_backtest(
    frame: pd.DataFrame,
    strategy: Strategy,
    *,
    initial_cash: float = 1_000_000.0,
    cost_model: CostModel | None = None,
    market: Market = "TW",
    instrument_type: InstrumentType = "stock",
    max_weight: float = 1.0,
) -> BacktestResult:
    """Run the strategy over ``frame`` (an OHLCV frame from ``bars_to_frame``).

    ``strategy`` receives, each day, a copy of the history sliced at that day and
    returns a target weight, clipped to ``[0, max_weight]`` (long-only). Returns
    a :class:`BacktestResult` with the daily equity curve, weights and trades.
    """
    costs = cost_model or CostModel()
    if frame.empty:
        return BacktestResult(
            dates=[],
            equity_curve=[],
            close=[],
            weights=[],
            initial_cash=initial_cash,
            market=market,
            instrument_type=instrument_type,
        )

    close = frame[CLOSE]
    dates = [ts.date().isoformat() for ts in frame.index]

    cash = initial_cash
    shares = 0.0
    cost_basis = 0.0  # total cost (incl. buy fees) of the shares currently held

    equity_curve: list[float] = []
    weights: list[float] = []
    trades: list[Trade] = []

    for t in range(len(frame)):
        # Point-in-time: the strategy sees only [0 .. t]. The copy prevents any
        # accidental (or deliberate) mutation or peeking beyond the slice.
        window = frame.iloc[: t + 1].copy()
        raw_weight = strategy(window)
        target_weight = _clip(raw_weight, low=0.0, high=max_weight)

        price = float(close.iloc[t])
        current_value = shares * price
        equity = cash + current_value
        target_value = target_weight * equity
        delta_value = target_value - current_value

        if abs(delta_value) > 1e-12 and price > 0.0:
            trade_shares = delta_value / price
            side = "buy" if trade_shares > 0 else "sell"
            cost = costs.trade_cost(
                notional=abs(delta_value),
                side=side,  # type: ignore[arg-type]  # side is exactly "buy"/"sell"
                market=market,
                instrument_type=instrument_type,
            )
            realized_pnl: float | None = None
            if side == "buy":
                cost_basis += abs(delta_value) + cost
            else:
                sold = -trade_shares  # positive number of shares sold
                avg_cost = cost_basis / shares if shares > 0 else 0.0
                basis_removed = avg_cost * sold
                proceeds_net = abs(delta_value) - cost
                realized_pnl = proceeds_net - basis_removed
                cost_basis -= basis_removed
            cash -= delta_value + cost
            shares += trade_shares
            trades.append(
                Trade(
                    date=dates[t],
                    bar_index=t,
                    side=side,
                    shares=trade_shares,
                    price=price,
                    notional=delta_value,
                    cost=cost,
                    realized_pnl=realized_pnl,
                )
            )

        equity_curve.append(cash + shares * price)
        weights.append(target_weight)

    return BacktestResult(
        dates=dates,
        equity_curve=equity_curve,
        close=[float(c) for c in close],
        weights=weights,
        trades=trades,
        initial_cash=initial_cash,
        market=market,
        instrument_type=instrument_type,
    )


def _clip(value: float, *, low: float, high: float) -> float:
    return max(low, min(high, value))
