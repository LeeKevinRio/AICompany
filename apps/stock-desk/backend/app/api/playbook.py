"""排程台 endpoints: today's directive table and the emergency exit.

``GET /api/playbook/today`` returns the three blocks the MVP promises -- 模式,
今日指令表, 部位快照 -- each line carrying its rule id, the measurement that
fired it, and the 依據資料日 / 預定執行日 / 參考價 stamp CEO 裁決七 requires.

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
)
from app.playbook.service import PlaybookService

router = APIRouter(prefix="/api/playbook", tags=["playbook"])

ServiceDep = Annotated[PlaybookService, Depends(get_playbook_service)]


class DirectiveLine(BaseModel):
    """A directive plus its rendered one-line form, so the UI cannot re-word it."""

    model_config = ConfigDict(frozen=True)

    line: str
    directive: Directive


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
        as_of=now_iso(),
    )


@router.get("/today", response_model=TodayResponse)
def today(service: ServiceDep) -> TodayResponse:
    """Evaluate the latest closing data and return today's directive table."""
    return _to_response(service.evaluate_today())


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
