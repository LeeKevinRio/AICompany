"""Airport / city suggestions for the form autocomplete (stateless, offline)."""

from __future__ import annotations

from flight_deals.domain import airports
from flight_deals.domain.airports import MAX_QUERY_LENGTH, MAX_RESULTS

__all__ = ["MAX_QUERY_LENGTH", "MAX_RESULTS", "place_label", "suggest"]


def suggest(q: str) -> list[dict[str, str]]:
    """Ranked suggestions (at most ``MAX_RESULTS``) shaped for the JSON endpoint."""
    return [
        {
            "code": place.code,
            "kind": place.kind,
            "label": airports.suggestion_label(place),
            "display": airports.place_label(place.code),
        }
        for place in airports.search_places(q)
    ]


def place_label(code: str) -> str:
    """``display_name CODE`` for table codes; codes outside the table are returned as-is."""
    return airports.place_label(code)
