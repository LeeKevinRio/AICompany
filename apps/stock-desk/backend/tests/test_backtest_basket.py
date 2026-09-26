"""The generic multi-asset basket backtester (ADR-0012 D-13, methodology §5.1).

Timing (t+1 open in, t+H close out, never overlapping), the limit-up-at-open
exclusion and its reference price, the round trip charged to the basket only,
the benchmark never charged, dividend restoration through the injected factor,
the strategy's point-in-time view, and the standard report fields.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date
from typing import cast

import pandas as pd
import pytest

from app.backtest.basket import (
    DISCLOSURE_BENCHMARK_COLUMN,
    DISCLOSURE_COST_UNVERIFIED,
    DISCLOSURE_EXIT_CARRIED,
    DISCLOSURE_REFERENCE_FALLBACK,
    BasketExecution,
    BasketResult,
    BasketSchedule,
    BasketStrategy,
    PriceBook,
    round_trip_cost,
    run_basket_backtest,
)
from app.backtest.costs import CostModel
from app.data.panel import (
    BARS_COLUMNS,
    CLASSIFICATION_COLUMNS,
    EX_DIVIDEND_COLUMNS,
    LISTING_COLUMNS,
    RUNS_COLUMNS,
    MarketPanel,
    PanelFrames,
    PointInTimePanel,
    PointInTimeViolation,
)
from app.positions.models import Market
from tests.sector_eval_helpers import taipei, weekdays

DAYS = weekdays(12)
#: open, close, change per session; NaN change means "no reference in the payload".
Quote = tuple[float, float, float]


def _flat(price: float = 100.0) -> list[Quote | None]:
    return [(price, price, 0.0)] * len(DAYS)


def _panel(quotes: Mapping[str, Sequence[Quote | None]]) -> MarketPanel:
    runs: list[dict[str, object]] = []
    bars: list[dict[str, object]] = []
    for index, day in enumerate(DAYS):
        run_id = f"b{index:03d}"
        runs.append(
            {
                "run_id": run_id,
                "kind": "bars",
                "session_date": day,
                "recorded_at": taipei(day),
                "source": "twse_snapshot",
                "status": "ok",
                "row_count": len(quotes),
                "expected_count": len(quotes),
            }
        )
        for symbol, series in quotes.items():
            quote = series[index]
            if quote is None:
                continue
            open_, close, change = quote
            bars.append(
                {
                    "run_id": run_id,
                    "session_date": day,
                    "recorded_at": taipei(day),
                    "source": "twse_snapshot",
                    "symbol": symbol,
                    "open": open_,
                    "high": max(open_, close),
                    "low": min(open_, close),
                    "close": close,
                    "shares": 1000,
                    "traded_value": 5e7,
                    "change": change,
                }
            )
    return MarketPanel(
        PanelFrames(
            bars=pd.DataFrame(bars, columns=list(BARS_COLUMNS)),
            listing=pd.DataFrame(columns=list(LISTING_COLUMNS)),
            classification=pd.DataFrame(columns=list(CLASSIFICATION_COLUMNS)),
            ex_dividend=pd.DataFrame(columns=list(EX_DIVIDEND_COLUMNS)),
            runs=pd.DataFrame(runs, columns=list(RUNS_COLUMNS)),
        )
    )


def _const(weights: Mapping[str, float]) -> BasketStrategy:
    def strategy(view: PointInTimePanel) -> Mapping[str, float]:
        return weights

    return strategy


def _schedule(decisions: Sequence[int], holding: int = 2) -> BasketSchedule:
    return BasketSchedule(
        decision_dates=tuple(DAYS[i] for i in decisions),
        holding_days=holding,
        calendar=tuple(DAYS),
    )


COST = CostModel()
EXECUTION = BasketExecution()


def _run(
    panel: MarketPanel,
    weights: Mapping[str, float],
    bench: Mapping[str, float],
    *,
    schedule: BasketSchedule | None = None,
    execution: BasketExecution = EXECUTION,
) -> BasketResult:
    return run_basket_backtest(
        panel,
        _const(weights),
        schedule=schedule or _schedule([2]),
        cost_model=COST,
        execution=execution,
        benchmark=_const(bench),
    )


def test_round_trip_cost_comes_from_the_cost_model() -> None:
    market: Market = "TW"
    cost = round_trip_cost(COST, market=market, instrument_type="stock")
    assert cost == pytest.approx(2 * 0.001425 + 0.003)
    slipped = round_trip_cost(CostModel(slippage_bps=10.0), market=market, instrument_type="stock")
    assert slipped == pytest.approx(cost + 2 * 0.001)


def test_enters_at_the_next_open_and_exits_at_the_close_h_sessions_later() -> None:
    a = _flat()
    a[3] = (105.0, 106.0, 6.0)  # t+1 = DAYS[3]: bought at the 105 open
    a[4] = (107.0, 115.5, 9.5)  # t+H = DAYS[4]: sold at the close 115.5
    a[5] = (200.0, 200.0, 84.5)  # after the exit: must not matter
    b = _flat()
    b[4] = (100.0, 101.0, 1.0)
    result = _run(_panel({"A": a, "B": b}), {"A": 1.0}, {"B": 1.0})
    (sample,) = result.samples
    assert (sample.decision_date, sample.entry_date, sample.exit_date) == (
        DAYS[2],
        DAYS[3],
        DAYS[4],
    )
    assert sample.basket is not None and sample.benchmark is not None
    assert sample.basket.basket_return == pytest.approx(115.5 / 105.0 - 1.0)
    assert sample.benchmark.basket_return == pytest.approx(101.0 / 100.0 - 1.0)
    assert sample.excess_gross == pytest.approx(115.5 / 105.0 - 101.0 / 100.0)
    # Diagnostic close t -> close t+H is reported apart and is not the label.
    assert sample.diagnostic_excess_gross == pytest.approx(115.5 / 100.0 - 101.0 / 100.0)


def test_only_the_basket_pays_the_round_trip() -> None:
    a = _flat()
    a[4] = (100.0, 103.0, 3.0)
    result = _run(_panel({"A": a, "B": _flat()}), {"A": 1.0}, {"B": 1.0})
    (sample,) = result.samples
    assert sample.excess_net is not None and sample.excess_gross is not None
    assert sample.excess_gross - sample.excess_net == pytest.approx(result.round_trip_cost)
    assert sample.benchmark is not None and sample.benchmark.basket_return == 0.0


def test_limit_up_at_the_open_is_dropped_and_the_rest_rescaled() -> None:
    a = _flat()
    a[3] = (109.5, 109.5, 9.5)  # reference 100: 109.5 >= 100 x 1.095 -> not buyable
    near = _flat()
    near[3] = (109.49, 109.49, 9.49)  # just below the threshold -> bought
    c = _flat()
    c[4] = (100.0, 102.0, 2.0)
    panel = _panel({"A": a, "N": near, "C": c})
    result = _run(panel, {"A": 1.0, "N": 1.0, "C": 1.0}, {"C": 1.0})
    (sample,) = result.samples
    assert sample.basket is not None
    assert dict(sample.basket.excluded) == {"A": "limit_up_open"}
    assert dict(sample.basket.held) == {"C": 0.5, "N": 0.5}


def test_reference_is_close_minus_change_else_the_previous_close() -> None:
    ex = _flat()
    # Ex-dividend on t+1: reference 95 (close 96 - change 1); open 104.1 >= 95 x 1.095
    # although it sits only 4.1% above the previous close.
    ex[3] = (104.1, 96.0, 1.0)
    unknown = _flat()
    unknown[3] = (104.0, 104.0, math.nan)  # no change: previous close 100 is the reference
    panel = _panel({"X": ex, "U": unknown, "B": _flat()})
    result = _run(panel, {"X": 1.0, "U": 1.0}, {"B": 1.0})
    (sample,) = result.samples
    assert sample.basket is not None
    assert dict(sample.basket.excluded) == {"X": "limit_up_open"}
    assert sample.basket.reference_fallback == frozenset({"U"})
    assert DISCLOSURE_REFERENCE_FALLBACK in result.disclosures


def test_the_strategy_sees_only_the_decision_view() -> None:
    seen: list[date] = []

    def peeking(view: PointInTimePanel) -> Mapping[str, float]:
        seen.append(view.decision_date)
        assert view.regime == "pit"
        assert max(view.sessions) == view.decision_date
        with pytest.raises(PointInTimeViolation):
            view.field_matrix("close", [DAYS[DAYS.index(view.decision_date) + 1]])
        return {"A": 1.0}

    panel = _panel({"A": _flat(), "B": _flat()})
    run_basket_backtest(
        panel,
        peeking,
        schedule=_schedule([2, 4, 6]),
        cost_model=COST,
        execution=EXECUTION,
        benchmark=_const({"B": 1.0}),
    )
    assert seen == [DAYS[2], DAYS[4], DAYS[6]]


def test_future_prices_cannot_change_the_basket() -> None:
    chosen: list[Mapping[str, float]] = []

    def momentum(view: PointInTimePanel) -> Mapping[str, float]:
        closes = view.field_matrix("close", view.sessions[-2:], ["A", "B"])
        pick = "A" if closes["A"].iloc[-1] >= closes["B"].iloc[-1] else "B"
        chosen.append({pick: 1.0})
        return {pick: 1.0}

    base = {"A": _flat(101.0), "B": _flat(100.0)}
    shocked = {"A": list(base["A"]), "B": list(base["B"])}
    shocked["B"][3:] = [(500.0, 500.0, 0.0)] * (len(DAYS) - 3)
    for quotes in (base, shocked):
        run_basket_backtest(
            _panel(quotes),
            momentum,
            schedule=_schedule([2]),
            cost_model=COST,
            execution=EXECUTION,
            benchmark=_const({"A": 1.0, "B": 1.0}),
        )
    assert chosen[0] == chosen[1] == {"A": 1.0}


def test_decisions_must_not_overlap() -> None:
    with pytest.raises(ValueError, match="overlap"):
        _schedule([2, 3], holding=2)
    grid = BasketSchedule.every_holding_period(DAYS, holding_days=3, start=DAYS[1])
    assert grid.decision_dates == (DAYS[1], DAYS[4], DAYS[7])
    windows = [grid.window(day) for day in grid.decision_dates]
    for earlier, later in zip(windows, windows[1:], strict=False):
        assert earlier is not None and later is not None
        # Next decision is at the previous exit close; next entry is strictly later.
        assert later.decision_date == earlier.exit_date
        assert later.entry_date > earlier.exit_date


def test_a_calendar_session_without_bars_invalidates_the_sample() -> None:
    a = _flat()
    b = _flat()
    a[4] = b[4] = None  # nobody traded / nothing captured on t+2
    result = _run(_panel({"A": a, "B": b}), {"A": 1.0}, {"B": 1.0})
    assert [s.status for s in result.samples] == ["bars_gap"]
    assert result.valid_samples == ()


def test_an_empty_decision_is_not_a_sample() -> None:
    result = _run(_panel({"A": _flat(), "B": _flat()}), {}, {"B": 1.0})
    assert [s.status for s in result.samples] == ["empty_basket"]


def test_restoration_factor_multiplies_the_holding_return() -> None:
    a = _flat()
    a[4] = (97.0, 97.0, -3.0)  # a 3.00 dividend went ex on t+2

    def factor(symbol: str, after: date, through: date) -> float | None:
        if symbol == "A" and after < DAYS[4] <= through:
            return 100.0 / 97.0
        if symbol == "Z" and after < DAYS[4] <= through:
            return None  # an event without a usable factor
        return 1.0

    execution = BasketExecution(adjustment=factor)
    panel = _panel({"A": a, "Z": _flat(), "B": _flat()})
    result = _run(panel, {"A": 1.0, "Z": 1.0}, {"B": 1.0}, execution=execution)
    (sample,) = result.samples
    assert sample.basket is not None
    assert dict(sample.basket.excluded) == {"Z": "label_factor_unavailable"}
    assert sample.basket.basket_return == pytest.approx(0.0)


def test_exit_is_carried_from_the_last_close_when_the_exit_bar_is_missing() -> None:
    a = _flat()
    a[3] = (100.0, 104.0, 4.0)
    a[4] = None  # suspended on the exit session
    b = _flat()
    result = _run(_panel({"A": a, "B": b}), {"A": 1.0}, {"B": 1.0})
    (sample,) = result.samples
    assert sample.basket is not None
    assert sample.basket.exit_carried == frozenset({"A"})
    assert sample.basket.basket_return == pytest.approx(0.04)
    assert DISCLOSURE_EXIT_CARRIED in result.disclosures


def test_standard_report_carries_every_protocol_field() -> None:
    a = _flat()
    for index in range(3, len(DAYS)):
        a[index] = (100.0 + index, 101.0 + index, 1.0)
    result = _run(
        _panel({"A": a, "B": _flat()}),
        {"A": 1.0},
        {"B": 1.0},
        schedule=_schedule([1, 3, 5, 7]),
    )
    strategy = result.report.strategy
    assert len(result.valid_samples) == 4
    assert strategy.num_round_trips == 4
    for name in (
        "cagr",
        "annualized_volatility",
        "sharpe",
        "max_drawdown",
        "win_rate",
        "turnover",
        "total_return",
    ):
        assert getattr(strategy, name) is not None, name
    assert result.report.buy_and_hold.observations == strategy.observations
    assert DISCLOSURE_BENCHMARK_COLUMN in result.disclosures
    assert DISCLOSURE_COST_UNVERIFIED in result.disclosures
    assert result.cost_verified_on is None


def test_price_book_reads_corrections_recorded_after_the_session() -> None:
    panel = _panel({"A": _flat(), "B": _flat()})
    frames = panel.frames
    late_run = pd.DataFrame(
        [
            {
                "run_id": "late",
                "kind": "bars",
                "session_date": DAYS[4],
                "recorded_at": taipei(DAYS[6], 9),
                "source": "twse_snapshot",
                "status": "ok",
                "row_count": 1,
                "expected_count": 1,
            }
        ]
    )
    late_bar = frames.bars.loc[frames.bars["session_date"] == DAYS[4]].iloc[[0]].copy()
    late_bar["run_id"] = "late"
    late_bar["recorded_at"] = taipei(DAYS[6], 9)
    late_bar["close"] = 123.0
    corrected = MarketPanel(
        PanelFrames(
            bars=pd.concat([frames.bars, late_bar], ignore_index=True),
            listing=frames.listing,
            classification=frames.classification,
            ex_dividend=frames.ex_dividend,
            runs=pd.concat([frames.runs, late_run], ignore_index=True),
        )
    )
    book = PriceBook.from_panel(corrected)
    symbol = str(late_bar["symbol"].iloc[0])
    assert book.value(book.close, symbol, DAYS[4]) == 123.0
    # ...while the decision view of that session does not see it yet.
    view = corrected.as_of(DAYS[4])
    # field_matrix is a float matrix; the stubs type an .iloc cell as Scalar.
    assert float(cast(float, view.field_matrix("close", [DAYS[4]], [symbol]).iloc[0, 0])) == 100.0
