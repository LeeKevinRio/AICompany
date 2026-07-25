"""Evaluate the rule set against one symbol and render an advice card.

The pipeline is deliberately boring and inspectable:

1. Flatten the signal/risk output into the rule vocabulary
   (:func:`app.advice.context.build_context`).
2. Evaluate every rule. A rule whose inputs are not all present is **skipped**
   with the missing fields named -- never treated as "did not match".
3. Sum the matched weights per action, and those per *direction*
   (:data:`ACTION_DIRECTION`). The heaviest direction wins, then the heaviest
   action inside it; ties break towards the more defensive side. Summing by
   direction first keeps a defensive cluster whose weight is split across
   ``reduce`` and ``stop_loss`` from being out-voted by one lighter
   constructive rule. Every action that matched stays on the card with its
   weight and rule ids, so the losing side is visible rather than discarded.
4. Apply the conservative gates, each of which is stated on the card:
   * thin data (fewer than :data:`MIN_COMPLETENESS_FOR_ACTION` of the rules
     evaluable) turns an ``add``, or a hold with no evidence at all, into
     ``insufficient_data``;
   * an ``add`` alongside *any* matched defensive rule becomes ``hold``;
   * **a violated risk cap can never leave the action as ``add``** -- it
     becomes ``hold`` and the card names the numbered cap that blocked it.
5. Size an indicative share range from the binding cap (never from a price
   target -- this module emits no target price of any kind).

Confidence is a function of two measurable things only: how much of the rule
set could be evaluated at all (data completeness) and how much of the matched
weight sits in the direction the call was taken from (agreement). It is not a
probability, and :data:`CONFIDENCE_MEANING` / :data:`WEIGHT_MEANING` say so on
the card itself rather than only in this docstring.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal, cast

from app.advice.context import build_context, describe_field
from app.advice.limits import (
    LimitCheck,
    PortfolioContext,
    RiskBudget,
    evaluate_limits,
    suggest_quantity_range,
)
from app.advice.loader import (
    AllOf,
    Comparison,
    ConditionNode,
    Rule,
    RuleSet,
    load_default_rules,
)

CardAction = Literal["add", "hold", "reduce", "stop_loss", "take_profit", "insufficient_data"]
Confidence = Literal["low", "medium", "high"]

#: Fixed Traditional Chinese disclaimer carried by every card.
DISCLAIMER: Final = "本工具為研究與教育用途，非投資建議"

#: What ``confidence`` is and is not. Travels *with* the card (the
#: ``NATURE``/``assumptions`` idiom of ``app/leverage/erosion.py``) so a
#: consumer that only reads the dict cannot mistake it for a probability.
CONFIDENCE_MEANING: Final = "信心等級反映規則一致性與資料完整度，非勝率或機率"

#: The same guard for every rule weight quoted on the card.
WEIGHT_MEANING: Final = "權重為規則優先序，非機率、勝率或預期報酬"

#: Tie-break order, most defensive first.
ACTION_PRECEDENCE: tuple[str, ...] = ("stop_loss", "reduce", "take_profit", "hold", "add")

#: Which way an action leans. Matched weight is summed per direction first, so
#: a defensive cluster split across ``reduce`` and ``stop_loss`` is compared as
#: one body of evidence rather than as two smaller ones.
ACTION_DIRECTION: dict[str, str] = {
    "stop_loss": "defensive",
    "reduce": "defensive",
    "take_profit": "defensive",
    "hold": "neutral",
    "add": "constructive",
}

#: Direction tie-break order, most defensive first.
DIRECTION_PRECEDENCE: tuple[str, ...] = ("defensive", "neutral", "constructive")

#: Below this share of the rule set being evaluable, the engine will not put its
#: name to an ``add`` or to an evidence-free ``hold`` -- it says so instead.
MIN_COMPLETENESS_FOR_ACTION = 0.5

#: Confidence thresholds (see module docstring).
HIGH_COMPLETENESS = 0.8
HIGH_AGREEMENT = 0.75
MEDIUM_COMPLETENESS = 0.5
MEDIUM_AGREEMENT = 0.5

_OPS: dict[str, Callable[[float, float], bool]] = {
    "gt": lambda left, right: left > right,
    "gte": lambda left, right: left >= right,
    "lt": lambda left, right: left < right,
    "lte": lambda left, right: left <= right,
    "eq": lambda left, right: left == right,
    "ne": lambda left, right: left != right,
    "abs_gt": lambda left, right: abs(left) > right,
    "abs_lt": lambda left, right: abs(left) < right,
}


@dataclass
class RuleOutcome:
    """How one rule fared: matched, or skipped because inputs were missing."""

    rule: Rule
    matched: bool
    missing_fields: list[str] = field(default_factory=list)

    @property
    def skipped(self) -> bool:
        return bool(self.missing_fields)


def _evaluate_node(
    node: ConditionNode, context: Mapping[str, float | None], missing: list[str]
) -> bool:
    """Evaluate a condition tree, collecting every unavailable field it touches.

    Children are evaluated eagerly (no short-circuit) so ``missing`` lists all
    the inputs a rule author would need to supply, not just the first one.
    """
    if isinstance(node, Comparison):
        left = context.get(node.field)
        if left is None:
            missing.append(node.field)
        if node.ref is not None:
            right = context.get(node.ref)
            if right is None:
                missing.append(node.ref)
        else:
            right = node.value
        if left is None or right is None:
            return False
        return bool(_OPS[node.op](left, right))

    children = node.all if isinstance(node, AllOf) else node.any
    results = [_evaluate_node(child, context, missing) for child in children]
    return all(results) if isinstance(node, AllOf) else any(results)


def evaluate_rule(rule: Rule, context: Mapping[str, float | None]) -> RuleOutcome:
    """Evaluate one rule. Any missing input makes the rule *skipped*.

    Skipping on partial data is intentional even for an ``any`` group that one
    available branch could already decide: a rule that reports "matched" on
    half its inputs cannot honestly claim the evidence its explanation states.
    """
    missing: list[str] = []
    matched = _evaluate_node(rule.condition, context, missing)
    unique_missing = list(dict.fromkeys(missing))
    return RuleOutcome(rule=rule, matched=matched and not unique_missing,
                       missing_fields=unique_missing)


def _action_weights(outcomes: list[RuleOutcome]) -> list[dict[str, Any]]:
    """Matched weight per action, heaviest first, with the rule ids behind it."""
    totals: dict[str, float] = {}
    rule_ids: dict[str, list[str]] = {}
    for outcome in outcomes:
        if not outcome.matched:
            continue
        action = outcome.rule.action
        totals[action] = totals.get(action, 0.0) + outcome.rule.weight
        rule_ids.setdefault(action, []).append(outcome.rule.id)
    ordered = sorted(
        totals.items(), key=lambda item: (-item[1], ACTION_PRECEDENCE.index(item[0]))
    )
    return [
        {"action": action, "weight": round(weight, 6), "rule_ids": rule_ids[action]}
        for action, weight in ordered
    ]


def _direction_weights(weights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Matched weight per direction, heaviest first.

    Aggregating by direction before picking an action is what stops a pair of
    light constructive rules from out-voting a heavier defensive cluster whose
    weight happens to be split across ``reduce`` and ``stop_loss``.
    """
    totals: dict[str, float] = {}
    actions: dict[str, list[str]] = {}
    for entry in weights:
        direction = ACTION_DIRECTION[entry["action"]]
        totals[direction] = totals.get(direction, 0.0) + float(entry["weight"])
        actions.setdefault(direction, []).append(entry["action"])
    ordered = sorted(
        totals.items(), key=lambda item: (-item[1], DIRECTION_PRECEDENCE.index(item[0]))
    )
    return [
        {"direction": direction, "weight": round(weight, 6), "actions": actions[direction]}
        for direction, weight in ordered
    ]


def _aggregate_action(weights: list[dict[str, Any]]) -> str | None:
    """The heaviest action inside the heaviest direction, or ``None`` if empty."""
    directions = _direction_weights(weights)
    if not directions:
        return None
    winning = directions[0]["direction"]
    for entry in weights:  # already ordered heaviest-first
        if ACTION_DIRECTION[entry["action"]] == winning:
            return str(entry["action"])
    return None  # pragma: no cover - the winning direction always has an action


def _agreement(directions: list[dict[str, Any]], aggregated: str | None) -> float:
    """Share of the matched weight that sits in the direction the call came from.

    Measured on the *winning direction*, because that is the unit the decision
    is taken in: two defensive rules that split their weight across ``reduce``
    and ``stop_loss`` agree with each other, and reading the heaviest single
    action instead would score that agreement against a losing constructive
    rule. The pre-override aggregate is used, since the overrides (thin data,
    defensive gate, risk caps) are disclosed separately on the card.
    """
    total = sum(float(entry["weight"]) for entry in directions)
    if aggregated is None or total <= 0.0:
        return 0.0
    winning = ACTION_DIRECTION[aggregated]
    for entry in directions:
        if entry["direction"] == winning:
            return float(entry["weight"]) / total
    return 0.0  # pragma: no cover - the aggregate always has a direction


def _confidence(
    *,
    action: CardAction,
    completeness: float,
    matched_count: int,
    agreement: float,
) -> Confidence:
    if action == "insufficient_data":
        return "low"
    if matched_count == 0:
        # Nothing fired, but the rule set was measurable: a defensible "hold".
        return "medium" if completeness >= HIGH_COMPLETENESS else "low"
    if (
        completeness >= HIGH_COMPLETENESS
        and agreement >= HIGH_AGREEMENT
        and matched_count >= 2
    ):
        return "high"
    if completeness >= MEDIUM_COMPLETENESS and agreement >= MEDIUM_AGREEMENT:
        return "medium"
    return "low"


def _skipped_entry(outcome: RuleOutcome) -> dict[str, Any]:
    fields = "、".join(describe_field(path) for path in outcome.missing_fields)
    return {
        "id": outcome.rule.id,
        "name": outcome.rule.name,
        "reason": f"缺少輸入欄位：{fields}",
        "missing_fields": list(outcome.missing_fields),
    }


def build_advice(
    *,
    symbol: str,
    signals: Mapping[str, Any],
    portfolio: PortfolioContext,
    budget: RiskBudget | None = None,
    ruleset: RuleSet | None = None,
) -> dict[str, Any]:
    """Produce the machine-readable advice card for one symbol.

    ``signals`` is a :func:`app.signals.service.compute_signals` output;
    ``portfolio`` describes the holding and the book around it. Neither is
    mutated. Every key of the returned dict is always present.
    """
    rules = ruleset if ruleset is not None else load_default_rules()
    risk_budget = budget if budget is not None else RiskBudget()

    # ATR drives the per-trade loss cap; take it from the signal layer when the
    # caller did not supply one, so the cap is evaluable without duplicated
    # plumbing at the call site.
    context = build_context(signals, portfolio)
    if portfolio.atr is None and context["atr14.last"] is not None:
        portfolio = portfolio.model_copy(update={"atr": context["atr14.last"]})

    outcomes = [evaluate_rule(rule, context) for rule in rules.rules]
    evaluated = [outcome for outcome in outcomes if not outcome.skipped]
    matched = [outcome for outcome in evaluated if outcome.matched]
    weights = _action_weights(outcomes)
    completeness = len(evaluated) / len(rules.rules)

    aggregated = _aggregate_action(weights) if evaluated else None
    action: CardAction = "hold" if aggregated is None else _as_card_action(aggregated)
    downgrade_notices: list[str] = []

    # Thin data is reported as thin data. An ``add`` needs a rule set that was
    # mostly evaluable, and so does an evidence-free "nothing to do" hold.
    if not evaluated or (
        completeness < MIN_COMPLETENESS_FOR_ACTION and (action == "add" or not matched)
    ):
        action = "insufficient_data"
    elif action == "add":
        # Never propose adding while defensive rules are also firing, even when
        # the constructive side carries slightly more weight.
        defensive = [
            outcome for outcome in matched if ACTION_DIRECTION[outcome.rule.action] == "defensive"
        ]
        if defensive:
            names = "、".join(outcome.rule.name for outcome in defensive)
            action = "hold"
            downgrade_notices.append(
                f"另有 {len(defensive)} 條防禦型規則同時命中（{names}），加碼建議改為觀望。"
            )

    limits = evaluate_limits(risk_budget, portfolio)
    violated = [check for check in limits if check.status == "violated"]
    blocked_action: str | None = None
    blocked_notices: list[str] = []
    if action == "add" and violated:
        blocked_action = "add"
        action = "hold"
        blocked_notices = [
            f"加碼建議被第 {check.index} 條上限（{check.name}）擋下。" for check in violated
        ]

    quantity = suggest_quantity_range(risk_budget, portfolio, action=action)
    directions = _direction_weights(weights)

    return {
        "symbol": symbol,
        "action": action,
        "quantity_range": quantity.model_dump() if quantity is not None else None,
        "matched_rules": [
            {
                "id": outcome.rule.id,
                "name": outcome.rule.name,
                "action": outcome.rule.action,
                "weight": outcome.rule.weight,
                "weight_meaning": WEIGHT_MEANING,
                "explanation": outcome.rule.explanation,
            }
            for outcome in matched
        ],
        "counterarguments": list(
            dict.fromkeys(outcome.rule.counterargument for outcome in matched)
        ),
        "invalidation_conditions": list(
            dict.fromkeys(outcome.rule.invalidation for outcome in matched)
        ),
        "confidence": _confidence(
            action=action,
            completeness=completeness,
            matched_count=len(matched),
            agreement=_agreement(directions, aggregated),
        ),
        "confidence_meaning": CONFIDENCE_MEANING,
        "rules_version": rules.version,
        "as_of": _as_of(signals),
        "observation_window": _observation_window(signals),
        "disclaimer": DISCLAIMER,
        "limits_check": [_limit_entry(check) for check in limits],
        "action_weights": weights,
        "direction_weights": directions,
        "has_conflict": len(weights) > 1,
        "aggregated_action": aggregated,
        "blocked_action": blocked_action,
        "blocked_notices": blocked_notices,
        "downgrade_notices": downgrade_notices,
        "evaluation": {
            "total_rules": len(rules.rules),
            "evaluated_rules": len(evaluated),
            "matched_rules": len(matched),
            "data_completeness": round(completeness, 4),
            "skipped_rules": [
                _skipped_entry(outcome) for outcome in outcomes if outcome.skipped
            ],
        },
    }


def _as_card_action(action: str) -> CardAction:
    """Narrow a rule action to a card action (the rule schema pins the values)."""
    if action not in ACTION_DIRECTION:  # pragma: no cover - schema-enforced
        raise ValueError(f"unknown action: {action}")
    return cast(CardAction, action)


def _as_of(signals: Mapping[str, Any]) -> str | None:
    value = signals.get("as_of")
    return value if isinstance(value, str) else None


def _observation_window(signals: Mapping[str, Any]) -> dict[str, Any]:
    """First/last bar date and bar count behind the signal inputs.

    Several rules speak of "觀察區間內" (drawdown, volume z-score); without the
    window those statements cannot be checked. The dates come from the aligned
    date index the indicators publish -- every indicator shares one index, so
    the first non-empty one describes them all. An indicator that reported
    ``insufficient_data`` carries no dates, hence the null-safe fallback to the
    bar count alone.
    """
    start: str | None = None
    end: str | None = None
    technical = signals.get("technical")
    if isinstance(technical, Mapping):
        for indicator in technical.values():
            if not isinstance(indicator, Mapping):
                continue
            dates = indicator.get("dates")
            if isinstance(dates, list) and dates:
                start, end = str(dates[0]), str(dates[-1])
                break
    bar_count = signals.get("bar_count")
    return {
        "start": start,
        "end": end,
        "bars": bar_count if isinstance(bar_count, int) else None,
    }


def _limit_entry(check: LimitCheck) -> dict[str, Any]:
    return check.model_dump()


__all__ = [
    "ACTION_PRECEDENCE",
    "DISCLAIMER",
    "CardAction",
    "Confidence",
    "RuleOutcome",
    "build_advice",
    "evaluate_rule",
]
