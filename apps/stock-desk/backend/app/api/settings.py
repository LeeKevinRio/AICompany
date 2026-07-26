"""Read/write the persisted risk budget, cost model and alert settings.

``PUT`` takes any subset of the three sections; an omitted section is left
untouched rather than reset. Each section is validated by its own pydantic model
(:mod:`app.settings.models`), so a bad value fails with a 422 naming the field
instead of being clamped into range -- a silently clamped risk cap is exactly
the kind of number a user would later believe they had set.

The risk-budget bounds are the ones declared on
:class:`app.advice.limits.RiskBudget` and are reused unchanged: fractional Kelly
stays at most a quarter and the hard Kelly ceiling at most 10%, whatever the
settings page asks for.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.common import now_iso
from app.api.deps import get_settings_store
from app.settings.models import AppSettings, AppSettingsPatch
from app.settings.store import SettingsStore

router = APIRouter(prefix="/api/settings", tags=["settings"])

SettingsDep = Annotated[SettingsStore, Depends(get_settings_store)]

RATE_PROVENANCE_NOTE = (
    "cost_model 的預設費率尚未經主要來源查證（verified_on 為 null）；"
    "查證後請更新 verified_on 與各項費率。"
)


class SettingsResponse(BaseModel):
    """The settings document plus its ``as_of`` stamp."""

    model_config = ConfigDict(frozen=True)

    settings: AppSettings
    rates_verified: bool
    notes: list[str]
    as_of: str


def _response(settings: AppSettings) -> SettingsResponse:
    verified = settings.cost_model.rates_verified
    return SettingsResponse(
        settings=settings,
        rates_verified=verified,
        notes=[] if verified else [RATE_PROVENANCE_NOTE],
        as_of=now_iso(),
    )


@router.get("", response_model=SettingsResponse)
def read_settings(store: SettingsDep) -> SettingsResponse:
    return _response(store.load())


@router.put("", response_model=SettingsResponse)
def write_settings(body: AppSettingsPatch, store: SettingsDep) -> SettingsResponse:
    return _response(store.save(body.apply_to(store.load())))
