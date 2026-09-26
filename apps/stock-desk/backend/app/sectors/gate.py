"""The one place the effective ``gate_status`` is composed (ADR-0012 D-8, C-20).

Inputs are handed in by the caller -- the evaluator's statistics rows, the
approval rows, the registry's D0, the run-status summary of the market DB,
the fee and DE-5 verification dates and the deployed CI attestation -- all read
by the services layer. This module reads no environment, no configuration and
no database (C-24): there is no switch, list or variable that can bypass
NE-1..NE-8, and the result depends only on NE conditions, statistics rows and
approval rows.

Three states (methodology §6.3):

* ``not_evaluated`` when any of NE-1..NE-8 holds, or -- with none holding --
  while the method version still awaits its first ``first_transition_risk``
  approval (``pending_review``). Reason selection: NE-8 ``demo_data`` always
  wins (risk NR-2); otherwise the lowest-numbered NE; ``pending_review`` only
  when no NE holds. In this state the historical statistics and gate checks
  are ``None`` and the candidate result is not carried anywhere (C-23).
* ``failed`` / ``passed`` from the evaluator's G1..G6, after the approval
  rules: ``passed -> failed`` is immediate; ``failed -> passed`` needs a
  ``quarterly_qa`` approval for that same ``run_id``.

``pit_gaps`` (C-40) is computed only by :func:`pit_gaps`; NE-1 holds iff it is
non-empty. An evaluator that reports NE-1 while the gap list is empty is a
contradiction: the gate reports NE-6 instead and records an internal error,
never "NE-1 without a gap".

The whole-card ``insufficient_reason`` (C-42) is chosen here as well, in the
fixed order :data:`INSUFFICIENT_REASON_ORDER`. **Changing that order requires
a new risk review** (risk §9 IP-3); ``tests/test_sectors_gate.py`` pins it.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal, TypedDict, get_args

from app.data.calendar import TradingCalendar
from app.sectors.definition import SectorMomentumDefinition, require_published
from app.sectors.models import (
    Accumulation,
    ApprovalRecord,
    GateCheck,
    GateName,
    GateStatus,
    HistoricalStat,
    InsufficientReason,
    NotEvaluatedReason,
    PitGap,
    StatsRecord,
)

#: NE-1..NE-8 in number order (the tie-break order after NE-8's priority).
NE_ORDER: Final[tuple[NotEvaluatedReason, ...]] = (
    "pit_history_missing",
    "accumulating",
    "fee_unverified",
    "stale_recompute",
    "version_mismatch",
    "data_quality",
    "lookahead_tests_failed",
    "demo_data",
)
PENDING_REVIEW: Final[NotEvaluatedReason] = "pending_review"
DEMO_DATA_SOURCE: Final = "demo_synthetic"

#: Fixed output order of ``pit_gaps`` (risk §8-3).
PIT_GAP_ORDER: Final[tuple[PitGap, ...]] = (
    "pit_universe",
    "pit_classification",
    "pit_ex_dividend",
    "de5_unverified",
)

#: Whole-card insufficiency, first match wins (risk §9 IP-3, C-42).
#: CHANGING THIS ORDER REQUIRES A NEW RISK REVIEW.
INSUFFICIENT_REASON_ORDER: Final[tuple[InsufficientReason, ...]] = (
    "as_of_unknown",
    "ex_dividend_feed_gap",
    "overall_completeness_low",
    "computable_ratio_low",
    "no_sector_computable",
)

GATE_ORDER: Final[tuple[GateName, ...]] = get_args(GateName)

#: A snapshot kind carried forward for more than this many trading days stops
#: being valid for a decision date (ADR-0012 D-2).
MAX_CARRIED_SESSIONS: Final = 5

PitKind = Literal["listing", "classification", "dividend_announce"]
_GAP_KINDS: Final[tuple[tuple[PitGap, PitKind], ...]] = (
    ("pit_universe", "listing"),
    ("pit_classification", "classification"),
    ("pit_ex_dividend", "dividend_announce"),
)

# Internal error notes (logged by the caller, never output by the API).
ERROR_NE1_WITHOUT_GAPS: Final = "ne1_without_pit_gaps"
ERROR_MALFORMED_GATE_CHECKS: Final = "malformed_gate_checks"
ERROR_MIXED_VERSIONS: Final = "stats_history_mixes_versions"
ERROR_CONSTITUENT_INVARIANT: Final = "constituent_invariant_violated"
ERROR_T8_NOT_PRODUCED: Final = "t8_deltas_missing"
ERROR_STATS_REJECTED: Final = "stats_rejected_on_read"


# ---------------------------------------------------------------------------
# pit_gaps (C-40)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PitStatus:
    """``pit_snapshot_runs`` summarised by the services layer in one query."""

    #: D0 from ``sector_method_registry.accumulation_start``; None before D0.
    accumulation_start: date | None
    #: Sessions that have an ``ok`` run, per snapshot kind.
    ok_sessions: Mapping[PitKind, frozenset[date]]


@dataclass(frozen=True)
class EvaluationWindow:
    """The judged period: its decision dates and the observed trading calendar."""

    decision_dates: tuple[date, ...]
    trading_days: tuple[date, ...]


def _kind_has_gap(status: PitStatus, kind: PitKind, window: EvaluationWindow) -> bool:
    d0 = status.accumulation_start
    if d0 is None:
        return True
    ok = sorted(status.ok_sessions.get(kind, frozenset()))
    days = sorted(window.trading_days)
    for decision in window.decision_dates:
        if decision < d0:
            # Before D0 nothing was saved as of its day: not point-in-time.
            return True
        position = bisect_right(ok, decision)
        if position == 0:
            return True
        last_ok = ok[position - 1]
        carried = bisect_right(days, decision) - bisect_right(days, last_ok)
        if carried > MAX_CARRIED_SESSIONS:
            return True
    return False


def judged_window(
    trading_days: Sequence[date], accumulation_start: date | None, holding_days: int
) -> EvaluationWindow:
    """The read-time judged period: the evaluator's main-phase decision dates.

    Mirrors ``sector_eval``: from D0, every ``holding_days``-th session whose
    holding window has completed within ``trading_days`` (non-overlapping
    samples, methodology §5.1). Before D0 there is nothing judged.
    """
    days = tuple(sorted(set(trading_days)))
    if accumulation_start is None:
        return EvaluationWindow(decision_dates=(), trading_days=days)
    first = bisect_left(days, accumulation_start)
    decisions = days[first : max(first, len(days) - holding_days) : holding_days]
    return EvaluationWindow(decision_dates=decisions, trading_days=days)


def pit_gaps(
    pit_status: PitStatus, de5_verified_on: date | None, window: EvaluationWindow
) -> list[PitGap]:
    """What is still missing for point-in-time judgement, in fixed order (C-40).

    Shared by the evaluator and the read path. Before D0 the first three are
    always present; after D0 a kind is a gap when any judged decision date has
    no valid snapshot of it (carried forward more than 5 sessions is invalid).
    """
    gaps = [gap for gap, kind in _GAP_KINDS if _kind_has_gap(pit_status, kind, window)]
    if de5_verified_on is None:
        gaps.append("de5_unverified")
    return gaps


# ---------------------------------------------------------------------------
# insufficient_reason (C-42)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InsufficientChecks:
    """The five whole-card conditions; ``None`` means "no board to check"."""

    data_as_of_known: bool
    ex_dividend_feed_covered: bool | None = None
    completeness_low: bool | None = None
    computable_low: bool | None = None
    any_sector_ranked: bool | None = None


def insufficient_reason(checks: InsufficientChecks) -> InsufficientReason | None:
    """The first failing condition in :data:`INSUFFICIENT_REASON_ORDER`, else None."""
    holds: dict[InsufficientReason, bool] = {
        "as_of_unknown": not checks.data_as_of_known,
        "ex_dividend_feed_gap": checks.ex_dividend_feed_covered is False,
        "overall_completeness_low": checks.completeness_low is True,
        "computable_ratio_low": checks.computable_low is True,
        "no_sector_computable": checks.any_sector_ranked is False,
    }
    for reason in INSUFFICIENT_REASON_ORDER:
        if holds[reason]:
            return reason
    if checks.data_as_of_known and None in (
        checks.ex_dividend_feed_covered,
        checks.completeness_low,
        checks.computable_low,
        checks.any_sector_ranked,
    ):
        raise ValueError("a known data_as_of needs every board check filled in")
    return None


# ---------------------------------------------------------------------------
# gate_status (C-20)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectorGateRuntime:
    """The gate's process-level inputs besides database rows (all ``None`` = not verified).

    Read once per process by the services layer
    (:mod:`app.services.sector_runtime`) and handed in; the type lives here so
    the read-only router can accept it without reaching the services layer
    (ADR-0012 D-1, C-5).
    """

    ci_passed_commit: str | None
    fee_verified_on: date | None
    de5_verified_on: date | None


#: Nothing verified: NE-3 and NE-7 hold and ``de5_unverified`` stays in ``pit_gaps``.
UNVERIFIED_RUNTIME: Final = SectorGateRuntime(
    ci_passed_commit=None, fee_verified_on=None, de5_verified_on=None
)


@dataclass(frozen=True)
class GateInputs:
    definition: SectorMomentumDefinition
    #: The board's bars source; ``demo_synthetic`` forces NE-8.
    data_source: str
    board_method_version: str | None
    #: The board broke the constituent invariant (C-35) -> NE-6.
    board_invariant_violated: bool
    #: The board's data_as_of session (NE-4 counts sessions up to it).
    as_of_session: date | None
    calendar: TradingCalendar
    #: ``CostModel.verified_on`` (D9); None forces NE-3 (C-25).
    fee_verified_on: date | None
    #: ``twse_snapshot.CHANGE_SEMANTICS_VERIFIED_ON`` (DE-5).
    de5_verified_on: date | None
    #: ``ci_passed_commit`` of the deployed build; None when the attestation is absent.
    ci_passed_commit: str | None
    pit_status: PitStatus
    window: EvaluationWindow
    #: Chronological ``sector_rank_stats`` rows of one method version (the
    #: latest row's); forward_pit only (the repository refuses anything else).
    stats_history: tuple[StatsRecord, ...]
    approvals: tuple[ApprovalRecord, ...]
    #: The repository refused the statistics on the way out (D-14): fail closed as
    #: NE-6, with no statistics row to publish.
    stats_rejected: bool = False

    def __post_init__(self) -> None:
        # The gate's output reaches the card: published definitions only (C-47).
        require_published(self.definition)


@dataclass(frozen=True)
class GateOutcome:
    gate_status: GateStatus
    not_evaluated_reason: NotEvaluatedReason | None
    not_evaluated_reasons: tuple[NotEvaluatedReason, ...]
    pit_gaps: tuple[PitGap, ...]
    accumulation: Accumulation
    historical_stat: HistoricalStat | None
    gate_checks: tuple[GateCheck, ...] | None
    fee_verified_on: str | None
    #: Internal error notes for the caller to log; never output by the API.
    internal_errors: tuple[str, ...]


def candidate_result(stats: StatsRecord) -> Literal["passed", "failed"] | None:
    """G1..G6 all passed -> ``passed``, any failed -> ``failed``; None if malformed."""
    names = [check.gate for check in stats.gate_checks]
    if sorted(names) != sorted(GATE_ORDER):
        return None
    return "passed" if all(check.passed for check in stats.gate_checks) else "failed"


def _deltas_present(stats: StatsRecord) -> bool:
    return stats.delta_real is not None and stats.delta_shuffle is not None


def _clean_at_write(stats: StatsRecord, definition: SectorMomentumDefinition) -> bool:
    """G0 as far as the row itself can tell (used when folding the history)."""
    rules = definition.gate
    return (
        stats.selfcheck_passed
        and stats.data_quality_passed
        and not stats.pit_history_missing
        and _deltas_present(stats)
        and stats.sample_count >= rules.min_samples
        and stats.effective_sample_count >= rules.min_effective_samples
        and candidate_result(stats) is not None
    )


def published_status(
    history: Sequence[StatsRecord],
    approvals: Sequence[ApprovalRecord],
    definition: SectorMomentumDefinition,
) -> Literal["passed", "failed"] | None:
    """The status the approvals allow to be shown, or None while pending review.

    The fold starts at the run named by the version's first
    ``first_transition_risk`` approval (an approval naming an unknown run keeps
    the version pending -- fail closed). After it, rows that were not G0-clean
    when written are skipped; a failing candidate publishes ``failed`` at once;
    a passing one publishes ``passed`` only from ``passed`` or with a
    ``quarterly_qa`` approval for that run.
    """
    if not history:
        return None
    version = history[-1].method_version
    anchors = {
        approval.run_id
        for approval in approvals
        if approval.kind == "first_transition_risk" and approval.method_version == version
    }
    quarterly = {
        approval.run_id
        for approval in approvals
        if approval.kind == "quarterly_qa" and approval.method_version == version
    }
    status: Literal["passed", "failed"] | None = None
    started = False
    for record in history:
        if record.method_version != version:
            continue
        if not started:
            if record.run_id in anchors:
                started = True
                status = candidate_result(record) or "failed"
            continue
        if not _clean_at_write(record, definition):
            continue
        candidate = candidate_result(record)
        if candidate == "failed":
            status = "failed"
        elif status != "passed":
            status = "passed" if record.run_id in quarterly else "failed"
    return status if started else None


def _historical_stat(stats: StatsRecord) -> HistoricalStat:
    if stats.delta_real is None or stats.delta_shuffle is None:
        raise ValueError("a published statistic needs both T8 deltas (C-36, C-41)")
    return HistoricalStat(
        rank_scope="rank_1",
        method_version=stats.method_version,
        m_at_evaluation=stats.m_at_evaluation,
        sample_count=stats.sample_count,
        effective_sample_count=stats.effective_sample_count,
        beat_count_net=stats.beat_count_net,
        beat_count_gross=stats.beat_count_gross,
        base_rate_net=stats.base_rate_net,
        base_rate_gross=stats.base_rate_gross,
        ci_low_net=stats.ci_low_net,
        ci_high_net=stats.ci_high_net,
        bootstrap_low_net=stats.bootstrap_low_net,
        bootstrap_high_net=stats.bootstrap_high_net,
        delta_real=stats.delta_real,
        delta_shuffle=stats.delta_shuffle,
        benchmark="equal_weight_market",
        sample_start=stats.sample_start.isoformat(),
        sample_end=stats.sample_end.isoformat(),
        stats_as_of=stats.stats_as_of.isoformat(),
        computed_at=stats.computed_at.isoformat(),
        run_id=stats.run_id,
    )


def _gate_checks(stats: StatsRecord) -> tuple[GateCheck, ...]:
    by_name = {check.gate: check for check in stats.gate_checks}
    return tuple(
        GateCheck(gate=name, passed=by_name[name].passed, detail=by_name[name].detail)
        for name in GATE_ORDER
    )


def evaluate(inputs: GateInputs) -> GateOutcome:
    """Compose the effective three-state result for the card (ADR-0012 D-8)."""
    rules = inputs.definition.gate
    history = inputs.stats_history
    stats = history[-1] if history else None
    errors: list[str] = []
    holds: set[NotEvaluatedReason] = set()

    if stats is not None and any(row.method_version != stats.method_version for row in history):
        holds.add("data_quality")
        errors.append(ERROR_MIXED_VERSIONS)

    gaps = pit_gaps(inputs.pit_status, inputs.de5_verified_on, inputs.window)
    if gaps:  # NE-1 <=> pit_gaps non-empty
        holds.add("pit_history_missing")
    elif stats is not None and stats.pit_history_missing:
        holds.add("data_quality")
        errors.append(ERROR_NE1_WITHOUT_GAPS)

    if (
        stats is None
        or stats.sample_count < rules.min_samples
        or stats.effective_sample_count < rules.min_effective_samples
    ):
        holds.add("accumulating")

    if inputs.fee_verified_on is None:
        holds.add("fee_unverified")

    if (
        stats is not None
        and inputs.as_of_session is not None
        and inputs.calendar.trading_days_between(stats.recompute_session, inputs.as_of_session)
        > rules.stale_after_sessions
    ):
        holds.add("stale_recompute")

    if (
        stats is not None
        and inputs.board_method_version is not None
        and inputs.board_method_version != stats.method_version
    ):
        holds.add("version_mismatch")

    if stats is not None and not stats.data_quality_passed:
        holds.add("data_quality")
    if inputs.board_invariant_violated:
        holds.add("data_quality")
        errors.append(ERROR_CONSTITUENT_INVARIANT)
    if stats is not None and candidate_result(stats) is None:
        holds.add("data_quality")
        errors.append(ERROR_MALFORMED_GATE_CHECKS)

    if stats is not None:
        if not _deltas_present(stats):
            holds.add("lookahead_tests_failed")
            errors.append(ERROR_T8_NOT_PRODUCED)
        if (
            not stats.selfcheck_passed
            or inputs.ci_passed_commit is None
            or stats.running_commit != inputs.ci_passed_commit
        ):
            holds.add("lookahead_tests_failed")

    if inputs.stats_rejected:
        holds.add("data_quality")
        errors.append(ERROR_STATS_REJECTED)

    if inputs.data_source == DEMO_DATA_SOURCE:
        holds.add("demo_data")

    accumulation = Accumulation(
        accumulated_samples=stats.sample_count if stats is not None else 0,
        accumulation_start=(
            inputs.pit_status.accumulation_start.isoformat()
            if inputs.pit_status.accumulation_start is not None
            else None
        ),
        required_samples=rules.min_samples,
    )
    fee = inputs.fee_verified_on.isoformat() if inputs.fee_verified_on is not None else None

    def not_evaluated(reasons: tuple[NotEvaluatedReason, ...]) -> GateOutcome:
        primary = "demo_data" if "demo_data" in reasons else reasons[0]
        return GateOutcome(
            gate_status="not_evaluated",
            not_evaluated_reason=primary,
            not_evaluated_reasons=reasons,
            pit_gaps=tuple(gaps),
            accumulation=accumulation,
            historical_stat=None,
            gate_checks=None,
            fee_verified_on=fee,
            internal_errors=tuple(errors),
        )

    ordered = tuple(reason for reason in NE_ORDER if reason in holds)
    if ordered:
        return not_evaluated(ordered)

    # G0 holds from here on, so stats is present and well formed.
    if stats is None:  # pragma: no cover - NE-2 holds without stats
        raise RuntimeError("G0 cannot hold without a statistics row")
    status = published_status(history, inputs.approvals, inputs.definition)
    if status is None:
        return not_evaluated((PENDING_REVIEW,))
    return GateOutcome(
        gate_status=status,
        not_evaluated_reason=None,
        not_evaluated_reasons=(),
        pit_gaps=(),
        accumulation=accumulation,
        historical_stat=_historical_stat(stats),
        gate_checks=_gate_checks(stats),
        fee_verified_on=fee,
        internal_errors=tuple(errors),
    )


class GateResponseFields(TypedDict):
    """The D-10 fields :func:`response_fields` hands to the response model."""

    gate_status: GateStatus
    not_evaluated_reason: NotEvaluatedReason | None
    not_evaluated_reasons: list[NotEvaluatedReason]
    pit_gaps: list[PitGap]
    accumulation: Accumulation
    historical_stat: HistoricalStat | None
    gate_checks: list[GateCheck] | None
    fee_verified_on: str | None


def response_fields(outcome: GateOutcome, *, insufficient: bool) -> GateResponseFields:
    """The gate's part of the D-10 response: B-class state and A-class statistics.

    The API unpacks this into ``SectorMomentumResponse`` so that ``gate_status``
    keeps a single assignment site (C-20, T-17). When the whole card is
    ``insufficient_data`` the A-class objects are dropped whatever the state
    (IP-5, C-43); B-class fields are output unchanged for the record.
    """
    return GateResponseFields(
        gate_status=outcome.gate_status,
        not_evaluated_reason=outcome.not_evaluated_reason,
        not_evaluated_reasons=list(outcome.not_evaluated_reasons),
        pit_gaps=list(outcome.pit_gaps),
        accumulation=outcome.accumulation,
        historical_stat=None if insufficient else outcome.historical_stat,
        gate_checks=(
            None if insufficient or outcome.gate_checks is None else list(outcome.gate_checks)
        ),
        fee_verified_on=outcome.fee_verified_on,
    )
