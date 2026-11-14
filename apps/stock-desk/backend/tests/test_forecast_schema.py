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
from collections.abc import Iterator
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
    HEX_A,
    HEX_B,
    TS,
    VALID_ROWS,
    file_ledger,
    insert,
    memory_ledger,
    row,
)

ULID_OTHER = "01JCZ0000000000000000000AC"


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = memory_ledger()
    yield connection
    connection.close()


# --- append-only triggers (S-1) --------------------------------------------------------


@pytest.mark.parametrize("table", TABLES)
def test_update_is_refused_on_every_table(table: str, conn: sqlite3.Connection) -> None:
    insert(conn, table, VALID_ROWS[table])
    column = next(iter(VALID_ROWS[table]))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(f'UPDATE {table} SET "{column}" = "{column}"')
    assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1


@pytest.mark.parametrize("table", TABLES)
def test_delete_is_refused_on_every_table(table: str, conn: sqlite3.Connection) -> None:
    insert(conn, table, VALID_ROWS[table])
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(f"DELETE FROM {table}")
    assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1


def test_an_upsert_update_is_refused_too(conn: sqlite3.Connection) -> None:
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


def test_recursive_triggers_are_the_second_layer(conn: sqlite3.Connection) -> None:
    # Without the no_replace trigger, the store's recursive_triggers = ON (store.py)
    # still makes the delete REPLACE performs fire the append-only DELETE trigger.
    conn.execute("DROP TRIGGER forecast_record_no_replace")
    conn.execute("PRAGMA recursive_triggers = ON")
    insert(conn, "forecast_record", VALID_ROWS["forecast_record"])
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        _replace(conn)
    assert conn.execute("SELECT label FROM forecast_record").fetchall() == [("range",)]


#: The nine key paths of ADR-0030 supplement 1: ``path -> (table, replacing row)``.
#: Each row collides with the table's valid row on the named key only, so an
#: ``INSERT OR REPLACE`` of it would delete that row and write this one instead.
REPLACE_PATHS: dict[str, tuple[str, dict[str, object]]] = {
    "forecast_run.run_id": (
        "forecast_run",
        row("forecast_run", run_id=1, code_commit="rewrite"),
    ),
    "forecast_run_end.run_id": (
        "forecast_run_end",
        row("forecast_run_end", outcome="error", records_written=0, error_class="Rewrite"),
    ),
    "forecast_input_series.series_id": (
        "forecast_input_series",
        row("forecast_input_series", series_id=1, content_sha256=HEX_A, source="rewrite"),
    ),
    "forecast_input_series.content_sha256": (
        "forecast_input_series",
        row("forecast_input_series", source="rewrite"),
    ),
    "forecast_claim_registry.rowid": (
        "forecast_claim_registry",
        row(
            "forecast_claim_registry",
            rowid=1,
            claim_id="market|h3|r2|dirdef-v1.0|forward",
            rules_version="r2",
        ),
    ),
    "forecast_claim_registry.claim_id": (
        "forecast_claim_registry",
        row("forecast_claim_registry", review_refs="work/reviews/rewrite.md"),
    ),
    "forecast_record.rowid": (
        "forecast_record",
        row(
            "forecast_record",
            rowid=1,
            forecast_id=ULID_OTHER,
            data_as_of="2026-11-16",
            label="bearish",
        ),
    ),
    "forecast_record.forecast_id": (
        "forecast_record",
        row("forecast_record", data_as_of="2026-11-16", label="bearish"),
    ),
    "forecast_record.claim_id+data_as_of": (
        "forecast_record",
        row("forecast_record", forecast_id=ULID_OTHER, label="bearish"),
    ),
}


def _insert_or_replace(conn: sqlite3.Connection, table: str, columns: dict[str, object]) -> None:
    names = ", ".join(f'"{name}"' for name in columns)
    marks = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({names}) VALUES ({marks})", tuple(columns.values())
    )


def _contents(conn: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    return conn.execute(f"SELECT rowid, * FROM {table} ORDER BY rowid").fetchall()


def test_the_replace_paths_are_the_nine_keys() -> None:
    expected = {
        f"{table}.{key if isinstance(key, str) else '+'.join(key)}"
        for table, keys in schema.REPLACE_KEYS.items()
        for key in keys
    }
    assert set(REPLACE_PATHS) == expected
    assert len(expected) == 9


@pytest.mark.parametrize("path", REPLACE_PATHS)
def test_insert_or_replace_is_refused_on_a_default_connection(
    path: str, conn: sqlite3.Connection
) -> None:
    # recursive_triggers is OFF (the SQLite default): the no_replace trigger alone refuses.
    table, replacing = REPLACE_PATHS[path]
    assert conn.execute("PRAGMA recursive_triggers").fetchone()[0] == 0
    insert(conn, table, VALID_ROWS[table])
    before = _contents(conn, table)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        _insert_or_replace(conn, table, replacing)
    assert _contents(conn, table) == before
    assert len(before) == 1


@pytest.mark.parametrize("path", REPLACE_PATHS)
def test_each_replace_path_rewrites_without_the_no_replace_trigger(
    path: str, conn: sqlite3.Connection
) -> None:
    # The fact behind SP-1, per path: without the trigger the stored row is replaced.
    table, replacing = REPLACE_PATHS[path]
    insert(conn, table, VALID_ROWS[table])
    before = _contents(conn, table)
    conn.execute(f"DROP TRIGGER {table}_no_replace")
    _insert_or_replace(conn, table, replacing)
    after = _contents(conn, table)
    assert len(after) == 1
    assert after != before


def test_before_insert_runs_before_replace_deletes_the_old_row(conn: sqlite3.Connection) -> None:
    # Supplement 1 point (a): a BEFORE INSERT trigger of an INSERT OR REPLACE still
    # sees the row REPLACE is about to delete (a TEMP probe; no_replace is dropped so
    # the statement completes).
    conn.execute("DROP TRIGGER forecast_record_no_replace")
    conn.execute("CREATE TEMP TABLE probe (old_rows)")
    conn.execute(
        "CREATE TEMP TRIGGER probe_insert BEFORE INSERT ON main.forecast_record BEGIN"
        " INSERT INTO probe VALUES"
        " ((SELECT count(*) FROM main.forecast_record WHERE forecast_id = NEW.forecast_id));"
        " END"
    )
    insert(conn, "forecast_record", VALID_ROWS["forecast_record"])
    _replace(conn)
    assert conn.execute("SELECT old_rows FROM probe ORDER BY rowid").fetchall() == [(0,), (1,)]
    assert conn.execute("SELECT label FROM forecast_record").fetchall() == [("bearish",)]


@pytest.mark.parametrize(
    "table", ["forecast_run", "forecast_input_series", "forecast_claim_registry", "forecast_record"]
)
def test_new_rowid_is_minus_one_when_no_rowid_is_given(
    table: str, conn: sqlite3.Connection
) -> None:
    # Supplement 1 point (b): SQLite documents NEW.rowid in a BEFORE INSERT trigger as
    # undefined when the INSERT names none; here it is -1, for the INTEGER PRIMARY KEY
    # tables and the TEXT primary key tables alike, and the row then gets rowid 1.
    conn.execute("CREATE TEMP TABLE probe (new_rowid)")
    conn.execute(
        f"CREATE TEMP TRIGGER probe_insert BEFORE INSERT ON main.{table} BEGIN"
        " INSERT INTO probe VALUES (NEW.rowid); END"
    )
    insert(conn, table, VALID_ROWS[table])
    assert conn.execute("SELECT new_rowid FROM probe").fetchall() == [(-1,)]
    assert conn.execute(f"SELECT rowid FROM {table}").fetchall() == [(1,)]


def test_a_row_with_rowid_minus_one_refuses_later_inserts(conn: sqlite3.Connection) -> None:
    # The fail-closed edge of (b): a row with rowid -1 exists only if an INSERT named
    # it, and then every INSERT that names no rowid matches it and is refused.
    insert(conn, "forecast_record", row("forecast_record", rowid=-1))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        insert(
            conn,
            "forecast_record",
            row("forecast_record", forecast_id=ULID_OTHER, data_as_of="2026-11-16"),
        )
    assert conn.execute("SELECT rowid FROM forecast_record").fetchall() == [(-1,)]


def test_a_row_with_new_keys_is_accepted(conn: sqlite3.Connection) -> None:
    insert(conn, "forecast_record", VALID_ROWS["forecast_record"])
    insert(
        conn,
        "forecast_record",
        row("forecast_record", forecast_id=ULID_OTHER, data_as_of="2026-11-16"),
    )
    assert conn.execute("SELECT count(*) FROM forecast_record").fetchone()[0] == 2


# --- column CHECKs --------------------------------------------------------------------

_BAD_TS = (
    "2026-11-13T14:10:00+00:00",  # no microseconds
    "2026-11-13T22:10:00.000000+08:00",  # not UTC
    "2026-11-13 14:10:00.000000+00:00",  # space separator
)


def _o(**overrides: object) -> dict[str, object]:
    return overrides


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
    *[("forecast_run", _o(started_at=bad), False) for bad in _BAD_TS],
    # forecast_run_end
    *[
        ("forecast_run_end", _o(outcome=outcome, records_written=0), True)
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
    *[("forecast_record", _o(label=label), True) for label in ("bullish", "range", "bearish")],
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
def test_column_checks(
    table: str, overrides: dict[str, object], accepted: bool, conn: sqlite3.Connection
) -> None:
    candidate = row(table, **overrides)
    if accepted:
        insert(conn, table, candidate)
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1
    else:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            insert(conn, table, candidate)


def test_claim_and_day_are_unique(conn: sqlite3.Connection) -> None:
    insert(conn, "forecast_record", VALID_ROWS["forecast_record"])
    duplicate = row("forecast_record", forecast_id=ULID_OTHER)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        insert(conn, "forecast_record", duplicate)
    # Under the no_replace trigger the UNIQUE constraint still holds on its own.
    conn.execute("DROP TRIGGER forecast_record_no_replace")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert(conn, "forecast_record", duplicate)


def test_snapshot_content_is_unique(conn: sqlite3.Connection) -> None:
    insert(conn, "forecast_input_series", VALID_ROWS["forecast_input_series"])
    duplicate = row("forecast_input_series", content_sha256=HEX_B)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        insert(conn, "forecast_input_series", duplicate)
    conn.execute("DROP TRIGGER forecast_input_series_no_replace")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert(conn, "forecast_input_series", duplicate)


def test_foreign_keys_hold_when_enabled(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        insert(conn, "forecast_record", VALID_ROWS["forecast_record"])
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        insert(conn, "forecast_run_end", VALID_ROWS["forecast_run_end"])


#: The ``WHERE`` of each no_replace trigger, written out: the keys of supplement 1 and
#: nothing else.
NO_REPLACE_WHERE = {
    "forecast_run": "run_id = NEW.run_id",
    "forecast_run_end": "run_id = NEW.run_id",
    "forecast_input_series": (
        "series_id = NEW.series_id\n        OR content_sha256 = NEW.content_sha256"
    ),
    "forecast_claim_registry": "rowid = NEW.rowid\n        OR claim_id = NEW.claim_id",
    "forecast_record": (
        "rowid = NEW.rowid\n        OR forecast_id = NEW.forecast_id\n"
        "        OR (claim_id = NEW.claim_id AND data_as_of = NEW.data_as_of)"
    ),
}


def test_every_table_has_exactly_the_three_triggers() -> None:
    for table in TABLES:
        triggers = sorted(
            name
            for kind, name in EXPECTED_OBJECTS
            if kind == "trigger" and name.rsplit("_no_", 1)[0] == table
        )
        assert triggers == [f"{table}_no_delete", f"{table}_no_replace", f"{table}_no_update"]
        for name in triggers:
            assert "RAISE(ABORT, 'append-only')" in EXPECTED_OBJECTS[("trigger", name)]
        for event in ("update", "delete"):
            assert " WHEN " not in EXPECTED_OBJECTS[("trigger", f"{table}_no_{event}")]
        assert EXPECTED_OBJECTS[("trigger", f"{table}_no_replace")] == (
            f"CREATE TRIGGER {table}_no_replace BEFORE INSERT ON {table}\n"
            f"WHEN EXISTS (\n"
            f"    SELECT 1 FROM {table}\n"
            f"    WHERE {NO_REPLACE_WHERE[table]}\n"
            f")\n"
            f"BEGIN\n"
            f"    SELECT RAISE(ABORT, 'append-only');\n"
            f"END"
        )


def test_the_database_holds_exactly_fifteen_ledger_triggers(conn: sqlite3.Connection) -> None:
    names = {
        name
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name LIKE 'forecast_%'"
        )
    }
    assert len(names) == 15
    assert names == {
        f"{table}_no_{event}" for table in TABLES for event in ("update", "delete", "replace")
    }


# --- schema_status ----------------------------------------------------------------------


def test_a_fresh_schema_is_complete(tmp_path: Path) -> None:
    path = file_ledger(tmp_path)
    connection = sqlite3.connect(path)
    try:
        status = schema_status(connection)
        require_complete_schema(connection)
    finally:
        connection.close()
    assert status.complete
    assert status.missing == status.altered == status.unexpected == ()


def test_an_empty_database_is_incomplete() -> None:
    connection = sqlite3.connect(":memory:")
    status = schema_status(connection)
    connection.close()
    assert not status.complete
    assert len(status.missing) == len(EXPECTED_OBJECTS) == 20
    assert sum(1 for kind, _ in EXPECTED_OBJECTS if kind == "trigger") == 15


@pytest.mark.parametrize("table", TABLES)
def test_a_missing_no_replace_trigger_is_incomplete(table: str, conn: sqlite3.Connection) -> None:
    conn.execute(f"DROP TRIGGER {table}_no_replace")
    status = schema_status(conn)
    assert status.missing == (f"trigger:{table}_no_replace",)
    assert not status.complete


def test_an_altered_no_replace_trigger_is_incomplete(conn: sqlite3.Connection) -> None:
    # An extra condition in WHEN (here one that lets a REPLACE through) is an alteration.
    original = EXPECTED_OBJECTS[("trigger", "forecast_record_no_replace")]
    conn.execute("DROP TRIGGER forecast_record_no_replace")
    conn.execute(original.replace("WHEN EXISTS (", "WHEN NEW.label <> 'bearish' AND EXISTS ("))
    status = schema_status(conn)
    assert status.altered == ("trigger:forecast_record_no_replace",)
    assert not status.complete


def test_a_sixteenth_trigger_is_incomplete(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TRIGGER forecast_record_no_replace_2 BEFORE INSERT ON forecast_record\n"
        "BEGIN\n    SELECT RAISE(ABORT, 'append-only');\nEND"
    )
    status = schema_status(conn)
    assert status.unexpected == ("trigger:forecast_record_no_replace_2",)
    assert not status.complete


def test_a_missing_table_is_incomplete(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE forecast_run_end")
    status = schema_status(conn)
    assert not status.complete
    assert "table:forecast_run_end" in status.missing
    with pytest.raises(SchemaIncompleteError):
        require_complete_schema(conn)


def test_a_missing_trigger_is_incomplete(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TRIGGER forecast_record_no_delete")
    status = schema_status(conn)
    assert status.missing == ("trigger:forecast_record_no_delete",)
    assert not status.complete


def test_an_altered_trigger_is_incomplete(conn: sqlite3.Connection) -> None:
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
def test_an_extra_ledger_object_is_incomplete(ddl: str, conn: sqlite3.Connection) -> None:
    conn.execute(ddl)
    status = schema_status(conn)
    assert status.unexpected != ()
    assert not status.complete


def test_other_tables_do_not_matter(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE alert_rules (x)")
    assert schema_status(conn).complete


def test_create_schema_refuses_a_database_with_ledger_objects(conn: sqlite3.Connection) -> None:
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
    conn.close()


def test_the_schema_module_has_no_migration() -> None:
    # K-12: schema_version is constant and nothing in schema.py alters a table.
    source = Path(schema.__file__).read_text(encoding="utf-8")
    assert schema.SCHEMA_VERSION == 1
    assert "ALTER TABLE" not in source.upper()
    names = {n.name for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef)}
    assert not any("migrat" in name for name in names)


def test_the_timestamp_fixture_is_store_format() -> None:
    assert TS.endswith("+00:00") and len(TS) == len("2026-11-13T14:10:00.000000+00:00")
