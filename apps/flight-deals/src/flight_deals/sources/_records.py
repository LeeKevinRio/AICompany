"""Convert Google Flights result records (``dataclasses.asdict`` shape) into quotes."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from flight_deals.domain.currency import major_to_minor
from flight_deals.domain.models import PriceKind, PriceQuote


class RecordFormatError(ValueError):
    """A record does not have the expected shape (treated as ``blocked``)."""


_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d", re.ASCII)


def _depart_time(record: Mapping[str, Any]) -> str | None:
    """Optional "HH:MM" set by the payload parser; anything else is dropped."""
    value = record.get("depart_time")
    return value if isinstance(value, str) and _HHMM.fullmatch(value) else None


def _carrier(record: Mapping[str, Any]) -> str | None:
    airlines = record.get("airlines")
    if isinstance(airlines, list):
        names = [str(a) for a in airlines if str(a).strip()]
        if names:
            return "、".join(names)
    code = record.get("type")
    return str(code) if code else None


def _segments(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    segs = record.get("flights")
    if not isinstance(segs, list):
        raise RecordFormatError("record has no 'flights' list")
    return [s for s in segs if isinstance(s, Mapping)]


def quotes_from_records(
    records: Sequence[Mapping[str, Any]],
    *,
    source: str,
    price_kind: PriceKind,
    currency: str,
    depart_date: date,
    return_date: date | None,
    fetched_at: datetime,
) -> list[PriceQuote]:
    """Map raw records to ``PriceQuote``. Raises ``RecordFormatError`` on shape changes."""
    quotes: list[PriceQuote] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise RecordFormatError("record is not a mapping")
        price = record.get("price")
        if isinstance(price, bool) or not isinstance(price, int):
            raise RecordFormatError("price is not an integer")
        if price <= 0:
            # Google sometimes lists itineraries without a price; skip, never invent one.
            continue
        segs = _segments(record)
        durations = [s.get("duration") for s in segs]
        duration = (
            sum(d for d in durations if isinstance(d, int))
            if segs and all(isinstance(d, int) for d in durations)
            else None
        )
        quotes.append(
            PriceQuote(
                source=source,
                price_kind=price_kind,
                depart_date=depart_date,
                return_date=return_date,
                amount_minor=major_to_minor(price, currency),
                currency=currency,
                as_of=fetched_at,
                as_of_basis="fetch_time",
                fetched_at=fetched_at,
                carrier=_carrier(record),
                stops=len(segs) - 1 if segs else None,
                duration_minutes=duration,
                depart_time=_depart_time(record),
            )
        )
    return quotes
