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

from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.positions.sectors import (
    SECTOR_REJECTED_MESSAGE,
    SECTOR_US_REJECTED_MESSAGE,
    is_valid_sector,
)

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


#: Positivity refusals shared by every door that writes a quantity or a cost
#: (``POST``/``PUT``, ``PATCH``), so all of them turn a zero down with the same
#: sentence. The CSV importer builds the same sentence from its own label.
QUANTITY_NOT_POSITIVE_MESSAGE: Final = "數量必須大於 0"
AVG_COST_NOT_POSITIVE_MESSAGE: Final = "平均成本必須大於 0"

#: Refusals for a ``PATCH`` that names a required field but sends ``null``: the
#: column cannot be cleared, and "unchanged" is said by omitting the field.
QUANTITY_REQUIRED_MESSAGE: Final = "數量不可空白"
AVG_COST_REQUIRED_MESSAGE: Final = "平均成本不可空白"

#: The currency a holding's cost must be stated in, per market. The valuation
#: engine picks the price source and the FX leg from ``market`` and reads the
#: cost basis in ``currency``; a row where the two disagree is valued wrongly
#: rather than refused, so the write doors refuse it instead.
MARKET_CURRENCY: Final[Mapping[str, str]] = {"TW": "TWD", "US": "USD"}

#: Wording approved verbatim by risk-compliance-officer on 2026-10-03 (fourth
#: review in work/reviews/2026-10-03-庫存頁-字面-風控確認.md); kept in one
#: constant so the API model and the CSV importer cannot drift apart.
CURRENCY_MARKET_MISMATCH_MESSAGE: Final = "幣別與市場不符：台股（TW）須為 TWD，美股（US）須為 USD"

# Error ``type`` codes. The ``msg`` a client renders is the sentence alone;
# a client that wants to branch reads ``type``.
_SYMBOL_BLANK_ERROR_TYPE = "position_symbol_blank"
_SYMBOL_INDEX_ERROR_TYPE = "position_symbol_is_index"
_QUANTITY_ERROR_TYPE = "position_quantity_not_positive"
_AVG_COST_ERROR_TYPE = "position_avg_cost_not_positive"
_QUANTITY_REQUIRED_ERROR_TYPE = "position_quantity_required"
_AVG_COST_REQUIRED_ERROR_TYPE = "position_avg_cost_required"
_OPENED_AT_ERROR_TYPE = "position_opened_at_in_future"
_SECTOR_ERROR_TYPE = "position_sector_not_listed"
_SECTOR_US_ERROR_TYPE = "position_sector_us_not_allowed"
_CURRENCY_MARKET_ERROR_TYPE = "position_currency_market_mismatch"


def _refuse(error_type: str, message: str) -> PydanticCustomError:
    """A validation error whose ``msg`` is ``message`` verbatim.

    :class:`~pydantic_core.PydanticCustomError` rather than ``ValueError``
    (qa B2, same fix as :mod:`app.kelly.models`): pydantic v2 prefixes a plain
    ``ValueError`` with ``"Value error, "``, and the front end renders
    ``detail[].msg`` as it arrives. No context is passed, so the message is not
    run through template substitution either.
    """
    return PydanticCustomError(error_type, message)


def check_quantity(value: Decimal) -> Decimal:
    """Refuse a non-positive quantity; shared by the full and the partial write."""
    if value <= 0:
        raise _refuse(_QUANTITY_ERROR_TYPE, QUANTITY_NOT_POSITIVE_MESSAGE)
    return value


def check_avg_cost(value: Decimal) -> Decimal:
    """Refuse a non-positive average cost; shared by the full and the partial write."""
    if value <= 0:
        raise _refuse(_AVG_COST_ERROR_TYPE, AVG_COST_NOT_POSITIVE_MESSAGE)
    return value


def currency_matches_market(market: str, currency: str) -> bool:
    """Whether ``currency`` is the one :data:`MARKET_CURRENCY` assigns ``market``."""
    return MARKET_CURRENCY.get(market) == currency


class PositionInput(BaseModel):
    """The user-supplied fields of a position (everything except id/timestamps).

    The validated shape a CSV import row must satisfy before it is stored, and
    the base of :class:`PositionWriteInput` (the ``POST``/``PUT`` body).

    Carries no cross-field market/currency rule on purpose (tech-architect C3):
    :class:`Position` inherits these validators and is rebuilt from every
    stored row, so a rule added here would turn a legacy mismatched row into a
    500 on every read instead of a row the user can still see and fix.
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
    #: Optional TWSE industry category (FR-12). ``None`` means "not stated" and
    #: is never guessed from the symbol: the sector cap then reports
    #: ``not_evaluable`` for this holding rather than filing it somewhere. Only
    #: TW holdings may carry one (see :mod:`app.positions.sectors`).
    sector: str | None = None
    note: str | None = None

    @field_validator("sector")
    @classmethod
    def _sector_must_be_a_known_category(cls, value: str | None) -> str | None:
        """Reject free text: an unrecognised category is a rejected write, not a
        new bucket (AC-12.1). A blank cell is read as "not stated"."""
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if not is_valid_sector(cleaned):
            raise _refuse(_SECTOR_ERROR_TYPE, SECTOR_REJECTED_MESSAGE)
        return cleaned

    @model_validator(mode="after")
    def _sector_is_tw_only(self) -> PositionInput:
        if self.market != "TW" and self.sector is not None:
            raise _refuse(_SECTOR_US_ERROR_TYPE, SECTOR_US_REJECTED_MESSAGE)
        return self

    @field_validator("symbol")
    @classmethod
    def _symbol_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise _refuse(_SYMBOL_BLANK_ERROR_TYPE, "股票代號不可空白")
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
            raise _refuse(_SYMBOL_INDEX_ERROR_TYPE, INDEX_SYMBOL_REJECTED_MESSAGE)
        return value

    @field_validator("quantity")
    @classmethod
    def _quantity_must_be_positive(cls, value: Decimal) -> Decimal:
        return check_quantity(value)

    @field_validator("avg_cost")
    @classmethod
    def _avg_cost_must_be_positive(cls, value: Decimal) -> Decimal:
        return check_avg_cost(value)

    @field_validator("opened_at")
    @classmethod
    def _opened_at_must_not_be_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > datetime.now(UTC).date():
            raise _refuse(_OPENED_AT_ERROR_TYPE, "建倉日期不可晚於今天")
        return value


class PositionWriteInput(PositionInput):
    """The ``POST``/``PUT`` body and the CSV row model: :class:`PositionInput`
    plus market/currency agreement and blank-note normalisation.

    The agreement rule lives on this subclass, not on :class:`PositionInput`
    (C3), so it guards new writes without making a legacy mismatched row
    unreadable. A field validator rather than a model validator so the 422
    points at ``("body", "currency")`` -- the field the user has to change.
    """

    @field_validator("currency")
    @classmethod
    def _currency_must_match_market(cls, value: str, info: ValidationInfo) -> str:
        market = info.data.get("market")
        # A market that failed its own validation is reported there; there is
        # nothing to compare against.
        if market is not None and not currency_matches_market(market, value):
            raise _refuse(_CURRENCY_MARKET_ERROR_TYPE, CURRENCY_MARKET_MISMATCH_MESSAGE)
        return value

    @field_validator("note")
    @classmethod
    def _blank_note_is_unstated(cls, value: str | None) -> str | None:
        """Store a blank note as NULL (ADR-0017 D-8), as ``PATCH`` and the CSV do.

        On the write model only, not on :class:`PositionInput`: normalising
        there would also rewrite what :class:`Position` reports for a stored
        row, which is a read, not a write.
        """
        if value is None or not value.strip():
            return None
        return value


class PositionPatch(BaseModel):
    """The ``PATCH`` body: the fields the inventory page edits in place.

    Only what the user typed is written (see :meth:`changes`), so a background
    write to another column -- the sector backfill -- between the page's read
    and this write survives, which a full ``PUT`` would overwrite.

    * a field left out stays as stored;
    * ``quantity`` / ``avg_cost`` sent as ``null`` is refused: both columns are
      required, and "leave it alone" is said by omitting the field;
    * ``note`` sent as ``null`` or blank clears the note.

    Any other field (``symbol``, ``market``, ``currency``, ``sector``...) is
    refused rather than ignored, so a client cannot believe it changed one.
    No market/currency check: neither can change through this door.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    quantity: Decimal | None = None
    avg_cost: Decimal | None = None
    note: str | None = None

    @field_validator("quantity")
    @classmethod
    def _quantity_present_and_positive(cls, value: Decimal | None) -> Decimal:
        if value is None:
            raise _refuse(_QUANTITY_REQUIRED_ERROR_TYPE, QUANTITY_REQUIRED_MESSAGE)
        return check_quantity(value)

    @field_validator("avg_cost")
    @classmethod
    def _avg_cost_present_and_positive(cls, value: Decimal | None) -> Decimal:
        if value is None:
            raise _refuse(_AVG_COST_REQUIRED_ERROR_TYPE, AVG_COST_REQUIRED_MESSAGE)
        return check_avg_cost(value)

    @field_validator("note")
    @classmethod
    def _blank_note_clears(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value

    def changes(self) -> dict[str, Decimal | str | None]:
        """The fields the client actually sent, keyed by column name.

        Uses ``model_fields_set`` so an omitted field is absent here, while an
        explicit ``null`` note is present as ``None`` (meaning: clear it).
        """
        return {name: getattr(self, name) for name in sorted(self.model_fields_set)}


class Position(PositionInput):
    """A stored position: user fields plus its id and audit timestamps."""

    id: int
    created_at: datetime
    updated_at: datetime
