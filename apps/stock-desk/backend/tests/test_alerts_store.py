"""Storage-level tests for alert rules and events (SQLite, no API)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.alerts.models import AlertRuleInput
from app.alerts.store import AlertStore
from tests.alerts_helpers import add_rule, limit_rule, price_rule, signal_rule

_NOW = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> AlertStore:
    return AlertStore(db_path=tmp_path / "alerts.db")


def test_rule_round_trips_including_its_params(store: AlertStore) -> None:
    created = add_rule(store, signal_rule(field="macd.histogram", op="lt", value=-0.5))
    fetched = store.get_rule(created.id)
    assert fetched == created
    assert fetched is not None
    assert fetched.params.condition.field == "macd.histogram"  # type: ignore[union-attr]


def test_every_rule_type_survives_a_round_trip(store: AlertStore) -> None:
    for payload in (price_rule(), price_rule(above=False), signal_rule(), limit_rule()):
        add_rule(store, payload)
    assert len(store.list_rules()) == 4
    assert len(store.list_rules(enabled_only=True)) == 4


def test_disabled_rules_are_excluded_from_the_enabled_listing(store: AlertStore) -> None:
    add_rule(store, price_rule(enabled=False))
    assert store.list_rules() != []
    assert store.list_rules(enabled_only=True) == []


def test_get_and_delete_missing_rule(store: AlertStore) -> None:
    assert store.get_rule(999) is None
    assert store.delete_rule(999) is False


def test_store_reports_the_database_file_it_uses(tmp_path: Path) -> None:
    store = AlertStore(db_path=tmp_path / "alerts.db")
    assert store.db_path == tmp_path / "alerts.db"
    assert store.db_path.exists()


def test_events_are_listed_newest_first(store: AlertStore) -> None:
    rule = add_rule(store, price_rule())
    for offset in range(3):
        store.append_event(
            rule=rule,
            message=f"事件 {offset}",
            observed={"n": float(offset)},
            triggered_at=_NOW + timedelta(minutes=offset),
        )
    messages = [event.message for event in store.list_events()]
    assert messages == ["事件 2", "事件 1", "事件 0"]


def test_event_limit_is_respected(store: AlertStore) -> None:
    rule = add_rule(store, price_rule())
    for offset in range(5):
        store.append_event(
            rule=rule,
            message=f"e{offset}",
            observed={},
            triggered_at=_NOW + timedelta(minutes=offset),
        )
    assert len(store.list_events(limit=2)) == 2


def test_last_triggered_at_drives_the_cooldown(store: AlertStore) -> None:
    rule = add_rule(store, price_rule())
    assert store.last_triggered_at(rule.id) is None
    store.append_event(rule=rule, message="x", observed={}, triggered_at=_NOW)
    store.append_event(
        rule=rule, message="y", observed={}, triggered_at=_NOW + timedelta(hours=2)
    )
    assert store.last_triggered_at(rule.id) == _NOW + timedelta(hours=2)


def test_acknowledge_sets_the_flag_and_the_timestamp(store: AlertStore) -> None:
    rule = add_rule(store, price_rule())
    event = store.append_event(rule=rule, message="x", observed={}, triggered_at=_NOW)
    acked = store.acknowledge(event.id, now=_NOW + timedelta(minutes=5))
    assert acked is not None
    assert acked.acknowledged is True
    assert acked.acknowledged_at == _NOW + timedelta(minutes=5)
    assert store.list_events(unacknowledged=True) == []
    assert store.list_events(unacknowledged=False) == [acked]


def test_acknowledging_a_missing_event_returns_none(store: AlertStore) -> None:
    assert store.acknowledge(999) is None
    assert store.get_event(999) is None


def test_deleting_a_rule_keeps_its_events(store: AlertStore) -> None:
    rule = add_rule(store, price_rule())
    store.append_event(rule=rule, message="x", observed={}, triggered_at=_NOW)
    assert store.delete_rule(rule.id) is True
    # Events are an append-only record of what was observed; they outlive the rule.
    assert len(store.list_events()) == 1


def test_rule_model_rejects_a_params_block_of_the_wrong_type() -> None:
    with pytest.raises(ValueError):
        AlertRuleInput.model_validate(
            {"type": "risk_limit_breach", "symbol": "2330", "params": {"threshold": 100}}
        )


def test_rule_model_rejects_a_non_positive_threshold() -> None:
    with pytest.raises(ValueError):
        AlertRuleInput.model_validate(
            {"type": "price_above", "symbol": "2330", "params": {"threshold": 0}}
        )


# --- Rule editing (FR-1) ------------------------------------------------------


def test_update_rule_keeps_the_id_and_created_at(store: AlertStore) -> None:
    created = add_rule(store, price_rule(threshold=1000.0))
    updated = store.update_rule(
        created.id,
        AlertRuleInput.model_validate(price_rule(threshold=1050.0)),
        now=_NOW,
    )
    assert updated is not None
    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.updated_at == _NOW
    assert updated.params.threshold == 1050.0  # type: ignore[union-attr]


def test_update_rule_replaces_the_params_document_on_a_type_switch(
    store: AlertStore,
) -> None:
    created = add_rule(store, price_rule(threshold=1000.0))
    updated = store.update_rule(
        created.id, AlertRuleInput.model_validate(limit_rule(limit_id="sector_weight"))
    )
    assert updated is not None
    assert updated.type == "risk_limit_breach"
    # Stored as one JSON document per rule, so nothing of the price rule is left.
    assert updated.params.model_dump() == {"limit_id": "sector_weight"}


def test_updating_a_missing_rule_returns_none(store: AlertStore) -> None:
    assert store.update_rule(999, AlertRuleInput.model_validate(price_rule())) is None


def test_editing_a_rule_keeps_its_events(store: AlertStore) -> None:
    rule = add_rule(store, price_rule(threshold=1000.0))
    store.append_event(rule=rule, message="觸發", observed={"close": 1100.0})
    store.update_rule(rule.id, AlertRuleInput.model_validate(price_rule(threshold=1200.0)))
    events = store.list_events()
    assert [event.rule_id for event in events] == [rule.id]
    assert store.last_triggered_at(rule.id) is not None
