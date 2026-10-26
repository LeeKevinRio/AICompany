"""Tolerant parser for the Google Flights results page (stdlib only, no I/O).

The results page embeds its data in ``<script class="ds:1">`` as
``AF_initDataCallback({key: 'ds:1', hash: '..', data:[...], sideChannel: {}});``.
The upstream parser reads every itinerary's price as ``k[1][0][1]`` and aborts the
whole page when one itinerary has no price; this module classifies each itinerary on
its own instead:

* priced    -- ``k[1][0]`` is ``[_, <positive int>]``
* unpriced  -- ``k[1][0] == []`` (the only "no price" shape observed live)
* malformed -- anything else

Only the price is required. Carrier, stop count and duration are optional and fall
back to ``None``. Records use the shape expected by ``sources._records``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from flight_deals.ports import ParseStats

SCRIPT_CLASS = "ds:1"
ERROR_STATUS_MARKER = "errorHasStatus: true"

# Positions inside the payload, mirroring the upstream parser.
RESULTS_INDEX = 3  # payload[3][0] is the itinerary list (None when there are none)
ITINERARY_INFO = 0  # k[0]: flight info
ITINERARY_PRICE = 1  # k[1]: [[None, price], token] or [[], token]
INFO_CARRIER_CODE = 0  # k[0][0]: airline code or "multi"
INFO_CARRIER_NAMES = 1  # k[0][1]: list of airline names
INFO_SEGMENTS = 2  # k[0][2]: list of segments
SEGMENT_DURATION = 11  # segment[11]: minutes


class PayloadFormatError(ValueError):
    """The page or payload does not have the expected shape (treated as ``blocked``)."""


class PayloadErrorStatus(Exception):
    """Google answered with ``errorHasStatus`` (treated as ``no_data``)."""


@dataclass(frozen=True)
class ParsedPage:
    records: tuple[dict[str, Any], ...]
    stats: ParseStats
    # True when payload[3][0] is None: Google listed no itineraries at all.
    no_results: bool = False


class _ScriptFinder(HTMLParser):
    """Collect the text of the first ``<script>`` whose class list contains ``ds:1``."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._capturing = False
        self._done = False
        self._parts: list[str] = []
        self.found = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done or tag != "script":
            return
        classes = " ".join(value or "" for name, value in attrs if name == "class").split()
        if SCRIPT_CLASS in classes:
            self._capturing = True
            self.found = True

    def handle_endtag(self, tag: str) -> None:
        if self._capturing and tag == "script":
            self._capturing = False
            self._done = True

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    @property
    def text(self) -> str:
        return "".join(self._parts)


def find_script_text(html: str) -> str | None:
    finder = _ScriptFinder()
    finder.feed(html)
    finder.close()
    return finder.text if finder.found else None


def extract_payload(html: str) -> Any:
    """Return the decoded ``data:`` JSON of the ``ds:1`` script.

    Raises ``PayloadErrorStatus`` for an error-status page and ``PayloadFormatError``
    when the script is missing or its data cannot be decoded.
    """
    if not isinstance(html, str) or not html.strip():
        raise PayloadFormatError("blank page")
    script = find_script_text(html)
    if script is None:
        raise PayloadFormatError(f"no <script class={SCRIPT_CLASS}> in page")
    _, sep, tail = script.partition("data:")
    if not sep:
        raise PayloadFormatError("results script has no data field")
    data = tail.rsplit(",", 1)[0].strip()
    if data.endswith(ERROR_STATUS_MARKER):
        raise PayloadErrorStatus("results script reports an error status")
    try:
        return json.loads(data)
    except (ValueError, RecursionError) as exc:
        raise PayloadFormatError(f"results data is not valid JSON ({type(exc).__name__})") from exc


def _at(value: Any, *path: int) -> Any:
    """Safe nested list lookup: ``None`` when any step is missing or not a list."""
    for index in path:
        if not isinstance(value, list) or not -len(value) <= index < len(value):
            return None
        value = value[index]
    return value


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _record(itinerary: list[Any], price: int) -> dict[str, Any]:
    info = _at(itinerary, ITINERARY_INFO)
    names = _at(info, INFO_CARRIER_NAMES)
    airlines = (
        [n for n in names if isinstance(n, str) and n.strip()] if isinstance(names, list) else []
    )
    segments = _at(info, INFO_SEGMENTS)
    flights: list[dict[str, Any]] = []
    if isinstance(segments, list) and all(isinstance(s, list) for s in segments):
        for segment in segments:
            duration = _at(segment, SEGMENT_DURATION)
            flights.append({"duration": duration if _is_positive_int(duration) else None})
    return {
        "type": _optional_str(_at(info, INFO_CARRIER_CODE)),
        "price": price,
        "airlines": airlines,
        "flights": flights,
    }


def classify_itinerary(itinerary: Any) -> str:
    """Return ``"priced"``, ``"unpriced"`` or ``"malformed"`` for one itinerary entry."""
    price_block = _at(itinerary, ITINERARY_PRICE)
    if not isinstance(price_block, list) or not price_block:
        return "malformed"
    head = price_block[0]
    if head == []:
        return "unpriced"
    if isinstance(head, list) and len(head) >= 2 and _is_positive_int(head[1]):
        return "priced"
    return "malformed"


def parse_payload(payload: Any) -> ParsedPage:
    """Split a decoded payload into priced records plus per-itinerary counts.

    Raises ``PayloadFormatError`` when the top-level shape is not recognised.
    """
    if not isinstance(payload, list) or len(payload) <= RESULTS_INDEX:
        raise PayloadFormatError("payload is not a list with a results section")
    results = payload[RESULTS_INDEX]
    if not isinstance(results, list) or not results:
        raise PayloadFormatError("results section is not a non-empty list")
    itineraries = results[0]
    if itineraries is None:
        return ParsedPage(records=(), stats=ParseStats(0, 0, 0, 0), no_results=True)
    if not isinstance(itineraries, list):
        raise PayloadFormatError("itinerary list has an unexpected type")

    records: list[dict[str, Any]] = []
    unpriced = malformed = 0
    for itinerary in itineraries:
        kind = classify_itinerary(itinerary)
        if kind == "priced":
            records.append(_record(itinerary, itinerary[ITINERARY_PRICE][0][1]))
        elif kind == "unpriced":
            unpriced += 1
        else:
            malformed += 1
    stats = ParseStats(
        itineraries=len(itineraries),
        priced=len(records),
        unpriced=unpriced,
        malformed=malformed,
    )
    return ParsedPage(records=tuple(records), stats=stats)


def parse_html(html: str) -> ParsedPage:
    return parse_payload(extract_payload(html))
