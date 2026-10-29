"""N-156 write-back protection: W-1 + W-2 (ADR-0032 Decision 4, K-10, DL-6).

* **W-1** -- a ``PUT`` that leaves a fallback section out does not write it:
  its stored payload and ``updated_at`` stay byte-identical, the response still
  lists it, and ``partial_save_notice`` names it.
* **W-2** -- a ``PUT`` that carries a fallback section without naming it in
  ``overwrite_fallback_sections`` is a 409 whose ``detail`` is the approved
  sentence, and **no section at all** is written -- not even the valid ones it
  carried alongside -- so that sentence is true. Named, it is written and stops
  being a fallback.
* The decision and the write share one ``BEGIN IMMEDIATE`` with the rows read
  *inside* it (N-154), and the handler itself reads nothing (K-5).
* ``note_cap1_write`` runs only when ``risk_budget`` is written (K-10).
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.advice.limits import RiskBudget
from app.api.deps import get_settings_store
from app.main import app
from app.settings import migrations as migrations_module
from app.settings import store as store_module
from app.settings.models import AlertSettings, AppSettings, CostModelSettings
from app.settings.store import (
    FallbackOverwriteRequired,
    LoadedSettings,
    SaveResult,
    SettingsStore,
)
from tests.api_helpers import position_payload, recent_bars, trending_closes
from tests.conftest import ApiHarness
from tests.settings_fallback_helpers import (
    SCHEMA_MISMATCH,
    SECTIONS,
    SpySettingsStore,
    break_sections,
    raw_rows,
    write_raw,
)
from tests.test_settings_fallback_wording import DETAIL_409, PARTIAL_SAVE

STORED = AppSettings(
    risk_budget=RiskBudget(max_position_weight=0.07),
    cost_model=CostModelSettings(slippage_bps=7.5),
    alerts=AlertSettings(cooldown_minutes=15),
)

#: A valid body for each section, different from both STORED and the defaults.
BODIES: dict[str, dict[str, Any]] = {
    "risk_budget": {"max_position_weight": 0.08},
    "cost_model": {"slippage_bps": 3.0},
    "alerts": {"cooldown_minutes": 30},
    "net_worth": {"total_net_worth_twd": 5_000_000.0},
}

NAMES = {
    "risk_budget": "風險預算",
    "cost_model": "費率",
    "alerts": "警示排程",
    "net_worth": "帳戶總淨值",
}


def _seeded(harness: ApiHarness, broken: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    harness.settings.save(STORED)
    break_sections(harness.settings, broken)
    return raw_rows(harness.settings)


def _migration_rows(store: SettingsStore) -> list[tuple[Any, ...]]:
    with sqlite3.connect(store.db_path) as conn:
        rows = conn.execute("SELECT * FROM settings_migrations").fetchall()
    conn.close()
    return rows


# --- W-1: an omitted fallback section keeps its payload ------------------------------------


#: (fallback section, the section the PUT carries instead), every pair.
OMITTED = [
    (broken, carried)
    for broken in SECTIONS
    for carried in ("risk_budget", "cost_model", "alerts")
    if carried != broken
]


@pytest.mark.parametrize(("broken", "carried"), OMITTED)
def test_an_omitted_fallback_section_is_not_written(
    api_harness: ApiHarness, broken: str, carried: str
) -> None:
    before = _seeded(api_harness, (broken,))

    response = api_harness.client.put("/api/settings", json={carried: BODIES[carried]})

    assert response.status_code == 200, response.text
    after = raw_rows(api_harness.settings)
    assert after[broken] == before[broken]  # payload and updated_at, byte for byte
    assert after[carried] != before[carried]
    body = response.json()
    assert body["settings_fallback"]["sections"] == [broken]
    assert body["partial_save_notice"] == PARTIAL_SAVE.format(section_names=NAMES[broken])
    assert api_harness.settings.load_with_status().fallback_sections == (broken,)


def test_saving_the_fee_rates_no_longer_freezes_the_budgets_defaults(
    api_harness: ApiHarness,
) -> None:
    """The bug in ADR-0032 背景: one unrelated save wrote 10% over the real budget."""
    api_harness.settings.save(STORED)
    real = '{"max_position_weight": 0.05, "unknown_field_from_a_newer_build": 1}'
    write_raw(api_harness.settings, "risk_budget", real)

    for _ in range(3):
        response = api_harness.client.put(
            "/api/settings", json={"cost_model": {"slippage_bps": 2.0}}
        )
        assert response.status_code == 200

    assert raw_rows(api_harness.settings)["risk_budget"][0] == real


def test_a_put_that_leaves_nothing_behind_has_no_partial_notice(api_harness: ApiHarness) -> None:
    _seeded(api_harness, ())
    body = api_harness.client.put("/api/settings", json={"alerts": BODIES["alerts"]}).json()
    assert body["settings_fallback"] is None
    assert body["partial_save_notice"] is None


def test_a_get_never_carries_the_partial_notice(api_harness: ApiHarness) -> None:
    _seeded(api_harness, ("risk_budget",))
    assert api_harness.client.get("/api/settings").json()["partial_save_notice"] is None


def test_a_net_worth_put_leaves_a_fallback_budget_alone(api_harness: ApiHarness) -> None:
    before = _seeded(api_harness, ("risk_budget",))
    response = api_harness.client.put("/api/settings", json={"net_worth": BODIES["net_worth"]})
    assert response.status_code == 200, response.text
    assert raw_rows(api_harness.settings)["risk_budget"] == before["risk_budget"]
    assert response.json()["partial_save_notice"] == PARTIAL_SAVE.format(section_names="風險預算")


# --- W-2: a carried fallback section needs a confirmed overwrite ---------------------------


@pytest.mark.parametrize("broken", SECTIONS)
def test_a_carried_fallback_section_without_confirmation_is_409_and_writes_nothing(
    api_harness: ApiHarness, broken: str
) -> None:
    """DL-6: not one section written -- the valid ones carried alongside included."""
    before = _seeded(api_harness, (broken,))
    record_before = _migration_rows(api_harness.settings)
    body = {name: BODIES[name] for name in SECTIONS}

    response = api_harness.client.put("/api/settings", json=body)

    assert response.status_code == 409
    assert response.json()["detail"] == DETAIL_409.format(section_names=NAMES[broken])
    assert raw_rows(api_harness.settings) == before
    assert _migration_rows(api_harness.settings) == record_before


def test_the_409_names_only_the_unconfirmed_sections_in_order(api_harness: ApiHarness) -> None:
    before = _seeded(api_harness, ("risk_budget", "alerts", "net_worth"))
    response = api_harness.client.put(
        "/api/settings",
        json={
            "alerts": BODIES["alerts"],
            "risk_budget": BODIES["risk_budget"],
            "overwrite_fallback_sections": ["risk_budget"],
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "沒有寫入任何設定：警示排程原本存的內容沒有通過驗證，要寫入這些區段必須先確認覆寫。"
    )
    # Confirming one section does not let it through on its own either.
    assert raw_rows(api_harness.settings) == before


@pytest.mark.parametrize("broken", ["risk_budget", "cost_model", "alerts"])
def test_a_confirmed_overwrite_is_written_and_ends_the_fallback(
    api_harness: ApiHarness, broken: str
) -> None:
    _seeded(api_harness, (broken,))

    response = api_harness.client.put(
        "/api/settings",
        json={broken: BODIES[broken], "overwrite_fallback_sections": [broken]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["settings_fallback"] is None
    assert body["partial_save_notice"] is None
    for field, value in BODIES[broken].items():
        assert body["settings"][broken][field] == value
    assert api_harness.settings.load_with_status().fallback_sections == ()


def test_a_confirmed_net_worth_overwrite_is_written_and_fresh(api_harness: ApiHarness) -> None:
    _seeded(api_harness, ("net_worth",))
    refused = api_harness.client.put("/api/settings", json={"net_worth": BODIES["net_worth"]})
    assert refused.status_code == 409
    assert refused.json()["detail"] == DETAIL_409.format(section_names="帳戶總淨值")

    response = api_harness.client.put(
        "/api/settings",
        json={"net_worth": BODIES["net_worth"], "overwrite_fallback_sections": ["net_worth"]},
    )
    assert response.status_code == 200, response.text
    block = response.json()["net_worth"]
    assert block["freshness"] == "fresh"
    assert block["total_net_worth_twd"] == 5_000_000.0


def test_confirming_a_section_that_is_not_a_fallback_changes_nothing(
    api_harness: ApiHarness,
) -> None:
    _seeded(api_harness, ())
    response = api_harness.client.put(
        "/api/settings",
        json={"alerts": BODIES["alerts"], "overwrite_fallback_sections": ["risk_budget"]},
    )
    assert response.status_code == 200
    assert response.json()["settings"]["risk_budget"]["max_position_weight"] == 0.07


def test_an_unknown_section_cannot_be_confirmed(api_harness: ApiHarness) -> None:
    response = api_harness.client.put(
        "/api/settings", json={"overwrite_fallback_sections": ["kelly"]}
    )
    assert response.status_code == 422


def test_the_confirmation_is_not_stored(api_harness: ApiHarness) -> None:
    _seeded(api_harness, ("alerts",))
    api_harness.client.put(
        "/api/settings",
        json={"alerts": BODIES["alerts"], "overwrite_fallback_sections": ["alerts"]},
    )
    body = api_harness.client.get("/api/settings").json()
    assert "overwrite_fallback_sections" not in body["settings"]
    assert all("overwrite" not in payload for payload, _ in raw_rows(api_harness.settings).values())


# --- the store itself -------------------------------------------------------------------


def test_a_full_save_over_a_fallback_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.db")
    store.save(STORED)
    write_raw(store, "cost_model", SCHEMA_MISMATCH)
    before = raw_rows(store)

    with pytest.raises(FallbackOverwriteRequired) as refused:
        store.save(AppSettings())

    assert refused.value.sections == ("cost_model",)
    assert raw_rows(store) == before
    assert store.save(AppSettings(), overwrite_fallback_sections=("cost_model",)) == AppSettings()


def test_write_reports_what_it_found_and_left(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.db")
    store.save(STORED)
    break_sections(store, ("risk_budget", "net_worth"))

    result = store.write({"alerts": AlertSettings(cooldown_minutes=45)})

    assert isinstance(result, SaveResult)
    assert result.previous.fallback_sections == ("risk_budget", "net_worth")
    assert result.loaded.fallback_sections == ("risk_budget", "net_worth")
    assert result.written_sections == ("cost_model", "alerts")
    # ``loaded`` is exactly what a fresh read now answers.
    assert result.loaded == store.load_with_status()
    assert result.loaded.settings.alerts.cooldown_minutes == 45


def test_write_refuses_an_unknown_or_mistyped_section(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.db")
    with pytest.raises(ValueError):
        store.write({"kelly": AlertSettings()})
    with pytest.raises(TypeError):
        store.write({"alerts": CostModelSettings()})


def _traced_write(
    store: SettingsStore, monkeypatch: pytest.MonkeyPatch, **kwargs: Any
) -> tuple[list[str], BaseException | None]:
    traced: list[str] = []
    real_connect = sqlite3.connect

    def tracing_connect(*args: Any, **kw: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kw)
        conn.set_trace_callback(traced.append)
        return conn

    error: BaseException | None = None
    # A scoped patch: ``undo()`` would also revert every earlier patch of the test.
    with monkeypatch.context() as patched:
        patched.setattr(sqlite3, "connect", tracing_connect)
        try:
            store.write(**kwargs)
        except FallbackOverwriteRequired as refused:
            error = refused
    return [sql.strip().upper() for sql in traced], error


def test_the_decision_is_made_on_rows_read_inside_begin_immediate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K-10 / N-154: explicit ``BEGIN IMMEDIATE``, the read after it, then the write."""
    store = SettingsStore(tmp_path / "settings.db")
    store.save(STORED)
    break_sections(store, ("risk_budget",))

    statements, error = _traced_write(
        store, monkeypatch, sections={"cost_model": CostModelSettings()}
    )

    assert error is None
    begin = statements.index("BEGIN IMMEDIATE")
    reads = [i for i, sql in enumerate(statements) if sql.startswith("SELECT SECTION, PAYLOAD")]
    writes = [i for i, sql in enumerate(statements) if sql.startswith("INSERT INTO APP_SETTINGS")]
    assert reads and all(i > begin for i in reads)
    assert writes and min(writes) > max(reads)
    assert statements[-1] == "COMMIT"
    assert not any(sql.startswith("BEGIN") for sql in statements[:begin])


def test_a_refused_write_rolls_back_inside_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SettingsStore(tmp_path / "settings.db")
    store.save(STORED)
    break_sections(store, ("risk_budget",))

    statements, error = _traced_write(
        store, monkeypatch, sections={"risk_budget": RiskBudget(), "alerts": AlertSettings()}
    )

    assert isinstance(error, FallbackOverwriteRequired)
    assert "BEGIN IMMEDIATE" in statements
    assert statements[-1] == "ROLLBACK"
    assert not any(sql.startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements)


def test_a_section_broken_after_the_page_was_read_is_judged_at_write_time(
    api_harness: ApiHarness,
) -> None:
    """Judged under the lock, not from an earlier read: a later break is caught."""
    _seeded(api_harness, ())
    assert api_harness.client.get("/api/settings").json()["settings_fallback"] is None
    break_sections(api_harness.settings, ("alerts",))
    before = raw_rows(api_harness.settings)

    response = api_harness.client.put("/api/settings", json={"alerts": BODIES["alerts"]})

    assert response.status_code == 409
    assert raw_rows(api_harness.settings) == before


# --- NB-6: a second writer waits for the first, and never half-writes -----------------------

#: How long the holder keeps the write lock while the writer is made to wait.
_HOLD_S = 0.4


class _Writer(threading.Thread):
    """Runs one ``store.write`` and keeps whatever it returned or raised."""

    def __init__(self, store: SettingsStore, sections: dict[str, Any]) -> None:
        super().__init__(daemon=True)
        self._store = store
        self._sections = sections
        self.result: SaveResult | None = None
        self.error: BaseException | None = None
        self.elapsed = 0.0

    def run(self) -> None:
        began = time.monotonic()
        try:
            self.result = self._store.write(self._sections)
        except BaseException as error:  # noqa: BLE001 - asserted by the test
            self.error = error
        self.elapsed = time.monotonic() - began


def _holder(store: SettingsStore) -> sqlite3.Connection:
    """A second connection holding ``BEGIN IMMEDIATE`` on the same file."""
    conn = sqlite3.connect(store.db_path, isolation_level=None)
    conn.execute("BEGIN IMMEDIATE")
    return conn


def test_a_second_writer_waits_and_judges_what_the_first_committed(tmp_path: Path) -> None:
    """The holder breaks risk_budget and commits; the waiting write must see that.

    It waits at ``BEGIN IMMEDIATE`` rather than deciding on what it could read
    before, then re-reads under the lock: the risk budget it carries is now a
    fallback it was not told to overwrite, so it refuses and writes nothing.
    """
    store = SettingsStore(tmp_path / "settings.db")
    store.save(STORED)
    holder = _holder(store)
    try:
        holder.execute(
            "UPDATE app_settings SET payload = ? WHERE section = 'risk_budget'",
            (SCHEMA_MISMATCH,),
        )
        writer = _Writer(store, {"risk_budget": RiskBudget(max_position_weight=0.08)})
        writer.start()
        time.sleep(_HOLD_S)
        assert writer.is_alive(), "the second writer did not wait for the lock"
        holder.execute("COMMIT")
        committed = raw_rows(store)
    finally:
        if holder.in_transaction:
            holder.execute("ROLLBACK")
        holder.close()
    writer.join(timeout=10)

    assert not writer.is_alive()
    assert writer.elapsed >= _HOLD_S
    assert isinstance(writer.error, FallbackOverwriteRequired)
    assert writer.error.sections == ("risk_budget",)
    assert raw_rows(store) == committed


def test_a_second_writer_proceeds_once_the_first_rolls_back(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.db")
    store.save(STORED)
    holder = _holder(store)
    try:
        holder.execute(
            "UPDATE app_settings SET payload = ? WHERE section = 'risk_budget'",
            (SCHEMA_MISMATCH,),
        )
        writer = _Writer(store, {"alerts": AlertSettings(cooldown_minutes=45)})
        writer.start()
        time.sleep(_HOLD_S)
        assert writer.is_alive(), "the second writer did not wait for the lock"
        holder.execute("ROLLBACK")
    finally:
        holder.close()
    writer.join(timeout=10)

    assert writer.error is None and writer.result is not None
    loaded = store.load_with_status()
    assert loaded.fallback_sections == ()  # the holder's change never landed
    assert loaded.settings.alerts.cooldown_minutes == 45
    assert loaded.settings.risk_budget == STORED.risk_budget


def test_a_writer_that_times_out_leaves_no_partial_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Past the busy timeout the write fails as "locked" -- and nothing of it is stored."""
    store = SettingsStore(tmp_path / "settings.db")
    store.save(STORED)
    before = raw_rows(store)
    migration_before = _migration_rows(store)
    holder = _holder(store)
    try:
        with monkeypatch.context() as patched:
            patched.setattr(store_module, "BUSY_TIMEOUT_MS", 150)
            began = time.monotonic()
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                store.write(
                    {
                        "risk_budget": RiskBudget(max_position_weight=0.08),
                        "alerts": AlertSettings(cooldown_minutes=45),
                    }
                )
            assert time.monotonic() - began >= 0.1
    finally:
        holder.execute("ROLLBACK")
        holder.close()

    assert raw_rows(store) == before
    assert _migration_rows(store) == migration_before
    # Usable again at once: the failed write left no transaction open.
    store.write({"alerts": AlertSettings(cooldown_minutes=45)})
    assert store.load().alerts.cooldown_minutes == 45


# --- K-10: note_cap1_write only when risk_budget is written ---------------------------------


def _migrated(tmp_path: Path) -> SettingsStore:
    """A file an earlier build left with cap 1 at 0.15, opened (and migrated) once."""
    db = tmp_path / "migrated.db"
    document = AppSettings(risk_budget=RiskBudget(max_position_weight=0.15))
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE app_settings ("
            "section TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO app_settings (section, payload, updated_at) VALUES (?, ?, ?)",
            [
                (name, getattr(document, name).model_dump_json(), "2026-01-01T00:00:00+00:00")
                for name in SECTIONS
            ],
        )
    conn.close()
    store = SettingsStore(db, now=datetime(2026, 10, 27, tzinfo=UTC))
    record = store.cap1_migration()
    assert record is not None and record.status == "migrated"
    return store


def test_a_kept_fallback_budget_does_not_touch_the_migration_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _migrated(tmp_path)
    write_raw(store, "risk_budget", SCHEMA_MISMATCH)
    calls: list[float] = []
    real = migrations_module.note_cap1_write

    def spy(conn: sqlite3.Connection, value: float) -> None:
        calls.append(value)
        real(conn, value)

    monkeypatch.setattr(store_module, "note_cap1_write", spy)
    store.write({"cost_model": CostModelSettings(slippage_bps=2.0)})

    assert calls == []
    record = store.cap1_migration()
    assert record is not None and record.changed_by_user is False

    # Written, it is noted as before.
    store.write(
        {"risk_budget": RiskBudget(max_position_weight=0.12)},
        overwrite_fallback_sections=("risk_budget",),
    )
    assert calls == [0.12]
    record = store.cap1_migration()
    assert record is not None and record.changed_by_user is True


# --- K-5 for PUT: the handler reads nothing itself ------------------------------------------


def test_a_put_makes_no_read_of_its_own(api_harness: ApiHarness, tmp_path: Path) -> None:
    store = SpySettingsStore(tmp_path / "spy.db")
    store.save(STORED)
    writes: list[tuple[str, ...]] = []
    real_write = store.write

    def counting_write(*args: Any, **kwargs: Any) -> SaveResult:
        result = real_write(*args, **kwargs)
        writes.append(result.written_sections)
        return result

    store.write = counting_write  # type: ignore[method-assign]
    app.dependency_overrides[get_settings_store] = lambda: store
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    api_harness.client.post("/api/positions", json=position_payload())
    store.reads.clear()

    for body in ({"alerts": BODIES["alerts"]}, {"net_worth": {"total_net_worth_twd": 9e6}}):
        response = api_harness.client.put("/api/settings", json=body)
        assert response.status_code == 200, response.text
    assert store.reads == []
    assert len(writes) == 2


def test_loaded_settings_is_what_the_response_states(api_harness: ApiHarness) -> None:
    """The response is built from the write's own result, not a second read."""
    _seeded(api_harness, ("risk_budget",))
    body = api_harness.client.put("/api/settings", json={"alerts": BODIES["alerts"]}).json()
    expected = api_harness.settings.load_with_status()
    assert isinstance(expected, LoadedSettings)
    assert body["settings"] == expected.settings.model_dump(mode="json")
    assert body["settings_fallback"]["sections"] == list(expected.fallback_sections)
