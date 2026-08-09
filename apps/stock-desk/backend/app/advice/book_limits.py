"""The same five caps as :mod:`app.advice.limits`, judged over the whole book.

The per-symbol card answers "is *this* holding inside the budget". The overview
asks a different question -- "is the book inside the budget" -- and three of the
five caps have no single book-level number to answer it with: a share of total
equity, an industry's share, and a stop-out loss are all per-holding
quantities. So this module does not invent a book-level formula for them. It
runs :func:`app.advice.limits.evaluate_limits` on every symbol in the book,
exactly as the card does, and reports **the worst verdict** with the symbol (or
industry) it came from. The other two caps -- gross exposure and Kelly -- are
already book-level questions and are read straight off a book-level context.

Three rules keep the aggregate as honest as the per-symbol verdict it is built
from:

1. **``not_evaluable`` is never read as ``passed``** (the engine's standing red
   line, :mod:`app.advice.limits`). A symbol whose cap could not be evaluated is
   *left out of the comparison* and listed in ``excluded`` with the cap's own
   verbatim reason -- never averaged in, never counted as a compliant holding.
2. **What was left out is stated with the verdict**, not only in a note beside
   it: the aggregate ``detail`` says how many symbols were excluded, and
   ``excluded`` carries each one with the reason the cap itself gave.
3. **A symbol with any unvalued lot is excluded from every per-symbol cap.**
   Its position value is short by the lots that could not be priced, and a short
   numerator makes a weight -- and a stop-out loss -- look smaller than it is.
   That is the one direction these caps must never err in (the same reasoning
   as :data:`app.advice.limits.GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL`), so the
   holding is withheld from the comparison rather than compared understated.

Like :mod:`app.advice.book`, this stays a pure function: the caller resolves
prices, ATR and FX rates and hands them in, so the whole aggregation is testable
without a network.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from app.advice.book import (
    SYMBOL_UNVALUED_NOTE,
    FxQuote,
    build_book_context,
    build_book_level_context,
)
from app.advice.limits import (
    LIMIT_IDS,
    LimitCheck,
    LimitStatus,
    PortfolioContext,
    RiskBudget,
    SelfReportedNetWorth,
    evaluate_limits,
)
from app.portfolio.summary import PortfolioSummary, SummaryPosition
from app.positions.models import Market

#: The caps whose observed value belongs to one holding, and which are therefore
#: aggregated by comparing every symbol in the book. The two absent ids
#: (``gross_exposure``, ``kelly_fraction``) already answer a book-level question
#: and are taken verbatim from the book-level context.
PER_SYMBOL_LIMIT_IDS: tuple[str, ...] = (
    "single_position_weight",
    "sector_weight",
    "per_trade_loss",
)

#: Prefix on the worst holding's own verdict, so the reader knows the sentence
#: that follows describes one symbol out of several rather than the book.
#: "觀測值最高" is the neutral way to say "closest to (or furthest past) the cap":
#: for all three per-symbol caps a higher observed value is nearer the ceiling.
WORST_SYMBOL_PREFIX = "逐檔評估帳本內 {count} 檔標的，觀測值最高者為 {symbol}："

#: The same for cap 2, which compares industries rather than holdings -- the
#: verdict that follows names the industry itself.
WORST_SECTOR_PREFIX = "逐項彙總帳本內 {count} 個產業，觀測值最高者為："

#: Rule 2: the aggregate says what it could not look at, next to the verdict.
EXCLUDED_SUFFIX = "另有 {count} 檔標的未納入本條上限的比較，各自的成因逐檔列出。"

#: Rule 3's ground, appended to the cap's own sentence about the same symbol.
UNVALUED_EXCLUSION_SUFFIX = "本條上限的逐檔比較未納入此標的。"

#: Nothing is held at all: there is no holding to compare, which is a different
#: statement from "the holdings could not be judged" below.
EMPTY_BOOK_DETAIL = "帳本內沒有任何持倉，{name}沒有可評估的部位，本次不計算，回報 not_evaluable。"

#: Holdings exist but not one of them could be judged against this cap. One
#: sentence per cap, so a gap in one is never described with another's cause;
#: the individual causes stay verbatim in ``excluded``.
NO_CANDIDATE_DETAILS: dict[str, str] = {
    "single_position_weight": (
        "帳本內沒有可估值的部位，單一標的佔比上限沒有可比較的標的，"
        "本次不計算，回報 not_evaluable；各標的的成因逐檔列出。"
    ),
    "sector_weight": (
        "帳本內沒有已估值且已填產業別的持倉，單一產業佔比上限本次不計算，"
        "回報 not_evaluable；各標的的成因逐檔列出。"
    ),
    "per_trade_loss": (
        "帳本內沒有可計算停損距離的標的，單筆最大可承受虧損上限本次不計算，"
        "回報 not_evaluable；各標的的成因逐檔列出。"
    ),
}

#: Worst-first ordering over statuses. ``not_evaluable`` never appears in a
#: comparison (rule 1), so it is not ranked here.
_STATUS_RANK: dict[LimitStatus, int] = {"violated": 2, "passed": 1, "not_evaluable": 0}


@dataclass(frozen=True)
class SymbolMarketInput:
    """The price-side inputs one symbol's caps need, resolved by the caller.

    Absent (or absent for one symbol) is a supported state: the caps that need a
    price or an ATR then report ``not_evaluable`` with their own reason, and this
    module lists the symbol as excluded instead of comparing a fabricated one.
    """

    close: float | None = None
    currency: str | None = None
    atr: float | None = None
    fx: FxQuote | None = None


class ExcludedSymbol(BaseModel):
    """One symbol left out of a cap's comparison, with the cap's own reason.

    ``reason`` is quoted verbatim from the per-symbol verdict (or from
    :data:`app.advice.book.SYMBOL_UNVALUED_NOTE` when the holding could not be
    valued), so the aggregate never paraphrases a cause it did not establish.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    market: Market
    reason: str


class BookLimitCheck(BaseModel):
    """One cap's book-level verdict."""

    model_config = ConfigDict(frozen=True)

    #: 1-based position in :data:`app.advice.limits.LIMIT_IDS` -- the "第 X 條上限"
    #: the rest of the product quotes.
    index: int
    limit_id: str
    name: str
    status: LimitStatus
    #: The worst holding's (or industry's) observed value for a per-symbol cap;
    #: the book's own value for the two book-level caps; ``None`` when the cap
    #: was not evaluated.
    observed: float | None
    threshold: float | None
    detail: str
    #: The holding ``observed`` came from, for the caps whose observed value
    #: belongs to a holding. ``None`` for cap 2 (whose verdict is about an
    #: industry, named in ``detail``) and for the two book-level caps.
    worst_symbol: str | None
    #: How many holdings -- or, for cap 2, how many industries -- were actually
    #: compared. ``0`` for the two book-level caps, which compare nothing.
    evaluated_count: int
    excluded: list[ExcludedSymbol]


class BookLimits(BaseModel):
    """Every cap's book-level verdict, plus what the book had to assume."""

    model_config = ConfigDict(frozen=True)

    limits: list[BookLimitCheck]
    #: The book-level notes :mod:`app.advice.book` attaches to any context built
    #: from this summary (equity basis, exposure denominator, unvalued
    #: positions, unclassified holdings).
    notes: list[str]


@dataclass(frozen=True)
class _Candidate:
    """One symbol of the book with its five per-symbol verdicts."""

    symbol: str
    market: Market
    checks: dict[str, LimitCheck]
    sector: str | None = None


@dataclass(frozen=True)
class _Group:
    """The lots of one symbol in one market."""

    symbol: str
    market: Market
    positions: list[SummaryPosition] = field(default_factory=list)


def evaluate_book_limits(
    summary: PortfolioSummary,
    budget: RiskBudget,
    *,
    net_worth: SelfReportedNetWorth | None = None,
    market_data: Mapping[tuple[str, Market], SymbolMarketInput] | None = None,
) -> BookLimits:
    """Judge the whole book against the five caps.

    ``market_data`` is keyed by ``(upper-cased symbol, market)`` and carries what
    the caller could resolve for that holding. A key with no entry is not an
    error: the price-based caps then report their own ``not_evaluable`` reason
    for that symbol and it is listed as excluded.
    """
    prices = market_data or {}
    book = build_book_level_context(summary, net_worth=net_worth)
    baseline = {check.id: check for check in evaluate_limits(budget, book.context)}

    groups = _group_positions(summary)
    candidates, unvalued = _split_by_valuation(summary, budget, groups, prices, net_worth)

    limits = [
        (
            _aggregate(
                limit_id,
                index,
                baseline[limit_id],
                candidates=candidates,
                unvalued=unvalued,
                book_is_empty=not groups,
            )
            if limit_id in PER_SYMBOL_LIMIT_IDS
            else _book_level_check(index, baseline[limit_id])
        )
        for index, limit_id in enumerate(LIMIT_IDS, start=1)
    ]
    return BookLimits(limits=limits, notes=book.notes)


def _book_level_check(index: int, check: LimitCheck) -> BookLimitCheck:
    """A cap whose question is about the book: its verdict travels unchanged."""
    return BookLimitCheck(
        index=index,
        limit_id=check.id,
        name=check.name,
        status=check.status,
        observed=check.observed,
        threshold=check.threshold,
        detail=check.detail,
        worst_symbol=None,
        evaluated_count=0,
        excluded=[],
    )


def _group_positions(summary: PortfolioSummary) -> list[_Group]:
    """The book's lots grouped into one entry per ``(symbol, market)``.

    Market is part of the key because the same ticker in two markets is two
    instruments in two currencies; merging them would put one weight on two
    different holdings. Order follows the position list, so the output is stable.
    """
    groups: dict[tuple[str, Market], _Group] = {}
    for position in summary.positions:
        key = (position.symbol.strip().upper(), position.market)
        group = groups.get(key)
        if group is None:
            group = _Group(symbol=position.symbol, market=position.market)
            groups[key] = group
        group.positions.append(position)
    return list(groups.values())


def _split_by_valuation(
    summary: PortfolioSummary,
    budget: RiskBudget,
    groups: list[_Group],
    prices: Mapping[tuple[str, Market], SymbolMarketInput],
    net_worth: SelfReportedNetWorth | None,
) -> tuple[list[_Candidate], list[ExcludedSymbol]]:
    """Split the book into comparable holdings and the ones rule 3 withholds."""
    candidates: list[_Candidate] = []
    unvalued: list[ExcludedSymbol] = []
    for group in groups:
        skipped = sum(1 for p in group.positions if p.valuation.status != "ok")
        if skipped:
            unvalued.append(
                ExcludedSymbol(
                    symbol=group.symbol,
                    market=group.market,
                    reason=SYMBOL_UNVALUED_NOTE.format(count=skipped)
                    + UNVALUED_EXCLUSION_SUFFIX,
                )
            )
            continue
        context = _symbol_context(summary, group, prices, net_worth)
        candidates.append(
            _Candidate(
                symbol=group.symbol,
                market=group.market,
                checks={check.id: check for check in evaluate_limits(budget, context)},
                sector=context.sector,
            )
        )
    return candidates, unvalued


def _symbol_context(
    summary: PortfolioSummary,
    group: _Group,
    prices: Mapping[tuple[str, Market], SymbolMarketInput],
    net_worth: SelfReportedNetWorth | None,
) -> PortfolioContext:
    """One holding's context, built by the same adapter the advice card uses."""
    data = prices.get((group.symbol.strip().upper(), group.market), SymbolMarketInput())
    return build_book_context(
        summary,
        symbol=group.symbol,
        market=group.market,
        close=data.close,
        currency=data.currency,
        atr=data.atr,
        fx=data.fx,
        net_worth=net_worth,
    ).context


def _aggregate(
    limit_id: str,
    index: int,
    baseline: LimitCheck,
    *,
    candidates: list[_Candidate],
    unvalued: list[ExcludedSymbol],
    book_is_empty: bool,
) -> BookLimitCheck:
    """The worst holding's verdict for one cap, with everything left out named.

    ``baseline`` is the same cap evaluated against the book-level context. Only
    its ``threshold`` is borrowed, and only when nothing could be compared: its
    *status* is an artefact of a context with no holding in it and would be a
    claim about the user's book if it were reported (see
    :func:`app.advice.book.build_book_level_context`).
    """
    excluded = list(unvalued)
    comparable: list[_Candidate] = []
    for candidate in candidates:
        check = candidate.checks[limit_id]
        if check.status == "not_evaluable":
            excluded.append(
                ExcludedSymbol(
                    symbol=candidate.symbol, market=candidate.market, reason=check.detail
                )
            )
        else:
            comparable.append(candidate)

    by_sector = limit_id == "sector_weight"
    if by_sector:
        comparable = _one_per_sector(comparable)

    if not comparable:
        detail = (
            EMPTY_BOOK_DETAIL.format(name=baseline.name)
            if book_is_empty
            else NO_CANDIDATE_DETAILS[limit_id]
        )
        return BookLimitCheck(
            index=index,
            limit_id=limit_id,
            name=baseline.name,
            status="not_evaluable",
            observed=None,
            threshold=baseline.threshold,
            detail=detail,
            worst_symbol=None,
            evaluated_count=0,
            excluded=excluded,
        )

    worst = max(comparable, key=lambda c: _worst_key(c.checks[limit_id]))
    check = worst.checks[limit_id]
    prefix = (
        WORST_SECTOR_PREFIX.format(count=len(comparable))
        if by_sector
        else WORST_SYMBOL_PREFIX.format(count=len(comparable), symbol=worst.symbol)
    )
    suffix = EXCLUDED_SUFFIX.format(count=len(excluded)) if excluded else ""
    return BookLimitCheck(
        index=index,
        limit_id=limit_id,
        name=check.name,
        status=check.status,
        observed=check.observed,
        threshold=check.threshold,
        detail=prefix + check.detail + suffix,
        # Cap 2's observed value is an industry's share, not this holding's, so
        # naming the holding it was read from would misattribute it.
        worst_symbol=None if by_sector else worst.symbol,
        evaluated_count=len(comparable),
        excluded=excluded,
    )


def _one_per_sector(candidates: list[_Candidate]) -> list[_Candidate]:
    """One holding per industry: cap 2 compares industries, not holdings.

    Every holding of the same industry carries the identical industry verdict
    (the numerator is the book's rollup for that industry), so keeping them all
    would report "5 檔" where the comparison really ran over one industry.
    """
    seen: dict[str, _Candidate] = {}
    for candidate in candidates:
        if candidate.sector is not None and candidate.sector not in seen:
            seen[candidate.sector] = candidate
    return list(seen.values())


def _worst_key(check: LimitCheck) -> tuple[int, float]:
    """Worst-first sort key: a breach outranks a pass, then the higher ratio.

    The status rank is explicit rather than implied by the number: it keeps a
    ``violated`` verdict on top even if a future cap ever measured its breach
    downwards.
    """
    return (_STATUS_RANK[check.status], check.observed if check.observed is not None else 0.0)
