"""E_g(t) and C_g(t,L): who is expected, and who is actually computed (ADR-0012 D-4).

``E_g(t)`` (expected members): names in the point-in-time listing snapshot,
classified into sector ``g`` by the point-in-time classification snapshot, of
an eligible security type, listed long enough and liquid enough.

``C_g(t,L)`` (calculation set): ``E_g(t)`` minus three exclusion categories,
each name attributed to the **first** that applies (risk §9):

1. missing -- no valid close on some session of ``t-L .. t``;
2. ex-date -- a visible ``TWT48U_ALL`` announcement puts an ex-date inside
   ``(t-L, t]`` (methodology §2.4 option 2);
3. corporate action -- a close-to-close move inside the window beyond the daily
   price limit plus tolerance.

so ``|E| - ① - ② - ③ == |C|`` at sector and market level alike.

:func:`calculation_set` is the **only** producer of ``C_g(t,L)`` (C-32). The
sector return, 「上漲 k／n 家」 and the constituent list are all derived from its
return value -- never recomputed from the panel -- and B_EW uses the market
level ``C_M(t,L)`` of the same object.

No suspension-list source exists (DE), so a suspended name stays in ``E`` and
counts as missing; ``suspended_count`` is therefore always ``None`` here.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

from app.data.panel import PointInTimePanel, Regime, Snapshot
from app.sectors import index
from app.sectors.definition import SectorCoreDefinition


@dataclass(frozen=True)
class SnapshotRef:
    """Which listing / classification run the universe was read from."""

    run_id: str
    session_date: date
    carried_sessions: int


@dataclass(frozen=True)
class EligibleSector:
    sector_code: str
    sector_name: str
    #: Code 20: counted in B_EW, never ranked.
    unranked: bool
    members: frozenset[str]


@dataclass(frozen=True)
class EligibleUniverse:
    decision_date: date
    regime: Regime
    #: Every sector present in the classification snapshot among listed,
    #: eligible-type names (code 91 removed), sorted by code; may have no members.
    sectors: tuple[EligibleSector, ...]
    #: E_M(t): union of every sector's members, code 20 included.
    market: frozenset[str]
    listing: SnapshotRef | None
    classification: SnapshotRef | None


@dataclass(frozen=True)
class ExclusionSplit:
    """One population split into the three categories and the calculation set."""

    expected: frozenset[str]
    missing: frozenset[str]
    ex_date_excluded: frozenset[str]
    corporate_action_excluded: frozenset[str]
    members: frozenset[str]


@dataclass(frozen=True)
class SectorSet:
    sector_code: str
    sector_name: str
    unranked: bool
    split: ExclusionSplit

    @property
    def members(self) -> frozenset[str]:
        """C_g(t,L)."""
        return self.split.members

    @property
    def expected(self) -> frozenset[str]:
        """E_g(t)."""
        return self.split.expected


@dataclass(frozen=True)
class CalculationSet:
    """The single source of C_g(t,L) and C_M(t,L) for one decision date (C-32)."""

    decision_date: date
    regime: Regime
    method_version: str
    lookback_days: int
    #: ``t-L .. t``; empty when the panel does not reach back L sessions.
    window: tuple[date, ...]
    sectors: tuple[SectorSet, ...]
    market: ExclusionSplit
    #: ``R_i(t,L)`` for every name in ``C_M(t,L)`` and only those.
    member_returns: Mapping[str, float]
    listing: SnapshotRef | None
    classification: SnapshotRef | None

    def sector(self, sector_code: str) -> SectorSet:
        for sector in self.sectors:
            if sector.sector_code == sector_code:
                return sector
        raise KeyError(sector_code)


def _ref(snapshot: Snapshot | None) -> SnapshotRef | None:
    if snapshot is None:
        return None
    return SnapshotRef(
        run_id=snapshot.run_id,
        session_date=snapshot.session_date,
        carried_sessions=snapshot.carried_sessions,
    )


def _liquid(
    panel: PointInTimePanel, symbols: set[str], definition: SectorCoreDefinition
) -> set[str]:
    """Median traded value and traded-day count over the 20 sessions ending at t.

    A session without a bar counts as NT$0 traded and as a day without trades.
    """
    rules = definition.universe
    window = index.trailing_window(panel, rules.liquidity_window_sessions - 1)
    if window is None or not symbols:
        return set()
    ordered = sorted(symbols)
    traded_value = panel.field_matrix("traded_value", window, ordered)
    shares = panel.field_matrix("shares", window, ordered)
    medians = traded_value.fillna(0.0).median(axis=0)
    traded_days = ((shares.fillna(0.0) > 0) & traded_value.notna()).sum(axis=0)
    ok = (medians >= rules.min_median_traded_value) & (traded_days >= rules.min_traded_sessions)
    return {str(symbol) for symbol in ok.index[ok.to_numpy()]}


def _seasoned(
    panel: PointInTimePanel, symbols: set[str], definition: SectorCoreDefinition
) -> set[str]:
    """Listed for at least ``min_listing_sessions`` visible sessions up to t.

    The listing snapshot carries no listing date, so age is counted from the
    first visible bar: warm-up history (>= 80 sessions before D0, D-3) makes an
    old listing pass, and a new one waits its 60 sessions.
    """
    t = panel.decision_date
    firsts = panel.first_bar_sessions()
    sessions = [session for session in panel.sessions if session <= t]
    seasoned: set[str] = set()
    for symbol in symbols:
        first = firsts.get(symbol)
        if first is None:
            continue
        age = len(sessions) - bisect_left(sessions, first)
        if age >= definition.universe.min_listing_sessions:
            seasoned.add(symbol)
    return seasoned


def eligible(panel: PointInTimePanel, definition: SectorCoreDefinition) -> EligibleUniverse:
    """E_g(t) for every sector and E_M(t) (methodology §2.2-§2.3)."""
    panel = index.require_pit_view(panel)
    rules = definition.universe
    listing = panel.snapshot("listing")
    classification = panel.snapshot("classification")
    if listing is None or classification is None:
        return EligibleUniverse(
            decision_date=panel.decision_date,
            regime=panel.regime,
            sectors=(),
            market=frozenset(),
            listing=_ref(listing),
            classification=_ref(classification),
        )

    listed = {
        str(row.symbol)
        for row in listing.rows.itertuples(index=False)
        if str(row.security_type) in rules.eligible_security_types
    }
    # One classification per name; a duplicated row in one snapshot resolves to
    # the lowest code so the answer is deterministic.
    classified: dict[str, tuple[str, str]] = {}
    for row in classification.rows.sort_values(["symbol", "sector_code"]).itertuples(index=False):
        classified.setdefault(str(row.symbol), (str(row.sector_code), str(row.sector_name)))

    candidates = {
        symbol
        for symbol in listed
        if symbol in classified and classified[symbol][0] not in rules.excluded_sector_codes
    }
    qualified = _seasoned(panel, candidates, definition) & _liquid(panel, candidates, definition)

    names: dict[str, str] = {}
    by_sector: dict[str, set[str]] = {}
    for symbol in sorted(candidates):
        code, name = classified[symbol]
        names.setdefault(code, name)
        by_sector.setdefault(code, set())
        if symbol in qualified:
            by_sector[code].add(symbol)

    sectors = tuple(
        EligibleSector(
            sector_code=code,
            sector_name=names[code],
            unranked=code in rules.unranked_sector_codes,
            members=frozenset(by_sector[code]),
        )
        for code in sorted(by_sector)
    )
    return EligibleUniverse(
        decision_date=panel.decision_date,
        regime=panel.regime,
        sectors=sectors,
        market=frozenset(qualified),
        listing=_ref(listing),
        classification=_ref(classification),
    )


def _split(
    expected: frozenset[str],
    missing: frozenset[str],
    ex_date: frozenset[str],
    corporate_action: frozenset[str],
) -> ExclusionSplit:
    """Attribute each name once, in the fixed order ① -> ② -> ③ (risk §9)."""
    first = expected & missing
    second = (expected & ex_date) - first
    third = (expected & corporate_action) - first - second
    return ExclusionSplit(
        expected=expected,
        missing=first,
        ex_date_excluded=second,
        corporate_action_excluded=third,
        members=expected - first - second - third,
    )


def calculation_set(panel: PointInTimePanel, definition: SectorCoreDefinition) -> CalculationSet:
    """The one producer of C_g(t,L) and C_M(t,L) (ADR-0012 D-4, C-32)."""
    panel = index.require_pit_view(panel)
    universe = eligible(panel, definition)
    t = panel.decision_date
    market = universe.market
    window = index.lookback_window(panel, definition.lookback_days)

    if window is None:
        missing = market
        ex_date: frozenset[str] = frozenset()
        corporate_action: frozenset[str] = frozenset()
    else:
        closes = index.window_closes(panel, market, window)
        missing = market - index.complete_symbols(closes)
        announcements = panel.ex_dividend_announcements()
        in_window = announcements.loc[
            (announcements["ex_date"] > window[0]) & (announcements["ex_date"] <= t)
        ]
        ex_date = frozenset(str(symbol) for symbol in in_window["symbol"]) & market
        limit = (
            definition.universe.daily_price_limit + definition.universe.daily_price_limit_tolerance
        )
        complete = sorted(market - missing)
        corporate_action = (
            index.daily_limit_breaches(closes[complete], limit) if complete else frozenset()
        )

    market_split = _split(market, missing, ex_date, corporate_action)
    returns = index.member_returns(panel, market_split.members, definition.lookback_days)
    if set(returns) != set(market_split.members):
        raise RuntimeError("every name in C_M(t,L) must carry a lookback return")

    sectors = tuple(
        SectorSet(
            sector_code=sector.sector_code,
            sector_name=sector.sector_name,
            unranked=sector.unranked,
            split=_split(sector.members, missing, ex_date, corporate_action),
        )
        for sector in universe.sectors
    )
    return CalculationSet(
        decision_date=t,
        regime=panel.regime,
        method_version=definition.method_version,
        lookback_days=definition.lookback_days,
        window=window or (),
        sectors=sectors,
        market=market_split,
        member_returns=MappingProxyType(returns),
        listing=universe.listing,
        classification=universe.classification,
    )
