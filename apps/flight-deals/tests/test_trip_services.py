"""FD-5 through services, storage and pages: revision, dedupe, labels, booking links
(ADR-0002 FD-5 Decisions 2, 5, 7, 8; C-38, C-40, C-42; PRD AC-P*, AC-A*, AC-V*, AC-C*)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from flight_deals.app import create_app
from flight_deals.config import Config
from flight_deals.domain.models import FlightSearch, PriceQuote
from flight_deals.domain.trip_labels import BOOKING_FALLBACK_NOTE
from flight_deals.services.views import NO_MATCH_LABEL
from flight_deals.storage.repository import airlines_from_db, airlines_to_db
from tests.conftest import CLIENT_HEADERS, FakeClock, FakeNotifier, Harness, ScriptedSource

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
TFS_PREFIX = "https://www.google.com/travel/flights/search?tfs="
FAMILY: dict[str, Any] = {
    "name": "全家東京",
    "destination": "NRT",
    "trip_type": "round_trip",
    "date_mode": "fixed",
    "depart_date": "2026-12-10",
    "return_date": "2026-12-15",
    "budget": 40000,
    "adults": 2,
    "children": 1,
    "cabin": "business",
    "airlines": ["CI", "br"],
    "dep_hour_from": 6,
    "dep_hour_to": 12,
}


def post(h: Harness, url: str, body: Any) -> Any:
    return h.client.post(url, json=body, headers=CLIENT_HEADERS)


def put(h: Harness, url: str, body: Any) -> Any:
    return h.client.put(url, json=body, headers=CLIENT_HEADERS)


def create_family(h: Harness, **overrides: Any) -> int:
    response = post(h, "/api/watches", {**FAMILY, **overrides})
    assert response.status_code == 201, response.json()
    return int(response.json()["id"])


def price_alerts(h: Harness) -> list[Any]:
    return [n for n in h.repo.list_notifications() if n.kind == "price_alert"]


# ---- create, store, query --------------------------------------------------------------


def test_family_watch_is_stored_and_queried_with_its_options(harness: Harness) -> None:
    watch_id = create_family(harness)  # AC-P1, AC-A2, AC-A9
    spec = harness.repo.get_watch(watch_id).spec
    assert (spec.adults, spec.children, spec.cabin) == (2, 1, "business")
    assert spec.airlines == ("BR", "CI")
    assert (spec.dep_hour_from, spec.dep_hour_to) == (6, 12)
    with harness.repo.db.connect() as conn:
        row = conn.execute("SELECT airlines FROM watch WHERE id = ?", (watch_id,)).fetchone()
    assert row["airlines"] == "BR,CI"
    harness.scan(watch_id)
    search: FlightSearch = harness.source.calls[-1]  # FR-P6: scan uses the watch options
    assert (search.adults, search.children, search.cabin) == (2, 1, "business")
    assert search.airlines == ("BR", "CI") and (search.dep_hour_from, search.dep_hour_to) == (6, 12)


def test_legacy_watch_queries_like_before(harness: Harness) -> None:  # AC-C6
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    search = harness.source.calls[-1]
    assert (search.adults, search.children, search.cabin, search.airlines) == (
        1, 0, "economy", (),
    )  # fmt: skip
    assert (search.dep_hour_from, search.dep_hour_to) == (None, None)


def test_airlines_serialisation_is_one_place() -> None:
    assert airlines_to_db(["ci", "BR", "BR"]) == "BR,CI"
    assert airlines_to_db([]) is None
    assert airlines_from_db(None) == () and airlines_from_db("") == ()
    assert airlines_from_db("CI,BR") == ("BR", "CI")
    hits = [
        p.relative_to(SRC).as_posix()
        for p in (SRC / "storage").rglob("*.py")
        if '",".join' in p.read_text(encoding="utf-8")
    ]
    assert hits == ["storage/repository.py"]


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"adults": 0}, "adults"),
        ({"adults": 10}, "adults"),
        ({"children": -1}, "children"),
        ({"children": 10}, "children"),
        ({"adults": 5, "children": 5}, "children"),
        ({"adults": "abc"}, "adults"),
        ({"adults": ""}, "adults"),
        ({"cabin": "first-class-xyz"}, "cabin"),
        ({"airlines": ["ZZ"]}, "airlines"),
        ({"airlines": ["BR", "CI", "JX", "IT", "JL", "NH"]}, "airlines"),
        ({"dep_hour_from": 24, "dep_hour_to": 23}, "dep_hour_from"),
        ({"dep_hour_from": 12, "dep_hour_to": 6}, "dep_hour_to"),
        ({"dep_hour_from": 6, "dep_hour_to": None}, "dep_hour_to"),
        ({"dep_hour_from": 6, "dep_hour_to": 7.5}, "dep_hour_to"),
        ({"dep_hour_from": "早上", "dep_hour_to": 12}, "dep_hour_from"),
    ],
)
def test_api_rejects_bad_options_without_writing(
    harness: Harness, overrides: dict[str, Any], field: str
) -> None:  # AC-P4, AC-A3, AC-A4, AC-A11
    response = post(harness, "/api/watches", {**FAMILY, **overrides})
    assert response.status_code == 422
    assert field in response.json()["errors"]
    assert harness.repo.list_watches() == []


def test_api_five_airlines_accepted(harness: Harness) -> None:  # AC-A3 (server-side cap)
    watch_id = create_family(harness, airlines=["BR", "CI", "JX", "IT", "JL"])
    assert len(harness.repo.get_watch(watch_id).spec.airlines) == 5


# ---- revision (C-38) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"adults": 3},
        {"children": 0},
        {"cabin": "first"},
        {"airlines": ["BR"]},
        {"airlines": []},
        {"dep_hour_from": 7},
        {"dep_hour_from": None, "dep_hour_to": None},
    ],
)
def test_price_affecting_change_bumps_revision(harness: Harness, change: dict[str, Any]) -> None:
    watch_id = create_family(harness)  # AC-C1, AC-C2
    harness.scan(watch_id)
    assert put(harness, f"/api/watches/{watch_id}", {**FAMILY, **change}).status_code == 200
    watch = harness.repo.get_watch(watch_id)
    assert watch.revision == 2
    detail = harness.services.views.detail_page(watch_id)
    assert detail["has_prices"] is False and detail["old_prices"]


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"airlines": ["CI", "BR"]},
        {"airlines": "br, ci"},
        {"budget": 50000},
        {"name": "改名"},
        {"notify_on_new_low": False},
    ],
)
def test_same_options_do_not_bump_revision(harness: Harness, change: dict[str, Any]) -> None:
    watch_id = create_family(harness)  # AC-C3, AC-C4
    assert put(harness, f"/api/watches/{watch_id}", {**FAMILY, **change}).status_code == 200
    assert harness.repo.get_watch(watch_id).revision == 1


# ---- dedupe across revisions (C-38) ---------------------------------------------------------


def test_switching_back_to_old_settings_alerts_again(harness: Harness) -> None:
    watch_id = create_family(harness)
    harness.source.default_price = 30_000  # total price below the 40,000 budget
    harness.scan(watch_id)
    assert len(price_alerts(harness)) == 1
    harness.scan(watch_id)
    assert len(price_alerts(harness)) == 1  # same revision, same price: no repeat
    put(harness, f"/api/watches/{watch_id}", {**FAMILY, "cabin": "economy"})
    put(harness, f"/api/watches/{watch_id}", FAMILY)  # back to business (revision 3)
    assert harness.repo.get_watch(watch_id).revision == 3
    harness.scan(watch_id)
    alerts = price_alerts(harness)
    assert len(alerts) == 2 and alerts[0].dedupe_key.startswith(f"price:{watch_id}:r3:")
    items = harness.repo.notification_items(alerts[0].id)
    assert items[0].item_key.startswith(f"price:{watch_id}:r3:live:")


def test_budget_compares_total_price(harness: Harness) -> None:  # AC-V1, AC-V2
    watch_id = create_family(harness, adults=2, children=0, budget=30000)
    harness.source.default_price = 32_000  # 16,000 each, still above the total budget
    harness.scan(watch_id)
    assert price_alerts(harness) == []
    harness.source.default_price = 28_000
    harness.clock.advance(hours=7)
    harness.scan(watch_id)
    [alert] = price_alerts(harness)
    assert alert.rule == "below_budget"
    text = harness.notifier.sent[-1]
    assert "TWD 28,000（2 人總價）" in text  # the source total, never divided or multiplied
    assert harness.services.views.list_page()["watches"][0]["min_price"] == "TWD 28,000"


# ---- push text and links (C-40, C-42) ---------------------------------------------------------


def test_push_carries_party_cabin_filters_and_tfs_link(harness: Harness) -> None:  # AC-V5/V7
    watch_id = create_family(harness)
    harness.source.default_price = 30_000
    harness.scan(watch_id)
    text = harness.notifier.sent[-1]
    assert "（來回・2 大 1 小・商務艙）" in text
    assert "篩選：航空公司 長榮、華航；去程出發 06–12 時" in text
    assert "TWD 30,000（2 大 1 小總價）" in text
    assert "查票連結：" + TFS_PREFIX in text and BOOKING_FALLBACK_NOTE not in text


class _BrokenBuilder:
    def url(self, search: FlightSearch) -> str | None:
        raise RuntimeError("encoder changed")


@pytest.fixture
def broken_links(
    config: Config, clock: FakeClock, source: ScriptedSource, notifier: FakeNotifier
) -> Iterator[Harness]:
    app = create_app(
        config,
        sources=[source],
        notifier=notifier,
        clock=clock,
        start_scheduler=False,
        link_builder=_BrokenBuilder(),
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield Harness(app.state.assembly, client, clock, source, notifier)


def test_builder_failure_falls_back_with_note(broken_links: Harness) -> None:  # C-42
    h = broken_links
    watch_id = create_family(h)
    h.source.default_price = 30_000
    h.scan(watch_id)
    text = h.notifier.sent[-1]
    assert "q=Flights%20to%20NRT" in text and BOOKING_FALLBACK_NOTE in text
    detail = h.services.views.detail_page(watch_id)
    assert detail["watch"]["booking_note"] == BOOKING_FALLBACK_NOTE
    assert "q=Flights" in detail["watch"]["booking_url"]
    row = detail["top"][0]
    assert row["booking_note"] == BOOKING_FALLBACK_NOTE and "q=Flights" in row["booking_url"]
    page = h.client.get(f"/watches/{watch_id}").text
    assert BOOKING_FALLBACK_NOTE in page


# ---- read models and pages (C-40) -------------------------------------------------------------


def test_list_row_labels(harness: Harness) -> None:  # AC-A14, AC-V3
    create_family(harness)
    harness.create_watch(name="單人")
    family, single = harness.services.views.list_page()["watches"]
    assert family["pax_note"] == "（2 大 1 小總價）" and family["cabin_label"] == "商務艙"
    assert family["conditions_label"] == "長榮、華航｜去程 06–12 時"
    assert single["pax_note"] == "（1 人總價）" and single["cabin_label"] == "經濟艙"
    assert single["conditions_label"] == "不限"
    page = harness.client.get("/").text
    assert "2 大 1 小總價" in page and "商務艙" in page and "長榮、華航" in page


def test_detail_labels_links_and_prices(harness: Harness) -> None:  # AC-P1, AC-A9, AC-V9
    watch_id = create_family(harness)
    harness.source.default_price = 18_509
    harness.scan(watch_id)
    data = harness.services.views.detail_page(watch_id)
    watch = data["watch"]
    assert watch["pax_full_label"] == "2 位成人、1 位兒童"
    assert watch["cabin_label"] == "商務艙" and watch["airlines_label"] == "長榮、華航"
    assert watch["dep_window_label"] == "去程 06–12 時"
    assert watch["pax_note"] == "（2 大 1 小總價）"
    assert watch["booking_url"].startswith(TFS_PREFIX) and watch["booking_note"] is None
    row = data["top"][0]
    assert row["amount_text"] == "TWD 18,509"
    assert row["booking_url"].startswith(TFS_PREFIX) and row["booking_note"] is None
    assert "depart_time" in row
    page = harness.client.get(f"/watches/{watch_id}").text
    for text in ("2 位成人、1 位兒童", "商務艙", "長榮、華航", "去程 06–12 時", "2 大 1 小總價"):
        assert text in page, text


def test_single_adult_detail_label(harness: Harness) -> None:  # AC-P2, AC-C5
    watch_id = harness.create_watch()
    watch = harness.services.views.detail_page(watch_id)["watch"]
    assert watch["pax_full_label"] == "1 位成人" and watch["cabin_label"] == "經濟艙"
    assert watch["airlines_label"] == "不限" and watch["dep_window_label"] == "不限"
    assert watch["pax_note"] == "（1 人總價）"


def test_old_revision_rows_use_text_link_with_note(harness: Harness) -> None:  # C-42
    watch_id = create_family(harness)
    harness.scan(watch_id)
    put(harness, f"/api/watches/{watch_id}", {**FAMILY, "adults": 3})
    old = harness.services.views.detail_page(watch_id)["old_prices"]
    assert old and old[0]["booking_note"] == BOOKING_FALLBACK_NOTE
    assert "q=Flights" in old[0]["booking_url"]


def test_no_match_with_filters_is_explained_not_failed(harness: Harness) -> None:  # AC-A13
    watch_id = create_family(harness, airlines=["QF"])
    harness.source.default_price = None  # the source answers no_data
    outcome = harness.scan(watch_id)
    assert outcome.status == "ok"
    run = harness.services.views.detail_page(watch_id)["last_run"]
    assert {p["status"] for p in run["pairs"]} == {NO_MATCH_LABEL}
    assert harness.repo.get_source_health("google_flights").consecutive_failures == 0
    assert price_alerts(harness) == [] and harness.notifier.sent == []
    plain = harness.create_watch()
    harness.scan(plain)
    run = harness.services.views.detail_page(plain)["last_run"]
    assert {p["status"] for p in run["pairs"]} == {"查無航班"}


def test_notifications_page_has_party_note(harness: Harness) -> None:  # AC-V3
    watch_id = create_family(harness)
    harness.source.default_price = 30_000
    harness.scan(watch_id)
    [row] = harness.services.views.notifications_page()["notifications"]
    assert row["pax_note"] == "（2 大 1 小總價）"
    assert "2 大 1 小總價" in harness.client.get("/notifications").text
    put(harness, f"/api/watches/{watch_id}", {**FAMILY, "adults": 3})
    [row] = harness.services.views.notifications_page()["notifications"]
    assert row["pax_note"] is None  # older revision: the party is only in the message text


def test_digest_line_has_party_and_cabin(harness: Harness) -> None:  # AC-V6
    watch_id = create_family(harness)
    harness.source.default_price = 50_000
    harness.scan(watch_id)
    text = harness.services.digest.compose(harness.clock())
    line = next(line for line in text.splitlines() if line.startswith("• 全家東京"))
    assert "商務艙" in line and "TWD 50,000（2 大 1 小總價）" in line


def test_form_values_and_options(harness: Harness) -> None:  # AC-P6
    new = harness.services.views.form_values(None)
    assert (new["adults"], new["children"], new["cabin"], new["airlines"]) == (
        1, 0, "economy", [],
    )  # fmt: skip
    watch_id = create_family(harness)
    values = harness.services.views.form_values(watch_id)
    assert (values["adults"], values["children"], values["cabin"]) == (2, 1, "business")
    assert values["airlines"] == ["BR", "CI"]
    assert (values["dep_hour_from"], values["dep_hour_to"]) == (6, 12)
    options = harness.services.views.form_options(values)
    assert [c["value"] for c in options["cabin_options"]] == [
        "economy", "premium_economy", "business", "first",
    ]  # fmt: skip
    assert options["cabin_options"][2]["label"] == "商務艙"
    first = options["airline_options"][0]
    assert first == {"code": "BR", "zh_name": "長榮航空", "display_name": "長榮"}
    legacy = harness.services.views.form_options({"airlines": ["ZZ"]})["airline_options"]
    assert legacy[-1]["code"] == "ZZ"  # kept so an unchanged legacy code survives an edit
    page = harness.client.get(f"/watches/{watch_id}/edit").text
    assert 'value="BR" checked' in page and "長榮航空" in page


def test_views_no_longer_hardcode_cabin_or_party() -> None:  # C-40
    text = (SRC / "services" / "views.py").read_text(encoding="utf-8")
    assert "經濟艙" not in text and '"adults": 1' not in text


def test_depart_time_round_trips_through_storage(harness: Harness) -> None:
    watch_id = harness.create_watch()
    run = harness.repo.insert_scan_run(
        watch_id=watch_id,
        revision=1,
        trigger="manual",
        started_at=harness.clock(),
        sampled_pairs=[],
        total_pairs=0,
        limit_reached=False,
    )
    now = harness.clock()
    base = PriceQuote(
        source="google_flights",
        price_kind="live",
        depart_date=date(2026, 12, 10),
        return_date=None,
        amount_minor=100,
        currency="TWD",
        as_of=now,
        as_of_basis="fetch_time",
        fetched_at=now,
        carrier="BR",
        stops=0,
        duration_minutes=200,
        depart_time="07:55",
    )
    harness.repo.insert_observation(scan_run_id=run, watch_id=watch_id, revision=1, quote=base)
    harness.repo.insert_observation(
        scan_run_id=run, watch_id=watch_id, revision=1, quote=replace(base, depart_time=None)
    )
    stored = sorted((o.depart_time or "") for o in harness.repo.observations_for_watch(watch_id))
    assert stored == ["", "07:55"]


# ---- FD-5 batch 2: pages without embedded results -------------------------------------


def _no_embedded_html() -> str:
    from tests.test_sources import other_only, page_html, sha_payload

    payload = other_only(sha_payload())
    payload[3] = None  # both sections absent, as captured for round trip + business + 2A1C
    return page_html(payload)


def test_no_embedded_results_is_explained_and_never_a_failure(harness: Harness) -> None:
    from flight_deals.services.views import NO_EMBEDDED_LABEL
    from tests.test_partial_prices import use_pages

    use_pages(harness, _no_embedded_html())
    watch_id = create_family(harness)
    for _ in range(5):  # more rounds than watch_stale_after_failed_scans
        assert harness.scan(watch_id).status == "ok"
        harness.clock.advance(hours=7)
    watch = harness.repo.get_watch(watch_id)
    assert watch.status == "active" and watch.consecutive_failed_scans == 0
    health = harness.repo.get_source_health("google_flights")
    assert health.consecutive_failures == 0 and health.breaker_state == "closed"
    assert harness.services.views.settings_page()["health"][0]["state_key"] == "ok"
    assert harness.repo.list_notifications() == []  # no ops alert, no price alert
    run = harness.repo.scan_runs_for_watch(watch_id)[0]
    assert run.query_results[0]["status"] == "no_data"
    assert run.query_results[0]["reason"] == "no_embedded_results"
    assert run.error_summary is None
    detail = harness.services.views.detail_page(watch_id)
    assert {p["status"] for p in detail["last_run"]["pairs"]} == {NO_EMBEDDED_LABEL}
    assert detail["last_run"]["no_embedded_note"] == NO_EMBEDDED_LABEL
    [row] = harness.services.views.list_page()["watches"]
    assert row["no_embedded_note"] == NO_EMBEDDED_LABEL
    assert NO_EMBEDDED_LABEL in harness.client.get("/").text
    assert NO_EMBEDDED_LABEL in harness.client.get(f"/watches/{watch_id}").text


def test_no_embedded_note_clears_once_results_return(harness: Harness) -> None:
    from tests.test_partial_prices import use_pages
    from tests.test_sources import page_html, sha_payload

    use_pages(harness, _no_embedded_html(), page_html(sha_payload()))
    watch_id = create_family(harness)
    harness.scan(watch_id)
    harness.clock.advance(hours=7)
    harness.scan(watch_id)
    [row] = harness.services.views.list_page()["watches"]
    assert row["no_embedded_note"] is None


def test_partial_update_keeps_trip_options(harness: Harness) -> None:  # qa B2
    watch_id = create_family(harness)
    partial = {
        k: v
        for k, v in FAMILY.items()
        if k not in {"adults", "children", "cabin", "airlines", "dep_hour_from", "dep_hour_to"}
    }
    assert put(harness, f"/api/watches/{watch_id}", {**partial, "budget": 45000}).status_code == 200
    watch = harness.repo.get_watch(watch_id)
    assert watch.revision == 1
    spec = watch.spec
    assert (spec.adults, spec.children, spec.cabin, spec.airlines) == (
        2,
        1,
        "business",
        ("BR", "CI"),
    )
    assert (spec.dep_hour_from, spec.dep_hour_to) == (6, 12)
    # An explicit value still changes it.
    put(harness, f"/api/watches/{watch_id}", {**partial, "adults": 3})
    assert harness.repo.get_watch(watch_id).spec.adults == 3


def test_list_row_pax_short_and_templates_have_no_cabin_literal(harness: Harness) -> None:
    create_family(harness)
    [row] = harness.services.views.list_page()["watches"]
    assert row["pax_short"] == "2 大 1 小總價"
    page = harness.client.get("/").text
    assert "商務艙・2 大 1 小總價" in page
    for name in ("index.html", "watch_form.html"):
        text = (SRC / "web" / "templates" / name).read_text(encoding="utf-8")
        assert "經濟艙" not in text and 'replace("（"' not in text, name
