"""Equal-weight sector basket series (ADR-0027 D-1 ``basket.py``; pre-registration §2.1).

Two pure functions. Members are passed in by the caller -- this module imports
nothing from ``app.sectors`` and decides no membership (S_T for the outlook,
S_{T-h} for B1 and B4 are the caller's choice):

* :func:`basket_log_returns` -- the daily basket log returns that sigma_d reads:
  ``r_t = ln((1 / N_t) * sum_{i in V_t} P*_i,t / P*_i,t-1)``, the *ratio*
  average (never the average of price levels). ``V_t`` holds the members with a
  bar on both t and t-1 that are not excluded; a day whose valid weight
  ``N_t / |S_T|`` is below ``definition.BASKET_MIN_MEMBER_WEIGHT`` (90%) is
  invalid (``r_t`` is ``None``), the denominator being the full member set
  ``|S_T|``. Members whose dividend coverage over the window is unknown
  (``coverage_unknown``, judged by the caller; must be a subset of ``members``)
  are excluded from every day. When the retained weight
  ``(|S_T| - excluded) / |S_T|`` is below ``BASKET_MIN_MEMBER_WEIGHT`` -- the
  exact form of "excluded weight above 10%", compared with the constant itself
  and never with one minus it, so 1 of 10 excluded does not trigger (risk R-2)
  -- the result carries ``E-ADJ-COVERAGE`` (fail-closed).
* :func:`basket_hold_ratio` -- the buy-and-hold basket of the B1 numerator:
  the equal-weight average of ``P*_i,end / P*_i,start`` over the members with a
  bar on both days.

``series`` maps each member to its adjusted closes (P* anchored by the caller)
keyed by session date, holding only bars that passed the quality checks; a
missing date is a missing bar. A non-finite or non-positive price is a program
defect and raises ``ValueError``.

The 90% / 10% thresholds come only from ``definition.BASKET_MIN_MEMBER_WEIGHT``
(B2D-3): the registered dirdef object of the record's ``definition_version``,
a keyword without default like ``coverage_unknown``. Its value carries the
``SectorMomentumDefinition`` v1 coverage threshold, but as a dirdef constant it
lies inside ``definition_logic_sha256`` and stays fixed with the
``definition_version``; this module never reads ``app.sectors``. Imports: the
standard library and the ``app.dirdef`` definition type only.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from typing import Final, Literal

from app.dirdef.definition import DirectionDefinition

BasketMissingCode = Literal["E-ADJ-COVERAGE"]

E_ADJ_COVERAGE: Final[BasketMissingCode] = "E-ADJ-COVERAGE"


@dataclass(frozen=True)
class BasketLogReturns:
    """The basket daily series over a window, one entry per return day."""

    #: Return days: the window sessions after the first.
    dates: tuple[date, ...]
    r_t: tuple[float | None, ...]
    V_t: tuple[tuple[str, ...], ...]
    N_t: tuple[int, ...]
    invalid_days: tuple[date, ...]
    #: Members excluded for unknown dividend coverage, sorted.
    excluded_members: tuple[str, ...]
    missing_code: BasketMissingCode | None


@dataclass(frozen=True)
class BasketHoldRatio:
    """The equal-weight buy-and-hold ratio from ``start`` to ``end``."""

    #: ``None`` when no member has a bar on both days.
    ratio: float | None
    members_used: tuple[str, ...]
    members_missing: tuple[str, ...]


def _member_tuple(members: Collection[str]) -> tuple[str, ...]:
    ordered = tuple(sorted(members))
    if not ordered:
        raise ValueError("members must not be empty")
    if len(set(ordered)) != len(ordered):
        raise ValueError("members must not repeat")
    return ordered


def _price(series: Mapping[str, Mapping[date, float]], member: str, day: date) -> float | None:
    price = series.get(member, {}).get(day)
    if price is None:
        return None
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        raise TypeError(f"prices must be numbers, got {type(price).__name__}")
    if not (math.isfinite(price) and price > 0):
        raise ValueError("prices must be positive finite numbers")
    return float(price)


def _weight_below(count: int, total: int, threshold: float) -> bool:
    """``count / total < threshold``, compared as doubles (``9 / 10`` equals ``0.9``)."""
    return count / total < threshold


def basket_log_returns(
    members: Collection[str],
    series: Mapping[str, Mapping[date, float]],
    window: Sequence[date],
    *,
    coverage_unknown: Collection[str],
    definition: DirectionDefinition,
) -> BasketLogReturns:
    """The basket daily log returns over ``window`` (consecutive sessions, oldest first)."""
    ordered = _member_tuple(members)
    min_member_weight = definition.BASKET_MIN_MEMBER_WEIGHT
    if len(window) < 2:
        raise ValueError("window needs at least two sessions")
    if any(earlier >= later for earlier, later in pairwise(window)):
        raise ValueError("window sessions must be strictly increasing")
    unknown = set(coverage_unknown)
    if not unknown <= set(ordered):
        raise ValueError("coverage_unknown names a non-member")
    excluded = tuple(member for member in ordered if member in unknown)
    eligible = tuple(member for member in ordered if member not in unknown)
    total = len(ordered)

    returns: list[float | None] = []
    valid_sets: list[tuple[str, ...]] = []
    counts: list[int] = []
    invalid: list[date] = []
    for previous, current in pairwise(window):
        ratios: list[float] = []
        valid: list[str] = []
        for member in eligible:
            before = _price(series, member, previous)
            after = _price(series, member, current)
            if before is None or after is None:
                continue
            ratios.append(after / before)
            valid.append(member)
        valid_sets.append(tuple(valid))
        counts.append(len(valid))
        if _weight_below(len(valid), total, min_member_weight):
            returns.append(None)
            invalid.append(current)
        else:
            returns.append(math.log(math.fsum(ratios) / len(ratios)))

    missing: BasketMissingCode | None = None
    # Retained weight against the constant itself, never ``1 - constant`` (risk R-2).
    if _weight_below(total - len(excluded), total, min_member_weight):
        missing = E_ADJ_COVERAGE
    return BasketLogReturns(
        dates=tuple(window[1:]),
        r_t=tuple(returns),
        V_t=tuple(valid_sets),
        N_t=tuple(counts),
        invalid_days=tuple(invalid),
        excluded_members=excluded,
        missing_code=missing,
    )


def basket_hold_ratio(
    members: Collection[str],
    series: Mapping[str, Mapping[date, float]],
    start: date,
    end: date,
) -> BasketHoldRatio:
    """The equal-weight buy-and-hold ratio of ``members`` from ``start`` to ``end``."""
    ordered = _member_tuple(members)
    if not start < end:
        raise ValueError("start must be before end")
    ratios: list[float] = []
    used: list[str] = []
    missing: list[str] = []
    for member in ordered:
        before = _price(series, member, start)
        after = _price(series, member, end)
        if before is None or after is None:
            missing.append(member)
            continue
        ratios.append(after / before)
        used.append(member)
    ratio = math.fsum(ratios) / len(ratios) if ratios else None
    return BasketHoldRatio(ratio=ratio, members_used=tuple(used), members_missing=tuple(missing))
