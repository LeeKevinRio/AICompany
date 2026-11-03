"""FD-12 rendering snapshots of the exploration pages (ADR-0002 FD-12 section 6, C-104).

The FD-9 snapshots retired with the FD-12 page redesign; ``fd12_*`` are the new baseline
recorded from the FD-12 templates. ``build_fixture`` and ``render`` are kept verbatim from
the FD-10 test, so the same frozen fixture (clock, prices, records, no flight details)
renders the pages the way old data degrades. ``fd12_exploration_flights.html`` adds the
opt-in flight details: nonstop, next-day arrival and one stop.

Every recording is checked first (DISCLAIMER once and outside ``<details>``, no ``None``
or retired wording, external links only to Google Flights in a new tab).

Re-recording is only allowed on purpose: ``FD12_RECORD_SNAPSHOTS=1 uv run pytest
tests/test_fd12_snapshots.py``; the recording run fails on purpose, rerun without it.
"""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.messages import DISCLAIMER
from flight_deals.domain.models import FlightSearch
from tests.conftest import CLIENT_HEADERS, Harness

SNAPSHOTS = Path(__file__).parent / "snapshots"
RECORD = os.environ.get("FD12_RECORD_SNAPSHOTS") == "1"
_VERSION = re.compile(r"\?v=[0-9a-f]{12}")
# render() keeps its FD-9 page keys verbatim; the files are the FD-12 baseline.
FILES = {
    "fd9_explore.html": "fd12_explore.html",
    "fd9_exploration.html": "fd12_exploration.html",
    "fd9_exploration_stale.html": "fd12_exploration_stale.html",
}
FLIGHTS_FILE = "fd12_exploration_flights.html"
FORBIDDEN = ("None", "未在頁面內嵌", "查票", "no result section")
GOOGLE_FLIGHTS = "https://www.google.com/travel/flights"

MONTH: dict[str, Any] = {
    "origin": "TPE",
    "destination": "NRT",
    "trip_type": "round_trip",
    "month": "2026-12",
    "trip_days": 5,
    "max_stops": "",
    "adults": 1,
    "children": 0,
    "cabin": "economy",
    "airlines": [],
    "dep_hour_from": None,
    "dep_hour_to": None,
}
# Opt-in flight details of the flights snapshot (ScriptedSource ``flights``).
NONSTOP = {
    "carrier": "長榮航空",
    "stops": 0,
    "depart_time": "07:55",
    "duration_minutes": 185,
    "flight_numbers": "BR184",
    "arrive_time": "12:00",
    "arrive_day_offset": 0,
    "route_airports": "TPE,NRT",
}
NEXT_DAY = {
    "carrier": "中華航空",
    "stops": 0,
    "depart_time": "23:55",
    "duration_minutes": 215,
    "flight_numbers": "CI100",
    "arrive_time": "04:30",
    "arrive_day_offset": 1,
    "route_airports": "TPE,NRT",
}
ONE_STOP = {
    "carrier": "長榮航空、日本航空",
    "stops": 1,
    "depart_time": "07:00",
    "duration_minutes": 300,
    "flight_numbers": "BR198,JL99",
    "arrive_time": "16:05",
    "arrive_day_offset": 0,
    "route_airports": "TPE,HKG,NRT",
}


class SnapshotLinks:
    def url(self, search: FlightSearch) -> str | None:
        ret = search.pair.return_date.isoformat() if search.pair.return_date else "-"
        return f"https://www.google.com/travel/flights/search?tfs={search.pair.depart}_{ret}"


def normalize(html: str) -> str:
    """The static ``?v=`` suffix follows app.js / app.css content, not the page."""
    return _VERSION.sub("?v=STATIC", html)


def build_fixture(harness: Harness) -> int:
    """One done all-weekdays single-month exploration with varied cells, plus one watch.

    The fake clock starts at 2026-10-25 12:00 Asia/Taipei (``today`` is fixed).
    """
    service = harness.services.exploration
    queued: list[int] = []
    service.hooks.schedule = queued.append
    service.hooks.scheduler_running = lambda: True
    harness.services.exploration_views._links = SnapshotLinks()
    harness.create_watch(name="東京十二月")
    prices = harness.source.prices
    for day, price in ((1, 5_000), (2, 6_000), (3, 7_000), (7, 5_000), (9, 9_500)):
        prices[(f"2026-12-{day:02d}", f"2026-12-{day + 5:02d}")] = price
    harness.source.fail_for.add(("2026-12-20", "2026-12-25"))
    response = harness.client.post("/api/explorations", json=MONTH, headers=CLIENT_HEADERS)
    assert response.status_code == 202, response.json()
    exploration_id = int(response.json()["id"])
    # A no-data day so more than one cell status is rendered.
    harness.source.prices[("2026-12-14", "2026-12-19")] = None  # type: ignore[assignment]
    while queued:
        service.run(queued.pop(0))
    return exploration_id


def render(harness: Harness, exploration_id: int) -> dict[str, str]:
    harness.clock.advance(hours=2)
    pages = {
        "fd9_explore.html": harness.client.get("/explore"),
        "fd9_exploration.html": harness.client.get(f"/explorations/{exploration_id}"),
    }
    harness.clock.advance(hours=30)  # finished more than 24 hours ago: stale branch
    pages["fd9_exploration_stale.html"] = harness.client.get(f"/explorations/{exploration_id}")
    out: dict[str, str] = {}
    for name, response in pages.items():
        assert response.status_code == 200, name
        out[name] = normalize(response.text)
    return out


_FORM = re.compile(r'<form id="explore-form".*?</form>', re.S)
_HEAD = re.compile(r'<div class="page-head">\s*<h1>.*?</h1>\s*</div>\s*<p>.*?</p>', re.S)
_ESTIMATE = re.compile(r'<p id="explore-estimate"[^>]*>(.*?)</p>', re.S)


def outside_form(html: str) -> str:
    """explore.html minus the FD-10 form shape changes (h1, intro and form)."""
    return _FORM.sub("<form/>", _HEAD.sub("<head/>", html, count=1), count=1)


def estimate_text(html: str) -> str:
    match = _ESTIMATE.search(html)
    assert match is not None
    return match.group(1)


def build_flights_fixture(harness: Harness) -> int:
    """``build_fixture`` plus flight details on three priced days (opt-in)."""
    flights = harness.source.flights
    flights[("2026-12-01", "2026-12-06")] = NONSTOP
    flights[("2026-12-02", "2026-12-07")] = NEXT_DAY
    flights[("2026-12-03", "2026-12-08")] = ONE_STOP
    return build_fixture(harness)


class _Page(HTMLParser):
    """Text inside / outside ``<details>`` and every ``<a>`` with an external href."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.inside: list[str] = []
        self.outside: list[str] = []
        self.external: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "details":
            self.depth += 1
        values = dict(attrs)
        href = values.get("href") or ""
        if tag == "a" and href.startswith(("http:", "https:", "//")):
            self.external.append(values)

    def handle_endtag(self, tag: str) -> None:
        if tag == "details":
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        (self.inside if self.depth else self.outside).append(data)


def check_before_writing(name: str, html: str) -> None:
    """Guards of a recording (contract section 6, point 5)."""
    page = _Page()
    page.feed(html)
    page.close()
    assert html.count(DISCLAIMER) == 1, name
    assert DISCLAIMER in "".join(page.outside), name
    assert DISCLAIMER not in "".join(page.inside), name
    for word in FORBIDDEN:
        assert word not in html, (name, word)
    for link in page.external:
        assert (link.get("href") or "").startswith(GOOGLE_FLIGHTS), (name, link)
        assert link.get("target") == "_blank", (name, link)
        rel = (link.get("rel") or "").split()
        assert "noopener" in rel and "noreferrer" in rel, (name, link)


def record_and_stop(pages: dict[str, str]) -> None:
    for name, html in pages.items():
        check_before_writing(name, html)
    SNAPSHOTS.mkdir(exist_ok=True)
    for name, html in pages.items():
        (SNAPSHOTS / name).write_text(html, encoding="utf-8", newline="")
    pytest.fail("recorded; rerun without FD12_RECORD_SNAPSHOTS")


@pytest.fixture
def rendered(harness: Harness) -> dict[str, str]:
    pages = {FILES[k]: v for k, v in render(harness, build_fixture(harness)).items()}
    if RECORD:
        record_and_stop(pages)
    return pages


@pytest.fixture
def rendered_flights(harness: Harness) -> str:
    exploration_id = build_flights_fixture(harness)
    harness.clock.advance(hours=2)
    response = harness.client.get(f"/explorations/{exploration_id}")
    assert response.status_code == 200
    html = normalize(response.text)
    if RECORD:
        record_and_stop({FLIGHTS_FILE: html})
    return html


def snapshot(name: str) -> str:
    return (SNAPSHOTS / name).read_text(encoding="utf-8")


def test_snapshot_files_are_the_fd12_set() -> None:  # C-104
    names = sorted(p.name for p in SNAPSHOTS.glob("*.html"))
    assert names == sorted([*FILES.values(), FLIGHTS_FILE])


@pytest.mark.parametrize("name", [*FILES.values(), FLIGHTS_FILE])
def test_recorded_snapshots_pass_the_guards(name: str) -> None:  # C-104 point 5
    check_before_writing(name, snapshot(name))


def test_exploration_page_matches_fd12(rendered: dict[str, str]) -> None:  # C-104
    assert rendered["fd12_exploration.html"] == snapshot("fd12_exploration.html")


def test_stale_exploration_page_matches_fd12(rendered: dict[str, str]) -> None:  # C-104
    assert rendered["fd12_exploration_stale.html"] == snapshot("fd12_exploration_stale.html")


def test_explore_page_matches_fd12_outside_the_form(rendered: dict[str, str]) -> None:
    page = rendered["fd12_explore.html"]
    recorded = snapshot("fd12_explore.html")
    assert outside_form(page) == outside_form(recorded)
    # C-80 (6): the all-weekdays single-month estimate text is unchanged.
    assert estimate_text(page) == estimate_text(recorded)


def test_exploration_flights_page_matches_fd12(rendered_flights: str) -> None:  # C-104
    assert rendered_flights == snapshot(FLIGHTS_FILE)
    for text in ("BR 184", "CI 100", "04:30", "+1", "BR 198 → JL 99", "轉機 1 次（HKG）"):
        assert text in rendered_flights, text
