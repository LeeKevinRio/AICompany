"""Assemble the portfolio summary response from stored positions.

Aggregation rule: ``totals`` sums only positions whose valuation is ``ok``
(every input available). ``status`` reflects coverage honestly --

    complete -- every position valued ok
    partial  -- some valued ok, some insufficient (totals cover the ok ones)
    no_data  -- nothing could be valued (or there are no positions)

so a partial total is never silently presented as if it were the whole book.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.data.interface import DataStatus
from app.portfolio.valuation import PositionValuator, Valuation
from app.positions.models import Currency, InstrumentType, Market, Position
from app.positions.store import PositionStore


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


class PortfolioSummary(BaseModel):
    """The full ``GET /api/portfolio/summary`` payload."""

    model_config = ConfigDict(frozen=True)

    as_of: str
    totals: Totals
    positions: list[SummaryPosition]
    #: The standing disclosure of every FX source whose rate went into this
    #: book's TWD figures (ADR-0011; 風控 2026-09-19 條件 (1)): shown beside the
    #: converted totals, in first-seen order, each sentence once.
    fx_disclosures: list[str] = []


def fx_disclosures_for(valuations: list[Valuation]) -> list[str]:
    """Unique ``source_note`` of every FX rate actually used, in first-seen order."""
    seen: list[str] = []
    for valuation in valuations:
        info = valuation.fx
        if info is None or info.data_status is DataStatus.UNAVAILABLE or not info.source_note:
            continue
        if info.source_note not in seen:
            seen.append(info.source_note)
    return seen


def build_summary(store: PositionStore, valuator: PositionValuator) -> PortfolioSummary:
    """Value every stored position and roll the ``ok`` ones up into totals."""
    as_of = datetime.now(UTC).isoformat()
    positions = store.list_all()

    summary_positions: list[SummaryPosition] = []
    cost = Decimal(0)
    market_value = Decimal(0)
    asset = Decimal(0)
    fx = Decimal(0)
    ok_count = 0

    # One pass per book (ADR-0010 D-2): repeated FX lookups are answered once.
    for position, valued in zip(positions, valuator.value_all(positions), strict=True):
        summary_positions.append(
            _to_summary_position(
                position, valued.valuation, valued.market_value_twd, valued.cost_twd
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
    return PortfolioSummary(
        as_of=as_of,
        totals=totals,
        positions=summary_positions,
        fx_disclosures=fx_disclosures_for([item.valuation for item in summary_positions]),
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
    )
