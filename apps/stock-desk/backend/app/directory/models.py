"""Pydantic models for the security directory.

Mirrors ``app.data.interface.PriceBar``'s provenance discipline: every entry
carries ``as_of`` (when this row's data was retrieved from the upstream
source) and ``source`` (which adapter produced it), so staleness and
provenance stay answerable questions for directory data too, not just price
bars.

The industry category (``sector``) carries its *own* provenance triple rather
than riding on the row's, because it comes from a different TWSE dataset
(``t187ap03_L``) fetched in a separate request from the symbol/name source
(``STOCK_DAY_ALL``) -- one ``as_of`` covering both would silently claim the
sector was retrieved at the moment the name was.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.data.interface import Market


class DirectoryEntry(BaseModel):
    """One 代號 -> 公司名稱 -> 市場 (-> 產業別) row.

    ``market`` reuses the same ``Literal["TW", "US"]`` the rest of the
    codebase already uses (``app.positions.models.Market`` /
    ``app.data.interface.Market``) rather than inventing a directory-specific
    type. Only ``"TW"`` is ever written this phase (PRD Q2 裁示: 美股第一期
    不收錄公司名稱), but keeping the type generic means a later US directory
    source does not need a model change.

    ``sector`` is ``None`` for everything the sector source does not cover --
    上櫃 (TPEx) rows and ETFs are never in ``t187ap03_L``, so their category
    stays NULL rather than being guessed from the symbol or copied from a
    neighbouring row.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    market: Market
    source: str
    as_of: datetime
    #: Resolved TWSE industry-category *name* (never the raw two-digit code),
    #: always one of ``app.positions.sectors.TWSE_SECTORS``. ``None`` means
    #: "this source has no category for this security" -- see the class
    #: docstring; it never means "unclassified".
    sector: str | None = None
    sector_source: str | None = None
    sector_as_of: datetime | None = None

    @field_validator("as_of", "sector_as_of")
    @classmethod
    def _as_of_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware (UTC)")
        return value

    @field_validator("symbol", "name", "source")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def _sector_provenance_is_all_or_nothing(self) -> DirectoryEntry:
        """A stored category without its source/as_of would be unattributable.

        Rejecting the half-filled shape at the model boundary means no caller
        can persist a category whose origin and retrieval time are unknown,
        which is what the disclosure copy next to the form field relies on.
        """
        provenance = (self.sector, self.sector_source, self.sector_as_of)
        if any(part is not None for part in provenance) and not all(
            part is not None for part in provenance
        ):
            raise ValueError("sector, sector_source and sector_as_of must be set together")
        return self


class DirectorySectorAssignment(BaseModel):
    """One resolved ``代號 -> 產業別`` fact, ready to be written onto a row.

    Deliberately separate from :class:`DirectoryEntry`: the sector source
    (``t187ap03_L``) publishes no price/quote row, so it can only ever update
    the category of a security the *directory* source already listed -- it is
    not itself a directory of what exists. Modelling it as a partial
    ``DirectoryEntry`` would invite writing a name from the wrong dataset.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    market: Market
    sector: str
    source: str
    as_of: datetime

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware (UTC)")
        return value

    @field_validator("symbol", "sector", "source")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value
