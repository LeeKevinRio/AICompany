"""Pydantic models for a portfolio position.

A position is one holding the user tells us about by hand (we never invent
holdings). ``avg_cost`` is the average acquisition price in the instrument's
own currency -- it is treated as ``P0`` (the cost basis) by the valuation
engine, which then only fetches the *current* market price and the two FX
rates it needs; it never fetches or fabricates the cost.

Money amounts are ``Decimal`` and serialize to JSON strings (Pydantic v2's
default for ``Decimal``), never floats, so precision is preserved end to end
per the data convention.

User-facing validation messages are written in Traditional Chinese (Taiwan)
so they can be shown to the user verbatim; code and comments stay in English.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, field_validator

Market = Literal["TW", "US"]
Currency = Literal["TWD", "USD"]
InstrumentType = Literal["stock", "etf", "leveraged_etf", "futures_etf"]

#: ``^`` marks an index series (``^GSPC``, ``^TWII``), which ADR-0005 決策三
#: point 5 routes through its own :class:`app.services.index.IndexSeriesService`
#: and deliberately keeps out of ``canonical_us_symbol``. An index is a
#: benchmark, not something a broker can fill: accepting one here would create a
#: holding whose price ladder, cost basis and risk caps are all meaningless.
INDEX_SYMBOL_PREFIX: Final = "^"

#: Shared by the model validator and the CSV importer so both doors reject the
#: same input with the same sentence.
INDEX_SYMBOL_REJECTED_MESSAGE: Final = (
    "指數代號（以 ^ 開頭，例如 ^GSPC）是市場基準，不可作為持倉標的；"
    "請改填實際持有的股票或 ETF 代號。"
)


class PositionInput(BaseModel):
    """The user-supplied fields of a position (everything except id/timestamps).

    Used both as the ``POST``/``PUT`` request body and as the validated shape
    a CSV import row must satisfy before it is stored.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    symbol: str
    market: Market
    quantity: Decimal
    avg_cost: Decimal
    currency: Currency
    #: Optional: the user may not remember when the holding was opened. ``None``
    #: means "not stated" and is never replaced by a guessed date; downstream
    #: figures that need an open date report ``None`` instead.
    opened_at: date | None = None
    instrument_type: InstrumentType
    note: str | None = None

    @field_validator("symbol")
    @classmethod
    def _symbol_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("股票代號不可空白")
        return value

    @field_validator("symbol")
    @classmethod
    def _symbol_must_not_be_an_index(cls, value: str) -> str:
        """Reject index codes (ADR-0005 約束 Q-6).

        Mirrors ``canonical_us_symbol``'s rejection so the two entry points to a
        US ticker -- the position book and the price adapters -- agree on what a
        holding symbol may be.
        """
        if value.strip().startswith(INDEX_SYMBOL_PREFIX):
            raise ValueError(INDEX_SYMBOL_REJECTED_MESSAGE)
        return value

    @field_validator("quantity")
    @classmethod
    def _quantity_must_be_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("數量必須大於 0")
        return value

    @field_validator("avg_cost")
    @classmethod
    def _avg_cost_must_be_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("平均成本必須大於 0")
        return value

    @field_validator("opened_at")
    @classmethod
    def _opened_at_must_not_be_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > datetime.now(UTC).date():
            raise ValueError("建倉日期不可晚於今天")
        return value


class Position(PositionInput):
    """A stored position: user fields plus its id and audit timestamps."""

    id: int
    created_at: datetime
    updated_at: datetime
