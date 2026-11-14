"""The ledger core schema (ADR-0030 D-2, D-9 S-1, K-5, K-8, K-12).

* every one of the five tables refuses UPDATE and DELETE with ``append-only``;
* each column CHECK has a passing and a failing example;
* ``schema_status`` is complete on a fresh schema and incomplete when a table
  or a trigger is missing, altered, or an extra ledger object exists.

All databases are in memory or under ``tmp_path``.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from app.forecast import schema
from app.forecast.schema import (
    EXPECTED_OBJECTS,
    TABLES,
    SchemaIncompleteError,
    SchemaNotEmptyError,
    create_schema,
    require_complete_schema,
    schema_status,
)
from tests.forecast_ledger_helpers import (
    CLAIM_H3,
    HEX_B,
    TS,
    VALID_ROWS,
    file_ledger,
    insert,
    memory_ledger,
    row,
)

# --- append-only triggers (S-1) --------------------------------------------------------


@pytest.mark.parametrize("table", TABLES)
def test_update_is_refused_on_every_table(table: str) -> None:
    conn = memory_ledger()
    insert(conn, table, VALID_ROWS[table])
    column = next(iter(VALID_ROWS[table]))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(f'UPDATE {table} SET "{column}" = "{column}"')
    assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1


@pytest.mark.parametrize("table", TABLES)
def test_delete_is_refused_on_every_table(table: str) -> None:
    conn = memory_ledger()
    insert(conn, table, VALID_ROWS[table])
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(f"DELETE FROM {table}")
    assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1


def test_an_upsert_update_is_refused_too() -> None:
    conn = memory_ledger()
    insert(conn, "forecast_input_series", VALID_ROWS["forecast_input_series"])
    columns = VALID_ROWS["forecast_input_series"]
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(
            f"INSERT INTO forecast_input_series ({names}) VALUES ({marks})"
            " ON CONFLICT (content_sha256) DO UPDATE SET source = 'other'",
            tuple(columns.values()),
        )


def _replace(conn: sqlite3.Connection) -> None:
    columns = row("forecast_record", label="bearish")
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT OR REPLACE INTO forecast_record ({names}) VALUES ({marks})",
        tuple(columns.values()),
    )


def test_insert_or_replace_is_refused_when_recursive_triggers_are_on() -> None:
    # The store's connections turn recursive_triggers on (store.py), so the
    # delete REPLACE performs fires the append-only DELETE trigger.
    conn = memory_ledger()
    conn.execute("PRAGMA recursive_triggers = ON")
    insert(conn, "forecast_record", VALID_ROWS["forecast_record"])
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        _replace(conn)
    assert conn.execute("SELECT label FROM forecast_record").fetchall() == [("range",)]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "stop point SP-1: with SQLite's default recursive_triggers = OFF, INSERT OR REPLACE "
        "deletes the old row without firing the BEFORE DELETE trigger; the D-2 triggers "
        "alone do not stop a rewrite from a connection outside the store"
    ),
)
def test_insert_or_replace_is_refused_on_a_default_connection() -> None:
    conn = memory_ledger()
    insert(conn, "forecast_record", VALID_ROWS["forecast_record"])
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        _replace(conn)


def test_insert_or_replace_rewrites_a_record_on_a_default_connection() -> None:
    # The fact behind SP-1, shown directly: the label of the stored row changed.
    conn = memory_ledger()
    insert(conn, "forecast_record", VALID_ROWS["forecast_record"])
    _replace(conn)
    assert conn.execute("SELECT label FROM forecast_record").fetchall() == [("bearish",)]


# --- column CHECKs --------------------------------------------------------------------

_BAD_TS = (
    "2026-11-13T14:10:00+00:00",  # no microseconds
    "2026-11-13T22:10:00.000000+08:00",  # not UTC
    "2026-11-13 14:10:00.000000+00:00",  # space separator
)

#: ``(table, overrides, accepted)``: each column CHECK with a pass and a fail.
CHECK_CASES: list[tuple[str, dict[str, object], bool]] = [
    # forecast_run
    ("forecast_run", {"trigger": "scheduled"}, True),
    ("forecast_run", {"trigger": "manual"}, False),
    ("forecast_run", {"schema_version": 1}, True),
    ("forecast_run", {"schema_version": 2}, False),
    ("forecast_run", {"code_digest": "0123456789abcdef" * 4}, True),
    ("forecast_run", {"code_digest": "A" * 64}, False),
    ("forecast_run", {"code_digest": "a" * 63}, False),
    ("forecast_run", {"code_commit": ""}, False),
    ("forecast_run", {"runtime_json": "[]"}, False),
    ("forecast_run", {"runtime_json": "{not json"}, False),
    *[("forecast_run", {"started_at": bad}, False) for bad in _BAD_TS],
    # forecast_run_end
    *[
        ("forecast_run_end", {"outcome": outcome, "records_written": 0}, True)
        for outcome in ("ok", "no_new_session", "inputs_not_ready")
    ],
    ("forecast_run_end", {"outcome": "gate_closed", "records_written": 0}, True),
    (
        "forecast_run_end",
        {"outcome": "gate_closed", "records_written": 0, "error_class": "SemanticsChanged"},
        True,
    ),
    ("forecast_run_end", {"outcome": "error", "error_class": "OperationalError"}, True),
    ("forecast_run_end", {"outcome": "late"}, False),
    ("forecast_run_end", {"outcome": "error", "error_class": None}, False),
    ("forecast_run_end", {"outcome": "ok", "error_class": "ValueError"}, False),
    ("forecast_run_end", {"outcome": "error", "error_class": "Bad Name"}, False),
    ("forecast_run_end", {"outcome": "error", "error_class": "9Lives"}, False),
    ("forecast_run_end", {"outcome": "error", "error_class": "E" * 129}, False),
    ("forecast_run_end", {"outcome": "no_new_session", "candidate_t": None}, False),
    ("forecast_run_end", {"outcome": "no_new_session", "records_written": 1}, False),
    ("forecast_run_end", {"outcome": "inputs_not_ready", "records_written": 1}, False),
    ("forecast_run_end", {"outcome": "gate_closed", "records_written": 1}, False),
    (
        "forecast_run_end",
        {"outcome": "inputs_not_ready", "candidate_t": None, "records_written": 0},
        True,
    ),
    ("forecast_run_end", {"candidate_t": "2026-02-30"}, False),
    ("forecast_run_end", {"records_written": -1}, False),
    ("forecast_run_end", {"ended_at": "yesterday"}, False),
    # forecast_input_series
    ("forecast_input_series", {"series_kind": "symbol_bars"}, False),
    ("forecast_input_series", {"raw_timestamp_available": 1}, True),
    ("forecast_input_series", {"raw_timestamp_available": 2}, False),
    ("forecast_input_series", {"staleness_minutes": None}, True),
    ("forecast_input_series", {"staleness_minutes": -1}, False),
    ("forecast_input_series", {"dropped_rows_json": None}, True),
    ("forecast_input_series", {"dropped_rows_json": "{}"}, False),
    ("forecast_input_series", {"bars_json": "[]"}, False),
    ("forecast_input_series", {"bars_json": "{}"}, False),
    ("forecast_input_series", {"bars_json": "nope"}, False),
    ("forecast_input_series", {"source": " "}, False),
    ("forecast_input_series", {"reason": ""}, False),
    ("forecast_input_series", {"content_sha256": "x" * 64}, False),
    # forecast_claim_registry
    ("forecast_claim_registry", {"kind": "replay"}, False),
    ("forecast_claim_registry", {"scope_kind": "symbol"}, False),
    ("forecast_claim_registry", {"scope_key": "2330"}, False),
    (
        "forecast_claim_registry",
        {"horizon": 5, "claim_id": "market|h5|r1|dirdef-v1.0|forward"},
        True,
    ),
    (
        "forecast_claim_registry",
        {"horizon": 4, "claim_id": "market|h4|r1|dirdef-v1.0|forward"},
        False,
    ),
    ("forecast_claim_registry", {"claim_id": "market|h5|r1|dirdef-v1.0|forward"}, False),
    ("forecast_claim_registry", {"provisional_results_seen": 1}, True),
    ("forecast_claim_registry", {"provisional_results_seen": 2}, False),
    ("forecast_claim_registry", {"replace_reason": "why"}, False),
    ("forecast_claim_registry", {"replaces_claim_id": "x|h3", "replace_reason": None}, False),
    (
        "forecast_claim_registry",
        {"replaces_claim_id": "market|h3|r0|dirdef-v1.0|forward", "replace_reason": "rules v2"},
        True,
    ),
    ("forecast_claim_registry", {"replaces_claim_id": CLAIM_H3, "replace_reason": "x"}, False),
    ("forecast_claim_registry", {"rules_bytes": b""}, False),
    ("forecast_claim_registry", {"rules_bytes": "text"}, False),
    ("forecast_claim_registry", {"prereg_doc_blob": b""}, False),
    ("forecast_claim_registry", {"frozen_commit": ""}, False),
    ("forecast_claim_registry", {"definition_json": "[]"}, False),
    ("forecast_claim_registry", {"definition_version": "v1.0"}, False),
    # forecast_record
    ("forecast_record", {"validation_status": "unverified"}, True),
    ("forecast_record", {"validation_status": "verified"}, False),
    ("forecast_record", {"validation_status": "better_than_baseline"}, False),
    *[("forecast_record", {"label": label}, True) for label in ("bullish", "range", "bearish")],
    ("forecast_record", {"label": "neutral"}, False),
    ("forecast_record", {"label": "insufficient"}, False),  # missing_json is empty
    (
        "forecast_record",
        {
            "label": "insufficient",
            "missing_json": '[{"code":"E-BARS-SHORT"}]',
            "band_def": (
                '{"EPS":null,"K_h":null,"down_pct":null,"sigma_d":null,'
                '"up_pct":null,"valid_returns":null}'
            ),
        },
        True,
    ),
    (
        "forecast_record",
        {"label": "insufficient", "missing_json": '[{"code":"E-BARS-SHORT"}]'},
        False,  # up_pct / down_pct are not null
    ),
    ("forecast_record", {"missing_json": '[{"code":"E-BARS-SHORT"}]'}, False),  # labelled
    ("forecast_record", {"missing_json": "{}"}, False),
    ("forecast_record", {"band_def": '{"K_h":0.43}'}, False),
    ("forecast_record", {"baseline_predictions_json": '{"B1":"a","B2":"b","B6":"c"}'}, False),
    ("forecast_record", {"baseline_predictions_json": "[]"}, False),
    ("forecast_record", {"evidence_json": "[]"}, False),
    ("forecast_record", {"scope_kind": "sector_main"}, False),
    ("forecast_record", {"horizon": 1}, False),
    ("forecast_record", {"late": 1}, False),  # created_at is before the cutoff
    (
        "forecast_record",
        {"late": 1, "created_at": "2026-11-13T16:00:00.000000+00:00"},
        True,
    ),
    ("forecast_record", {"late": 0, "created_at": "2026-11-13T16:00:00.000000+00:00"}, False),
    (
        "forecast_record",
        {"late": 0, "created_at": "2026-11-13T15:59:59.999999+00:00"},
        True,
    ),
    ("forecast_record", {"late": 2}, False),
    ("forecast_record", {"forecast_id": "01JCZ0000000000000000000AI"}, False),  # I
    ("forecast_record", {"forecast_id": "81JCZ0000000000000000000AB"}, False),  # > 128 bits
    ("forecast_record", {"forecast_id": "01JCZ"}, False),
    ("forecast_record", {"data_as_of": "2026-13-01"}, False),
    ("forecast_record", {"valid_until_session_estimate": "2026-11-13"}, False),
    ("forecast_record", {"content_hash": "short"}, False),
    ("forecast_record", {"base_close": ""}, False),
    ("forecast_record", {"range_basis": "sigma_band"}, True),
    ("forecast_record", {"range_basis": " "}, False),
]


@pytest.mark.parametrize(
    ("table", "overrides", "accepted"),
    CHECK_CASES,
    ids=[
        f"{table}-{'ok' if ok else 'bad'}-{'-'.join(o)}-{i}"
        for i, (table, o, ok) in enumerate(CHECK_CASES)
    ],
)
def test_column_checks(table: str, overrides: dict[str, object], accepted: bool) -> None:
    conn = memory_ledger()
    candidate = row(table, **overrides)
    if accepted:
        insert(conn, table, candidate)
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1
    else:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            insert(conn, table, candidate)


def test_claim_and_day_are_unique() -> None:
    conn = memory_ledger()
    insert(conn, "forecast_record", VALID_ROWS["forecast_record"])
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert(
            conn,
            "forecast_record",
            row("forecast_record", forecast_id="01JCZ0000000000000000000AC"),
        )


def test_snapshot_content_is_unique() -> None:
    conn = memory_ledger()
    insert(conn, "forecast_input_series", VALID_ROWS["forecast_input_series"])
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert(conn, "forecast_input_series", row("forecast_input_series", content_sha256=HEX_B))


def test_foreign_keys_hold_when_enabled() -> None:
    conn = memory_ledger()
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        insert(conn, "forecast_record", VALID_ROWS["forecast_record"])
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        insert(conn, "forecast_run_end", VALID_ROWS["forecast_run_end"])


def test_every_table_has_exactly_the_two_triggers() -> None:
    for table in TABLES:
        triggers = sorted(
            name
            for kind, name in EXPECTED_OBJECTS
            if kind == "trigger" and name.rsplit("_no_", 1)[0] == table
        )
        assert triggers == [f"{table}_no_delete", f"{table}_no_update"]
        for name in triggers:
            sql = EXPECTED_OBJECTS[("trigger", name)]
            assert "RAISE(ABORT, 'append-only')" in sql
            assert " WHEN " not in sql


# --- schema_status ----------------------------------------------------------------------


def test_a_fresh_schema_is_complete(tmp_path: Path) -> None:
    path = file_ledger(tmp_path)
    with sqlite3.connect(path) as conn:
        status = schema_status(conn)
        require_complete_schema(conn)
    assert status.complete
    assert status.missing == status.altered == status.unexpected == ()


def test_an_empty_database_is_incomplete() -> None:
    status = schema_status(sqlite3.connect(":memory:"))
    assert not status.complete
    assert len(status.missing) == len(EXPECTED_OBJECTS) == 15


def test_a_missing_table_is_incomplete() -> None:
    conn = memory_ledger()
    conn.execute("DROP TABLE forecast_run_end")
    status = schema_status(conn)
    assert not status.complete
    assert "table:forecast_run_end" in status.missing
    with pytest.raises(SchemaIncompleteError):
        require_complete_schema(conn)


def test_a_missing_trigger_is_incomplete() -> None:
    conn = memory_ledger()
    conn.execute("DROP TRIGGER forecast_record_no_delete")
    status = schema_status(conn)
    assert status.missing == ("trigger:forecast_record_no_delete",)
    assert not status.complete


def test_an_altered_trigger_is_incomplete() -> None:
    conn = memory_ledger()
    conn.execute("DROP TRIGGER forecast_record_no_update")
    conn.execute(
        "CREATE TRIGGER forecast_record_no_update BEFORE UPDATE ON forecast_record WHEN 0\n"
        "BEGIN\n    SELECT RAISE(ABORT, 'append-only');\nEND"
    )
    status = schema_status(conn)
    assert status.altered == ("trigger:forecast_record_no_update",)
    assert not status.complete


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE TABLE forecast_correction (x)",
        "CREATE TABLE plan_record (x)",
        "CREATE VIEW forecast_view AS SELECT 1",
        "CREATE INDEX forecast_record_label ON forecast_record (label)",
        "CREATE TRIGGER sneaky AFTER INSERT ON forecast_record BEGIN SELECT 1; END",
    ],
)
def test_an_extra_ledger_object_is_incomplete(ddl: str) -> None:
    conn = memory_ledger()
    conn.execute(ddl)
    status = schema_status(conn)
    assert status.unexpected != ()
    assert not status.complete


def test_other_tables_do_not_matter() -> None:
    conn = memory_ledger()
    conn.execute("CREATE TABLE alert_rules (x)")
    assert schema_status(conn).complete


def test_create_schema_refuses_a_database_with_ledger_objects() -> None:
    conn = memory_ledger()
    with pytest.raises(SchemaNotEmptyError):
        create_schema(conn)
    conn.execute("DROP TABLE forecast_record")
    with pytest.raises(SchemaNotEmptyError):
        create_schema(conn)
    assert "table:forecast_record" in schema_status(conn).missing


def test_create_schema_rolls_back_on_failure() -> None:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute("CREATE TABLE plan_outcome (x)")
    with pytest.raises(SchemaNotEmptyError):
        create_schema(conn)
    assert not conn.in_transaction
    assert "table:forecast_run" in schema_status(conn).missing


def test_the_schema_module_has_no_migration() -> None:
    # K-12: schema_version is constant and nothing in schema.py alters a table.
    source = Path(schema.__file__).read_text(encoding="utf-8")
    assert schema.SCHEMA_VERSION == 1
    assert "ALTER TABLE" not in source.upper()
    names = {n.name for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef)}
    assert not any("migrat" in name for name in names)


def test_the_timestamp_fixture_is_store_format() -> None:
    assert TS.endswith("+00:00") and len(TS) == len("2026-11-13T14:10:00.000000+00:00")
