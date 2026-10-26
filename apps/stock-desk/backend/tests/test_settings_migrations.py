"""S2: the stored cap-1 value 0.15 becomes 0.10 once, with a record (CEO #63).

Covers quant constraint 4 (only 0.15 moves, a record with previous/new/time/
basis, idempotent across starts, the four named cases), and the risk review's
S2 附加實作約束 (never ``load`` -> ``save``; only
``risk_budget.max_position_weight`` changes; any invalid section means no
migration, a record, a visible notice, and not one byte of stored data
changed). The last test is the merge gate for the notice copy.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.advice.limits import RiskBudget
from app.api.deps import get_settings_store
from app.main import app
from app.settings import migrations
from app.settings.migrations import (
    CAP1_MIGRATION_BASIS,
    CAP1_MIGRATION_NOTICES,
    NOTICE_PENDING_RISK_REVIEW,
    Cap1MigrationRecord,
)
from app.settings.models import AlertSettings, AppSettings, CostModelSettings
from app.settings.store import SettingsStore
from tests.conftest import ApiHarness

MIGRATED_AT = datetime(2026, 10, 27, 1, 2, 3, tzinfo=UTC)
LATER = datetime(2026, 11, 3, 4, 5, 6, tzinfo=UTC)


def _seed(db: Path, sections: dict[str, str], *, updated_at: str = "2026-01-01T00:00:00+00:00") -> None:
    """Write raw section payloads the way an earlier build would have left them."""
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_settings ("
            "section TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT OR REPLACE INTO app_settings (section, payload, updated_at) VALUES (?, ?, ?)",
            [(name, payload, updated_at) for name, payload in sections.items()],
        )
    conn.close()


def _rows(db: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT section, payload, updated_at FROM app_settings ORDER BY section"
        ).fetchall()
    conn.close()
    return rows


def _full_document(max_position_weight: float, **budget: float) -> dict[str, str]:
    """Every section as a saved build writes it, with cap 1 at ``max_position_weight``."""
    settings = AppSettings(
        risk_budget=RiskBudget(max_position_weight=max_position_weight, **budget),
        cost_model=CostModelSettings(slippage_bps=7.5),
        alerts=AlertSettings(cooldown_minutes=15),
    )
    return {
        name: json.dumps(getattr(settings, name).model_dump(), ensure_ascii=False)
        for name in ("risk_budget", "cost_model", "alerts", "net_worth")
    }


def _record(store: SettingsStore) -> Cap1MigrationRecord:
    record = store.cap1_migration()
    assert record is not None
    return record


# --- The four cases quant constraint 4 names ---------------------------------


def test_a_stored_old_default_becomes_the_new_one_with_a_record(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.15, max_loss_per_trade=0.02))

    store = SettingsStore(db, now=MIGRATED_AT)

    budget = store.load().risk_budget
    assert budget.max_position_weight == 0.10
    record = _record(store)
    assert record.status == "migrated"
    assert record.previous_value == 0.15
    assert record.new_value == 0.10
    assert record.recorded_at == MIGRATED_AT.isoformat()
    assert record.basis == CAP1_MIGRATION_BASIS
    assert "#61" in record.basis and "#63" in record.basis
    assert record.failed_sections == ()


def test_a_stored_custom_value_is_left_exactly_as_stored(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.12))
    before = _rows(db)

    store = SettingsStore(db, now=MIGRATED_AT)

    assert store.load().risk_budget.max_position_weight == 0.12
    assert _rows(db) == before
    record = _record(store)
    assert record.status == "not_applicable"
    assert record.previous_value == 0.12
    assert record.new_value is None


def test_a_never_saved_install_reads_the_new_default(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.db", now=MIGRATED_AT)

    assert store.load().risk_budget.max_position_weight == 0.10
    assert _rows(store.db_path) == []
    record = _record(store)
    assert record.status == "not_applicable"
    assert record.previous_value is None


def test_a_second_start_changes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.15))
    first = _record(SettingsStore(db, now=MIGRATED_AT))
    after_first = _rows(db)

    second = SettingsStore(db, now=LATER)

    assert _rows(db) == after_first
    assert _record(second) == first


# --- Only the old default, only that key -------------------------------------


@pytest.mark.parametrize(
    ("stored", "migrated"),
    [
        (0.15, True),
        (0.15 + 1e-12, True),
        (0.15 - 1e-12, True),
        (0.1501, False),
        (0.1499, False),
        (0.10, False),
        (0.20, False),
    ],
)
def test_only_a_value_equal_to_the_old_default_moves(
    tmp_path: Path, stored: float, migrated: bool
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, _full_document(stored))

    store = SettingsStore(db, now=MIGRATED_AT)

    expected = 0.10 if migrated else stored
    assert store.load().risk_budget.max_position_weight == expected
    assert _record(store).status == ("migrated" if migrated else "not_applicable")


def test_only_max_position_weight_changes(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    document = _full_document(0.15, max_loss_per_trade=0.02, max_sector_weight=0.25)
    _seed(db, document)
    before = {section: (payload, stamp) for section, payload, stamp in _rows(db)}

    SettingsStore(db, now=MIGRATED_AT)

    after = {section: (payload, stamp) for section, payload, stamp in _rows(db)}
    # Every other section's row is not written at all: payload and stamp intact.
    for section in ("cost_model", "alerts", "net_worth"):
        assert after[section] == before[section]
    old_budget = json.loads(before["risk_budget"][0])
    new_budget = json.loads(after["risk_budget"][0])
    assert {k: v for k, v in new_budget.items() if k != "max_position_weight"} == {
        k: v for k, v in old_budget.items() if k != "max_position_weight"
    }
    assert list(new_budget) == list(old_budget)
    assert new_budget["max_position_weight"] == 0.10
    assert after["risk_budget"][1] == MIGRATED_AT.isoformat()
    # The Kelly fields stay on the stored section (quant constraint 5).
    assert new_budget["kelly_fraction_cap"] == old_budget["kelly_fraction_cap"]
    assert new_budget["kelly_position_cap"] == old_budget["kelly_position_cap"]


def test_the_migration_never_goes_through_load_and_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S2 附加實作約束: not ``load`` -> change -> ``save``."""

    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the migration must not call SettingsStore.load/save")

    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.15))
    monkeypatch.setattr(SettingsStore, "load", _refuse)
    monkeypatch.setattr(SettingsStore, "save", _refuse)

    store = SettingsStore(db, now=MIGRATED_AT)

    assert _record(store).status == "migrated"
    monkeypatch.undo()
    assert SettingsStore(db).load().risk_budget.max_position_weight == 0.10


# --- Any invalid section: no migration, a record, nothing touched ------------


@pytest.mark.parametrize(
    ("section", "payload"),
    [
        ("cost_model", '{"slippage_bps": "nonsense"}'),
        ("alerts", "not json at all"),
        ("net_worth", '{"total_net_worth_twd": -5}'),
        ("risk_budget", '{"max_position_weight": 0.15, "removed_field": 1}'),
    ],
)
def test_an_invalid_section_stops_the_migration_and_changes_no_byte(
    tmp_path: Path, section: str, payload: str
) -> None:
    db = tmp_path / "settings.db"
    document = _full_document(0.15)
    document[section] = payload
    _seed(db, document)
    before = _rows(db)

    store = SettingsStore(db, now=MIGRATED_AT)

    assert _rows(db) == before
    record = _record(store)
    assert record.status == "skipped"
    assert record.failed_sections == (section,)
    assert record.new_value is None
    assert record.notice(current_max_position_weight=0.15, surface="settings") is not None
    assert record.notice(current_max_position_weight=0.15, surface="risk_gauge") is not None


def test_a_skip_is_retried_and_migrates_once_the_document_is_repaired(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    document = _full_document(0.15)
    broken = dict(document, cost_model='{"slippage_bps": "nonsense"}')
    _seed(db, broken)
    assert _record(SettingsStore(db, now=MIGRATED_AT)).status == "skipped"

    _seed(db, {"cost_model": document["cost_model"]})
    store = SettingsStore(db, now=LATER)

    assert store.load().risk_budget.max_position_weight == 0.10
    record = _record(store)
    assert record.status == "migrated"
    assert record.recorded_at == LATER.isoformat()


def test_a_restored_pre_migration_backup_is_migrated_and_announced_again(tmp_path: Path) -> None:
    """Risk review point 3 (1): the marker lives in the same file as the value."""
    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.15))
    backup = db.read_bytes()
    SettingsStore(db, now=MIGRATED_AT)

    db.write_bytes(backup)
    for suffix in ("-wal", "-shm"):
        (tmp_path / f"settings.db{suffix}").unlink(missing_ok=True)
    store = SettingsStore(db, now=LATER)

    assert store.load().risk_budget.max_position_weight == 0.10
    assert _record(store).recorded_at == LATER.isoformat()


# --- A user who sets 0.15 back keeps it ---------------------------------------


def test_setting_the_old_value_back_is_not_undone_by_a_later_start(tmp_path: Path) -> None:
    db = tmp_path / "settings.db"
    _seed(db, _full_document(0.15))
    store = SettingsStore(db, now=MIGRATED_AT)
    record = _record(store)
    store.save(
        AppSettings(
            risk_budget=RiskBudget(max_position_weight=0.15),
            cost_model=store.load().cost_model,
            alerts=store.load().alerts,
            net_worth=store.load().net_worth,
        )
    )

    restarted = SettingsStore(db, now=LATER)

    assert restarted.load().risk_budget.max_position_weight == 0.15
    assert _record(restarted) == record


# --- Where the notice shows -----------------------------------------------------


def test_the_gauge_notice_stands_until_the_user_changes_the_value() -> None:
    record = Cap1MigrationRecord(
        status="migrated",
        previous_value=0.15,
        new_value=0.10,
        failed_sections=(),
        basis=CAP1_MIGRATION_BASIS,
        recorded_at=MIGRATED_AT.isoformat(),
    )
    assert record.notice(current_max_position_weight=0.10, surface="risk_gauge") is not None
    assert record.notice(current_max_position_weight=0.12, surface="risk_gauge") is None
    # The settings page keeps the record whatever the current value is.
    assert record.notice(current_max_position_weight=0.12, surface="settings") is not None
    assert record.notice(current_max_position_weight=0.10, surface="settings") is not None


def test_nothing_to_migrate_shows_nothing() -> None:
    record = Cap1MigrationRecord(
        status="not_applicable",
        previous_value=0.12,
        new_value=None,
        failed_sections=(),
        basis=CAP1_MIGRATION_BASIS,
        recorded_at=MIGRATED_AT.isoformat(),
    )
    assert record.notice(current_max_position_weight=0.12, surface="settings") is None
    assert record.notice(current_max_position_weight=0.12, surface="risk_gauge") is None


def test_the_notice_is_the_single_constant_formatted_with_the_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The slot is filled from :data:`CAP1_MIGRATION_NOTICES` and nowhere else."""
    template = (
        "{previous_value}|{new_value}|{previous_percent}|{new_percent}|"
        "{recorded_at}|{failed_sections}"
    )
    monkeypatch.setattr(
        migrations, "CAP1_MIGRATION_NOTICES", {"migrated": template, "skipped": template}
    )
    migrated = Cap1MigrationRecord(
        status="migrated",
        previous_value=0.15,
        new_value=0.10,
        failed_sections=(),
        basis=CAP1_MIGRATION_BASIS,
        recorded_at=MIGRATED_AT.isoformat(),
    )
    assert migrated.notice(current_max_position_weight=0.10, surface="settings") == (
        "0.15|0.10|15%|10%|2026-10-27 09:02（台北時間）|"
    )
    skipped = Cap1MigrationRecord(
        status="skipped",
        previous_value=0.15,
        new_value=None,
        failed_sections=("cost_model", "alerts"),
        basis=CAP1_MIGRATION_BASIS,
        recorded_at=MIGRATED_AT.isoformat(),
    )
    assert skipped.notice(current_max_position_weight=0.15, surface="risk_gauge") == (
        "0.15|0.10|15%|10%|2026-10-27 09:02（台北時間）|cost_model, alerts"
    )


def test_settings_and_gauge_responses_carry_the_record_and_notice(
    api_harness: ApiHarness, tmp_path: Path
) -> None:
    db = tmp_path / "migrated-settings.db"
    _seed(db, _full_document(0.15))
    store = SettingsStore(db, now=MIGRATED_AT)
    app.dependency_overrides[get_settings_store] = lambda: store

    body = api_harness.client.get("/api/settings").json()
    assert body["settings"]["risk_budget"]["max_position_weight"] == 0.10
    view = body["cap1_migration"]
    assert view["status"] == "migrated"
    assert view["previous_value"] == 0.15
    assert view["new_value"] == 0.10
    assert view["recorded_at"] == MIGRATED_AT.isoformat()
    assert view["basis"] == CAP1_MIGRATION_BASIS
    assert view["failed_sections"] == []
    assert view["notice"] == CAP1_MIGRATION_NOTICES["migrated"]
    # The record is not part of the editable document.
    assert "cap1_migration" not in body["settings"]
    assert "migration" not in json.dumps(body["settings"]["risk_budget"])

    gauge = api_harness.client.get("/api/portfolio/limits").json()
    assert gauge["cap1_migration_notice"] == CAP1_MIGRATION_NOTICES["migrated"]

    # The user moves cap 1 themselves: the gauge stops, the settings page keeps it.
    response = api_harness.client.put(
        "/api/settings", json={"risk_budget": {"max_position_weight": 0.12}}
    )
    assert response.status_code == 200
    assert response.json()["cap1_migration"]["notice"] == CAP1_MIGRATION_NOTICES["migrated"]
    assert api_harness.client.get("/api/portfolio/limits").json()["cap1_migration_notice"] is None


def test_the_record_cannot_be_written_through_put(api_harness: ApiHarness) -> None:
    response = api_harness.client.put(
        "/api/settings", json={"cap1_migration": {"status": "not_applicable"}}
    )
    assert response.status_code == 422
    response = api_harness.client.put(
        "/api/settings",
        json={"risk_budget": {"max_position_weight": 0.1, "cap1_migrated": True}},
    )
    assert response.status_code == 422


def test_a_fresh_install_serves_a_record_with_no_notice(api_harness: ApiHarness) -> None:
    body = api_harness.client.get("/api/settings").json()
    assert body["cap1_migration"]["status"] == "not_applicable"
    assert body["cap1_migration"]["notice"] is None
    assert api_harness.client.get("/api/portfolio/limits").json()["cap1_migration_notice"] is None


# --- Merge gate ------------------------------------------------------------------


@pytest.mark.parametrize("slot", sorted(CAP1_MIGRATION_NOTICES))
def test_the_s2_notice_copy_has_been_finalised(slot: str) -> None:
    """Merge gate: the S2 copy is drafted by creative-lead and reviewed by risk.

    Until that copy replaces the placeholder this test is red on purpose, so the
    batch cannot merge with a notice that says nothing.
    """
    assert CAP1_MIGRATION_NOTICES[slot] != NOTICE_PENDING_RISK_REVIEW, (
        f"S2 告知字面未定稿，不得合併（app/settings/migrations.py "
        f"CAP1_MIGRATION_NOTICES[{slot!r}] 仍為 {NOTICE_PENDING_RISK_REVIEW}）"
    )
