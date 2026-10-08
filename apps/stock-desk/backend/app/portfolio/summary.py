"""Assemble the portfolio summary response from stored positions.

Aggregation rule: ``totals`` sums only positions whose valuation is ``ok``
(every input available). ``status`` reflects coverage honestly --

    complete -- every position valued ok
    partial  -- some valued ok, some insufficient (totals cover the ok ones)
    no_data  -- nothing could be valued (or there are no positions)

so a partial total is never silently presented as if it were the whole book.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from app.data.interface import DataStatus
from app.portfolio.price_change import ChangeScreen, PriceChange
from app.portfolio.valuation import ChangeMode, PositionValuator, Valuation
from app.positions.models import Currency, InstrumentType, Market, Position
from app.positions.store import PositionStore

logger = logging.getLogger(__name__)

#: Closes ``fx_disclosures`` when at least one ``ok`` position's open-date rate
#: (F0, behind the cost and the FX contribution) and current rate (F1) carry two
#: different source ids (task RK-5, R5-8 / RK5-R2): the gap between the two
#: sources' measures is then part of the FX contribution and of the unrealized
#: P&L. Compared by id, not by sentence (S-1). Always the last item, at most once;
#: never a source's standing disclosure (R5-11: not in ``fx_notes``), and never
#: on the advice card or a push (W5-T7).
#: 風控核可文案,修改須重新送審(2026-10-08)
#: ``work/reviews/2026-10-08-W-RK4-1-W-RK5-1逐字審與X-11-X-12核對-風控審查.md`` (W-RK5-1)
FX_OPEN_MIXED_SOURCES_NOTE: Final = (
    "至少一筆持倉的買入日匯率與目前匯率來自不同來源，"
    "兩個來源的口徑差會算進「匯率貢獻」，因此也會算進「未實現損益」。"
)


class Totals(BaseModel):
    """Book-level totals in TWD, summed over the ``ok`` positions only.

    ``status`` states *coverage* -- how many positions were valued -- and
    nothing about freshness: a ``complete`` book valued from the local cache
    (ADR-0010 D-1) is still ``complete``. How new the prices are travels on
    each position's ``valuation.price.data_status`` and, on the advice card,
    on the standing cache-only note (風控 2026-09-18 D-2).
    """

    model_config = ConfigDict(frozen=True)

    cost_twd: Decimal
    market_value_twd: Decimal
    unrealized_pnl_twd: Decimal
    asset_contribution_twd: Decimal
    fx_contribution_twd: Decimal
    status: Literal["complete", "partial", "no_data"]


class SummaryPosition(BaseModel):
    """One position echoed back with its valuation attached."""

    model_config = ConfigDict(frozen=True)

    id: int
    symbol: str
    market: Market
    quantity: Decimal
    avg_cost: Decimal
    currency: Currency
    instrument_type: InstrumentType
    #: ``None`` when the user did not state an open date.
    opened_at: str | None
    #: TWSE industry category, or ``None`` when the user did not state one
    #: (FR-12). Never inferred from the symbol.
    sector: str | None
    note: str | None
    valuation: Valuation
    #: This position's own contribution to ``totals.market_value_twd``, or
    #: ``None`` when it could not be valued. Carried per position (rather than
    #: only in the totals) so book-level slices -- the sector cap's numerator,
    #: today -- are summed from the same TWD figures the totals use instead of
    #: re-deriving them from a price in the instrument's own currency.
    market_value_twd: Decimal | None
    #: The matching contribution to ``totals.cost_twd`` (converted at the FX rate
    #: of the open date, as the valuator defines it), or ``None`` on the same
    #: terms. It travels beside ``market_value_twd`` because the two are only
    #: comparable to each other in the same currency: a slice that rolls up one
    #: in TWD and the other in the instrument's own currency would report a
    #: return that is really an exchange rate.
    cost_twd: Decimal | None
    #: Day-over-day change of ``valuation.price`` (ADR-0016). ``None`` whenever
    #: it cannot be stated truthfully -- with no reason attached (K-6) -- and on
    #: every row of a summary built without a ``ChangeScreen`` (D-3, F8). A
    #: display column only: nothing downstream may read it (K-4).
    change: PriceChange | None = None


class PortfolioSummary(BaseModel):
    """The full ``GET /api/portfolio/summary`` payload."""

    model_config = ConfigDict(frozen=True)

    as_of: str
    totals: Totals
    positions: list[SummaryPosition]
    #: The standing disclosure of every FX source whose rate went into this
    #: book's TWD figures (ADR-0011; 風控 2026-09-19 條件 (1)): shown beside the
    #: converted totals, in first-seen order, each sentence once. Read from the
    #: ``ok`` positions only (task RK-5, O-5), both rates of each (R5-8), and
    #: closed by :data:`FX_OPEN_MIXED_SOURCES_NOTE` when the two rates of one of
    #: them come from two sources.
    fx_disclosures: list[str] = []
    #: Which change bases this book's rows may carry (ADR-0016 D-8), fixed by
    #: how the valuator was built. ``close_only`` guarantees no
    #: ``intraday_quote`` price and no ``intraday`` change basis in the payload.
    change_mode: ChangeMode = "close_only"


def fx_disclosures_for(valuations: list[Valuation]) -> list[str]:
    """Unique ``source_note`` of every FX rate actually used, in first-seen order.

    Only an ``ok`` valuation put its rates into a figure; an unvalued position's
    rates were looked up but multiplied into nothing, so their sources are not
    described (task RK-5, O-5 / R5-3). Each ``ok`` position adds its ``fx_now``
    sentence, then its ``fx_open`` sentence (R5-8), each sentence once. If any
    of them took its two rates from two source ids, the list ends with
    :data:`FX_OPEN_MIXED_SOURCES_NOTE`, once (RK5-R2).
    """
    seen: list[str] = []
    mixed = False
    for valuation in valuations:
        if valuation.status != "ok":
            continue
        for info in (valuation.fx, valuation.fx_open):
            if info is None or info.data_status is DataStatus.UNAVAILABLE or not info.source_note:
                continue
            if info.source_note not in seen:
                seen.append(info.source_note)
        mixed = mixed or _sources_differ(valuation)
    if mixed:
        seen.append(FX_OPEN_MIXED_SOURCES_NOTE)
    return seen


def _sources_differ(valuation: Valuation) -> bool:
    """Whether an ``ok`` valuation's two rates carry two source ids (RK5-R2, S-1).

    The one definition of "mixed" behind both :data:`FX_OPEN_MIXED_SOURCES_NOTE`
    and the R5-4 log line. A row that is not ``ok`` -- the X-3c mismatched row,
    whose rates are both ``None``, included -- never counts.
    """
    now, open_ = valuation.fx, valuation.fx_open
    if valuation.status != "ok" or now is None or open_ is None:
        return False
    return now.source != open_.source


def _log_mixed_fx_sources(valuations: list[Valuation]) -> None:
    """Log each ``ok`` position whose two rates come from two source ids (task RK-5, R5-4).

    Observability only: the FX contribution of such a position also carries
    the gap between the two sources' measures. One line per
    ``(pair, now source, open source)`` per call, carrying the first such
    position's rate dates; pair, source ids and dates only -- no symbol,
    position id, amount, quantity or rate -- and never forwarded to a push.
    """
    logged: set[tuple[str, str, str]] = set()
    for valuation in valuations:
        if not _sources_differ(valuation):
            continue
        now, open_ = valuation.fx, valuation.fx_open
        # Both present once _sources_differ holds; guarded for the type checker.
        assert now is not None and open_ is not None
        combination = (now.pair, now.source, open_.source)
        if combination in logged:
            continue
        logged.add(combination)
        logger.warning(
            "fx_now and fx_open sources differ within one book: pair=%s now_source=%s "
            "now_as_of=%s open_source=%s open_as_of=%s",
            now.pair,
            now.source,
            now.as_of,
            open_.source,
            open_.as_of,
        )


def build_summary(
    store: PositionStore,
    valuator: PositionValuator,
    *,
    change_screen: ChangeScreen | None = None,
) -> PortfolioSummary:
    """Value every stored position and roll the ``ok`` ones up into totals.

    ``change_screen`` is injected by ``GET /api/portfolio/summary`` alone
    (ADR-0016 D-3); without it every row's ``change`` is ``None`` (F8).
    """
    as_of = datetime.now(UTC).isoformat()
    positions = store.list_all()

    summary_positions: list[SummaryPosition] = []
    cost = Decimal(0)
    market_value = Decimal(0)
    asset = Decimal(0)
    fx = Decimal(0)
    ok_count = 0

    # One pass per book (ADR-0010 D-2): repeated FX lookups are answered once.
    valuations = valuator.value_all(positions)
    rows = list(zip(positions, valuations, strict=True))
    changes: list[PriceChange | None] = (
        change_screen.screen(rows) if change_screen is not None else [None] * len(rows)
    )
    for (position, valued), change in zip(rows, changes, strict=True):
        summary_positions.append(
            _to_summary_position(
                position, valued.valuation, valued.market_value_twd, valued.cost_twd, change
            )
        )
        if valued.valuation.status == "ok":
            ok_count += 1
            # Present when status is ok; guarded for the type checker.
            assert valued.cost_twd is not None
            assert valued.market_value_twd is not None
            assert valued.valuation.asset_contribution_twd is not None
            assert valued.valuation.fx_contribution_twd is not None
            cost += valued.cost_twd
            market_value += valued.market_value_twd
            asset += valued.valuation.asset_contribution_twd
            fx += valued.valuation.fx_contribution_twd

    totals = Totals(
        cost_twd=cost,
        market_value_twd=market_value,
        unrealized_pnl_twd=market_value - cost,
        asset_contribution_twd=asset,
        fx_contribution_twd=fx,
        status=_totals_status(total=len(positions), ok=ok_count),
    )
    valued_rows = [item.valuation for item in summary_positions]
    _log_mixed_fx_sources(valued_rows)
    return PortfolioSummary(
        as_of=as_of,
        totals=totals,
        positions=summary_positions,
        fx_disclosures=fx_disclosures_for(valued_rows),
        change_mode=valuator.change_mode,
    )


def _totals_status(*, total: int, ok: int) -> Literal["complete", "partial", "no_data"]:
    if ok == 0:
        return "no_data"
    if ok == total:
        return "complete"
    return "partial"


def _to_summary_position(
    position: Position,
    valuation: Valuation,
    market_value_twd: Decimal | None,
    cost_twd: Decimal | None,
    change: PriceChange | None = None,
) -> SummaryPosition:
    return SummaryPosition(
        id=position.id,
        symbol=position.symbol,
        market=position.market,
        quantity=position.quantity,
        avg_cost=position.avg_cost,
        currency=position.currency,
        instrument_type=position.instrument_type,
        opened_at=(position.opened_at.isoformat() if position.opened_at is not None else None),
        sector=position.sector,
        note=position.note,
        valuation=valuation,
        market_value_twd=market_value_twd,
        cost_twd=cost_twd,
        change=change,
    )
