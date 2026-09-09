"""Tests for the five-condition event study (CEO 2026-09-09 回測).

Three things are pinned here, in order of importance:

1. **No look-ahead on the event side.** Which bars count as events must be a
   function of the past only: appending later bars may not change an earlier
   verdict, and the events found are exactly the strategy's own
   ``all_met`` bars (one definition, not two).
2. **The arithmetic.** Forward returns, the horizon truncation at the end of the
   series, the greedy non-overlapping subsample, the quartiles and the Wilson
   interval -- each against a hand-checkable case.
3. **The disclosures.** The rendered report has to carry the sentences that make
   the numbers readable (the excluded sixth condition, the overlap caveat, the
   demo-data warning) and must not carry directive wording.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.backtest.event_study import (
    FOOTNOTES,
    HORIZONS,
    format_report,
    forward_returns,
    non_overlapping_indices,
    run_event_study,
    summarise_horizon,
)
from app.backtest.strategies import five_condition_series
from app.signals.frame import bars_to_frame
from tests.signals_helpers import bars_from_closes
from tests.test_backtest_strategies import _FIVE_CLOSES, _FIVE_VOLUMES


def _frame(n: int | None = None) -> pd.DataFrame:
    closes = _FIVE_CLOSES if n is None else _FIVE_CLOSES[:n]
    volumes = _FIVE_VOLUMES if n is None else _FIVE_VOLUMES[:n]
    return bars_to_frame(bars_from_closes(closes, volumes=volumes))


# --- forward returns ----------------------------------------------------------


def test_forward_returns_are_close_to_close_and_stop_at_the_series_end() -> None:
    close = np.asarray([100.0, 110.0, 121.0, 121.0], dtype="float64")
    values = forward_returns(close, 2)
    assert values[0] == pytest.approx(0.21)
    assert values[1] == pytest.approx(0.1)
    # The last two bars have no bar two ahead: undefined, never measured over a
    # shorter distance under the same label.
    assert np.isnan(values[2:]).all()


def test_forward_returns_of_a_series_shorter_than_the_horizon_are_all_undefined() -> None:
    assert np.isnan(forward_returns(np.asarray([100.0, 101.0]), 5)).all()


def test_forward_returns_rejects_a_non_positive_horizon() -> None:
    with pytest.raises(ValueError):
        forward_returns(np.asarray([100.0, 101.0]), 0)


# --- overlap handling ---------------------------------------------------------


def test_non_overlapping_subsample_skips_events_inside_the_horizon() -> None:
    # Greedy from the earliest: 0 is kept, 3 and 4 fall inside its 5-bar window,
    # 5 is exactly one horizon later and is kept.
    assert non_overlapping_indices([0, 3, 4, 5, 9, 11], 5) == [0, 5, 11]
    # Horizon 1 excludes nothing: every window is one bar wide.
    assert non_overlapping_indices([0, 1, 2], 1) == [0, 1, 2]


def test_non_overlapping_subsample_is_order_independent() -> None:
    assert non_overlapping_indices([11, 0, 5, 4, 3, 9], 5) == [0, 5, 11]


# --- horizon statistics -------------------------------------------------------


def test_summarise_horizon_reports_the_distribution_and_both_samples() -> None:
    returns = np.asarray([0.10, -0.20, 0.30, 0.40, np.nan], dtype="float64")
    stats = summarise_horizon(returns, [0, 1, 2, 3, 4], horizon=2)
    # Bar 4 has no outcome and is dropped rather than counted as a zero.
    assert stats.n == 4
    assert stats.n_positive == 3
    assert stats.positive_rate == pytest.approx(0.75)
    assert stats.median == pytest.approx(0.20)
    assert stats.q1 == pytest.approx(0.025)
    assert stats.q3 == pytest.approx(0.325)
    interval = stats.positive_interval
    assert interval is not None
    assert interval.low < 0.75 < interval.high
    # Non-overlapping at horizon 2 over indices 0..3 keeps 0 and 2.
    assert stats.independent_n == 2
    assert stats.independent_positive_rate == pytest.approx(1.0)


def test_summarise_horizon_on_an_empty_sample_reports_nothing_rather_than_zero() -> None:
    stats = summarise_horizon(np.asarray([np.nan, np.nan]), [0, 1], horizon=1)
    assert stats.n == 0
    assert stats.median is None
    assert stats.positive_rate is None
    assert stats.positive_interval is None
    assert stats.independent_positive_rate is None


# --- the study ----------------------------------------------------------------


def test_events_are_exactly_the_strategy_five_condition_bars() -> None:
    frame = _frame()
    expected = int(five_condition_series(frame).all_met.sum())
    report = run_event_study(frame, symbol="TEST")
    full = report.periods[0]
    assert full.label == "全期"
    assert full.n_events == expected > 0
    # The two halves partition the same events, no bar counted twice.
    assert report.periods[1].n_events + report.periods[2].n_events == expected


def test_the_split_is_by_bar_position_and_the_halves_tile_the_series() -> None:
    frame = _frame()
    report = run_event_study(frame, symbol="TEST")
    full, first, second = report.periods
    assert (first.start_index, first.stop_index) == (0, report.split_index)
    assert (second.start_index, second.stop_index) == (report.split_index, report.n_bars)
    assert first.n_bars + second.n_bars == full.n_bars == len(frame)
    assert first.end_date is not None and second.start_date is not None
    assert first.end_date < second.start_date


def test_event_verdicts_do_not_change_when_later_bars_arrive() -> None:
    # The look-ahead guard of this module: an event is a statement about bars up
    # to and including its own, so truncating the future must leave every earlier
    # verdict untouched. (Only the *outcomes* shrink, which the next test pins.)
    frame = _frame()
    cut = 300
    whole = five_condition_series(frame).all_met[:cut]
    truncated = five_condition_series(frame.iloc[:cut].copy()).all_met
    assert np.array_equal(whole, truncated)


def test_sample_size_shrinks_with_the_horizon_at_the_end_of_the_series() -> None:
    report = run_event_study(_frame(), symbol="TEST")
    baseline = report.periods[0].baseline.horizons
    sizes = [stats.n for stats in baseline]
    assert sizes == sorted(sizes, reverse=True)
    for stats in baseline:
        assert stats.n == report.periods[0].baseline.n_bars - stats.horizon


def test_the_baseline_covers_every_bar_of_the_period() -> None:
    report = run_event_study(_frame(), symbol="TEST")
    for period in report.periods:
        assert period.baseline.n_bars == period.n_bars
        assert period.events.n_bars == period.n_events


def test_a_series_shorter_than_the_warmup_yields_no_events_but_still_reports() -> None:
    report = run_event_study(_frame(40), symbol="TEST")
    assert report.n_bars == 40
    for period in report.periods:
        assert period.n_events == 0
        for stats in period.events.horizons:
            assert stats.n == 0
            assert stats.positive_rate is None


def test_an_empty_frame_is_a_report_with_nothing_in_it_not_a_crash() -> None:
    report = run_event_study(bars_to_frame([]), symbol="TEST")
    assert report.n_bars == 0
    assert report.first_date is None
    assert all(period.n_events == 0 for period in report.periods)
    assert report.periods[0].event_rate is None


def test_horizons_are_the_ones_the_ceo_asked_about() -> None:
    assert HORIZONS == (5, 10, 20, 60)
    report = run_event_study(_frame(), symbol="TEST")
    for period in report.periods:
        assert tuple(s.horizon for s in period.events.horizons) == HORIZONS


# --- rendering ----------------------------------------------------------------


def test_the_report_carries_every_disclosure_and_flags_demo_data() -> None:
    report = run_event_study(_frame(), symbol="2330", source="demo_synthetic")
    text = format_report(report)
    for note in FOOTNOTES:
        assert note in text
    assert "第 6 條" in text
    assert "demo_synthetic" in text
    assert "不是市場資料" in text
    assert "非重疊子樣本" in text
    assert "Wilson 95%" in text


def test_the_report_states_its_source_and_does_not_invent_one() -> None:
    text = format_report(run_event_study(_frame(), symbol="2330", source=None))
    assert "資料來源：未知" in text
    assert "demo_synthetic" not in text


def test_the_report_never_uses_directive_or_price_target_wording() -> None:
    # 紅線: this is a研究 output. It describes a distribution and its
    # uncertainty; it does not tell anyone to do anything and never names a
    # single price to aim at.
    text = format_report(run_event_study(_frame(), symbol="2330", source="demo_synthetic"))
    # 「建議引擎」 (the advice engine) is a module name, and 「不是對未來的機率」 is a
    # denial, so the scan lists directive *phrases* rather than lone characters
    # that a truthful negation would trip over.
    for forbidden in (
        "目標價",
        "買進",
        "賣出",
        "可以進場",
        "建議買",
        "建議賣",
        "應該",
        "勝率",
        "必漲",
        "必跌",
        "保證獲利",
    ):
        assert forbidden not in text, forbidden
