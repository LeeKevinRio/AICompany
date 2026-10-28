"""FD-2 airport table, search, validation and display (ADR-0002 C-19..C-25)."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pytest

from flight_deals.domain import airports
from flight_deals.domain.airports import (
    MAX_QUERY_LENGTH,
    MAX_RESULTS,
    PLACES,
    Place,
    city_airports,
    is_selectable,
    lookup,
    normalize,
    place_label,
    route_label,
    same_city_group,
    search_places,
    suggestion_label,
)
from flight_deals.domain.currency import major_to_minor
from flight_deals.domain.messages import BANNED_PHRASES, price_alert_message
from flight_deals.domain.models import WatchSpec
from flight_deals.domain.rules import Candidate, TriggeredItem
from flight_deals.domain.validation import (
    ORIGIN_REQUIRED,
    SAME_CITY,
    UNKNOWN_PLACE,
    UNVERIFIED_CITY,
    validate_watch_input,
)
from flight_deals.notify.telegram import MAX_MESSAGE_LENGTH
from flight_deals.services.airports import suggest
from tests.conftest import CLIENT_HEADERS, Harness

TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 4, 0, tzinfo=UTC)


def codes(q: str) -> list[str]:
    return [p.code for p in search_places(q)]


# ---- C-19 data integrity ------------------------------------------------------------


def test_table_size_and_fields() -> None:  # AC-D1
    assert 100 <= len(PLACES) <= 150
    for place in PLACES:
        assert re.fullmatch(r"[A-Z]{3}", place.code), place
        assert place.kind in ("airport", "city")
        for text in (place.zh_name, place.display_name, place.en_name, place.country_zh):
            assert text and text == text.strip(), place
        assert len(place.display_name) <= 8, place


def test_codes_unique() -> None:
    all_codes = [p.code for p in PLACES]
    assert len(all_codes) == len(set(all_codes))


def test_city_code_points_to_city() -> None:  # AC-D2
    for place in PLACES:
        if place.kind == "city":
            assert place.city_code is None, place
        elif place.city_code is not None:
            parent = lookup(place.city_code)
            assert parent is not None and parent.kind == "city", place
    for city in (p for p in PLACES if p.kind == "city"):
        assert city_airports(city.code), city


def test_verified_cities_have_notes() -> None:  # AC-D3
    for place in PLACES:
        if place.city_query_verified:
            assert place.kind == "city" and place.verified_note, place
            assert "2026-" in place.verified_note
        if place.kind == "airport":
            assert not place.city_query_verified and place.verified_note is None


def test_known_city_verification_facts() -> None:  # AC-D2, AC-D3
    tyo, osa, lon = lookup("TYO"), lookup("OSA"), lookup("LON")
    assert tyo and osa and lon
    assert tyo.kind == "city" and tyo.city_query_verified
    assert osa.kind == "city" and osa.city_query_verified
    assert {p.code for p in city_airports("TYO")} == {"NRT", "HND"}
    assert lon.kind == "city" and not is_selectable(lon)
    nrt = lookup("NRT")
    assert nrt and nrt.kind == "airport" and nrt.city_code == "TYO"
    assert {"LHR", "LGW"} <= {p.code for p in city_airports("LON")}


def test_taiwan_airports_and_short_names() -> None:  # AC-D6, FR-F5
    for code in ("TPE", "TSA", "KHH", "RMQ"):
        place = lookup(code)
        assert place is not None and is_selectable(place)
    assert place_label("TPE") == "台北桃園 TPE"
    assert place_label("TSA") == "台北松山 TSA"


def test_regions_covered() -> None:  # AC-D1
    countries = {p.country_zh for p in PLACES}
    for country in ("台灣", "日本", "韓國", "香港", "澳門", "中國", "泰國", "新加坡", "越南"):
        assert country in countries
    for country in ("美國", "加拿大", "英國", "法國", "德國", "澳洲", "紐西蘭"):
        assert country in countries


def test_header_cites_source_date_and_checker() -> None:  # C-23, AC-D4
    doc = airports.__doc__ or ""
    assert "iata.org" in doc and "2026-10-26" in doc and "dev-lead" in doc


def test_place_names_have_no_banned_wording() -> None:  # C-17 / AC-S4
    for place in PLACES:
        texts = [
            place.zh_name,
            place.display_name,
            place.country_zh,
            *place.aliases,
            suggestion_label(place),
            place_label(place.code),
        ]
        for text in texts:
            for phrase in BANNED_PHRASES:
                assert phrase not in text, (phrase, text)


# ---- C-20 search and ranking ----------------------------------------------------------


def test_east_finds_tokyo_city_and_airports() -> None:  # AC-Q1
    assert codes("東")[:3] == ["TYO", "NRT", "HND"]


def test_code_match_first_and_case_insensitive() -> None:  # AC-Q2, AC-Q5
    assert codes("nrt")[0] == "NRT"
    assert codes("nrt") == codes("NRT") == codes(" Nrt ")


def test_english_prefix() -> None:  # AC-Q3
    assert {"TYO", "NRT", "HND"} <= set(codes("tok"))


def test_no_results() -> None:  # AC-Q6
    assert codes("ZZZ") == [] and codes("xyzxyz") == []
    assert codes("") == [] and codes("   ") == []


def test_normalization() -> None:
    assert normalize("臺北") == "台北"
    assert codes("臺北") == codes("台北")
    assert codes("ＮＲＴ")[0] == "NRT"


def test_ranking_tiers_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # AC-Q4 with a synthetic table
    table = (
        Place("ZZD", "airport", None, "某地zzaq", "某地", "Somewhere", "測試"),
        Place("ZZC", "airport", None, "某處", "某處", "Zzaq Field", "測試"),
        Place("ZZB", "airport", None, "zzaq中心", "中心", "Center", "測試"),
        Place("ZZAQ", "airport", None, "無關", "無關", "Unrelated", "測試"),
    )
    index = tuple((p, normalize(p.code), *airports._names(p)) for p in table)
    monkeypatch.setattr(airports, "_SEARCH_INDEX", index)
    # Table order is the reverse of tier order, so the result proves tier-first sorting:
    # exact code > zh-name prefix > en-name prefix > contains.
    assert codes("zzaq") == ["ZZAQ", "ZZB", "ZZC", "ZZD"]
    monkeypatch.undo()
    real = codes("han")
    assert real[0] == "HAN"  # exact code before "Haneda" / "Hangzhou" prefixes
    assert real.index("HND") < real.index("SHA")  # en prefix before contains ("Shanghai")


def test_ties_keep_table_order_city_first() -> None:
    assert codes("大阪")[:3] == ["OSA", "KIX", "ITM"]


def test_result_limit_for_every_single_character() -> None:  # AC-Q7, C-20
    chars = {ch for p in PLACES for ch in p.zh_name + p.en_name}
    for ch in chars | set("abcdefghijklmnopqrstuvwxyz"):
        assert len(search_places(ch)) <= MAX_RESULTS
    assert len(search_places("a", limit=50)) == MAX_RESULTS


def test_unverified_city_hidden_but_airports_found_by_city_name() -> None:  # AC-D3
    for q in ("倫敦", "london", "LON", "巴黎", "paris", "札幌"):
        assert not {"LON", "PAR", "SPK"} & set(codes(q)), q
    assert {"LHR", "LGW"} <= set(codes("倫敦"))
    assert {"LHR", "LGW"} <= set(codes("london"))
    assert {"CDG", "ORY"} <= set(codes("巴黎"))
    assert "CTS" in codes("札幌")


def test_suggest_shape() -> None:
    items = suggest("成田")
    assert items[0] == {
        "code": "NRT",
        "kind": "airport",
        "label": "東京成田國際機場 NRT（日本）",
        "display": "東京成田 NRT",
    }
    tyo = suggest("東")[0]
    assert tyo["kind"] == "city" and tyo["label"] == "東京（所有機場）TYO（日本）"


# ---- C-21 validation ------------------------------------------------------------------


def base(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "origin": "TPE",
        "destination": "NRT",
        "trip_type": "round_trip",
        "date_mode": "fixed",
        "depart_date": "2026-12-10",
        "return_date": "2026-12-15",
        "budget": "12000",
    }
    values.update(overrides)
    return values


def existing_spec(**overrides: Any) -> WatchSpec:
    outcome = validate_watch_input(base(), TODAY)
    assert outcome.spec is not None
    return replace(outcome.spec, **overrides)


def test_unknown_code_rejected() -> None:  # AC-V1
    outcome = validate_watch_input(base(destination="ZZZ"), TODAY)
    assert outcome.spec is None and outcome.errors["destination"] == UNKNOWN_PLACE
    outcome = validate_watch_input(base(origin="QQQ"), TODAY)
    assert outcome.errors["origin"] == UNKNOWN_PLACE
    outcome = validate_watch_input(base(destination="TOKYO"), TODAY)
    assert outcome.errors["destination"] == UNKNOWN_PLACE


def test_blank_origin_is_not_defaulted() -> None:  # second line of defence for the form
    for blank in ("", "   "):
        outcome = validate_watch_input(base(origin=blank), TODAY)
        assert outcome.spec is None
        assert outcome.errors["origin"] == ORIGIN_REQUIRED
    raw = base()
    del raw["origin"]
    outcome = validate_watch_input(raw, TODAY)
    assert outcome.spec is not None and outcome.spec.origin == "TPE"


def test_unknown_place_wording_matches_prd() -> None:  # FR-V2 / AC-V1
    assert UNKNOWN_PLACE == "找不到此機場或城市，請從下拉選取"


def test_island_aliases() -> None:
    assert codes("濟州島")[0] == "CJU"
    assert codes("普吉島")[0] == "HKT" and codes("布吉")[0] == "HKT"


def test_lowercase_normalized() -> None:  # AC-V2
    outcome = validate_watch_input(base(origin="tsa", destination="nrt"), TODAY)
    assert outcome.spec is not None
    assert (outcome.spec.origin, outcome.spec.destination) == ("TSA", "NRT")


def test_unverified_city_rejected_airport_ok() -> None:  # AC-V3
    outcome = validate_watch_input(base(destination="LON"), TODAY)
    assert outcome.errors["destination"] == UNVERIFIED_CITY
    assert validate_watch_input(base(destination="LHR"), TODAY).spec is not None
    assert validate_watch_input(base(destination="TYO"), TODAY).spec is not None


def test_same_code_and_same_city_rejected() -> None:  # AC-V4, FR-V3
    assert validate_watch_input(base(destination="TPE"), TODAY).errors["destination"]
    for origin, destination in (("TYO", "NRT"), ("NRT", "HND"), ("HND", "TYO"), ("KIX", "UKB")):
        outcome = validate_watch_input(base(origin=origin, destination=destination), TODAY)
        assert outcome.errors.get("destination") == SAME_CITY, (origin, destination)
    assert validate_watch_input(base(origin="NRT", destination="KIX"), TODAY).spec is not None


def test_edit_keeps_unchanged_legacy_code() -> None:  # AC-C1, FR-C1
    legacy = existing_spec(destination="XYZ")
    raw = base(destination="XYZ", budget="9000")
    assert validate_watch_input(raw, TODAY, legacy).spec is not None
    assert validate_watch_input(raw, TODAY).errors["destination"] == UNKNOWN_PLACE
    changed = validate_watch_input(base(destination="XYW"), TODAY, legacy)
    assert changed.errors["destination"] == UNKNOWN_PLACE
    assert validate_watch_input(base(destination="HND"), TODAY, legacy).spec is not None


def test_edit_cannot_switch_to_unverified_city() -> None:
    existing = existing_spec()
    outcome = validate_watch_input(base(destination="PAR"), TODAY, existing)
    assert outcome.errors["destination"] == UNVERIFIED_CITY


def test_same_city_group_helper() -> None:
    assert same_city_group("TYO", "NRT") and same_city_group("NRT", "HND")
    assert not same_city_group("TPE", "NRT")
    assert not same_city_group("XYZ", "NRT")


# ---- display (FR-S1..S3) and C-25 ----------------------------------------------------------


def test_route_label_and_fallback() -> None:  # AC-S1, AC-S3
    assert route_label("TPE", "NRT") == "台北桃園 TPE → 東京成田 NRT"
    assert route_label("TPE", "TYO") == "台北桃園 TPE → 東京 TYO"
    assert route_label("XYZ", "NRT") == "XYZ → 東京成田 NRT"
    assert place_label("xyz") == "xyz"


def _items(count: int) -> list[TriggeredItem]:
    return [
        TriggeredItem(
            candidate=Candidate(
                observation_id=None,
                depart_date=date(2026, 12, 1 + i),
                return_date=date(2026, 12, 20 + i),
                amount_minor=major_to_minor(99_999, "TWD"),
                currency="TWD",
                price_kind="cached",
                source="google_flights",
                carrier="Carrier Name " * 4,
                fetched_at=NOW,
            ),
            reasons=("below_budget", "drop_pct", "new_low"),
            drop_percent=99,
            item_key=f"k{i}",
        )
        for i in range(count)
    ]


def test_alert_length_with_longest_names() -> None:  # C-25, AC-S2
    longest = max((p for p in PLACES if is_selectable(p)), key=lambda p: len(p.display_name))
    other = next(p for p in PLACES if p.code != longest.code and len(p.display_name) >= 6)
    text = price_alert_message(
        watch_name="名" * 80,
        origin=longest.code,
        destination=other.code,
        trip_type="round_trip",
        items=_items(5),
        links=[None] * 5,
    )
    assert len(text) < MAX_MESSAGE_LENGTH
    assert route_label(longest.code, other.code) in text
    for phrase in BANNED_PHRASES:
        assert phrase not in text


def test_alert_route_growth_is_small() -> None:  # AC-S2: growth is per item route line only
    items = _items(1)
    new = price_alert_message(
        watch_name="w",
        origin="TPE",
        destination="NRT",
        trip_type="round_trip",
        items=items,
        links=[None],
    )
    old_route, new_route = "TPE→NRT", route_label("TPE", "NRT")
    assert new_route in new
    growth = len(new_route) - len(old_route)
    assert 0 < growth <= 20


# ---- web endpoint (C-20) ---------------------------------------------------------------


def test_api_airports_basic(harness: Harness) -> None:
    response = harness.client.get("/api/airports", params={"q": "東"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, max-age=300"
    items = response.json()["items"]
    assert [i["code"] for i in items[:3]] == ["TYO", "NRT", "HND"]
    assert items[0]["label"] == "東京（所有機場）TYO（日本）"
    assert items[1] == {
        "code": "NRT",
        "kind": "airport",
        "label": "東京成田國際機場 NRT（日本）",
        "display": "東京成田 NRT",
    }


def test_api_airports_empty_and_limits(harness: Harness) -> None:
    for params in ({}, {"q": ""}, {"q": "   "}):
        response = harness.client.get("/api/airports", params=params)
        assert response.status_code == 200 and response.json() == {"items": []}
    assert harness.client.get("/api/airports", params={"q": "ZZZ"}).json() == {"items": []}
    for q in ("a", "國", "機場", "i"):
        assert len(harness.client.get("/api/airports", params={"q": q}).json()["items"]) <= 10
    ok = harness.client.get("/api/airports", params={"q": "a" * MAX_QUERY_LENGTH})
    assert ok.status_code == 200
    too_long = harness.client.get("/api/airports", params={"q": "a" * (MAX_QUERY_LENGTH + 1)})
    assert too_long.status_code == 422 and "q" in too_long.json()["errors"]


def test_api_airports_needs_no_client_header(harness: Harness) -> None:
    response = harness.client.get("/api/airports", params={"q": "nrt"}, headers={})
    assert response.status_code == 200 and response.json()["items"][0]["code"] == "NRT"


def test_api_blank_origin_rejected(harness: Harness) -> None:
    response = harness.client.post("/api/watches", json=base(origin=""), headers=CLIENT_HEADERS)
    assert response.status_code == 422
    assert response.json()["errors"]["origin"] == ORIGIN_REQUIRED
    assert harness.repo.list_watches() == []


def test_api_rejects_out_of_table_codes(harness: Harness) -> None:  # AC-V1, AC-V3
    body = {**base(destination="ZZZ")}
    response = harness.client.post("/api/watches", json=body, headers=CLIENT_HEADERS)
    assert response.status_code == 422
    assert response.json()["errors"]["destination"] == UNKNOWN_PLACE
    response = harness.client.post(
        "/api/watches", json=base(destination="LON"), headers=CLIENT_HEADERS
    )
    assert response.json()["errors"]["destination"] == UNVERIFIED_CITY
    assert harness.repo.list_watches() == []


def test_pages_show_route_labels(harness: Harness) -> None:  # AC-S1
    watch_id = harness.create_watch()
    assert "台北桃園 TPE → 東京成田 NRT" in harness.client.get("/").text
    assert "台北桃園 TPE → 東京成田 NRT" in harness.client.get(f"/watches/{watch_id}").text


def test_form_values_include_labels(harness: Harness) -> None:  # AC-F5, AC-F10
    new = harness.services.views.form_values(None)
    assert new["origin"] == "TPE" and new["origin_label"] == "台北桃園 TPE"
    assert new["destination"] == "" and new["destination_label"] == ""
    watch_id = harness.create_watch()
    values = harness.services.views.form_values(watch_id)
    assert values["origin_label"] == "台北桃園 TPE"
    assert values["destination_label"] == "東京成田 NRT"


def test_legacy_code_watch_still_works(harness: Harness) -> None:  # AC-S3, AC-V5, AC-C1
    legacy = existing_spec(destination="XYZ", name="legacy")
    watch_id = harness.repo.insert_watch(legacy, NOW)
    page = harness.client.get("/").text
    assert "台北桃園 TPE → XYZ" in page
    assert harness.client.get(f"/watches/{watch_id}").status_code == 200
    assert harness.client.get(f"/watches/{watch_id}/edit").status_code == 200
    assert harness.services.views.form_values(watch_id)["destination_label"] == "XYZ"
    harness.scan(watch_id)
    assert harness.repo.get_watch(watch_id).last_scanned_at is not None
    response = harness.client.put(
        f"/api/watches/{watch_id}",
        json=base(destination="XYZ", budget="9000"),
        headers=CLIENT_HEADERS,
    )
    assert response.status_code == 200


@pytest.mark.parametrize("q", ["nrt", "東京", "tok"])
def test_endpoint_matches_domain_ranking(harness: Harness, q: str) -> None:  # C-22
    api = [i["code"] for i in harness.client.get("/api/airports", params={"q": q}).json()["items"]]
    assert api == codes(q)
