"""Read/write the persisted risk budget, cost model, alert and net-worth settings.

The response also carries a read-only data-source block (ADR-0005 決策三 point
6): today's Alpha Vantage ``used`` / ``limit_value`` / ``quota_date`` straight
out of :class:`app.data.quota.QuotaLedger`. It is strictly an observation --
this endpoint never reserves a slot, never writes to the ledger, and holds no
opinion on the budget; the gating decision stays where it is, inside the
adapter.

``PUT`` takes any subset of the four sections; an omitted section is left
untouched rather than reset. Each section is validated by its own pydantic model
(:mod:`app.settings.models`), so a bad value fails with a 422 naming the field
instead of being clamped into range -- a silently clamped risk cap is exactly
the kind of number a user would later believe they had set.

The ``net_worth`` section (FR-9) is the one write that is also checked against
the *book*, not only against its own field bounds: a figure below the valued
positions is refused and one far above them is stored with a warning
(:mod:`app.settings.net_worth`). That comparison needs the positions valued, so
it is done **only on a write that carries the section** -- reading the settings
page must not turn into a round of price fetches. The consequence is stated
where it matters: the freshness block below is computed on every read from the
clock alone, while the "this is 10x your book" warning belongs to the response
of the write that produced it.

The risk-budget bounds are the ones declared on
:class:`app.advice.limits.RiskBudget` and are reused unchanged, whatever the
settings page asks for: a single name stays at most 50% of equity, gross
exposure at most 150%, fractional Kelly at most a quarter and the hard Kelly
ceiling at most 10%. Those four are hard ceilings with no request-level
override -- a write past one is a 422 quoting the ceiling and the reason, not a
warning the caller can acknowledge and proceed through.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.advice.book import self_reported_net_worth
from app.advice.limits import NET_WORTH_SOFT_NOTICE_DAYS, NET_WORTH_STALE_AFTER_DAYS
from app.api.common import now_iso
from app.api.deps import (
    get_position_store,
    get_quota_ledger,
    get_settings_store,
    get_valuator,
)
from app.data.providers.alpha_vantage import AlphaVantageAdapter
from app.data.quota import (
    DEFAULT_RESET_TZ,
    QuotaConfigError,
    QuotaLedger,
    current_quota_date,
    resolve_quota_config,
)
from app.portfolio.summary import build_summary
from app.portfolio.valuation import PositionValuator
from app.positions.store import PositionStore
from app.settings.models import AppSettings, AppSettingsPatch
from app.settings.net_worth import NetWorthReview, review_net_worth
from app.settings.store import SettingsStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

SettingsDep = Annotated[SettingsStore, Depends(get_settings_store)]
QuotaDep = Annotated[QuotaLedger, Depends(get_quota_ledger)]
PositionStoreDep = Annotated[PositionStore, Depends(get_position_store)]
ValuatorDep = Annotated[PositionValuator, Depends(get_valuator)]

RATE_PROVENANCE_NOTE = (
    "cost_model 的預設費率尚未經主要來源查證（verified_on 為 null）；"
    "查證後請更新 verified_on 與各項費率。"
)

#: The daily cap is configuration, and the safety margin is subtracted from it,
#: so the number shown is our own usable budget -- not a figure verified against
#: the vendor (ADR-0005 記載其所有額度數字 verified=False).
QUOTA_LIMIT_NOTE = (
    "每日額度上限來自 ALPHA_VANTAGE_DAILY_LIMIT 環境變數扣除安全邊際後的可用值，"
    "數字本身未經線上查證。"
)

#: ADR-0005 決策三 point 4 explicitly flags the reset boundary as unverified.
QUOTA_RESET_TZ_NOTE = (
    "額度重置時區為 {reset_tz}（QUOTA_RESET_TZ 設定值），"
    "實際重置時點未經查證，跨日附近的用量可能與供應商認定不同。"
)

#: Without a configured cap there is no denominator, so remaining is withheld
#: rather than guessed.
QUOTA_UNCONFIGURED_NOTE = (
    "尚未設定 ALPHA_VANTAGE_DAILY_LIMIT，無法得知今日剩餘額度；"
    "Alpha Vantage 主來源在此設定完成前不會發出請求。"
)

#: The ledger lives in the database the scheduler process also writes to; a
#: locked or missing file must not take the whole settings page down with it.
QUOTA_UNREADABLE_NOTE = "無法讀取額度計數器，今日用量暫時無法顯示。"

#: FR-9 (f) required reminder. A USD figure typed into this field is off by
#: roughly thirty times, and the 10x warning is only the *second* line of
#: defence against that; this sentence is the first.
NET_WORTH_CURRENCY_NOTE = (
    "此欄位只收新台幣。若你有外幣資產，請自行換算為台幣後填入；"
    "系統不會為此欄位做匯率換算。"
)

#: The state the product shipped in for months, and still the default one.
NET_WORTH_ABSENT_NOTE = (
    "尚未輸入帳戶總淨值，第 3 條總曝險上限維持 not_evaluable（無法評估）。"
)

NET_WORTH_AGEING_NOTE = "帳戶總淨值已 {age_days} 天未更新，滿 {days} 天後第 3 條上限將停止計算。"

NET_WORTH_EXPIRED_NOTE = (
    "帳戶總淨值輸入已超過 {days} 天未更新（距今 {age_days} 天），"
    "第 3 條總曝險上限已退回 not_evaluable；請更新後再評估。"
)

#: ``absent`` -- never entered; ``fresh`` / ``ageing`` -- usable, the second one
#: with a reminder; ``expired`` -- past the freshness rule, cap 3 is off again.
NetWorthFreshness = Literal["absent", "fresh", "ageing", "expired"]


class QuotaUsageView(BaseModel):
    """One provider's quota observation for today.

    ``used`` is ``None`` only when the ledger could not be read at all; a
    provider that has simply not been called yet today reports ``0``.
    ``limit_value`` and ``remaining`` are ``None`` when no cap is configured.
    """

    model_config = ConfigDict(frozen=True)

    provider: str
    quota_date: str
    used: int | None
    limit_value: int | None
    remaining: int | None
    reset_tz: str
    notes: list[str]


class DataSourcesView(BaseModel):
    """The read-only data-source block of the settings document."""

    model_config = ConfigDict(frozen=True)

    quotas: list[QuotaUsageView]


class NetWorthView(BaseModel):
    """What the settings page needs to show about the reported net worth.

    ``age_days`` and ``freshness`` are derived from the same helper the risk
    layer uses (:func:`app.advice.book.self_reported_net_worth`), so the page
    can never say "fresh" about a figure the cap has already stopped using.
    """

    model_config = ConfigDict(frozen=True)

    total_net_worth_twd: float | None
    updated_at: str | None
    age_days: int | None
    freshness: NetWorthFreshness
    #: Always present: the currency reminder plus whatever the freshness state
    #: obliges us to say.
    notes: list[str]
    #: Only the write that produced them carries these -- the checks behind
    #: them need the book valued, which a read deliberately does not do.
    warnings: list[str]


class SettingsResponse(BaseModel):
    """The settings document plus its data-source block and ``as_of`` stamp."""

    model_config = ConfigDict(frozen=True)

    settings: AppSettings
    rates_verified: bool
    notes: list[str]
    data_sources: DataSourcesView
    net_worth: NetWorthView
    as_of: str


def _alpha_vantage_quota(ledger: QuotaLedger) -> QuotaUsageView:
    """Today's Alpha Vantage usage, degrading to a stated gap on any failure."""
    provider = AlphaVantageAdapter.source_id
    notes: list[str] = []
    try:
        config = resolve_quota_config()
    except QuotaConfigError as exc:
        logger.warning("settings: quota configuration unreadable: %s", exc)
        reset_tz, limit_value = DEFAULT_RESET_TZ, None
        notes.append(QUOTA_UNCONFIGURED_NOTE)
    else:
        reset_tz, limit_value = config.reset_tz, config.effective_limit
        notes.append(QUOTA_LIMIT_NOTE)
    notes.append(QUOTA_RESET_TZ_NOTE.format(reset_tz=reset_tz))

    try:
        usage = ledger.status(provider, reset_tz=reset_tz)
        quota_date = current_quota_date(reset_tz)
    except sqlite3.Error as exc:
        logger.warning("settings: quota ledger unreadable: %s", exc)
        return QuotaUsageView(
            provider=provider,
            quota_date=current_quota_date(reset_tz),
            used=None,
            limit_value=limit_value,
            remaining=None,
            reset_tz=reset_tz,
            notes=[*notes, QUOTA_UNREADABLE_NOTE],
        )

    if usage is None:
        # No row yet means no slot has been reserved today -- a real zero, not a
        # missing reading, so the configured cap is still the day's denominator.
        return QuotaUsageView(
            provider=provider,
            quota_date=quota_date,
            used=0,
            limit_value=limit_value,
            remaining=limit_value,
            reset_tz=reset_tz,
            notes=notes,
        )
    # The stored ``limit_value`` is the cap that was actually applied when the
    # day's first slot was taken; it wins over the currently configured one,
    # which may have been edited mid-day.
    return QuotaUsageView(
        provider=provider,
        quota_date=usage.quota_date,
        used=usage.used,
        limit_value=usage.limit_value,
        remaining=usage.remaining,
        reset_tz=reset_tz,
        notes=notes,
    )


def _net_worth_view(settings: AppSettings, *, warnings: list[str]) -> NetWorthView:
    """The freshness block, from the clock only -- no prices are fetched here."""
    stored = settings.net_worth
    reported = self_reported_net_worth(stored.total_net_worth_twd, stored.updated_at)
    if reported is None:
        return NetWorthView(
            total_net_worth_twd=stored.total_net_worth_twd,
            updated_at=stored.updated_at,
            age_days=None,
            freshness="absent",
            notes=[NET_WORTH_ABSENT_NOTE, NET_WORTH_CURRENCY_NOTE],
            warnings=warnings,
        )

    notes = [NET_WORTH_CURRENCY_NOTE]
    freshness: NetWorthFreshness = "fresh"
    if reported.age_days >= NET_WORTH_STALE_AFTER_DAYS:
        freshness = "expired"
        notes.insert(
            0,
            NET_WORTH_EXPIRED_NOTE.format(
                days=NET_WORTH_STALE_AFTER_DAYS, age_days=reported.age_days
            ),
        )
    elif reported.age_days >= NET_WORTH_SOFT_NOTICE_DAYS:
        freshness = "ageing"
        notes.insert(
            0,
            NET_WORTH_AGEING_NOTE.format(
                age_days=reported.age_days, days=NET_WORTH_STALE_AFTER_DAYS
            ),
        )
    return NetWorthView(
        total_net_worth_twd=reported.amount_twd,
        updated_at=reported.reported_at,
        age_days=reported.age_days,
        freshness=freshness,
        notes=notes,
        warnings=warnings,
    )


def _response(
    settings: AppSettings,
    ledger: QuotaLedger,
    *,
    net_worth_warnings: list[str] | None = None,
    net_worth_notes: list[str] | None = None,
) -> SettingsResponse:
    verified = settings.cost_model.rates_verified
    view = _net_worth_view(settings, warnings=net_worth_warnings or [])
    if net_worth_notes:
        view = view.model_copy(update={"notes": [*view.notes, *net_worth_notes]})
    return SettingsResponse(
        settings=settings,
        rates_verified=verified,
        notes=[] if verified else [RATE_PROVENANCE_NOTE],
        data_sources=DataSourcesView(quotas=[_alpha_vantage_quota(ledger)]),
        net_worth=view,
        as_of=now_iso(),
    )


def _review_reported_net_worth(
    amount_twd: float, positions: PositionStore, valuator: PositionValuator
) -> NetWorthReview:
    """Run the FR-9 (c) bands against the currently valued book.

    The book is valued here and nowhere else in this router, so the cost is
    paid only by a request that actually reports a net worth.
    """
    summary = build_summary(positions, valuator)
    valued = [
        position for position in summary.positions if position.valuation.status == "ok"
    ]
    return review_net_worth(
        amount_twd,
        valued_market_value_twd=float(summary.totals.market_value_twd),
        valued_count=len(valued),
        total_count=len(summary.positions),
    )


@router.get("", response_model=SettingsResponse)
def read_settings(store: SettingsDep, ledger: QuotaDep) -> SettingsResponse:
    return _response(store.load(), ledger)


@router.put("", response_model=SettingsResponse)
def write_settings(
    body: AppSettingsPatch,
    store: SettingsDep,
    ledger: QuotaDep,
    positions: PositionStoreDep,
    valuator: ValuatorDep,
) -> SettingsResponse:
    current = store.load()
    if body.net_worth is None:
        return _response(store.save(body.apply_to(current)), ledger)

    amount = body.net_worth.total_net_worth_twd
    review = _review_reported_net_worth(amount, positions, valuator)
    if review.rejection is not None:
        # Refused outright, and nothing is written: the stored figure keeps
        # standing rather than being replaced by one that would make the cap
        # permanently violated.
        logger.info("net worth rejected: reported=%.2f", amount)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=review.rejection
        )

    saved = store.save(body.apply_to(current))
    # FR-9 (d): no history table, but the change does leave a trace.
    logger.info(
        "net worth updated: previous=%s new=%.2f at=%s warnings=%d",
        current.net_worth.total_net_worth_twd,
        amount,
        saved.net_worth.updated_at,
        len(review.warnings),
    )
    return _response(
        saved, ledger, net_worth_warnings=review.warnings, net_worth_notes=review.notes
    )
