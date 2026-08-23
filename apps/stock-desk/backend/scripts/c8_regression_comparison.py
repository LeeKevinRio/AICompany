"""C8 regression comparison: pre-fix fill-layer stats vs post-fix round-trip stats.

The C8 fix changed the statistical unit of the report's ``win_rate`` /
``profit_factor`` from closing fills to complete holding round trips (supplied
by ``app.backtest.episodes``). This script reproduces the **legacy** fill-layer
numbers exactly as ``report._trade_stats`` computed them before the fix, runs
the **fixed** report, and prints both side by side for representative seeded
random-walk runs -- the same walk convention the test suite uses
(``tests/test_api_kelly_import.py``).

It also derives the D9 §2.1 diagnostics: the fill-layer vs round-trip win rate
gap in percentage points, the payoff-ratio pair, and the Kelly fraction each
layer would imply (via the one ``kelly_fraction`` in ``app.advice.limits``),
so the "21pp / 50% cap" magnitude claim can be checked against this engine.

Run from ``apps/stock-desk/backend``:

    uv run python scripts/c8_regression_comparison.py

The Markdown it prints is the source of ``work/C8-修復回歸對照.md``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import fmean

from app.advice.limits import kelly_fraction
from app.backtest.costs import CostModel
from app.backtest.engine import BacktestResult, Trade, run_backtest
from app.backtest.episodes import attribute_round_trips
from app.backtest.report import build_segment_report
from app.backtest.splits import walk_forward_splits
from app.backtest.strategies import build_strategy
from app.signals.frame import bars_to_frame
from tests.signals_helpers import bars_from_closes

BARS = 4_000
TRAIN_SIZE = 120
TEST_SIZE = 60

#: Same deterministic walk convention as tests/test_api_kelly_import.py.
WALK = {"seed": 14, "drift": 0.0004, "vol": 0.03}

STRATEGIES = ("ma_cross", "rsi_reversal", "breakout")


def _walk(*, seed: int, drift: float, vol: float, bars: int = BARS) -> list[float]:
    """A deterministic lognormal-ish walk: wins and losses in the same run."""
    rnd = random.Random(seed)
    price = 100.0
    closes = [price]
    for _ in range(bars - 1):
        price = max(price * (1.0 + rnd.gauss(drift, vol)), 1.0)
        closes.append(round(price, 4))
    return closes


@dataclass(frozen=True)
class FillLayerStats:
    """The pre-C8 legacy numbers, reproduced verbatim for comparison only."""

    win_rate: float | None
    profit_factor: float | None
    payoff_ratio: float | None
    num_closing: int


def legacy_fill_stats(trades: list[Trade]) -> FillLayerStats:
    """Exactly what ``report._trade_stats`` returned before the C8 fix.

    (Plus the fill-layer payoff ratio D9 §2.1 measured, which the report never
    published but the pollution analysis relies on.)
    """
    realized = [t.realized_pnl for t in trades if t.realized_pnl is not None]
    if not realized:
        return FillLayerStats(None, None, None, 0)
    wins = [p for p in realized if p > 0]
    losses = [p for p in realized if p < 0]
    win_rate = len(wins) / len(realized)
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    payoff = fmean(wins) / -fmean(losses) if wins and losses else None
    return FillLayerStats(win_rate, profit_factor, payoff, len(realized))


def _segment_trades(result: BacktestResult, start: int, stop: int) -> list[Trade]:
    """The very date filter ``build_segment_report`` applies to fills."""
    dates = result.dates[start:stop]
    if not dates:
        return []
    seg_start, seg_end = dates[0], dates[-1]
    return [t for t in result.trades if seg_start <= t.date <= seg_end]


def _fmt(value: float | None, digits: int = 3) -> str:
    return "None" if value is None else f"{value:.{digits}f}"


def _pp(new: float | None, old: float | None) -> str:
    if new is None or old is None:
        return "n/a"
    return f"{(new - old) * 100.0:+.1f}pp"


def _cap_ratio(f_new: float | None, f_old: float | None) -> str:
    """Relative change of the implied (floored-at-zero) Kelly cap."""
    if f_new is None or f_old is None:
        return "n/a"
    capped_old, capped_new = max(f_old, 0.0), max(f_new, 0.0)
    if capped_old == 0.0:
        return "n/a (old cap 0)"
    return f"{(capped_new / capped_old - 1.0) * 100.0:+.0f}%"


def _report_run(strategy_id: str) -> None:
    closes = _walk(**WALK)  # type: ignore[arg-type]  # scalar kwargs
    frame = bars_to_frame(bars_from_closes(closes))
    strategy = build_strategy(strategy_id)
    result = run_backtest(frame, strategy, initial_cash=1_000_000.0, cost_model=CostModel())

    folds = walk_forward_splits(len(closes), train_size=TRAIN_SIZE, test_size=TEST_SIZE)
    segments = {
        "full": (0, len(result.equity_curve)),
        "oos": (folds[0].test_start, folds[-1].test_stop),
    }
    for name, (start, stop) in segments.items():
        report = build_segment_report(result, label=name, start=start, stop=stop)
        new = report.strategy
        old = legacy_fill_stats(_segment_trades(result, start, stop))
        trips = attribute_round_trips(result, start=start, stop=stop)
        b_new = trips.stats.round_trip_payoff_ratio
        f_old = (
            kelly_fraction(old.win_rate, old.payoff_ratio)
            if old.win_rate is not None and old.payoff_ratio is not None
            else None
        )
        f_new = (
            kelly_fraction(new.win_rate, b_new)
            if new.win_rate is not None and b_new is not None
            else None
        )
        assert new.win_rate == new.round_trip_win_rate  # C8 single-source invariant
        print(
            f"| {strategy_id} | {name} | "
            f"{old.num_closing} | {trips.stats.n} | "
            f"{_fmt(old.win_rate)} | {_fmt(new.win_rate)} | {_pp(new.win_rate, old.win_rate)} | "
            f"{_fmt(old.profit_factor)} | {_fmt(new.profit_factor)} | "
            f"{_fmt(old.payoff_ratio)} | {_fmt(b_new)} | "
            f"{_fmt(f_old)} | {_fmt(f_new)} | {_cap_ratio(f_new, f_old)} |"
        )


def main() -> None:
    print(
        f"Walk: seed={WALK['seed']}, drift={WALK['drift']}, vol={WALK['vol']}, "
        f"bars={BARS}; cost model: default TW; walk-forward "
        f"train={TRAIN_SIZE}/test={TEST_SIZE}."
    )
    print()
    print(
        "| strategy | segment | closing fills | round trips | "
        "win_rate 舊(fill) | win_rate 新(回合) | Δp | "
        "PF 舊(fill) | PF 新(回合) | b 舊(fill) | b 新(回合) | "
        "f* 舊 | f* 新 | 額度變化 |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for strategy_id in STRATEGIES:
        _report_run(strategy_id)


if __name__ == "__main__":
    main()
