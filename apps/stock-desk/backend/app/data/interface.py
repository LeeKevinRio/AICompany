"""Abstract data-layer interface shared by every market data provider.

Design rule (see ``.claude/skills/data-source-integration/SKILL.md`` and
ADR-0002 "所有市場資料存取走 MarketDataProvider 抽象介面"): callers never talk
to a vendor SDK directly. They talk to ``MarketDataProvider`` /
``MarketDataService``, and every object that crosses this boundary carries
``as_of`` (when the data was produced/fetched) and ``source`` (who produced
it) so staleness and provenance are always answerable questions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, field_validator

Market = Literal["TW", "US"]


class DataStatus(StrEnum):
    """Where in the four-layer degradation ladder a response came from.

    fresh        -- served live by the primary provider.
    backup       -- primary failed or was empty; served live by a backup.
    cached_stale -- all live providers failed; served from local SQLite cache.
    unavailable  -- no live provider and no usable cache entry either.
    """

    FRESH = "fresh"
    BACKUP = "backup"
    CACHED_STALE = "cached_stale"
    UNAVAILABLE = "unavailable"


class PriceBar(BaseModel):
    """One OHLCV daily bar for a single symbol.

    Every bar is self-describing: it always knows which market/currency it
    is quoted in, when it was retrieved (``as_of``), and which adapter
    produced it (``source``). Nothing in this model is ever synthesized or
    interpolated by the data layer -- values come straight from the
    upstream provider.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    market: Market
    date: date_type
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    currency: str
    as_of: datetime
    source: str

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware (UTC)")
        return value

    @field_validator("volume")
    @classmethod
    def _volume_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("volume must be non-negative")
        return value

    @field_validator("symbol", "source", "currency")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value


class ProviderResult(BaseModel):
    """Envelope returned by every ``MarketDataProvider.get_daily_bars`` call."""

    model_config = ConfigDict(frozen=True)

    bars: list[PriceBar]
    status: DataStatus
    as_of: datetime
    source: str
    staleness_minutes: int | None = None

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware (UTC)")
        return value

    @field_validator("staleness_minutes")
    @classmethod
    def _staleness_must_be_non_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("staleness_minutes must be non-negative")
        return value


class MarketDataProvider(ABC):
    """Abstract adapter for a daily-bar market data source.

    Every concrete provider (TWSE, TPEx, FinMind, ...) implements this same
    interface so ``MarketDataService`` never needs to know which vendor
    answered a given request; providers are interchangeable.
    """

    #: Short machine-readable identifier written into ``PriceBar.source``.
    source_id: ClassVar[str]

    @abstractmethod
    def get_daily_bars(
        self, symbol: str, start: date_type, end: date_type
    ) -> ProviderResult:
        """Return daily OHLCV bars for ``symbol`` within ``[start, end]``.

        Implementations must not raise for *expected* failure modes (network
        errors, missing credentials, empty upstream result, unexpected
        response shape); they must instead return a ``ProviderResult`` with
        ``status=DataStatus.UNAVAILABLE`` and an empty ``bars`` list, and log
        the reason. Truly unexpected bugs may still propagate as exceptions,
        which is why ``MarketDataService`` also guards each provider call.
        """
        raise NotImplementedError
