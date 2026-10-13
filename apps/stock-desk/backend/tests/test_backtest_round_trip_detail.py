"""F-11 report-layer assembly: ``walk_forward_round_trip_detail`` and its decisions.

Covers the invariants tech-architect requires of the sibling block
(F11-A-20 (a)-(f), A-40 (e) (g) (i)), the attribution scenarios of AC-16 (i)-(vi)
at r = 0 and r > 0 (quant's n = 360 / r = 45 geometry), the empty-state truth
table of F11-A-54 with its two boundary cases, the sample flag edge, the Buy &
Hold in-market value of F11-A-13(b), and F11-A-43: nothing
``walk_forward_report`` accepts makes this assembly raise.
"""

from __future__ import annotations

import inspect
import random
from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from app.api.backtest_wording import build_round_trip_labels
from app.backtest.costs import CostModel
from app.backtest.display_params import N_MIN_DISPLAY, N_WORST
from app.backtest.engine import BacktestResult, Trade, run_backtest
from app.backtest.episodes import (
    RoundTripAttribution,
    RoundTripStats,
    attribute_round_trips,
    extract_episodes,
    held_mask,
    in_market_intervals,
)
from app.backtest.report import (
    SegmentRoundTripDetail,
    WalkForwardRoundTripDetail,
    round_trip_empty_state,
    walk_forward_curves,
    walk_forward_report,
    walk_forward_round_trip_detail,
)
from app.backtest.splits import WalkForwardFold, walk_forward_splits
from app.backtest.strategies import STRATEGY_IDS, STRATEGY_WARMUP_BARS, build_strategy
from app.signals.frame import bars_to_frame
from tests.import_graph import reachable_app_modules
from tests.test_golden_backtest_outputs import _REPORT_WALK, _walk_bars

TRAIN = 252
TEST = 63
#: quant §5.8: n = 360 leaves a 45-bar tail; n = 315 leaves none.
N_TAIL = 360
N_NO_TAIL = 315
SEGMENTS = ("in_sample", "out_of_sample")
ROW_KEYS = {"entry_date", "exit_date", "holding_bars", "return_on_entry_equity", "realized_pnl"}


# --------------------------------------------------------------------------
# Synthetic runs: one position, one fill in and one fill out per round trip
# --------------------------------------------------------------------------


def _dates(bars: int) -> list[str]:
    return [(date(2020, 1, 1) + timedelta(days=t)).isoformat() for t in range(bars)]


def _run(
    bars: int,
    spans: list[tuple[int, int, float]],
    *,
    open_entry: int | None = None,
    closes: list[float] | None = None,
) -> BacktestResult:
    """A run whose round trips are exactly ``spans`` (entry, exit, return)."""
    equity = 1_000_000.0
    trades: list[Trade] = []
    weights = [0.0] * bars
    dates = _dates(bars)
    for entry, exit_, ret in spans:
        trades.append(Trade(dates[entry], entry, "buy", 100.0, 100.0, 10_000.0, 0.0, None))
        trades.append(
            Trade(dates[exit_], exit_, "sell", -100.0, 100.0, -10_000.0, 0.0, ret * equity)
        )
        for t in range(entry, exit_):
            weights[t] = 1.0
    if open_entry is not None:
        trades.append(
            Trade(dates[open_entry], open_entry, "buy", 100.0, 100.0, 10_000.0, 0.0, None)
        )
        for t in range(open_entry, bars):
            weights[t] = 1.0
    trades.sort(key=lambda trade: trade.bar_index)
    return BacktestResult(
        dates=dates,
        equity_curve=[equity] * bars,
        close=closes if closes is not None else [100.0] * bars,
        weights=weights,
        trades=trades,
        initial_cash=equity,
    )


def _folds(bars: int, *, train: int = TRAIN, test: int = TEST) -> list[WalkForwardFold]:
    folds = walk_forward_splits(bars, train_size=train, test_size=test)
    assert folds
    return folds


def _detail(
    result: BacktestResult, folds: list[WalkForwardFold], warmup: int = 0
) -> WalkForwardRoundTripDetail:
    return walk_forward_round_trip_detail(result, folds, warmup_bars=warmup)


def _segment(detail: WalkForwardRoundTripDetail, name: str) -> SegmentRoundTripDetail:
    segment: SegmentRoundTripDetail = getattr(detail, name)
    return segment


def _bounds(folds: list[WalkForwardFold], name: str) -> tuple[int, int]:
    if name == "in_sample":
        return folds[0].train_start, folds[0].train_stop
    return folds[0].test_start, folds[-1].test_stop


def _intervals(detail_segment: SegmentRoundTripDetail, start: int, stop: int) -> int | None:
    """Recover the integer count behind the shipped ratio."""
    if detail_segment.in_market_ratio is None:
        return None
    return round(detail_segment.in_market_ratio * (stop - start - 1))


def _standard(strategy_id: str) -> tuple[BacktestResult, list[WalkForwardFold]]:
    """The golden fixture with the golden geometry (train 120 / test 60, r = 40)."""
    frame = bars_to_frame(_walk_bars(_REPORT_WALK))
    result = run_backtest(frame, build_strategy(strategy_id), cost_model=CostModel())
    return result, _folds(len(frame), train=120, test=60)


# --------------------------------------------------------------------------
# AC-16 (i)-(vi) at r = 0 and r > 0, with F11-A-20(f) and F11-W-25 on each
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Case:
    name: str
    bars: int
    spans: tuple[tuple[int, int, float], ...]
    open_entry: int | None
    #: (excluded_boundary_trips, open_trip_at_end) per segment.
    in_sample: tuple[int, int]
    out_of_sample: tuple[int, int]


_AC16 = (
    _Case("i r=0", N_NO_TAIL, ((240, 260, 0.01),), None, (1, 0), (1, 0)),
    _Case("i r>0", N_TAIL, ((240, 260, 0.01),), None, (1, 0), (1, 0)),
    _Case("ii r=0", N_NO_TAIL, (), 200, (0, 1), (0, 1)),
    _Case("ii r>0", N_TAIL, (), 200, (0, 1), (0, 1)),
    _Case("iii r>0", N_TAIL, ((300, 330, -0.02),), None, (0, 0), (1, 0)),
    _Case("iv r=0", N_NO_TAIL, (), 300, (0, 0), (0, 1)),
    _Case("iv r>0", N_TAIL, (), 300, (0, 0), (0, 1)),
    _Case("v r>0", N_TAIL, (), 330, (0, 0), (0, 0)),
    _Case("vi r>0", N_TAIL, ((320, 340, 0.03),), None, (0, 0), (0, 0)),
    # The same exclusions beside contained round trips on both sides.
    _Case(
        "i+contained r>0",
        N_TAIL,
        ((100, 110, 0.02), (240, 260, 0.01), (270, 280, -0.01), (330, 350, 0.05)),
        None,
        (1, 0),
        (1, 0),
    ),
)


@pytest.mark.parametrize("case", _AC16, ids=lambda case: case.name)
def test_ac16_attribution_counts_per_segment(case: _Case) -> None:
    result = _run(case.bars, list(case.spans), open_entry=case.open_entry)
    folds = _folds(case.bars)
    detail = _detail(result, folds)
    report = walk_forward_report(result, folds)
    for name, expected in (("in_sample", case.in_sample), ("out_of_sample", case.out_of_sample)):
        segment = _segment(detail, name)
        assert (segment.excluded_boundary_trips, segment.open_trip_at_end) == expected, name
        # F11-W-25: both counts are non-negative integers, never absent.
        for count in (segment.excluded_boundary_trips, segment.open_trip_at_end):
            assert type(count) is int and count >= 0
        # F11-A-20(f) / A-51: the sibling block and the table count one window.
        assert segment.num_round_trips == getattr(report, name).strategy.num_round_trips
        assert segment.num_round_trips == len(segment.round_trips)
    # (vi): a round trip wholly inside the tail is in no list at all.
    listed = {
        (row.entry_date, row.exit_date)
        for name in SEGMENTS
        for row in _segment(detail, name).round_trips
    }
    dates = result.dates
    for entry, exit_, _ in case.spans:
        contained = (entry >= 0 and exit_ < TRAIN) or (entry >= TRAIN and exit_ < TRAIN + TEST)
        assert ((dates[entry], dates[exit_]) in listed) == contained


def test_the_exclusion_counts_are_typed_as_plain_integers() -> None:
    """F11-W-25(c): a null count would be a contract error, so the type cannot carry one."""
    fields = SegmentRoundTripDetail.model_fields
    assert fields["excluded_boundary_trips"].annotation is int
    assert fields["open_trip_at_end"].annotation is int
    assert fields["num_round_trips"].annotation is int


# --------------------------------------------------------------------------
# F11-A-20 (a)-(c), (f), F11-A-18 and the list rows on every shipped strategy
# --------------------------------------------------------------------------


@pytest.mark.parametrize("strategy_id", STRATEGY_IDS)
def test_list_invariants_on_the_standard_fixture(strategy_id: str) -> None:
    result, folds = _standard(strategy_id)
    detail = _detail(result, folds, STRATEGY_WARMUP_BARS[strategy_id])
    report = walk_forward_report(result, folds)
    traded = 0
    for name in SEGMENTS:
        segment = _segment(detail, name)
        start, stop = _bounds(folds, name)
        attribution = attribute_round_trips(result, start=start, stop=stop)
        metrics = getattr(report, name).strategy
        rows = segment.round_trips
        traded += len(rows)
        # (a) list size is the count, which is the table's count (f).
        assert len(rows) == segment.num_round_trips == metrics.num_round_trips
        assert segment.num_winning_round_trips == attribution.stats.n_win
        assert segment.num_losing_round_trips == attribution.stats.n_loss
        # (b) P&L reconciles with the attribution object.
        assert sum(row.realized_pnl for row in rows) == pytest.approx(
            sum(e.realized_pnl for e in attribution.episodes)
        )
        # Rows: exactly five keys, earliest entry first, dates from bar indices.
        for row, episode in zip(rows, attribution.episodes, strict=True):
            assert set(row.model_dump()) == ROW_KEYS
            assert row.entry_date == result.dates[episode.entry_idx]
            assert row.exit_date == result.dates[episode.exit_idx]
            assert row.holding_bars == episode.exit_idx - episode.entry_idx >= 1
            assert row.return_on_entry_equity == episode.return_on_entry_equity
        assert [row.entry_date for row in rows] == sorted(row.entry_date for row in rows)
        # (c) the lowest rows are a subset, ordered, at most N_WORST of them.
        lowest = segment.lowest_return_round_trips
        assert len(lowest) == min(N_WORST, len(rows))
        assert all(row in rows for row in lowest)
        keys = [(row.return_on_entry_equity, row.entry_date) for row in lowest]
        assert keys == sorted(keys)
        if rows:
            worst_kept = lowest[-1].return_on_entry_equity
            left_out = [row for row in rows if row not in lowest]
            assert all(row.return_on_entry_equity >= worst_kept for row in left_out)
        # F11-A-18: the two means divide to the table's payoff ratio, exactly.
        payoff = metrics.round_trip_payoff_ratio
        if segment.mean_winning_return is None or segment.mean_losing_return is None:
            assert payoff is None
        else:
            assert segment.mean_winning_return / -segment.mean_losing_return == payoff
        # Losing streak against the side counts (D-11).
        streak = segment.longest_losing_streak
        if segment.num_round_trips == 0:
            assert streak is None
        else:
            assert streak is not None
            assert 0 <= streak.length <= segment.num_losing_round_trips
            assert (streak.length == 0) == (segment.num_losing_round_trips == 0)
            assert (streak.start_date is None) == (streak.length == 0)
    assert traded > 0


# --------------------------------------------------------------------------
# F11-A-40 (e): in-market intervals reconcile with holding bars
# --------------------------------------------------------------------------


@pytest.mark.parametrize("strategy_id", STRATEGY_IDS)
def test_in_market_intervals_cover_the_holding_bars(strategy_id: str) -> None:
    result, folds = _standard(strategy_id)
    detail = _detail(result, folds, STRATEGY_WARMUP_BARS[strategy_id])
    held = held_mask(extract_episodes(result), len(result.dates))
    for name in SEGMENTS:
        segment = _segment(detail, name)
        start, stop = _bounds(folds, name)
        intervals = in_market_intervals(held, start=start, stop=stop)
        assert _intervals(segment, start, stop) == intervals
        holding = sum(row.holding_bars for row in segment.round_trips)
        assert intervals >= holding
        if segment.excluded_boundary_trips == 0 and segment.open_trip_at_end == 0:
            assert intervals == holding


@pytest.mark.parametrize("case", _AC16, ids=lambda case: case.name)
def test_in_market_reconciliation_on_the_attribution_scenarios(case: _Case) -> None:
    result = _run(case.bars, list(case.spans), open_entry=case.open_entry)
    folds = _folds(case.bars)
    detail = _detail(result, folds)
    for name in SEGMENTS:
        segment = _segment(detail, name)
        start, stop = _bounds(folds, name)
        intervals = _intervals(segment, start, stop)
        assert intervals is not None
        holding = sum(row.holding_bars for row in segment.round_trips)
        assert intervals >= holding
        if segment.excluded_boundary_trips == 0 and segment.open_trip_at_end == 0:
            assert intervals == holding
        if (
            segment.num_round_trips == 0
            and segment.excluded_boundary_trips == 0
            and segment.open_trip_at_end == 0
        ):
            assert intervals == 0


def test_ac17_buy_and_hold_is_a_definition_and_absent_without_a_path() -> None:
    folds = _folds(N_TAIL)
    detail = _detail(_run(N_TAIL, [(10, 20, 0.01)]), folds)
    for name in SEGMENTS:
        assert _segment(detail, name).buy_and_hold_in_market_ratio == 1.0
    # A non-positive first close leaves the Buy & Hold path undefined.
    closes = [100.0] * N_TAIL
    closes[0] = 0.0
    detail = _detail(_run(N_TAIL, [(10, 20, 0.01)], closes=closes), folds)
    assert detail.in_sample.buy_and_hold_in_market_ratio is None
    assert detail.in_sample.in_market_ratio is not None
    assert detail.out_of_sample.buy_and_hold_in_market_ratio == 1.0


def test_a_one_bar_segment_has_neither_in_market_value() -> None:
    """F11-A-43's own example: test_size = 1 leaves the out-of-sample one bar long."""
    bars = TRAIN + 1
    folds = _folds(bars, test=1)
    detail = _detail(_run(bars, [(10, 20, 0.01)], open_entry=TRAIN), folds)
    assert detail.out_of_sample.in_market_ratio is None
    assert detail.out_of_sample.buy_and_hold_in_market_ratio is None
    assert detail.out_of_sample.open_trip_at_end == 1


# --------------------------------------------------------------------------
# F11-A-40 (g): the tail and the coverage block
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("bars", "tail"), [(N_NO_TAIL, 0), (N_TAIL, 45), (TRAIN + TEST + 1, 1)])
def test_coverage_is_the_geometry_of_the_same_run_and_folds(bars: int, tail: int) -> None:
    result = _run(bars, [(10, 20, 0.01), (260, 270, -0.01)])
    folds = _folds(bars)
    detail = _detail(result, folds)
    coverage = detail.coverage
    assert set(coverage.model_dump()) == {
        "last_bar_date",
        "unattributed_tail_bars",
        "unattributed_tail_start_date",
    }
    (is_start, is_stop), (oos_start, oos_stop) = (
        (folds[0].train_start, folds[0].train_stop),
        (folds[0].test_start, folds[-1].test_stop),
    )
    # The tail is the only part of the run in no segment.
    assert is_start == 0 and oos_start == is_stop
    assert coverage.last_bar_date == result.dates[-1]
    assert coverage.unattributed_tail_bars == tail == len(result.dates) - oos_stop
    assert (coverage.unattributed_tail_bars == 0) == (coverage.unattributed_tail_start_date is None)
    report = walk_forward_report(result, folds)
    curves = walk_forward_curves(result, folds)
    assert curves.out_of_sample.dates[-1] == result.dates[oos_stop - 1]
    if tail:
        assert coverage.unattributed_tail_start_date == result.dates[oos_stop]
        oos_end = report.out_of_sample.strategy.end_date
        assert oos_end is not None and coverage.unattributed_tail_start_date > oos_end


# --------------------------------------------------------------------------
# F11-A-40 (i): warm-up intervals
# --------------------------------------------------------------------------


@pytest.mark.parametrize("strategy_id", STRATEGY_IDS)
def test_warmup_flat_intervals_are_structurally_flat(strategy_id: str) -> None:
    warmup = STRATEGY_WARMUP_BARS[strategy_id]
    result, folds = _standard(strategy_id)
    detail = _detail(result, folds, warmup)
    is_start, is_stop = _bounds(folds, "in_sample")
    expected = len(set(range(is_start, is_stop - 1)) & set(range(0, warmup - 1)))
    assert detail.in_sample.warmup_flat_intervals == expected > 0
    assert detail.out_of_sample.warmup_flat_intervals == 0
    held = held_mask(extract_episodes(result), len(result.dates))
    for t in range(0, warmup - 1):
        assert result.weights[t] == 0.0 and not held[t], (strategy_id, t)


def test_the_quant_example_of_fifty_nine_warmup_intervals() -> None:
    """quant §2.4: W = 60 on a 252-bar in-sample block -> 59 of 251 intervals."""
    detail = _detail(_run(N_TAIL, []), _folds(N_TAIL), warmup=60)
    assert detail.in_sample.warmup_flat_intervals == 59
    assert detail.out_of_sample.warmup_flat_intervals == 0


# --------------------------------------------------------------------------
# F11-A-54: the empty-state code, from the counts alone
# --------------------------------------------------------------------------


def _attribution(n: int, boundary: int, open_: int) -> RoundTripAttribution:
    return RoundTripAttribution(
        window_start=0,
        window_stop=10,
        episodes=(),
        excluded_boundary_trips=boundary,
        open_trip_at_end=open_,
        stats=RoundTripStats(
            n=n, n_win=0, n_loss=0, round_trip_win_rate=None, round_trip_payoff_ratio=None
        ),
    )


@pytest.mark.parametrize(
    ("n", "boundary", "open_", "expected"),
    [
        (1, 0, 0, None),
        (5, 3, 1, None),
        (0, 0, 0, "no_position"),
        (0, 1, 0, "excluded_only"),
        (0, 0, 1, "excluded_only"),
        (0, 2, 1, "excluded_only"),
        # Outside the domain the engine can produce: still an answer, never a raise.
        (0, -1, 0, "no_position"),
        (-1, 0, 0, "no_position"),
        (0, 10**9, 1, "excluded_only"),
    ],
)
def test_the_empty_state_truth_table(
    n: int, boundary: int, open_: int, expected: str | None
) -> None:
    assert round_trip_empty_state(_attribution(n, boundary, open_)) == expected


def test_the_empty_state_function_takes_the_attribution_and_nothing_else() -> None:
    parameters = inspect.signature(round_trip_empty_state).parameters
    assert list(parameters) == ["attribution"]


@dataclass(frozen=True)
class _EmptyCase:
    name: str
    spans: tuple[tuple[int, int, float], ...]
    open_entry: int | None
    segment: str
    code: str | None
    intervals: int | None  # None: positive, asserted as a fixture fact only


_A54 = (
    # (a) nothing ever entered the segment.
    _EmptyCase("a no trades", (), None, "in_sample", "no_position", 0),
    _EmptyCase("a no trades oos", (), None, "out_of_sample", "no_position", 0),
    # (b) the one round trip straddles the edge: in-market > 0 on this fixture.
    _EmptyCase("b straddle", ((240, 260, 0.01),), None, "in_sample", "excluded_only", None),
    # (c) entered on the segment's last bar, closed later / still open.
    _EmptyCase("c last-bar entry", ((251, 270, 0.01),), None, "in_sample", "excluded_only", 0),
    _EmptyCase("c last-bar entry open", (), 251, "in_sample", "excluded_only", 0),
    # (d) entered in the previous segment, exited on this segment's first bar.
    _EmptyCase("d first-bar exit", ((240, 252, -0.01),), None, "out_of_sample", "excluded_only", 0),
    # (e) a complete round trip -> no code.
    _EmptyCase("e contained", ((10, 20, 0.01),), None, "in_sample", None, None),
)


@pytest.mark.parametrize("case", _A54, ids=lambda case: case.name)
def test_ac10_empty_state_cases(case: _EmptyCase) -> None:
    result = _run(N_TAIL, list(case.spans), open_entry=case.open_entry)
    folds = _folds(N_TAIL)
    detail = _detail(result, folds)
    segment = _segment(detail, case.segment)
    start, stop = _bounds(folds, case.segment)
    assert segment.empty_state == case.code
    intervals = _intervals(segment, start, stop)
    if case.intervals is None:
        assert intervals is not None and intervals > 0
    else:
        assert intervals == case.intervals
    if case.code is not None:
        assert segment.num_round_trips == 0
        assert segment.round_trips == [] and segment.lowest_return_round_trips == []
        assert segment.longest_losing_streak is None
        assert segment.mean_winning_return is None and segment.mean_losing_return is None
        # Disclosure still ships: the flag is set and the counts are integers.
        assert segment.below_display_minimum is True
        assert segment.in_market_ratio is not None


def test_no_position_implies_no_in_market_interval_one_way_only() -> None:
    """F11-A-54(f): ``no_position`` => in-market 0. The converse is not asserted."""
    rnd = random.Random(11)
    seen_codes: set[str | None] = set()
    for _ in range(150):
        spans: list[tuple[int, int, float]] = []
        cursor = rnd.randint(0, 40)
        while cursor < N_TAIL - 5 and rnd.random() < 0.8:
            length = rnd.randint(1, 40)
            exit_ = min(cursor + length, N_TAIL - 1)
            spans.append((cursor, exit_, rnd.uniform(-0.05, 0.05)))
            cursor = exit_ + rnd.randint(1, 80)
        open_entry = cursor if cursor < N_TAIL and rnd.random() < 0.3 else None
        folds = _folds(N_TAIL)
        detail = _detail(_run(N_TAIL, spans, open_entry=open_entry), folds)
        for name in SEGMENTS:
            segment = _segment(detail, name)
            seen_codes.add(segment.empty_state)
            if segment.empty_state == "no_position":
                start, stop = _bounds(folds, name)
                assert _intervals(segment, start, stop) == 0
    assert "no_position" in seen_codes and None in seen_codes


# --------------------------------------------------------------------------
# D-13: the sample flag edge
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "flagged"), [(0, True), (1, True), (N_MIN_DISPLAY - 1, True), (N_MIN_DISPLAY, False)]
)
def test_the_flag_is_set_strictly_below_the_display_minimum(count: int, flagged: bool) -> None:
    spans = [(TRAIN + 2 * i, TRAIN + 2 * i + 1, 0.01) for i in range(count)]
    detail = _detail(_run(N_TAIL, spans), _folds(N_TAIL))
    assert detail.out_of_sample.num_round_trips == count
    assert detail.out_of_sample.below_display_minimum is flagged


# --------------------------------------------------------------------------
# F11-A-43: total over every input walk_forward_report accepts
# --------------------------------------------------------------------------


def _strings(value: object) -> list[str]:
    """Every string leaf of a dumped model."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _empty_result() -> BacktestResult:
    return BacktestResult(dates=[], equity_curve=[], close=[], weights=[], initial_cash=1e6)


_EDGE_INPUTS: tuple[tuple[str, BacktestResult, list[WalkForwardFold]], ...] = (
    ("no bars at all", _empty_result(), _folds(N_TAIL)),
    ("test_size 1", _run(TRAIN + 1, [], open_entry=5), _folds(TRAIN + 1, test=1)),
    ("no trades", _run(N_TAIL, []), _folds(N_TAIL)),
    ("open at the end", _run(N_TAIL, [(10, 20, 0.0)], open_entry=300), _folds(N_TAIL)),
    ("trades only in the tail", _run(N_TAIL, [(320, 340, 0.02)], open_entry=350), _folds(N_TAIL)),
    ("all closes zero", _run(N_TAIL, [(10, 20, 0.01)], closes=[0.0] * N_TAIL), _folds(N_TAIL)),
    ("one-bar train", _run(10, [(1, 2, -0.01)]), _folds(10, train=1, test=3)),
)


@pytest.mark.parametrize(
    ("result", "folds"),
    [(case[1], case[2]) for case in _EDGE_INPUTS],
    ids=[case[0] for case in _EDGE_INPUTS],
)
def test_nothing_the_report_accepts_makes_the_detail_raise(
    result: BacktestResult, folds: list[WalkForwardFold]
) -> None:
    walk_forward_report(result, folds)  # the precondition: the report accepts it
    for warmup in (0, 1, 60, 10_000):
        detail = _detail(result, folds, warmup)
        labels = build_round_trip_labels(detail)
        for name in SEGMENTS:
            segment = _segment(detail, name)
            assert segment.excluded_boundary_trips >= 0 and segment.open_trip_at_end >= 0
            assert segment.warmup_flat_intervals >= 0
        assert detail.coverage.unattributed_tail_bars >= 0
        for text in _strings(labels.model_dump()):
            assert "{" not in text and "}" not in text, text


def test_no_fold_is_refused_exactly_as_the_report_refuses_it() -> None:
    result = _run(20, [])
    with pytest.raises(ValueError):
        walk_forward_report(result, [])
    with pytest.raises(ValueError):
        walk_forward_round_trip_detail(result, [], warmup_bars=0)


# --------------------------------------------------------------------------
# F11-A-41: strategy-agnostic report layer
# --------------------------------------------------------------------------


def test_the_warmup_length_is_a_keyword_argument() -> None:
    parameter = inspect.signature(walk_forward_round_trip_detail).parameters["warmup_bars"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


@pytest.mark.parametrize("module", ["app.backtest.report", "app.backtest.episodes"])
def test_the_report_layer_never_reaches_the_strategies(module: str) -> None:
    assert "app.backtest.strategies" not in reachable_app_modules((module,))
