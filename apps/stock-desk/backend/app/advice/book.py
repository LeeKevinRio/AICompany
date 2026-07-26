"""Build a :class:`PortfolioContext` from stored positions and their valuations.

This is the adapter between the *bookkeeping* layer (``app/positions`` +
``app/portfolio``, Decimal money, per-position valuations that may individually
be ``insufficient_data``) and the *risk-budget* layer (``app/advice/limits``,
float ratios). It exists so both the advice endpoint and the alert engine build
the same context from the same rules instead of each inventing its own.

Three honesty rules govern what is filled in:

1. **Only ``ok`` valuations are aggregated.** A position whose price could not
   be fetched contributes nothing to the book total and is listed in
   ``notes``, so a partial book is never presented as a whole one.
2. **Equity is the valued book, and says so.** There is no cash or account
   balance anywhere in this product, so ``total_equity_twd`` is the market
   value of the successfully valued positions. That is an assumption, and it is
   stated in ``notes`` rather than left for the reader to infer.
3. **Gross exposure is left unset.** Without cash and margin balances the
   book's gross exposure is not computable; supplying the equity figure again
   would force the ratio to exactly 100% and turn an unknown into a permanent
   "violated". The cap therefore reports ``not_evaluable``, which is what it is.

``sector`` and the Kelly inputs stay ``None`` for the same reason: no source
produces them yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.advice.limits import PortfolioContext
from app.portfolio.summary import PortfolioSummary, SummaryPosition
from app.positions.models import Market

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


@dataclass(frozen=True)
class BookContext:
    """A :class:`PortfolioContext` plus what had to be assumed or left out."""

    context: PortfolioContext
    held: bool
    position_ids: list[int] = field(default_factory=list)
    #: Currency of the matched holding(s), or ``None`` for a candidate.
    currency: str | None = None
    notes: list[str] = field(default_factory=list)


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


def _position_rollup(
    positions: list[SummaryPosition],
) -> tuple[float, float | None, float, int]:
    """Roll up the ``ok``-valued rows: ``(market value, cost, quantity, skipped)``.

    ``cost`` is ``None`` when no row carried one, so the unrealized-P&L ratio
    reports "no cost" instead of a zero that would read as a -100% loss.
    """
    market_value = Decimal(0)
    cost = Decimal(0)
    quantity = Decimal(0)
    has_cost = False
    skipped = 0
    for position in positions:
        valuation = position.valuation
        if valuation.status != "ok" or valuation.price is None:
            skipped += 1
            continue
        market_value += position.quantity * valuation.price.value
        cost += position.quantity * position.avg_cost
        has_cost = True
        quantity += position.quantity
    return (
        float(market_value),
        float(cost) if has_cost else None,
        float(quantity),
        skipped,
    )


def build_book_context(
    summary: PortfolioSummary,
    *,
    symbol: str,
    market: Market | None = None,
    close: float | None = None,
    currency: str | None = None,
    atr: float | None = None,
) -> BookContext:
    """Assemble the risk-budget context for ``symbol`` against the whole book.

    ``close`` is the latest close **in the instrument's own currency** (the unit
    the caps compare); pass ``None`` when no price is available and the
    price-dependent caps will report ``not_evaluable`` instead of guessing.
    A symbol with no holding yields a *candidate* context
    (``position_market_value_twd=0``, ``quantity=0``) so a card can still be
    produced for something the user does not own yet.
    """
    notes: list[str] = [EQUITY_BASIS_NOTE, GROSS_EXPOSURE_NOTE]
    equity, valued_count, total_count = _book_equity(summary)
    if total_count and valued_count < total_count:
        notes.append(
            f"組合中有 {total_count - valued_count} 筆部位無法估值（缺價格或匯率），"
            "未計入總資產；比率會因此偏高。"
        )

    matched = _matching(summary, symbol, market)
    market_value, cost, quantity, skipped = _position_rollup(matched)
    if skipped:
        notes.append(
            f"此標的有 {skipped} 筆持倉無法估值，未計入本標的的部位市值與成本。"
        )

    currencies = sorted({position.currency for position in matched})
    holding_currency = currencies[0] if len(currencies) == 1 else None
    mixed_currencies = len(currencies) > 1
    if mixed_currencies:
        notes.append("此標的的持倉橫跨多種計價幣別，無法決定單一匯率，價格類上限不計算。")

    if mixed_currencies:
        fx = None
    else:
        fx = _resolve_fx(holding_currency if matched else currency, notes)

    context = PortfolioContext(
        symbol=symbol,
        total_equity_twd=equity,
        position_market_value_twd=market_value,
        position_cost_twd=cost,
        # Deliberately absent -- see the module docstring, rule 3.
        gross_exposure_twd=None,
        quantity=quantity,
        close=close if fx is not None else None,
        fx_to_twd=fx if fx is not None else 1.0,
        atr=atr,
    )
    return BookContext(
        context=context,
        held=bool(matched),
        position_ids=[position.id for position in matched],
        currency=holding_currency if matched else currency,
        notes=notes,
    )


def _resolve_fx(currency: str | None, notes: list[str]) -> float | None:
    """Instrument currency -> TWD, or ``None`` when it cannot be established.

    Only TWD is resolvable today: there is no US price adapter, so a non-TWD
    holding never reaches this module with a usable price anyway, and inventing
    a rate of 1.0 would silently mis-scale every cap.
    """
    if currency is None or currency == "TWD":
        return 1.0
    notes.append(
        f"計價幣別為 {currency}，目前沒有可用的匯率換算來源，"
        "價格與 ATR 相關的上限不計算，不以 1.0 匯率代入。"
    )
    return None
