"""N-156 detection: which stored sections fell back to their defaults (ADR-0032).

Sources: ADR-0032 (accepted, CEO #74) Decision 1 and K-1 ~ K-5, K-12; 「風控
2026-10-29 N-156 字面定稿與表態」. What is pinned here:

* **K-1** -- ``load_with_status()`` returns a frozen ``LoadedSettings`` whose
  ``fallback_sections`` follow ``_SECTIONS`` order, and ``load()`` is exactly
  its ``.settings``; absent row, valid row, invalid JSON and schema mismatch.
* **K-2** -- only a stored-but-invalid section is a fallback; a missing row
  (a pre-FR-9 file has no ``net_worth`` row) is not.
* Judged on **every read**, never remembered: a section broken after the
  store was built shows up on the next read, and drops out once repaired.
* **K-3** -- the read path writes nothing and takes no lock (trace callback).
* **K-4** -- no module outside ``app/settings`` names the table or the judge.
* **K-5** -- each handler that reads settings reads them once.
* **K-12** -- the store docstring no longer calls the defaults "conservative".
"""

from __future__ import annotations

import ast
import dataclasses
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app.advice.limits import RiskBudget
from app.api.deps import get_settings_store
from app.main import app
from app.settings import store as store_module
from app.settings.models import AlertSettings, AppSettings, CostModelSettings, NetWorthSettings
from app.settings.store import LoadedSettings, SettingsStore
from tests.api_helpers import position_payload, recent_bars, trending_closes
from tests.conftest import ApiHarness
from tests.import_graph import APP_ROOT
from tests.settings_fallback_helpers import (
    NOT_JSON,
    SCHEMA_MISMATCH,
    SECTIONS,
    SpySettingsStore,
    break_sections,
    delete_row,
    write_raw,
)

#: A saved document that differs from the defaults in every section, so a
#: section served from its defaults cannot pass for the stored one.
STORED = AppSettings(
    risk_budget=RiskBudget(max_position_weight=0.07),
    cost_model=CostModelSettings(slippage_bps=7.5),
    alerts=AlertSettings(cooldown_minutes=15, notify_webhooks=False),
    net_worth=NetWorthSettings(
        total_net_worth_twd=2_000_000.0, updated_at="2026-10-01T00:00:00+00:00"
    ),
)

#: The default value each section falls back to.
DEFAULTS = AppSettings()


def _saved_store(tmp_path: Path) -> SettingsStore:
    store = SettingsStore(tmp_path / "settings.db")
    store.save(STORED)
    return store


# --- K-1 / K-2 -------------------------------------------------------------------


def test_load_with_status_is_frozen_and_load_is_its_settings(tmp_path: Path) -> None:
    store = _saved_store(tmp_path)
    loaded = store.load_with_status()

    assert isinstance(loaded, LoadedSettings)
    assert loaded == LoadedSettings(settings=STORED, fallback_sections=())
    assert store.load() == loaded.settings
    with pytest.raises(dataclasses.FrozenInstanceError):
        loaded.fallback_sections = ("risk_budget",)  # type: ignore[misc]


def test_a_fresh_file_has_no_rows_and_no_fallback(tmp_path: Path) -> None:
    """K-2: no row at all is the defaults, honestly -- not a fallback."""
    loaded = SettingsStore(tmp_path / "settings.db").load_with_status()
    assert loaded == LoadedSettings(settings=DEFAULTS, fallback_sections=())


def test_a_missing_net_worth_row_is_not_a_fallback(tmp_path: Path) -> None:
    """K-2: a file saved before FR-9 has no ``net_worth`` row, and that is valid."""
    store = _saved_store(tmp_path)
    delete_row(store, "net_worth")

    loaded = store.load_with_status()
    assert loaded.fallback_sections == ()
    assert loaded.settings.net_worth == DEFAULTS.net_worth
    assert loaded.settings.risk_budget == STORED.risk_budget


@pytest.mark.parametrize("payload", [NOT_JSON, SCHEMA_MISMATCH], ids=["not-json", "schema"])
@pytest.mark.parametrize("section", SECTIONS)
def test_a_stored_invalid_section_is_a_fallback_served_with_its_defaults(
    tmp_path: Path, section: str, payload: str
) -> None:
    """K-1: bad JSON and a schema mismatch both count; the others keep their values."""
    store = _saved_store(tmp_path)
    write_raw(store, section, payload)

    loaded = store.load_with_status()
    assert loaded.fallback_sections == (section,)
    for name in SECTIONS:
        expected = DEFAULTS if name == section else STORED
        assert getattr(loaded.settings, name) == getattr(expected, name), name
    assert store.load() == loaded.settings


def test_a_stored_value_beyond_a_ceiling_is_a_fallback(tmp_path: Path) -> None:
    """The likeliest real trigger: a bound tightened under a stored value (ADR-0032 背景)."""
    store = _saved_store(tmp_path)
    write_raw(store, "risk_budget", json.dumps({"max_position_weight": 0.99}))
    assert store.load_with_status().fallback_sections == ("risk_budget",)


def test_fallback_sections_follow_the_sections_order(tmp_path: Path) -> None:
    store = _saved_store(tmp_path)
    for section in reversed(SECTIONS):
        write_raw(store, section, SCHEMA_MISMATCH)
    assert store.load_with_status().fallback_sections == SECTIONS
    assert SECTIONS == tuple(store_module._SECTIONS)


def test_the_state_is_judged_on_every_read(tmp_path: Path) -> None:
    """Never remembered: broken after construction shows, repaired drops out."""
    store = _saved_store(tmp_path)
    assert store.load_with_status().fallback_sections == ()

    break_sections(store, ("alerts",))
    assert store.load_with_status().fallback_sections == ("alerts",)

    write_raw(store, "alerts", json.dumps(STORED.alerts.model_dump()))
    assert store.load_with_status().fallback_sections == ()


def test_the_fallback_state_is_never_stored(tmp_path: Path) -> None:
    """Decision 1 / D3 rejected: no table, no row, no field holds the state."""
    store = _saved_store(tmp_path)
    break_sections(store, ("risk_budget",))
    store.load_with_status()

    with sqlite3.connect(store.db_path) as conn:
        tables = {
            str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    conn.close()
    assert tables == {"app_settings", "settings_migrations"}
    assert "fallback" not in json.dumps(AppSettings.model_json_schema())


# --- K-3: the read path writes nothing ---------------------------------------------


@pytest.mark.parametrize("method", ["load", "load_with_status"])
def test_reading_takes_no_lock_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    store = _saved_store(tmp_path)
    break_sections(store, ("risk_budget", "net_worth"))

    traced: list[str] = []
    real_connect = sqlite3.connect

    def tracing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        conn.set_trace_callback(traced.append)
        return conn

    # A scoped patch: ``undo()`` would also revert every earlier patch of the test.
    with monkeypatch.context() as patched:
        patched.setattr(sqlite3, "connect", tracing_connect)
        getattr(store, method)()

    assert traced, "the trace callback saw nothing; the test would be vacuous"
    upper = [sql.upper().lstrip() for sql in traced]
    assert not any(sql.startswith("BEGIN") for sql in upper), traced
    assert not any(sql.startswith(("INSERT", "UPDATE", "DELETE")) for sql in upper), traced


# --- K-4: the table and the judge stay inside app/settings ----------------------------


def _string_constants_and_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
        elif isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add(node.name)
    return found


def test_no_module_outside_app_settings_names_the_table_or_the_judge() -> None:
    """K-4: nobody else reads raw payloads or judges a section on their own."""
    offenders = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path.is_relative_to(APP_ROOT / "settings"):
            continue
        text = path.read_text(encoding="utf-8")
        tokens = _string_constants_and_names(path)
        if "app_settings" in text or "_parse_section" in tokens:
            offenders.append(str(path.relative_to(APP_ROOT)))
    assert offenders == []


def test_the_k4_scan_has_teeth() -> None:
    assert "app_settings" in (APP_ROOT / "settings" / "store.py").read_text(encoding="utf-8")
    assert "_parse_section" in _string_constants_and_names(APP_ROOT / "settings" / "store.py")


# --- K-5: one read per handler ---------------------------------------------------------


@pytest.fixture
def spy(api_harness: ApiHarness, tmp_path: Path) -> SpySettingsStore:
    store = SpySettingsStore(tmp_path / "spy-settings.db")
    store.save(STORED)
    app.dependency_overrides[get_settings_store] = lambda: store
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    api_harness.client.post("/api/positions", json=position_payload())
    store.reads.clear()
    return store


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/settings"),
        ("GET", "/api/advice/2330"),
        ("GET", "/api/advice/9999"),
        ("GET", "/api/portfolio/limits"),
        ("GET", "/api/kelly-inputs/2330/disclosures"),
        ("POST", "/api/alerts/evaluate"),
    ],
)
def test_each_handler_reads_the_settings_once(
    api_harness: ApiHarness, spy: SpySettingsStore, method: str, path: str
) -> None:
    """K-5: values and disclosure from one read, so they cannot disagree."""
    response = api_harness.client.request(method, path)
    assert response.status_code == 200, response.text
    assert len(spy.reads) == 1, spy.reads


# --- K-12 --------------------------------------------------------------------------------


def test_the_store_no_longer_calls_the_defaults_conservative() -> None:
    doc = store_module.__doc__ or ""
    assert "conservative default" not in doc
    assert "load_with_status" in doc
