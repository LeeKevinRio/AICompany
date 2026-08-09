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

from app.portfolio.valuation import PositionValuator, Valuation
from app.positions.models import Currency, InstrumentType, Market, Position
from app.positions.store import PositionStore


class Totals(BaseModel):
    """Book-level totals in TWD, summed over the ``ok`` positions only."""

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


class PortfolioSummary(BaseModel):
    """The full ``GET /api/portfolio/summary`` payload."""

    model_config = ConfigDict(frozen=True)

    as_of: str
    totals: Totals
    positions: list[SummaryPosition]


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

    for position in positions:
        valued = valuator.value_position(position)
        summary_positions.append(
            _to_summary_position(position, valued.valuation, valued.market_value_twd)
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
    return PortfolioSummary(as_of=as_of, totals=totals, positions=summary_positions)


def _totals_status(*, total: int, ok: int) -> Literal["complete", "partial", "no_data"]:
    if ok == 0:
        return "no_data"
    if ok == total:
        return "complete"
    return "partial"


def _to_summary_position(
    position: Position, valuation: Valuation, market_value_twd: Decimal | None
) -> SummaryPosition:
    return SummaryPosition(
        id=position.id,
        symbol=position.symbol,
        market=position.market,
        quantity=position.quantity,
        avg_cost=position.avg_cost,
        currency=position.currency,
        instrument_type=position.instrument_type,
        opened_at=(
            position.opened_at.isoformat() if position.opened_at is not None else None
        ),
        sector=position.sector,
        note=position.note,
        valuation=valuation,
        market_value_twd=market_value_twd,
    )
