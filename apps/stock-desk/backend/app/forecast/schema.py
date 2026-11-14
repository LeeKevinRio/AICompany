"""DDL of the forecast ledger core and its completeness check (ADR-0030 D-1 point 3, D-2, D-9 S-1).

The five tables of D-2, every one with a ``BEFORE UPDATE`` and a
``BEFORE DELETE`` trigger that raises ``RAISE(ABORT, 'append-only')`` -- no
exception, no ``WHEN`` clause (D-2 point 6, S-1) -- and a ``BEFORE INSERT``
``{table}_no_replace`` trigger (ADR-0030 supplement 1, SP-1) that raises the
same message when a row with any of the table's keys already exists
(:data:`REPLACE_KEYS`; its ``WHEN`` compares those keys and nothing else).
SQLite skips DELETE triggers on the rows ``INSERT OR REPLACE`` removes unless
``recursive_triggers`` is on, and a BEFORE INSERT trigger runs before REPLACE
resolves the conflict, so this one refuses a rewrite on any connection; the
store's ``recursive_triggers = ON`` stays as the second layer. The two tables
with a TEXT primary key also keep a hidden ``rowid``, which is a key of its
own: ``INSERT OR REPLACE ... (rowid, ...)`` naming an existing rowid deletes
that row too. When an INSERT names no rowid, ``NEW.rowid`` is -1 in a BEFORE
INSERT trigger (SQLite documents it as undefined; the tests pin the value),
so an insert is refused -- fail-closed -- only if a row with rowid -1 exists.
Column CHECKs pin each
closed value list of D-2 (``trigger``, ``outcome``, ``series_kind``, ``label``,
``late``, ``validation_status``, ``kind``, ``provisional_results_seen``), the
core scope of D-1 point 1 (``market`` / ``TAIEX`` / horizon 3 or 5), the text
forms the store writes (UTC timestamps with microseconds, ISO dates, sha256
hex, ULID ids, JSON) and the row invariants that need no other table:

* ``forecast_record``: ``label = 'insufficient'`` exactly when ``missing_json``
  is a non-empty array, and then ``up_pct`` / ``down_pct`` are null (D-3
  point 6); ``late = 1`` exactly when ``created_at >= late_cutoff_at`` (D-3
  point 3); the six ``band_def`` keys and the four baselines B1, B2, B6, B8
  are present (D-2 point 4, D-4 point 1, S-8);
* ``forecast_run_end``: ``no_new_session`` carries ``candidate_t``; the three
  outcomes that write nothing record 0 rows; ``error`` carries an
  ``error_class`` in the ``exception_class_name`` format, and ``ok``,
  ``no_new_session`` and ``inputs_not_ready`` carry none (D-2 point 2);
* ``forecast_claim_registry``: ``claim_id`` is the R-113 key of its own
  columns; ``replace_reason`` is set exactly when ``replaces_claim_id`` is
  (D-1 point 2).

Checks that need another table or Python (the snapshot hash, finality of the
bars, the dirdef band judgement, ``MissingItem``) are the store's write
validation (D-2 point 7).

There is no migration (K-12): ``SCHEMA_VERSION`` is 1, :func:`create_schema`
only creates on a database holding no ledger object at all, and
:func:`schema_status` compares ``sqlite_master`` with the DDL text here, so a
missing table or trigger, an altered one, or any extra ``forecast_`` /
``plan_`` object (K-5) makes the schema incomplete and the store refuses to
write. Nothing in this module runs on import, and nothing calls
:func:`create_schema` outside the tests until the wiring PR (D-6 CG-3).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Final

#: ``forecast_run.schema_version`` (K-12: constant 1).
SCHEMA_VERSION: Final = 1

#: The five ledger tables of D-2, in creation order.
TABLES: Final = (
    "forecast_run",
    "forecast_run_end",
    "forecast_input_series",
    "forecast_claim_registry",
    "forecast_record",
)

#: Name prefixes of the ledger tables; K-5 allows exactly :data:`TABLES` under them.
LEDGER_PREFIXES: Final = ("forecast_", "plan_")

#: The message every append-only trigger raises.
APPEND_ONLY_MESSAGE: Final = "append-only"


def _ts(column: str) -> str:
    # UTC ISO 8601 with microseconds, as ``store.py`` writes it.
    return (
        f"{column} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:"
        f"[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'"
    )


def _date(column: str) -> str:
    # SQLite's date() normalises an impossible date (02-30), so it must round-trip.
    return f"(typeof({column}) = 'text' AND date({column}) IS {column})"


def _hex64(column: str) -> str:
    return f"(length({column}) = 64 AND {column} NOT GLOB '*[^0-9a-f]*')"


def _text(column: str) -> str:
    return f"(typeof({column}) = 'text' AND length(trim({column})) > 0)"


def _json(column: str, kind: str) -> str:
    return f"(json_valid({column}) AND json_type({column}) = '{kind}')"


def _has_keys(column: str, keys: tuple[str, ...]) -> str:
    present = " AND ".join(f"json_type({column}, '$.{key}') IS NOT NULL" for key in keys)
    return f"CASE WHEN {_json(column, 'object')} THEN ({present}) ELSE 0 END"


#: ``band_def`` keys (D-2 point 4); values may be JSON null.
BAND_DEF_KEYS: Final = ("K_h", "EPS", "sigma_d", "valid_returns", "up_pct", "down_pct")
#: The four baselines published with every record (D-4 point 1).
BASELINE_KEYS: Final = ("B1", "B2", "B6", "B8")

_EXCEPTION_CLASS = (
    "(length(error_class) BETWEEN 1 AND 128"
    " AND error_class NOT GLOB '*[^A-Za-z0-9_]*' AND error_class NOT GLOB '[0-9]*')"
)
_ULID = (
    "(length(forecast_id) = 26 AND forecast_id GLOB '[0-7]*'"
    " AND forecast_id NOT GLOB '*[^0123456789ABCDEFGHJKMNPQRSTVWXYZ]*')"
)

_RUN = f"""CREATE TABLE forecast_run (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL CHECK ({_ts("started_at")}),
    "trigger" TEXT NOT NULL CHECK ("trigger" = 'scheduled'),
    code_commit TEXT NOT NULL CHECK ({_text("code_commit")}),
    code_digest TEXT NOT NULL CHECK ({_hex64("code_digest")}),
    runtime_json TEXT NOT NULL CHECK ({_json("runtime_json", "object")}),
    schema_version INTEGER NOT NULL CHECK (schema_version = {SCHEMA_VERSION})
)"""

_RUN_END = f"""CREATE TABLE forecast_run_end (
    run_id INTEGER PRIMARY KEY REFERENCES forecast_run (run_id),
    outcome TEXT NOT NULL CHECK (
        outcome IN ('ok', 'no_new_session', 'inputs_not_ready', 'gate_closed', 'error')
    ),
    candidate_t TEXT CHECK (candidate_t IS NULL OR {_date("candidate_t")}),
    records_written INTEGER NOT NULL CHECK (
        typeof(records_written) = 'integer' AND records_written >= 0
    ),
    error_class TEXT CHECK (error_class IS NULL OR {_EXCEPTION_CLASS}),
    ended_at TEXT NOT NULL CHECK ({_ts("ended_at")}),
    CHECK (outcome <> 'no_new_session' OR candidate_t IS NOT NULL),
    CHECK (
        outcome NOT IN ('no_new_session', 'inputs_not_ready', 'gate_closed')
        OR records_written = 0
    ),
    CHECK (outcome <> 'error' OR error_class IS NOT NULL),
    CHECK (outcome NOT IN ('ok', 'no_new_session', 'inputs_not_ready') OR error_class IS NULL)
)"""

_INPUT_SERIES = f"""CREATE TABLE forecast_input_series (
    series_id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_sha256 TEXT NOT NULL UNIQUE CHECK ({_hex64("content_sha256")}),
    series_kind TEXT NOT NULL CHECK (series_kind = 'index_bars'),
    source TEXT NOT NULL CHECK ({_text("source")}),
    source_status TEXT NOT NULL CHECK ({_text("source_status")}),
    staleness_minutes INTEGER CHECK (
        staleness_minutes IS NULL
        OR (typeof(staleness_minutes) = 'integer' AND staleness_minutes >= 0)
    ),
    reason TEXT CHECK (reason IS NULL OR {_text("reason")}),
    dropped_rows_json TEXT CHECK (
        dropped_rows_json IS NULL OR {_json("dropped_rows_json", "array")}
    ),
    raw_timestamp_available INTEGER NOT NULL CHECK (raw_timestamp_available IN (0, 1)),
    bars_json TEXT NOT NULL CHECK (
        CASE WHEN {_json("bars_json", "array")} THEN json_array_length(bars_json) > 0 ELSE 0 END
    ),
    captured_at TEXT NOT NULL CHECK ({_ts("captured_at")})
)"""

_CLAIM_REGISTRY = f"""CREATE TABLE forecast_claim_registry (
    claim_id TEXT PRIMARY KEY NOT NULL,
    scope_kind TEXT NOT NULL CHECK (scope_kind = 'market'),
    scope_key TEXT NOT NULL CHECK (scope_key = 'TAIEX'),
    horizon INTEGER NOT NULL CHECK (typeof(horizon) = 'integer' AND horizon IN (3, 5)),
    kind TEXT NOT NULL CHECK (kind = 'forward'),
    rules_version TEXT NOT NULL CHECK ({_text("rules_version")}),
    rules_sha256 TEXT NOT NULL CHECK ({_hex64("rules_sha256")}),
    rules_logic_sha256 TEXT NOT NULL CHECK ({_hex64("rules_logic_sha256")}),
    rules_bytes BLOB NOT NULL CHECK (typeof(rules_bytes) = 'blob' AND length(rules_bytes) > 0),
    definition_version TEXT NOT NULL CHECK (definition_version GLOB 'dirdef-v[0-9]*.[0-9]*'),
    definition_sha256 TEXT NOT NULL CHECK ({_hex64("definition_sha256")}),
    definition_logic_sha256 TEXT NOT NULL CHECK ({_hex64("definition_logic_sha256")}),
    definition_json TEXT NOT NULL CHECK ({_json("definition_json", "object")}),
    frozen_commit TEXT NOT NULL CHECK ({_text("frozen_commit")}),
    prereg_doc_path TEXT NOT NULL CHECK ({_text("prereg_doc_path")}),
    prereg_doc_blob BLOB NOT NULL CHECK (
        typeof(prereg_doc_blob) = 'blob' AND length(prereg_doc_blob) > 0
    ),
    review_refs TEXT NOT NULL CHECK ({_text("review_refs")}),
    replaces_claim_id TEXT REFERENCES forecast_claim_registry (claim_id),
    replace_reason TEXT CHECK (replace_reason IS NULL OR {_text("replace_reason")}),
    provisional_results_seen INTEGER NOT NULL CHECK (provisional_results_seen IN (0, 1)),
    registered_at TEXT NOT NULL CHECK ({_ts("registered_at")}),
    CHECK (
        claim_id = scope_kind || '|h' || horizon || '|' || rules_version || '|'
            || definition_version || '|' || kind
    ),
    CHECK ((replaces_claim_id IS NULL) = (replace_reason IS NULL)),
    CHECK (replaces_claim_id IS NULL OR replaces_claim_id <> claim_id)
)"""

_RECORD = f"""CREATE TABLE forecast_record (
    forecast_id TEXT PRIMARY KEY NOT NULL CHECK ({_ULID}),
    run_id INTEGER NOT NULL REFERENCES forecast_run (run_id),
    claim_id TEXT NOT NULL REFERENCES forecast_claim_registry (claim_id),
    scope_kind TEXT NOT NULL CHECK (scope_kind = 'market'),
    scope_key TEXT NOT NULL CHECK (scope_key = 'TAIEX'),
    horizon INTEGER NOT NULL CHECK (typeof(horizon) = 'integer' AND horizon IN (3, 5)),
    data_as_of TEXT NOT NULL CHECK ({_date("data_as_of")}),
    definition_version TEXT NOT NULL CHECK (definition_version GLOB 'dirdef-v[0-9]*.[0-9]*'),
    definition_sha256 TEXT NOT NULL CHECK ({_hex64("definition_sha256")}),
    rules_version TEXT NOT NULL CHECK ({_text("rules_version")}),
    rules_sha256 TEXT NOT NULL CHECK ({_hex64("rules_sha256")}),
    label TEXT NOT NULL CHECK (label IN ('bullish', 'range', 'bearish', 'insufficient')),
    range_basis TEXT CHECK (range_basis IS NULL OR {_text("range_basis")}),
    missing_json TEXT NOT NULL CHECK ({_json("missing_json", "array")}),
    evidence_json TEXT NOT NULL CHECK ({_json("evidence_json", "object")}),
    band_def TEXT NOT NULL CHECK ({_has_keys("band_def", BAND_DEF_KEYS)}),
    base_close TEXT NOT NULL CHECK ({_text("base_close")}),
    baseline_predictions_json TEXT NOT NULL CHECK (
        {_has_keys("baseline_predictions_json", BASELINE_KEYS)}
    ),
    input_series_sha256 TEXT NOT NULL REFERENCES forecast_input_series (content_sha256),
    inputs_max_fetched_at TEXT NOT NULL CHECK ({_ts("inputs_max_fetched_at")}),
    created_at TEXT NOT NULL CHECK ({_ts("created_at")}),
    late INTEGER NOT NULL CHECK (typeof(late) = 'integer' AND late IN (0, 1)),
    late_cutoff_at TEXT NOT NULL CHECK ({_ts("late_cutoff_at")}),
    valid_until_session_estimate TEXT NOT NULL CHECK (
        {_date("valid_until_session_estimate")} AND valid_until_session_estimate > data_as_of
    ),
    validation_status TEXT NOT NULL CHECK (validation_status = 'unverified'),
    content_hash TEXT NOT NULL CHECK ({_hex64("content_hash")}),
    UNIQUE (claim_id, data_as_of),
    CHECK (late = (created_at >= late_cutoff_at)),
    CHECK (
        CASE WHEN json_valid(missing_json) AND json_type(missing_json) = 'array'
        THEN (label = 'insufficient') = (json_array_length(missing_json) > 0)
        ELSE 0 END
    ),
    CHECK (
        label <> 'insufficient'
        OR CASE WHEN json_valid(band_def)
            THEN json_extract(band_def, '$.up_pct') IS NULL
                AND json_extract(band_def, '$.down_pct') IS NULL
            ELSE 0 END
    )
)"""


#: The keys each ``{table}_no_replace`` trigger compares (ADR-0030 supplement 1): every
#: column set an ``INSERT OR REPLACE`` can collide on. A tuple is one composite key.
REPLACE_KEYS: Final[dict[str, tuple[str | tuple[str, ...], ...]]] = {
    "forecast_run": ("run_id",),
    "forecast_run_end": ("run_id",),
    "forecast_input_series": ("series_id", "content_sha256"),
    "forecast_claim_registry": ("rowid", "claim_id"),
    "forecast_record": ("rowid", "forecast_id", ("claim_id", "data_as_of")),
}


def _key_match(key: str | tuple[str, ...]) -> str:
    if isinstance(key, str):
        return f"{key} = NEW.{key}"
    return "(" + " AND ".join(f"{column} = NEW.{column}" for column in key) + ")"


def _no_replace_trigger(table: str) -> tuple[str, str]:
    name = f"{table}_no_replace"
    matches = "\n        OR ".join(_key_match(key) for key in REPLACE_KEYS[table])
    sql = (
        f"CREATE TRIGGER {name} BEFORE INSERT ON {table}\n"
        f"WHEN EXISTS (\n"
        f"    SELECT 1 FROM {table}\n"
        f"    WHERE {matches}\n"
        f")\n"
        f"BEGIN\n"
        f"    SELECT RAISE(ABORT, '{APPEND_ONLY_MESSAGE}');\n"
        f"END"
    )
    return name, sql


def _trigger(table: str, event: str) -> tuple[str, str]:
    name = f"{table}_no_{event.lower()}"
    sql = (
        f"CREATE TRIGGER {name} BEFORE {event} ON {table}\n"
        f"BEGIN\n"
        f"    SELECT RAISE(ABORT, '{APPEND_ONLY_MESSAGE}');\n"
        f"END"
    )
    return name, sql


#: Every ledger object: ``(type, name) -> CREATE statement``, in creation order.
EXPECTED_OBJECTS: Final[dict[tuple[str, str], str]] = {
    ("table", "forecast_run"): _RUN,
    ("table", "forecast_run_end"): _RUN_END,
    ("table", "forecast_input_series"): _INPUT_SERIES,
    ("table", "forecast_claim_registry"): _CLAIM_REGISTRY,
    ("table", "forecast_record"): _RECORD,
}
for _table in TABLES:
    for _event in ("UPDATE", "DELETE"):
        _name, _sql = _trigger(_table, _event)
        EXPECTED_OBJECTS[("trigger", _name)] = _sql
    _name, _sql = _no_replace_trigger(_table)
    EXPECTED_OBJECTS[("trigger", _name)] = _sql


class SchemaIncompleteError(RuntimeError):
    """The ledger schema in this database is not exactly the D-2 schema; writes are refused."""


class SchemaNotEmptyError(RuntimeError):
    """:func:`create_schema` found ledger objects already present; it creates nothing."""


@dataclass(frozen=True)
class SchemaStatus:
    """What :func:`schema_status` found, each as sorted ``type:name`` strings."""

    missing: tuple[str, ...]
    altered: tuple[str, ...]
    unexpected: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not (self.missing or self.altered or self.unexpected)


def _ledger_objects(conn: sqlite3.Connection) -> dict[tuple[str, str], str | None]:
    """Every ``sqlite_master`` object named or attached to a ``forecast_`` / ``plan_`` table."""
    clauses = " OR ".join(
        f"substr({column}, 1, {len(prefix)}) = '{prefix}'"
        for prefix in LEDGER_PREFIXES
        for column in ("name", "tbl_name")
    )
    rows = conn.execute(f"SELECT type, name, sql FROM sqlite_master WHERE {clauses}").fetchall()
    return {
        (str(kind), str(name)): (None if sql is None else str(sql))
        for kind, name, sql in rows
        # Unique constraints' implicit indexes have no SQL and are part of their table.
        if not (kind == "index" and str(name).startswith("sqlite_autoindex_"))
    }


def schema_status(conn: sqlite3.Connection) -> SchemaStatus:
    """Compare ``sqlite_master`` with :data:`EXPECTED_OBJECTS` (ADR-0030 D-1, S-1, K-5)."""
    found = _ledger_objects(conn)
    missing = sorted(
        f"{kind}:{name}" for kind, name in EXPECTED_OBJECTS if (kind, name) not in found
    )
    altered = sorted(
        f"{kind}:{name}"
        for (kind, name), sql in EXPECTED_OBJECTS.items()
        if (kind, name) in found and found[(kind, name)] != sql
    )
    unexpected = sorted(
        f"{kind}:{name}" for kind, name in found if (kind, name) not in EXPECTED_OBJECTS
    )
    return SchemaStatus(
        missing=tuple(missing), altered=tuple(altered), unexpected=tuple(unexpected)
    )


def require_complete_schema(conn: sqlite3.Connection) -> None:
    """Raise :class:`SchemaIncompleteError` unless :func:`schema_status` is complete."""
    status = schema_status(conn)
    if not status.complete:
        raise SchemaIncompleteError(
            f"forecast ledger schema incomplete: missing={list(status.missing)} "
            f"altered={list(status.altered)} unexpected={list(status.unexpected)}"
        )


def create_schema(conn: sqlite3.Connection) -> None:
    """Create every ledger object in one transaction, on a database that has none of them.

    ``conn`` must be in autocommit mode (``isolation_level=None``). Any ledger
    object already present raises :class:`SchemaNotEmptyError` and nothing is
    created: there is no "create what is missing", because that is a migration.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        if _ledger_objects(conn):
            raise SchemaNotEmptyError("forecast ledger objects already exist; nothing created")
        for sql in EXPECTED_OBJECTS.values():
            conn.execute(sql)
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
