"""API types of the sector momentum card (ADR-0012 D-10) and the gate's inputs.

**Field names follow ADR-0012 D-10 verbatim; D-10 is the only naming
authority** (qa re-review, dev-lead ruling 2026-09-24). Do not rename to match
the methodology's older spellings.

Two D-10 types live outside this package and cannot be imported here, because
``app.sectors`` must not reach ``app.api`` (C-2):

* ``PayloadStatus`` is re-declared below with the identical literal set;
  ``tests/test_sectors_models.py`` pins it to ``app.api.common.PayloadStatus``.
* ``DataMeta`` ("reused unchanged") is a type parameter: the router
  instantiates ``SectorMomentumResponse[DataMeta]``, so the schema carries the
  shared envelope without this package importing it.

The response model validates the structural rules of D-10 / C-23 / C-42 / C-43
at construction, so an assembler cannot emit a payload that breaks them.

The dataclasses at the bottom are *inputs* to :mod:`app.sectors.gate`, written
by the evaluator (wave 2) and the approval CLI (wave 3) through
:mod:`app.sectors.store`. They never appear in a response as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

#: Identical to ``app.api.common.PayloadStatus`` (pinned by a test).
PayloadStatus = Literal["ok", "insufficient_data"]

GateStatus = Literal["passed", "failed", "not_evaluated"]
NotEvaluatedReason = Literal[
    "pit_history_missing",  # NE-1
    "accumulating",  # NE-2
    "fee_unverified",  # NE-3
    "stale_recompute",  # NE-4
    "version_mismatch",  # NE-5
    "data_quality",  # NE-6
    "lookahead_tests_failed",  # NE-7
    "demo_data",  # NE-8
    "pending_review",  # D-8 first transition (adopted, risk §6.4)
]
ReasonCode = Literal[
    "unranked_category", "too_few_members", "low_coverage", "ex_dividend_exclusion"
]
PitGap = Literal["pit_universe", "pit_classification", "pit_ex_dividend", "de5_unverified"]
InsufficientReason = Literal[
    "as_of_unknown",
    "ex_dividend_feed_gap",
    "overall_completeness_low",
    "computable_ratio_low",
    "no_sector_computable",
]
GateName = Literal["G1", "G2", "G3", "G4", "G5", "G6"]

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class Accumulation(BaseModel):
    """Always present; feeds 「目前已累積 {n} 個」."""

    model_config = _FROZEN

    accumulated_samples: int
    #: D0; None before D0 -> front end uses risk sentence 2' (派工單 §8-3).
    accumulation_start: str | None
    required_samples: int


class HistoricalStat(BaseModel):
    """Rank 1 only; forward_pit only; None unless passed/failed (A class, C-23)."""

    model_config = _FROZEN

    rank_scope: Literal["rank_1"]
    method_version: str
    m_at_evaluation: int
    sample_count: int
    effective_sample_count: float
    beat_count_net: int
    beat_count_gross: int
    base_rate_net: float
    base_rate_gross: float
    ci_low_net: float
    ci_high_net: float
    bootstrap_low_net: float
    bootstrap_high_net: float
    delta_real: float
    delta_shuffle: float
    benchmark: Literal["equal_weight_market"]
    sample_start: str
    sample_end: str
    stats_as_of: str
    computed_at: str
    run_id: str


class GateCheck(BaseModel):
    model_config = _FROZEN

    gate: GateName
    passed: bool
    detail: str | None


class Coverage(BaseModel):
    """Counts attribute each name once: missing -> ex-date -> corporate action."""

    model_config = _FROZEN

    expected_count: int
    calculation_count: int
    missing_count: int
    ex_date_excluded_count: int
    corporate_action_excluded_count: int
    #: None: no suspension-list source; suspended names counted as missing.
    suspended_count: int | None
    #: |C| / |E| (all three categories count).
    coverage_ratio: float | None
    #: 1 - missing / |E| (category 1 only; risk §8-1).
    completeness_ratio: float | None

    @model_validator(mode="after")
    def _counts_add_up(self) -> Self:
        excluded = (
            self.missing_count + self.ex_date_excluded_count + self.corporate_action_excluded_count
        )
        if self.expected_count - excluded != self.calculation_count:
            raise ValueError("expected - missing - ex_date - corporate_action != calculation")
        return self


class ConstituentItem(BaseModel):
    model_config = _FROZEN

    symbol: str
    name: str
    return_L: float | None  # noqa: N815 -- D-10 field name
    #: None when the positions lookup failed; no badge (risk §6.3 H-2, C-34).
    held: bool | None


class SectorItem(BaseModel):
    model_config = _FROZEN

    rank: int
    sector_code: str
    sector_name: str
    sector_return_L: float | None  # noqa: N815 -- D-10 field name
    benchmark_return_L: float | None  # noqa: N815 -- D-10 field name
    rel_return_L: float | None  # noqa: N815 -- D-10 field name
    up_count: int
    constituent_count: int
    #: Descriptive; detail view only; NOT a ranking input (C-26).
    turnover_value_ratio_5_20: float | None
    #: Detail view only; reference, not a comparator.
    reference_taiex_return_L: float | None  # noqa: N815 -- D-10 field name
    coverage: Coverage
    top_contributor_share: float | None
    single_stock_dominated: bool
    #: Top 2 then bottom 1 (C-17); always 3 for a ranked sector (C-35).
    constituents: list[ConstituentItem]

    @model_validator(mode="after")
    def _same_set_counts(self) -> Self:
        if self.constituent_count != self.coverage.calculation_count:
            raise ValueError("constituent_count must equal coverage.calculation_count (C-32)")
        if len(self.constituents) != 3:
            raise ValueError("a ranked sector lists exactly 3 constituents (C-35)")
        return self


class ExcludedSector(BaseModel):
    model_config = _FROZEN

    sector_code: str
    sector_name: str
    reason_code: ReasonCode
    computable_count: int  # c = |C_g(t,L)|
    expected_count: int  # e = |E_g(t)|
    coverage: Coverage


class ExcludedReasonCounts(BaseModel):
    """{n1}/{n2}/{n3} for no_sector_computable; sum == ranked-eligible sectors."""

    model_config = _FROZEN

    too_few_members: int
    low_coverage: int
    ex_dividend_exclusion: int


class SectorMomentumResponse[DataMetaT: BaseModel](BaseModel):
    """``GET /api/sectors/momentum`` (ADR-0012 D-10).

    Instantiate as ``SectorMomentumResponse[DataMeta]`` in the router.
    """

    model_config = _FROZEN

    market: str
    status: PayloadStatus
    insufficient_reason: InsufficientReason | None
    reason: str | None
    method_version: str | None
    lookback_days: int | None
    holding_days: int | None
    data_as_of: str | None
    market_scope: Literal["twse_only"]
    benchmark: Literal["equal_weight_market"]
    data_source: str
    coverage: Coverage | None
    min_constituents: int
    sector_coverage_threshold: float
    overall_coverage_threshold: float
    computable_ratio: float | None
    computable_ratio_min: float
    computable_ratio_pct_display: float | None
    completeness_pct_display: float | None
    market_expected_count: int | None
    market_missing_count: int | None
    market_ex_date_excluded_count: int | None
    market_corporate_action_excluded_count: int | None
    market_ex_date_excluded_ratio: float | None
    ex_date_tag_ratio_min: float
    ex_date_tag: bool
    excluded_reason_counts: ExcludedReasonCounts | None
    headline_count: int
    sectors: list[SectorItem]
    excluded_sectors: list[ExcludedSector]
    gate_status: GateStatus
    not_evaluated_reason: NotEvaluatedReason | None
    not_evaluated_reasons: list[NotEvaluatedReason]
    pit_gaps: list[PitGap]
    accumulation: Accumulation
    historical_stat: HistoricalStat | None
    gate_checks: list[GateCheck] | None
    fee_verified_on: str | None
    disclosures: list[str]
    data: DataMetaT
    as_of: str

    @model_validator(mode="after")
    def _structural_rules(self) -> Self:
        insufficient = self.status == "insufficient_data"
        # C-42 / IP-1: a reason code iff the card is insufficient.
        if insufficient != (self.insufficient_reason is not None):
            raise ValueError("insufficient_reason must be set iff status == insufficient_data")
        if insufficient:
            # C-43 / IP-5: nothing ranked, nothing historical.
            if self.sectors or self.excluded_sectors:
                raise ValueError("insufficient_data carries no sectors (IP-5)")
            if self.historical_stat is not None or self.gate_checks is not None:
                raise ValueError("insufficient_data carries no historical statistics (IP-5)")
        # C-44 / 派工單 §10: n1/n2/n3 only for no_sector_computable.
        if (self.insufficient_reason == "no_sector_computable") != (
            self.excluded_reason_counts is not None
        ):
            raise ValueError("excluded_reason_counts is set iff no_sector_computable")
        not_evaluated = self.gate_status == "not_evaluated"
        # C-23: A-class objects are None whenever not evaluated (incl. pending_review).
        if not_evaluated and (self.historical_stat is not None or self.gate_checks is not None):
            raise ValueError("not_evaluated carries no historical statistics (C-23)")
        if not_evaluated != (self.not_evaluated_reason is not None):
            raise ValueError("not_evaluated_reason is set iff gate_status == not_evaluated")
        if not not_evaluated and self.not_evaluated_reasons:
            raise ValueError("not_evaluated_reasons is [] unless not_evaluated")
        if not_evaluated and self.not_evaluated_reason not in self.not_evaluated_reasons:
            raise ValueError("not_evaluated_reason must be one of not_evaluated_reasons")
        # C-29 / NR-2: demo data always reports demo_data first.
        if self.data_source == "demo_synthetic" and self.not_evaluated_reason != "demo_data":
            raise ValueError("demo_synthetic data must report not_evaluated_reason=demo_data")
        # C-40: pit_gaps non-empty iff NE-1 holds.
        if bool(self.pit_gaps) != ("pit_history_missing" in self.not_evaluated_reasons):
            raise ValueError("pit_gaps is non-empty iff pit_history_missing holds (C-40)")
        # C-28: rank lives on sectors only, and is 1..n in order.
        if [item.rank for item in self.sectors] != list(range(1, len(self.sectors) + 1)):
            raise ValueError("sector ranks must run 1..n in list order")
        return self


# ---------------------------------------------------------------------------
# Gate inputs (not API types)
# ---------------------------------------------------------------------------

StatsRegime = Literal["pit", "hindsight"]
DataRegime = Literal["forward_pit", "backfill_non_pit"]
ApprovalKind = Literal["first_transition_risk", "quarterly_qa"]
ApprovalOperator = Literal["ceo", "dev-lead"]
SelfcheckStatus = Literal["pass", "fail", "skipped_insufficient_n", "vacuous"]


@dataclass(frozen=True)
class GateCheckRecord:
    """One G1..G6 outcome as the evaluator computed it (candidate, never output as such)."""

    gate: GateName
    passed: bool
    detail: str | None = None


@dataclass(frozen=True)
class SelfcheckRecord:
    """One methodology T1..T9 runtime outcome (``sector_gate_checks``, check_kind=selfcheck)."""

    check_name: str
    status: SelfcheckStatus
    seed: int | None = None
    value: float | None = None
    detail: str | None = None


@dataclass(frozen=True)
class StatsRecord:
    """One ``sector_rank_stats`` row: the evaluator's result for one run (wave 2 writes it).

    ``regime`` / ``data_regime`` and the five ``source_*`` fields are
    provenance the repository checks on every save and load (D-14, C-27,
    C-50): anything but ``pit`` + ``forward_pit`` whose source fingerprint
    matches the market DB's ``pit_snapshot_runs`` is rejected. The fingerprint
    describes the source set 𝒮 -- every ``ok`` run with ``session_date <=
    source_session_end`` and ``run_id <= source_run_max`` -- in fixed width;
    no field lists the source runs one by one (C-50, C-51).
    """

    run_id: str
    method_version: str
    regime: StatsRegime
    data_regime: DataRegime
    #: First and last market-DB ``run_id`` of 𝒮.
    source_run_min: int
    source_run_max: int
    #: The latest ``session_date`` in 𝒮.
    source_session_end: date
    #: Number of runs in 𝒮 (> 0).
    source_run_count: int
    #: SHA-256 hex of 𝒮 (``app.data.panel.source_fingerprint``).
    source_digest: str
    m_at_evaluation: int
    sample_count: int
    effective_sample_count: float
    beat_count_net: int
    beat_count_gross: int
    base_rate_net: float
    base_rate_gross: float
    ci_low_net: float
    ci_high_net: float
    bootstrap_low_net: float
    bootstrap_high_net: float
    #: None when T8 did not produce it -- the evaluator must then fail the selfcheck (C-36).
    delta_real: float | None
    delta_shuffle: float | None
    sample_start: date
    sample_end: date
    stats_as_of: date
    computed_at: datetime
    #: Trading session the recompute ran for (NE-4 counts sessions from here).
    recompute_session: date
    #: ``git rev-parse HEAD`` of the scheduler process that computed the row (C-36).
    running_commit: str
    #: Methodology T1..T9 all passed in this run, CI attestation included (NE-7).
    selfcheck_passed: bool
    #: Future dates / duplicates / coverage checks passed (NE-6).
    data_quality_passed: bool
    #: The evaluator's own NE-1 finding; must be backed by a non-empty ``pit_gaps``.
    pit_history_missing: bool
    gate_checks: tuple[GateCheckRecord, ...]
    selfchecks: tuple[SelfcheckRecord, ...] = ()


@dataclass(frozen=True)
class ApprovalRecord:
    """One ``sector_gate_approvals`` row (CLI only, C-31)."""

    kind: ApprovalKind
    run_id: str
    method_version: str
    operator: ApprovalOperator
    reviewer: str
    review_doc_path: str
    review_doc_blob_hash: str
    approved_at: datetime


@dataclass(frozen=True)
class MethodRegistryRow:
    """One ``sector_method_registry`` row (D-6)."""

    method_version: str
    lookback_days: int
    holding_days: int
    frozen_commit: str
    registered_at: datetime
    accumulation_start: date | None
    first_forward_eval_at: datetime | None
    counts_toward_m: bool
