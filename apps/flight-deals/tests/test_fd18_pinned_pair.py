"""FD-18: the main card's date pair is checked again every round."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pytest

from flight_deals.domain.models import DatePair
from flight_deals.services import scan as scan_module
from tests.conftest import Harness
from tests.test_fd12_pages import flexible_round_trip

CHEAP = ("2026-12-10", "2026-12-15")
OTHER = ("2026-12-11", "2026-12-16")


def only(depart: date, truncated: bool = True) -> Any:
    def pick(pairs: list[DatePair], limit: int, offset: int) -> Any:
        return [p for p in pairs if p.depart == depart], offset + 1, truncated

    return pick


def first_round(h: Harness) -> int:
    h.source.prices[CHEAP] = 7_000
    h.source.prices[OTHER] = 9_000
    watch_id = flexible_round_trip(h)
    h.scan(watch_id)
    h.clock.advance(hours=7)
    return watch_id


def test_main_card_pair_is_added_first(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_id = first_round(harness)
    monkeypatch.setattr(scan_module, "sample_pairs", only(date(2026, 12, 11)))
    harness.scan(watch_id)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert [e["depart"] for e in run.query_results] == ["2026-12-10", "2026-12-11"]
    assert run.query_results[0].get("pinned") is True
    assert "pinned" not in run.query_results[1]
    assert run.limit_reached  # sampling itself is unchanged
    assert harness.repo.get_watch(watch_id).sample_offset == 1  # as sample_pairs returned


def test_pinned_mark_survives_the_hourly_limit(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    monkeypatch.setattr(scan_module, "sample_pairs", only(date(2026, 12, 11)))
    settings = harness.services.scan._settings
    original = settings.current
    monkeypatch.setattr(
        settings, "current", lambda: replace(original(), global_hourly_query_limit=0)
    )
    harness.scan(watch_id)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    first = run.query_results[0]
    assert first["depart"] == "2026-12-10" and first["pinned"] is True
    assert first["reason"] == "global_hourly_limit"


def test_cached_or_other_currency_rows_are_not_the_main_card(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)  # 12/10 at 7,000 is the main card
    run_id = harness.repo.latest_scan_run_for_watch(watch_id).id
    with harness.repo.db.connect() as conn:
        # Both rows become far cheaper than the 7,000 main card, but neither may count.
        conn.execute(
            "UPDATE price_observation SET price_kind = 'cached', amount_minor = 100"
            " WHERE watch_id = ? AND scan_run_id = ? AND depart_date = '2026-12-11'",
            (watch_id, run_id),
        )
        conn.execute(
            "INSERT INTO price_observation (scan_run_id, watch_id, watch_revision, source,"
            " price_kind, depart_date, return_date, amount_minor, currency, as_of,"
            " as_of_basis, fetched_at, carrier, stops, duration_minutes)"
            " SELECT scan_run_id, watch_id, watch_revision, source, 'live', '2026-12-12',"
            " '2026-12-17', 100, 'JPY', as_of, as_of_basis, fetched_at, carrier, stops,"
            " duration_minutes FROM price_observation WHERE watch_id = ? AND scan_run_id = ?"
            " AND depart_date = '2026-12-10'",
            (watch_id, run_id),
        )
    monkeypatch.setattr(scan_module, "sample_pairs", only(date(2026, 12, 11)))
    harness.scan(watch_id)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert run.query_results[0]["depart"] == "2026-12-10"
    assert run.query_results[0].get("pinned") is True


def test_already_sampled_pair_is_moved_first_not_doubled(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)

    def main_card_last(pairs: list[DatePair], limit: int, offset: int) -> Any:
        return sorted(pairs, key=lambda p: p.depart, reverse=True), offset, False

    monkeypatch.setattr(scan_module, "sample_pairs", main_card_last)
    harness.scan(watch_id)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert [e["depart"] for e in run.query_results] == ["2026-12-10", "2026-12-11"]
    assert run.query_results[0].get("pinned") is True
    assert run.queries_used == 2


def test_fresh_price_replaces_the_old_card(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = first_round(harness)
    harness.source.prices[CHEAP] = 9_500  # the old cheapest went up
    monkeypatch.setattr(scan_module, "sample_pairs", only(date(2026, 12, 11)))
    harness.scan(watch_id)
    page = harness.client.get(f"/watches/{watch_id}").text
    card = page.split('class="price-card"', 1)[1].split("</section>", 1)[0]
    assert "9,000" in card and "7,000" not in card


def test_no_pin_without_a_price(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    harness.source.prices[CHEAP] = 7_000
    watch_id = flexible_round_trip(harness)
    monkeypatch.setattr(scan_module, "sample_pairs", only(date(2026, 12, 11)))
    harness.scan(watch_id)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert [e["depart"] for e in run.query_results] == ["2026-12-11"]


def test_departed_pair_is_not_pinned(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_id = first_round(harness)
    # 01:00 on 12/11 in Taipei: 12/10 has departed, 12/11 has not.
    harness.clock.now = datetime(2026, 12, 10, 17, 0, tzinfo=UTC)
    watch = harness.repo.get_watch(watch_id)
    scan = harness.services.scan
    stale_pairs = [DatePair(date(2026, 12, 10), date(2026, 12, 15))]
    # Even when handed the departed pair, the helper finds no current main card for it.
    assert scan._main_card_pair(watch, stale_pairs, harness.clock.now) is None
    monkeypatch.setattr(scan_module, "sample_pairs", only(date(2026, 12, 11)))
    harness.scan(watch_id)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert [e["depart"] for e in run.query_results] == ["2026-12-11"]


def test_other_revision_is_not_pinned(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    watch_id = first_round(harness)
    result = harness.services.watches.update(
        watch_id,
        {
            "name": "東京十二月",
            "destination": "NRT",
            "trip_type": "round_trip",
            "date_mode": "flexible",
            "window_start": "2026-12-10",
            "window_end": "2026-12-16",
            "min_trip_days": 5,
            "max_trip_days": 5,
            "budget": 12000,
            "max_stops": "0",
        },
    )
    assert result.ok, result.errors
    monkeypatch.setattr(scan_module, "sample_pairs", only(date(2026, 12, 11)))
    harness.scan(watch_id)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert [e["depart"] for e in run.query_results] == ["2026-12-11"]
