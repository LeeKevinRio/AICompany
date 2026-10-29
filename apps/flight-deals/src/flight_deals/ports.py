"""Ports: interfaces the services depend on; adapters implement them."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from flight_deals.domain.models import FlightSearch, PriceKind, PriceQuote, QueryStatus

Redactor = Callable[[str], str]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class ParseStats:
    """Per-response itinerary counts from a payload parser (all non-negative ints).

    ``unpriced`` itineraries carry no price at all and are skipped silently;
    ``malformed`` ones had a shape the parser did not recognise. ``itineraries`` counts
    the merged list after de-duplication; ``best`` / ``other`` are the raw lengths of
    the two result sections before merging.
    """

    itineraries: int
    priced: int
    unpriced: int
    malformed: int
    best: int = 0
    other: int = 0


@dataclass(frozen=True)
class SourceResult:
    """Outcome of one search against one source.

    ``blocked`` means the source answered with nothing usable (blank page, parse
    failure); it must never be recorded as "no flights". ``attempts`` counts outbound
    requests actually made (0 when served from cache).
    """

    source: str
    status: QueryStatus
    fetched_at: datetime
    quotes: tuple[PriceQuote, ...] = ()
    error: str | None = None
    attempts: int = 1
    from_cache: bool = False
    extra: dict[str, str] = field(default_factory=dict)
    parse_stats: ParseStats | None = None

    @property
    def is_failure(self) -> bool:
        return self.status in ("blocked", "error")


class FlightPriceSource(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def price_kind(self) -> PriceKind: ...

    def search(self, query: FlightSearch) -> SourceResult: ...


@dataclass(frozen=True)
class SendResult:
    ok: bool
    error: str | None = None


class Notifier(Protocol):
    @property
    def channel(self) -> str: ...

    def is_configured(self) -> bool: ...

    def send(self, text: str) -> SendResult: ...


@dataclass(frozen=True)
class AutostartStatus:
    """Login autostart entry: present at all, and pointing at this checkout."""

    registered: bool
    points_here: bool


class AutostartProbe(Protocol):
    def status(self) -> AutostartStatus | None:
        """None when the state cannot be determined (not Windows, access error)."""
        ...


class BookingLinkBuilder(Protocol):
    """Exact booking-search URL for one query (ADR-0002 FD-5 Decision 7).

    Implementations must not fetch anything. None (or an exception, which callers
    contain) means the caller falls back to the route-and-date search link.
    """

    def url(self, search: FlightSearch) -> str | None: ...


# ---- Telegram command inbox (ADR-0002 FD-7 Decision 1) -------------------------------

InboundKind = Literal["message", "edited_message", "other"]
InboxErrorKind = Literal[
    "unauthorized", "conflict", "rate_limited", "network", "http", "invalid_response"
]


@dataclass(frozen=True)
class InboundUpdate:
    """One inbound bot update, reduced to what command handling needs.

    ``text`` is None for non-text messages (stickers, photos, ...); ``chat_id`` and
    ``chat_type`` are None when the update carries no chat; ``sent_at`` is the message
    date (UTC) when Telegram supplied one.
    """

    update_id: int
    kind: InboundKind
    chat_id: int | None
    chat_type: str | None
    text: str | None
    sent_at: datetime | None


@dataclass(frozen=True)
class InboxResult:
    ok: bool
    updates: tuple[InboundUpdate, ...] = ()
    error: str | None = None
    error_kind: InboxErrorKind | None = None
    retry_after_seconds: int | None = None


class TelegramInbox(Protocol):
    """Long-poll reader of the bot's messages. Never raises; errors are redacted."""

    def get_updates(self, offset: int | None, long_poll_seconds: int) -> InboxResult: ...
