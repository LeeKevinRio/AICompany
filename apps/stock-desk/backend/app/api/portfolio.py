"""Portfolio summary endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_position_store, get_valuator
from app.portfolio.summary import PortfolioSummary, build_summary
from app.portfolio.valuation import PositionValuator
from app.positions.store import PositionStore

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

StoreDep = Annotated[PositionStore, Depends(get_position_store)]
ValuatorDep = Annotated[PositionValuator, Depends(get_valuator)]


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(store: StoreDep, valuator: ValuatorDep) -> PortfolioSummary:
    return build_summary(store, valuator)
