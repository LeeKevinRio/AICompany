"""Sensitivity variants of the biased study (methodology §11.1; ADR-0012 D-15, C-48, C-49).

Methodology §11.1 registered four sensitivity values -- liquidity NT$5M and
NT$20M, minimum constituents 3 and 8 -- to be **listed, never used to choose**.
Two of them are looser than v1, so :class:`~app.sectors.definition.SectorMomentumDefinition`
cannot express them (its construction refuses anything looser, T-12). The
concrete types that can carry them live here and nowhere else:
:class:`ResearchVariant`, :class:`ResearchUniverseRules` and
:class:`ResearchCoverageRules`. They satisfy the core's structural protocols
(``SectorEvalDefinition``), so the variants run through the very same function
objects the judged path uses -- ``sector_eval.evaluate_views`` and below it
``universe.calculation_set`` / ``ranking.rank_sectors`` (T-15, T-32).

Rules (C-48):

* nothing here inherits from, ``dataclasses.replace``-s or constructs a
  published type (``SectorMomentumDefinition``, ``UniverseRules``,
  ``CoverageRules``, ``GateRules``); values are copied field by field;
* a variant's ``method_version`` lives in the ``research-sens-`` namespace and
  is never a method version (``is_method_version`` is False), so no gated
  entry, repository or registry accepts it (C-47);
* each variant is derived from a published definition and changes exactly one
  parameter; its ``gate`` **is** the base's object, and lookback, holding and
  the open limit-up factor are the base's; ``min_constituents`` stays >= 3
  (top-2 + bottom-1, C-35);
* :data:`SENSITIVITY_VARIANTS` is the §11.1 table -- two independent axes,
  four variants, no cross combinations -- and every run computes the base and
  all of them, and stores all of them (changing the table needs a methodology
  §11.1 amendment reviewed by qa first).

Data scope and output are the biased study's (C-49): hindsight views only,
``backfill_non_pit`` runs only, every session before D0; results go to the
research DB only, each row with the bias label, ``variant_of`` and
``variant_diff``. A version proposed after reading these numbers counts
towards m (``counts_toward_m=1``, D-14).
"""

from __future__ import annotations

import dataclasses
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Final, Literal

from app.backtest.costs import CostModel
from app.data.market_panel import MarketPanelReader
from app.data.panel import MarketPanel
from app.research.sector_biased.hindsight import BIAS_DIRECTIONS, BIAS_LABEL
from app.research.sector_biased.store import (
    DATA_REGIME,
    ResearchStore,
    SensitivityRow,
)
from app.research.sector_biased.study import (
    TEST_SESSIONS,
    TRAIN_SESSIONS,
    BiasedScopeViolation,
    BiasedStudyReport,
    admit_biased_panel,
    jsonable,
    require_before_d0,
    study_on_hindsight,
)
from app.sectors.definition import (
    SECTOR_MOMENTUM_V1,
    CoverageRulesView,
    GateRules,
    SectorEvalDefinition,
    SectorMomentumDefinition,
    UniverseRulesView,
    is_method_version,
    require_published,
)

#: A research variant's name: ``research-sens-<lowercase tokens joined by ->``.
RESEARCH_VERSION_PATTERN: Final = re.compile(r"^research-sens-[a-z0-9.]+(?:-[a-z0-9.]+)*$")
#: Fewer constituents cannot list top-2 + bottom-1 (C-35).
MIN_RESEARCH_CONSTITUENTS: Final = 3

#: The two parameters §11.1 varies, as ``variant_diff`` keys.
LIQUIDITY: Final = "universe.min_median_traded_value"
MIN_CONSTITUENTS: Final = "coverage.min_constituents"
VariedParameter = Literal["universe.min_median_traded_value", "coverage.min_constituents"]


class InvalidVariant(ValueError):
    """A research variant broke one of the C-48 rules."""


@dataclass(frozen=True)
class ResearchUniverseRules:
    """Every field of ``UniverseRules``, without its tighten-only floors."""

    min_listing_sessions: int
    liquidity_window_sessions: int
    min_median_traded_value: float
    min_traded_sessions: int
    eligible_security_types: frozenset[str]
    unranked_sector_codes: frozenset[str]
    excluded_sector_codes: frozenset[str]
    daily_price_limit: float
    daily_price_limit_tolerance: float

    def __post_init__(self) -> None:
        if self.min_median_traded_value <= 0:
            raise InvalidVariant("min_median_traded_value must be positive")


@dataclass(frozen=True)
class ResearchCoverageRules:
    """Every field of ``CoverageRules``, with ``min_constituents`` allowed down to 3."""

    min_constituents: int
    sector_coverage_threshold: float
    overall_coverage_threshold: float
    computable_ratio_min: float
    ex_date_tag_ratio_min: float

    def __post_init__(self) -> None:
        if self.min_constituents < MIN_RESEARCH_CONSTITUENTS:
            raise InvalidVariant(
                f"min_constituents must be at least {MIN_RESEARCH_CONSTITUENTS} (C-35)"
            )


@dataclass(frozen=True)
class ResearchVariant:
    """One sensitivity variant: a ``SectorEvalDefinition`` that is not a method version."""

    method_version: str
    #: The published base's ``method_version``.
    variant_of: str
    lookback_days: int
    holding_days: int
    universe: ResearchUniverseRules
    coverage: ResearchCoverageRules
    #: The base's own object, never a copy (C-48).
    gate: GateRules
    open_limit_up_factor: float
    single_stock_dominance_share: float

    def __post_init__(self) -> None:
        if RESEARCH_VERSION_PATTERN.fullmatch(self.method_version) is None:
            raise InvalidVariant(
                f"{self.method_version!r} must match {RESEARCH_VERSION_PATTERN.pattern}"
            )
        if is_method_version(self.method_version):  # pragma: no cover - disjoint namespaces
            raise InvalidVariant(f"{self.method_version!r} must not be a method version")


def _universe_copy(
    rules: UniverseRulesView, *, min_median_traded_value: float | None = None
) -> ResearchUniverseRules:
    return ResearchUniverseRules(
        min_listing_sessions=rules.min_listing_sessions,
        liquidity_window_sessions=rules.liquidity_window_sessions,
        min_median_traded_value=(
            rules.min_median_traded_value
            if min_median_traded_value is None
            else min_median_traded_value
        ),
        min_traded_sessions=rules.min_traded_sessions,
        eligible_security_types=rules.eligible_security_types,
        unranked_sector_codes=rules.unranked_sector_codes,
        excluded_sector_codes=rules.excluded_sector_codes,
        daily_price_limit=rules.daily_price_limit,
        daily_price_limit_tolerance=rules.daily_price_limit_tolerance,
    )


def _coverage_copy(
    rules: CoverageRulesView, *, min_constituents: int | None = None
) -> ResearchCoverageRules:
    return ResearchCoverageRules(
        min_constituents=rules.min_constituents if min_constituents is None else min_constituents,
        sector_coverage_threshold=rules.sector_coverage_threshold,
        overall_coverage_threshold=rules.overall_coverage_threshold,
        computable_ratio_min=rules.computable_ratio_min,
        ex_date_tag_ratio_min=rules.ex_date_tag_ratio_min,
    )


def research_version(base: SectorMomentumDefinition, tag: str) -> str:
    """``research-sens-<base version without its family prefix, lower-cased>-<tag>``."""
    family = "sector-rel-"
    if not base.method_version.startswith(family):  # pragma: no cover - C-16 pattern
        raise InvalidVariant(f"{base.method_version!r} is not a sector-rel version")
    return f"research-sens-{base.method_version[len(family) :].lower()}-{tag}"


def parameters(definition: SectorEvalDefinition) -> dict[str, object]:
    """Every parameter a variant may be compared on, flattened (names as in ``variant_diff``).

    ``gate`` is compared by identity (its object id), never by value: an equal
    copy of the base's gate is a difference.
    """
    flat: dict[str, object] = {
        "lookback_days": definition.lookback_days,
        "holding_days": definition.holding_days,
        "open_limit_up_factor": definition.open_limit_up_factor,
        "single_stock_dominance_share": definition.single_stock_dominance_share,
        "gate": id(definition.gate),
    }
    for field in dataclasses.fields(ResearchUniverseRules):
        flat[f"universe.{field.name}"] = getattr(definition.universe, field.name)
    for field in dataclasses.fields(ResearchCoverageRules):
        flat[f"coverage.{field.name}"] = getattr(definition.coverage, field.name)
    return flat


def variant_diff(
    base: SectorEvalDefinition, variant: SectorEvalDefinition
) -> dict[str, dict[str, object]]:
    """``{parameter: {"base": ..., "variant": ...}}`` for every parameter that differs."""
    left, right = parameters(base), parameters(variant)
    return {
        name: {"base": left[name], "variant": right[name]}
        for name in left
        if left[name] != right[name]
    }


def check_variant(base: SectorMomentumDefinition, variant: ResearchVariant) -> None:
    """C-48 against the base: one parameter changed, the base's gate object, >= 3 constituents."""
    require_published(base)
    if variant.variant_of != base.method_version:
        raise InvalidVariant(f"{variant.method_version} is not derived from {base.method_version}")
    if variant.gate is not base.gate:
        raise InvalidVariant(f"{variant.method_version} must carry the base's own gate object")
    changed = sorted(variant_diff(base, variant))
    if changed not in ([LIQUIDITY], [MIN_CONSTITUENTS]):
        raise InvalidVariant(
            f"{variant.method_version} must change exactly one registered parameter; "
            f"changed {changed}"
        )


def derive_variant(
    base: SectorMomentumDefinition, parameter: VariedParameter, value: float, tag: str
) -> ResearchVariant:
    """A variant of the published ``base`` with ``parameter`` set to ``value`` and nothing else."""
    require_published(base)
    universe = _universe_copy(
        base.universe, min_median_traded_value=float(value) if parameter == LIQUIDITY else None
    )
    if parameter == MIN_CONSTITUENTS and value != int(value):
        raise InvalidVariant("min_constituents is a whole number")
    coverage = _coverage_copy(
        base.coverage, min_constituents=int(value) if parameter == MIN_CONSTITUENTS else None
    )
    variant = ResearchVariant(
        method_version=research_version(base, tag),
        variant_of=base.method_version,
        lookback_days=base.lookback_days,
        holding_days=base.holding_days,
        universe=universe,
        coverage=coverage,
        gate=base.gate,
        open_limit_up_factor=base.open_limit_up_factor,
        single_stock_dominance_share=base.single_stock_dominance_share,
    )
    check_variant(base, variant)
    return variant


#: The published definition the variants are derived from.
SENSITIVITY_BASE: Final = SECTOR_MOMENTUM_V1

#: Methodology §11.1: two independent axes, two values each, no cross combinations.
#: Amending this table needs a methodology §11.1 change reviewed by qa first.
SENSITIVITY_VARIANTS: Final[tuple[ResearchVariant, ...]] = (
    derive_variant(SENSITIVITY_BASE, LIQUIDITY, 5_000_000.0, "liq5m"),
    derive_variant(SENSITIVITY_BASE, LIQUIDITY, 20_000_000.0, "liq20m"),
    derive_variant(SENSITIVITY_BASE, MIN_CONSTITUENTS, 3, "minc3"),
    derive_variant(SENSITIVITY_BASE, MIN_CONSTITUENTS, 8, "minc8"),
)


# ---------------------------------------------------------------------------
# Running and storing: the base and every variant, always together
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SensitivityEntry:
    """One definition's study inside a sensitivity run (the base included)."""

    method_version: str
    #: The base's ``method_version`` (the base names itself).
    variant_of: str
    #: Empty for the base.
    variant_diff: Mapping[str, Mapping[str, object]]
    study: BiasedStudyReport


@dataclass(frozen=True)
class SensitivityReport:
    """The base and all :data:`SENSITIVITY_VARIANTS`, labelled. Never an input to any gate."""

    sensitivity_id: str
    bias_label: str
    bias_directions: Mapping[str, str]
    base_version: str
    d0: date | None
    data_end: date
    entries: tuple[SensitivityEntry, ...]

    def entry(self, method_version: str) -> SensitivityEntry:
        for item in self.entries:
            if item.method_version == method_version:
                return item
        raise KeyError(method_version)


def expected_versions() -> tuple[str, ...]:
    """The base first, then every variant, in table order."""
    return (
        SENSITIVITY_BASE.method_version,
        *(variant.method_version for variant in SENSITIVITY_VARIANTS),
    )


def _diff_for_output(diff: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, object]]:
    return {name: dict(values) for name, values in diff.items()}


def run_sensitivity(
    panel: MarketPanel,
    *,
    market_db: MarketPanelReader,
    cost_model: CostModel,
    start: date,
    seed: int,
    calendar: Sequence[date] | None = None,
    train_sessions: int = TRAIN_SESSIONS,
    test_sessions: int = TEST_SESSIONS,
) -> SensitivityReport:
    """The biased study for :data:`SENSITIVITY_BASE` and every variant, on one admitted panel.

    There is no way to run a subset: the variant table is not a parameter.
    The panel is admitted once (C-49) before anything runs; each variant is
    re-checked against the base (C-48) before it runs.
    """
    base = require_published(SENSITIVITY_BASE)
    scope = admit_biased_panel(panel, market_db)
    for variant in SENSITIVITY_VARIANTS:
        check_variant(base, variant)
    definitions: tuple[SectorEvalDefinition, ...] = (base, *SENSITIVITY_VARIANTS)
    entries: list[SensitivityEntry] = []
    for definition in definitions:
        study = study_on_hindsight(
            panel,
            definition,
            scope=scope,
            cost_model=cost_model,
            start=start,
            seed=seed,
            calendar=calendar,
            train_sessions=train_sessions,
            test_sessions=test_sessions,
        )
        diff = variant_diff(base, definition)  # {} for the base; one key for a variant
        entries.append(
            SensitivityEntry(
                method_version=definition.method_version,
                variant_of=base.method_version,
                variant_diff=MappingProxyType(diff),
                study=study,
            )
        )
    return SensitivityReport(
        sensitivity_id=f"sens-{uuid.uuid4().hex[:12]}",
        bias_label=BIAS_LABEL,
        bias_directions=BIAS_DIRECTIONS,
        base_version=base.method_version,
        d0=scope.d0,
        data_end=scope.data_end,
        entries=tuple(entries),
    )


def save_sensitivity(report: SensitivityReport, store: ResearchStore) -> str:
    """Write every segment of every entry to the research DB, in one transaction.

    Refuses a partial report (the base and all variants, exactly once each),
    anything unlabelled or not hindsight / ``backfill_non_pit``, and data that
    does not end before D0 -- nothing is written then.
    """
    versions = tuple(entry.method_version for entry in report.entries)
    if versions != expected_versions():
        raise InvalidVariant(
            f"a sensitivity run stores the base and every variant, in order; got {versions}"
        )
    if report.bias_label != BIAS_LABEL:
        raise ValueError("research rows must carry the bias label")
    require_before_d0(report.d0, report.data_end)
    created = datetime.now(UTC)
    rows: list[SensitivityRow] = []
    for entry in report.entries:
        study = entry.study
        if study.regime != "hindsight" or study.data_regime != DATA_REGIME:
            raise BiasedScopeViolation("research rows come from hindsight backfill data only")
        if study.bias_label != BIAS_LABEL or entry.variant_of != report.base_version:
            raise ValueError("every entry is labelled and derived from the report's base")
        require_before_d0(study.d0, study.data_end)
        diff = _diff_for_output(entry.variant_diff)
        for item in study.segments:
            rows.append(
                SensitivityRow(
                    sensitivity_id=report.sensitivity_id,
                    method_version=entry.method_version,
                    variant_of=entry.variant_of,
                    variant_diff=json.dumps(diff, sort_keys=True),
                    segment=item.segment,
                    created_at=created,
                    sample_start=item.sample_start,
                    sample_end=item.sample_end,
                    sample_count=item.summary.sample_count,
                    beat_count_net=item.summary.beat_count_net,
                    beat_count_gross=item.summary.beat_count_gross,
                    base_rate_net=item.summary.q_net,
                    base_rate_gross=item.summary.q_gross,
                    report={
                        "segment": jsonable(item),
                        "folds": jsonable(study.folds),
                        "seeds": jsonable(study.statistics.seeds),
                        "delta_real": study.statistics.delta_real,
                        "delta_shuffle": study.statistics.delta_shuffle,
                        "variant_of": entry.variant_of,
                        "variant_diff": diff,
                    },
                )
            )
    store.save_sensitivity_rows(rows)
    return report.sensitivity_id
