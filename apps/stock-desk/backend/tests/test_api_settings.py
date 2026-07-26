"""API tests for ``GET/PUT /api/settings`` and the SQLite settings store."""

from __future__ import annotations

from pathlib import Path

from app.api.settings import RATE_PROVENANCE_NOTE
from app.settings.models import AppSettings, AppSettingsPatch, CostModelSettings
from app.settings.store import SettingsStore
from tests.conftest import ApiHarness


def test_get_returns_the_three_sections_with_defaults(api_harness: ApiHarness) -> None:
    body = api_harness.client.get("/api/settings").json()
    assert set(body["settings"]) == {"risk_budget", "cost_model", "alerts"}
    assert body["settings"]["risk_budget"]["max_position_weight"] == 0.15
    assert body["settings"]["alerts"]["evaluation_interval_minutes"] == 60
    assert "as_of" in body


def test_unverified_rates_are_flagged_on_read(api_harness: ApiHarness) -> None:
    body = api_harness.client.get("/api/settings").json()
    assert body["rates_verified"] is False
    assert RATE_PROVENANCE_NOTE in body["notes"]


def test_put_persists_and_round_trips(api_harness: ApiHarness) -> None:
    response = api_harness.client.put(
        "/api/settings",
        json={
            "risk_budget": {"max_position_weight": 0.2, "max_loss_per_trade": 0.02},
            "alerts": {"evaluation_interval_minutes": 15, "cooldown_minutes": 0},
        },
    )
    assert response.status_code == 200
    stored = api_harness.client.get("/api/settings").json()["settings"]
    assert stored["risk_budget"]["max_position_weight"] == 0.2
    assert stored["risk_budget"]["max_loss_per_trade"] == 0.02
    assert stored["alerts"]["evaluation_interval_minutes"] == 15
    assert stored["alerts"]["cooldown_minutes"] == 0


def test_omitted_sections_are_left_untouched(api_harness: ApiHarness) -> None:
    api_harness.client.put("/api/settings", json={"alerts": {"enabled": False}})
    api_harness.client.put("/api/settings", json={"risk_budget": {"max_position_weight": 0.3}})
    stored = api_harness.client.get("/api/settings").json()["settings"]
    assert stored["alerts"]["enabled"] is False
    assert stored["risk_budget"]["max_position_weight"] == 0.3


def test_kelly_policy_bounds_survive_the_settings_page(api_harness: ApiHarness) -> None:
    # The caps on RiskBudget are policy, not preference: the API must not let a
    # settings write raise fractional Kelly past a quarter or the hard cap past 10%.
    for field, value in (("kelly_fraction_cap", 0.5), ("kelly_position_cap", 0.2)):
        response = api_harness.client.put("/api/settings", json={"risk_budget": {field: value}})
        assert response.status_code == 422
        locs = [tuple(err["loc"]) for err in response.json()["detail"]]
        assert ("body", "risk_budget", field) in locs


def test_out_of_range_values_are_422_not_clamped(api_harness: ApiHarness) -> None:
    response = api_harness.client.put(
        "/api/settings", json={"risk_budget": {"max_position_weight": 5}}
    )
    assert response.status_code == 422
    stored = api_harness.client.get("/api/settings").json()["settings"]
    assert stored["risk_budget"]["max_position_weight"] == 0.15


def test_unknown_field_is_rejected_rather_than_ignored(api_harness: ApiHarness) -> None:
    response = api_harness.client.put(
        "/api/settings", json={"risk_budget": {"max_positon_weight": 0.2}}
    )
    assert response.status_code == 422


def test_cost_model_verified_on_must_be_an_iso_date(api_harness: ApiHarness) -> None:
    assert (
        api_harness.client.put(
            "/api/settings", json={"cost_model": {"verified_on": "yesterday"}}
        ).status_code
        == 422
    )
    response = api_harness.client.put(
        "/api/settings", json={"cost_model": {"verified_on": "2026-08-01"}}
    )
    assert response.status_code == 200
    assert response.json()["rates_verified"] is True
    assert response.json()["notes"] == []


# --- Store-level behaviour ---------------------------------------------------


def test_store_round_trips_every_section(tmp_path: Path) -> None:
    store = SettingsStore(db_path=tmp_path / "settings.db")
    saved = store.save(
        AppSettingsPatch(cost_model=CostModelSettings(slippage_bps=7.5)).apply_to(store.load())
    )
    assert store.load() == saved
    assert store.load().cost_model.slippage_bps == 7.5


def test_store_falls_back_to_defaults_for_a_corrupt_section(tmp_path: Path) -> None:
    # An older build could have written a shape the schema no longer accepts.
    # Settings are preferences: serve the conservative default rather than
    # refusing to answer at all.
    store = SettingsStore(db_path=tmp_path / "settings.db")
    store.save(AppSettings())
    import sqlite3

    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE app_settings SET payload = ? WHERE section = 'risk_budget'",
            ('{"max_position_weight": "nonsense"}',),
        )
    assert store.load().risk_budget.max_position_weight == 0.15


def test_cost_model_settings_convert_to_the_backtest_dataclass() -> None:
    settings = CostModelSettings(slippage_bps=3.0, verified_on="2026-08-01")
    model = settings.to_cost_model()
    assert model.slippage_bps == 3.0
    assert model.verified_on == "2026-08-01"
    assert CostModelSettings.from_cost_model(model) == settings
