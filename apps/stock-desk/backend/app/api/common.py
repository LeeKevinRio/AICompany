"""Shared pieces of the API surface: the ``as_of`` stamp and the data envelope.

Every response object carries ``as_of`` (when it was produced) per the company
data convention, and every endpoint that reads market data carries a ``data``
block describing which layer of the degradation ladder answered. Both live here
so a new router cannot invent a third spelling of either.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

#: ``ok`` -- the payload was produced; ``insufficient_data`` -- the inputs were
#: not available and the payload is ``None`` with ``reason`` set. Both are 200:
#: "we could not compute this" is a state of the world, not a server fault.
PayloadStatus = Literal["ok", "insufficient_data"]


def now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat()


class DataMeta(BaseModel):
    """Provenance of the bars behind a response (``LoadedBars.meta``)."""

    model_config = ConfigDict(frozen=True)

    status: str
    source: str
    staleness_minutes: int | None
    bar_count: int
    first_bar_date: str | None
    last_bar_date: str | None
    reason: str | None


class EnvelopeBase(BaseModel):
    """Fields shared by every symbol-scoped response."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    market: str
    status: PayloadStatus
    reason: str | None
    data: DataMeta
    as_of: str


def data_meta(meta: dict[str, Any]) -> DataMeta:
    """Validate a ``LoadedBars.meta()`` mapping into the response model."""
    return DataMeta.model_validate(meta)
