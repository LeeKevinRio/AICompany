"""Build a :class:`PortfolioContext` from stored positions and their valuations.

This is the adapter between the *bookkeeping* layer (``app/positions`` +
``app/portfolio``, Decimal money, per-position valuations that may individually
be ``insufficient_data``) and the *risk-budget* layer (``app/advice/limits``,
float ratios). It exists so both the advice endpoint and the alert engine build
the same context from the same rules instead of each inventing its own.

Three honesty rules govern what is filled in:

1. **Only ``ok`` valuations are aggregated.** A position that could not be
   valued (no price, or no FX rate) contributes nothing to the book total and
   is listed in ``notes``, so a partial book is never presented as a whole one.
2. **Equity is the valued book, and says so.** There is no cash or account
   balance anywhere in this product, so ``total_equity_twd`` is the market
   value of the successfully valued positions. That is an assumption, and it is
   stated in ``notes`` rather than left for the reader to infer.
3. **Gross exposure needs a denominator the user supplied.** Nothing in this
   product knows the account's cash or margin balances, so the only figure that
   can sit under the exposure ratio is the net worth the user reports on the
   settings page (FR-9). Without one the cap stays ``not_evaluable`` exactly as
   it always was -- the equity figure is *not* substituted, because dividing
   the valued book by itself would force the ratio to 100% and turn an unknown
   into a permanent "violated". With one, the numerator is the valued book and
   the denominator is the reported net worth, and the two different origins are
   disclosed on the verdict itself (:mod:`app.advice.limits`).

   The valued book is used as the numerator **only when every position could be
   valued**: a short numerator makes exposure look lower than it is, and that is
   the single direction this cap must never err in, so an incomplete book yields
   ``not_evaluable`` instead (FR-9 (a-附加)).

4. **A sector total only counts what was actually classified.** ``sector`` is
   the category the user typed on the holding itself (FR-12); positions with no
   category are counted into no industry at all, and the fact that some were
   left out travels with the context in ``notes`` (AC-12.5). Nothing is
   inferred from a symbol, and an unclassified book is never presented as a
   diversified one. *Why* this symbol has no category -- nothing held, nothing
   filed, an ETF the taxonomy does not apply to, a market with no taxonomy, or
   two categories on one symbol -- travels with it in ``sector_gap``, because
   the five are different problems and only this layer can tell them apart
   (AC-12.3).

5. **The Kelly pair is passed in, never fetched.** Since C5 there *is* a source
   for it (``kelly_inputs``, ADR-0006 D-2), but reading it here would put a
   database call inside the one purely-computational assembly point. The caller
   resolves the row and hands it to :func:`kelly_inputs_of`, which is where the
   clock is read and where an expired pair keeps its age instead of being
   flattened into an absence -- cap 5 has four different sentences for the ways
   an input can be unusable, and it can only choose between them if the
   difference survives this layer.

FX (ADR-0005 decision 5): this module stays a pure function and **never imports
an adapter**. The caller resolves the rate (``app/services/fx.py``) and passes a
:class:`FxQuote` in; letting this layer fetch would put I/O into the one
purely-computational risk assembly point and force every test to mock a
network. The red line is unchanged: no quote, no rate, or a quote for the wrong
pair all yield ``None`` -- the price is then withheld so the price-based caps
report ``not_evaluable``, and **no default rate is ever substituted for a
non-TWD currency**. The reason text distinguishes "no price" from "no FX
conversion", because they call for different things from the reader.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from app.advice.limits import (
    NET_WORTH_STALE_AFTER_DAYS,
    SECTOR_MIXED_DETAIL,
    KellyInputs,
    PortfolioContext,
    SectorGap,
    SelfReportedNetWorth,
    format_percent,
    format_reported_at,
)
from app.data.interface import DataStatus
from app.kelly.models import KellyInputRow, ageing_of
from app.portfolio.summary import PortfolioSummary, SummaryPosition
from app.positions.models import InstrumentType, Market

#: The markets whose holdings may carry an industry category at all. TWSE's
#: taxonomy is TW-only by decision (AC-12.6, :mod:`app.positions.sectors`), and
#: a holding outside this set is not "missing a value" -- there is nothing it
#: could be filed under yet, which is why cap 2 says something different about
#: it (:data:`app.advice.limits.NO_SECTOR_UNSUPPORTED_MARKET_DETAIL`).
SECTOR_CLASSIFIED_MARKETS: frozenset[Market] = frozenset({"TW"})

#: The instrument types that are funds rather than individual companies. A TW
#: holding of one of these with no category is not "not filled in yet": TWSE's
#: industry taxonomy classifies listed companies, so an ETF has nothing true it
#: could be filed under, and cap 2 must say that instead of directing its owner
#: to fill the field (D6, :data:`app.advice.limits.NO_SECTOR_ETF_DETAIL`).
ETF_INSTRUMENT_TYPES: frozenset[InstrumentType] = frozenset(
    {"etf", "leveraged_etf", "futures_etf"}
)

#: Stated on every context so the equity assumption travels with the numbers.
EQUITY_BASIS_NOTE = (
    "總資產以「已成功估值的部位市值合計」為代表，系統沒有現金與帳戶淨值資料，"
    "因此所有以總資產為分母的比率都建立在這個假設上。"
)

#: Stated whenever gross exposure is deliberately left out.
GROSS_EXPOSURE_NOTE = (
    "缺少現金與融資餘額資料，總曝險無法計算；該上限會回報 not_evaluable，"
    "不以總資產代入而讓比率恆為 100%。"
)

#: Stated instead, once the user has supplied a net worth for the cap to use.
#: It names both halves of the ratio and where each came from, because the two
#: numbers no longer share an origin.
GROSS_EXPOSURE_SELF_REPORTED_NOTE = (
    "總曝險以「已估值部位市值合計」為分子、使用者自報的帳戶總淨值"
    "新台幣 {amount:,.0f} 元為分母，輸入時間為 {reported_at}；"
    "此淨值由使用者自行輸入，系統未加以查核。"
)

#: And stated when the report is past its freshness rule. The present-tense
#: sentence above would otherwise sit next to a cap reporting ``not_evaluable``
#: for that very reason, describing a division this context does not perform.
GROSS_EXPOSURE_EXPIRED_NOTE = (
    "使用者自報的帳戶總淨值新台幣 {amount:,.0f} 元，輸入時間為 {reported_at}，"
    "已超過 {days} 天未更新，本次不以它為分母計算總曝險；"
    "該上限回報 not_evaluable，待使用者更新淨值後才會恢復計算。"
)

#: AC-12.5: the sector ratio was computed while some holdings sat outside every
#: industry bucket, so it is a floor rather than the whole picture -- and says so
#: instead of quietly reporting ``passed``. The count travels with the market
#: value and the share of equity it stands for, because a number of rows hides
#: the size of the hole: "3 筆" reads the same whether those rows are 1% or 40%
#: of the book. The last clause is the one
#: :data:`app.advice.limits.GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL` already makes
#: about its own numerator -- a ``passed`` derived from an understated ratio is
#: still an understated ratio.
#:
#: Wording reviewed and approved by risk-compliance on 2026-08-09 (FR-12 句 2
#: 修正句), recorded in ``work/reviews/c1-phase8-review.md``; changing it needs a
#: fresh review.
SECTOR_UNCLASSIFIED_NOTE = (
    "組合中有 {count} 筆已估值持倉未填產業別，合計市值新台幣 {amount:,.0f} 元、"
    "佔總資產 {share}，未計入任何產業的市值合計；單一產業佔比可能被低估，"
    "這條上限的通過判定也可能建立在偏低的比率上。"
)

#: Rule 1 stated on the book as a whole: positions that could not be valued are
#: outside every total, so every ratio built on the valued book reads high.
#: A constant rather than an inline f-string because the book-level assembly
#: (:func:`build_book_level_context`) states the same fact about the same books.
UNVALUED_POSITIONS_NOTE = (
    "組合中有 {count} 筆部位無法估值（缺價格或匯率），未計入總資產；比率會因此偏高。"
)

#: The same fact about *one* symbol's own lots. Extracted for the same reason:
#: the book-level caps name this as the ground for leaving a symbol out of a
#: per-symbol comparison, and the two statements must not drift apart.
SYMBOL_UNVALUED_NOTE = "此標的有 {count} 筆持倉無法估值，未計入本標的的部位市值與成本。"

#: No quote at all reached this layer for a non-TWD holding.
NO_FX_QUOTE_NOTE = (
    "計價幣別為 {currency}，本次沒有取得任何匯率報價，"
    "價格與 ATR 相關的上限不計算；這是「無法取得匯率換算」，與「無法取得價格」不同，"
    "且不以 1.0 匯率代入。"
)

#: A quote arrived but carries no usable rate.
FX_UNAVAILABLE_NOTE = (
    "計價幣別為 {currency}，{pair} 匯率報價沒有可用數值"
    "（資料狀態 {status}、來源 {source}、匯率日期 {as_of}），"
    "價格與 ATR 相關的上限不計算；這是「無法取得匯率換算」，與「無法取得價格」不同，"
    "且不以 1.0 匯率代入。"
)

#: A quote arrived for a different pair than the holding needs.
FX_PAIR_MISMATCH_NOTE = (
    "計價幣別為 {currency}，需要的匯率是 {expected}，但取得的報價是 {pair}；"
    "不以不相符的匯率換算，價格與 ATR 相關的上限不計算。"
)

#: The rate actually used, with the freshness the reader needs to judge it.
FX_APPLIED_NOTE = (
    "價格與 ATR 以 {pair} 匯率 {rate} 換算為台幣"
    "（資料狀態 {status}、來源 {source}、匯率日期 {as_of}）。"
)


@dataclass(frozen=True)
class FxQuote:
    """One instrument-currency -> TWD rate with the provenance it must carry.

    ``rate`` is ``None`` when the source had nothing usable: the failure is
    still delivered as a quote so its ``status``/``as_of``/``source`` can reach
    ``notes`` instead of collapsing into a silent absence (ADR-0005 F-3).

    ``as_of`` is the **date of the rate that was used**, not the time the fetch
    happened -- a rate from three days ago used today is exactly what a reader
    needs to see. ``source_note`` carries the source's own standing disclosure
    (unverified endpoint, mid-point model value, ...) so this module does not
    have to know which adapter produced the number (F-4).
    """

    pair: str
    rate: float | None
    as_of: str | None
    source: str
    status: DataStatus
    source_note: str = ""


#: The ``symbol`` a book-level context carries (:func:`build_book_level_context`).
#: Nothing reads it: the only cap evaluated against such a context is the one
#: whose verdict is about the whole book rather than about a holding -- gross
#: exposure -- and its sentence names no symbol. (Cap 5 was the second such cap
#: until C5 gave it a per-symbol input; it is aggregated per holding now, D-7.)
#: It is spelled as a visible label rather than left
#: blank so that a value leaking into prose would be recognisable as this
#: placeholder instead of reading like a ticker.
BOOK_LEVEL_SYMBOL = "（整體帳本）"


@dataclass(frozen=True)
class BookContext:
    """A :class:`PortfolioContext` plus what had to be assumed or left out."""

    context: PortfolioContext
    held: bool
    position_ids: list[int] = field(default_factory=list)
    #: Currency of the matched holding(s), or ``None`` for a candidate.
    currency: str | None = None
    notes: list[str] = field(default_factory=list)
    #: The rate applied (``1.0`` for TWD), or ``None`` when none could be.
    fx_rate: float | None = None
    #: The single FX sentence from ``notes``, for callers whose output shape has
    #: no notes list of its own (the alert snapshot).
    fx_note: str | None = None


def _matching(
    summary: PortfolioSummary, symbol: str, market: Market | None
) -> list[SummaryPosition]:
    """Positions in ``summary`` for ``symbol`` (optionally pinned to a market)."""
    wanted = symbol.strip().upper()
    return [
        position
        for position in summary.positions
        if position.symbol.strip().upper() == wanted
        and (market is None or position.market == market)
    ]


def _book_equity(summary: PortfolioSummary) -> tuple[float, int, int]:
    """Return ``(valued market value, valued count, total count)``.

    The market value comes from ``totals``, which the summary layer already
    restricts to the ``ok`` valuations.
    """
    total = len(summary.positions)
    valued = sum(1 for position in summary.positions if position.valuation.status == "ok")
    return float(summary.totals.market_value_twd), valued, total


def _fully_valued(summary: PortfolioSummary) -> bool:
    """Whether every stored position could be valued.

    An empty book is ``True``: nothing failed to value, and an exposure of zero
    against a reported net worth is a fact, not a gap.
    """
    return all(position.valuation.status == "ok" for position in summary.positions)


def _gross_exposure_note(net_worth: SelfReportedNetWorth | None) -> str:
    """The standing sentence about the exposure cap, in whichever state it is in.

    Three states, three sentences: no figure at all, a usable one, and one the
    freshness rule has retired. The third exists because the second is written
    in the present tense -- claiming a division that an expired report does not
    get to perform, right beside a cap saying it could not perform it.
    """
    if net_worth is None:
        return GROSS_EXPOSURE_NOTE
    if net_worth.age_days >= NET_WORTH_STALE_AFTER_DAYS:
        return GROSS_EXPOSURE_EXPIRED_NOTE.format(
            reported_at=format_reported_at(net_worth.reported_at),
            amount=net_worth.amount_twd,
            days=NET_WORTH_STALE_AFTER_DAYS,
        )
    return GROSS_EXPOSURE_SELF_REPORTED_NOTE.format(
        reported_at=format_reported_at(net_worth.reported_at), amount=net_worth.amount_twd
    )


def _position_rollup(
    positions: list[SummaryPosition],
) -> tuple[float, float | None, float, int]:
    """Roll up the ``ok``-valued rows: ``(market value, cost, quantity, skipped)``.

    Both money figures are the position's **own TWD contribution** as the
    summary layer computed it, for the same reason ``_sector_rollup`` uses them:
    these two feed ``position_market_value_twd`` / ``position_cost_twd``, which
    sit over TWD denominators (``total_equity_twd``, and the TWD price used for
    share sizing). Multiplying quantity by a close in the instrument's own
    currency would put a USD numerator over a TWD denominator and make a foreign
    holding's share of the book read low by the exchange rate -- "risk looks
    smaller than it is", the one direction these caps must never err in -- and
    the same mixed unit would then travel into every suggested share count via
    :func:`app.advice.limits.notional_caps`. Only the share count stays as it
    is: a quantity has no currency.

    ``cost`` is ``None`` when no row carried one, so the unrealized-P&L ratio
    reports "no cost" instead of a zero that would read as a -100% loss.
    """
    market_value = Decimal(0)
    cost = Decimal(0)
    quantity = Decimal(0)
    has_cost = False
    skipped = 0
    for position in positions:
        if position.valuation.status != "ok" or position.market_value_twd is None:
            skipped += 1
            continue
        market_value += position.market_value_twd
        if position.cost_twd is not None:
            cost += position.cost_twd
            has_cost = True
        quantity += position.quantity
    return (
        float(market_value),
        float(cost) if has_cost else None,
        float(quantity),
        skipped,
    )


def _resolve_sector(matched: list[SummaryPosition]) -> tuple[str | None, SectorGap | None]:
    """The symbol's industry category -> ``(sector, gap)``.

    ``gap`` is ``None`` exactly when a category was resolved; otherwise it names
    *which* of the five states left this symbol unclassified, so cap 2 can say
    the one true thing about each instead of one sentence covering all five
    (see :data:`app.advice.limits.SectorGap`). Only this layer can tell them
    apart: it is the one that sees whether anything is held, in which market,
    with which instrument type, and whether the holdings agree with each other.
    """
    if not matched:
        return None, "no_position"
    categories = sorted({position.sector for position in matched if position.sector})
    if len(categories) > 1:
        return None, "mixed"
    if categories:
        return categories[0], None
    classifiable = [
        position for position in matched if position.market in SECTOR_CLASSIFIED_MARKETS
    ]
    if not classifiable:
        return None, "unsupported_market"
    if all(
        position.instrument_type in ETF_INSTRUMENT_TYPES for position in classifiable
    ):
        # Every TW lot behind this symbol is a fund: there is no company-level
        # industry it could truthfully be filed under, so the "fill it in"
        # guidance would be an instruction the owner cannot follow (D6). The
        # symbol stays excluded from cap 2 exactly as before.
        return None, "etf_instrument"
    # At least one holding *could* carry a category, so naming the action is
    # a true statement. A symbol held in both markets lands here too: the TW
    # leg is the one that would turn the cap on. A stock lot alongside an ETF
    # lot keeps this state as well -- the stock lot is the one the guidance
    # sentence is true for.
    return None, "unfiled"


def _sector_rollup(summary: PortfolioSummary, sector: str) -> float:
    """``sector``'s TWD market value across the whole book.

    Only ``ok`` valuations are summed (rule 1) and only their own TWD
    contribution is used, so the numerator and ``total_equity_twd`` come from
    the same figures.
    """
    total = Decimal(0)
    for position in summary.positions:
        if position.valuation.status != "ok" or position.market_value_twd is None:
            continue
        if position.sector == sector:
            total += position.market_value_twd
    return float(total)


def _unclassified_rollup(summary: PortfolioSummary) -> tuple[int, float]:
    """Valued holdings that sit outside every industry: ``(count, market value)``.

    This is what AC-12.5 requires disclosing: valued holdings that belong to
    *some* industry the user has not named, and therefore make every industry's
    share look smaller than it is. The value is carried beside the count because
    the count alone does not say how much of the book is missing from the ratio.
    """
    count = 0
    value = Decimal(0)
    for position in summary.positions:
        if position.valuation.status != "ok" or position.market_value_twd is None:
            continue
        if position.sector is None:
            count += 1
            value += position.market_value_twd
    return count, float(value)


def _sector_unclassified_note(summary: PortfolioSummary, equity: float) -> str | None:
    """AC-12.5's disclosure, or ``None`` when there is nothing to disclose.

    The share is only stated when there is a denominator to state it against. An
    unclassified *valued* row is itself part of ``equity``, so a non-zero count
    with a zero book is not reachable in practice; when it is, every
    equity-based cap already reports ``not_evaluable`` and this disclosure would
    have nothing to qualify.
    """
    count, value = _unclassified_rollup(summary)
    if not count or equity <= 0.0:
        return None
    return SECTOR_UNCLASSIFIED_NOTE.format(
        count=count, amount=value, share=format_percent(value / equity)
    )


def self_reported_net_worth(
    amount_twd: float | None,
    updated_at: str | None,
    *,
    now: datetime | None = None,
) -> SelfReportedNetWorth | None:
    """Turn the stored settings pair into the risk layer's view of it.

    This is the single place the clock is read for FR-9, so the freshness the
    settings page displays and the freshness the cap enforces can never drift
    apart. ``None`` comes back when there is nothing usable to report:

    * no amount, or a non-positive one (the settings boundary already rejects
      those with a 422; this is the second line, not the first);
    * no timestamp, or one that cannot be parsed -- an amount whose age is
      unknown cannot be shown to be fresh, and FR-9 (b) forbids using it
      anyway, so it is withheld rather than passed on as if it were current.

    A naive stored timestamp is read as UTC, matching what
    :meth:`app.settings.store.SettingsStore.save` writes.
    """
    if amount_twd is None or amount_twd <= 0.0 or updated_at is None:
        return None
    try:
        reported = datetime.fromisoformat(updated_at)
    except ValueError:
        return None
    if reported.tzinfo is None:
        reported = reported.replace(tzinfo=UTC)
    moment = now if now is not None else datetime.now(UTC)
    # A timestamp in the future (clock skew, or an edited database) is treated
    # as "reported now" rather than as a negative age.
    age_days = max((moment - reported).days, 0)
    return SelfReportedNetWorth(
        amount_twd=amount_twd, reported_at=updated_at, age_days=age_days
    )


def kelly_inputs_of(
    row: KellyInputRow | None,
    *,
    ci_includes_no_edge: bool = False,
    now: datetime | None = None,
) -> KellyInputs | None:
    """Turn one stored Kelly row into the risk layer's view of it (D-6).

    The Kelly half of what :func:`self_reported_net_worth` does for FR-9, and
    for the same reason: this is the single place the clock is read for cap 5,
    so the age the settings page shows and the age the cap enforces cannot
    drift apart. Ageing itself is delegated to
    :func:`app.kelly.models.ageing_of` -- the one place the "no anchor means
    expired" rule lives -- rather than re-derived here, where a second
    derivation could land on a friendlier answer.

    ``None`` in gives ``None`` out, and that ``None`` carries a specific
    meaning downstream: **no pair has ever been entered**. An expired row is
    *not* collapsed into it. Cap 5 has four different things to say about an
    unusable input ((g-1) to (g-4)) and could not tell them apart from an
    absence, so the row travels on with its age and source and the cap decides
    (D-6 puts the expiry判定 in ``_check_kelly_fraction``).

    ``ci_includes_no_edge`` is passed in, never computed here: 約束 36 makes
    ``app/api/kelly.py`` the one place that reduces the stored interval to that
    boolean.

    This function reads no database. The caller resolves the row, exactly as it
    resolves prices and FX rates, so this module stays the pure function
    ADR-0005 decision 5 requires.
    """
    if row is None:
        return None
    ageing = ageing_of(row, now=now)
    return KellyInputs(
        win_rate=row.win_rate,
        payoff_ratio=row.payoff_ratio,
        source=row.source,
        age_days=ageing.age_days,
        # 6-A: a plain calendar day, never an ISO datetime. The backtest
        # anchor's time of day is padded, so rendering it would show precision
        # the measurement does not have; the manual anchor is truncated to the
        # same shape so the two sentences cannot be told apart by their format.
        anchored_at=None if ageing.anchored_at is None else ageing.anchored_at.date().isoformat(),
        strategy_id=row.strategy_id,
        oos_start_date=row.oos_start_date,
        oos_end_date=row.oos_end_date,
        oos_round_trips=row.oos_round_trips,
        ci_includes_no_edge=ci_includes_no_edge,
    )


def _book_level_notes(
    summary: PortfolioSummary, net_worth: SelfReportedNetWorth | None
) -> list[str]:
    """The notes that describe the book itself, whatever symbol is being asked about.

    Assembled in one place so the per-symbol context and the book-level context
    state the same three things about the same book: what stands in for total
    equity, which state the exposure cap's denominator is in, and how much of
    the book could not be valued at all.
    """
    notes = [EQUITY_BASIS_NOTE, _gross_exposure_note(net_worth)]
    _, valued_count, total_count = _book_equity(summary)
    if total_count and valued_count < total_count:
        notes.append(UNVALUED_POSITIONS_NOTE.format(count=total_count - valued_count))
    return notes


def build_book_level_context(
    summary: PortfolioSummary, *, net_worth: SelfReportedNetWorth | None = None
) -> BookContext:
    """The whole book as one context, for the cap that is not about a holding.

    One of the five caps asks a question with a single book-level answer: gross
    exposure, the valued book over the reported net worth. It reads no
    per-symbol field, so it needs no symbol -- the context therefore carries
    :data:`BOOK_LEVEL_SYMBOL` and leaves every per-symbol field unset, which is
    exactly what makes caps 1, 2, 4 and 5 report ``not_evaluable`` if anyone
    evaluates them here. **They must not be read from this context**: their
    book-level verdicts are aggregated per symbol by
    :mod:`app.advice.book_limits`, and a ``not_evaluable`` produced by an unset
    field would look like a fact about the user's book.

    ``kelly`` is unset here and there is no parameter to set it with. Cap 5
    became a per-symbol cap in C5 (D-7): its input is keyed on
    ``(symbol, market)``, so the book as a whole has no pair to be judged
    against, and one borrowed from any single holding would be applied to all
    of them. ``tests/test_advice_book.py`` pins the field at ``None`` here.

    ``held`` is ``False`` and ``position_ids`` empty for the same reason: this
    context stands for no holding.
    """
    equity, _, _ = _book_equity(summary)
    notes = _book_level_notes(summary, net_worth)
    # Attached on the same condition as in :func:`build_book_context`: the
    # sentence qualifies an industry ratio, so it is stated when there is at
    # least one classified valued holding for that ratio to be computed from.
    if _has_classified_holding(summary):
        unclassified_note = _sector_unclassified_note(summary, equity)
        if unclassified_note is not None:
            notes.append(unclassified_note)
    context = PortfolioContext(
        symbol=BOOK_LEVEL_SYMBOL,
        total_equity_twd=equity,
        # Same rule as the per-symbol context: the numerator is only offered
        # when a denominator exists to divide it by (module docstring, rule 3).
        gross_exposure_twd=equity if net_worth is not None else None,
        net_worth=net_worth,
        book_fully_valued=_fully_valued(summary),
    )
    return BookContext(context=context, held=False, notes=notes)


def _has_classified_holding(summary: PortfolioSummary) -> bool:
    """Whether any valued holding carries an industry category at all."""
    return any(
        position.valuation.status == "ok" and position.sector is not None
        for position in summary.positions
    )


def build_book_context(
    summary: PortfolioSummary,
    *,
    symbol: str,
    market: Market | None = None,
    close: float | None = None,
    currency: str | None = None,
    atr: float | None = None,
    fx: FxQuote | None = None,
    net_worth: SelfReportedNetWorth | None = None,
    kelly: KellyInputs | None = None,
) -> BookContext:
    """Assemble the risk-budget context for ``symbol`` against the whole book.

    ``close`` is the latest close **in the instrument's own currency** (the unit
    the caps compare); pass ``None`` when no price is available and the
    price-dependent caps will report ``not_evaluable`` instead of guessing.
    A symbol with no holding yields a *candidate* context
    (``position_market_value_twd=0``, ``quantity=0``) so a card can still be
    produced for something the user does not own yet.

    ``fx`` is the instrument-currency -> TWD quote the caller resolved. It is
    ignored for a TWD instrument (which needs no conversion) and required for
    every other currency; without a usable one the price is withheld rather
    than scaled by an invented rate.

    ``net_worth`` is the figure the user reported on the settings page, built
    by :func:`self_reported_net_worth`. It reaches one cap and one cap only
    (gross exposure); ``total_equity_twd`` keeps its old definition whether it
    is supplied or not, so caps 1 and 4 are unaffected by it.

    ``kelly`` is this symbol's stored Kelly pair, built by
    :func:`kelly_inputs_of`. It likewise reaches one cap and one cap only
    (cap 5). Omitting it is a supported state and means exactly what an empty
    ``kelly_inputs`` table means -- the cap reports (g-1), "nothing entered
    yet". A caller that *has* a row and forgets to pass it therefore produces a
    card stating something untrue about the user's own input, which is why the
    production call sites are pinned by
    ``tests/test_book_context_call_sites.py``.
    """
    fully_valued = _fully_valued(summary)
    notes: list[str] = _book_level_notes(summary, net_worth)
    equity, _, _ = _book_equity(summary)

    matched = _matching(summary, symbol, market)
    market_value, cost, quantity, skipped = _position_rollup(matched)
    if skipped:
        notes.append(SYMBOL_UNVALUED_NOTE.format(count=skipped))

    sector, sector_gap = _resolve_sector(matched)
    if sector_gap == "mixed":
        notes.append(SECTOR_MIXED_DETAIL)
    sector_market_value: float | None = None
    if sector is not None:
        sector_market_value = _sector_rollup(summary, sector)
        unclassified_note = _sector_unclassified_note(summary, equity)
        if unclassified_note is not None:
            notes.append(unclassified_note)

    currencies = sorted({position.currency for position in matched})
    holding_currency = currencies[0] if len(currencies) == 1 else None
    mixed_currencies = len(currencies) > 1
    if mixed_currencies:
        notes.append("此標的的持倉橫跨多種計價幣別，無法決定單一匯率，價格類上限不計算。")

    effective_currency = holding_currency if matched else currency
    if mixed_currencies:
        # Which of the two rates would be the right one is undecidable, so the
        # question is refused rather than answered with one of them.
        rate, fx_note = None, None
    else:
        rate, fx_note = _resolve_fx(effective_currency, fx)
    if fx_note is not None:
        notes.append(fx_note)
    if rate is not None and fx is not None and fx.source_note:
        notes.append(fx.source_note)

    context = PortfolioContext(
        symbol=symbol,
        total_equity_twd=equity,
        position_market_value_twd=market_value,
        position_cost_twd=cost,
        # The numerator is the valued book; it is only offered when there is a
        # denominator to divide it by. Without a reported net worth the field
        # stays absent and the cap behaves exactly as it did before FR-9
        # (AC-9.2) -- see the module docstring, rule 3.
        gross_exposure_twd=equity if net_worth is not None else None,
        net_worth=net_worth,
        book_fully_valued=fully_valued,
        quantity=quantity,
        close=close if rate is not None else None,
        # ``close`` is ``None`` whenever ``rate`` is, so this 1.0 is never
        # applied to a foreign-currency amount; it only satisfies the field's
        # "must be a positive float" contract.
        fx_to_twd=rate if rate is not None else 1.0,
        atr=atr if rate is not None else None,
        sector=sector,
        sector_market_value_twd=sector_market_value,
        sector_gap=sector_gap,
        kelly=kelly,
    )
    return BookContext(
        context=context,
        held=bool(matched),
        position_ids=[position.id for position in matched],
        currency=effective_currency,
        notes=notes,
        fx_rate=rate,
        fx_note=fx_note,
    )


def _resolve_fx(currency: str | None, fx: FxQuote | None) -> tuple[float | None, str | None]:
    """Instrument currency -> ``(rate, note)``; ``rate`` is ``None`` if unusable.

    A TWD instrument (or a candidate with no currency at all) is already in the
    reporting currency and needs no quote. For every other currency the quote
    has to exist, be for the right pair, and carry a positive rate; anything
    else returns ``None`` with a sentence naming *which* input was missing, so
    "no price" and "no FX conversion" never look the same downstream.
    """
    if currency is None or currency.strip().upper() == "TWD":
        return 1.0, None
    if fx is None:
        return None, NO_FX_QUOTE_NOTE.format(currency=currency)

    expected = f"{currency.strip().upper()}TWD"
    if fx.pair.strip().upper() != expected:
        return None, FX_PAIR_MISMATCH_NOTE.format(
            currency=currency, expected=expected, pair=fx.pair
        )
    if fx.rate is None or fx.rate <= 0.0:
        return None, FX_UNAVAILABLE_NOTE.format(
            currency=currency,
            pair=fx.pair,
            status=fx.status.value,
            source=fx.source,
            as_of=fx.as_of or "未知",
        )
    return fx.rate, FX_APPLIED_NOTE.format(
        pair=fx.pair,
        rate=f"{fx.rate:g}",
        status=fx.status.value,
        source=fx.source,
        as_of=fx.as_of or "未知",
    )
