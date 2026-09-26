"""The sector evaluator (ADR-0012 D-8, D-13, C-15, C-32, C-36, C-41; methodology §5, §6, §8).

CI halves of the NE-7 set live here and carry the ``sector_ne7`` marker:

* T-15 (methodology T2): the evaluator calls the very function objects of the
  sector core, and the repository holds no second implementation;
* T-9 (T9): board == replay, and R_g / 「上漲 k／n 家」 / constituents share one set;
* T-13 first half (T7): B_EW is C_M(t,L), equally weighted, never charged;
* T-7 (T4): ex-dividend exclusions and label factors are point-in-time;
* T-8 (T5, T6): a name delisted later is in the universe before it leaves; a
  reclassified name stays in its old sector until the new snapshot is visible.

Plus the statistics (Wilson, circular block bootstrap, permutation, N_eff),
G1..G6 each failing alone, the self-check status rules of C-36 / T-22, and the
hand-off to the first-wave gate and repository types.
"""

from __future__ import annotations

import ast
import dataclasses
import math
from collections.abc import Collection
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.backtest import sector_eval
from app.backtest.basket import (
    BasketExecution,
    BasketSchedule,
    HoldingWindow,
    PriceBook,
    run_basket_backtest,
)
from app.backtest.costs import CostModel
from app.backtest.episodes import wilson_interval
from app.backtest.sector_eval import (
    RateSummary,
    SectorStatistics,
    candidate_gates,
    selfchecks_passed,
    to_stats_record,
)
from app.data.calendar import TradingCalendar
from app.data.panel import cutoff, source_fingerprint
from app.sectors import gate, ranking, universe
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.definition import GateRules, SectorMomentumDefinition
from app.sectors.gate import EvaluationWindow, GateInputs, PitStatus
from app.sectors.models import SelfcheckRecord, StatsRecord
from app.sectors.store import BiasedDataRejected, SectorStatsRepository
from tests.import_graph import APP_ROOT
from tests.sector_eval_helpers import SyntheticMarket, boards_for, replace_frame, synthetic_market
from tests.source_helpers import FakeSources

#: V1 with fewer T1 dates, only to keep CI time sane; every other value is V1's.
FAST = SectorMomentumDefinition(
    method_version=V1.method_version,
    lookback_days=V1.lookback_days,
    holding_days=V1.holding_days,
    gate=GateRules(lookahead_sample_dates=6),
)
DE5 = date(2026, 9, 1)
SEED = 20260925


def _pit_status(market: SyntheticMarket) -> PitStatus:
    forward = frozenset(market.calendar[market.calendar.index(market.d0) :])
    return PitStatus(
        accumulation_start=market.d0,
        ok_sessions={kind: forward for kind in ("listing", "classification", "dividend_announce")},
    )


@pytest.fixture(scope="module")
def market() -> SyntheticMarket:
    return synthetic_market(seed=11, forward=165, n_dividends=10)


@pytest.fixture(scope="module")
def evaluation(market: SyntheticMarket) -> sector_eval.SectorEvaluation:
    grid = BasketSchedule.every_holding_period(
        market.calendar, holding_days=5, start=market.d0
    ).decision_dates
    return sector_eval.evaluate(
        market.panel,
        FAST,
        cost_model=CostModel(),
        start=market.d0,
        m=1,
        seed=SEED,
        pit_status=_pit_status(market),
        de5_verified_on=DE5,
        boards=boards_for(market, grid),
    )


# ---------------------------------------------------------------------------
# T-15 (methodology T2): one implementation, the same function objects
# ---------------------------------------------------------------------------


@pytest.mark.sector_ne7
def test_evaluator_calls_the_core_function_objects() -> None:
    assert sector_eval.calculation_set is universe.calculation_set
    assert sector_eval.rank_sectors is ranking.rank_sectors


@pytest.mark.sector_ne7
def test_services_call_the_same_function_objects() -> None:
    from app.services import sector_board

    assert sector_board.calculation_set is universe.calculation_set
    assert sector_board.rank_sectors is ranking.rank_sectors
    assert sector_board.calculation_set is sector_eval.calculation_set
    assert sector_board.rank_sectors is sector_eval.rank_sectors


def _definitions_of(names: Collection[str], root: Path = APP_ROOT) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {name: [] for name in names}
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in names:
                found[node.name].append(str(path.relative_to(root)))
    return found


@pytest.mark.sector_ne7
def test_no_second_implementation_of_the_universe_or_the_ranking() -> None:
    found = _definitions_of({"calculation_set", "rank_sectors"})
    assert found == {
        "calculation_set": ["sectors/universe.py"],
        "rank_sectors": ["sectors/ranking.py"],
    }


def test_second_implementation_scan_has_teeth(tmp_path: Path) -> None:
    (tmp_path / "sectors").mkdir()
    (tmp_path / "sectors" / "universe.py").write_text(
        "def calculation_set(p, d):\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "fast.py").write_text(
        "class V:\n    def calculation_set(self, p, d):\n        pass\n", encoding="utf-8"
    )
    found = _definitions_of({"calculation_set"}, tmp_path)
    assert found == {"calculation_set": ["research/fast.py", "sectors/universe.py"]}


# ---------------------------------------------------------------------------
# The fixture evaluation itself
# ---------------------------------------------------------------------------


def test_evaluation_counts_non_overlapping_samples(
    evaluation: sector_eval.SectorEvaluation, market: SyntheticMarket
) -> None:
    main = [week for week in evaluation.main if week.valid]
    assert len(main) >= 30
    for earlier, later in zip(main, main[1:], strict=False):
        assert later.window.entry_date > earlier.window.exit_date
        assert later.decision_date >= earlier.window.exit_date
    assert main[0].decision_date >= market.d0
    assert len(evaluation.phases) == V1.holding_days
    assert evaluation.regime == "pit" and evaluation.data_regime == "forward_pit"


def test_selfchecks_all_run_and_pass_on_clean_synthetic_data(
    evaluation: sector_eval.SectorEvaluation,
) -> None:
    statuses = {check.check_name: check.status for check in evaluation.selfchecks}
    assert tuple(statuses) == sector_eval.SELFCHECK_ORDER
    assert statuses == {
        sector_eval.T1: "pass",
        sector_eval.T3A: "pass",
        sector_eval.T3B: "pass",
        sector_eval.T4: "pass",
        sector_eval.T5: "pass",
        sector_eval.T6: "pass",
        sector_eval.T7: "pass",
        sector_eval.T8: "pass",
        sector_eval.T8_SHUFFLE: "pass",
        sector_eval.T9: "pass",
    }
    assert evaluation.data_quality_problems == ()
    assert evaluation.pit_gaps == ()


def test_deltas_are_produced_in_percentage_points(
    evaluation: sector_eval.SectorEvaluation,
) -> None:
    stats = evaluation.statistics
    assert stats.delta_real is not None and stats.delta_shuffle is not None
    assert stats.main.p_net is not None and stats.main.q_net is not None
    assert stats.delta_real == pytest.approx((stats.main.p_net - stats.main.q_net) * 100.0)
    assert stats.delta_real_interval is not None and stats.delta_shuffle_interval is not None
    assert stats.shuffle is not None and stats.shuffle.deltas.size == V1.gate.label_shuffle_draws


def test_matches_the_generic_engine_on_the_main_phase(
    evaluation: sector_eval.SectorEvaluation, market: SyntheticMarket
) -> None:
    """The evaluator's rank-1 labels are what run_basket_backtest produces."""
    schedule = BasketSchedule.every_holding_period(market.calendar, holding_days=5, start=market.d0)
    factors = sector_eval.pit_label_factors(market.panel)
    result = run_basket_backtest(
        market.panel,
        sector_eval.rank_1_strategy(V1),
        schedule=schedule,
        cost_model=CostModel(),
        execution=BasketExecution(adjustment=factors.adjustment),
        benchmark=sector_eval.benchmark_strategy(V1),
    )
    engine = {s.decision_date: s for s in result.samples if s.valid}
    judged = {w.decision_date: w.rank_1_sample for w in evaluation.main if w.valid}
    assert set(judged) <= set(engine)
    for day, sample in judged.items():
        assert sample is not None
        assert engine[day].excess_net == sample.excess_net
        assert engine[day].excess_gross == sample.excess_gross


# ---------------------------------------------------------------------------
# T-9: same set, board == replay
# ---------------------------------------------------------------------------


@pytest.mark.sector_ne7
def test_same_set_holds_for_every_ranked_sector(market: SyntheticMarket) -> None:
    for t in market.calendar[-40::7]:
        decision = sector_eval.decide(market.panel.as_of(t), V1)
        assert decision.ranking.ranked
        assert sector_eval.same_set_violations(decision) == []


@pytest.mark.sector_ne7
def test_same_set_check_has_teeth(market: SyntheticMarket) -> None:
    decision = sector_eval.decide(market.panel.as_of(market.calendar[-10]), V1)
    first = decision.ranking.ranked[0]
    intruder = next(iter(decision.calc.market.members - first.members))
    tampered_row = dataclasses.replace(first, members=first.members | {intruder})
    tampered = dataclasses.replace(
        decision,
        ranking=dataclasses.replace(
            decision.ranking, ranked=(tampered_row, *decision.ranking.ranked[1:])
        ),
    )
    assert sector_eval.same_set_violations(tampered) != []


@pytest.mark.sector_ne7
def test_board_replay_mismatch_fails_t9(market: SyntheticMarket) -> None:
    t = market.calendar[-10]
    decision = sector_eval.decide(market.panel.as_of(t), V1)
    board = sector_eval.fingerprint_ranking(decision.ranking)
    row = board.rows[0]
    wrong = dataclasses.replace(
        board, rows=(dataclasses.replace(row, up_count=row.up_count + 1), *board.rows[1:])
    )
    good = sector_eval._Audit(frames=market.panel.frames, boards={t: board})
    good.decision(decision)
    assert good.t9_problems == [] and good.t9_compared == 1
    bad = sector_eval._Audit(frames=market.panel.frames, boards={t: wrong})
    bad.decision(decision)
    assert bad.t9_problems == [f"{t.isoformat()}:board_differs"]


def test_t9_fails_closed_without_boards(market: SyntheticMarket) -> None:
    short = synthetic_market(seed=3, forward=40, n_dividends=0)
    result = sector_eval.evaluate(
        short.panel,
        FAST,
        cost_model=CostModel(),
        start=short.d0,
        m=1,
        seed=1,
        pit_status=_pit_status(short),
        de5_verified_on=DE5,
        boards=None,
    )
    t9 = next(c for c in result.selfchecks if c.check_name == sector_eval.T9)
    assert t9.status == "fail" and t9.detail is not None and "no_board_compared" in t9.detail


# ---------------------------------------------------------------------------
# T-13 first half (T7): the benchmark
# ---------------------------------------------------------------------------


@pytest.mark.sector_ne7
def test_benchmark_is_the_calculation_set_of_the_market_and_is_never_charged(
    evaluation: sector_eval.SectorEvaluation, market: SyntheticMarket
) -> None:
    cost = evaluation.round_trip_cost
    checked = 0
    for week in [w for w in evaluation.main if w.valid][:8]:
        decision = sector_eval.decide(market.panel.as_of(week.decision_date), V1)
        assert week.benchmark is not None
        assert set(week.benchmark.requested) == set(decision.calc.market.members)
        assert len(set(week.benchmark.requested.values())) == 1
        for sample in week.labels.values():
            if sample.valid:
                assert sample.excess_gross is not None and sample.excess_net is not None
                assert sample.excess_gross - sample.excess_net == pytest.approx(cost, abs=1e-15)
                checked += 1
    assert checked > 0


@pytest.mark.sector_ne7
def test_benchmark_audit_has_teeth(
    evaluation: sector_eval.SectorEvaluation, market: SyntheticMarket
) -> None:
    week = next(w for w in evaluation.main if w.valid)
    decision = sector_eval.decide(market.panel.as_of(week.decision_date), V1)
    assert week.benchmark is not None
    short = dataclasses.replace(
        week,
        benchmark=dataclasses.replace(
            week.benchmark, requested=dict(list(week.benchmark.requested.items())[1:])
        ),
    )
    audit = sector_eval._Audit(frames=market.panel.frames, boards=None)
    audit.week(short, decision, evaluation.round_trip_cost)
    assert any("benchmark_members" in p for p in audit.t7_problems)
    charged = sector_eval._Audit(frames=market.panel.frames, boards=None)
    charged.week(week, decision, evaluation.round_trip_cost * 2)
    assert any(p.endswith(":cost") for p in charged.t7_problems)


# ---------------------------------------------------------------------------
# T-7 (T4): ex-dividend never leaks
# ---------------------------------------------------------------------------


@pytest.mark.sector_ne7
def test_the_ci_path_contains_ex_dividend_events(
    evaluation: sector_eval.SectorEvaluation, market: SyntheticMarket
) -> None:
    factors = sector_eval.pit_label_factors(market.panel)
    usable = [item for item in factors.factors if item.factor is not None]
    assert len(usable) == len(market.dividends)
    in_period = [
        e
        for e in market.dividends
        if evaluation.main[0].decision_date < e.ex_date <= evaluation.main[-1].window.exit_date
    ]
    assert in_period, "the synthetic path must hold events inside the judged period"
    held_adjusted = [
        outcome
        for week in evaluation.main
        if week.valid
        for sample in week.labels.values()
        if sample.basket is not None
        for symbol in sample.basket.held
        if (outcome := symbol) in {e.symbol for e in in_period}
    ]
    assert held_adjusted
    t4 = next(c for c in evaluation.selfchecks if c.check_name == sector_eval.T4)
    assert t4.status == "pass"


@pytest.mark.sector_ne7
def test_label_factor_is_previous_close_over_the_reference(market: SyntheticMarket) -> None:
    factors = sector_eval.pit_label_factors(market.panel)
    frames = market.panel.frames
    for event in market.dividends:
        # What was on file at cutoff(ex_date): a late correction of the previous
        # session recorded that morning counts; the latest record wins.
        bars = frames.bars.loc[
            (frames.bars["symbol"] == event.symbol)
            & (frames.bars["recorded_at"] <= cutoff(event.ex_date))
        ].sort_values(["session_date", "recorded_at"])
        bars = bars.drop_duplicates("session_date", keep="last").set_index("session_date")
        days = list(bars.index)
        before = days[days.index(event.ex_date) - 1]
        reference = bars.loc[event.ex_date, "close"] - bars.loc[event.ex_date, "change"]
        expected = bars.loc[before, "close"] / reference
        (found,) = [f for f in factors.factors if f.symbol == event.symbol]
        assert found.factor == pytest.approx(expected, rel=1e-12)
        # T4 ②: the independent rebuild from raw rows agrees.
        assert sector_eval._same_factor(
            found.factor, sector_eval._audit_factor(frames, event.symbol, event.ex_date)
        )
        assert factors.adjustment(event.symbol, before, event.ex_date) == found.factor
        assert factors.adjustment(event.symbol, event.ex_date, event.ex_date) == 1.0


@pytest.mark.sector_ne7
def test_an_announcement_recorded_late_neither_excludes_nor_restores(
    market: SyntheticMarket,
) -> None:
    event = market.dividends[0]
    frames = market.panel.frames
    rows = frames.ex_dividend
    mine = (rows["symbol"] == event.symbol) & (rows["ex_date"] == event.ex_date)
    late = rows.copy()
    late.loc[mine, "recorded_at"] = late.loc[mine, "recorded_at"] + np.timedelta64(400, "D")
    runs = frames.runs.copy()
    late_runs = set(late.loc[mine, "run_id"])
    runs.loc[runs["run_id"].isin(late_runs), "recorded_at"] = runs.loc[
        runs["run_id"].isin(late_runs), "recorded_at"
    ] + np.timedelta64(400, "D")
    delayed = replace_frame(market.panel, ex_dividend=late, runs=runs)
    # Not known at cutoff(ex_date): no restoration factor exists for it.
    factors = sector_eval.pit_label_factors(delayed)
    assert all(
        not (f.symbol == event.symbol and f.ex_date == event.ex_date) for f in factors.factors
    )
    # ...and the lookback window of a decision just after the ex-date keeps the name.
    position = market.calendar.index(event.ex_date)
    t = market.calendar[position + 2]
    on_time = sector_eval.decide(market.panel.as_of(t), V1)
    too_late = sector_eval.decide(delayed.as_of(t), V1)
    if event.symbol in on_time.calc.market.expected:
        assert event.symbol in on_time.calc.market.ex_date_excluded
        assert event.symbol not in too_late.calc.market.ex_date_excluded


@pytest.mark.sector_ne7
def test_ex_date_exclusion_audit_has_teeth(market: SyntheticMarket) -> None:
    t = market.calendar[-12]
    decision = sector_eval.decide(market.panel.as_of(t), V1)
    stranger = sorted(decision.calc.market.members)[0]
    market_split = dataclasses.replace(
        decision.calc.market,
        ex_date_excluded=decision.calc.market.ex_date_excluded | {stranger},
    )
    tampered = dataclasses.replace(
        decision, calc=dataclasses.replace(decision.calc, market=market_split)
    )
    audit = sector_eval._Audit(frames=market.panel.frames, boards=None)
    audit.decision(tampered)
    assert audit.t4_untraceable == [f"{t.isoformat()}:{stranger}"]


def test_no_dividend_event_makes_t4_vacuous() -> None:
    quiet = synthetic_market(seed=5, forward=40, n_dividends=0, delist=False, reclassify=False)
    result = sector_eval.evaluate(
        quiet.panel,
        FAST,
        cost_model=CostModel(),
        start=quiet.d0,
        m=1,
        seed=2,
        pit_status=_pit_status(quiet),
        de5_verified_on=DE5,
        boards=None,
    )
    statuses = {c.check_name: c.status for c in result.selfchecks}
    assert statuses[sector_eval.T4] == "vacuous"
    assert statuses[sector_eval.T5] == "vacuous"
    assert statuses[sector_eval.T6] == "vacuous"


# ---------------------------------------------------------------------------
# T-8 (T5, T6): survivorship and point-in-time classification
# ---------------------------------------------------------------------------


@pytest.mark.sector_ne7
def test_a_name_delisted_later_is_in_the_universe_before_it_leaves(
    market: SyntheticMarket,
) -> None:
    assert market.delisted is not None and market.delisted_from is not None
    position = market.calendar.index(market.delisted_from)
    before = sector_eval.decide(market.panel.as_of(market.calendar[position - 3]), V1)
    after = sector_eval.decide(market.panel.as_of(market.calendar[position + 3]), V1)
    assert market.delisted in before.calc.market.expected
    assert market.delisted not in after.calc.market.expected


@pytest.mark.sector_ne7
def test_a_reclassified_name_stays_in_its_old_sector_until_the_new_snapshot(
    market: SyntheticMarket,
) -> None:
    assert market.moved and market.moved_from and market.moved_to_code
    old_code = market.moved[:2]
    position = market.calendar.index(market.moved_from)
    before = sector_eval.decide(market.panel.as_of(market.calendar[position - 1]), V1)
    after = sector_eval.decide(market.panel.as_of(market.calendar[position]), V1)
    assert market.moved in before.calc.sector(old_code).expected
    assert market.moved not in before.calc.sector(market.moved_to_code).expected
    assert market.moved in after.calc.sector(market.moved_to_code).expected


@pytest.mark.sector_ne7
def test_survivorship_and_classification_audits_have_teeth(market: SyntheticMarket) -> None:
    """A pipeline that reads today's directory for every past day is caught."""
    assert market.delisted_from is not None and market.moved_from is not None
    frames = market.panel.frames
    final_listing_run = frames.listing["run_id"].iloc[-1]
    final_class_run = frames.classification["run_id"].iloc[-1]
    latest_listing = frames.listing.loc[frames.listing["run_id"] == final_listing_run]
    latest_class = frames.classification.loc[frames.classification["run_id"] == final_class_run]
    t = market.calendar[market.calendar.index(market.moved_from) - 5]
    # Today's directory, stamped as if it had been captured on each day.
    honest_listing = frames.listing.loc[frames.listing["session_date"] == t]
    honest_class = frames.classification.loc[frames.classification["session_date"] == t]
    hindsight_listing = latest_listing.assign(
        run_id=honest_listing["run_id"].iloc[0],
        session_date=t,
        recorded_at=honest_listing["recorded_at"].iloc[0],
    )
    hindsight_class = latest_class.assign(
        run_id=honest_class["run_id"].iloc[0],
        session_date=t,
        recorded_at=honest_class["recorded_at"].iloc[0],
    )
    cheat = replace_frame(
        market.panel,
        listing=pd.concat(
            [frames.listing.loc[frames.listing["session_date"] != t], hindsight_listing],
            ignore_index=True,
        ),
        classification=pd.concat(
            [
                frames.classification.loc[frames.classification["session_date"] != t],
                hindsight_class,
            ],
            ignore_index=True,
        ),
    )
    decision = sector_eval.decide(cheat.as_of(t), V1)
    audit = sector_eval._Audit(frames=frames, boards=None)
    audit.decision(decision)
    assert any("dropped_before_delisting" in p for p in audit.t5_problems)
    assert any(p.endswith(market.moved or "") for p in audit.t6_problems)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def test_wilson_is_the_episodes_implementation_at_alpha_over_m() -> None:
    stats = _passing_stats(m=3)
    assert stats.alpha_per_test == pytest.approx(0.05 / 3)
    interval = wilson_interval(140, 200, alpha=0.05 / 3)
    assert interval is not None and interval.low < 0.7 < interval.high


def test_block_bootstrap_is_seeded_and_centred() -> None:
    values = (np.arange(200) % 3 == 0).astype(float)
    first = sector_eval.block_bootstrap_means(
        values, block_length=4, draws=2000, rng=np.random.default_rng(1)
    )
    again = sector_eval.block_bootstrap_means(
        values, block_length=4, draws=2000, rng=np.random.default_rng(1)
    )
    assert np.array_equal(first, again)
    assert float(first.mean()) == pytest.approx(values.mean(), abs=0.01)
    low, high = sector_eval.percentile_interval(first, 0.05)
    assert low < values.mean() < high


def test_effective_sample_count_is_n_for_independent_draws_and_less_when_clustered() -> None:
    rng = np.random.default_rng(7)
    iid = (rng.random(400) < 0.5).astype(float)
    boot = sector_eval.block_bootstrap_means(iid, block_length=4, draws=4000, rng=rng)
    assert sector_eval.effective_sample_count(iid, boot) == pytest.approx(400, rel=0.2)
    clustered = np.repeat((rng.random(50) < 0.5).astype(float), 8)
    boot = sector_eval.block_bootstrap_means(clustered, block_length=4, draws=4000, rng=rng)
    assert sector_eval.effective_sample_count(clustered, boot) < 250


def test_permutation_pvalue_separates_a_real_edge_from_noise() -> None:
    rng = np.random.default_rng(3)
    weeks = [np.array([1.0] + [0.0] * 9) for _ in range(60)]
    assert sector_eval.permutation_pvalue(weeks, 1.0, draws=2000, rng=rng) < 0.001
    noise = [(rng.random(10) < 0.5).astype(float) for _ in range(60)]
    observed = float(np.mean([w[0] for w in noise]))
    p = sector_eval.permutation_pvalue(noise, observed, draws=2000, rng=rng)
    assert 0.05 < p < 0.95


def test_segments_follow_the_walk_forward_test_windows() -> None:
    assert sector_eval.segment_bounds(300) == [(0, 126), (126, 252), (252, 300)]
    assert sector_eval.segment_bounds(252) == [(0, 126), (126, 252)]
    assert sector_eval.segment_bounds(50) == [(0, 50)]


# ---------------------------------------------------------------------------
# G1..G6 each failing alone (candidate only)
# ---------------------------------------------------------------------------


def _summary(k: int, n: int, *, q_gross: float = 0.45, mean: float = 0.01) -> RateSummary:
    return RateSummary(
        sample_count=n,
        beat_count_net=k,
        beat_count_gross=k,
        p_net=k / n,
        p_gross=k / n,
        q_net=0.40,
        q_gross=q_gross,
        b=max(q_gross, 0.5),
        mean_excess_net=mean,
        mean_excess_gross=mean,
        median_excess_net=mean,
    )


def _passing_stats(m: int = 1) -> SectorStatistics:
    main = _summary(140, 200)
    return SectorStatistics(
        main=main,
        m=m,
        alpha_per_test=0.05 / m,
        effective_sample_count=150.0,
        wilson=(0.62, 0.77),
        bootstrap={2: (0.61, 0.78), 4: (0.61, 0.78), 8: (0.60, 0.79)},
        permutation_p=0.0001,
        halves=(_summary(70, 100), _summary(70, 100)),
        phases=tuple(_summary(35, 50) for _ in range(5)),
        without_most_frequent=_summary(100, 150),
        most_frequent_sector="24",
        last_12_months=_summary(35, 49),
        segments=(),
        time_shift=None,
        shuffle=None,
        delta_real=30.0,
        delta_shuffle=1.0,
        delta_real_interval=(20.0, 40.0),
        delta_shuffle_interval=(-2.0, 4.0),
        p_leak=0.99,
        p_lag=0.6,
        seeds={},
    )


def _failing(gate_name: str) -> SectorStatistics:
    base = _passing_stats()
    changes: dict[str, object] = {
        "G1": {"effective_sample_count": 59.0},
        "G2": {"wilson": (0.49, 0.77)},
        "G3": {"main": _summary(109, 200)},
        "G4": {"permutation_p": 0.2},
        "G5": {"phases": (*base.phases[:4], _summary(25, 50))},
        "G6": {"last_12_months": _summary(24, 49)},
    }
    return dataclasses.replace(base, **changes[gate_name])  # type: ignore[arg-type]


def test_all_gates_pass_on_the_passing_fixture() -> None:
    assert all(check.passed for check in candidate_gates(_passing_stats(), V1))


@pytest.mark.parametrize("gate_name", ["G1", "G2", "G3", "G4", "G5", "G6"])
def test_each_gate_fails_alone(gate_name: str) -> None:
    checks = {c.gate: c.passed for c in candidate_gates(_failing(gate_name), V1)}
    assert [name for name, passed in checks.items() if not passed] == [gate_name]
    assert all(c.detail is None for c in candidate_gates(_failing(gate_name), V1))


def test_g3_boundary_is_exact() -> None:
    # p_net - b == 0.05 exactly passes; one fewer beat fails.
    stats = dataclasses.replace(_passing_stats(), main=_summary(110, 200))
    assert {c.gate: c.passed for c in candidate_gates(stats, V1)}["G3"]
    stats = dataclasses.replace(_passing_stats(), main=_summary(109, 200))
    assert not {c.gate: c.passed for c in candidate_gates(stats, V1)}["G3"]


def test_g4_needs_a_positive_mean_net_excess() -> None:
    stats = dataclasses.replace(_passing_stats(), main=_summary(140, 200, mean=0.0))
    assert not {c.gate: c.passed for c in candidate_gates(stats, V1)}["G4"]


def test_g2_uses_the_larger_of_q_gross_and_one_half() -> None:
    stats = dataclasses.replace(
        _passing_stats(), main=_summary(140, 200, q_gross=0.63)
    )  # b = 0.63 > Wilson low 0.62
    assert not {c.gate: c.passed for c in candidate_gates(stats, V1)}["G2"]


# ---------------------------------------------------------------------------
# C-36 / T-22: self-check statuses
# ---------------------------------------------------------------------------


def _checks(**override: str) -> list[SelfcheckRecord]:
    return [
        SelfcheckRecord(check_name=name, status=override.get(name, "pass"))  # type: ignore[arg-type]
        for name in sector_eval.SELFCHECK_ORDER
    ]


@pytest.mark.sector_ne7
def test_skip_is_allowed_only_for_t3a_and_t8_below_thirty() -> None:
    skipped = _checks(
        **{sector_eval.T3A: "skipped_insufficient_n", sector_eval.T8: "skipped_insufficient_n"}
    )
    assert selfchecks_passed(skipped, 29, V1)
    assert not selfchecks_passed(skipped, 30, V1)
    assert not selfchecks_passed(skipped, 150, V1)
    other = _checks(**{sector_eval.T7: "skipped_insufficient_n"})
    assert not selfchecks_passed(other, 10, V1)


@pytest.mark.sector_ne7
def test_label_shuffle_is_skipped_not_passed_without_samples(market: SyntheticMarket) -> None:
    """C-36 state semantics: with N = 0 nothing was shuffled, so it is a skip, not a pass."""
    empty = sector_eval.evaluate(
        market.panel,
        FAST,
        cost_model=CostModel(),
        start=market.calendar[-3],
        m=1,
        seed=SEED,
        pit_status=_pit_status(market),
        de5_verified_on=DE5,
    )
    assert empty.sample_count == 0
    statuses = {check.check_name: check.status for check in empty.selfchecks}
    assert statuses[sector_eval.T8_SHUFFLE] == "skipped_insufficient_n"
    assert statuses[sector_eval.T8] == "skipped_insufficient_n"
    # The skip is T8's allowance (N < 30 only); past it the same status fails the set.
    shuffle_skipped = _checks(**{sector_eval.T8_SHUFFLE: "skipped_insufficient_n"})
    assert selfchecks_passed(shuffle_skipped, 0, V1)
    assert not selfchecks_passed(shuffle_skipped, 30, V1)
    assert not selfchecks_passed(shuffle_skipped, 150, V1)


@pytest.mark.sector_ne7
def test_vacuous_is_allowed_only_for_t4_t5_t6() -> None:
    for name in (sector_eval.T4, sector_eval.T5, sector_eval.T6):
        assert selfchecks_passed(_checks(**{name: "vacuous"}), 200, V1)
    for name in (sector_eval.T1, sector_eval.T7, sector_eval.T8, sector_eval.T9):
        assert not selfchecks_passed(_checks(**{name: "vacuous"}), 200, V1)


@pytest.mark.sector_ne7
def test_a_missing_or_failed_check_fails_the_set() -> None:
    assert not selfchecks_passed(_checks()[1:], 200, V1)
    assert not selfchecks_passed(_checks(**{sector_eval.T8_SHUFFLE: "fail"}), 200, V1)


@pytest.mark.sector_ne7
def test_leak_and_placebo_statuses() -> None:
    assert sector_eval.leak_control_status(0.4, 0.95, 29, V1) == "skipped_insufficient_n"
    assert sector_eval.leak_control_status(0.4, 0.95, 30, V1) == "pass"
    assert sector_eval.leak_control_status(0.80, 0.95, 150, V1) == "fail"
    assert sector_eval.leak_control_status(None, 0.95, 150, V1) == "fail"
    assert sector_eval.time_shift_status(0.024, 150, V1) == "pass"
    assert sector_eval.time_shift_status(-0.025, 150, V1) == "fail"
    assert sector_eval.time_shift_status(None, 150, V1) == "fail"
    assert sector_eval.time_shift_status(None, 10, V1) == "skipped_insufficient_n"


# ---------------------------------------------------------------------------
# Hand-off to the first-wave store and gate types
# ---------------------------------------------------------------------------


def _market_of(evaluation: sector_eval.SectorEvaluation) -> FakeSources:
    """A market DB holding exactly the source set the evaluation read."""
    sources = source_fingerprint(evaluation.source_runs)
    assert sources is not None
    return FakeSources((sources,))


def _record(evaluation: sector_eval.SectorEvaluation, *, ci_ok: bool = True) -> StatsRecord | None:
    return to_stats_record(
        evaluation,
        FAST,
        run_id="eval-001",
        computed_at=datetime(2026, 9, 25, 12, tzinfo=UTC),
        recompute_session=evaluation.main[-1].window.exit_date,
        running_commit="0123abcd",
        ci_attestation_ok=ci_ok,
    )


def test_stats_record_round_trips_through_the_repository(
    evaluation: sector_eval.SectorEvaluation, tmp_path: Path
) -> None:
    record = _record(evaluation)
    assert record is not None
    assert record.regime == "pit" and record.data_regime == "forward_pit"
    assert record.sample_count == evaluation.sample_count
    assert record.selfcheck_passed and record.data_quality_passed
    assert not record.pit_history_missing
    assert record.delta_real is not None and record.delta_shuffle is not None
    repo = SectorStatsRepository(_market_of(evaluation), tmp_path / "main.db")
    repo.save(record)
    (loaded,) = repo.load(record.method_version)
    assert loaded.source_digest == record.source_digest
    assert loaded.source_run_count == len(evaluation.source_runs)
    assert loaded.beat_count_net == record.beat_count_net
    assert {c.check_name for c in loaded.selfchecks} == set(sector_eval.SELFCHECK_ORDER)


def test_without_ci_attestation_the_row_fails_its_selfcheck(
    evaluation: sector_eval.SectorEvaluation,
) -> None:
    record = _record(evaluation, ci_ok=False)
    assert record is not None and not record.selfcheck_passed


def test_the_gate_reads_the_row_and_stays_not_evaluated(
    evaluation: sector_eval.SectorEvaluation, market: SyntheticMarket
) -> None:
    record = _record(evaluation)
    assert record is not None
    outcome = gate.evaluate(
        GateInputs(
            definition=V1,
            data_source="twse_snapshot",
            board_method_version=V1.method_version,
            board_invariant_violated=False,
            as_of_session=record.recompute_session,
            calendar=TradingCalendar(market.calendar),
            fee_verified_on=sector_eval.fee_verified_on(CostModel()),
            de5_verified_on=DE5,
            ci_passed_commit="0123abcd",
            pit_status=_pit_status(market),
            window=EvaluationWindow(
                decision_dates=tuple(w.decision_date for w in evaluation.main),
                trading_days=market.calendar,
            ),
            stats_history=(record,),
            approvals=(),
        )
    )
    assert outcome.gate_status == "not_evaluated"
    assert outcome.not_evaluated_reason == "accumulating"
    assert "fee_unverified" in outcome.not_evaluated_reasons
    assert outcome.historical_stat is None and outcome.gate_checks is None


def test_de5_unverified_is_ne1_backed_by_a_gap(market: SyntheticMarket) -> None:
    short = synthetic_market(seed=9, forward=30, n_dividends=0)
    result = sector_eval.evaluate(
        short.panel,
        FAST,
        cost_model=CostModel(),
        start=short.d0,
        m=1,
        seed=1,
        pit_status=_pit_status(short),
        de5_verified_on=None,
        boards=None,
    )
    assert result.pit_gaps == ("de5_unverified",)
    record = to_stats_record(
        result,
        FAST,
        run_id="x",
        computed_at=datetime(2026, 9, 25, tzinfo=UTC),
        recompute_session=short.calendar[-1],
        running_commit="c",
        ci_attestation_ok=True,
    )
    assert record is None or record.pit_history_missing


def test_hindsight_or_backfill_records_never_become_rows(
    evaluation: sector_eval.SectorEvaluation, tmp_path: Path
) -> None:
    hindsight = dataclasses.replace(evaluation, regime="hindsight")
    with pytest.raises(ValueError):
        _record(hindsight)
    backfill = dataclasses.replace(evaluation, data_regime="backfill_non_pit")
    with pytest.raises(ValueError):
        _record(backfill)
    record = _record(evaluation)
    assert record is not None
    repo = SectorStatsRepository(_market_of(evaluation), tmp_path / "main.db")
    for bad in (
        dataclasses.replace(record, regime="hindsight"),
        dataclasses.replace(record, data_regime="backfill_non_pit"),
        dataclasses.replace(record, source_digest="0" * 64),
        dataclasses.replace(record, source_run_count=record.source_run_count - 1),
    ):
        with pytest.raises(BiasedDataRejected):
            repo.save(bad)


def test_fee_verified_on_parses_the_cost_model_date() -> None:
    assert sector_eval.fee_verified_on(CostModel()) is None
    assert sector_eval.fee_verified_on(CostModel(verified_on="2026-09-30")) == date(2026, 9, 30)


def test_data_quality_flags_future_dated_rows_and_duplicates(market: SyntheticMarket) -> None:
    frames = market.panel.frames
    bars = frames.bars.copy()
    bars.loc[bars.index[0], "session_date"] = market.calendar[-1]
    broken = replace_frame(
        market.panel, bars=pd.concat([bars, frames.bars.iloc[[5]]], ignore_index=True)
    )
    problems = sector_eval.data_quality_problems(broken, 0)
    assert "bars:future_dated" in problems and "bars:duplicates" in problems
    assert sector_eval.data_quality_problems(market.panel, 0) == []
    assert "ranking:constituent_invariant_violated" in sector_eval.data_quality_problems(
        market.panel, 1
    )


def test_q_is_averaged_per_week_and_b_is_floored_at_one_half(
    evaluation: sector_eval.SectorEvaluation,
) -> None:
    valid = [w for w in evaluation.main if w.valid]
    per_week = [sum(w.gross_beats().values()) / len(w.gross_beats()) for w in valid]
    summary = evaluation.statistics.main
    assert summary.q_gross == pytest.approx(math.fsum(per_week) / len(per_week))
    assert summary.b == max(summary.q_gross or 0.0, 0.5)


def test_a_card_in_insufficient_data_is_not_a_sample(market: SyntheticMarket) -> None:
    """C-42: no TWT48U_ALL ok run on one of the last L sessions -> no ranking that day."""
    t = market.calendar[-20]
    runs = market.panel.frames.runs
    missing = runs.loc[
        (runs["kind"] == "dividend_announce") & (runs["session_date"] == market.calendar[-22]),
        "run_id",
    ]
    gap = replace_frame(market.panel, runs=runs.loc[~runs["run_id"].isin(set(missing))])
    decision = sector_eval.decide(gap.as_of(t), V1)
    assert decision.insufficient == "ex_dividend_feed_gap"
    assert decision.ranking.ranked  # the core still ranks; the card would not show it
    clean = sector_eval.decide(market.panel.as_of(t), V1)
    assert clean.insufficient is None
    position = market.calendar.index(t)
    sessions = market.calendar[position + 1 : position + 6]
    window = HoldingWindow(t, sessions[0], sessions[-1], tuple(sessions))
    book = PriceBook.from_panel(gap)
    reason = sector_eval._invalid_reason(decision, market.calendar, V1, book, window)
    assert reason == "card_insufficient"


def test_a_missed_capture_day_is_never_silently_skipped() -> None:
    """D-2: a trading session without bars invalidates the samples that touch it."""
    small = synthetic_market(seed=12, forward=45, n_dividends=0, delist=False, reclassify=False)
    missed = small.calendar[small.calendar.index(small.d0) + 17]
    frames = small.panel.frames
    runs = frames.runs.loc[
        ~((frames.runs["kind"] == "bars") & (frames.runs["session_date"] == missed))
    ]
    bars = frames.bars.loc[frames.bars["session_date"] != missed]
    gap = replace_frame(small.panel, runs=runs, bars=bars)
    run = sector_eval.evaluate_views(
        gap.as_of,
        gap,
        V1,
        cost_model=CostModel(),
        start=small.d0,
        m=1,
        seed=1,
        calendar=small.calendar,  # the real trading calendar still lists the missed day
    )
    reasons = {week.decision_date: week.invalid_reason for phase in run.weeks for week in phase}
    assert reasons[missed] == "no_board"
    position = small.calendar.index(missed)
    for offset in range(1, V1.holding_days + 1):  # windows that hold through the missed day
        assert reasons[small.calendar[position - offset]] == "bars_gap"
    for offset in range(1, V1.lookback_days + 1):  # lookbacks that span it
        assert reasons[small.calendar[position + offset]] == "lookback_gap"


def test_small_sector_monitor_compares_rank_1_with_chance(
    evaluation: sector_eval.SectorEvaluation,
) -> None:
    groups = {g.group: g for g in evaluation.statistics.size_groups}
    assert set(groups) == {"5-9", "10-19", ">=20"}
    assert sum(g.observed_share for g in groups.values()) == pytest.approx(1.0)
    assert sum(g.expected_share for g in groups.values()) == pytest.approx(1.0)
    for group in groups.values():
        assert group.flagged == (group.observed_share > 2.0 * group.expected_share)
