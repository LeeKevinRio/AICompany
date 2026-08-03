"""Read/write the persisted risk budget, cost model and alert settings.

The response also carries a read-only data-source block (ADR-0005 決策三 point
6): today's Alpha Vantage ``used`` / ``limit_value`` / ``quota_date`` straight
out of :class:`app.data.quota.QuotaLedger`. It is strictly an observation --
this endpoint never reserves a slot, never writes to the ledger, and holds no
opinion on the budget; the gating decision stays where it is, inside the
adapter.

``PUT`` takes any subset of the three sections; an omitted section is left
untouched rather than reset. Each section is validated by its own pydantic model
(:mod:`app.settings.models`), so a bad value fails with a 422 naming the field
instead of being clamped into range -- a silently clamped risk cap is exactly
the kind of number a user would later believe they had set.

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
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.common import now_iso
from app.api.deps import get_quota_ledger, get_settings_store
from app.data.providers.alpha_vantage import AlphaVantageAdapter
from app.data.quota import (
    DEFAULT_RESET_TZ,
    QuotaConfigError,
    QuotaLedger,
    current_quota_date,
    resolve_quota_config,
)
from app.settings.models import AppSettings, AppSettingsPatch
from app.settings.store import SettingsStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

SettingsDep = Annotated[SettingsStore, Depends(get_settings_store)]
QuotaDep = Annotated[QuotaLedger, Depends(get_quota_ledger)]

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


class SettingsResponse(BaseModel):
    """The settings document plus its data-source block and ``as_of`` stamp."""

    model_config = ConfigDict(frozen=True)

    settings: AppSettings
    rates_verified: bool
    notes: list[str]
    data_sources: DataSourcesView
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


def _response(settings: AppSettings, ledger: QuotaLedger) -> SettingsResponse:
    verified = settings.cost_model.rates_verified
    return SettingsResponse(
        settings=settings,
        rates_verified=verified,
        notes=[] if verified else [RATE_PROVENANCE_NOTE],
        data_sources=DataSourcesView(quotas=[_alpha_vantage_quota(ledger)]),
        as_of=now_iso(),
    )


@router.get("", response_model=SettingsResponse)
def read_settings(store: SettingsDep, ledger: QuotaDep) -> SettingsResponse:
    return _response(store.load(), ledger)


@router.put("", response_model=SettingsResponse)
def write_settings(
    body: AppSettingsPatch, store: SettingsDep, ledger: QuotaDep
) -> SettingsResponse:
    return _response(store.save(body.apply_to(store.load())), ledger)
