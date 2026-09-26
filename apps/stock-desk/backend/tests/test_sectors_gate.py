"""The effective three-state gate (ADR-0012 D-8, C-19/20/23/25/29/40/42).

* T-11: NE-1..NE-8 and pending_review each alone; priority (NE-8 first, then
  the lowest number, pending_review last); pending_review only when no NE
  holds, for both candidate outcomes, with no candidate leaking; fee
  unverified always NE-3; NE-4 on the 21st trading day, not the 20th; G1..G6
  each failing alone -> failed; approval rules for first transition and
  failed -> passed.
* T-25: pit_gaps single cases, fixed order, D0 missing, NE-1 without gaps ->
  NE-6, [] when NE-1 does not hold.
* T-27 (backend): the five insufficient codes alone, every pair resolves to
  the earlier one, and the order constant is pinned (changing it needs a new
  risk review).
"""

from __future__ import annotations

import dataclasses
import itertools
from datetime import UTC, date, datetime
from typing import get_args

import pytest

from app.data.calendar import TradingCalendar
from app.sectors import gate
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.gate import (
    EvaluationWindow,
    GateInputs,
    InsufficientChecks,
    PitStatus,
    evaluate,
    insufficient_reason,
    pit_gaps,
)
from app.sectors.models import (
    ApprovalRecord,
    GateCheckRecord,
    GateName,
    InsufficientReason,
    NotEvaluatedReason,
    StatsRecord,
)
from tests.sectors_helpers import weekdays
from tests.source_helpers import DEFAULT_FINGERPRINT, source_fields

DAYS = tuple(weekdays(420, date(2026, 1, 5)))
D0 = DAYS[0]
CALENDAR = TradingCalendar(DAYS)
KINDS: tuple[gate.PitKind, ...] = ("listing", "classification", "dividend_announce")
DECISIONS = DAYS[5:300:5]
RECOMPUTE = DAYS[300]
COMMIT = "0123abcd"
GATES: tuple[GateName, ...] = ("G1", "G2", "G3", "G4", "G5", "G6")


def _status(**missing: tuple[date, ...]) -> PitStatus:
    return PitStatus(
        accumulation_start=D0,
        ok_sessions={kind: frozenset(DAYS) - set(missing.get(kind, ())) for kind in KINDS},
    )


def _window(decisions: tuple[date, ...] = DECISIONS) -> EvaluationWindow:
    return EvaluationWindow(decision_dates=decisions, trading_days=DAYS)


def _stats(
    run_id: str = "run-1", *, failing: tuple[GateName, ...] = (), **kw: object
) -> StatsRecord:
    base = StatsRecord(
        run_id=run_id,
        method_version=V1.method_version,
        regime="pit",
        data_regime="forward_pit",
        **source_fields(DEFAULT_FINGERPRINT),  # type: ignore[arg-type]
        m_at_evaluation=1,
        sample_count=160,
        effective_sample_count=70.0,
        beat_count_net=110,
        beat_count_gross=120,
        base_rate_net=0.48,
        base_rate_gross=0.52,
        ci_low_net=0.60,
        ci_high_net=0.75,
        bootstrap_low_net=0.59,
        bootstrap_high_net=0.76,
        delta_real=20.75,
        delta_shuffle=3.1,
        sample_start=DAYS[5],
        sample_end=DAYS[295],
        stats_as_of=DAYS[295],
        computed_at=datetime(2027, 3, 1, 12, tzinfo=UTC),
        recompute_session=RECOMPUTE,
        running_commit=COMMIT,
        selfcheck_passed=True,
        data_quality_passed=True,
        pit_history_missing=False,
        gate_checks=tuple(GateCheckRecord(gate=g, passed=g not in failing) for g in GATES),
    )
    return dataclasses.replace(base, **kw)  # type: ignore[arg-type]


def _approval(run_id: str = "run-1", kind: str = "first_transition_risk") -> ApprovalRecord:
    return ApprovalRecord(
        kind=kind,  # type: ignore[arg-type]
        run_id=run_id,
        method_version=V1.method_version,
        operator="dev-lead" if kind == "quarterly_qa" else "ceo",
        reviewer="risk-compliance-officer" if kind != "quarterly_qa" else "qa-reviewer",
        review_doc_path="work/review.md",
        review_doc_blob_hash="deadbeef",
        approved_at=datetime(2027, 3, 2, tzinfo=UTC),
    )


def _inputs(**kw: object) -> GateInputs:
    base = GateInputs(
        definition=V1,
        data_source="twse_snapshot",
        board_method_version=V1.method_version,
        board_invariant_violated=False,
        as_of_session=DAYS[305],
        calendar=CALENDAR,
        fee_verified_on=date(2026, 9, 1),
        de5_verified_on=date(2026, 9, 1),
        ci_passed_commit=COMMIT,
        pit_status=_status(),
        window=_window(),
        stats_history=(_stats(),),
        approvals=(_approval(),),
    )
    return dataclasses.replace(base, **kw)  # type: ignore[arg-type]


def _assert_not_evaluated(outcome: gate.GateOutcome, reason: NotEvaluatedReason) -> None:
    assert outcome.gate_status == "not_evaluated"
    assert outcome.not_evaluated_reason == reason
    assert outcome.historical_stat is None
    assert outcome.gate_checks is None


# ---------------------------------------------------------------------------
# baseline
# ---------------------------------------------------------------------------


def test_clean_inputs_with_approval_pass() -> None:
    outcome = evaluate(_inputs())
    assert outcome.gate_status == "passed"
    assert outcome.not_evaluated_reason is None and outcome.not_evaluated_reasons == ()
    assert outcome.pit_gaps == ()
    assert outcome.historical_stat is not None
    assert outcome.historical_stat.delta_real == 20.75
    assert outcome.historical_stat.delta_shuffle == 3.1
    assert [check.gate for check in outcome.gate_checks or ()] == list(GATES)
    assert outcome.accumulation.accumulated_samples == 160
    assert outcome.accumulation.accumulation_start == D0.isoformat()
    assert outcome.accumulation.required_samples == 150
    assert outcome.fee_verified_on == "2026-09-01"


# ---------------------------------------------------------------------------
# each NE alone (T-11)
# ---------------------------------------------------------------------------

SINGLE_NE: dict[NotEvaluatedReason, list[dict[str, object]]] = {
    "pit_history_missing": [
        {"de5_verified_on": None},
        {"pit_status": _status(listing=DAYS[100:110])},
    ],
    "accumulating": [
        {"stats_history": (_stats(sample_count=149),)},
        {"stats_history": (_stats(effective_sample_count=59.9),)},
        {"stats_history": ()},
    ],
    "fee_unverified": [{"fee_verified_on": None}],
    "stale_recompute": [{"as_of_session": DAYS[321]}],
    "version_mismatch": [{"board_method_version": "sector-rel-v1.1-L20-H5"}],
    "data_quality": [
        {"stats_history": (_stats(data_quality_passed=False),)},
        {"board_invariant_violated": True},
        {"stats_history": (_stats(gate_checks=(GateCheckRecord("G1", True),)),)},
        {"stats_history": (_stats(pit_history_missing=True),)},
    ],
    "lookahead_tests_failed": [
        {"stats_history": (_stats(selfcheck_passed=False),)},
        {"ci_passed_commit": "ffff0000"},
        {"ci_passed_commit": None},
        {"stats_history": (_stats(delta_shuffle=None),)},
        {"stats_history": (_stats(delta_real=None),)},
    ],
    "demo_data": [{"data_source": "demo_synthetic"}],
}


@pytest.mark.parametrize(
    ("reason", "overrides"),
    [(reason, case) for reason, cases in SINGLE_NE.items() for case in cases],
)
def test_each_ne_alone(reason: NotEvaluatedReason, overrides: dict[str, object]) -> None:
    outcome = evaluate(_inputs(**overrides))
    _assert_not_evaluated(outcome, reason)
    assert outcome.not_evaluated_reasons == (reason,)
    assert bool(outcome.pit_gaps) == (reason == "pit_history_missing")


def test_fee_unverified_always_forces_not_evaluated() -> None:
    for case in (_inputs(fee_verified_on=None), _inputs(fee_verified_on=None, approvals=())):
        outcome = evaluate(case)
        assert outcome.gate_status == "not_evaluated"
        assert "fee_unverified" in outcome.not_evaluated_reasons
        assert outcome.fee_verified_on is None


def test_ne4_boundary_20th_trading_day_holds_21st_is_stale() -> None:
    assert CALENDAR.trading_days_between(RECOMPUTE, DAYS[320]) == 20
    assert evaluate(_inputs(as_of_session=DAYS[320])).gate_status == "passed"
    _assert_not_evaluated(evaluate(_inputs(as_of_session=DAYS[321])), "stale_recompute")


# ---------------------------------------------------------------------------
# priority (T-11, NR-2)
# ---------------------------------------------------------------------------


def test_demo_data_wins_over_ne1() -> None:
    outcome = evaluate(_inputs(data_source="demo_synthetic", de5_verified_on=None))
    _assert_not_evaluated(outcome, "demo_data")
    assert outcome.not_evaluated_reasons == ("pit_history_missing", "demo_data")
    assert outcome.pit_gaps == ("de5_unverified",)


def test_demo_data_wins_over_everything() -> None:
    outcome = evaluate(
        _inputs(
            data_source="demo_synthetic",
            fee_verified_on=None,
            stats_history=(),
            de5_verified_on=None,
        )
    )
    _assert_not_evaluated(outcome, "demo_data")
    assert outcome.not_evaluated_reasons == (
        "pit_history_missing",
        "accumulating",
        "fee_unverified",
        "demo_data",
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"fee_verified_on": None, "board_method_version": "x-other"}, "fee_unverified"),
        ({"stats_history": (_stats(sample_count=10, selfcheck_passed=False),)}, "accumulating"),
        ({"as_of_session": DAYS[330], "board_invariant_violated": True}, "stale_recompute"),
        ({"de5_verified_on": None, "fee_verified_on": None}, "pit_history_missing"),
        ({"ci_passed_commit": None, "board_invariant_violated": True}, "data_quality"),
    ],
)
def test_otherwise_the_lowest_number_wins(
    overrides: dict[str, object], expected: NotEvaluatedReason
) -> None:
    outcome = evaluate(_inputs(**overrides))
    _assert_not_evaluated(outcome, expected)
    assert len(outcome.not_evaluated_reasons) >= 2
    assert outcome.not_evaluated_reasons[0] == expected


def test_ne_order_constant_is_pinned() -> None:
    assert gate.NE_ORDER == (
        "pit_history_missing",
        "accumulating",
        "fee_unverified",
        "stale_recompute",
        "version_mismatch",
        "data_quality",
        "lookahead_tests_failed",
        "demo_data",
    )


# ---------------------------------------------------------------------------
# pending_review (risk §6.4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failing", [(), ("G3",)])
def test_pending_review_hides_either_candidate(failing: tuple[GateName, ...]) -> None:
    outcome = evaluate(_inputs(approvals=(), stats_history=(_stats(failing=failing),)))
    _assert_not_evaluated(outcome, "pending_review")
    assert outcome.not_evaluated_reasons == ("pending_review",)
    assert outcome.pit_gaps == ()
    rendered = repr(outcome)
    assert "'passed'" not in rendered and "'failed'" not in rendered
    assert "G3" not in rendered


def test_pending_review_never_appears_alongside_an_ne() -> None:
    outcome = evaluate(_inputs(approvals=(), fee_verified_on=None))
    assert outcome.not_evaluated_reasons == ("fee_unverified",)


def test_quarterly_qa_alone_does_not_lift_pending_review() -> None:
    outcome = evaluate(_inputs(approvals=(_approval(kind="quarterly_qa"),)))
    _assert_not_evaluated(outcome, "pending_review")


def test_an_approval_for_an_unknown_run_keeps_the_version_pending() -> None:
    outcome = evaluate(_inputs(approvals=(_approval("run-that-does-not-exist"),)))
    _assert_not_evaluated(outcome, "pending_review")


def test_an_approval_for_another_version_does_not_count() -> None:
    other = dataclasses.replace(_approval(), method_version="sector-rel-v1.1-L20-H5")
    _assert_not_evaluated(evaluate(_inputs(approvals=(other,))), "pending_review")


# ---------------------------------------------------------------------------
# G1..G6 each failing alone -> failed (C-19)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failing", GATES)
def test_each_gate_failing_alone_fails(failing: GateName) -> None:
    outcome = evaluate(_inputs(stats_history=(_stats(failing=(failing,)),)))
    assert outcome.gate_status == "failed"
    assert outcome.not_evaluated_reason is None
    assert outcome.historical_stat is not None
    checks = {check.gate: check.passed for check in outcome.gate_checks or ()}
    assert [name for name, ok in checks.items() if not ok] == [failing]


def test_changing_only_delta_shuffle_does_not_change_the_status() -> None:
    for value in (-50.0, 0.0, 19.0, 50.0):
        outcome = evaluate(_inputs(stats_history=(_stats(delta_shuffle=value),)))
        assert outcome.gate_status == "passed"


# ---------------------------------------------------------------------------
# transitions (D-8)
# ---------------------------------------------------------------------------


def _history(*candidates: tuple[str, tuple[GateName, ...]]) -> tuple[StatsRecord, ...]:
    return tuple(
        _stats(run_id, failing=failing, computed_at=datetime(2027, 3, 1 + n, tzinfo=UTC))
        for n, (run_id, failing) in enumerate(candidates)
    )


def test_passed_to_failed_is_immediate() -> None:
    history = _history(("r1", ()), ("r2", ("G6",)))
    assert evaluate(_inputs(stats_history=history, approvals=(_approval("r1"),))).gate_status == (
        "failed"
    )


def test_failed_to_passed_needs_quarterly_qa_on_that_run() -> None:
    history = _history(("r1", ()), ("r2", ("G6",)), ("r3", ()))
    without = evaluate(_inputs(stats_history=history, approvals=(_approval("r1"),)))
    assert without.gate_status == "failed"
    wrong_run = evaluate(
        _inputs(stats_history=history, approvals=(_approval("r1"), _approval("r2", "quarterly_qa")))
    )
    assert wrong_run.gate_status == "failed"
    with_qa = evaluate(
        _inputs(stats_history=history, approvals=(_approval("r1"), _approval("r3", "quarterly_qa")))
    )
    assert with_qa.gate_status == "passed"


def test_first_transition_publishes_the_approved_candidate() -> None:
    history = _history(("r1", ("G2",)), ("r2", ()))
    assert (
        evaluate(_inputs(stats_history=history[:1], approvals=(_approval("r1"),))).gate_status
        == "failed"
    )
    # After a failed first transition, passing again still needs quarterly QA.
    assert evaluate(_inputs(stats_history=history, approvals=(_approval("r1"),))).gate_status == (
        "failed"
    )


def test_stats_history_mixing_versions_is_a_data_quality_failure() -> None:
    mixed = (_stats("r0", method_version="sector-rel-v1.1-L20-H5"), _stats("r1"))
    outcome = evaluate(_inputs(stats_history=mixed))
    _assert_not_evaluated(outcome, "data_quality")
    assert gate.ERROR_MIXED_VERSIONS in outcome.internal_errors


# ---------------------------------------------------------------------------
# pit_gaps (C-40, T-25)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "de5", "expected"),
    [
        (_status(listing=DAYS[100:110]), date(2026, 9, 1), ["pit_universe"]),
        (_status(classification=DAYS[100:110]), date(2026, 9, 1), ["pit_classification"]),
        (_status(dividend_announce=DAYS[100:110]), date(2026, 9, 1), ["pit_ex_dividend"]),
        (_status(), None, ["de5_unverified"]),
        (
            _status(dividend_announce=DAYS[100:110], listing=DAYS[100:110]),
            None,
            ["pit_universe", "pit_ex_dividend", "de5_unverified"],
        ),
    ],
)
def test_pit_gaps_cases_and_fixed_order(
    status: PitStatus, de5: date | None, expected: list[str]
) -> None:
    assert pit_gaps(status, de5, _window()) == expected


def test_before_d0_the_three_snapshot_gaps_always_hold() -> None:
    status = PitStatus(
        accumulation_start=None, ok_sessions={kind: frozenset(DAYS) for kind in KINDS}
    )
    assert pit_gaps(status, date(2026, 9, 1), _window(())) == [
        "pit_universe",
        "pit_classification",
        "pit_ex_dividend",
    ]
    outcome = evaluate(_inputs(pit_status=status, stats_history=()))
    assert outcome.accumulation.accumulation_start is None
    assert outcome.not_evaluated_reason == "pit_history_missing"
    assert outcome.pit_gaps == ("pit_universe", "pit_classification", "pit_ex_dividend")


def test_carry_forward_is_valid_for_five_sessions_not_six() -> None:
    decision = DAYS[110]
    five = _status(listing=DAYS[106:111])  # last ok DAYS[105]: 5 sessions carried
    six = _status(listing=DAYS[105:111])  # last ok DAYS[104]: 6 sessions carried
    assert pit_gaps(five, date(2026, 9, 1), _window((decision,))) == []
    assert pit_gaps(six, date(2026, 9, 1), _window((decision,))) == ["pit_universe"]


def test_a_decision_date_before_d0_is_a_gap() -> None:
    late_d0 = dataclasses.replace(_status(), accumulation_start=DAYS[50])
    assert pit_gaps(late_d0, date(2026, 9, 1), _window((DAYS[40],))) == [
        "pit_universe",
        "pit_classification",
        "pit_ex_dividend",
    ]


def test_ne1_claimed_without_gaps_becomes_ne6() -> None:
    outcome = evaluate(_inputs(stats_history=(_stats(pit_history_missing=True),)))
    _assert_not_evaluated(outcome, "data_quality")
    assert outcome.pit_gaps == ()
    assert "pit_history_missing" not in outcome.not_evaluated_reasons
    assert gate.ERROR_NE1_WITHOUT_GAPS in outcome.internal_errors


def test_no_ne1_means_no_gaps() -> None:
    outcome = evaluate(_inputs(stats_history=()))
    assert outcome.not_evaluated_reasons == ("accumulating",)
    assert outcome.pit_gaps == ()


def test_pit_gap_order_constant_is_pinned() -> None:
    assert gate.PIT_GAP_ORDER == (
        "pit_universe",
        "pit_classification",
        "pit_ex_dividend",
        "de5_unverified",
    )


# ---------------------------------------------------------------------------
# insufficient_reason (C-42, T-27 backend)
# ---------------------------------------------------------------------------

ALL_GOOD = InsufficientChecks(
    data_as_of_known=True,
    ex_dividend_feed_covered=True,
    completeness_low=False,
    computable_low=False,
    any_sector_ranked=True,
)
FAILING: dict[InsufficientReason, dict[str, bool]] = {
    "as_of_unknown": {"data_as_of_known": False},
    "ex_dividend_feed_gap": {"ex_dividend_feed_covered": False},
    "overall_completeness_low": {"completeness_low": True},
    "computable_ratio_low": {"computable_low": True},
    "no_sector_computable": {"any_sector_ranked": False},
}


def test_insufficient_order_is_pinned_and_matches_the_literal() -> None:
    expected = (
        "as_of_unknown",
        "ex_dividend_feed_gap",
        "overall_completeness_low",
        "computable_ratio_low",
        "no_sector_computable",
    )
    assert gate.INSUFFICIENT_REASON_ORDER == expected
    assert get_args(InsufficientReason) == expected


@pytest.mark.parametrize("reason", list(FAILING))
def test_each_insufficient_reason_alone(reason: InsufficientReason) -> None:
    assert insufficient_reason(dataclasses.replace(ALL_GOOD, **FAILING[reason])) == reason


@pytest.mark.parametrize(
    ("first", "second"), list(itertools.combinations(gate.INSUFFICIENT_REASON_ORDER, 2))
)
def test_any_pair_resolves_to_the_earlier_reason(
    first: InsufficientReason, second: InsufficientReason
) -> None:
    both = dataclasses.replace(ALL_GOOD, **FAILING[first], **FAILING[second])
    assert insufficient_reason(both) == first


def test_no_board_is_as_of_unknown_and_all_good_is_sufficient() -> None:
    assert insufficient_reason(InsufficientChecks(data_as_of_known=False)) == "as_of_unknown"
    assert insufficient_reason(ALL_GOOD) is None
    with pytest.raises(ValueError):
        insufficient_reason(InsufficientChecks(data_as_of_known=True))
