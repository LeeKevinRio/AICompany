"""The ``/today`` seam N-171 and N-168 build on (ADR-0035 補充四 S-4, CEO #102).

Structure only -- no wording, no behaviour. SEAM-T1～T7 here; SEAM-T8 is the
frontend's (``app/playbook/__tests__/TodaySeamFixture.test.tsx``).

* T1 -- the new keys exist and are empty / ``null``, on every scenario, except
  what an owner registered as ``filled`` (補充四釐清二 E-6 第 6 點).
* T2 -- with the new keys dropped, every body equals the one recorded on the
  pre-seam code (``tests/golden/seam/pre_seam_responses.json``, frozen by
  sha256) with the registered deltas applied (釐清二 E-5, E-6).
* T3 -- ``read_in_flight`` runs exactly once per ``evaluate_today``, on both
  paths; on the authored one after ``_settle_pending``.
* T4 -- ``read_in_flight`` runs ``BEGIN``, SELECTs and ``COMMIT`` only; the
  parts no owner registered as filled are still their stub defaults.
* T5 -- ``DirectiveLine(`` appears in ``_lines`` only; ``labeled_batches`` is
  keyword-only with no default.
* T6 -- ``settle_pending(today=d) == _settle_pending(d).result``.
* T7 -- the unauthored path still loads, settles and writes nothing.
"""

from __future__ import annotations

import ast
import inspect
import json
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.api import playbook as api_module
from app.playbook import wording
from app.playbook.models import LabeledBatch, PlaybookEvaluation
from app.playbook.service import PlaybookService, SettlementRun
from app.playbook.store import (
    EntryBeforeExitRead,
    InFlightRead,
    PendingExitRead,
    PlaybookStore,
)
from tests.same_day_helpers import (
    TUESDAY,
    WEDNESDAY,
    buy_line,
    hold,
    log_like_before_n172a,
)
from tests.seam_helpers import (
    APPROVED,
    CLOCK_KEYS,
    GOLDEN,
    GOLDEN_SHA256,
    SCENARIOS,
    Registration,
    RegistryError,
    clocked_desk,
    dropped_keys,
    expected_bodies,
    filled,
    golden_sha256,
    load_registrations,
    parse_registration,
    without,
)

TODAY_LISTS = (
    "pending_exit_directives",
    "entry_before_exit_directives",
    "entry_before_exit_blocked_directives",
)
NOTE = "entry_before_exit_note"
SEAM_KEYS = frozenset({*TODAY_LISTS, NOTE})

APP_ROOT = Path(api_module.__file__).resolve().parents[1]
TESTS_ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="module")
def registrations() -> list[Registration]:
    return load_registrations()


@pytest.fixture(scope="module")
def bodies(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    work = tmp_path_factory.mktemp("seam")
    return {name: run(work / f"{name}.db") for name, run in SCENARIOS.items()}


def _directive_lines(body: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for key in ("directives", "pending_directives", *TODAY_LISTS):
        yield from body.get(key, [])


# --- SEAM-T1 -----------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_t1_the_new_keys_are_there_and_empty(
    bodies: dict[str, dict[str, Any]], scenario: str, registrations: list[Registration]
) -> None:
    filled_lists = filled(registrations, "today_lists")
    note_filled = bool(filled(registrations, "note"))
    lines = 0
    for name, body in bodies[scenario].items():
        if name.startswith("today"):
            for key in TODAY_LISTS:
                assert key in body, (scenario, name, key)
                if key not in filled_lists:
                    assert body[key] == [], (scenario, name, key)
        for line in _directive_lines(body):
            assert NOTE in line, (scenario, name)
            if not note_filled:
                assert line[NOTE] is None, (scenario, name)
            lines += 1
    assert lines  # each scenario carries directive lines to check


def test_t1_the_scenarios_cover_the_three_paths(bodies: dict[str, dict[str, Any]]) -> None:
    assert bodies["authored"]["today"]["mode"] == "normal"
    assert bodies["unauthored"]["today"]["mode"] == "unconfirmed"
    after = bodies["after_exit"]
    assert after["exit"]["directives"] and after["exit_repeat"]["pending_directives"]
    assert after["today"]["mode"] == "emergency_frozen"


# --- SEAM-T2 -----------------------------------------------------------------------------


def test_t2_without_the_new_keys_every_body_is_the_pre_seam_one(
    bodies: dict[str, dict[str, Any]], registrations: list[Registration]
) -> None:
    """釐清二 E-6 第 3 點: sha256, registrations, dropped keys, deltas, exact equality."""
    assert golden_sha256() == GOLDEN_SHA256  # 1) the golden is the frozen one
    recorded = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert not _keys(recorded) & SEAM_KEYS  # the record predates the seam
    drop = dropped_keys(registrations, recorded)  # 3)
    assert drop >= CLOCK_KEYS | SEAM_KEYS
    expected = expected_bodies(recorded, registrations)  # 4)
    now = without(bodies, drop)
    assert now == expected  # 5)


def test_t2_every_filled_entry_names_a_test_that_exists(
    registrations: list[Registration],
) -> None:
    """E-6 第 6 點: each ``filled`` entry points at an exact-value test."""
    for registration in registrations:
        for _, _, node in registration.filled_tests:
            file, _, name = node.partition("::")
            path = TESTS_ROOT.parent / file
            assert path.is_file(), node
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = {
                function.name
                for function in ast.walk(tree)
                if isinstance(function, ast.FunctionDef)
            }
            assert name.split("[")[0] in names, node


def test_t2_registration_files_are_one_per_owner_and_json() -> None:
    if APPROVED.is_dir():
        for path in APPROVED.iterdir():
            assert path.suffix == ".json" or path.name == ".gitkeep", path


def _registration(**changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {"owner": "x", "added_keys": [], "filled": [], "deltas": []}
    raw.update(changes)
    return raw


def _delta(**changes: Any) -> dict[str, Any]:
    delta: dict[str, Any] = {
        "id": "X-D1",
        "source": "ADR",
        "approval": "work/reviews/x.md",
        "scenario": "authored",
        "body": "today",
        "path": ["mode_label"],
        "op": "replace",
        "before": "正常",
        "after": "正常（改）",
    }
    delta.update(changes)
    return delta


def _insert(**changes: Any) -> dict[str, Any]:
    delta = _delta(scenario="after_exit", op="insert", **changes)
    del delta["before"]
    return delta


def _golden() -> Any:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_t2_registry_applies_a_valid_replace_and_insert() -> None:
    golden = _golden()
    before = golden["authored"]["today"]["mode_label"]
    warnings = golden["after_exit"]["today"]["warnings"]
    registration = parse_registration(
        "x.json",
        _registration(
            deltas=[
                _delta(before=before, after=before + "（改）"),
                _insert(id="X-D2", path=["warnings", len(warnings)]),
            ]
        ),
    )
    expected = expected_bodies(golden, [registration])
    assert expected["authored"]["today"]["mode_label"] == before + "（改）"
    assert expected["after_exit"]["today"]["warnings"][-1] == "正常（改）"
    assert golden == _golden()  # the golden itself is never touched


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (_registration(deltas=[_delta(before="not the golden value")]), "before does not match"),
        (_registration(deltas=[_delta(after="正常")]), "empty delta"),
        (_registration(deltas=[_delta(path=["*"])]), "path element"),
        (_registration(deltas=[_delta(path=["warnings"], before=[], after=["x"])]), "whole-list"),
        (_registration(deltas=[_delta(op="move")]), "op"),
        (_registration(deltas=[_delta(op="insert")]), "keys"),
        (_registration(deltas=[_insert(path=["warnings", 99])]), "insert index"),
        (_registration(owner="y"), "one file per owner"),
        (
            _registration(
                filled=[
                    {"kind": "today_lists", "name": "directives", "source": "s", "test": "t::u"}
                ]
            ),
            "filled name",
        ),
    ],
)
def test_t2_registry_rejects_what_e6_forbids(raw: dict[str, Any], message: str) -> None:
    with pytest.raises(RegistryError, match=message):
        expected_bodies(_golden(), [parse_registration("x.json", raw)])


def test_t2_registry_rejects_an_added_key_the_golden_already_has() -> None:
    registration = parse_registration(
        "x.json", _registration(added_keys=[{"key": "title", "source": "ADR"}])
    )
    with pytest.raises(RegistryError, match="already in the golden"):
        dropped_keys([registration], _golden())


def test_t2_registry_rejects_a_message_that_is_not_appended_to() -> None:
    golden = _golden()
    message = golden["after_exit"]["exit"]["message"]
    raw = _registration(
        deltas=[
            _delta(scenario="after_exit", body="exit", path=["message"], before=message, after="x")
        ]
    )
    with pytest.raises(RegistryError, match="appended"):
        expected_bodies(golden, [parse_registration("x.json", raw)])


def test_t2_registry_rejects_two_owners_on_one_list_and_duplicate_ids(tmp_path: Path) -> None:
    golden = _golden()
    warnings = golden["after_exit"]["today"]["warnings"]
    insert = _insert(path=["warnings", len(warnings)])
    first = parse_registration("x.json", _registration(deltas=[insert]))
    second = parse_registration("y.json", _registration(owner="y", deltas=[{**insert, "id": "Y"}]))
    with pytest.raises(RegistryError, match="shares"):
        expected_bodies(golden, [first, second])

    for owner in ("x", "y"):
        (tmp_path / f"{owner}.json").write_text(
            json.dumps(_registration(owner=owner, deltas=[insert])), encoding="utf-8"
        )
    with pytest.raises(RegistryError, match="duplicate delta id"):
        load_registrations(tmp_path)


def test_t2_an_empty_registry_is_the_original_comparison() -> None:
    """Equivalence with the pre-registry T2 when nothing is registered (E-10 第 4 點)."""
    golden = _golden()
    assert expected_bodies(golden, []) == golden
    assert dropped_keys([], golden) == CLOCK_KEYS | SEAM_KEYS


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


# --- SEAM-T3 -----------------------------------------------------------------------------


def _spied(
    store: PlaybookStore, service: PlaybookService, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    calls: list[str] = []
    real_read = store.read_in_flight
    real_settle = service._settle_pending

    def read() -> InFlightRead:
        calls.append("read_in_flight")
        return real_read()

    def settle(as_of: date) -> SettlementRun:
        calls.append("_settle_pending")
        return real_settle(as_of)

    monkeypatch.setattr(store, "read_in_flight", read)
    monkeypatch.setattr(service, "_settle_pending", settle)
    return calls


def test_t3_authored_reads_once_after_the_settlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = clocked_desk(tmp_path / "playbook.db")
    log_like_before_n172a(desk.store, [buy_line(execution_date=TUESDAY)])
    calls = _spied(desk.store, desk.service, monkeypatch)
    real_list = desk.store.list_batches

    def list_batches() -> Any:
        calls.append("list_batches")
        return real_list()

    monkeypatch.setattr(desk.store, "list_batches", list_batches)

    desk.service.evaluate_today(today=TUESDAY)
    desk.service.evaluate_today(today=TUESDAY)

    assert calls.count("read_in_flight") == 2  # once per call
    first = calls[: calls.index("_settle_pending", 1)]
    assert first.count("read_in_flight") == 1
    assert first.index("_settle_pending") < first.index("read_in_flight")
    assert first.index("read_in_flight") < first.index("list_batches")


def test_t3_unauthored_reads_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    desk = clocked_desk(tmp_path / "playbook.db", seed=False)
    calls = _spied(desk.store, desk.service, monkeypatch)

    evaluation = desk.service.evaluate_today(today=TUESDAY)

    assert evaluation.mode == "unconfirmed"
    assert calls == ["read_in_flight"]  # and no settlement on this path


# --- SEAM-T4 -----------------------------------------------------------------------------


def _traced(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    statements: list[str] = []
    real_connect = sqlite3.connect

    def tracing(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracing)
    return statements


def test_t4_the_read_is_begin_selects_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stays green once N-171 and N-168 fill their reads in."""
    desk = clocked_desk(tmp_path / "playbook.db")
    hold(desk.store, "2330", 2)
    log_like_before_n172a(desk.store, [buy_line(execution_date=WEDNESDAY)])
    desk.service.emergency_exit(today=TUESDAY)
    statements = _traced(monkeypatch)

    read = desk.store.read_in_flight()

    assert statements[0] == "BEGIN" and statements[-1] == "COMMIT"
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements[1:-1])
    # 釐清二 E-6 第 6 點: a part no owner registered as filled is still the stub's.
    in_flight = filled(load_registrations(), "in_flight")
    defaults: dict[str, Any] = {"exits": PendingExitRead, "entries": EntryBeforeExitRead}
    assert set(defaults) == set(InFlightRead._fields)
    for name, default in defaults.items():
        if name not in in_flight:
            assert getattr(read, name) == default(), name


def test_t4_a_failing_read_rolls_back_and_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.playbook import store as store_module

    desk = clocked_desk(tmp_path / "playbook.db")
    statements = _traced(monkeypatch)

    def broken(conn: sqlite3.Connection) -> PendingExitRead:
        raise sqlite3.OperationalError("boom")

    monkeypatch.setattr(store_module, "_read_pending_exits", broken)

    with pytest.raises(sqlite3.OperationalError, match="boom"):
        desk.store.read_in_flight()
    assert statements == ["BEGIN", "ROLLBACK"]


# --- SEAM-T5 -----------------------------------------------------------------------------


def _directive_line_builds(tree: ast.AST) -> list[ast.Call]:
    """Calls of ``DirectiveLine(...)`` or of any ``DirectiveLine.<method>(...)``."""

    def names_it(node: ast.expr) -> bool:
        return (isinstance(node, ast.Name) and node.id == "DirectiveLine") or (
            isinstance(node, ast.Attribute) and node.attr == "DirectiveLine"
        )

    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            names_it(node.func)
            or (isinstance(node.func, ast.Attribute) and names_it(node.func.value))
        )
    ]


def test_t5_every_directive_line_is_built_in_lines() -> None:
    sites: list[tuple[str, str]] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for call in _directive_line_builds(tree):
            owner: ast.AST = call
            while owner in parents and not isinstance(
                owner, ast.FunctionDef | ast.AsyncFunctionDef
            ):
                owner = parents[owner]
            name = owner.name if isinstance(owner, ast.FunctionDef | ast.AsyncFunctionDef) else ""
            sites.append((path.relative_to(APP_ROOT).as_posix(), name))
    assert sites == [("api/playbook.py", "_lines")]


def test_t5_labeled_batches_is_keyword_only_and_required() -> None:
    parameter = inspect.signature(api_module._lines).parameters["labeled_batches"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        api_module._lines([], ())  # type: ignore[call-arg]


def test_t5_the_line_is_never_touched_and_the_note_stays_null() -> None:
    labeled = (LabeledBatch(symbol="2330", batch_no=1, entry_date=TUESDAY),)
    sell = buy_line().model_copy(update={"action": "sell", "rule_id": "S1"})
    (line,) = api_module._lines([sell], labeled_batches=labeled)
    assert line.line == wording.directive_line(sell)
    # 釐清二 E-6 第 6 點 (N-168): the note is the W-B2L rule's, never part of ``line``.
    assert line.entry_before_exit_note == wording.ENTRY_BEFORE_EXIT_NOTE.format(
        entry_date=TUESDAY.isoformat()
    )
    unlabeled = sell.model_copy(update={"batch_no": 2})
    (other,) = api_module._lines([unlabeled], labeled_batches=labeled)
    assert other.entry_before_exit_note is None


def test_t5_the_service_fields_default_to_empty() -> None:
    for name in (*TODAY_LISTS, "labeled_batches"):
        assert PlaybookEvaluation.model_fields[name].is_required() is False
    assert api_module.DirectiveLine.model_fields[NOTE].default is None


# --- SEAM-T6 -----------------------------------------------------------------------------


def test_t6_settle_pending_is_the_result_of_settle_pending_run(tmp_path: Path) -> None:
    """Two identical books: the public method on one, the run on the other."""
    saturday = date(2026, 8, 15)  # after the last seeded bar: stays unsettled
    results = []
    for name in ("public", "run"):
        desk = clocked_desk(tmp_path / f"{name}.db")
        log_like_before_n172a(
            desk.store,
            [
                buy_line(execution_date=WEDNESDAY),
                buy_line(batch_no=2, execution_date=saturday),
                buy_line(batch_no=3, execution_date=date(2026, 8, 20)),  # not due
            ],
        )
        if name == "public":
            results.append(desk.service.settle_pending(today=saturday))
        else:
            run = desk.service._settle_pending(saturday)
            assert set(run.loaded) == {"2330"}  # what the settlement itself loaded
            results.append(run.result)
    public, run_result = results
    assert public == run_result
    assert (public.executed, len(public.unsettled)) == (1, 1)


def test_t6_nothing_due_loads_nothing(tmp_path: Path) -> None:
    desk = clocked_desk(tmp_path / "playbook.db")

    run = desk.service._settle_pending(TUESDAY)

    assert run.loaded == {}
    assert run.result == desk.service.settle_pending(today=TUESDAY)


# --- SEAM-T7 -----------------------------------------------------------------------------


def test_t7_the_unauthored_read_leaves_no_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """題 9 零痕跡 with the new read: no load, no settlement, no write."""
    desk = clocked_desk(tmp_path / "playbook.db", seed=False)
    desk.store.ensure_batches(["2330"], batches_per_target=3)
    hold(desk.store, "2330", 1)
    statements = _traced(monkeypatch)

    evaluation = desk.service.evaluate_today(today=TUESDAY)

    assert evaluation.mode == "unconfirmed"
    assert desk.prices.calls == [] and desk.index.calls == []
    assert evaluation.settlement is None
    writes = [
        sql
        for sql in statements
        if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE"))
    ]
    assert writes == []
