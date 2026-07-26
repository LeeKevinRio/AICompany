"""Alert rule CRUD, event listing/acknowledgement, and a manual evaluation tick.

Rules and events are the two halves of M6: a rule is a line the user drew, an
event is a record that the line was crossed at a moment in time. Deleting a rule
therefore does **not** delete its events -- they still happened -- and an event
is acknowledged rather than removed.

``POST /api/alerts/evaluate`` runs the same :func:`app.alerts.engine.evaluate_alerts`
tick the scheduler runs, so the UI can force a check without waiting for the
next interval. Webhook delivery is not attempted here: a user-triggered check
should not spray notifications, and the scheduler owns that side effect.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict

from app.advice.limits import RiskBudget
from app.alerts.engine import (
    EvaluationResult,
    SnapshotLoader,
    SymbolSnapshot,
    evaluate_alerts,
)
from app.alerts.models import AlertEvent, AlertRule, AlertRuleInput
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api.common import now_iso
from app.api.deps import (
    get_alert_store,
    get_market_resolver,
    get_position_store,
    get_settings_store,
    get_valuator,
)
from app.portfolio.valuation import PositionValuator
from app.positions.models import Market
from app.positions.store import PositionStore
from app.services.market import MarketDataResolver
from app.settings.store import SettingsStore

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

AlertStoreDep = Annotated[AlertStore, Depends(get_alert_store)]
ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]
PositionStoreDep = Annotated[PositionStore, Depends(get_position_store)]
ValuatorDep = Annotated[PositionValuator, Depends(get_valuator)]
SettingsDep = Annotated[SettingsStore, Depends(get_settings_store)]


class AlertRuleListResponse(BaseModel):
    """Envelope for the rule list, carrying an ``as_of`` timestamp."""

    model_config = ConfigDict(frozen=True)

    items: list[AlertRule]
    as_of: str


class AlertEventListResponse(BaseModel):
    """Envelope for the event list, carrying an ``as_of`` timestamp."""

    model_config = ConfigDict(frozen=True)

    items: list[AlertEvent]
    as_of: str


class EvaluationResponse(BaseModel):
    """The result of one evaluation tick."""

    model_config = ConfigDict(frozen=True)

    evaluated: int
    fired: int
    events: list[AlertEvent]
    outcomes: list[dict[str, object]]
    as_of: str


@router.get("", response_model=AlertRuleListResponse)
def list_rules(
    store: AlertStoreDep,
    enabled_only: Annotated[bool, Query(description="只列出啟用中的規則")] = False,
) -> AlertRuleListResponse:
    return AlertRuleListResponse(
        items=store.list_rules(enabled_only=enabled_only), as_of=now_iso()
    )


@router.post("", response_model=AlertRule, status_code=status.HTTP_201_CREATED)
def create_rule(body: AlertRuleInput, store: AlertStoreDep) -> AlertRule:
    return store.create_rule(body)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, store: AlertStoreDep) -> Response:
    if not store.delete_rule(rule_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的警示規則"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/events", response_model=AlertEventListResponse)
def list_events(
    store: AlertStoreDep,
    unacknowledged: Annotated[
        bool | None, Query(description="true 只列未確認、false 只列已確認、省略則全部")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> AlertEventListResponse:
    return AlertEventListResponse(
        items=store.list_events(unacknowledged=unacknowledged, limit=limit),
        as_of=now_iso(),
    )


@router.post("/events/{event_id}/ack", response_model=AlertEvent)
def acknowledge_event(event_id: int, store: AlertStoreDep) -> AlertEvent:
    event = store.acknowledge(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的警示事件"
        )
    return event


@router.post("/evaluate", response_model=EvaluationResponse)
def evaluate_now(
    store: AlertStoreDep,
    resolver: ResolverDep,
    position_store: PositionStoreDep,
    valuator: ValuatorDep,
    settings_store: SettingsDep,
) -> EvaluationResponse:
    settings = settings_store.load()
    result = evaluate_alerts(
        store,
        _loader(resolver, position_store, valuator, settings.risk_budget),
        cooldown_minutes=settings.alerts.cooldown_minutes,
    )
    return _evaluation_response(result)


def _loader(
    resolver: MarketDataResolver,
    position_store: PositionStore,
    valuator: PositionValuator,
    budget: RiskBudget,
) -> SnapshotLoader:
    def load(symbol: str, market: Market) -> SymbolSnapshot:
        return build_snapshot(
            symbol,
            market,
            resolver=resolver,
            store=position_store,
            valuator=valuator,
            budget=budget,
        )

    return load


def _evaluation_response(result: EvaluationResult) -> EvaluationResponse:
    return EvaluationResponse(
        evaluated=result.evaluated,
        fired=len(result.events),
        events=result.events,
        outcomes=[
            {"rule_id": outcome.rule_id, "status": outcome.status, "reason": outcome.reason}
            for outcome in result.outcomes
        ],
        as_of=result.as_of,
    )
