"""Notification rules and dedupe keys (pure functions).

Comparisons only ever happen within one ``price_kind`` and one currency, against the
watch's current revision; cached prices can never move the live baseline.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from flight_deals.domain.models import AlertReason, PriceKind
from flight_deals.domain.timeutil import TAIPEI, taipei_date

BP_SCALE = 10_000


@dataclass(frozen=True)
class Candidate:
    """One priced date pair found in the current scan."""

    observation_id: int | None
    depart_date: date
    return_date: date | None
    amount_minor: int
    currency: str
    price_kind: PriceKind
    source: str
    carrier: str | None
    fetched_at: datetime


@dataclass(frozen=True)
class AlertBaseline:
    """State the rules compare against (same watch, revision, price_kind, currency)."""

    last_notified_amount_minor: int | None
    armed: bool
    historical_min_amount_minor: int | None


@dataclass(frozen=True)
class TriggeredItem:
    candidate: Candidate
    reasons: tuple[AlertReason, ...]
    drop_percent: int | None
    item_key: str


def price_item_key(
    watch_id: int, price_kind: str, depart: date, return_date: date | None, amount_minor: int
) -> str:
    ret = return_date.isoformat() if return_date else "-"
    return f"price:{watch_id}:{price_kind}:{depart.isoformat()}:{ret}:{amount_minor}"


def price_message_key(watch_id: int, price_kind: str, items: Iterable[TriggeredItem]) -> str:
    parts = sorted(
        f"{i.candidate.depart_date.isoformat()}:"
        f"{i.candidate.return_date.isoformat() if i.candidate.return_date else '-'}:"
        f"{i.candidate.amount_minor}"
        for i in items
    )
    return f"price:{watch_id}:{price_kind}:" + "|".join(parts)


def ops_failure_key(source: str, now: datetime) -> str:
    """At most one source-failure alert per source per Asia/Taipei calendar day."""
    return f"ops:{source}:{taipei_date(now).isoformat()}"


def telegram_test_key(now: datetime) -> str:
    return "test:" + now.astimezone(TAIPEI).isoformat(timespec="microseconds")


def drop_percent(previous: int, current: int) -> int:
    """Whole-percent drop from ``previous`` to ``current`` (integer math, floor)."""
    if previous <= 0 or current >= previous:
        return 0
    return ((previous - current) * 100) // previous


def is_drop_at_least(previous: int, current: int, threshold_bp: int) -> bool:
    return current * BP_SCALE <= previous * (BP_SCALE - threshold_bp)


def evaluate_price_alerts(
    candidates: Iterable[Candidate],
    *,
    watch_id: int,
    price_kind: PriceKind,
    currency: str,
    budget_amount_minor: int | None,
    notify_on_new_low: bool,
    drop_threshold_bp: int,
    baseline: AlertBaseline,
    already_notified_keys: set[str],
    max_items: int,
) -> list[TriggeredItem]:
    """Return the cheapest triggered items (at most ``max_items``), cheapest first."""
    triggered: list[TriggeredItem] = []
    for cand in candidates:
        if cand.price_kind != price_kind or cand.currency != currency:
            continue
        key = price_item_key(
            watch_id, price_kind, cand.depart_date, cand.return_date, cand.amount_minor
        )
        if key in already_notified_keys:
            continue
        reasons: list[AlertReason] = []
        pct: int | None = None
        if (
            budget_amount_minor is not None
            and baseline.armed
            and cand.amount_minor <= budget_amount_minor
        ):
            reasons.append("below_budget")
        last = baseline.last_notified_amount_minor
        if last is not None and is_drop_at_least(last, cand.amount_minor, drop_threshold_bp):
            reasons.append("drop_pct")
            pct = drop_percent(last, cand.amount_minor)
        low = baseline.historical_min_amount_minor
        if notify_on_new_low and low is not None and cand.amount_minor < low:
            reasons.append("new_low")
        if reasons:
            triggered.append(TriggeredItem(cand, tuple(reasons), pct, key))
    triggered.sort(
        key=lambda t: (
            t.candidate.amount_minor,
            t.candidate.depart_date,
            t.candidate.return_date or t.candidate.depart_date,
        )
    )
    return triggered[:max_items]


def should_rearm(run_min_amount_minor: int | None, budget_amount_minor: int | None) -> bool:
    """Re-arm the budget rule once prices are seen back above the budget."""
    if run_min_amount_minor is None or budget_amount_minor is None:
        return False
    return run_min_amount_minor > budget_amount_minor


def primary_reason(item: TriggeredItem) -> AlertReason:
    return item.reasons[0]
