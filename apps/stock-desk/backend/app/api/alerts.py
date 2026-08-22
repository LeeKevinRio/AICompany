"""Alert rule CRUD, event listing/acknowledgement, and a manual evaluation tick.

Rules and events are the two halves of M6: a rule is a line the user drew, an
event is a record that the line was crossed at a moment in time. Deleting a rule
therefore does **not** delete its events -- they still happened -- and an event
is acknowledged rather than removed.

Rules are editable in place (FR-1): ``PUT`` replaces every user field and
``PATCH`` changes a subset, both keeping the ``rule_id``. That is what keeps a
rule's history attached to it -- deleting and recreating a rule to change a
threshold would leave its past events pointing at an id that no longer exists.

``POST /api/alerts/evaluate`` runs the same :func:`app.alerts.engine.evaluate_alerts`
tick the scheduler runs, so the UI can force a check without waiting for the
next interval. Webhook delivery is not attempted here: a user-triggered check
should not spray notifications, and the scheduler owns that side effect.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, ValidationError

from app.advice.book import self_reported_net_worth
from app.advice.limits import RiskBudget, SelfReportedNetWorth
from app.alerts.engine import (
    EvaluationResult,
    SnapshotLoader,
    SymbolSnapshot,
    evaluate_alerts,
)
from app.alerts.models import AlertEvent, AlertRule, AlertRuleInput, AlertRulePatch
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api.common import now_iso
from app.api.deps import (
    get_alert_store,
    get_fx_provider,
    get_kelly_input_store,
    get_market_resolver,
    get_position_store,
    get_settings_store,
    get_valuator,
)
from app.api.kelly import kelly_inputs_for
from app.data.providers.fx import FxRateProvider
from app.kelly.store import KellyInputStore
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
FxProviderDep = Annotated[FxRateProvider, Depends(get_fx_provider)]
KellyStoreDep = Annotated[KellyInputStore, Depends(get_kelly_input_store)]


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


@router.put("/{rule_id}", response_model=AlertRule)
def replace_rule(rule_id: int, body: AlertRuleInput, store: AlertStoreDep) -> AlertRule:
    """Replace every user field of one rule, keeping its id (FR-1).

    A full replacement, validated exactly like a ``POST``: switching a rule's
    ``type`` therefore has to bring the matching ``params`` document with it,
    and the old type's parameters cannot survive the switch because ``params``
    is stored as one document rather than a column per type (AC-1.5).
    """
    updated = store.update_rule(rule_id, body)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的警示規則"
        )
    return updated


@router.patch("/{rule_id}", response_model=AlertRule)
def patch_rule(rule_id: int, body: AlertRulePatch, store: AlertStoreDep) -> AlertRule:
    """Change some fields of one rule, leaving the rest as they are (AC-1.2).

    The merged rule is validated as a whole before anything is written, so a
    patch that would produce an impossible rule (a threshold on a rule that is
    no longer a price rule, a negative threshold, ...) is a 422 and the stored
    rule is left untouched -- never partially applied (AC-1.3).
    """
    current = store.get_rule(rule_id)
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的警示規則"
        )
    try:
        merged = body.apply_to(current)
    except ValidationError as exc:
        # Raised while merging, i.e. outside FastAPI's own body validation, so
        # it has to be turned into the same 422 the ``POST`` path would give.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_validation_detail(exc),
        ) from exc
    updated = store.update_rule(rule_id, merged)
    if updated is None:  # pragma: no cover - the rule was read a moment ago
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的警示規則"
        )
    return updated


def _validation_detail(exc: ValidationError) -> list[dict[str, object]]:
    """The failing fields and their Traditional Chinese reasons, as FastAPI shapes them."""
    return [
        {"loc": ["body", *(str(part) for part in error["loc"])], "msg": error["msg"]}
        for error in exc.errors()
    ]


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
    fx_provider: FxProviderDep,
    kelly_store: KellyStoreDep,
) -> EvaluationResponse:
    settings = settings_store.load()
    result = evaluate_alerts(
        store,
        _loader(
            resolver,
            position_store,
            valuator,
            settings.risk_budget,
            fx_provider,
            self_reported_net_worth(
                settings.net_worth.total_net_worth_twd, settings.net_worth.updated_at
            ),
            kelly_store,
        ),
        cooldown_minutes=settings.alerts.cooldown_minutes,
    )
    return _evaluation_response(result)


def _loader(
    resolver: MarketDataResolver,
    position_store: PositionStore,
    valuator: PositionValuator,
    budget: RiskBudget,
    fx_provider: FxRateProvider,
    net_worth: SelfReportedNetWorth | None,
    kelly_store: KellyInputStore,
) -> SnapshotLoader:
    def load(symbol: str, market: Market) -> SymbolSnapshot:
        return build_snapshot(
            symbol,
            market,
            resolver=resolver,
            store=position_store,
            valuator=valuator,
            budget=budget,
            fx_provider=fx_provider,
            net_worth=net_worth,
            # Per rule, not per book: an alert watches one symbol, so cap 5 is
            # evaluated against that symbol's own pair (D-1/D-7).
            kelly=kelly_inputs_for(kelly_store, symbol, market),
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
