"""FD-20: every round checks the list card's three pairs again, in card order."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from flight_deals.domain.models import DatePair
from flight_deals.services import scan as scan_module
from tests.conftest import Harness

WINDOW = {
    "date_mode": "flexible",
    "depart_date": None,
    "return_date": None,
    "window_start": "2026-12-10",
    "window_end": "2026-12-19",
    "min_trip_days": 5,
    "max_trip_days": 5,
}
# Five pairs: the card shows 12/12 (main), then 12/14 and 12/10.
PRICES = {
    ("2026-12-10", "2026-12-15"): 9_000,
    ("2026-12-11", "2026-12-16"): 9_800,
    ("2026-12-12", "2026-12-17"): 8_000,
    ("2026-12-13", "2026-12-18"): 9_500,
    ("2026-12-14", "2026-12-19"): 8_500,
}
CARD = ["2026-12-12", "2026-12-14", "2026-12-10"]


def only(*departs: str, truncated: bool = True) -> Any:
    wanted = {date.fromisoformat(d) for d in departs}

    def pick(pairs: list[DatePair], limit: int, offset: int) -> Any:
        return [p for p in pairs if p.depart in wanted], offset + 1, truncated

    return pick


def first_round(h: Harness) -> int:
    h.source.default_price = None
    h.source.prices.update(PRICES)
    watch_id = h.create_watch(**WINDOW)
    h.scan(watch_id)  # five pairs fit in one round
    h.clock.advance(hours=7)
    return watch_id


def departs(h: Harness, watch_id: int) -> list[str]:
    run = h.repo.latest_scan_run_for_watch(watch_id)
    return [e["depart"] for e in run.query_results]


def pinned(h: Harness, watch_id: int) -> list[str]:
    run = h.repo.latest_scan_run_for_watch(watch_id)
    return [e["depart"] for e in run.query_results if e.get("pinned")]


def card_departs(h: Harness) -> list[str]:
    row = h.services.views.list_page()["watches"][0]
    more = [p["dates"].split("–")[0] for p in row["more_pairs"]]
    return [row["min_price_dates"].split("–")[0], *more]


def test_card_pairs_come_first_in_card_order(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    assert card_departs(harness) == ["12/12", "12/14", "12/10"]
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-13"))
    harness.scan(watch_id)
    assert departs(harness, watch_id) == [*CARD, "2026-12-13"]
    assert pinned(harness, watch_id) == CARD
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert run.limit_reached  # sampling itself is unchanged
    assert harness.repo.get_watch(watch_id).sample_offset == 1


def test_sampled_card_pairs_are_not_doubled(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-10", "2026-12-11"))
    harness.scan(watch_id)
    assert departs(harness, watch_id) == [*CARD, "2026-12-11"]
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert len(run.query_results) == 4  # three card pairs plus the one non-card sample


def test_rows_get_fresh_prices(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_id = first_round(harness)
    harness.source.prices[("2026-12-14", "2026-12-19")] = 8_700
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-13"))
    harness.scan(watch_id)
    row = harness.services.views.list_page()["watches"][0]
    assert row["more_pairs"][0]["amount"] == "TWD 8,700"
    fetched = {p["fetched_label"] for p in row["more_pairs"]}
    assert fetched == {row["cheapest_fetched_label"]}  # all three from this round


def test_a_row_that_goes_up_drops_off_the_card(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    harness.source.prices[("2026-12-14", "2026-12-19")] = 9_900
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-13"))
    harness.scan(watch_id)
    assert card_departs(harness) == ["12/12", "12/10", "12/13"]


def test_fewer_priced_pairs_pin_fewer(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    harness.source.default_price = None
    harness.source.prices[("2026-12-12", "2026-12-17")] = 8_000
    harness.source.prices[("2026-12-14", "2026-12-19")] = 8_500
    watch_id = harness.create_watch(**WINDOW)
    harness.scan(watch_id)
    harness.clock.advance(hours=7)
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-13"))
    harness.scan(watch_id)
    assert pinned(harness, watch_id) == ["2026-12-12", "2026-12-14"]
    assert departs(harness, watch_id) == ["2026-12-12", "2026-12-14", "2026-12-13"]


def test_hourly_limit_keeps_card_order_and_marks(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    settings = harness.services.scan._settings
    original = settings.current
    monkeypatch.setattr(
        settings, "current", lambda: replace(original(), global_hourly_query_limit=0)
    )
    monkeypatch.setattr(scan_module, "sample_pairs", only("2026-12-13"))
    harness.scan(watch_id)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert [e["depart"] for e in run.query_results if e.get("pinned")] == CARD
    assert all(e["reason"] == "global_hourly_limit" for e in run.query_results)
