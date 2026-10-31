"""FD-9 rendering snapshots for the all-weekdays single-month path (ADR-0002 FD-10 C-76).

The snapshots in ``tests/snapshots/`` were recorded from the FD-9 code before any FD-10
change. The fixture below is frozen: same clock, same prices, same records. Under the
FD-10 code the same fixture must render ``exploration.html`` byte for byte, and
``explore.html`` byte for byte outside the explore form (whose h1, intro, month fields and
weekday group are FD-10 shape changes listed in AC-F4).

Re-recording is only allowed on purpose: ``FD10_RECORD_SNAPSHOTS=1 uv run pytest
tests/test_fd10_snapshots.py``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.messages import EXPLORATION_TOP_SCOPE_NOTE
from flight_deals.domain.models import FlightSearch
from tests.conftest import CLIENT_HEADERS, Harness

SNAPSHOTS = Path(__file__).parent / "snapshots"
RECORD = os.environ.get("FD10_RECORD_SNAPSHOTS") == "1"
_VERSION = re.compile(r"\?v=[0-9a-f]{12}")

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


@pytest.fixture
def rendered(harness: Harness) -> dict[str, str]:
    pages = render(harness, build_fixture(harness))
    if RECORD:
        SNAPSHOTS.mkdir(exist_ok=True)
        for name, html in pages.items():
            (SNAPSHOTS / name).write_text(html, encoding="utf-8", newline="")
    return pages


def snapshot(name: str) -> str:
    return (SNAPSHOTS / name).read_text(encoding="utf-8")


# FD-10 R1 (risk-compliance) adds one always-shown line under the top-5 heading. It is
# the ONLY difference allowed against the FD-9 snapshot (listed in AC-F4); it is removed
# here, with its indentation and trailing newline, before the byte-for-byte comparison.
_TOP_SCOPE = re.compile(
    r"[ \t]*<p class=\"muted\">" + re.escape(EXPLORATION_TOP_SCOPE_NOTE) + r"</p>\n?"
)


def without_top_scope_note(html: str) -> str:
    stripped, count = _TOP_SCOPE.subn("", html)
    assert count == 1, "the FD-10 R1 note must appear exactly once"
    return stripped


def test_exploration_page_matches_fd9(rendered: dict[str, str]) -> None:  # C-76, AC-D11
    page = without_top_scope_note(rendered["fd9_exploration.html"])
    assert page == snapshot("fd9_exploration.html")


def test_stale_exploration_page_matches_fd9(rendered: dict[str, str]) -> None:  # C-78 F3
    page = without_top_scope_note(rendered["fd9_exploration_stale.html"])
    assert page == snapshot("fd9_exploration_stale.html")


def test_explore_page_matches_fd9_outside_the_form(rendered: dict[str, str]) -> None:  # C-76
    page = rendered["fd9_explore.html"]
    recorded = snapshot("fd9_explore.html")
    assert outside_form(page) == outside_form(recorded)
    # C-80 (6): the all-weekdays single-month estimate text is unchanged.
    assert estimate_text(page) == estimate_text(recorded)
