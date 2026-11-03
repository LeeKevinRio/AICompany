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

# Flight details (ADR-0002 FD-12, C-94): derived here only, never raise, never touch
# the price, stops, carrier, departure time, duration or query status.
MAX_DETAIL_SEGMENTS = 6
MIN_ARRIVE_DAY_OFFSET = -1
MAX_ARRIVE_DAY_OFFSET = 3
_AIRLINE_CODE = re.compile(r"[A-Z0-9]{2}", re.ASCII)
_FLIGHT_NUMBER = re.compile(r"[0-9]{1,4}", re.ASCII)
_AIRPORT_CODE = re.compile(r"[A-Z]{3}", re.ASCII)


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


def _text(segment: Mapping[str, Any], key: str) -> str | None:
    value = segment.get(key)
    return value if isinstance(value, str) else None


def _iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _flight_numbers(segs: Sequence[Mapping[str, Any]]) -> str | None:
    """ "BR184" / "CZ3088,CZ3575": every segment or nothing."""
    if not 1 <= len(segs) <= MAX_DETAIL_SEGMENTS:
        return None
    parts: list[str] = []
    for seg in segs:
        code, number = _text(seg, "code"), _text(seg, "number")
        if code is None or number is None:
            return None
        if not (_AIRLINE_CODE.fullmatch(code) and _FLIGHT_NUMBER.fullmatch(number)):
            return None
        parts.append(code + number)
    return ",".join(parts)


def _arrival(segs: Sequence[Mapping[str, Any]], depart_date: date) -> tuple[str | None, int | None]:
    """Local arrival "HH:MM" and day offset, both set or both None.

    The offset is the final airport's local arrival date minus the first segment's
    local departure date, which must be the queried departure date.
    """
    if not segs:
        return None, None
    arrive_time = _text(segs[-1], "arrive_time")
    if arrive_time is None or not _HHMM.fullmatch(arrive_time):
        return None, None
    first = _iso_date(segs[0].get("depart_date"))
    last = _iso_date(segs[-1].get("arrive_date"))
    if first is None or last is None or first != depart_date:
        return None, None
    offset = (last - first).days
    if not MIN_ARRIVE_DAY_OFFSET <= offset <= MAX_ARRIVE_DAY_OFFSET:
        return None, None
    return arrive_time, offset


def _route_airports(segs: Sequence[Mapping[str, Any]]) -> str | None:
    """ "TPE,NRT" / "TPE,SZX,SHA"; None when any code is missing or a connection changes
    airport."""
    if not 1 <= len(segs) <= MAX_DETAIL_SEGMENTS:
        return None
    codes: list[str] = []
    for index, seg in enumerate(segs):
        origin, arrival = _text(seg, "from"), _text(seg, "to")
        if origin is None or arrival is None:
            return None
        if not (_AIRPORT_CODE.fullmatch(origin) and _AIRPORT_CODE.fullmatch(arrival)):
            return None
        if index == 0:
            codes.append(origin)
        elif codes[-1] != origin:
            return None
        codes.append(arrival)
    return ",".join(codes)


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
        arrive_time, arrive_day_offset = _arrival(segs, depart_date)
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
                flight_numbers=_flight_numbers(segs),
                arrive_time=arrive_time,
                arrive_day_offset=arrive_day_offset,
                route_airports=_route_airports(segs),
            )
        )
    return quotes
