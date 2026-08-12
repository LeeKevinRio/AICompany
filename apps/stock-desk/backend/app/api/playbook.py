"""排程台 endpoints: today's directive table and the emergency exit.

``GET /api/playbook/today`` returns the three blocks the MVP promises -- 模式,
今日指令表, 部位快照 -- each line carrying its rule id, the measurement that
fired it, and the 依據資料日 / 預定執行日 / 參考價 stamp CEO 裁決七 requires.

``POST /api/playbook/settle`` closes the loop CEO 裁決七 opened: yesterday's
lines are stamped against the 預定執行日 opening price and the book moves. It is
idempotent, and ``GET /today`` runs it first so the table is never computed from
a book that is a day behind.

``POST /api/playbook/rebalance`` is the quarterly TOTAL_DEPLOY recomputation
(CEO 裁決一), triggered by hand because the user decides which day ends the
quarter. It writes the new locked value and reports an overshoot rather than
trading it away.

``POST /api/playbook/emergency-exit`` is the escape hatch (CEO 裁決六): it takes
no body at all, because it is all-or-nothing by design -- naming a symbol would
turn it into a discretionary trade, which is precisely what the rule set exists
to prevent. It works in every mode, and the 20-trading-day freeze that follows
is part of the same response rather than a surprise the next day.

Neither endpoint places an order anywhere: this product does not connect to a
broker (風控 R10, R15).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.common import now_iso
from app.api.deps import get_playbook_service
from app.playbook import wording
from app.playbook.models import (
    BatchSnapshot,
    Directive,
    FastMarketState,
    PlaybookEvaluation,
    SettlementResult,
)
from app.playbook.service import PlaybookService

router = APIRouter(prefix="/api/playbook", tags=["playbook"])

ServiceDep = Annotated[PlaybookService, Depends(get_playbook_service)]


class DirectiveLine(BaseModel):
    """A directive plus its rendered one-line form, so the UI cannot re-word it."""

    model_config = ConfigDict(frozen=True)

    line: str
    directive: Directive


class SettledLineResponse(BaseModel):
    """One settled line: what it was, what happened to it, at which open."""

    model_config = ConfigDict(frozen=True)

    directive_id: int
    line: str
    status: str
    open_price: str
    directive: Directive


class UnsettledLineResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    directive_id: int
    line: str
    reason: str
    directive: Directive


class SettlementResponse(BaseModel):
    """``POST /api/playbook/settle`` and the ``settlement`` block of ``/today``."""

    model_config = ConfigDict(frozen=True)

    settled_on: str
    executed: int
    missed: int
    settled: list[SettledLineResponse]
    unsettled: list[UnsettledLineResponse]
    warnings: list[str]
    as_of: str


class RebalanceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    executed_at: str
    status: str
    total_assets: str | None
    previous_total_deploy: str
    new_total_deploy: str | None
    deployed_value: str | None
    overshoot: str | None
    message: str
    directives: list[DirectiveLine]
    warnings: list[str]
    as_of: str


class TodayResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_date: str
    execution_date: str
    mode: str
    mode_label: str
    mode_reason: str
    is_schedule_day: bool
    fast_market: FastMarketState
    rules_version: int
    directives: list[DirectiveLine]
    snapshot: list[BatchSnapshot]
    warnings: list[str]
    #: The T+1 settlement that ran before this evaluation (CEO 裁決七).
    settlement: SettlementResponse | None
    as_of: str


class EmergencyExitResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    executed_at: str
    execution_date: str
    total_shares: int
    freeze_until: str
    message: str
    directives: list[DirectiveLine]
    warnings: list[str]
    as_of: str


def _lines(directives: list[Directive]) -> list[DirectiveLine]:
    return [
        DirectiveLine(line=wording.directive_line(directive), directive=directive)
        for directive in directives
    ]


def _settlement_response(result: SettlementResult) -> SettlementResponse:
    return SettlementResponse(
        settled_on=result.settled_on.isoformat(),
        executed=result.executed,
        missed=result.missed,
        settled=[
            SettledLineResponse(
                directive_id=item.directive_id,
                line=wording.directive_line(item.directive),
                status=item.directive.status,
                open_price=str(item.open_price),
                directive=item.directive,
            )
            for item in result.settled
        ],
        unsettled=[
            UnsettledLineResponse(
                directive_id=item.directive_id,
                line=wording.directive_line(item.directive),
                reason=item.reason,
                directive=item.directive,
            )
            for item in result.unsettled
        ],
        warnings=result.warnings,
        as_of=now_iso(),
    )


def _to_response(evaluation: PlaybookEvaluation) -> TodayResponse:
    return TodayResponse(
        data_date=evaluation.data_date.isoformat(),
        execution_date=evaluation.execution_date.isoformat(),
        mode=evaluation.mode,
        mode_label=wording.MODE_LABELS[evaluation.mode],
        mode_reason=evaluation.mode_reason,
        is_schedule_day=evaluation.is_schedule_day,
        fast_market=evaluation.fast_market,
        rules_version=evaluation.rules_version,
        directives=_lines(evaluation.directives),
        snapshot=evaluation.snapshot,
        warnings=evaluation.warnings,
        settlement=(
            None
            if evaluation.settlement is None
            else _settlement_response(evaluation.settlement)
        ),
        as_of=now_iso(),
    )


@router.get("/today", response_model=TodayResponse)
def today(service: ServiceDep) -> TodayResponse:
    """Evaluate the latest closing data and return today's directive table.

    Settles yesterday's due lines first (idempotently), so the book the table is
    computed from is the book after T+1 execution rather than the one before it.
    """
    return _to_response(service.evaluate_today())


@router.post("/settle", response_model=SettlementResponse)
def settle(service: ServiceDep) -> SettlementResponse:
    """Settle every due T+1 line against its 預定執行日 opening price.

    Takes no body: the lines to settle are the ones already in the log, and the
    price is the market's, not the caller's. Safe to call repeatedly -- a line
    that was already settled is not settled again.
    """
    return _settlement_response(service.settle_pending())


@router.post("/rebalance", response_model=RebalanceResponse)
def rebalance(service: ServiceDep) -> RebalanceResponse:
    """季末 REBALANCE: recompute TOTAL_DEPLOY from the assets of the day.

    Manual on purpose (CEO 裁決一): the user decides which day closes the
    quarter. An overshoot is reported and logged, never silently absorbed, and
    no order is issued by this endpoint.
    """
    result = service.rebalance()
    return RebalanceResponse(
        executed_at=result.executed_at.isoformat(),
        status=result.status,
        total_assets=None if result.total_assets is None else str(result.total_assets),
        previous_total_deploy=str(result.previous_total_deploy),
        new_total_deploy=(
            None if result.new_total_deploy is None else str(result.new_total_deploy)
        ),
        deployed_value=None if result.deployed_value is None else str(result.deployed_value),
        overshoot=None if result.overshoot is None else str(result.overshoot),
        message=result.message,
        directives=_lines(result.directives),
        warnings=result.warnings,
        as_of=now_iso(),
    )


@router.post("/emergency-exit", response_model=EmergencyExitResponse)
def emergency_exit(service: ServiceDep) -> EmergencyExitResponse:
    """Liquidate every batch and freeze the schedule for 20 trading days."""
    result = service.emergency_exit()
    return EmergencyExitResponse(
        executed_at=result.executed_at.isoformat(),
        execution_date=result.execution_date.isoformat(),
        total_shares=result.total_shares,
        freeze_until=result.freeze_until.isoformat(),
        message=result.message,
        directives=_lines(result.directives),
        warnings=result.warnings,
        as_of=now_iso(),
    )
