"""API tests for the alert rule CRUD, the event feed, and the manual tick."""

from __future__ import annotations

from tests.alerts_helpers import limit_rule, price_rule, signal_rule
from tests.api_helpers import position_payload, recent_bars, trending_closes
from tests.conftest import ApiHarness

# --- Rule CRUD ---------------------------------------------------------------


def test_create_and_list_rules(api_harness: ApiHarness) -> None:
    response = api_harness.client.post("/api/alerts", json=price_rule(threshold=700.0))
    assert response.status_code == 201
    created = response.json()
    assert created["id"] >= 1
    assert created["params"]["threshold"] == 700.0

    body = api_harness.client.get("/api/alerts").json()
    assert [item["id"] for item in body["items"]] == [created["id"]]
    assert "as_of" in body


def test_list_can_be_restricted_to_enabled_rules(api_harness: ApiHarness) -> None:
    api_harness.client.post("/api/alerts", json=price_rule(threshold=700.0))
    api_harness.client.post("/api/alerts", json=price_rule(threshold=800.0, enabled=False))
    all_rules = api_harness.client.get("/api/alerts").json()["items"]
    enabled = api_harness.client.get(
        "/api/alerts", params={"enabled_only": True}
    ).json()["items"]
    assert len(all_rules) == 2
    assert len(enabled) == 1


def test_every_rule_type_round_trips(api_harness: ApiHarness) -> None:
    for payload in (price_rule(), price_rule(above=False), signal_rule(), limit_rule()):
        assert api_harness.client.post("/api/alerts", json=payload).status_code == 201
    types = {item["type"] for item in api_harness.client.get("/api/alerts").json()["items"]}
    assert types == {"price_above", "price_below", "signal_condition", "risk_limit_breach"}


def test_params_must_match_the_declared_type(api_harness: ApiHarness) -> None:
    payload = price_rule()
    payload["params"] = {"limit_id": "any"}
    response = api_harness.client.post("/api/alerts", json=payload)
    assert response.status_code == 422
    assert "params" in response.text


def test_signal_condition_rejects_a_field_outside_the_vocabulary(
    api_harness: ApiHarness,
) -> None:
    response = api_harness.client.post(
        "/api/alerts", json=signal_rule(field="moon_phase.last")
    )
    assert response.status_code == 422
    assert "未知的欄位" in response.text


def test_delete_rule_then_missing_is_404(api_harness: ApiHarness) -> None:
    created = api_harness.client.post("/api/alerts", json=price_rule()).json()
    assert api_harness.client.delete(f"/api/alerts/{created['id']}").status_code == 204
    response = api_harness.client.delete(f"/api/alerts/{created['id']}")
    assert response.status_code == 404
    assert "找不到指定的警示規則" in response.json()["detail"]


# --- Rule editing (FR-1) ------------------------------------------------------


def test_put_edits_a_threshold_in_place_keeping_the_rule_id(api_harness: ApiHarness) -> None:
    # AC-1.1: the id survives the edit, which is the whole reason this endpoint
    # exists instead of delete-and-recreate.
    created = api_harness.client.post("/api/alerts", json=price_rule(threshold=1000.0)).json()
    response = api_harness.client.put(
        f"/api/alerts/{created['id']}", json=price_rule(threshold=1050.0)
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == created["id"]
    assert updated["params"]["threshold"] == 1050.0
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] >= created["updated_at"]
    listed = api_harness.client.get("/api/alerts").json()["items"]
    assert [item["params"]["threshold"] for item in listed] == [1050.0]


def test_an_edited_rule_keeps_the_events_it_already_raised(api_harness: ApiHarness) -> None:
    # AC-1.1 second half: history stays attached because the id never moved.
    _seed_market(api_harness)
    rule = api_harness.client.post("/api/alerts", json=price_rule(threshold=100.0)).json()
    api_harness.client.post("/api/alerts/evaluate")
    api_harness.client.put(f"/api/alerts/{rule['id']}", json=price_rule(threshold=101.0))
    events = api_harness.client.get("/api/alerts/events").json()["items"]
    assert [event["rule_id"] for event in events] == [rule["id"]]


def test_patch_toggles_enabled_and_leaves_every_other_field_alone(
    api_harness: ApiHarness,
) -> None:
    # AC-1.2.
    created = api_harness.client.post(
        "/api/alerts", json=price_rule(threshold=700.0, note="原註記")
    ).json()
    updated = api_harness.client.patch(
        f"/api/alerts/{created['id']}", json={"enabled": False}
    ).json()
    assert updated["enabled"] is False
    assert updated["params"]["threshold"] == 700.0
    assert updated["note"] == "原註記"
    assert updated["type"] == created["type"]
    # A disabled rule is skipped by the next tick.
    assert api_harness.client.get(
        "/api/alerts", params={"enabled_only": True}
    ).json()["items"] == []


def test_patch_can_clear_a_note_only_when_asked_to(api_harness: ApiHarness) -> None:
    created = api_harness.client.post(
        "/api/alerts", json=price_rule(note="原註記")
    ).json()
    kept = api_harness.client.patch(
        f"/api/alerts/{created['id']}", json={"note": None}
    ).json()
    assert kept["note"] == "原註記"
    cleared = api_harness.client.patch(
        f"/api/alerts/{created['id']}", json={"clear_note": True}
    ).json()
    assert cleared["note"] is None


def test_clear_note_wins_over_a_note_sent_in_the_same_patch(
    api_harness: ApiHarness,
) -> None:
    # The contradictory pair has to resolve the same way every time, so it is
    # pinned here rather than left to whichever branch of ``apply_to`` runs
    # first: ``clear_note`` is the field that exists solely to answer "keep or
    # remove", so it decides, and a note sent beside it is ignored.
    created = api_harness.client.post(
        "/api/alerts", json=price_rule(note="原註記")
    ).json()
    response = api_harness.client.patch(
        f"/api/alerts/{created['id']}", json={"note": "新註記", "clear_note": True}
    )
    assert response.status_code == 200
    assert response.json()["note"] is None
    # And it is what was stored, not only what was echoed back.
    assert api_harness.client.get("/api/alerts").json()["items"][0]["note"] is None


def test_an_invalid_edit_is_422_and_changes_nothing(api_harness: ApiHarness) -> None:
    # AC-1.3: no partial write; the stored rule keeps its old value.
    created = api_harness.client.post("/api/alerts", json=price_rule(threshold=1000.0)).json()
    responses = (
        api_harness.client.put(
            f"/api/alerts/{created['id']}", json=price_rule(threshold=-100.0)
        ),
        api_harness.client.patch(
            f"/api/alerts/{created['id']}", json={"params": {"threshold": -100.0}}
        ),
    )
    for response in responses:
        assert response.status_code == 422
        stored = api_harness.client.get("/api/alerts").json()["items"][0]
        assert stored["params"]["threshold"] == 1000.0


def test_editing_a_missing_rule_is_404(api_harness: ApiHarness) -> None:
    # AC-1.4.
    for response in (
        api_harness.client.put("/api/alerts/999", json=price_rule()),
        api_harness.client.patch("/api/alerts/999", json={"enabled": False}),
    ):
        assert response.status_code == 404
        assert response.json()["detail"] == "找不到指定的警示規則"


def test_put_can_switch_the_rule_type_with_matching_params(api_harness: ApiHarness) -> None:
    # AC-1.5: a full replacement may change the type, and the old type's
    # parameters do not survive it.
    created = api_harness.client.post("/api/alerts", json=price_rule(threshold=1000.0)).json()
    updated = api_harness.client.put(f"/api/alerts/{created['id']}", json=signal_rule()).json()
    assert updated["id"] == created["id"]
    assert updated["type"] == "signal_condition"
    assert "threshold" not in updated["params"]
    assert updated["params"]["condition"]["field"] == "rsi14.last"


def test_a_type_switch_without_matching_params_is_422(api_harness: ApiHarness) -> None:
    created = api_harness.client.post("/api/alerts", json=price_rule(threshold=1000.0)).json()
    # PUT: the body itself is inconsistent.
    payload = price_rule(threshold=1000.0)
    payload["type"] = "signal_condition"
    assert (
        api_harness.client.put(f"/api/alerts/{created['id']}", json=payload).status_code == 422
    )
    # PATCH: the *merged* rule is inconsistent, which is only visible after the
    # merge -- the stored params still belong to the old type.
    response = api_harness.client.patch(
        f"/api/alerts/{created['id']}", json={"type": "signal_condition"}
    )
    assert response.status_code == 422
    assert "params" in response.text
    assert api_harness.client.get("/api/alerts").json()["items"][0]["type"] == "price_above"


def test_patch_rejects_an_unknown_field(api_harness: ApiHarness) -> None:
    created = api_harness.client.post("/api/alerts", json=price_rule()).json()
    response = api_harness.client.patch(
        f"/api/alerts/{created['id']}", json={"threshold": 900.0}
    )
    assert response.status_code == 422


def test_patch_validates_the_signal_vocabulary_after_merging(
    api_harness: ApiHarness,
) -> None:
    created = api_harness.client.post("/api/alerts", json=signal_rule()).json()
    response = api_harness.client.patch(
        f"/api/alerts/{created['id']}",
        json={"params": {"condition": {"field": "moon_phase.last", "op": "gt", "value": 1.0}}},
    )
    assert response.status_code == 422
    assert "未知的欄位" in response.text


# --- Evaluation and events ---------------------------------------------------


def _seed_market(harness: ApiHarness) -> None:
    harness.price_service.seed("2330", recent_bars(trending_closes(200, start=500.0)))
    harness.client.post("/api/positions", json=position_payload())


def test_evaluate_fires_and_the_event_appears_in_the_feed(api_harness: ApiHarness) -> None:
    _seed_market(api_harness)
    api_harness.client.post("/api/alerts", json=price_rule(threshold=100.0))
    result = api_harness.client.post("/api/alerts/evaluate").json()
    assert result["evaluated"] == 1
    assert result["fired"] == 1
    assert result["outcomes"][0]["status"] == "fired"

    events = api_harness.client.get("/api/alerts/events").json()["items"]
    assert len(events) == 1
    assert events[0]["acknowledged"] is False
    assert events[0]["symbol"] == "2330"


def test_evaluate_reports_a_skip_when_the_symbol_has_no_data(
    api_harness: ApiHarness,
) -> None:
    api_harness.client.post("/api/alerts", json=price_rule(symbol="9999", threshold=1.0))
    result = api_harness.client.post("/api/alerts/evaluate").json()
    assert result["fired"] == 0
    assert result["outcomes"][0]["status"] == "skipped"
    assert result["outcomes"][0]["reason"]


def test_events_can_be_filtered_by_acknowledgement(api_harness: ApiHarness) -> None:
    _seed_market(api_harness)
    api_harness.client.post("/api/alerts", json=price_rule(threshold=100.0))
    api_harness.client.post("/api/alerts/evaluate")
    event_id = api_harness.client.get("/api/alerts/events").json()["items"][0]["id"]

    unack = api_harness.client.get(
        "/api/alerts/events", params={"unacknowledged": True}
    ).json()["items"]
    assert len(unack) == 1

    acked = api_harness.client.post(f"/api/alerts/events/{event_id}/ack").json()
    assert acked["acknowledged"] is True
    assert acked["acknowledged_at"] is not None

    assert (
        api_harness.client.get(
            "/api/alerts/events", params={"unacknowledged": True}
        ).json()["items"]
        == []
    )
    assert (
        len(
            api_harness.client.get(
                "/api/alerts/events", params={"unacknowledged": False}
            ).json()["items"]
        )
        == 1
    )


def test_acknowledging_a_missing_event_is_404(api_harness: ApiHarness) -> None:
    response = api_harness.client.post("/api/alerts/events/999/ack")
    assert response.status_code == 404
    assert "找不到指定的警示事件" in response.json()["detail"]


def test_deleting_a_rule_keeps_the_events_it_already_raised(
    api_harness: ApiHarness,
) -> None:
    _seed_market(api_harness)
    rule = api_harness.client.post("/api/alerts", json=price_rule(threshold=100.0)).json()
    api_harness.client.post("/api/alerts/evaluate")
    api_harness.client.delete(f"/api/alerts/{rule['id']}")
    # The event recorded something that happened; deleting the rule does not
    # un-happen it.
    events = api_harness.client.get("/api/alerts/events").json()["items"]
    assert len(events) == 1
    assert events[0]["rule_id"] == rule["id"]


def test_cooldown_from_settings_is_honoured_by_the_manual_tick(
    api_harness: ApiHarness,
) -> None:
    _seed_market(api_harness)
    api_harness.client.put("/api/settings", json={"alerts": {"cooldown_minutes": 60}})
    api_harness.client.post("/api/alerts", json=price_rule(threshold=100.0))
    first = api_harness.client.post("/api/alerts/evaluate").json()
    second = api_harness.client.post("/api/alerts/evaluate").json()
    assert first["fired"] == 1
    assert second["fired"] == 0
    assert second["outcomes"][0]["status"] == "suppressed"


def test_risk_limit_alert_fires_off_the_real_book(api_harness: ApiHarness) -> None:
    # One holding worth ~600k against a book of the same size: the position is
    # 100% of the valued equity, well past the 15% cap.
    _seed_market(api_harness)
    api_harness.client.post("/api/alerts", json=limit_rule(limit_id="single_position_weight"))
    result = api_harness.client.post("/api/alerts/evaluate").json()
    assert result["fired"] == 1
    events = api_harness.client.get("/api/alerts/events").json()["items"]
    assert "單一標的佔比上限" in events[0]["message"]
