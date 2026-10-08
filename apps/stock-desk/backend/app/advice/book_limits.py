"""The same five caps as :mod:`app.advice.limits`, judged over the whole book.

The per-symbol card answers "is *this* holding inside the budget". The overview
asks a different question -- "is the book inside the budget" -- and four of the
five caps have no single book-level number to answer it with: a share of total
equity, an industry's share, a stop-out loss and a Kelly allowance are all
per-holding quantities. So this module does not invent a book-level formula for
them. It runs :func:`app.advice.limits.evaluate_limits` on every symbol in the
book, exactly as the card does, and reports **the worst verdict** with the
symbol (or industry) it came from. The remaining cap -- gross exposure -- is
already a book-level question and is read straight off a book-level context.

Cap 5 joined the per-symbol four in C5 (ADR-0006 D-7). Its input is stored per
``(symbol, market)``, so there is no book-wide pair to judge the book against;
the aggregate compares each holding against *its own* pair and reports the
worst, and a holding whose pair is missing or expired is excluded with that
cap's own sentence rather than compared against a borrowed one.

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
   Cap 2 is the one cap where withholding a holding can understate a verdict
   that *is* reported -- the holding may belong to an industry still in the
   comparison -- so its exclusion sentence discloses that
   (:data:`SECTOR_UNVALUED_EXCLUSION_SUFFIX`). Since ADR-0022 the holdings that
   *are* compared carry the same fact in their own verdict (route C'), and the
   exclusion sentence is chosen once the comparison is known: a holding whose
   industries are all outside it says so instead
   (:data:`SECTOR_UNVALUED_OUTSIDE_COMPARISON_SUFFIX`,
   :data:`SECTOR_UNVALUED_MIXED_OUTSIDE_COMPARISON_SUFFIX`), and a holding with
   no category while nothing at all was compared says that
   (:data:`SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX`).
4. **An empty book is not a book that passed.** With no holding at all there is
   no weight, no industry and no stop-out loss to compare, and no exposure to
   put in cap 3's numerator either: every cap that measures holdings reports
   ``not_evaluable`` with :data:`EMPTY_BOOK_DETAIL` rather than a 0% pass.

Like :mod:`app.advice.book`, this stays a pure function: the caller resolves
prices, ATR and FX rates and hands them in, so the whole aggregation is testable
without a network.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from app.advice.book import (
    SYMBOL_UNVALUED_NOTE,
    BookContext,
    FxQuote,
    SectorComparison,
    book_notes,
    build_book_context,
    build_book_level_context,
    limits_fx_disclosures,
    sector_categories,
)
from app.advice.limits import (
    LIMIT_IDS,
    LIMIT_NAMES,
    KellyInputs,
    LimitCheck,
    LimitStatus,
    RiskBudget,
    SelfReportedNetWorth,
    evaluate_limits,
    shows_price_input_figure,
)
from app.portfolio.summary import PortfolioSummary, SummaryPosition
from app.positions.models import Market
from app.positions.sectors import TWSE_SECTORS

#: The caps whose observed value belongs to one holding, and which are therefore
#: aggregated by comparing every symbol in the book. The one absent id
#: (``gross_exposure``) already answers a book-level question and is taken
#: verbatim from the book-level context.
#:
#: ``kelly_fraction`` is here since C5 (D-7): the pair behind it is keyed on
#: ``(symbol, market)``, so its verdict is about one holding no less than cap 1's
#: is. Reading it off the book-level context instead would report the verdict of
#: a context that carries no pair at all -- "nothing entered yet" -- over a book
#: where the user may well have entered several.
PER_SYMBOL_LIMIT_IDS: tuple[str, ...] = (
    "single_position_weight",
    "sector_weight",
    "per_trade_loss",
    "kelly_fraction",
)

#: Prefix on the worst holding's own verdict, so the reader knows the sentence
#: that follows describes one symbol out of several rather than the book.
#: "觀測值最高" is the neutral way to say "closest to (or furthest past) the cap":
#: for all four per-symbol caps a higher observed value is nearer the ceiling
#: (cap 5's observed value is the holding's weight, like cap 1's).
WORST_SYMBOL_PREFIX = "逐檔評估帳本內 {count} 檔標的，觀測值最高者為 {symbol}："

#: The same for cap 2, which compares industries rather than holdings -- the
#: verdict that follows names the industry itself. ``{count}`` is the number of
#: industries actually compared (``len(comparable)``), which is why the
#: sentence says "納入比較的" rather than "帳本內": route C' and the excluded
#: holdings make the two differ, and a holding filed under several categories
#: is never counted here (ADR-0022 M-2a).
#:
#: W7, replacing the 2026-08-09 sentence unconditionally.
#: 風控核可文案,修改須重新送審(2026-10-07)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (W7)
WORST_SECTOR_PREFIX = "逐項彙總納入比較的 {count} 個產業，觀測值最高者為："

#: Rule 2: the aggregate says what it could not look at, next to the verdict.
EXCLUDED_SUFFIX = "另有 {count} 檔標的未納入本條上限的比較，各自的成因逐檔列出。"

#: Rule 3's ground, appended to the cap's own sentence about the same symbol.
UNVALUED_EXCLUSION_SUFFIX = "本條上限的逐檔比較未納入此標的。"

#: The same for cap 2, which needs one more sentence the other caps do not.
#: Withholding a holding removes it from the numerator of *its own* industry,
#: and that industry may well be one still being compared -- so the industry the
#: verdict is read from can be understated. Cap 1 and cap 4 have no such
#: exposure: their observed value belongs to the withheld holding alone. The
#: direction is stated here, next to the holding that causes it, because the
#: book-level notes say the opposite ("偏高") about a different quantity.
#: 風控核可文案,修改須重新送審(2026-08-09)
#:
#: Since ADR-0022 (M-4) it is used only where it is true: the withheld holding
#: has no category while some industry is compared, or is filed under an
#: industry still in the comparison, or under several categories at least one
#: of which is. The other states have their own sentences below.
SECTOR_UNVALUED_EXCLUSION_SUFFIX = (
    "本條上限的比較未納入此標的；此標的可能屬於已納入比較的產業，使該產業的佔比被低估。"
)

#: W6: the withheld holding is filed under one industry Y, and Y is not in the
#: comparison at all -- so the sentence above ("may belong to a compared
#: industry") would be false. Says instead that Y was not compared, and that
#: not being compared is not the same as being under the cap.
#: 風控核可文案,修改須重新送審(2026-10-07)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (W6)
SECTOR_UNVALUED_OUTSIDE_COMPARISON_SUFFIX = (
    "本條上限的比較未納入此標的；此標的屬於 {sector} 產業，該產業本次沒有任何持倉納入比較，"
    "未納入比較不代表該產業未超過上限。"
)

#: W-6m: the withheld holding's lots were filed under several categories, and
#: none of them is in the comparison (the comparison may be empty). It names
#: every category the user filed -- what the data says, not a claim about the
#: company's business -- in :func:`format_sector_list` order, all of them.
#: 風控核可文案,修改須重新送審(2026-10-07)
#: ``work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md`` (第三段 W-6m)
SECTOR_UNVALUED_MIXED_OUTSIDE_COMPARISON_SUFFIX = (
    "本條上限的比較未納入此標的；此標的的持倉所填產業別為 {sectors}，"
    "這些產業本次沒有任何持倉納入比較，未納入比較不代表這些產業未超過上限。"
)

#: W-6u: the withheld holding was filed under no category at all and *nothing*
#: was compared, so the 2026-08-09 sentence above ("may belong to a compared
#: industry") would point at nothing and contradict cap 2's own "nothing
#: could be compared". No category, nothing compared: the sentence says so and
#: states that the cap could not be confirmed either way -- neither "under"
#: nor "over" (the drafted "does not mean no industry is over" was vetoed as
#: leaning towards "over"). One sentence for all three sub-types, no count
#: (``SYMBOL_UNVALUED_NOTE`` carries it) and no fill-in guidance (D6).
#: 風控核可文案,修改須重新送審(2026-10-07)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (W-6u 逐字審)
SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX = (
    "本條上限的比較未納入此標的；此標的沒有產業別資料，本次沒有任何產業納入比較，"
    "因此無法確認各產業的佔比是否超過上限。"
)

#: The joiner of :func:`format_sector_list`: every name, no "等", no truncation.
SECTOR_LIST_SEPARATOR = "、"

#: Nothing is held at all: there is no holding to compare, which is a different
#: statement from "the holdings could not be judged" below. Also used by cap 3,
#: whose exposure ratio has no numerator on an empty book.
#: 風控核可文案,修改須重新送審(2026-08-09);空帳本第 3 條採路線(a)已核可
EMPTY_BOOK_DETAIL = "帳本內沒有任何持倉，{name}沒有可評估的部位，本次不計算，回報 not_evaluable。"

#: Holdings exist but not one of them could be judged against this cap. The
#: sentence states only that the cap has nothing to compare: naming a cause here
#: would describe every gap with one gap's reason (AC-12.3), and the causes are
#: already carried verbatim, one per holding, in ``excluded``.
#: 風控核可文案,修改須重新送審(2026-08-09);第 2 條採路線(a)揭露低估,已核可
#: 第 2 條 same 情境改採路線 C′（ADR-0022，風控 2026-10-07 核可）；sector 為 None 仍採路線(a)
NO_CANDIDATE_DETAIL = (
    "{name}沒有可納入比較的{unit}，本次不計算，回報 not_evaluable；各標的的成因逐檔列出。"
)

#: What each per-symbol cap compares -- cap 2 ranks industries, the other three
#: rank holdings.
_COMPARED_UNITS: dict[str, str] = {
    "single_position_weight": "標的",
    "sector_weight": "產業",
    "per_trade_loss": "標的",
    "kelly_fraction": "標的",
}

#: :data:`NO_CANDIDATE_DETAIL` per cap, with the cap's own name from
#: :data:`app.advice.limits.LIMIT_NAMES` so the two tables cannot drift apart.
NO_CANDIDATE_DETAILS: dict[str, str] = {
    limit_id: NO_CANDIDATE_DETAIL.format(name=LIMIT_NAMES[limit_id], unit=unit)
    for limit_id, unit in _COMPARED_UNITS.items()
}

#: The book-level caps that still have nothing to compute on an empty book: an
#: exposure ratio with no position in the numerator is not a 0% exposure that
#: passed, it is a ratio with nothing to measure. Only cap 3 is judged at book
#: level at all now (C5 moved cap 5 to the per-symbol path, D-7), and the
#: per-symbol caps get rule 4's treatment from :func:`_aggregate` instead.
EMPTY_BOOK_UNCOMPUTABLE_IDS: frozenset[str] = frozenset({"gross_exposure"})

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
    #: The book-level notes :mod:`app.advice.book` states about this summary
    #: (equity basis, exposure denominator, unvalued positions, unclassified
    #: holdings), assembled by :func:`app.advice.book.book_notes` after every
    #: verdict above exists, then the FX source sentences of
    #: :func:`app.advice.book.limits_fx_disclosures` (task RK-4, R4-25).
    notes: list[str]


@dataclass(frozen=True)
class _Candidate:
    """One symbol of the book with its five per-symbol verdicts."""

    symbol: str
    market: Market
    checks: dict[str, LimitCheck]
    sector: str | None = None
    #: The quote this holding's context applied under (A′), if any (R4-22).
    disclosed_quote: FxQuote | None = None


@dataclass(frozen=True)
class _UnvaluedSymbol:
    """A holding rule 3 withholds, with the note that establishes why.

    The per-cap suffix is attached where the exclusion is reported rather than
    here, because cap 2 has to disclose something the other two caps do not --
    and which sentence is true depends on the comparison, which is only known
    once every candidate has been judged (ADR-0022 M-4, RM-3).
    """

    symbol: str
    market: Market
    note: str
    #: categories(G): every industry the holding's lots were filed under.
    categories: frozenset[str] = frozenset()


@dataclass(frozen=True)
class _Aggregate:
    """One per-symbol cap's book-level verdict, plus the industry it reports.

    ``reported_sector`` is only set for cap 2 when an industry was compared:
    the overview's notes need it (ADR-0022 M-5), and it is not part of the
    response itself.
    """

    check: BookLimitCheck
    reported_sector: str | None = None


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
    kelly_inputs: Mapping[tuple[str, Market], KellyInputs] | None = None,
) -> BookLimits:
    """Judge the whole book against the five caps.

    ``market_data`` is keyed by ``(upper-cased symbol, market)`` and carries what
    the caller could resolve for that holding. A key with no entry is not an
    error: the price-based caps then report their own ``not_evaluable`` reason
    for that symbol and it is listed as excluded.

    ``kelly_inputs`` is keyed the same way and carries cap 5's stored pair per
    holding (D-7). It is deliberately *not* folded into ``market_data``: that
    mapping holds what a price chain resolved, and the caller only fills it for
    symbols whose bars loaded. A Kelly pair exists independently of today's
    prices, and a holding that lost its pair because its bars failed to load
    would be told "nothing entered yet" about an input the user did enter.
    A key with no entry means exactly that nothing was entered for it.
    """
    prices = market_data or {}
    kelly = kelly_inputs or {}
    book = build_book_level_context(summary, net_worth=net_worth)
    baseline = {check.id: check for check in evaluate_limits(budget, book.context)}

    groups = _group_positions(summary)
    candidates, unvalued = _split_by_valuation(summary, budget, groups, prices, kelly, net_worth)

    limits: list[BookLimitCheck] = []
    reported_sector: str | None = None
    for index, limit_id in enumerate(LIMIT_IDS, start=1):
        if limit_id not in PER_SYMBOL_LIMIT_IDS:
            limits.append(_book_level_check(index, baseline[limit_id], book_is_empty=not groups))
            continue
        aggregate = _aggregate(
            limit_id,
            index,
            baseline[limit_id],
            candidates=candidates,
            unvalued=unvalued,
            book_is_empty=not groups,
        )
        limits.append(aggregate.check)
        if limit_id == "sector_weight":
            reported_sector = aggregate.reported_sector
    # Last, once every verdict exists: the notes' direction clause reads the
    # industry cap 2 reported (ADR-0022 M-5), and they are assembled by the
    # one finalizer every response uses (ADR-0023 Decision 8-1).
    notes = book_notes(book, sector_comparison=SectorComparison(reported_sector=reported_sector))
    # Then the FX source sentences (task RK-4, risk RK4-R5): this module only
    # picks the quotes, the sentences are chosen by the book layer.
    notes.extend(limits_fx_disclosures(book, _compared_quotes(candidates)))
    return BookLimits(limits=limits, notes=notes)


def _compared_quotes(candidates: list[_Candidate]) -> list[FxQuote]:
    """G1 of risk RK4-R5: the quotes that reached a figure the overview compares.

    R4-23: a candidate (every lot ``ok``) whose quote was applied under (A′)
    *and* that was compared on at least one cap reading the price or the ATR
    (:data:`app.advice.limits.PRICE_INPUT_LIMIT_IDS`). The quote converts the
    close and the ATR only, so a holding left out of those caps -- no ATR, say
    -- had its quote multiplied into nothing shown. Book order. Judged by the
    one predicate the card and the push use (PR-RK4c, R4c-9); the overview
    shows no share range, hence ``sized=False``.
    """
    return [
        candidate.disclosed_quote
        for candidate in candidates
        if candidate.disclosed_quote is not None
        and shows_price_input_figure(candidate.checks.values(), sized=False)
    ]


def _book_level_check(index: int, check: LimitCheck, *, book_is_empty: bool) -> BookLimitCheck:
    """A cap whose question is about the book: its verdict travels unchanged.

    The one exception is rule 4: on an empty book a cap in
    :data:`EMPTY_BOOK_UNCOMPUTABLE_IDS` has nothing to measure, and the context
    would otherwise hand back a 0% that reads as a pass. A cap that is already
    ``not_evaluable`` keeps its own reason -- it established a cause of its own
    (an absent or stale net worth), and restating it as "no holdings" would
    describe one gap with another's cause.
    """
    nothing_to_measure = (
        book_is_empty
        and check.id in EMPTY_BOOK_UNCOMPUTABLE_IDS
        and check.status != "not_evaluable"
    )
    return BookLimitCheck(
        index=index,
        limit_id=check.id,
        name=check.name,
        status="not_evaluable" if nothing_to_measure else check.status,
        observed=None if nothing_to_measure else check.observed,
        threshold=check.threshold,
        detail=EMPTY_BOOK_DETAIL.format(name=check.name) if nothing_to_measure else check.detail,
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
    kelly: Mapping[tuple[str, Market], KellyInputs],
    net_worth: SelfReportedNetWorth | None,
) -> tuple[list[_Candidate], list[_UnvaluedSymbol]]:
    """Split the book into comparable holdings and the ones rule 3 withholds."""
    candidates: list[_Candidate] = []
    unvalued: list[_UnvaluedSymbol] = []
    for group in groups:
        skipped = sum(1 for p in group.positions if p.valuation.status != "ok")
        if skipped:
            unvalued.append(
                _UnvaluedSymbol(
                    symbol=group.symbol,
                    market=group.market,
                    note=SYMBOL_UNVALUED_NOTE.format(count=skipped),
                    categories=sector_categories(group.positions),
                )
            )
            continue
        book = _symbol_context(summary, group, prices, kelly, net_worth)
        candidates.append(
            _Candidate(
                symbol=group.symbol,
                market=group.market,
                checks={check.id: check for check in evaluate_limits(budget, book.context)},
                sector=book.context.sector,
                disclosed_quote=book.disclosed_quote,
            )
        )
    return candidates, unvalued


def _symbol_context(
    summary: PortfolioSummary,
    group: _Group,
    prices: Mapping[tuple[str, Market], SymbolMarketInput],
    kelly: Mapping[tuple[str, Market], KellyInputs],
    net_worth: SelfReportedNetWorth | None,
) -> BookContext:
    """One holding's context, built by the same adapter the advice card uses.

    The whole :class:`app.advice.book.BookContext`, not only its ``.context``:
    the quote it disclosed is one of the overview's FX sources (R4-22).
    """
    key = (group.symbol.strip().upper(), group.market)
    data = prices.get(key, SymbolMarketInput())
    return build_book_context(
        summary,
        symbol=group.symbol,
        market=group.market,
        close=data.close,
        currency=data.currency,
        atr=data.atr,
        fx=data.fx,
        net_worth=net_worth,
        kelly=kelly.get(key),
    )


def _aggregate(
    limit_id: str,
    index: int,
    baseline: LimitCheck,
    *,
    candidates: list[_Candidate],
    unvalued: list[_UnvaluedSymbol],
    book_is_empty: bool,
) -> _Aggregate:
    """The worst holding's verdict for one cap, with everything left out named.

    ``baseline`` is the same cap evaluated against the book-level context. Only
    its ``threshold`` is borrowed, and only when nothing could be compared: its
    *status* is an artefact of a context with no holding in it and would be a
    claim about the user's book if it were reported (see
    :func:`app.advice.book.build_book_level_context`).

    The comparison is settled first and the withheld holdings' sentences are
    chosen after it (ADR-0022 M-4, RM-3): for cap 2, which sentence is true of
    a withheld holding depends on which industries ended up compared. The
    withheld holdings still come first in ``excluded``, as they always have.
    """
    by_sector = limit_id == "sector_weight"
    comparable: list[_Candidate] = []
    candidate_exclusions: list[ExcludedSymbol] = []
    for candidate in candidates:
        check = candidate.checks[limit_id]
        if check.status == "not_evaluable":
            candidate_exclusions.append(
                ExcludedSymbol(
                    symbol=candidate.symbol, market=candidate.market, reason=check.detail
                )
            )
        else:
            comparable.append(candidate)

    if by_sector:
        comparable = _one_per_sector(comparable)
    compared_sectors = frozenset(
        candidate.sector for candidate in comparable if candidate.sector is not None
    )
    excluded = [
        ExcludedSymbol(
            symbol=entry.symbol,
            market=entry.market,
            reason=entry.note
            + (
                _sector_unvalued_suffix(entry.categories, compared_sectors)
                if by_sector
                else UNVALUED_EXCLUSION_SUFFIX
            ),
        )
        for entry in unvalued
    ]
    excluded.extend(candidate_exclusions)

    if not comparable:
        detail = (
            EMPTY_BOOK_DETAIL.format(name=baseline.name)
            if book_is_empty
            else NO_CANDIDATE_DETAILS[limit_id]
        )
        return _Aggregate(
            BookLimitCheck(
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
        )

    worst = max(comparable, key=lambda c: _worst_key(c.checks[limit_id]))
    check = worst.checks[limit_id]
    prefix = (
        WORST_SECTOR_PREFIX.format(count=len(comparable))
        if by_sector
        else WORST_SYMBOL_PREFIX.format(count=len(comparable), symbol=worst.symbol)
    )
    suffix = EXCLUDED_SUFFIX.format(count=len(excluded)) if excluded else ""
    return _Aggregate(
        BookLimitCheck(
            index=index,
            limit_id=limit_id,
            name=check.name,
            status=check.status,
            observed=check.observed,
            threshold=check.threshold,
            detail=prefix + check.detail + suffix,
            # Cap 2's observed value is an industry's share, not this holding's,
            # so naming the holding it was read from would misattribute it.
            worst_symbol=None if by_sector else worst.symbol,
            evaluated_count=len(comparable),
            excluded=excluded,
        ),
        reported_sector=worst.sector if by_sector else None,
    )


def _sector_unvalued_suffix(categories: frozenset[str], compared: frozenset[str]) -> str:
    """Cap 2's sentence for a withheld holding, given what was compared (M-4).

    * Filed under one industry Y (unfiled lots beside it included), Y not
      compared -> W6 naming Y.
    * Filed under several, none compared (or nothing compared) -> W-6m naming
      them all.
    * Filed under no category while nothing at all was compared -> W-6u
      (:data:`SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX`): "may belong
      to a compared industry" would point at nothing.
    * Otherwise -- no category with some industry compared, or an industry
      still in the comparison -> the 2026-08-09 sentence, unchanged: there it
      is true.
    """
    if len(categories) == 1:
        (sector,) = categories
        if sector not in compared:
            return SECTOR_UNVALUED_OUTSIDE_COMPARISON_SUFFIX.format(sector=sector)
        return SECTOR_UNVALUED_EXCLUSION_SUFFIX
    if len(categories) > 1 and not categories & compared:
        return SECTOR_UNVALUED_MIXED_OUTSIDE_COMPARISON_SUFFIX.format(
            sectors=format_sector_list(categories)
        )
    if not categories and not compared:
        return SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX
    # Only reachable with something compared: the old sentence has a referent.
    return SECTOR_UNVALUED_EXCLUSION_SUFFIX


#: Position of each TWSE category in the exchange's own order, for
#: :func:`format_sector_list`.
_TWSE_SECTOR_RANK: dict[str, int] = {name: rank for rank, name in enumerate(TWSE_SECTORS)}


def _sector_list_key(sector: str) -> tuple[int, int, str]:
    """Sort key for one category: TWSE order first, anything else after it.

    A total order over every string, so sorting can never raise: a category
    in :data:`app.positions.sectors.TWSE_SECTORS` sorts by its index there; a
    value that is not (legacy data) sorts after all of them, by code point.
    """
    rank = _TWSE_SECTOR_RANK.get(sector)
    if rank is None:
        return (1, 0, sector)
    return (0, rank, "")


def format_sector_list(categories: Iterable[str]) -> str:
    """Every category in ``categories``, once, in TWSE order, joined by "、".

    ADR-0022 M-4 / RM-2 -- W-6m's ``{sectors}``: de-duplicated, ordered by
    :data:`app.positions.sectors.TWSE_SECTORS` (the order the user picks from
    on the positions form) with any other value last, joined with "、", never
    shortened and never ending in "等". Its own function on purpose: the order
    a reader sees is not borrowed from any other sort in the code base.
    """
    return SECTOR_LIST_SEPARATOR.join(sorted(set(categories), key=_sector_list_key))


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
