"""FD-3 partial price lists end to end: real adapter + scan + views (AC-T1..T5, C-27)."""

from __future__ import annotations

from typing import Any

from flight_deals.domain.models import FlightSearch
from flight_deals.ports import SourceResult
from flight_deals.services.views import parse_notes, try_note
from flight_deals.sources._support import Throttle, TTLCache
from flight_deals.sources.google_flights import GoogleFlightsSource
from tests.conftest import Harness
from tests.test_sources import itineraries, other_only, page_html, sha_payload, unpriced_only

SKIP_NOTE = "略過 2 筆無價格航班"
ONE_WAY_SHA = {
    "destination": "SHA",
    "trip_type": "one_way",
    "depart_date": "2026-12-10",
    "return_date": "",
    "budget": 10000,
}


def use_pages(h: Harness, *pages: str) -> list[str]:
    """Route the harness source through the real Google adapter, one page per query."""
    queue = list(pages)

    def fetch(_search: FlightSearch) -> str:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    adapter = GoogleFlightsSource(
        timeout_seconds=5.0,
        max_attempts=1,
        backoff_base_seconds=0.0,
        throttle=Throttle(0.0),
        cache=TTLCache(0.0),
        fetch=fetch,
        clock=h.clock,
    )

    def handler(query: FlightSearch) -> SourceResult:
        return adapter.search(query)

    h.source.handler = handler
    return queue


def all_priced() -> Any:
    payload = other_only(sha_payload())
    payload[3][0] = [k for k in itineraries(payload) if k[1][0] != []]
    return payload


def malformed_only() -> Any:
    payload = unpriced_only(sha_payload())
    for itinerary in itineraries(payload):
        itinerary[1] = "changed"
    return payload


def last_try(h: Harness, watch_id: int) -> dict[str, Any]:
    run = h.repo.scan_runs_for_watch(watch_id)[0]
    tries: list[dict[str, Any]] = run.query_results[0]["tries"]
    return tries[-1]


def sampled_note(h: Harness, watch_id: int) -> str | None:
    page = h.services.views.detail_page(watch_id)
    note: str | None = page["last_run"]["pairs"][0]["error"]
    return note


def test_mixed_list_records_priced_flights_only(harness: Harness) -> None:  # AC-T1, AC-T2
    use_pages(harness, page_html(sha_payload()))
    watch_id = harness.create_watch(**ONE_WAY_SHA)
    outcome = harness.scan(watch_id)
    assert outcome.status == "ok"
    [obs] = harness.repo.observations_for_watch(watch_id)
    # The cheapest fare sits in the "best flights" section (FD-5 batch 2).
    assert obs.amount_minor == 463300 and obs.source == "google_flights"
    run = harness.repo.scan_runs_for_watch(watch_id)[0]
    assert run.status == "ok" and run.error_summary is None  # C-27: unpriced only -> NULL
    assert run.query_results[0]["status"] == "ok"
    tried = last_try(harness, watch_id)
    assert (tried["itineraries"], tried["unpriced"], tried["malformed"]) == (9, 2, 0)
    assert all(isinstance(tried[k], int) for k in ("itineraries", "unpriced", "malformed"))
    assert sampled_note(harness, watch_id) == SKIP_NOTE
    assert SKIP_NOTE in harness.client.get(f"/watches/{watch_id}").text


def test_all_priced_list_has_no_skip_note(harness: Harness) -> None:  # AC-T2, AC-T5
    use_pages(harness, page_html(all_priced()))
    watch_id = harness.create_watch(**ONE_WAY_SHA)
    assert harness.scan(watch_id).status == "ok"
    [obs] = harness.repo.observations_for_watch(watch_id)
    assert obs.amount_minor == 1265500
    tried = last_try(harness, watch_id)
    assert (tried["itineraries"], tried["unpriced"], tried["malformed"]) == (2, 0, 0)
    assert sampled_note(harness, watch_id) is None
    assert "無價格" not in harness.client.get(f"/watches/{watch_id}").text


def test_all_unpriced_is_no_data_with_note(harness: Harness) -> None:  # AC-T3
    use_pages(harness, page_html(unpriced_only(sha_payload())))
    watch_id = harness.create_watch(**ONE_WAY_SHA)
    harness.scan(watch_id)
    assert harness.repo.count_observations(watch_id) == 0
    run = harness.repo.scan_runs_for_watch(watch_id)[0]
    assert run.query_results[0]["status"] == "no_data" and run.error_summary is None
    page = harness.services.views.detail_page(watch_id)
    assert page["has_prices"] is False
    assert page["last_run"]["pairs"][0]["status_key"] == "no_data"
    assert sampled_note(harness, watch_id) == SKIP_NOTE


def test_skips_do_not_count_as_source_failures(harness: Harness) -> None:  # AC-T4, AC-T4b
    use_pages(
        harness,
        page_html(malformed_only()),
        page_html(malformed_only()),
        page_html(sha_payload()),
        page_html(unpriced_only(sha_payload())),
    )
    watch_id = harness.create_watch(**ONE_WAY_SHA)
    for _ in range(2):  # AC-T4b: a real format change is still a counted failure
        assert harness.scan(watch_id).status == "failed"
    health = harness.repo.get_source_health("google_flights")
    assert health.consecutive_failures == 2 and health.breaker_state == "closed"
    run = harness.repo.scan_runs_for_watch(watch_id)[0]
    assert run.query_results[0]["status"] == "blocked" and run.error_summary

    for _ in range(2):  # mixed list, then all unpriced
        harness.scan(watch_id)
        health = harness.repo.get_source_health("google_flights")
        assert health.consecutive_failures == 0 and health.breaker_state == "closed"
    assert not [n for n in harness.repo.list_notifications() if n.kind == "ops_source_failure"]
    page = harness.services.views.settings_page()
    assert page["health"][0]["state_key"] == "ok"


def test_malformed_items_beside_prices_are_reported(harness: Harness) -> None:
    payload = other_only(sha_payload())
    itineraries(payload)[3][1] = [[None, "?"], "token"]
    use_pages(harness, page_html(payload))
    watch_id = harness.create_watch(**ONE_WAY_SHA)
    assert harness.scan(watch_id).status == "ok"
    run = harness.repo.scan_runs_for_watch(watch_id)[0]
    assert run.error_summary == "google_flights 回應中有 1 筆格式無法辨識"
    assert sampled_note(harness, watch_id) == ("略過 1 筆無價格航班；回應中有 1 筆格式無法辨識")


def test_note_helpers_ignore_non_integer_counts() -> None:
    assert parse_notes({"unpriced": "2", "malformed": True}) == []
    assert parse_notes({"unpriced": 0, "malformed": 0}) == []
    assert parse_notes({}) == []
    assert try_note({"error": "timeout: x", "unpriced": 3}) == ("timeout: x；略過 3 筆無價格航班")
    assert try_note({"error": None}) is None
