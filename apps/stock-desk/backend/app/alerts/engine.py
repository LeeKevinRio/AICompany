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

import logging
import math
from collections import Counter
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
    unevaluable_alert_fields,
)
from app.alerts.store import AlertStore
from app.positions.models import Market

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SymbolSnapshot:
    """Everything the rule types need about one symbol at one moment.

    Every field is optional in the "could not be produced" sense: ``close`` is
    ``None`` without usable bars, ``signals`` is empty when the signal layer was
    not run, ``limits`` is empty when no risk context could be built. Each rule
    type turns its own missing input into a skip.

    Two ways a snapshot ends up empty besides missing bars:

    * The latest bar's close is unusable (see :func:`usable_price`). The signal
      layer is then not run (``signals`` is empty) and the risk caps are built
      without a price or an ATR, but ``close`` keeps the bar's raw value, so a
      price rule reports the price itself as the missing input.
    * The loader raised. :func:`evaluate_alerts` then stands in a bare
      ``SymbolSnapshot(symbol, market)`` for that symbol for the rest of the
      tick, so its rules are skipped with their type's usual reason.
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
    #: The data layer's own sentence about the bars the rule was judged on
    #: (``ProviderResult.reason``: served from cache, spliced from more than one
    #: source -- ADR-0009 D-7 / ADR-0005 D-5). A threshold crossing can be made
    #: by the seam of a spliced series, so this travels with every **fired**
    #: message (風控 2026-09-15 R1-a), the same way ``fx_disclosure`` does.
    data_disclosure: str | None = None


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
    #: How many (symbol, market) snapshots failed to load this tick -- counted
    #: per symbol, not per rule. Log-only: the API response does not carry it.
    load_failures: int = 0


#: Appended to a fired price-threshold or signal-condition message: the bar
#: date the quoted figures come from, as opposed to the evaluation time the
#: push adds. Wording by creative-lead (`work/stock-desk-alerts-asof揭露句-文案.md`),
#: fixed verbatim by risk-compliance-officer 2026-09-15 for those two rule
#: types only; any change, or use on another type, goes back to them.
BAR_AS_OF_NOTE = "上述數值之資料日為 {as_of}。"


def _fmt(value: float) -> str:
    """Render a number for a message without exponent noise or trailing zeros."""
    return f"{value:,.4f}".rstrip("0").rstrip(".") if value % 1 else f"{value:,.0f}"


def usable_price(close: float | None) -> float | None:
    """``close`` if it is a usable latest close, else ``None``.

    The single definition of "usable": a missing, zero, negative or non-finite
    close is "no price". ``PriceBar.close`` rejects NaN but not ``<= 0``, and a
    snapshot can be built by any loader, so the guard sits in the alert layer
    rather than upstream. Shared by :func:`usable_close` (the rule paths) and
    :func:`app.alerts.snapshot.build_snapshot` (whether to run the signal layer
    and price the risk caps at all), so the two can never disagree.
    """
    return close if close is not None and math.isfinite(close) and close > 0 else None


def usable_close(snapshot: SymbolSnapshot) -> float | None:
    """The snapshot's close if a price rule or ``close`` field may use it, else ``None``.

    The one guard both alert paths share; see :func:`usable_price`.
    """
    return usable_price(snapshot.close)


def _price_outcome(
    rule: AlertRule, snapshot: SymbolSnapshot, params: PriceThresholdParams
) -> tuple[bool, str, dict[str, float | str | None]]:
    """``(crossed, message, observed)`` for a price threshold rule."""
    close = usable_close(snapshot)
    assert close is not None  # the caller skips a snapshot without a usable price
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


def signal_context(snapshot: SymbolSnapshot) -> dict[str, float | None]:
    """The rule inputs a ``signal_condition`` alert is judged on.

    The snapshot's signal layer plus its latest close, and no portfolio
    position: the fields this can produce as non-``None`` are exactly
    :data:`app.advice.context.ALERT_RULE_FIELDS` (ADR-0021 K-1). ``beta.value``
    needs a benchmark the snapshot does not load (K-7) and ``position.*`` needs
    a position it does not carry; both stay ``None`` here, and a rule naming one
    is skipped before this is consulted (see :func:`_evaluate_one`).
    """
    return build_context(
        snapshot.signals,
        PortfolioContext(symbol=snapshot.symbol, close=usable_close(snapshot)),
    )


def _signal_outcome(
    rule: AlertRule, snapshot: SymbolSnapshot, params: SignalConditionParams
) -> tuple[bool, str, dict[str, float | str | None]] | str:
    """``(crossed, message, observed)``, or a skip reason string."""
    comparison = params.condition
    context = signal_context(snapshot)
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
            # ``reason`` usually says *why* the inputs are missing (no FX rate,
            # a degraded data layer); "缺少輸入" alone would leave the reader to
            # guess which of them it was. Not always: when the close is present
            # but unusable (A′), the price and ATR were withheld for that, and
            # ``reason`` only holds whatever unrelated note the data layer or
            # the FX lookup added -- or nothing.
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
    """Evaluate every enabled rule once and persist the events that fired.

    A loader that raises for one (symbol, market) does not end the tick: that
    symbol gets a bare snapshot for the rest of the tick (no retry), so each of
    its rules is skipped with its type's existing reason, and every other
    symbol is evaluated as usual. Only :class:`Exception` is caught; an
    interrupt or a system exit still propagates.
    """
    moment = now if now is not None else datetime.now(UTC)
    rules = store.list_rules(enabled_only=True)
    outcomes: list[RuleOutcome] = []
    events: list[AlertEvent] = []

    # One snapshot per (symbol, market) is reused by every rule watching it, so
    # ten rules on one symbol cost one data fetch, not ten.
    snapshots: dict[tuple[str, Market], SymbolSnapshot] = {}
    rules_per_key = Counter((rule.symbol, rule.market) for rule in rules)
    load_failures = 0

    for rule in rules:
        key = (rule.symbol, rule.market)
        if key not in snapshots:
            snapshots[key], loaded = _load_isolated(
                loader, rule.symbol, rule.market, rule_count=rules_per_key[key]
            )
            # Each key is loaded at most once per tick, so this counts symbols.
            if not loaded:
                load_failures += 1
        snapshot = snapshots[key]

        evaluated = _evaluate_one(rule, snapshot)
        if isinstance(evaluated, str):
            outcomes.append(RuleOutcome(rule_id=rule.id, status="skipped", reason=evaluated))
            continue
        crossed, message, observed = evaluated
        if not crossed:
            outcomes.append(RuleOutcome(rule_id=rule.id, status="quiet"))
            continue
        # The bar date the figures come from, then what the data layer said
        # about those bars (cache, spliced sources), go out with the message
        # itself: the feed, Discord and Telegram are what the user reads, and
        # the push only adds the *evaluation* time (風控 2026-09-15 R1-a / R4-a).
        # Not on ``risk_limit_breach``: its figures are portfolio weights built
        # from every holding's own latest close (and a rate that may date from
        # an earlier day), so one bar date would overstate their precision
        # (風控 2026-09-15 R4-a 覆審 VETO, direction (c)).
        if snapshot.as_of and not isinstance(rule.params, RiskLimitParams):
            message = f"{message} {BAR_AS_OF_NOTE.format(as_of=snapshot.as_of)}"
        if snapshot.data_disclosure:
            message = f"{message} {snapshot.data_disclosure}"
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
        load_failures=load_failures,
    )


def _load_isolated(
    loader: SnapshotLoader, symbol: str, market: Market, *, rule_count: int
) -> tuple[SymbolSnapshot, bool]:
    """``(loader(symbol, market), True)``, or ``(bare snapshot, False)`` if it raised.

    The warning carries the market, a count and the exception class only --
    no rule id and no symbol, the same as the start-up diagnostic
    (``app.scheduler.log_unevaluable_alert_rules``); the traceback rides on
    ``exc_info`` for whoever reads the log.
    """
    try:
        return loader(symbol, market), True
    except Exception as exc:
        logger.warning(
            "alert evaluation: snapshot load failed (market=%s, %s); %d rule(s) skipped this tick",
            market,
            type(exc).__name__,
            rule_count,
            exc_info=True,
        )
        return SymbolSnapshot(symbol=symbol, market=market), False


def count_unevaluable_rules(rules: Sequence[AlertRule]) -> int:
    """How many of ``rules`` name a field alerts cannot evaluate (ADR-0021 K-8).

    Read-only diagnostic: such rules are left exactly as stored.
    """
    return sum(1 for rule in rules if unevaluable_alert_fields(rule.params))


def _evaluate_one(
    rule: AlertRule, snapshot: SymbolSnapshot
) -> tuple[bool, str, dict[str, float | str | None]] | str:
    """Dispatch one rule to its type's evaluator, or return a skip reason."""
    params = rule.params
    if isinstance(params, PriceThresholdParams):
        if snapshot.close is None:
            return snapshot.reason or "沒有可用的最新收盤價。"
        if usable_close(snapshot) is None:
            # A close that is present but zero, negative or NaN: ``reason`` may
            # hold an unrelated note (data layer, FX), so name the price itself.
            return "沒有可用的最新收盤價。"
        return _price_outcome(rule, snapshot, params)
    if isinstance(params, SignalConditionParams):
        unevaluable = unevaluable_alert_fields(params)
        if unevaluable:
            # ADR-0021 K-6: a stored rule naming a field alerts never produce is
            # skipped on membership, not on the value being ``None`` -- and ahead
            # of the "no signals" check, because its cause does not go away
            # when the data comes back. Wording is ADR-0021 W-2, approved
            # verbatim by risk-compliance-officer 2026-10-06
            # (`work/reviews/2026-10-06-ADR-0021-警示欄位可評估性-字面-風控審查.md`);
            # any change goes back to them.
            path = unevaluable[0]
            return (
                f"此規則使用的 {describe_field(path)}，警示不提供作為條件。"
                "每次檢查都會略過此規則，不會觸發。可改用其他欄位的條件，或刪除此規則。"
            )
        if not snapshot.signals:
            if snapshot.close is not None and usable_close(snapshot) is None:
                # Signals were withheld because the close is unusable (A′), not
                # for whatever ``reason`` holds (data layer, FX) -- the same
                # guard as the price path, so the existing wording stands alone.
                return "沒有可用的訊號輸出。"
            return snapshot.reason or "沒有可用的訊號輸出。"
        return _signal_outcome(rule, snapshot, params)
    return _limit_outcome(rule, snapshot, params)
