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
    """Envelope returned by every ``MarketDataProvider.get_daily_bars`` call.

    ``is_within_ttl`` (ADR-0005 決策四 "TTL 內快取先行", freshness rule revised
    by ADR-0009): whether the served cache already holds the latest session
    the market has completed and published -- ``True`` means "as current as a
    live fetch would be", ``False`` means the cache is known to be short of at
    least one session (served anyway, disclosed as stale). It is meaningful only
    for ``status=CACHED_STALE`` responses and is ``None`` for any live source
    (``FRESH``/``BACKUP``) and for ``UNAVAILABLE``, where "within TTL" is not
    a question that applies. This does **not** add a fifth ``DataStatus`` --
    ADR-0005 explicitly rejected that option to keep the blast radius small --
    so a ``CACHED_STALE`` response with ``is_within_ttl=True`` still means
    "served from the local cache", just one that happens to still be fresh
    enough to trust without re-fetching; a front end must read both fields to
    render an honest freshness message (決策四 point 4).

    ``reason`` is an optional, user-facing Traditional Chinese sentence
    explaining *why* a response degraded (quota exhausted, ticker not found,
    ambiguous "no data" from an upstream that cannot distinguish "symbol does
    not exist" from "temporarily no data", ...). It is ``None`` on ordinary
    success. Wiring it into API responses / UI copy is outside this data
    layer's file ownership (see ``app/services/market.py`` /
    ``app/api/*``); it exists here so that information is not lost at the
    point it is first known.
    """

    model_config = ConfigDict(frozen=True)

    bars: list[PriceBar]
    status: DataStatus
    as_of: datetime
    source: str
    staleness_minutes: int | None = None
    is_within_ttl: bool | None = None
    reason: str | None = None
    #: ``False`` when the provider answered for only part of the requested
    #: range (a month endpoint failed and was skipped) but still had bars to
    #: return. The service then writes what came back through to the cache but
    #: does **not** record the range as covered, so the hole is re-fetched on
    #: the next request instead of being frozen in by layer 0 (ADR-0009 R-4).
    #: The service propagates it on the result it returns; surfacing it on the
    #: API's ``data`` block is a follow-up, not yet wired.
    complete: bool = True

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
    def get_daily_bars(self, symbol: str, start: date_type, end: date_type) -> ProviderResult:
        """Return daily OHLCV bars for ``symbol`` within ``[start, end]``.

        Implementations must not raise for *expected* failure modes (network
        errors, missing credentials, empty upstream result, unexpected
        response shape); they must instead return a ``ProviderResult`` with
        ``status=DataStatus.UNAVAILABLE`` and an empty ``bars`` list, and log
        the reason. Truly unexpected bugs may still propagate as exceptions,
        which is why ``MarketDataService`` also guards each provider call.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# ADR-0012 D-3: whole-market snapshot provider (forward-looking PIT capture).
# ---------------------------------------------------------------------------
#
# This is a second, independent provider shape living next to
# ``MarketDataProvider`` above (ADR-0012 §7 "把「走 MarketDataProvider」擴充
# 解讀為「走 app/data 內可替換的抽象介面」"). ``MarketDataProvider`` answers
# "one symbol, one date range"; a whole-market snapshot source such as TWSE's
# ``STOCK_DAY_ALL`` only ever answers "today, every symbol" -- there is no
# date parameter to ask it about because it cannot be asked about a different
# day (unlike ``MI_INDEX``, which if ever verified usable would get its own,
# differently-shaped provider).

#: One capture batch always covers exactly these four kinds together (D-2):
#: ``STOCK_DAY_ALL``, ``t187ap03_L`` and ``TWT48U_ALL`` are each "current
#: state" endpoints with no queryable history, so one provider call captures
#: all four for the same trading session at once.
SnapshotKind = Literal["bars", "listing", "classification", "dividend_announce"]

#: ``pit_snapshot_runs.status`` domain (D-2). A concrete
#: ``MarketSnapshotProvider`` only ever produces ``"ok"`` (fetched, parsed,
#: and -- for the batch as a whole -- the trading session was self-certified)
#: or ``"failed"`` (any structural failure, including a failed self-certified
#: date). ``"partial"`` (coverage below the 0.98 threshold) and
#: ``"quality_failed"`` (future dates, duplicate symbols, ...) are judgements
#: that need the PIT-visible listing size and the store's other rows to make,
#: so they are assigned by ``app.services.pit_snapshot`` after the fact, never
#: by the provider itself.
SnapshotRunStatus = Literal["ok", "partial", "failed", "quality_failed"]


class BarSnapshotRow(BaseModel):
    """One symbol's row out of a whole-market daily-bar snapshot.

    Deliberately not ``PriceBar``: this is share-normalized market-wide
    snapshot data (``shares``/``traded_value``, ADR-0012 D-2), not a
    per-symbol series bar, and it never touches ``price_bars_cache`` (C-7).
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    #: Always normalized to shares (1 張 = 1,000 股); see
    #: ``app.data.providers.twse_snapshot`` for the header-driven detection.
    shares: int
    traded_value: Decimal
    #: ``None`` when the source did not report a change figure for this row.
    #: Whether this is measured against the ex-dividend reference price is
    #: DE-5, unverified -- see
    #: ``app.data.providers.twse_snapshot.CHANGE_SEMANTICS_VERIFIED_ON``.
    change: Decimal | None

    @field_validator("shares")
    @classmethod
    def _shares_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("shares must be non-negative")
        return value


class ListingSnapshotRow(BaseModel):
    """One symbol captured as "listed and classifiable" on the snapshot day.

    Membership is the forward-filtering intersection of ``STOCK_DAY_ALL``'s
    same-day symbol set and ``t187ap03_L``'s symbol set (ADR-0012 D-3) --
    an allow-list, never a deny-list guess at "this looks like an ETF".
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    security_type: str


class ClassificationSnapshotRow(BaseModel):
    """One symbol's official TWSE industry classification, as captured that day."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    sector_code: str
    sector_name: str


class DividendAnnounceSnapshotRow(BaseModel):
    """One raw ``TWT48U_ALL`` row, kept verbatim (D-2: "保存全部原始欄位").

    ``ex_date`` is a best-effort parse of ``raw["Date"]`` using the same
    ROC-date parser ``app.dividends.providers.parse_twse_date`` already uses.
    It is ``None`` when that specific row's date could not be parsed -- the
    row is still captured under ``raw`` for provenance (this table is a
    faithful record of what TWSE published, not a filtered feed), but it is
    then excluded from the ``ex_dividend`` ``PanelFrame`` the sector core
    reads, since a dateless row cannot drive the look-ahead-free exclusion
    window (D-4).
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    ex_date: date_type | None
    raw: dict[str, str]


class SnapshotKindOutcome(BaseModel):
    """Per-kind outcome inside one ``SnapshotResult`` (mirrors ``pit_snapshot_runs`` columns).

    ``expected_count`` is always ``None`` here: a provider does not know the
    PIT-visible listing size that ``bars`` coverage needs (that requires
    reading the store), so it is filled in by
    ``app.services.pit_snapshot`` before the run is written.
    """

    model_config = ConfigDict(frozen=True)

    status: SnapshotRunStatus
    row_count: int
    expected_count: int | None = None
    reason: str | None = None


class SnapshotResult(BaseModel):
    """Everything one ``MarketSnapshotProvider.get_latest_snapshot()`` call produced.

    ``session_date`` is self-certified (ADR-0012 D-3/C-12), never
    clock-derived: it is read straight off the payload when the payload
    carries a trading date, otherwise it is the *candidate* date that passed
    a FinMind cross-check on a small symbol sample. ``session_date is None``
    means self-certification failed outright, in which case every kind's
    outcome must be ``"failed"`` and every ``*_rows`` tuple must be empty --
    there is no trustworthy day to attach any row to.

    The four kinds share one ``session_date``/``as_of``/``source`` because
    they are read from three "current state" endpoints in the same batch
    (module docstring above); an individual kind can still fail on its own
    (e.g. the ``TWT48U_ALL`` request errors while ``STOCK_DAY_ALL`` and
    ``t187ap03_L`` succeed) without invalidating the others' certified date.
    """

    model_config = ConfigDict(frozen=True)

    as_of: datetime
    source: str
    session_date: date_type | None
    #: ``True`` when the payload itself carried the trading date (DE-1',
    #: confirmed); ``False`` when the date came from the FinMind cross-check
    #: fallback. Meaningless (``False``) when ``session_date is None``.
    session_date_self_certified: bool

    bars: SnapshotKindOutcome
    bars_rows: tuple[BarSnapshotRow, ...] = ()
    listing: SnapshotKindOutcome
    listing_rows: tuple[ListingSnapshotRow, ...] = ()
    classification: SnapshotKindOutcome
    classification_rows: tuple[ClassificationSnapshotRow, ...] = ()
    dividend_announce: SnapshotKindOutcome
    dividend_announce_rows: tuple[DividendAnnounceSnapshotRow, ...] = ()

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware (UTC)")
        return value

    @field_validator("source")
    @classmethod
    def _source_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source must not be blank")
        return value


class MarketSnapshotProvider(ABC):
    """Abstract adapter for a whole-market, same-day snapshot source.

    Unlike ``MarketDataProvider``, this has no ``start``/``end`` parameters:
    the underlying endpoints (``STOCK_DAY_ALL``, ``t187ap03_L``,
    ``TWT48U_ALL``) only ever answer for "today" (ADR-0012 D-3).
    """

    #: Short machine-readable identifier written into every run's ``source``.
    source_id: ClassVar[str]

    @abstractmethod
    def get_latest_snapshot(self) -> SnapshotResult:
        """Fetch and self-certify one day's bundle of the four PIT snapshot kinds.

        Must not raise for expected failure modes (network errors, unexpected
        response shape, a self-certification that comes back inconclusive);
        those come back as a per-kind ``status="failed"`` with a Traditional
        Chinese ``reason``, never an exception -- one kind failing must not
        take down the others (mirrors ``MarketDataProvider.get_daily_bars``'s
        discipline, and ADR-0012 D-5 "四種 kind 各自獨立成敗").
        """
        raise NotImplementedError
