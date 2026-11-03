"""'Results not embedded' hints: list streak and 24-hour ratio (FD-6 Decision 8, C-48)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from flight_deals.config import Limits
from flight_deals.domain.messages import health_no_embedded_note
from flight_deals.domain.models import FlightSearch
from flight_deals.ports import SourceResult
from flight_deals.services.health import (
    no_embedded_counts,
    no_embedded_hint,
    no_embedded_streak,
    round_not_embedded,
)
from tests.conftest import Harness
from tests.test_exploration_service import Queue, start

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
HIT = {"source": "google_flights", "status": "no_data", "reason": "no_embedded_results"}
OK = {"source": "google_flights", "status": "ok", "amount_minor": 1}
SKIP = {"source": None, "status": "skipped", "reason": "global_hourly_limit"}


def hint(counts: dict[str, tuple[int, int]]) -> dict[str, int] | None:
    return no_embedded_hint(counts, min_queries=10, min_ratio_pct=50)


# ---- pure functions ------------------------------------------------------------------


def test_thresholds_live_in_config() -> None:
    limits = Limits()
    assert (
        limits.no_embedded_streak_rounds,
        limits.no_embedded_min_queries,
        limits.no_embedded_min_ratio_pct,
    ) == (3, 10, 50)


@pytest.mark.parametrize(
    "hits,total,shown",
    [
        (9, 9, False),  # all hit but under 10 queries
        (5, 10, True),  # 50 % and 10 queries: boundary shown
        (4, 10, False),
        (6, 10, True),
        (20, 40, True),  # AC-H2
        (49, 100, False),  # AC-H3
        (50, 100, True),
    ],
)
def test_ratio_hint_boundaries(hits: int, total: int, shown: bool) -> None:
    result = hint({"google_flights": (hits, total)})
    assert (result is not None) == shown
    if result:
        assert result == {"ratio_pct": hits * 100 // total, "count": hits, "total": total}


def test_counts_exclude_skipped_pending_and_cache() -> None:
    runs: list[list[dict[str, Any]]] = [
        [HIT, HIT, SKIP, {**HIT, "from_cache": True}, {**OK, "status": "pending"}],
        [OK, {**HIT, "source": None}],
    ]
    assert no_embedded_counts(runs) == {"google_flights": (2, 3)}


def test_counts_include_exploration_cells() -> None:
    counts = no_embedded_counts([[HIT] * 4], [("google_flights", 6, 2)])
    assert counts == {"google_flights": (6, 10)}
    assert hint(counts) == {"ratio_pct": 60, "count": 6, "total": 10}


def test_round_and_streak_rules() -> None:
    assert round_not_embedded([HIT, SKIP])
    assert not round_not_embedded([SKIP, SKIP])  # an all-skipped round breaks the streak
    assert not round_not_embedded([HIT, OK])
    assert not round_not_embedded([])
    assert no_embedded_streak([[HIT]] * 3, 3)
    assert not no_embedded_streak([[HIT]] * 2, 3)
    assert not no_embedded_streak([[HIT], [HIT], [OK]], 3)
    assert not no_embedded_streak([[HIT], [SKIP], [HIT]], 3)


def test_storage_uses_no_json_sql_functions() -> None:
    for path in (SRC / "storage").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".sql"}:
            assert "json_" not in path.read_text(encoding="utf-8").lower(), path


# ---- list streak through the repository ----------------------------------------------


def not_embedded(harness: Harness) -> None:
    def handler(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights", "no_data", harness.clock(), extra={"reason": "no_embedded_results"}
        )

    harness.source.handler = handler


def priced(harness: Harness) -> None:
    harness.source.handler = None


def scan_round(harness: Harness, watch_id: int) -> None:
    harness.scan(watch_id)
    harness.clock.advance(hours=7)


def streak(harness: Harness) -> bool:
    [row] = harness.services.views.list_page()["watches"]
    return bool(row["no_embedded_streak"])


def test_three_rounds_mark_and_a_priced_round_clears(harness: Harness) -> None:  # AC-H1
    watch_id = harness.create_watch()
    not_embedded(harness)
    scan_round(harness, watch_id)
    scan_round(harness, watch_id)
    assert not streak(harness)  # only two rounds
    scan_round(harness, watch_id)
    assert streak(harness)
    page = harness.client.get("/").text
    # FD-12 FR-11: without any price the card only says "需人工查價" (no streak label).
    assert "需人工查價" in page and "連續 3 輪" not in page
    (row,) = harness.services.views.list_page()["watches"]
    assert row["manual_check"] is True and row["stale_rounds_label"] is None
    priced(harness)
    scan_round(harness, watch_id)
    assert not streak(harness)


def test_two_hits_and_one_ok_is_not_a_streak(harness: Harness) -> None:
    watch_id = harness.create_watch()
    priced(harness)
    scan_round(harness, watch_id)
    not_embedded(harness)
    scan_round(harness, watch_id)
    scan_round(harness, watch_id)
    assert not streak(harness)


def test_all_skipped_round_breaks_the_streak(harness: Harness) -> None:
    watch_id = harness.create_watch()
    not_embedded(harness)
    scan_round(harness, watch_id)
    scan_round(harness, watch_id)
    assert harness.services.settings.update({"global_hourly_query_limit": "1"}) == {}
    harness.scan(watch_id)  # within the hour of the last scan: everything skipped
    harness.scan(watch_id)
    run = harness.repo.scan_runs_for_watch(watch_id)[0]
    assert {r["status"] for r in run.query_results} == {"skipped"}
    assert not streak(harness)


def test_edit_restarts_the_count(harness: Harness) -> None:
    watch_id = harness.create_watch()
    not_embedded(harness)
    for _ in range(3):
        scan_round(harness, watch_id)
    assert streak(harness)
    result = harness.services.watches.update(
        watch_id,
        {
            "destination": "NRT",
            "trip_type": "round_trip",
            "date_mode": "fixed",
            "depart_date": "2026-12-11",
            "return_date": "2026-12-16",
            "budget": 12000,
        },
    )
    assert result.ok
    assert not streak(harness)  # only the current revision's rounds count
    for _ in range(3):
        scan_round(harness, watch_id)
    assert streak(harness)


def test_hints_never_alert_or_trip_the_breaker(harness: Harness) -> None:  # AC-H4
    watch_id = harness.create_watch()
    not_embedded(harness)
    for _ in range(4):
        scan_round(harness, watch_id)
    health = harness.repo.get_source_health("google_flights")
    assert health.breaker_state == "closed" and health.consecutive_failures == 0
    assert harness.repo.get_watch(watch_id).status == "active"
    assert harness.repo.list_notifications() == []


def test_list_page_stays_one_query_plus_one_per_watch(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-48 / C-34
    ids = [harness.create_watch(budget=12000 + i) for i in range(3)]
    for watch_id in ids:
        for _ in range(4):
            scan_round(harness, watch_id)
    database = harness.repo.db
    real = database.connect
    calls: list[int] = []

    @contextmanager
    def counting() -> Iterator[Any]:
        calls.append(1)
        with real() as conn:
            yield conn

    monkeypatch.setattr(database, "connect", counting)
    harness.services.views.list_page()
    assert len(calls) == 1 + len(ids)


# ---- health page ratio, including exploration cells ------------------------------------


def test_health_page_ratio_counts_exploration_cells(harness: Harness) -> None:
    queue = Queue(harness.services.exploration)
    page = harness.services.views.settings_page()
    assert page["no_embedded_summary"] is None and page["active_exploration"] is None
    not_embedded(harness)
    exploration_id = start(harness, month="2026-10")  # 7 cells
    assert harness.services.views.settings_page()["active_exploration"] == {
        "id": exploration_id,
        "done": 0,
        "total": 7,
    }
    queue.run_all()
    assert harness.services.views.settings_page()["no_embedded_summary"] is None  # 7 < 10
    watch_id = harness.create_watch()
    for _ in range(3):
        scan_round(harness, watch_id)
    summary = harness.services.views.settings_page()["no_embedded_summary"]
    assert {k: summary[k] for k in ("ratio_pct", "count", "total")} == {
        "ratio_pct": 100,
        "count": 10,
        "total": 10,
    }
    assert summary["note"] == health_no_embedded_note(100, 10, 10)  # FD-12 #35
    html = harness.client.get("/settings").text
    assert "（可能是非同步載入或封鎖），需人工查價。" in html


def test_streak_label_comes_from_config(harness: Harness) -> None:
    from flight_deals.domain.messages import stale_rounds_label

    # FD-12 #42: a priced watch whose latest rounds were not embedded gets the short
    # "近 N 輪未更新" label; N comes from config, the template never writes it.
    rounds = Limits().no_embedded_streak_rounds
    watch_id = harness.create_watch()
    priced(harness)
    scan_round(harness, watch_id)
    not_embedded(harness)
    for _ in range(rounds):
        scan_round(harness, watch_id)
    (row,) = harness.services.views.list_page()["watches"]
    assert row["stale_rounds_label"] == stale_rounds_label(rounds) == "近 3 輪未更新"
    assert row["manual_check"] is False and row["min_price"]
    assert "no_embedded_streak_label" not in harness.services.views.list_page()
    template = (SRC / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    assert "近 3 輪" not in template and "連續 3 輪" not in template
