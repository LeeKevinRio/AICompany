"""排程台 endpoints: today's directive table and the emergency exit.

``GET /api/playbook/today`` returns the three blocks the MVP promises -- 模式,
今日指令表, 部位快照 -- each line carrying its rule id, the measurement that
fired it, and the 依據資料日 / 預定執行日 / 參考價 stamp CEO 裁決七 requires.

``POST /api/playbook/settle`` closes the loop CEO 裁決七 opened: yesterday's
lines are stamped against the 預定執行日 opening price and the book moves. It is
idempotent, and ``GET /today`` runs it first so the table is never computed from
a book that is a day behind.

``GET /api/playbook/rule-set`` and ``POST /api/playbook/confirm-rules`` are the
two halves of the one action that lifts the 歸屬語情境 1 block (風控 R2): the GET
states the thresholds of the parameter version in force and whether the user has
adopted them, and the POST records the adoption together with the opening
capital. The POST body carries a capital figure and nothing else -- the rule set
it confirms is the one already in force, so confirmation can never smuggle a
threshold change past 鐵律④.

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

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.common import now_iso
from app.api.deps import get_playbook_service
from app.playbook import wording
from app.playbook.models import (
    BatchSnapshot,
    Directive,
    ExitConfirm,
    FastMarketState,
    PlaybookEvaluation,
    RuleParams,
    RuleSetStatus,
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


class RuleTextItem(BaseModel):
    """One rule's restatement, rendered with the thresholds in force.

    The text is :func:`app.playbook.wording.rule_text` output, so the client
    shows the risk-compliance-approved sentence with this version's numbers
    already in it and never composes a summary of its own.
    """

    model_config = ConfigDict(frozen=True)

    rule_id: str
    text: str


class RuleParamItem(BaseModel):
    """One threshold of the parameter version in force.

    ``field`` is the :class:`RuleParams` field name verbatim -- an identifier,
    not a label. Naming each threshold in prose would invent user-facing wording
    nobody approved, and an identifier keeps every row traceable to the field the
    engine actually reads.
    """

    model_config = ConfigDict(frozen=True)

    field: str
    value: str


class RuleSetResponse(BaseModel):
    """``GET /rule-set`` and ``POST /confirm-rules``: the same picture either way.

    Both endpoints answer with the state *after* they ran, so a client never has
    to guess what a confirmation changed.
    """

    model_config = ConfigDict(frozen=True)

    #: 風控 R2 authorship record. ``False`` is the 歸屬語情境 1 block.
    user_authored: bool
    #: The version the authorship record names; ``None`` while unauthored -- a
    #: system default's version number is not the user's rule set version.
    rules_version: int | None
    #: 生效日 of the stored row in force; ``None`` when no row answers.
    rules_effective_date: str | None
    #: 風控 R2 常駐歸屬語, or the 情境 1 blocking sentence, rendered server-side.
    attribution: str
    rules: list[RuleTextItem]
    params: list[RuleParamItem]
    #: ``deploy_ratio`` of the version in force, written the way the approved
    #: 資金用途句 shows it: the percentage **with its ``%`` sign** (``"70%"``),
    #: rendered here so the confirmation screen substitutes one backend string
    #: and never scales a ratio or appends a unit of its own (五輪定稿 ④).
    deploy_ratio_pct: str
    #: The recorded capital and its provenance (CEO 裁決 D-2).
    cash: str
    total_deploy: str
    total_deploy_set_at: str | None
    total_deploy_source: str | None
    as_of: str


class ConfirmRulesRequest(BaseModel):
    """The one figure a confirmation carries.

    No threshold may be sent: the set being confirmed is the one already in
    force (see the endpoint). ``source`` is not accepted either -- the provenance
    of this write is 「使用者確認」 by construction, and a client-supplied source
    could claim to be anything.
    """

    model_config = ConfigDict(frozen=True)

    #: 資本額 in TWD, the cash pool the rule set starts from. Must be positive:
    #: a zero or negative capital is not a book this rule set can act on.
    capital: Decimal = Field(gt=0)


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
    #: 生效日 of the rule version in force; ``None`` when no stored row answers,
    #: which is what makes ``page_summary`` take its 讀取失敗 branch.
    rules_effective_date: str | None
    #: §6 頁面免責句, three sentences in a fixed order (四輪收斂裁決 題 11),
    #: rendered server-side so the page cannot compose or shorten them.
    page_summary: list[str]
    directives: list[DirectiveLine]
    snapshot: list[BatchSnapshot]
    warnings: list[str]
    #: 題 12 完整性旗標 -- see :attr:`PlaybookEvaluation.rules_fully_evaluated`.
    rules_fully_evaluated: bool
    #: The sentence an empty ledger gets **only** when the flag above is true:
    #: 「今日規則已全數評估，無任何規則命中，未產生指令。」 ``None`` on every
    #: other day, so a client that renders it whenever it is present cannot
    #: claim a completeness the evaluation did not have.
    no_directive_note: str | None
    #: 風控 R2 常駐歸屬語, or the 情境 1 sentence saying no rule set is confirmed.
    attribution: str | None
    #: The T+1 settlement that ran before this evaluation (CEO 裁決七).
    settlement: SettlementResponse | None
    #: The four EMERGENCY_EXIT confirmation sentences with this day's freeze
    #: length and 預計恢復日 already rendered, so the confirmation screen shows
    #: the freeze the user would actually get instead of a mirrored default.
    #: Filled on every service path, including 待確認規則集 (EX-2 出口零摩擦);
    #: ``None`` only on the pure-engine path, which no response reads.
    exit_confirm: ExitConfirm | None
    as_of: str


class EmergencyExitResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    executed_at: str
    execution_date: str
    total_shares: int
    freeze_until: str
    message: str
    #: The mode line for today, recomputed on every response.
    mode_reason: str
    #: EMERGENCY_EXIT 專用歸屬語; ``None`` when the exit produced no line.
    attribution: str | None
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


#: ``RuleParams`` fields that are provenance rather than thresholds. Both have
#: their own response field, where an unreadable or unauthored value is stated as
#: missing; repeating them in the threshold list would put a system default's
#: derived date back on screen as if it were the rule set's own.
_RULE_PARAM_PROVENANCE_FIELDS = frozenset({"version", "effective_date"})


def _rule_param_items(params: RuleParams) -> list[RuleParamItem]:
    """Every threshold of ``params``, in the order the model declares them."""
    return [
        RuleParamItem(field=name, value=str(getattr(params, name)))
        for name in RuleParams.model_fields
        if name not in _RULE_PARAM_PROVENANCE_FIELDS
    ]


def _rule_set_response(status: RuleSetStatus) -> RuleSetResponse:
    authorship = status.authorship
    portfolio = status.portfolio
    return RuleSetResponse(
        user_authored=authorship.user_authored,
        rules_version=authorship.version if authorship.user_authored else None,
        rules_effective_date=(
            None
            if status.rules_effective_date is None
            else status.rules_effective_date.isoformat()
        ),
        attribution=wording.attribution_note(authorship),
        rules=[
            RuleTextItem(rule_id=rule_id, text=wording.rule_text(rule_id, status.params))
            for rule_id in wording.RULE_TEXT
        ],
        params=_rule_param_items(status.params),
        deploy_ratio_pct=wording.ratio_pct(status.params.deploy_ratio) + "%",
        cash=str(portfolio.cash),
        total_deploy=str(portfolio.total_deploy),
        total_deploy_set_at=(
            None
            if portfolio.total_deploy_set_at is None
            else portfolio.total_deploy_set_at.isoformat()
        ),
        total_deploy_source=portfolio.total_deploy_source,
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
        rules_effective_date=(
            None
            if evaluation.rules_effective_date is None
            else evaluation.rules_effective_date.isoformat()
        ),
        page_summary=evaluation.page_summary,
        directives=_lines(evaluation.directives),
        snapshot=evaluation.snapshot,
        warnings=evaluation.warnings,
        rules_fully_evaluated=evaluation.rules_fully_evaluated,
        no_directive_note=(
            wording.NO_RULE_HIT_NOTE
            if evaluation.rules_fully_evaluated and not evaluation.directives
            else None
        ),
        attribution=evaluation.attribution,
        settlement=(
            None
            if evaluation.settlement is None
            else _settlement_response(evaluation.settlement)
        ),
        exit_confirm=evaluation.exit_confirm,
        as_of=now_iso(),
    )


@router.get("/today", response_model=TodayResponse)
def today(service: ServiceDep) -> TodayResponse:
    """Evaluate the latest closing data and return today's directive table.

    Settles yesterday's due lines first (idempotently), so the book the table is
    computed from is the book after T+1 execution rather than the one before it.

    Also carries ``exit_confirm``: the EMERGENCY_EXIT confirmation sentences a
    client needs *before* it can submit the exit. They are here rather than on
    ``POST /emergency-exit`` because that endpoint renders them by executing the
    exit, which is one step too late for a confirmation screen, and because a
    client that mirrors the freeze length states a number that a dated rule
    change has already moved.
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


@router.get("/rule-set", response_model=RuleSetResponse)
def rule_set(service: ServiceDep) -> RuleSetResponse:
    """The rule set in force, its thresholds and whether the user adopted it.

    Read-only: reading the rules is not adopting them (風控 R2). This is what a
    confirmation screen renders *before* it asks, so the thresholds on screen are
    the ones ``GET /today`` would evaluate rather than a client-side copy.
    """
    return _rule_set_response(service.rule_set_status())


@router.post("/confirm-rules", response_model=RuleSetResponse)
def confirm_rules(payload: ConfirmRulesRequest, service: ServiceDep) -> RuleSetResponse:
    """Adopt the rule set in force as the user's own and record the capital.

    The one action that lifts the 歸屬語情境 1 block: until it runs, ``GET
    /today`` produces no rule-driven directive and says so on the response.

    Idempotent, in the two senses that matter. Confirming twice does not add a
    rule version -- the authorship record is written once -- so re-submitting
    cannot walk the rule set forward one version per click. The capital is
    written on every call, because this is also the capital entry point, and each
    write carries its timestamp and ``user_confirmation`` source (CEO 裁決 D-2)
    rather than replacing the previous figure silently.

    Confirms thresholds, never changes them: the body carries a capital figure
    only, so 鐵律④ (a rule change takes effect on the next trading day) cannot be
    routed around by re-confirming with different numbers.
    """
    return _rule_set_response(service.confirm_rules(capital=payload.capital))


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
        mode_reason=result.mode_reason,
        attribution=result.attribution,
        directives=_lines(result.directives),
        warnings=result.warnings,
        as_of=now_iso(),
    )
