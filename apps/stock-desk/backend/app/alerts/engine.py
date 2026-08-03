"""Evaluate alert rules against the live service outputs and raise events.

The engine owns no data access. It is handed a :data:`SnapshotLoader` -- one
call per symbol returning a :class:`SymbolSnapshot` built from the *existing*
services (``MarketDataService`` -> ``compute_signals`` -> ``evaluate_limits``)
-- so the scheduler, the API and the tests all evaluate exactly the same way and
a test can drive any state without a network.

Two rules that keep the output truthful:

* A rule whose inputs are missing is **skipped with a reason**, never evaluated
  as "did not fire". Silence must mean "the line was not crossed", not "we could
  not look", which is the same distinction the signal and advice layers draw.
* An event's ``message`` states the observation and the threshold and stops
  there. No action verb, no suggestion: alerts are measurement, and any advice
  wording belongs to the reviewed advice engine.

Cooldown is applied per rule against the store's last event for that rule, so a
value that sits above its threshold for a week does not produce an event on
every tick.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.advice.context import build_context, describe_field
from app.advice.engine import COMPARISON_OPS
from app.advice.limits import LimitCheck, PortfolioContext
from app.alerts.models import (
    AlertEvent,
    AlertRule,
    PriceThresholdParams,
    RiskLimitParams,
    SignalConditionParams,
)
from app.alerts.store import AlertStore
from app.positions.models import Market


@dataclass(frozen=True)
class SymbolSnapshot:
    """Everything the rule types need about one symbol at one moment.

    Every field is optional in the "could not be produced" sense: ``close`` is
    ``None`` without usable bars, ``signals`` is empty when the signal layer was
    not run, ``limits`` is empty when no risk context could be built. Each rule
    type turns its own missing input into a skip.
    """

    symbol: str
    market: Market
    close: float | None = None
    currency: str | None = None
    signals: Mapping[str, Any] = field(default_factory=dict)
    limits: Sequence[LimitCheck] = ()
    as_of: str | None = None
    #: Why the snapshot is thin, when it is (data status, missing adapter, ...).
    #: Only ever read on a rule that is **skipped**; a fired rule's message does
    #: not include it, which is why the disclosure below has its own field.
    reason: str | None = None
    #: The FX source's standing disclosure (ADR-0005 F-4), set only when a rate
    #: was actually applied to build ``limits``. The risk-cap message quotes
    #: TWD-converted figures, so this sentence has to travel with the *fired*
    #: message -- all the way to Discord/Telegram -- not merely with a skip.
    fx_disclosure: str | None = None


#: Loads the snapshot for one symbol/market. Supplied by the caller.
SnapshotLoader = Callable[[str, Market], SymbolSnapshot]


@dataclass(frozen=True)
class RuleOutcome:
    """What happened to one rule on one tick."""

    rule_id: int
    #: ``fired`` -- an event was written; ``suppressed`` -- it would have fired
    #: but is inside its cooldown; ``quiet`` -- the line was not crossed;
    #: ``skipped`` -- the inputs were not available.
    status: str
    reason: str | None = None
    event: AlertEvent | None = None


@dataclass(frozen=True)
class EvaluationResult:
    """The whole tick: the events raised and what happened to every rule."""

    as_of: str
    evaluated: int
    events: list[AlertEvent]
    outcomes: list[RuleOutcome]


def _fmt(value: float) -> str:
    """Render a number for a message without exponent noise or trailing zeros."""
    return f"{value:,.4f}".rstrip("0").rstrip(".") if value % 1 else f"{value:,.0f}"


def _price_outcome(
    rule: AlertRule, snapshot: SymbolSnapshot, params: PriceThresholdParams
) -> tuple[bool, str, dict[str, float | str | None]]:
    """``(crossed, message, observed)`` for a price threshold rule."""
    close = snapshot.close
    assert close is not None  # the caller skips a snapshot without a price
    above = rule.type == "price_above"
    crossed = close > params.threshold if above else close < params.threshold
    direction = "高於" if above else "低於"
    unit = f" {snapshot.currency}" if snapshot.currency else ""
    message = (
        f"{rule.symbol} 最新收盤價 {_fmt(close)}{unit}，"
        f"{direction}設定的門檻 {_fmt(params.threshold)}{unit}。"
    )
    observed: dict[str, float | str | None] = {
        "close": close,
        "threshold": params.threshold,
        "currency": snapshot.currency,
        "bar_as_of": snapshot.as_of,
    }
    return crossed, message, observed


def _signal_outcome(
    rule: AlertRule, snapshot: SymbolSnapshot, params: SignalConditionParams
) -> tuple[bool, str, dict[str, float | str | None]] | str:
    """``(crossed, message, observed)``, or a skip reason string."""
    comparison = params.condition
    # A ``signal_condition`` alert reads the signal fields only; the two
    # position-derived fields of the vocabulary stay ``None`` and a rule naming
    # one of them is skipped with that field named, as in the advice engine.
    context = build_context(snapshot.signals, PortfolioContext(symbol=rule.symbol))
    left = context.get(comparison.field)
    if left is None:
        return f"缺少輸入欄位：{describe_field(comparison.field)}"
    if comparison.ref is not None:
        right = context.get(comparison.ref)
        if right is None:
            return f"缺少輸入欄位：{describe_field(comparison.ref)}"
        right_label = describe_field(comparison.ref)
    else:
        assert comparison.value is not None  # the schema pins exactly one side
        right = comparison.value
        right_label = _fmt(comparison.value)
    crossed = bool(COMPARISON_OPS[comparison.op](left, right))
    message = (
        f"{rule.symbol} 的 {describe_field(comparison.field)} 目前為 {_fmt(left)}，"
        f"符合設定的條件 {comparison.op} {right_label}。"
    )
    observed: dict[str, float | str | None] = {
        "field": comparison.field,
        "value": left,
        "op": comparison.op,
        "compared_to": right,
        "signals_as_of": snapshot.as_of,
    }
    return crossed, message, observed


def _limit_outcome(
    rule: AlertRule, snapshot: SymbolSnapshot, params: RiskLimitParams
) -> tuple[bool, str, dict[str, float | str | None]] | str:
    """``(crossed, message, observed)``, or a skip reason string."""
    if not snapshot.limits:
        return "沒有可用的風險上限檢查結果（缺少組合估值）。"
    watched = [
        check
        for check in snapshot.limits
        if params.limit_id == "any" or check.id == params.limit_id
    ]
    if not watched:
        return f"風險上限 {params.limit_id} 不在本次檢查結果中。"
    violated = [check for check in watched if check.status == "violated"]
    if not violated:
        # Distinguish "checked and fine" from "could not be checked": a cap that
        # is not_evaluable must not read as a passing cap.
        if all(check.status == "not_evaluable" for check in watched):
            names = "、".join(check.name for check in watched)
            # The snapshot knows *why* the inputs are missing (no FX rate, a
            # degraded data layer); "缺少輸入" alone would leave the reader to
            # guess which of them it was.
            cause = f" {snapshot.reason}" if snapshot.reason else ""
            return f"監看的上限（{names}）缺少輸入，無法判定是否違反。{cause}"
        return False, "", {}
    names = "、".join(f"第 {check.index} 條（{check.name}）" for check in violated)
    details = " ".join(check.detail for check in violated)
    message = f"{rule.symbol} 觸發風險上限：{names}。{details}"
    # Every cap here is measured in TWD, so on a foreign-currency holding every
    # figure in ``details`` passed through the FX rate. ADR-0005 F-4 requires
    # the rate's provenance to be visible wherever it is used, and this message
    # is what the user actually receives (feed, Discord, Telegram).
    if snapshot.fx_disclosure:
        message = f"{message} {snapshot.fx_disclosure}"
    observed: dict[str, float | str | None] = {
        "violated_limit_ids": "、".join(check.id for check in violated),
        "violated_count": float(len(violated)),
    }
    return True, message, observed


def _in_cooldown(
    store: AlertStore, rule: AlertRule, *, now: datetime, cooldown_minutes: int
) -> bool:
    if cooldown_minutes <= 0:
        return False
    last = store.last_triggered_at(rule.id)
    if last is None:
        return False
    return now - last < timedelta(minutes=cooldown_minutes)


def evaluate_alerts(
    store: AlertStore,
    loader: SnapshotLoader,
    *,
    cooldown_minutes: int = 60,
    now: datetime | None = None,
) -> EvaluationResult:
    """Evaluate every enabled rule once and persist the events that fired."""
    moment = now if now is not None else datetime.now(UTC)
    rules = store.list_rules(enabled_only=True)
    outcomes: list[RuleOutcome] = []
    events: list[AlertEvent] = []

    # One snapshot per (symbol, market) is reused by every rule watching it, so
    # ten rules on one symbol cost one data fetch, not ten.
    snapshots: dict[tuple[str, Market], SymbolSnapshot] = {}

    for rule in rules:
        key = (rule.symbol, rule.market)
        if key not in snapshots:
            snapshots[key] = loader(rule.symbol, rule.market)
        snapshot = snapshots[key]

        evaluated = _evaluate_one(rule, snapshot)
        if isinstance(evaluated, str):
            outcomes.append(RuleOutcome(rule_id=rule.id, status="skipped", reason=evaluated))
            continue
        crossed, message, observed = evaluated
        if not crossed:
            outcomes.append(RuleOutcome(rule_id=rule.id, status="quiet"))
            continue
        if _in_cooldown(store, rule, now=moment, cooldown_minutes=cooldown_minutes):
            outcomes.append(
                RuleOutcome(
                    rule_id=rule.id,
                    status="suppressed",
                    reason=f"距離上次觸發不足 {cooldown_minutes} 分鐘，本次不重複發出。",
                )
            )
            continue
        event = store.append_event(
            rule=rule, message=message, observed=observed, triggered_at=moment
        )
        events.append(event)
        outcomes.append(RuleOutcome(rule_id=rule.id, status="fired", event=event))

    return EvaluationResult(
        as_of=moment.isoformat(),
        evaluated=len(rules),
        events=events,
        outcomes=outcomes,
    )


def _evaluate_one(
    rule: AlertRule, snapshot: SymbolSnapshot
) -> tuple[bool, str, dict[str, float | str | None]] | str:
    """Dispatch one rule to its type's evaluator, or return a skip reason."""
    params = rule.params
    if isinstance(params, PriceThresholdParams):
        if snapshot.close is None:
            return snapshot.reason or "沒有可用的最新收盤價。"
        return _price_outcome(rule, snapshot, params)
    if isinstance(params, SignalConditionParams):
        if not snapshot.signals:
            return snapshot.reason or "沒有可用的訊號輸出。"
        return _signal_outcome(rule, snapshot, params)
    return _limit_outcome(rule, snapshot, params)
