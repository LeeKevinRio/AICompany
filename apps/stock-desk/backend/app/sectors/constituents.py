"""Which constituents a ranked sector lists (ADR-0012 D-7, F1; risk §4.1 a-f).

The candidates are exactly ``C_g(t,L)`` from
:func:`app.sectors.universe.calculation_set` (C-32), ordered by the same
already-realised variable the sectors are ranked by -- the member's own
lookback return -- with ties broken by symbol: key ``(-return_L, symbol)``.
Positions ``[0, 1, -1]`` are listed: the two largest and the smallest move,
which shows the dispersion inside the sector (risk §4.1-f).

Nothing here evaluates a stock. No second variable, no rule-engine output,
no historical figure (C-17).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.sectors.universe import CalculationSet

#: Positions taken from the ordered calculation set: top 2, then bottom 1.
LISTED_POSITIONS: Final[tuple[int, ...]] = (0, 1, -1)


@dataclass(frozen=True)
class Constituent:
    symbol: str
    return_L: float  # noqa: N815 -- mirrors the D-10 field name


def ordered_members(calc: CalculationSet, sector_code: str) -> tuple[Constituent, ...]:
    """Every member of ``C_g(t,L)`` ordered by ``(-return_L, symbol)``."""
    members = calc.sector(sector_code).members
    returns = calc.member_returns
    ordered = sorted(members, key=lambda symbol: (-returns[symbol], symbol))
    return tuple(Constituent(symbol=symbol, return_L=returns[symbol]) for symbol in ordered)


def list_constituents(calc: CalculationSet, sector_code: str) -> tuple[Constituent, ...]:
    """Positions ``[0, 1, -1]`` of :func:`ordered_members`, each name at most once.

    With fewer than three members the positions collide and fewer names come
    back; a ranked sector always has at least ``min_constituents`` (>= 5), so a
    short list is a bug and :func:`app.sectors.ranking.rank_sectors` moves the
    sector out of the ranking (C-35).
    """
    ordered = ordered_members(calc, sector_code)
    if not ordered:
        return ()
    picked: list[Constituent] = []
    seen: set[str] = set()
    for position in LISTED_POSITIONS:
        index = position if position >= 0 else len(ordered) + position
        if 0 <= index < len(ordered) and ordered[index].symbol not in seen:
            picked.append(ordered[index])
            seen.add(ordered[index].symbol)
    return tuple(picked)
