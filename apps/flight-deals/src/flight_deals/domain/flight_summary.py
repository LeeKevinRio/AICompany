"""Display text of the cheapest itinerary's outbound flight (ADR-0002 FD-12, C-98).

The only place web pages and Telegram messages get flight wording from: airline names,
flight numbers ("BR 198 → JL 99"), local departure / arrival times with the arrival day
offset ("+1", "−1"), stops with layover airports. Pure; imports stdlib and domain only.

Times and dates are local to each airport and never converted. Unknown values show
"—"; no field ever contains ``None``. Rows written before migration 0009 have only
carrier, stops, departure time and duration (``detailed`` is False).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from flight_deals.domain.airlines import lookup_airline
from flight_deals.domain.models import TripType
from flight_deals.domain.trip_labels import flight_duration_label

UNKNOWN = "—"
OUTBOUND_LABEL = "去程"
NONSTOP_LABEL = "直飛"
FLIGHT_UNKNOWN_SR = "航班資訊未提供"
MINUS_SIGN = "−"  # "−", never the ASCII hyphen
FLIGHT_SEPARATOR = " → "
TIME_SEPARATOR = " → "
TIME_SEPARATOR_COMPACT = "→"
_FLIGHT = re.compile(r"([A-Z0-9]{2})([0-9]{1,4})", re.ASCII)
_AIRPORT = re.compile(r"[A-Z]{3}", re.ASCII)
TRIPS: tuple[TripType, ...] = ("round_trip", "one_way")


class FlightFacts(Protocol):
    """Flight fields shared by observations, cells, alert candidates and /watch rows."""

    @property
    def carrier(self) -> str | None: ...

    @property
    def stops(self) -> int | None: ...

    @property
    def depart_time(self) -> str | None: ...

    @property
    def duration_minutes(self) -> int | None: ...

    @property
    def flight_numbers(self) -> str | None: ...

    @property
    def arrive_time(self) -> str | None: ...

    @property
    def arrive_day_offset(self) -> int | None: ...

    @property
    def route_airports(self) -> str | None: ...


@dataclass(frozen=True)
class FlightSummary:
    leg_label: str | None  # "去程" for round trips, None for one-way
    is_outbound_only: bool  # leg_label is not None
    airline: str  # "長榮航空" / "長榮航空、日本航空" / "—"
    flight_numbers: str  # "BR 184" / "BR 198 → JL 99" / "—"
    depart_time: str  # "07:55" / "—"
    arrive_time: str  # "12:00" / "—"
    day_offset: str | None  # "+1" / "−1"; None when 0 or unknown
    day_offset_sr: str | None  # screen-reader wording of the offset, e.g. "（隔天）"
    times: str  # "07:55 → 12:00" / "23:55 → 03:30+1" / "07:55 → —"
    times_compact: str  # "07:55→12:00" (Telegram /watch)
    depart_airport: str | None
    arrive_airport: str | None
    stops: str  # "直飛" / "轉機 1 次（HKG）" / "轉機 1 次" / "—"
    stops_short: str | None  # "直飛" / "轉機 1 次" / None
    duration: str | None  # "3 小時 5 分" / None
    # Shown next to the stops: with a connection the time is flight time only (M3).
    duration_text: str | None  # "3 小時 5 分" / "飛行 4 小時 30 分（不含轉機等候）" / None
    detailed: bool  # any FD-12 field is known
    sr_text: str  # one sentence for screen readers, unknown parts left out


def format_flight_numbers(canonical: str | None) -> str | None:
    """ "BR184,JL99" -> "BR 184 → JL 99"; None when absent or not in the stored shape."""
    if not canonical:
        return None
    parts = []
    for token in canonical.split(","):
        match = _FLIGHT.fullmatch(token)
        if match is None:
            return None
        parts.append(f"{match.group(1)} {match.group(2)}")
    return FLIGHT_SEPARATOR.join(parts)


def flight_codes(canonical: str | None) -> tuple[str, ...]:
    """Airline codes of each segment ("BR184,JL99" -> ("BR", "JL")); () when unknown."""
    if format_flight_numbers(canonical) is None:
        return ()
    return tuple(token[:2] for token in (canonical or "").split(","))


def day_offset_label(offset: int | None) -> str | None:
    """+1 -> "+1", -1 -> "−1" (U+2212); 0 or unknown -> None."""
    if offset is None or offset == 0:
        return None
    return f"+{offset}" if offset > 0 else f"{MINUS_SIGN}{-offset}"


def day_offset_sr(offset: int | None) -> str | None:
    """Spoken form of the arrival day offset; None when 0 or unknown."""
    if offset is None or offset == 0:
        return None
    if offset == 1:
        return "（隔天）"
    if offset == -1:
        return "（前一天）"
    return f"（{offset} 天後）" if offset > 0 else f"（{-offset} 天前）"


def layover_codes(route_airports: str | None) -> tuple[str, ...] | None:
    """Connection airports of "TPE,HKG,NRT" -> ("HKG",); None when unknown."""
    if not route_airports:
        return None
    codes = route_airports.split(",")
    if len(codes) < 2 or not all(_AIRPORT.fullmatch(code) for code in codes):
        return None
    return tuple(codes[1:-1])


def _airline(facts: FlightFacts) -> str:
    names: list[str] = []
    for name in (facts.carrier or "").split("、"):
        name = name.strip()
        if name and name not in names:
            names.append(name)
    if not names:
        for code in flight_codes(facts.flight_numbers):
            airline = lookup_airline(code)
            name = airline.zh_name if airline else code
            if name not in names:
                names.append(name)
    return "、".join(names) or UNKNOWN


def _stops(facts: FlightFacts) -> tuple[str, str | None]:
    stops = facts.stops
    if stops is None or stops < 0:
        return UNKNOWN, None
    if stops == 0:
        return NONSTOP_LABEL, NONSTOP_LABEL
    short = f"轉機 {stops} 次"
    layovers = layover_codes(facts.route_airports)
    if layovers and len(layovers) == stops:
        return f"{short}（{'、'.join(layovers)}）", short
    return short, short


def flight_summary(facts: FlightFacts, *, trip_type: TripType) -> FlightSummary:
    leg = OUTBOUND_LABEL if trip_type == "round_trip" else None
    airline = _airline(facts)
    numbers = format_flight_numbers(facts.flight_numbers)
    depart = facts.depart_time or UNKNOWN
    # An arrival time is only shown with its day offset (FR-2: never a wrong "same day").
    known_arrival = facts.arrive_time is not None and facts.arrive_day_offset is not None
    arrive = facts.arrive_time if known_arrival and facts.arrive_time else UNKNOWN
    offset = facts.arrive_day_offset if known_arrival else None
    offset_text = day_offset_label(offset)
    offset_sr = day_offset_sr(offset)
    arrive_full = arrive + (offset_text or "")
    stops, stops_short = _stops(facts)
    duration = flight_duration_label(facts.duration_minutes)
    known_route = layover_codes(facts.route_airports) is not None
    codes = (facts.route_airports or "").split(",") if known_route else []
    detailed = any(
        value is not None
        for value in (
            facts.flight_numbers,
            facts.arrive_time,
            facts.arrive_day_offset,
            facts.route_airports,
        )
    )
    spoken = [part for part in (leg,) if part]
    who = " ".join(p for p in (airline if airline != UNKNOWN else "", numbers or "") if p)
    if who:
        spoken.append(who)
    if facts.depart_time:
        spoken.append(f"{facts.depart_time} 出發")
    if arrive != UNKNOWN:
        spoken.append(f"{arrive} 抵達{offset_sr or ''}")
    if stops != UNKNOWN:
        spoken.append(stops)
    if len(spoken) == (1 if leg else 0):
        spoken.append(FLIGHT_UNKNOWN_SR)
    return FlightSummary(
        leg_label=leg,
        is_outbound_only=leg is not None,
        airline=airline,
        flight_numbers=numbers or UNKNOWN,
        depart_time=depart,
        arrive_time=arrive,
        day_offset=offset_text,
        day_offset_sr=offset_sr,
        times=f"{depart}{TIME_SEPARATOR}{arrive_full}",
        times_compact=f"{depart}{TIME_SEPARATOR_COMPACT}{arrive_full}",
        depart_airport=codes[0] if codes else None,
        arrive_airport=codes[-1] if codes else None,
        stops=stops,
        stops_short=stops_short,
        duration=duration,
        duration_text=(
            f"飛行 {duration}（不含轉機等候）" if duration and (facts.stops or 0) > 0 else duration
        ),
        detailed=detailed,
        sr_text="，".join(spoken),
    )


@dataclass(frozen=True)
class _Sample:
    carrier: str | None = "長榮航空"
    stops: int | None = 0
    depart_time: str | None = "07:55"
    duration_minutes: int | None = 185
    flight_numbers: str | None = "BR184"
    arrive_time: str | None = "12:00"
    arrive_day_offset: int | None = 0
    route_airports: str | None = "TPE,NRT"


def static_texts() -> list[str]:
    """Wording of this module, for the banned-phrase test."""
    samples = [
        _Sample(),
        _Sample(depart_time="23:55", arrive_time="03:30", arrive_day_offset=1),
        _Sample(arrive_day_offset=-1),
        _Sample(arrive_day_offset=2),
        _Sample(stops=1, flight_numbers="BR198,JL99", route_airports="TPE,HKG,NRT"),
        _Sample(stops=2, flight_numbers=None, route_airports="TPE,HKG,ICN,NRT"),
        _Sample(None, None, None, None, None, None, None, None),
    ]
    texts = [UNKNOWN, OUTBOUND_LABEL, NONSTOP_LABEL, FLIGHT_UNKNOWN_SR]
    for sample in samples:
        for trip in TRIPS:
            summary = flight_summary(sample, trip_type=trip)
            texts.extend([summary.sr_text, summary.stops, summary.times, summary.airline])
            texts.extend(
                t for t in (summary.day_offset_sr, summary.duration, summary.duration_text) if t
            )
    return texts
