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
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.advice.context import build_context, describe_field
from app.advice.engine import COMPARISON_OPS
from app.advice.limits import (
    PRICE_INPUT_LIMIT_IDS,
    LimitCheck,
    PortfolioContext,
    shows_price_input_figure,
)
from app.alerts.models import (
    AlertEvent,
    AlertRule,
    PriceThresholdParams,
    RiskLimitParams,
    SignalConditionParams,
    unevaluable_alert_fields,
)
from app.alerts.store import AlertStore
from app.data.price_guard import usable_price as is_usable_price
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
    #: Only ever read on a price or signal rule that is **skipped**; a fired
    #: rule's message does not include it, which is why the disclosure below has
    #: its own field. A risk-limit skip does not read it either: it is a join of
    #: unrelated notes (data layer, applied rate), most of which are not why a
    #: cap was unevaluable -- that skip reads ``price_cap_cause`` instead.
    reason: str | None = None
    #: The sentence naming a failed FX conversion -- no quote, no usable rate,
    #: or a quote for the wrong pair -- or a holding whose currency is not its
    #: market's (task X-3c), and nothing else: ``None`` when the rate
    #: was applied, when none was needed (TWD), or when the holding spans more
    #: than one currency. Either cause withholds the price and the ATR
    #: from the caps, so this is the cause of an unevaluable cap that reads them
    #: (:data:`app.advice.limits.PRICE_INPUT_LIMIT_IDS`) and only of those; the
    #: risk-limit skip appends it under exactly that condition.
    price_cap_cause: str | None = None
    #: The FX source's standing disclosure (ADR-0005 F-4) for a fired message
    #: that shows a figure the applied quote was multiplied into -- the version
    #: *with* the quote (``BookContext.fx_disclosure``). The risk-cap message
    #: quotes TWD-converted figures, so this sentence has to travel with the
    #: *fired* message -- all the way to Discord/Telegram -- not merely with a
    #: skip. Read by :func:`_limit_outcome` only, which picks it or the field
    #: below per fired rule (PR-RK4c, R4c-8).
    fx_disclosure: str | None = None
    #: The same disclosure for a fired message that shows no figure the quote
    #: was multiplied into (``BookContext.fx_disclosure_without_quote``):
    #: W-RK4-1 and the valuator's sentences, or ``None``.
    fx_disclosure_without_quote: str | None = None
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
    #: Always set on ``skipped`` and ``suppressed``. On ``quiet`` it is ``None``
    #: except for a risk-limit rule that left some caps unevaluated
    #: (:data:`UNEVALUATED_LIMITS_NOTE`).
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

#: The ``reason`` on a quiet ``risk_limit_breach`` rule when some watched caps
#: passed, none was violated and the rest could not be evaluated (S-B2). Only
#: ``limit_id="any"`` can reach that mix. ``{n}`` is the count of unevaluated
#: caps and ``{names}`` their ``LimitCheck.name`` in ``LIMIT_IDS`` order joined
#: with "、". Approved verbatim by risk-compliance-officer 2026-10-07 (S-B2-A,
#: `work/reviews/2026-10-07-S-B2-風險上限any規則-未評估揭露-字面-風控審查.md`);
#: nothing may be appended to it, and any change goes back to them.
UNEVALUATED_LIMITS_NOTE = "本次有 {n} 條上限未評估，未納入判定：{names}。其餘已評估的上限皆未違反。"


@dataclass(frozen=True)
class _QuietWithReason:
    """A rule that did not cross its line but carries a disclosure on its outcome.

    Only the risk-limit evaluator produces this, and only for the mixed case
    behind :data:`UNEVALUATED_LIMITS_NOTE`. Its outcome stays ``quiet``: no
    event is written and the cooldown is not consulted.
    """

    reason: str


#: What a rule-type evaluator hands back: ``(crossed, message, observed)``, a
#: skip reason string, or a quiet outcome that carries a reason.
_Evaluated = tuple[bool, str, dict[str, float | str | None]] | str | _QuietWithReason


def _fmt(value: float) -> str:
    """Render a number for a message without exponent noise or trailing zeros."""
    return f"{value:,.4f}".rstrip("0").rstrip(".") if value % 1 else f"{value:,.0f}"


def usable_price(close: float | None) -> float | None:
    """``close`` if it is a usable latest close, else ``None``.

    "Usable" is defined once, by :func:`app.data.price_guard.usable_price` (a
    missing, zero, negative or non-finite close is "no price"); this keeps its
    name and its value-or-``None`` shape for the alert layer. A snapshot can be
    built by any loader, so the alert layer still applies the guard itself.
    Shared by :func:`usable_close` (the rule paths) and
    :func:`app.alerts.snapshot.build_snapshot` (whether to run the signal layer
    and price the risk caps at all), so the two can never disagree.
    """
    return close if close is not None and is_usable_price(close) else None


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
) -> _Evaluated:
    """``(crossed, message, observed)``, a skip reason string, or a quiet disclosure."""
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
            # "缺少輸入" alone leaves the reader to guess between "no price" and
            # "no FX conversion", so a failed conversion is named -- but only
            # where it is the cause; see :func:`_limit_cause` for the two gates.
            cause = _limit_cause(snapshot, watched)
            return f"監看的上限（{names}）缺少輸入，無法判定是否違反。{cause}"
        unevaluated = [check for check in watched if check.status == "not_evaluable"]
        passed = [check for check in watched if check.status == "passed"]
        if unevaluated and passed:
            # Mixed: some caps passed, none was violated, the rest could not be
            # evaluated. The rule stays quiet; its reason only discloses which
            # caps were left out of the verdict, it is not a cause. So nothing
            # else is appended: not ``snapshot.reason``, not any ``check.detail``,
            # not a disclosure -- why a cap was unevaluable is not stated here.
            return _QuietWithReason(
                UNEVALUATED_LIMITS_NOTE.format(
                    n=len(unevaluated), names="、".join(check.name for check in unevaluated)
                )
            )
        return False, "", {}
    names = "、".join(f"第 {check.index} 條（{check.name}）" for check in violated)
    details = " ".join(check.detail for check in violated)
    message = f"{rule.symbol} 觸發風險上限：{names}。{details}"
    # Every cap here is measured in TWD, so on a foreign-currency holding the
    # figures in ``details`` passed through an FX rate -- the valuator's for
    # the market value and the equity, the applied quote only for a cap that
    # reads the price or the ATR (risk RK4-E1b-1). ADR-0005 F-4 requires the
    # rate's provenance to be visible wherever it is used, and this message is
    # what the user actually receives (feed, Discord, Telegram). Which version
    # is judged per rule (PR-RK4c, R4c-8) from ``violated`` -- the very list
    # ``details`` was built from, so the judged caps are exactly the caps the
    # message lists (risk RK4c-R1). If this message ever lists passed caps'
    # details too, they have to be passed to the judgement as well.
    disclosure = (
        snapshot.fx_disclosure
        if shows_price_input_figure(violated, sized=False)
        else snapshot.fx_disclosure_without_quote
    )
    if disclosure:
        message = f"{message} {disclosure}"
    observed: dict[str, float | str | None] = {
        "violated_limit_ids": "、".join(check.id for check in violated),
        "violated_count": float(len(violated)),
    }
    return True, message, observed


def _limit_cause(snapshot: SymbolSnapshot, watched: Sequence[LimitCheck]) -> str:
    """The tail of an all-unevaluated risk-limit skip: ``" " + cause`` or ``""``.

    The only cause ever appended is ``price_cap_cause`` -- a failed FX
    conversion, or a holding whose currency is not its market's (task X-3c) --
    and only past two gates:

    * A′ -- the close is present but unusable (the same :func:`usable_close` the
      price and signal paths use). The price and ATR were then withheld for the
      close, not for the FX lookup, so no FX sentence may stand as the cause.
    * Scope -- at least one watched, unevaluable cap reads the price or ATR
      (:data:`app.advice.limits.PRICE_INPUT_LIMIT_IDS`). A missing conversion
      is not why the other caps could not be evaluated.

    ``snapshot.reason`` is never read here: the data layer's note and an
    applied-rate note are not causes of an unevaluable cap.
    """
    if snapshot.close is not None and usable_close(snapshot) is None:
        return ""
    if not any(
        check.status == "not_evaluable" and check.id in PRICE_INPUT_LIMIT_IDS for check in watched
    ):
        return ""
    return f" {snapshot.price_cap_cause}" if snapshot.price_cap_cause else ""


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
        if isinstance(evaluated, _QuietWithReason):
            outcomes.append(RuleOutcome(rule_id=rule.id, status="quiet", reason=evaluated.reason))
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


def _evaluate_one(rule: AlertRule, snapshot: SymbolSnapshot) -> _Evaluated:
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
