"""Sector coverage, exclusion attribution and card-level completeness (ADR-0012 D-7, D-8).

Three distinct ratios live here and must never be confused (C-44):

* sector coverage ``|C_g| / |E_g|`` against ``sector_coverage_threshold``
  (all three exclusion categories count);
* card completeness ``(|E_M| - missing) / |E_M|`` against
  ``overall_coverage_threshold`` (category ① only, risk §8-1);
* card computable ratio ``|C_M| / |E_M|`` against ``computable_ratio_min``
  (all three categories, risk §8 C1-1).

Threshold comparisons are exact rational arithmetic on the counts, so a ratio
sitting exactly on a threshold is never pushed across it by float rounding
(T-23 boundary). Display percentages are floored to one decimal
(``floor(ratio * 1000) / 10``, risk §9): 79.99% is shown as 79.9, never 80.0.

Nothing in this module reads configuration or the environment (C-24): every
threshold comes from the :class:`SectorMomentumDefinition` passed in.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from app.data.panel import PointInTimePanel
from app.sectors import index
from app.sectors.definition import CoverageRules, SectorMomentumDefinition
from app.sectors.models import Coverage, ExcludedReasonCounts, ReasonCode
from app.sectors.universe import CalculationSet, ExclusionSplit

#: Attribution order for an excluded sector (risk §8-2, C-39). First match wins.
REASON_CODE_ORDER: Final[tuple[ReasonCode, ...]] = (
    "unranked_category",
    "too_few_members",
    "low_coverage",
    "ex_dividend_exclusion",
)


def _exact(value: float) -> Fraction:
    """The decimal a threshold or ratio was written as (``0.9`` -> 9/10)."""
    return Fraction(repr(value))


def ratio_at_least(numerator: int, denominator: int, threshold: float) -> bool:
    """``numerator / denominator >= threshold`` in exact arithmetic."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    return Fraction(numerator, denominator) >= _exact(threshold)


def floor_pct_display(ratio: float | Fraction) -> float:
    """Percent with one decimal, always rounded **down** (risk §9, C-37).

    A float is read as the decimal it prints as, so float noise cannot move the
    floor (0.29 is 29.0, not 28.9); an exact :class:`Fraction` is used as is.
    """
    exact = ratio if isinstance(ratio, Fraction) else _exact(ratio)
    return math.floor(exact * 1000) / 10


def coverage_from_counts(
    *, expected: int, missing: int, ex_date: int, corporate_action: int
) -> Coverage:
    """The D-10 ``Coverage`` block from the four counts (the one formula)."""
    calculation = expected - missing - ex_date - corporate_action
    return Coverage(
        expected_count=expected,
        calculation_count=calculation,
        missing_count=missing,
        ex_date_excluded_count=ex_date,
        corporate_action_excluded_count=corporate_action,
        # No suspension-list source: suspended names are counted as missing.
        suspended_count=None,
        coverage_ratio=calculation / expected if expected else None,
        completeness_ratio=(expected - missing) / expected if expected else None,
    )


def coverage_of(split: ExclusionSplit) -> Coverage:
    """The D-10 ``Coverage`` block for one population (sector or whole market)."""
    return coverage_from_counts(
        expected=len(split.expected),
        missing=len(split.missing),
        ex_date=len(split.ex_date_excluded),
        corporate_action=len(split.corporate_action_excluded),
    )


def _meets(count: int, expected: int, rules: CoverageRules) -> bool:
    return count >= rules.min_constituents and ratio_at_least(
        count, expected, rules.sector_coverage_threshold
    )


def attribute(split: ExclusionSplit, *, unranked: bool, rules: CoverageRules) -> ReasonCode | None:
    """Why a sector is not ranked, or ``None`` when it is rankable (C-39).

    The order is fixed and exactly one code is returned: ``too_few_members``
    is structural (|E| below the minimum); ``low_coverage`` already fails on
    missing data alone; ``ex_dividend_exclusion`` passes on missing data alone
    and fails only once ex-date and corporate-action exclusions are taken out.
    """
    if unranked:
        return "unranked_category"
    expected = len(split.expected)
    if expected < rules.min_constituents:
        return "too_few_members"
    if not _meets(expected - len(split.missing), expected, rules):
        return "low_coverage"
    if not _meets(len(split.members), expected, rules):
        return "ex_dividend_exclusion"
    return None


@dataclass(frozen=True)
class SectorAssessment:
    sector_code: str
    sector_name: str
    coverage: Coverage
    reason_code: ReasonCode | None
    #: c = |C_g(t,L)|
    computable_count: int
    #: e = |E_g(t)|
    expected_count: int


@dataclass(frozen=True)
class CardAssessment:
    """Whole-market counts and ratios for the card (C-37, C-38)."""

    coverage: Coverage
    completeness_ratio: float | None
    computable_ratio: float | None
    completeness_pct_display: float | None
    computable_ratio_pct_display: float | None
    market_expected_count: int
    market_missing_count: int
    market_ex_date_excluded_count: int
    market_corporate_action_excluded_count: int
    market_ex_date_excluded_ratio: float | None
    #: completeness below ``overall_coverage_threshold`` (insufficient reason ③).
    completeness_low: bool
    #: computable ratio below ``computable_ratio_min`` (insufficient reason ④).
    computable_low: bool
    #: ex-date share at or above ``ex_date_tag_ratio_min`` (one of the tag triggers).
    ex_date_ratio_reached: bool


@dataclass(frozen=True)
class CoverageAssessment:
    sectors: tuple[SectorAssessment, ...]
    card: CardAssessment


def card_from_counts(
    *, expected: int, missing: int, ex_date: int, corporate_action: int, rules: CoverageRules
) -> CardAssessment:
    """Card-level ratios, displays and threshold verdicts from the market counts."""
    computable = expected - missing - ex_date - corporate_action
    completeness: Fraction | None = None
    computable_share: Fraction | None = None
    completeness_low = computable_low = ex_date_reached = False
    if expected:
        completeness = Fraction(expected - missing, expected)
        computable_share = Fraction(computable, expected)
        completeness_low = not ratio_at_least(
            expected - missing, expected, rules.overall_coverage_threshold
        )
        computable_low = not ratio_at_least(computable, expected, rules.computable_ratio_min)
        ex_date_reached = ratio_at_least(ex_date, expected, rules.ex_date_tag_ratio_min)
    # |E_M| == 0 leaves the ratios undefined: neither ③ nor ④ can be asserted,
    # and with no expected member every sector is too_few_members, so the card
    # falls through to no_sector_computable (⑤).
    return CardAssessment(
        coverage=coverage_from_counts(
            expected=expected, missing=missing, ex_date=ex_date, corporate_action=corporate_action
        ),
        completeness_ratio=float(completeness) if completeness is not None else None,
        computable_ratio=float(computable_share) if computable_share is not None else None,
        completeness_pct_display=(
            floor_pct_display(completeness) if completeness is not None else None
        ),
        computable_ratio_pct_display=(
            floor_pct_display(computable_share) if computable_share is not None else None
        ),
        market_expected_count=expected,
        market_missing_count=missing,
        market_ex_date_excluded_count=ex_date,
        market_corporate_action_excluded_count=corporate_action,
        market_ex_date_excluded_ratio=ex_date / expected if expected else None,
        completeness_low=completeness_low,
        computable_low=computable_low,
        ex_date_ratio_reached=ex_date_reached,
    )


def assess_card(split: ExclusionSplit, rules: CoverageRules) -> CardAssessment:
    return card_from_counts(
        expected=len(split.expected),
        missing=len(split.missing),
        ex_date=len(split.ex_date_excluded),
        corporate_action=len(split.corporate_action_excluded),
        rules=rules,
    )


def assess(calc: CalculationSet, definition: SectorMomentumDefinition) -> CoverageAssessment:
    """Per-sector attribution plus the card-level ratios, all from one ``calc``."""
    rules = definition.coverage
    sectors = tuple(
        SectorAssessment(
            sector_code=sector.sector_code,
            sector_name=sector.sector_name,
            coverage=coverage_of(sector.split),
            reason_code=attribute(sector.split, unranked=sector.unranked, rules=rules),
            computable_count=len(sector.members),
            expected_count=len(sector.expected),
        )
        for sector in calc.sectors
    )
    return CoverageAssessment(sectors=sectors, card=assess_card(calc.market, rules))


def ex_dividend_feed_covered(panel: PointInTimePanel, definition: SectorMomentumDefinition) -> bool:
    """Whether ``TWT48U_ALL`` ok runs cover each of the last L sessions (C-18).

    Strict reading of D-4: every one of the L most recent sessions up to and
    including the decision date needs its own visible ``ok`` announcement run.
    A carried-forward announcement snapshot does not count as coverage here,
    because the exclusion window cannot be trusted on a day nobody looked.
    """
    t = index.require_pit_view(panel).decision_date
    recent = (*panel.sessions_before(t, definition.lookback_days - 1), t)
    if len(recent) < definition.lookback_days:
        return False
    covered = panel.ok_run_sessions("dividend_announce")
    return all(session in covered for session in recent)


def ex_date_tag(card: CardAssessment, excluded_reason_codes: Iterable[ReasonCode]) -> bool:
    """「除權息排除 {m} 檔」 tag: ratio at the threshold, or any ex-dividend exclusion (C-38)."""
    return card.ex_date_ratio_reached or any(
        code == "ex_dividend_exclusion" for code in excluded_reason_codes
    )


def excluded_reason_counts(excluded_reason_codes: Iterable[ReasonCode]) -> ExcludedReasonCounts:
    """{n1}/{n2}/{n3} of the no_sector_computable sentence (派工單 §10, C-44).

    ``unranked_category`` is not a rankable sector and is left out, so the three
    counts add up to the number of rankable sectors when none is ranked.
    """
    codes = list(excluded_reason_codes)
    return ExcludedReasonCounts(
        too_few_members=codes.count("too_few_members"),
        low_coverage=codes.count("low_coverage"),
        ex_dividend_exclusion=codes.count("ex_dividend_exclusion"),
    )


def published_thresholds(definition: SectorMomentumDefinition) -> dict[str, int | float]:
    """The five thresholds the API echoes, taken off the gate's own object (C-33)."""
    rules = definition.coverage
    return {
        "min_constituents": rules.min_constituents,
        "sector_coverage_threshold": rules.sector_coverage_threshold,
        "overall_coverage_threshold": rules.overall_coverage_threshold,
        "computable_ratio_min": rules.computable_ratio_min,
        "ex_date_tag_ratio_min": rules.ex_date_tag_ratio_min,
    }
