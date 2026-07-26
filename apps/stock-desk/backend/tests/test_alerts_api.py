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
