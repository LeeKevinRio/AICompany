"""API tests for ``GET/PUT /api/settings`` and the SQLite settings store."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.advice.limits import NET_WORTH_SOFT_NOTICE_DAYS, NET_WORTH_STALE_AFTER_DAYS
from app.api.settings import (
    QUOTA_UNCONFIGURED_NOTE,
    QUOTA_UNREADABLE_NOTE,
    RATE_PROVENANCE_NOTE,
)
from app.data.quota import QuotaLedger, QuotaUsage
from app.settings.models import (
    AppSettings,
    AppSettingsPatch,
    CostModelSettings,
    NetWorthSettings,
)
from app.settings.store import SettingsStore
from tests.api_helpers import position_payload, recent_bars, trending_closes
from tests.conftest import ApiHarness


def test_get_returns_every_section_with_defaults(api_harness: ApiHarness) -> None:
    body = api_harness.client.get("/api/settings").json()
    assert set(body["settings"]) == {"risk_budget", "cost_model", "alerts", "net_worth"}
    assert body["settings"]["risk_budget"]["max_position_weight"] == 0.15
    assert body["settings"]["alerts"]["evaluation_interval_minutes"] == 60
    assert body["settings"]["net_worth"] == {
        "total_net_worth_twd": None,
        "updated_at": None,
        "valued_book_twd_at_report": None,
    }
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


def test_hard_ceilings_survive_the_settings_page(api_harness: ApiHarness) -> None:
    # The settings page used to accept a 100% single-name weight and 200% gross
    # exposure with no gate. Both are now hard ceilings, and the 422 has to say
    # so rather than leaving the user with a bare "invalid value".
    for field, ceiling in (("max_position_weight", 0.50), ("max_gross_exposure", 1.50)):
        response = api_harness.client.put(
            "/api/settings", json={"risk_budget": {field: ceiling + 0.01}}
        )
        assert response.status_code == 422
        errors = [
            err for err in response.json()["detail"] if tuple(err["loc"])[-1:] == (field,)
        ]
        assert errors, response.json()
        assert f"{ceiling:.2f}" in errors[0]["msg"]
        assert "硬性上界" in errors[0]["msg"]
        assert "風控" in errors[0]["msg"] and "CEO" in errors[0]["msg"]


def test_openapi_states_the_ceilings_the_validators_enforce(api_harness: ApiHarness) -> None:
    # These two bounds live in validators, not in ``le=``, so the 422 can keep
    # its own wording -- but a validator contributes no ``maximum`` keyword, so
    # a reader of /openapi.json (or a generated client) would otherwise see an
    # unbounded number. The description has to state the bound instead.
    schemas = api_harness.client.get("/openapi.json").json()["components"]["schemas"]
    properties = schemas["RiskBudget"]["properties"]
    for field, ceiling in (("max_position_weight", 0.50), ("max_gross_exposure", 1.50)):
        assert "maximum" not in properties[field]
        description = properties[field]["description"]
        assert f"{ceiling:.2f}" in description
        assert "422" in description
    # The fields bounded the ordinary way still publish a machine-readable one.
    assert properties["kelly_fraction_cap"]["maximum"] == 0.25


def test_a_cap_may_be_written_up_to_its_ceiling(api_harness: ApiHarness) -> None:
    response = api_harness.client.put(
        "/api/settings",
        json={"risk_budget": {"max_position_weight": 0.50, "max_gross_exposure": 1.50}},
    )
    assert response.status_code == 200
    stored = api_harness.client.get("/api/settings").json()["settings"]["risk_budget"]
    assert stored["max_position_weight"] == 0.50
    assert stored["max_gross_exposure"] == 1.50


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


# --- FR-9: the self-reported account net worth -------------------------------


def _valued_book(harness: ApiHarness) -> float:
    """What the API itself says the valued positions are worth, in TWD."""
    summary = harness.client.get("/api/portfolio/summary").json()
    return float(summary["totals"]["market_value_twd"])


def _seed_valued_position(harness: ApiHarness) -> float:
    """Give the harness one priced holding and return the book's TWD value."""
    harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    harness.client.post("/api/positions", json=position_payload())
    valued = _valued_book(harness)
    assert valued > 0.0
    return valued


def _put_net_worth(harness: ApiHarness, amount: float) -> Any:
    return harness.client.put("/api/settings", json={"net_worth": {"total_net_worth_twd": amount}})


def test_net_worth_round_trips_with_the_time_it_was_reported(
    api_harness: ApiHarness,
) -> None:
    # AC-9.1: the value persists, and so does when the user last stood behind it.
    _seed_valued_position(api_harness)
    response = _put_net_worth(api_harness, 3_000_000.0)
    assert response.status_code == 200

    stored = api_harness.client.get("/api/settings").json()
    assert stored["settings"]["net_worth"]["total_net_worth_twd"] == 3_000_000.0
    written_at = stored["settings"]["net_worth"]["updated_at"]
    assert written_at is not None
    assert datetime.fromisoformat(written_at).tzinfo is not None
    block = stored["net_worth"]
    assert block["updated_at"] == written_at
    assert block["age_days"] == 0
    assert block["freshness"] == "fresh"


def test_the_net_worth_field_states_that_it_converts_no_currency(
    api_harness: ApiHarness,
) -> None:
    # FR-9 (f): a USD figure typed here is off by roughly thirty times, and this
    # sentence is the first line of defence against that.
    notes = " ".join(api_harness.client.get("/api/settings").json()["net_worth"]["notes"])
    assert "請自行換算為台幣後填入" in notes
    assert "不會為此欄位做匯率換算" in notes


def test_an_unreported_net_worth_says_which_cap_stays_off(api_harness: ApiHarness) -> None:
    # AC-9.2 as the settings page sees it: nothing is claimed, and the
    # consequence of the empty field is spelled out.
    block = api_harness.client.get("/api/settings").json()["net_worth"]
    assert block["freshness"] == "absent"
    assert block["total_net_worth_twd"] is None
    assert block["age_days"] is None
    assert any("not_evaluable" in note for note in block["notes"])


def test_a_non_positive_net_worth_is_refused_and_changes_nothing(
    api_harness: ApiHarness,
) -> None:
    # FR-9 (c) row 1. 422 per field, and emphatically not a clamp to some
    # "nearest legal" value the user never typed.
    _seed_valued_position(api_harness)
    _put_net_worth(api_harness, 3_000_000.0)
    for amount in (0, -1):
        response = _put_net_worth(api_harness, amount)
        assert response.status_code == 422
        locs = [tuple(err["loc"]) for err in response.json()["detail"]]
        assert ("body", "net_worth", "total_net_worth_twd") in locs
    stored = api_harness.client.get("/api/settings").json()["settings"]["net_worth"]
    assert stored["total_net_worth_twd"] == 3_000_000.0


def test_a_net_worth_below_the_valued_book_is_refused_with_the_reason(
    api_harness: ApiHarness,
) -> None:
    # FR-9 (c) row 2: this is almost always a cash balance in the wrong field,
    # and accepting it would pin the exposure cap at "violated" forever.
    valued = _seed_valued_position(api_harness)
    response = _put_net_worth(api_harness, valued * 0.5)
    assert response.status_code == 422
    assert "自報淨值小於系統已估值的部位市值" in response.json()["detail"]
    # Nothing was written, and nothing was quietly adjusted upwards either.
    stored = api_harness.client.get("/api/settings").json()["settings"]["net_worth"]
    assert stored["total_net_worth_twd"] is None


def test_the_five_percent_tolerance_is_real(api_harness: ApiHarness) -> None:
    # A close-based valuation and a broker app read minutes apart differ; the
    # band exists so that ordinary gap is not treated as a typo.
    valued = _seed_valued_position(api_harness)
    assert _put_net_worth(api_harness, valued * 0.96).status_code == 200
    assert _put_net_worth(api_harness, valued * 0.9).status_code == 422


def test_a_net_worth_far_above_the_book_is_stored_but_warned_about(
    api_harness: ApiHarness,
) -> None:
    # FR-9 (c) row 3: holding mostly cash is legitimate, so this is accepted --
    # but an inflated denominator makes the cap agree with everything forever,
    # and only the user can tell the two cases apart.
    valued = _seed_valued_position(api_harness)
    response = _put_net_worth(api_harness, valued * 11)
    assert response.status_code == 200
    warnings = response.json()["net_worth"]["warnings"]
    assert warnings
    assert "若此數字有誤，第 3 條上限將失去意義" in warnings[0]
    stored = api_harness.client.get("/api/settings").json()["settings"]["net_worth"]
    assert stored["total_net_worth_twd"] == valued * 11


def test_ten_times_the_book_is_inside_the_band(api_harness: ApiHarness) -> None:
    valued = _seed_valued_position(api_harness)
    response = _put_net_worth(api_harness, valued * 10)
    assert response.status_code == 200
    assert response.json()["net_worth"]["warnings"] == []


def test_the_far_above_disclosure_survives_every_later_read(
    api_harness: ApiHarness,
) -> None:
    # A warning shown once and never again leaves the user believing the
    # exposure cap is guarding them while an inflated denominator makes it
    # agree with everything. It is restated on every read, from the yardstick
    # stored with the report, and stays in ``warnings`` (what must be seen)
    # rather than sinking into the small print.
    valued = _seed_valued_position(api_harness)
    _put_net_worth(api_harness, valued * 11)
    for _ in range(3):
        block = api_harness.client.get("/api/settings").json()["net_worth"]
        assert block["warnings"]
        assert "第 3 條上限將失去意義" in block["warnings"][0]
        assert "輸入當下" in block["warnings"][0]


def test_the_standing_disclosure_costs_no_price_lookup(api_harness: ApiHarness) -> None:
    # It is restated from ``valued_book_twd_at_report``, not from a fresh
    # valuation: opening the settings page must not spend provider budget.
    valued = _seed_valued_position(api_harness)
    _put_net_worth(api_harness, valued * 11)
    before = len(api_harness.price_service.calls)
    api_harness.client.get("/api/settings")
    assert len(api_harness.price_service.calls) == before


def test_the_yardstick_is_stored_with_the_report(api_harness: ApiHarness) -> None:
    valued = _seed_valued_position(api_harness)
    _put_net_worth(api_harness, valued * 2)
    stored = api_harness.client.get("/api/settings").json()["settings"]["net_worth"]
    assert stored["valued_book_twd_at_report"] == pytest.approx(valued)


def test_no_yardstick_is_invented_when_nothing_could_be_valued(
    api_harness: ApiHarness,
) -> None:
    # A stored zero would later read as a comparison that happened and would
    # make every figure look infinitely above the book.
    _put_net_worth(api_harness, 3_000_000.0)
    body = api_harness.client.get("/api/settings").json()
    assert body["settings"]["net_worth"]["valued_book_twd_at_report"] is None
    assert body["net_worth"]["warnings"] == []


def test_a_corrected_net_worth_drops_the_standing_disclosure(
    api_harness: ApiHarness,
) -> None:
    # The disclosure follows the figure, not the user: entering a plausible
    # one clears it, because the yardstick is re-measured on every write.
    valued = _seed_valued_position(api_harness)
    _put_net_worth(api_harness, valued * 11)
    _put_net_worth(api_harness, valued * 2)
    block = api_harness.client.get("/api/settings").json()["net_worth"]
    assert block["warnings"] == []


def test_without_a_valued_book_only_the_positive_rule_can_be_applied(
    api_harness: ApiHarness,
) -> None:
    # No position could be priced, so there is no yardstick for the relative
    # bands. The response says the check was skipped rather than implying the
    # figure was vetted.
    response = _put_net_worth(api_harness, 3_000_000.0)
    assert response.status_code == 200
    notes = " ".join(response.json()["net_worth"]["notes"])
    assert "無法用部位市值檢查" in notes


def test_the_report_time_is_the_servers_not_the_callers(api_harness: ApiHarness) -> None:
    # A client-supplied timestamp would let a stale figure look fresh, which is
    # exactly what the freshness rule exists to prevent.
    response = api_harness.client.put(
        "/api/settings",
        json={
            "net_worth": {
                "total_net_worth_twd": 3_000_000.0,
                "updated_at": "2020-01-01T00:00:00+00:00",
            }
        },
    )
    assert response.status_code == 422


def test_saving_another_section_does_not_refresh_the_net_worth(
    api_harness: ApiHarness,
) -> None:
    # The settings form leaves this section out unless the user acted on it;
    # saving a fee rate must not make an untouched figure look re-confirmed.
    _put_net_worth(api_harness, 3_000_000.0)
    first = api_harness.client.get("/api/settings").json()["settings"]["net_worth"]
    api_harness.client.put("/api/settings", json={"cost_model": {"slippage_bps": 4.0}})
    after = api_harness.client.get("/api/settings").json()["settings"]["net_worth"]
    assert after == first


def _store_net_worth(harness: ApiHarness, *, days_ago: int) -> None:
    """Write a net worth reported ``days_ago`` days back, straight to the store."""
    reported_at = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    current = harness.settings.load()
    harness.settings.save(
        current.model_copy(
            update={
                "net_worth": NetWorthSettings(
                    total_net_worth_twd=3_000_000.0, updated_at=reported_at
                )
            }
        )
    )


def test_an_ageing_net_worth_is_flagged_while_it_is_still_usable(
    api_harness: ApiHarness,
) -> None:
    # FR-9 (b), soft half: the cap does not simply vanish one morning.
    _store_net_worth(api_harness, days_ago=NET_WORTH_SOFT_NOTICE_DAYS + 1)
    block = api_harness.client.get("/api/settings").json()["net_worth"]
    assert block["freshness"] == "ageing"
    assert block["age_days"] == NET_WORTH_SOFT_NOTICE_DAYS + 1
    assert any("未更新" in note for note in block["notes"])


def test_an_expired_net_worth_says_the_cap_has_gone_back_to_not_evaluable(
    api_harness: ApiHarness,
) -> None:
    # AC-9.4 as the settings page sees it.
    _store_net_worth(api_harness, days_ago=NET_WORTH_STALE_AFTER_DAYS + 5)
    block = api_harness.client.get("/api/settings").json()["net_worth"]
    assert block["freshness"] == "expired"
    assert any("not_evaluable" in note for note in block["notes"])
    assert any(f"超過 {NET_WORTH_STALE_AFTER_DAYS} 天未更新" in note for note in block["notes"])


def test_a_stored_non_positive_net_worth_falls_back_to_none(tmp_path: Path) -> None:
    # The forgiving read (see the store's docstring) meets the positivity rule:
    # a row an older build could have written is dropped back to "not reported"
    # rather than served as a denominator no ratio can use.
    store = SettingsStore(db_path=tmp_path / "settings.db")
    store.save(AppSettings())
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE app_settings SET payload = ? WHERE section = 'net_worth'",
            ('{"total_net_worth_twd": 0, "updated_at": "2026-08-01T00:00:00+00:00"}',),
        )
    assert store.load().net_worth.total_net_worth_twd is None


def test_reading_the_settings_page_prices_nothing(api_harness: ApiHarness) -> None:
    # The relative bands need the book valued; the freshness block does not.
    # A read that valued positions would spend provider budget every time the
    # page is opened, so it must not.
    _seed_valued_position(api_harness)
    before = len(api_harness.price_service.calls)
    api_harness.client.get("/api/settings")
    api_harness.client.put("/api/settings", json={"alerts": {"enabled": False}})
    assert len(api_harness.price_service.calls) == before


# --- Data-source block (ADR-0005 決策三 point 6) ------------------------------


def _quota_block(harness: ApiHarness) -> dict[str, Any]:
    quotas = harness.client.get("/api/settings").json()["data_sources"]["quotas"]
    block: dict[str, Any] = next(
        block for block in quotas if block["provider"] == "alpha_vantage"
    )
    return block


def test_quota_block_reports_todays_usage_after_a_reservation(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALPHA_VANTAGE_DAILY_LIMIT", "25")
    monkeypatch.setenv("ALPHA_VANTAGE_SAFETY_MARGIN", "2")
    monkeypatch.setenv("QUOTA_RESET_TZ", "UTC")
    for _ in range(3):
        api_harness.quota.reserve("alpha_vantage", limit_value=23)

    block = _quota_block(api_harness)
    assert block["used"] == 3
    assert block["limit_value"] == 23  # 25 minus the safety margin
    assert block["remaining"] == 20
    assert block["quota_date"] == datetime.now(UTC).date().isoformat()
    assert block["reset_tz"] == "UTC"


def test_quota_block_reports_a_real_zero_before_the_first_call_of_the_day(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No ledger row exists yet today. That is "nothing spent", not "unknown",
    # and the configured cap is still the day's denominator.
    monkeypatch.setenv("ALPHA_VANTAGE_DAILY_LIMIT", "25")
    monkeypatch.setenv("ALPHA_VANTAGE_SAFETY_MARGIN", "2")
    block = _quota_block(api_harness)
    assert block["used"] == 0
    assert block["limit_value"] == 23
    assert block["remaining"] == 23
    assert QUOTA_UNCONFIGURED_NOTE not in block["notes"]


def test_quota_block_withholds_the_limit_when_none_is_configured(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No configured cap means no denominator: the remaining count is withheld
    # rather than guessed, and the note says the primary source is inert.
    monkeypatch.delenv("ALPHA_VANTAGE_DAILY_LIMIT", raising=False)
    block = _quota_block(api_harness)
    assert block["used"] == 0
    assert block["limit_value"] is None
    assert block["remaining"] is None
    assert QUOTA_UNCONFIGURED_NOTE in block["notes"]


def test_quota_block_discloses_the_unverified_reset_boundary(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ADR-0005 決策三 point 4 records the reset timezone as unverified; the
    # disclosure travels with the number it qualifies.
    monkeypatch.setenv("ALPHA_VANTAGE_DAILY_LIMIT", "25")
    notes = " ".join(_quota_block(api_harness)["notes"])
    assert "未經查證" in notes
    assert "ALPHA_VANTAGE_DAILY_LIMIT" in notes


def test_quota_block_survives_an_unreadable_ledger(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The ledger is in the database the scheduler process writes to as well. A
    # locked file must degrade this one block, not the settings page.
    monkeypatch.setenv("ALPHA_VANTAGE_DAILY_LIMIT", "25")

    def _boom(*args: object, **kwargs: object) -> QuotaUsage | None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(QuotaLedger, "status", _boom)
    response = api_harness.client.get("/api/settings")
    assert response.status_code == 200
    block = _quota_block(api_harness)
    assert block["used"] is None
    assert block["remaining"] is None
    assert QUOTA_UNREADABLE_NOTE in block["notes"]
    # The rest of the document is unaffected.
    assert response.json()["settings"]["risk_budget"]["max_position_weight"] == 0.15


def test_reading_settings_never_spends_a_quota_slot(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The block is an observation. If it reserved, opening the settings page
    # would consume the budget it is there to report on.
    monkeypatch.setenv("ALPHA_VANTAGE_DAILY_LIMIT", "25")
    api_harness.quota.reserve("alpha_vantage", limit_value=23)
    for _ in range(5):
        api_harness.client.get("/api/settings")
    api_harness.client.put("/api/settings", json={"alerts": {"enabled": False}})
    assert _quota_block(api_harness)["used"] == 1


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


def test_a_stored_budget_above_a_ceiling_falls_back_to_defaults(tmp_path: Path) -> None:
    # A build shipped before the ceilings existed could have written 0.99 here.
    # The forgiving read then serves the conservative default for the section
    # rather than honouring a cap that is no longer allowed -- the safe
    # direction, and the only one available while a section is validated whole.
    store = SettingsStore(db_path=tmp_path / "settings.db")
    store.save(AppSettings())
    import sqlite3

    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE app_settings SET payload = ? WHERE section = 'risk_budget'",
            ('{"max_position_weight": 0.99}',),
        )
    assert store.load().risk_budget.max_position_weight == 0.15


def test_cost_model_settings_convert_to_the_backtest_dataclass() -> None:
    settings = CostModelSettings(slippage_bps=3.0, verified_on="2026-08-01")
    model = settings.to_cost_model()
    assert model.slippage_bps == 3.0
    assert model.verified_on == "2026-08-01"
    assert CostModelSettings.from_cost_model(model) == settings
