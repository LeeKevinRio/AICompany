"""Manual price-check links. Pure URL building; nothing is fetched."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

GOOGLE_FLIGHTS_BASE = "https://www.google.com/travel/flights?hl=zh-TW&curr=TWD&q="


def google_flights_url(
    origin: str, destination: str, depart: date, return_date: date | None = None
) -> str:
    """Google Flights search URL pre-filled with route and dates."""
    query = f"Flights to {destination} from {origin} on {depart.isoformat()}"
    if return_date is not None:
        query += f" through {return_date.isoformat()}"
    return GOOGLE_FLIGHTS_BASE + quote(query, safe="")
