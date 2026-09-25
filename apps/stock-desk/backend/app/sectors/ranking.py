"""Sector ranking on a single variable, S_A = R_g(t,L) - R_EW(t,L) (ADR-0012 D-6, R-B).

One variable, nothing else: no blend, no turnover, no breadth. Ties are broken
by sector code ascending (methodology §3.1), so ranks are always ``1..n`` with
no shared places. ``turnover_value_ratio_5_20`` is descriptive only and is
deliberately not a parameter here (C-26, T-12).

Everything is derived from one :class:`~app.sectors.universe.CalculationSet`:
the sector return, 「上漲 k／n 家」 and the listed constituents all use its
``C_g(t,L)`` (C-32), and the benchmark uses its ``C_M(t,L)``.

Constituent invariant (C-35): a ranked sector has at least
``min_constituents`` members, so it always lists three. If the list ever comes
back shorter -- only a bug can do that -- the sector is moved to the excluded
list as ``low_coverage`` with an internal ``constituent_invariant_violated``
note (never output by the API), and the ranking carries the violation so the
gate reports NE-6 for the day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

from app.sectors import constituents, coverage, index
from app.sectors.constituents import Constituent
from app.sectors.coverage import CoverageAssessment
from app.sectors.definition import SectorMomentumDefinition
from app.sectors.models import Coverage, ReasonCode
from app.sectors.universe import CalculationSet

#: The internal note written when C-35 is broken (not an API reason code).
CONSTITUENT_INVARIANT_VIOLATED: Final = "constituent_invariant_violated"
#: How many constituents a ranked sector lists.
LISTED_CONSTITUENTS: Final = 3


@dataclass(frozen=True)
class RankedSector:
    rank: int
    sector_code: str
    sector_name: str
    sector_return: float
    benchmark_return: float
    rel_return: float
    up_count: int
    constituent_count: int
    #: C_g(t,L) itself, kept so the same-set rule can be audited (T-9).
    members: frozenset[str]
    coverage: Coverage
    top_contributor_share: float | None
    single_stock_dominated: bool
    constituents: tuple[Constituent, ...]


@dataclass(frozen=True)
class ExcludedSectorRow:
    sector_code: str
    sector_name: str
    reason_code: ReasonCode
    computable_count: int
    expected_count: int
    coverage: Coverage
    #: Internal only (C-35); never part of the API payload.
    internal_reason: str | None = None


@dataclass(frozen=True)
class SectorRanking:
    decision_date: date
    method_version: str
    lookback_days: int
    #: R_EW(t,L) over C_M(t,L); None when nothing is computable.
    benchmark_return: float | None
    ranked: tuple[RankedSector, ...]
    excluded: tuple[ExcludedSectorRow, ...]
    assessment: CoverageAssessment
    #: Sector codes whose constituent list broke C-35 (drives NE-6).
    invariant_violations: tuple[str, ...]

    @property
    def excluded_reason_codes(self) -> tuple[ReasonCode, ...]:
        return tuple(row.reason_code for row in self.excluded)


def rank_sectors(calc: CalculationSet, definition: SectorMomentumDefinition) -> SectorRanking:
    """Rank the rankable sectors of ``calc`` by S_A and list the rest as excluded."""
    if calc.method_version != definition.method_version:
        raise ValueError("calculation set and definition disagree on method_version")
    assessment = coverage.assess(calc, definition)
    returns = calc.member_returns
    benchmark = index.mean_return(returns, calc.market.members)

    candidates: list[tuple[float, str, float, float]] = []
    excluded: list[ExcludedSectorRow] = []
    violations: list[str] = []
    listed: dict[str, tuple[Constituent, ...]] = {}
    for sector, verdict in zip(calc.sectors, assessment.sectors, strict=True):
        if verdict.reason_code is not None:
            excluded.append(
                ExcludedSectorRow(
                    sector_code=sector.sector_code,
                    sector_name=sector.sector_name,
                    reason_code=verdict.reason_code,
                    computable_count=verdict.computable_count,
                    expected_count=verdict.expected_count,
                    coverage=verdict.coverage,
                )
            )
            continue
        picked = constituents.list_constituents(calc, sector.sector_code)
        if len(picked) < LISTED_CONSTITUENTS:
            violations.append(sector.sector_code)
            excluded.append(
                ExcludedSectorRow(
                    sector_code=sector.sector_code,
                    sector_name=sector.sector_name,
                    reason_code="low_coverage",
                    computable_count=verdict.computable_count,
                    expected_count=verdict.expected_count,
                    coverage=verdict.coverage,
                    internal_reason=CONSTITUENT_INVARIANT_VIOLATED,
                )
            )
            continue
        sector_return = index.mean_return(returns, sector.members)
        if sector_return is None or benchmark is None:
            raise RuntimeError("a rankable sector must have a computable return")
        listed[sector.sector_code] = picked
        candidates.append((sector_return - benchmark, sector.sector_code, sector_return, benchmark))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    by_code = {sector.sector_code: sector for sector in calc.sectors}
    verdicts = {verdict.sector_code: verdict for verdict in assessment.sectors}
    ranked: list[RankedSector] = []
    for rank, (rel, code, sector_return, sector_benchmark) in enumerate(candidates, start=1):
        sector = by_code[code]
        share = index.top_contributor_share(returns, sector.members)
        ranked.append(
            RankedSector(
                rank=rank,
                sector_code=code,
                sector_name=sector.sector_name,
                sector_return=sector_return,
                benchmark_return=sector_benchmark,
                rel_return=rel,
                up_count=index.up_count(returns, sector.members),
                constituent_count=len(sector.members),
                members=sector.members,
                coverage=verdicts[code].coverage,
                top_contributor_share=share,
                single_stock_dominated=(
                    share is not None and share > definition.single_stock_dominance_share
                ),
                constituents=listed[code],
            )
        )
    excluded.sort(key=lambda row: row.sector_code)
    return SectorRanking(
        decision_date=calc.decision_date,
        method_version=calc.method_version,
        lookback_days=calc.lookback_days,
        benchmark_return=benchmark,
        ranked=tuple(ranked),
        excluded=tuple(excluded),
        assessment=assessment,
        invariant_violations=tuple(violations),
    )
