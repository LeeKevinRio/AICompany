"""Pydantic model for one security-directory row.

Mirrors ``app.data.interface.PriceBar``'s provenance discipline: every entry
carries ``as_of`` (when this row's data was retrieved from the upstream
source) and ``source`` (which adapter produced it), so staleness and
provenance stay answerable questions for directory data too, not just price
bars.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.data.interface import Market


class DirectoryEntry(BaseModel):
    """One 代號 -> 公司名稱 -> 市場 row.

    ``market`` reuses the same ``Literal["TW", "US"]`` the rest of the
    codebase already uses (``app.positions.models.Market`` /
    ``app.data.interface.Market``) rather than inventing a directory-specific
    type. Only ``"TW"`` is ever written this phase (PRD Q2 裁示: 美股第一期
    不收錄公司名稱), but keeping the type generic means a later US directory
    source does not need a model change.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    market: Market
    source: str
    as_of: datetime

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware (UTC)")
        return value

    @field_validator("symbol", "name", "source")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value
