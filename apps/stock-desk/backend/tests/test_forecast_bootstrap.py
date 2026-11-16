"""``ForecastStore.bootstrap`` and ``schema.create_objects`` (ADR-0030 supplement 7, S-15).

* point 1: ``create_objects`` runs only inside the caller's transaction, refuses
  any ledger object and commits nothing itself; the DDL text is the one the
  existing schema tests pin (:data:`EXPECTED_OBJECTS_SHA256`, equal to the value
  before this change);
* points 2-3: one transaction -- no ledger object, every object, the
  completeness check, the h3 row, the h5 row, COMMIT. 0 and 1 each register;
  six kinds of existing object (table, trigger, index, view, ``plan_`` table,
  a name in other letter case) are each refused with nothing created; a
  clock error, ``KeyboardInterrupt``, a ``registered_at`` that does not
  increase and a failure after the objects are created each roll everything
  back, leaving no ledger object and the non-ledger table unchanged; success
  leaves exactly 15 triggers; the input checks run before any connection;
* point 4: the store clock is re-read until it is later (success), for at most
  ``CLOCK_WAIT_SECONDS`` (rollback); ``register_claim`` still refuses at once;
* point 2: ``provisional_results_seen`` in registration order, refusing a value
  that is not 0 or 1;
* point 6 (AST): in ``app/`` only ``store.py`` calls ``create_objects``, no
  module calls ``create_schema``, only ``claims.py`` calls ``bootstrap`` (CG-2 PR),
  ``_write(fresh=True)`` is only in ``ForecastStore.bootstrap``, recorder.py and
  report.py call none of them, schema.py holds no INSERT.

Every database is a ``tmp_path`` file with synthetic rows; the clock is injected.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest

from app.forecast import schema as schema_module
from app.forecast import store as store_module
from app.forecast.canonical import APP_ROOT, canonical_timestamp
from app.forecast.schema import (
    EXPECTED_OBJECTS,
    LEDGER_PREFIXES,
    SchemaNotEmptyError,
    create_objects,
)
from app.forecast.store import (
    ClaimInput,
    ForecastStore,
    ForecastStoreError,
    LedgerInconsistentError,
)
from tests.forecast_ledger_helpers import FakeClock, fixture_definition, taipei

#: sha256 of ``json.dumps([[list(key), sql] for key, sql in EXPECTED_OBJECTS.items()])``,
#: computed on ``origin/product/stock-desk`` before supplement 7 (DDL zero diff).
EXPECTED_OBJECTS_SHA256: Final = "efecca9bc815f3022eb92444ea59d2e8836c2f4ad6b3a5a7cafb8f0bb90f6d47"

START = taipei(2026, 11, 20, 21, 0)
APP_ROWS: Final = [("theme", "dark"), ("currency", "TWD")]


def claim_input(horizon: Any, *, seen: bool = False, **overrides: Any) -> ClaimInput:
    values: dict[str, Any] = {
        "horizon": horizon,
        "rules_version": f"outlook-test-h{horizon}",
        "rules_bytes": f"version: 1.0.0\nrules: [h{horizon}]\n".encode(),
        "rules_logic_sha256": str(horizon) * 64,
        "definition": fixture_definition(),
        "frozen_commit": "0123456789abcdef0123456789abcdef01234567",
        "prereg_doc_path": "work/research/prereg.md",
        "prereg_doc_blob": b"prereg bytes",
        "review_refs": "work/reviews/risk.md work/reviews/qa.md",
        "replaces_claim_id": None,
        "replace_reason": None,
        "provisional_results_seen": seen,
    }
    values.update(overrides)
    return ClaimInput(**values)


def pair(*, seen: bool = False) -> list[ClaimInput]:
    return [claim_input(3, seen=seen), claim_input(5, seen=seen)]


class ScriptedClock:
    """Returns ``script`` one value per call (a callable is called), then keeps the last."""

    def __init__(self, *script: datetime | Callable[[], datetime]) -> None:
        self.script = list(script)
        self.calls = 0

    def __call__(self) -> datetime:
        index = min(self.calls, len(self.script) - 1)
        self.calls += 1
        value = self.script[index]
        return value() if callable(value) else value


class FakeTime:
    """A stand-in for the store module's ``time``: monotonic ticks ``step`` per read."""

    def __init__(self, *, step: float) -> None:
        self.step = step
        self.reads = 0
        self.sleeps = 0

    def monotonic(self) -> float:
        self.reads += 1
        return self.reads * self.step

    def sleep(self, seconds: float) -> None:
        self.sleeps += 1


def _raise(exc: BaseException) -> Callable[[], datetime]:
    def fail() -> datetime:
        raise exc

    return fail


@pytest.fixture
def db(tmp_path: Path) -> Path:
    """A synthetic main database: one non-ledger table with rows, no ledger object."""
    path = tmp_path / "main.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE app_settings (k TEXT PRIMARY KEY, v TEXT)")
        conn.executemany("INSERT INTO app_settings VALUES (?, ?)", APP_ROWS)
        conn.commit()
    return path


def _master(path: Path) -> list[tuple[str, str, str, str | None]]:
    with closing(sqlite3.connect(path)) as conn:
        return [
            (str(t), str(n), str(tbl), None if s is None else str(s))
            for t, n, tbl, s in conn.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            )
        ]


def _ledger_names(path: Path) -> list[str]:
    return [
        name
        for _, name, tbl, _ in _master(path)
        if any(n.lower().startswith(p) for n in (name, tbl) for p in LEDGER_PREFIXES)
    ]


def _app_rows(path: Path) -> list[tuple[str, str]]:
    with closing(sqlite3.connect(path)) as conn:
        return [(str(k), str(v)) for k, v in conn.execute("SELECT k, v FROM app_settings")]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_untouched(path: Path, before: str) -> None:
    assert _ledger_names(path) == []
    assert _app_rows(path) == APP_ROWS
    assert _digest(path) == before
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]


# --- point 1: create_objects ---------------------------------------------------------------


def test_s15_the_ddl_text_is_unchanged() -> None:
    payload = json.dumps([[list(key), sql] for key, sql in EXPECTED_OBJECTS.items()])
    assert hashlib.sha256(payload.encode()).hexdigest() == EXPECTED_OBJECTS_SHA256
    assert len(EXPECTED_OBJECTS) == 20


def test_create_objects_refuses_outside_a_transaction(db: Path) -> None:
    before = _digest(db)
    with closing(sqlite3.connect(db, isolation_level=None)) as conn:
        with pytest.raises(RuntimeError, match="inside the caller's open transaction"):
            create_objects(conn)
    _assert_untouched(db, before)


def test_create_objects_commits_nothing_itself(db: Path) -> None:
    before = _digest(db)
    with closing(sqlite3.connect(db, isolation_level=None)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        create_objects(conn)
        assert conn.in_transaction
        assert schema_module.schema_status(conn).complete
        conn.execute("ROLLBACK")
    _assert_untouched(db, before)


def test_create_objects_refuses_a_ledger_object_before_creating_any(db: Path) -> None:
    with closing(sqlite3.connect(db, isolation_level=None)) as conn:
        conn.execute("CREATE TABLE forecast_x (a)")
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(SchemaNotEmptyError):
            create_objects(conn)
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master")]
        conn.execute("ROLLBACK")
    assert sorted(names) == ["app_settings", "forecast_x", "sqlite_autoindex_app_settings_1"]


# --- points 2-3: bootstrap ------------------------------------------------------------------


@pytest.mark.parametrize("seen", [False, True])
def test_s15_bootstrap_registers_both_claims_with_the_typed_value(db: Path, seen: bool) -> None:
    store = ForecastStore(db, clock=ScriptedClock(START, START + timedelta(seconds=1)))
    h3, h5 = store.bootstrap(claims=pair(seen=seen))
    assert h3.startswith("market|h3|") and h5.startswith("market|h5|")
    assert store.ledger_schema_status().complete
    assert [row.claim_id for row in store.forward_claims()] == [h3, h5]
    assert store.runs() == []
    assert store.provisional_results_seen() == [(h3, int(seen)), (h5, int(seen))]
    assert _app_rows(db) == APP_ROWS
    first, second = store.forward_claims()
    assert first.registered_at < second.registered_at


def test_s15_bootstrap_leaves_exactly_fifteen_triggers(db: Path) -> None:
    ForecastStore(db, clock=ScriptedClock(START, START + timedelta(seconds=1))).bootstrap(
        claims=pair()
    )
    triggers = [name for kind, name, _, _ in _master(db) if kind == "trigger"]
    assert len(triggers) == 15
    assert sorted(triggers) == sorted(n for kind, n in EXPECTED_OBJECTS if kind == "trigger")


def test_bootstrap_stores_what_register_claim_would(db: Path, tmp_path: Path) -> None:
    # The shared _prepare_claim / _insert_claim: the same row either way.
    store = ForecastStore(db, clock=ScriptedClock(START, START + timedelta(seconds=1)))
    store.bootstrap(claims=pair(seen=True))
    other = tmp_path / "other.db"
    with closing(sqlite3.connect(other, isolation_level=None)) as conn:
        schema_module.create_schema(conn)
    plain = ForecastStore(other, clock=ScriptedClock(START, START + timedelta(seconds=1)))
    for claim in pair(seen=True):
        plain.register_claim(**{f: getattr(claim, f) for f in ClaimInput.__dataclass_fields__})

    def rows(path: Path) -> list[tuple[object, ...]]:
        with closing(sqlite3.connect(path)) as conn:
            return conn.execute("SELECT * FROM forecast_claim_registry ORDER BY rowid").fetchall()

    assert rows(db) == rows(other)


#: S-15: the six kinds of existing object, each a ledger object by name or table.
EXISTING_OBJECTS: Final = {
    "table": "CREATE TABLE forecast_extra (a)",
    "trigger": ("CREATE TRIGGER forecast_audit AFTER INSERT ON app_settings BEGIN SELECT 1; END"),
    "index": "CREATE INDEX forecast_by_value ON app_settings (v)",
    "view": "CREATE VIEW forecast_view AS SELECT k FROM app_settings",
    "plan_table": "CREATE TABLE plan_items (a)",
    "other_case": "CREATE TABLE Forecast_Run (a)",
}


@pytest.mark.parametrize("kind", sorted(EXISTING_OBJECTS))
def test_s15_an_existing_ledger_object_is_refused_and_nothing_is_created(
    db: Path, kind: str
) -> None:
    with closing(sqlite3.connect(db)) as conn:
        conn.execute(EXISTING_OBJECTS[kind])
        conn.commit()
    master, before = _master(db), _digest(db)
    clock = ScriptedClock(START, START + timedelta(seconds=1))
    with pytest.raises(SchemaNotEmptyError):
        ForecastStore(db, clock=clock).bootstrap(claims=pair())
    assert _master(db) == master
    assert _app_rows(db) == APP_ROWS
    assert _digest(db) == before
    assert clock.calls == 0  # refused before any registration step


def test_a_second_bootstrap_is_refused_and_changes_nothing(db: Path) -> None:
    store = ForecastStore(db, clock=ScriptedClock(START, START + timedelta(seconds=1)))
    ids = store.bootstrap(claims=pair())
    before = _digest(db)
    with pytest.raises(SchemaNotEmptyError):
        store.bootstrap(claims=pair(seen=True))
    assert _digest(db) == before
    assert [row.claim_id for row in store.forward_claims()] == list(ids)


def _rollback_cases() -> Iterator[tuple[str, Callable[[], ScriptedClock], type[BaseException]]]:
    yield (
        "clock_raises_before_the_second_row",
        lambda: ScriptedClock(START, _raise(RuntimeError("clock failed"))),
        RuntimeError,
    )
    yield (
        "keyboard_interrupt_before_the_second_row",
        lambda: ScriptedClock(START, _raise(KeyboardInterrupt())),
        KeyboardInterrupt,
    )
    yield (
        "keyboard_interrupt_on_the_first_row",
        lambda: ScriptedClock(_raise(KeyboardInterrupt())),
        KeyboardInterrupt,
    )
    yield (
        "registered_at_does_not_increase",
        lambda: ScriptedClock(START),
        ForecastStoreError,
    )
    yield (
        "registered_at_goes_back",
        lambda: ScriptedClock(START, START - timedelta(seconds=5)),
        ForecastStoreError,
    )


@pytest.mark.parametrize(
    ("make_clock", "error"),
    [(make, error) for _, make, error in _rollback_cases()],
    ids=[name for name, _, _ in _rollback_cases()],
)
def test_s15_a_failure_in_the_transaction_rolls_everything_back(
    db: Path, make_clock: Callable[[], ScriptedClock], error: type[BaseException]
) -> None:
    before = _digest(db)
    with pytest.raises(error):
        ForecastStore(db, clock=make_clock()).bootstrap(claims=pair())
    _assert_untouched(db, before)


def test_a_failure_after_the_objects_are_created_rolls_them_back(
    db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The completeness check fails after create_objects ran in the transaction.
    def incomplete(conn: sqlite3.Connection) -> None:
        assert schema_module.schema_status(conn).complete  # the objects exist here
        raise schema_module.SchemaIncompleteError("injected")

    monkeypatch.setattr(store_module, "require_complete_schema", incomplete)
    before = _digest(db)
    with pytest.raises(schema_module.SchemaIncompleteError, match="injected"):
        ForecastStore(db, clock=ScriptedClock(START)).bootstrap(claims=pair())
    _assert_untouched(db, before)


def test_a_failure_on_the_second_insert_rolls_the_first_row_back(db: Path) -> None:
    # An SQL error in the transaction after the h3 row is inserted: the h3 row goes too.
    store = ForecastStore(db, clock=ScriptedClock(START, START + timedelta(seconds=1)))
    original = store._insert_claim
    calls: list[str] = []

    def second_fails(conn: sqlite3.Connection, prepared: Any, **kw: Any) -> str:
        calls.append(prepared.claim_id)
        if len(calls) == 2:
            conn.execute("INSERT INTO forecast_run (run_id) VALUES (NULL)")  # NOT NULL fails
        return original(conn, prepared, **kw)

    store._insert_claim = second_fails  # type: ignore[method-assign]
    before = _digest(db)
    with pytest.raises(sqlite3.IntegrityError):
        store.bootstrap(claims=pair())
    assert len(calls) == 2
    _assert_untouched(db, before)


@pytest.mark.parametrize(
    "claims",
    [
        [],
        [claim_input(3)],
        [claim_input(3), claim_input(5), claim_input(5)],
        [claim_input(5), claim_input(3)],
        [claim_input(3), claim_input(3)],
        [claim_input(3), claim_input(5, replaces_claim_id="x", replace_reason="r")],
        [claim_input(3), {"horizon": 5}],
        [claim_input(3), claim_input(5, provisional_results_seen=1)],
        [claim_input(3), claim_input(5, frozen_commit=" ")],
    ],
    ids=[
        "none",
        "one",
        "three",
        "reversed",
        "h3_twice",
        "replacing",
        "not_a_claim_input",
        "seen_not_bool",
        "blank_commit",
    ],
)
def test_the_inputs_are_checked_before_any_connection(tmp_path: Path, claims: list[Any]) -> None:
    path = tmp_path / "absent.db"
    clock = ScriptedClock(START)
    with pytest.raises(ForecastStoreError):
        ForecastStore(path, clock=clock).bootstrap(claims=claims)
    assert not path.exists()
    assert clock.calls == 0


# --- point 4: the store clock ---------------------------------------------------------------


def test_s15_the_clock_is_re_read_until_it_is_later(db: Path) -> None:
    later = START + timedelta(microseconds=1)
    clock = ScriptedClock(START, START, START, START, later)
    h3, h5 = ForecastStore(db, clock=clock).bootstrap(claims=pair())
    rows = ForecastStore(db).forward_claims()
    assert [r.registered_at for r in rows] == [START, later]
    assert clock.calls == 5
    assert [r.claim_id for r in rows] == [h3, h5]


def test_s15_a_clock_that_never_gets_later_is_given_up_within_the_wait(
    db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store_module, "time", FakeTime(step=0.01))
    clock = ScriptedClock(START)
    before = _digest(db)
    with pytest.raises(ForecastStoreError, match="later than every registration"):
        ForecastStore(db, clock=clock).bootstrap(claims=pair())
    # 1 s of 0.01 s ticks: the first row's read, then about 100 re-reads.
    assert 90 <= clock.calls <= 110
    _assert_untouched(db, before)


def test_the_wait_is_bounded_in_real_time(db: Path) -> None:
    started = datetime.now()
    with pytest.raises(ForecastStoreError):
        ForecastStore(db, clock=ScriptedClock(START)).bootstrap(claims=pair())
    assert timedelta(seconds=1) <= datetime.now() - started < timedelta(seconds=5)
    assert store_module.CLOCK_WAIT_SECONDS == 1.0


def test_register_claim_never_waits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "ledger.db"
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        schema_module.create_schema(conn)
    store = ForecastStore(path, clock=FakeClock(START))
    store.register_claim(**{f: getattr(claim_input(3), f) for f in ClaimInput.__dataclass_fields__})

    fake = FakeTime(step=0.01)
    monkeypatch.setattr(store_module, "time", fake)
    with pytest.raises(ForecastStoreError, match="later than every registration"):
        store.register_claim(
            **{f: getattr(claim_input(5), f) for f in ClaimInput.__dataclass_fields__}
        )
    assert len(store.forward_claims()) == 1
    assert fake.sleeps == 0


def test_registered_at_comes_from_the_store_clock(db: Path) -> None:
    times = (START, START + timedelta(minutes=3))
    ForecastStore(db, clock=ScriptedClock(*times)).bootstrap(claims=pair())
    with closing(sqlite3.connect(db)) as conn:
        stored = [r[0] for r in conn.execute("SELECT registered_at FROM forecast_claim_registry")]
    assert stored == [canonical_timestamp(t) for t in times]


# --- provisional_results_seen ---------------------------------------------------------------


def test_provisional_results_seen_is_in_registration_order(tmp_path: Path) -> None:
    path = tmp_path / "ledger.db"
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        schema_module.create_schema(conn)
    clock = FakeClock(START)
    store = ForecastStore(path, clock=clock)
    assert store.provisional_results_seen() == []
    for claim in (claim_input(5, seen=True), claim_input(3)):
        clock.advance(seconds=1)
        store.register_claim(**{f: getattr(claim, f) for f in ClaimInput.__dataclass_fields__})
    assert [v for _, v in store.provisional_results_seen()] == [1, 0]


@pytest.mark.parametrize("value", [2, -1, "1", 1.0, None])
def test_provisional_results_seen_refuses_a_value_that_is_not_0_or_1(
    tmp_path: Path, value: object
) -> None:
    # A stand-in registry without the CHECK, so the value can be stored at all.
    path = tmp_path / "raw.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(
            "CREATE TABLE forecast_claim_registry"
            " (claim_id TEXT, provisional_results_seen, registered_at TEXT)"
        )
        conn.execute("INSERT INTO forecast_claim_registry VALUES ('a', 0, '1')")
        conn.execute("INSERT INTO forecast_claim_registry VALUES ('b', ?, '2')", (value,))
        conn.commit()
    with pytest.raises(LedgerInconsistentError):
        ForecastStore(path).provisional_results_seen()


def test_provisional_results_seen_reads_on_a_read_only_connection(
    db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ForecastStore(db, clock=ScriptedClock(START, START + timedelta(seconds=1)))
    store.bootstrap(claims=pair())

    def no_write(self: ForecastStore) -> Any:
        raise AssertionError("a write connection was opened")

    monkeypatch.setattr(ForecastStore, "_connect", no_write)
    assert len(store.provisional_results_seen()) == 2


# --- point 6: AST boundaries ----------------------------------------------------------------


def _app_sources() -> dict[str, str]:
    return {
        path.relative_to(APP_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(APP_ROOT.rglob("*.py"))
    }


def _callers(name: str, sources: dict[str, str]) -> set[str]:
    """Modules that call ``name`` as ``x.name(...)`` or ``name(...)``."""
    return {
        path
        for path, source in sources.items()
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == name)
            or (isinstance(node.func, ast.Name) and node.func.id == name)
        )
    }


def _fresh_write_sites(source: str) -> list[str]:
    """``Class.method`` of every ``_write(...)`` call that passes any argument (``fresh``)."""
    found: list[str] = []
    tree = ast.parse(source)
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
            for call in ast.walk(fn):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "_write"
                    and (call.args or call.keywords)
                ):
                    found.append(f"{cls.name}.{fn.name}")
    return found


def test_s15_only_the_store_calls_create_objects() -> None:
    # Supplement 7 point 1 has create_schema wrap create_objects inside schema.py
    # itself; every other caller in app/ is store.py.
    sources = _app_sources()
    assert _callers("create_objects", sources) == {"forecast/store.py", "forecast/schema.py"}
    tree = ast.parse(sources["forecast/schema.py"])
    in_schema = {
        fn.name
        for fn in tree.body
        if isinstance(fn, ast.FunctionDef) and _callers("create_objects", {"x": ast.unparse(fn)})
    }
    assert in_schema == {"create_schema"}


def test_s15_no_app_module_calls_create_schema() -> None:
    assert _callers("create_schema", _app_sources()) == set()


def test_s15_only_the_claims_cli_calls_bootstrap() -> None:
    # Supplement 7 point 6: before the CG-2 PR no module; from the CG-2 PR on, claims.py.
    assert _callers("bootstrap", _app_sources()) == {"forecast/claims.py"}


def test_s15_write_fresh_is_only_in_store_bootstrap() -> None:
    sources = _app_sources()
    assert _fresh_write_sites(sources["forecast/store.py"]) == ["ForecastStore.bootstrap"]
    others = {p: s for p, s in sources.items() if p != "forecast/store.py"}
    assert {p for p, s in others.items() if _fresh_write_sites(s)} == set()
    # No other module reaches a store's _write; api/settings.py has an unrelated
    # module-level function of that name, called bare, so only method calls count.
    method_calls = {
        p
        for p, s in others.items()
        for n in ast.walk(ast.parse(s))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "_write"
    }
    assert method_calls == set()


def test_s15_the_bootstrap_call_passes_fresh_true() -> None:
    tree = ast.parse(Path(store_module.__file__).read_text(encoding="utf-8"))
    (bootstrap,) = [
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "bootstrap"
    ]
    calls = [
        ast.unparse(c)
        for c in ast.walk(bootstrap)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "_write"
    ]
    assert calls == ["self._write(fresh=True)"]


@pytest.mark.parametrize("module", ["forecast/recorder.py", "forecast/report.py"])
def test_s15_recorder_and_report_call_none_of_the_schema_paths(module: str) -> None:
    source = {module: _app_sources()[module]}
    for name in ("create_objects", "create_schema", "bootstrap"):
        assert _callers(name, source) == set(), name
    assert not _fresh_write_sites(source[module])


def test_s15_schema_holds_no_insert() -> None:
    tree = ast.parse(Path(schema_module.__file__).read_text(encoding="utf-8"))
    sql = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.search(r"\bINSERT\s+(OR\s+\w+\s+)?INTO\b", node.value)
    ]
    assert sql == []


def test_the_boundary_scans_have_teeth() -> None:
    sources = {
        "a.py": "store.bootstrap(claims=c)\n",
        "b.py": "create_objects(conn)\n",
        "c.py": "bootstrap = 1\n",
    }
    assert _callers("bootstrap", sources) == {"a.py"}
    assert _callers("create_objects", sources) == {"b.py"}
    source = (
        "class S:\n"
        "    def a(self):\n        with self._write(fresh=True):\n            pass\n"
        "    def b(self):\n        with self._write():\n            pass\n"
        "    def c(self):\n        with self._write(True):\n            pass\n"
    )
    assert _fresh_write_sites(source) == ["S.a", "S.c"]


# --- supplement 7 addendum S-15a point 1: create_objects callers per function ----------------


def _create_objects_sites(source: str) -> set[str]:
    """The functions of ``source`` that call ``create_objects``, under any import alias.

    A call counts when it is ``create_objects(...)`` or a name bound by
    ``from ... import create_objects as <name>``, or any ``<expr>.create_objects(...)``
    (``schema.create_objects``, a module alias), or ``getattr(<expr>, "create_objects")``.
    The site is the innermost enclosing function's name (``<module>`` at top level).
    """
    tree = ast.parse(source)
    names = {"create_objects"} | {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name == "create_objects"
    }

    def is_call(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Name) and func.id in names:
            return True
        if isinstance(func, ast.Attribute) and func.attr == "create_objects":
            return True
        return (
            isinstance(func, ast.Name)
            and func.id == "getattr"
            and any(isinstance(a, ast.Constant) and a.value == "create_objects" for a in node.args)
        )

    found: set[str] = set()

    def visit(node: ast.AST, where: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = (
                child.name if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) else where
            )
            if is_call(child):
                found.add(inner)
            visit(child, inner)

    visit(tree, "<module>")
    return found


def test_s15a_create_objects_is_called_from_exactly_two_functions() -> None:
    sites = {
        (path, site)
        for path, source in _app_sources().items()
        for site in _create_objects_sites(source)
    }
    assert sites == {("forecast/store.py", "_write"), ("forecast/schema.py", "create_schema")}


def test_s15a_the_function_scan_has_teeth() -> None:
    assert _create_objects_sites("def f(c):\n    create_objects(c)\n") == {"f"}
    aliased = "from app.forecast.schema import create_objects as make\ndef g(c):\n    make(c)\n"
    assert _create_objects_sites(aliased) == {"g"}
    module = (
        "import app.forecast.schema as s\n"
        "class K:\n    def h(self, c):\n        s.create_objects(c)\n"
    )
    assert _create_objects_sites(module) == {"h"}
    dynamic = "def i(m, c):\n    getattr(m, 'create_objects')(c)\n"
    assert _create_objects_sites(dynamic) == {"i"}
    assert _create_objects_sites("create_objects(c)\n") == {"<module>"}
    assert _create_objects_sites("def j():\n    create_objects = 1\n") == set()
    # The real store.py with one more caller is caught (reverse check on a copy).
    store_source = Path(store_module.__file__).read_text(encoding="utf-8")
    sneaky = (
        store_source
        + "\n\ndef sneaky(conn):\n"
        + "    from app.forecast.schema import create_objects as build\n"
        + "    build(conn)\n"
    )
    assert _create_objects_sites(store_source) == {"_write"}
    assert _create_objects_sites(sneaky) == {"_write", "sneaky"}


# --- a failure of COMMIT itself ---------------------------------------------------------------


class CommitFailsConnection:
    """Wraps a ``sqlite3.Connection``: ``execute("COMMIT")`` raises, the rest is delegated.

    Every statement's first word passed to ``execute`` is recorded, and so is
    ``close``, so the test sees that the store issued ROLLBACK itself before
    closing (closing alone would also discard the transaction).
    """

    def __init__(self, conn: sqlite3.Connection, log: list[str]) -> None:
        self._conn = conn
        self._log = log

    def execute(self, sql: str, *args: Any) -> sqlite3.Cursor:
        self._log.append(sql.split()[0].upper())
        if sql.strip().upper() == "COMMIT":
            raise sqlite3.OperationalError("injected: COMMIT failed")
        return self._conn.execute(sql, *args)

    @property
    def in_transaction(self) -> bool:
        return self._conn.in_transaction

    def close(self) -> None:
        self._log.append("<close>")
        self._conn.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def test_a_failing_commit_rolls_everything_back(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log: list[str] = []
    real_open = store_module._open_connection

    def open_wrapped(path: Path) -> Any:
        return CommitFailsConnection(real_open(path), log)

    monkeypatch.setattr(store_module, "_open_connection", open_wrapped)
    before = _digest(db)
    store = ForecastStore(db, clock=ScriptedClock(START, START + timedelta(seconds=1)))
    with pytest.raises(sqlite3.OperationalError, match="injected: COMMIT failed"):
        store.bootstrap(claims=pair())
    # Both rows were inserted, COMMIT failed, the store rolled back, then closed.
    assert log.count("INSERT") == 2
    assert log[-3:] == ["COMMIT", "ROLLBACK", "<close>"]
    monkeypatch.undo()
    # A new connection: no ledger object, the other table as it was, no left-over file.
    with closing(sqlite3.connect(db)) as conn:
        names = [str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master")]
    assert not [n for n in names if n.lower().startswith(LEDGER_PREFIXES)]
    _assert_untouched(db, before)
