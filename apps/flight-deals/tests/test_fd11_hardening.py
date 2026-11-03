"""Stability and tech-debt fixes of FD-11 (ADR-0002 FD-11 Decisions 1-9, 11; C-83..C-90,
C-92)."""

from __future__ import annotations

import ast
import html
import importlib.metadata
import json
import logging
import random
import re
import sqlite3
import threading
import time
import tomllib
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from apscheduler.jobstores.base import JobLookupError
from fastapi.testclient import TestClient

import flight_deals
from flight_deals import cli
from flight_deals.app import assemble, create_app
from flight_deals.config import Config
from flight_deals.domain.dates import month_weekday_counts, range_pairs
from flight_deals.domain.messages import (
    BANNED_PHRASES,
    COMPARISON_NOT_FOUND,
    COMPARISON_PREFILL_MISSING,
    COMPARISON_SCHEDULER_OFF,
    EXPLORATION_NOT_FOUND,
    EXPLORATION_PREFILL_MISSING,
    EXPLORATION_SCHEDULER_OFF,
    EXPLORATION_TOO_MANY_CELLS,
    all_static_texts,
    exploration_too_many_cells,
)
from flight_deals.domain.models import ComparisonSpec, DatePair, ExplorationSpec
from flight_deals.domain.timeutil import to_utc_iso
from flight_deals.domain.validation import exploration_months
from flight_deals.domain.weekdays import ALL_WEEKDAYS
from flight_deals.services.commands import OFFSET_BOT_KEY, OFFSET_KEY, bot_id_of
from flight_deals.storage import db as db_module
from flight_deals.web import server
from tests.conftest import (
    CLIENT_HEADERS,
    FakeClock,
    FakeLock,
    FakeNotifier,
    Harness,
    ScriptedSource,
)
from tests.test_commands import BOT_ID, Bot, FakeInbox, bot_config, make_poller
from tests.test_comparison_service import TRIP
from tests.test_exploration_service import DECEMBER
from tests.test_telegram_setup import Console

APP_DIR = Path(__file__).resolve().parents[1]
SRC = APP_DIR / "src" / "flight_deals"
MIGRATIONS = SRC / "storage" / "migrations"


def table_count(harness: Harness, table: str) -> int:
    with harness.repo.db.connect() as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def all_counts(harness: Harness) -> dict[str, int]:
    with harness.repo.db.connect() as conn:
        tables = [
            str(r[0])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
    return {t: table_count(harness, t) for t in tables}


def set_limit(harness: Harness, limit: int, reserve: int = 0) -> None:
    errors = harness.services.settings.update(
        {"global_hourly_query_limit": str(limit), "exploration_reserve_for_scans": str(reserve)}
    )
    assert errors == {}


def comparison_spec(*destinations: str, origin: str = "TPE") -> ComparisonSpec:
    return ComparisonSpec(origin, tuple(destinations), "one_way", date(2026, 12, 10), None, None)


def exploration_spec() -> ExplorationSpec:
    return ExplorationSpec("TPE", "NRT", "round_trip", 2026, 12, 5, None)


# ---- W1: queries_used_since uses the started indexes (C-83) ----------------------------

# The FD-10 statement, kept verbatim as the reference for the equivalence tests.
OLD_QUERIES_USED_SQL = (
    "SELECT (SELECT COALESCE(SUM(queries_used), 0) FROM scan_run"
    "  WHERE started_at >= ?)"
    " + (SELECT COALESCE(SUM(queries_used), 0) FROM exploration"
    "  WHERE COALESCE(started_at, created_at) >= ?)"
    " + (SELECT COALESCE(SUM(queries_used), 0) FROM comparison"
    "  WHERE COALESCE(started_at, created_at) >= ?) AS n"
)


def old_queries_used(harness: Harness, since: datetime) -> int:
    stamp = to_utc_iso(since)
    with harness.repo.db.connect() as conn:
        row = conn.execute(OLD_QUERIES_USED_SQL, (stamp, stamp, stamp)).fetchone()
    return int(row[0])


def _stamp(value: datetime | None) -> str | None:
    return None if value is None else to_utc_iso(value)


def add_exploration(
    harness: Harness, created: datetime, started: datetime | None, used: int
) -> int:
    pairs = [DatePair(date(2026, 12, 1))]
    exploration_id = int(harness.repo.insert_exploration(exploration_spec(), pairs, created))
    with harness.repo.db.connect() as conn:
        conn.execute(
            "UPDATE exploration SET created_at = ?, started_at = ?, queries_used = ? WHERE id = ?",
            (to_utc_iso(created), _stamp(started), used, exploration_id),
        )
    return exploration_id


def add_comparison(harness: Harness, created: datetime, started: datetime | None, used: int) -> int:
    comparison_id = int(harness.repo.insert_comparison(comparison_spec("NRT", "KIX"), created))
    with harness.repo.db.connect() as conn:
        conn.execute(
            "UPDATE comparison SET created_at = ?, started_at = ?, queries_used = ? WHERE id = ?",
            (to_utc_iso(created), _stamp(started), used, comparison_id),
        )
    return comparison_id


@pytest.fixture
def statements(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every statement sent through Database connections (PRAGMAs left out)."""
    seen: list[str] = []
    real_open = db_module.Database._open

    def record(sql: str) -> None:
        if not sql.lstrip().upper().startswith("PRAGMA"):
            seen.append(sql)

    def traced(self: db_module.Database) -> sqlite3.Connection:
        conn = real_open(self)
        conn.set_trace_callback(record)
        return conn

    monkeypatch.setattr(db_module.Database, "_open", traced)
    return seen


def test_no_new_migration_and_schema_stays_8(harness: Harness) -> None:  # C-83
    # C-83 covered the FD-11 batch only; FD-12 adds 0009 (ADR-0002 FD-12, C-95).
    names = sorted(p.name[:4] for p in MIGRATIONS.glob("*.sql"))
    assert names == [f"{n:04d}" for n in range(1, 10)]
    assert harness.repo.db.schema_version() == 9


def test_queries_used_since_is_one_statement_without_coalesce(
    harness: Harness, statements: list[str]
) -> None:  # C-83
    source = (SRC / "storage" / "repository.py").read_text(encoding="utf-8")
    assert "COALESCE(started_at" not in source
    statements.clear()
    harness.repo.queries_used_since(harness.clock() - timedelta(hours=1))
    assert len(statements) == 1 and statements[0].lstrip().startswith("SELECT")


@pytest.mark.parametrize(
    ("created", "started", "counted"),
    [
        (0, None, True),  # started NULL, created == since
        (5, None, True),  # started NULL, created > since
        (-5, None, False),  # started NULL, created < since
        (-5, 0, True),  # started == since, created < since
        (-5, 5, True),  # started > since, created < since
        (5, -5, False),  # started < since, created >= since: not counted
        (0, -1, False),  # started < since, created == since: not counted
    ],
)
def test_four_boundaries_match_the_old_sql(
    harness: Harness, created: int, started: int | None, counted: bool
) -> None:  # C-83
    since = harness.clock() - timedelta(hours=1)
    created_at = since + timedelta(minutes=created)
    started_at = None if started is None else since + timedelta(minutes=started)
    add_exploration(harness, created_at, started_at, 3)
    add_comparison(harness, created_at, started_at, 5)
    expected = 8 if counted else 0
    assert harness.repo.queries_used_since(since) == expected == old_queries_used(harness, since)


def test_seeded_random_rows_match_the_old_sql(harness: Harness) -> None:  # C-83
    rng = random.Random(20261101)
    base = harness.clock()
    for _ in range(40):
        for add in (add_exploration, add_comparison):
            created = base - timedelta(minutes=rng.randint(0, 4 * 24 * 60))
            started = (
                None if rng.random() < 0.3 else created + timedelta(minutes=rng.randint(-120, 600))
            )
            add(harness, created, started, rng.randint(0, 31))
    sinces = [base - timedelta(minutes=rng.randint(0, 5 * 24 * 60)) for _ in range(25)]
    totals = set()
    for since in [*sinces, base, base - timedelta(days=30)]:
        new = harness.repo.queries_used_since(since)
        assert new == old_queries_used(harness, since)
        totals.add(new)
    assert len(totals) > 10  # the data really spreads across the boundaries


def _plan_subtrees(rows: list[tuple[int, int, str]]) -> list[list[str]]:
    """Detail lines under each ``SCALAR SUBQUERY`` node of an EXPLAIN QUERY PLAN."""
    children: dict[int, list[tuple[int, str]]] = {}
    for node, parent, detail in rows:
        children.setdefault(parent, []).append((node, detail))

    def below(node: int) -> list[str]:
        out: list[str] = []
        for child, detail in children.get(node, []):
            out.append(detail)
            out.extend(below(child))
        return out

    return [below(node) for node, _parent, detail in rows if "SCALAR SUBQUERY" in detail]


def test_query_plan_uses_both_started_indexes(
    harness: Harness, statements: list[str]
) -> None:  # C-83
    statements.clear()
    since = harness.clock() - timedelta(hours=1)
    harness.repo.queries_used_since(since)
    (sql,) = statements
    params = (to_utc_iso(since),) * sql.count("?")
    with harness.repo.db.connect() as conn:
        rows = [
            (int(r[0]), int(r[1]), str(r[3]))
            for r in conn.execute(f"EXPLAIN QUERY PLAN {sql}", params)
        ]
    details = [d for _n, _p, d in rows]
    assert not any(d.startswith(("SCAN exploration", "SCAN comparison")) for d in details)
    subtrees = _plan_subtrees(rows)
    for table in ("exploration", "comparison"):
        (tree,) = [t for t in subtrees if any(f" {table} " in d for d in t)]
        assert "MULTI-INDEX OR" in tree, tree
        searches = [d for d in tree if f" {table} " in d]
        assert len(searches) == 2, tree
        assert all(f"USING INDEX idx_{table}_started" in d for d in searches), tree


# ---- W2: insert_comparison guards the stored code shape (C-86) --------------------------


@pytest.mark.parametrize(
    "spec",
    [
        comparison_spec("A,B", "CCC"),
        comparison_spec("TOKY", "CCC"),
        comparison_spec("nrt", "KIX"),
        comparison_spec("ＮＲＴ", "KIX"),
        comparison_spec("NRT", "NRT"),
        comparison_spec("NRT"),
        comparison_spec("NRT", "KIX", "ICN", "BKK", "SIN", "HKG", "MNL", "CTS", "OKA"),
        comparison_spec("NRT", "KIX", origin="TP"),
        comparison_spec("NRT", "KIX", origin="tpe"),
        comparison_spec("NRT", "KIX", origin="T,E"),
        comparison_spec("NRT", "KIX", origin="ＴＰＥ"),
    ],
)
def test_insert_comparison_rejects_bad_codes_and_writes_nothing(
    harness: Harness, spec: ComparisonSpec
) -> None:  # C-86
    with pytest.raises(ValueError):
        harness.repo.insert_comparison(spec, harness.clock())
    assert table_count(harness, "comparison") == 0
    assert table_count(harness, "comparison_cell") == 0


def test_insert_comparison_still_accepts_two_and_eight(harness: Harness) -> None:  # C-86
    harness.repo.insert_comparison(comparison_spec("NRT", "KIX"), harness.clock())
    eight = ("NRT", "KIX", "ICN", "BKK", "SIN", "HKG", "MNL", "CTS")
    harness.repo.insert_comparison(comparison_spec(*eight), harness.clock())
    assert table_count(harness, "comparison") == 2
    assert table_count(harness, "comparison_cell") == 10


@pytest.mark.parametrize(
    "overrides",
    [{"destinations": ["AAAABBB", "NRT"]}, {"depart_date": "2026-99-99"}],
)
def test_api_bad_shapes_are_422_and_write_nothing(
    harness: Harness, overrides: dict[str, Any]
) -> None:  # C-86
    before = all_counts(harness)
    response = harness.client.post(
        "/api/comparisons", json={**TRIP, **overrides}, headers=CLIENT_HEADERS
    )
    assert response.status_code == 422
    assert all_counts(harness) == before


def test_insert_comparison_check_does_not_use_assert() -> None:  # C-86
    tree = ast.parse((SRC / "storage" / "repository.py").read_text(encoding="utf-8"))
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in ("insert_comparison", "_check_comparison_places")
    ]
    assert sorted(f.name for f in functions) == ["_check_comparison_places", "insert_comparison"]
    for function in functions:
        assert not any(isinstance(n, ast.Assert) for n in ast.walk(function))


# ---- W3: ASCII-only digits (C-85) ----------------------------------------------------------


def _method_target(node: ast.AST, method: str) -> str | None:
    """``ast.dump`` of ``x`` when ``node`` is ``x.<method>()``."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
    ):
        return ast.dump(node.func.value)
    return None


def _ascii_guarded(call: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    """The call sits in an ``and`` chain after ``<same name>.isascii()``."""
    target = _method_target(call, "isdecimal") or _method_target(call, "isdigit")
    node: ast.AST = call
    while node in parents:
        parent = parents[node]
        if isinstance(parent, ast.BoolOp) and isinstance(parent.op, ast.And):
            earlier = parent.values[: parent.values.index(node)]  # type: ignore[arg-type]
            return any(_method_target(e, "isascii") == target for e in earlier)
        node = parent
    return False


def test_every_digit_check_is_ascii_guarded() -> None:  # C-85
    checked = 0
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _method_target(node, "isdecimal") or _method_target(node, "isdigit"):
                assert _ascii_guarded(node, parents), f"{path.name}:{node.lineno}"
                checked += 1
    assert checked >= 5


@pytest.mark.parametrize("text", ["１", "١", "²", " ١ "])
def test_comparison_prefill_ignores_non_ascii_ids(harness: Harness, text: str) -> None:  # C-85
    comparison_id = harness.repo.insert_comparison(comparison_spec("NRT", "KIX"), harness.clock())
    assert comparison_id == 1
    views = harness.services.comparison_views
    base = {"marker": True}
    values, note, _ = views.watch_prefill(base, text, "NRT")
    assert values is base and note == COMPARISON_PREFILL_MISSING
    assert views._record(text) is None and views._record("1") is not None
    assert views.watch_prefill(base, "1", "NRT")[1] != COMPARISON_PREFILL_MISSING


@pytest.mark.parametrize("text", ["１", "١", "²", "１２３", "١٢٣"])
def test_exploration_prefill_ignores_non_ascii_ids(harness: Harness, text: str) -> None:  # C-85
    exploration_id = add_exploration(harness, harness.clock(), None, 0)
    assert exploration_id == 1
    views = harness.services.exploration_views
    base = {"marker": True}
    values, note, _ = views.watch_prefill(base, text, "2026-12-01", "fixed")
    assert values is base and note == EXPLORATION_PREFILL_MISSING
    assert views._record(text) is None and views._record("1") is not None


def test_bot_id_of_needs_ascii_digits() -> None:  # C-85
    assert bot_id_of("123456:abc") == "123456"
    assert bot_id_of("²:abc") == bot_id_of("１２３:abc") == bot_id_of("١٢٣:abc") == "0"


@pytest.fixture
def tg(
    tmp_path: Path, clock: FakeClock, source: ScriptedSource, notifier: FakeNotifier
) -> Iterator[Bot]:
    """Same assembly as ``tests.test_commands.bot``: Telegram commands on a fake inbox."""
    inbox = FakeInbox()
    app = create_app(
        bot_config(tmp_path),
        sources=[source],
        notifier=notifier,
        clock=clock,
        start_scheduler=False,
        inbox=inbox,
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield Bot(app.state.assembly, client, clock, source, notifier, inbox)


@pytest.mark.parametrize(("raw", "expected"), [("²", None), ("９", None), ("١٢", None), ("7", 7)])
def test_load_offset_never_raises_on_unicode_digits(
    tg: Bot, raw: str, expected: int | None
) -> None:  # C-85
    tg.repo.save_state({OFFSET_KEY: raw, OFFSET_BOT_KEY: BOT_ID}, tg.clock.now)
    assert make_poller(tg)._load_offset() == expected


@pytest.mark.parametrize("bad", ["²", "２", "١"])
def test_wizard_choice_asks_again_on_unicode_digits(bad: str) -> None:  # C-85
    chats = [
        SimpleNamespace(title="Kevin", chat_type="private", chat_id=556677),
        SimpleNamespace(title="群", chat_type="group", chat_id=-42),
    ]
    console = Console(answers=[bad, "2"])
    assert cli._choose_chat(console.io(), chats) is chats[1]
    assert console.err == ["編號不正確，請重新輸入。"]


def test_validation_integer_pattern_is_unchanged() -> None:  # C-85
    source = (SRC / "domain" / "validation.py").read_text(encoding="utf-8")
    assert re.search(r"^_INTEGER = ", source, re.MULTILINE)


# ---- W4: scheduling and its compensation inside the create lock (C-87) -----------------

PAYLOADS: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "comparison": (dict(TRIP), {**TRIP, "destinations": ["BKK", "SIN"]}),
    "exploration": (dict(DECEMBER), {**DECEMBER, "destination": "KIX"}),
}
SCHEDULER_OFF = {"comparison": COMPARISON_SCHEDULER_OFF, "exploration": EXPLORATION_SCHEDULER_OFF}


def _row(harness: Harness, kind: str, row_id: int) -> Any:
    return getattr(harness.repo, f"get_{kind}")(row_id)


def _active(harness: Harness, kind: str) -> Any:
    return getattr(harness.repo, f"active_{kind}")()


@pytest.mark.parametrize("kind", ["comparison", "exploration"])
def test_failed_schedule_is_compensated_inside_the_lock(harness: Harness, kind: str) -> None:
    set_limit(harness, 500)  # C-87
    service = getattr(harness.services, kind)
    service.hooks.scheduler_running = lambda: True
    first_payload, second_payload = PAYLOADS[kind]
    seen: dict[str, Any] = {}
    scheduled: list[int] = []
    results: dict[str, Any] = {}
    other = threading.Thread(
        target=lambda: results.update(second=service.create(second_payload)), daemon=True
    )

    def hook(row_id: int) -> None:
        if "first" in seen:  # the second request's job: scheduled normally
            seen["active_seen_by_second"] = _active(harness, kind).id
            scheduled.append(row_id)
            return
        seen["first"] = row_id
        seen["locked"] = service._create_lock.locked()
        other.start()
        other.join(0.2)
        seen["second_waiting"] = other.is_alive()
        raise RuntimeError("scheduler went away")

    service.hooks.schedule = hook
    used_before = harness.repo.queries_used_since(harness.clock() - timedelta(hours=1))
    result = service.create(first_payload)
    other.join(5)
    assert not other.is_alive()
    assert result.status == "scheduler_off" and result.message == SCHEDULER_OFF[kind]
    assert seen["locked"] is True and seen["second_waiting"] is True
    failed = _row(harness, kind, seen["first"])
    assert failed.status == "failed" and failed.error_summary == SCHEDULER_OFF[kind]
    second = results["second"]
    second_id = getattr(second, f"{kind}_id")
    assert second.status == "created" and second_id != seen["first"]
    assert scheduled == [second_id] and seen["active_seen_by_second"] == second_id
    assert harness.repo.queries_used_since(harness.clock() - timedelta(hours=1)) == used_before
    assert harness.source.calls == []
    assert not service._create_lock.locked()


@pytest.mark.parametrize("kind", ["comparison", "exploration"])
def test_failed_schedule_leaves_no_active_row(harness: Harness, kind: str) -> None:  # C-87
    service = getattr(harness.services, kind)
    service.hooks.scheduler_running = lambda: True
    locked: list[bool] = []

    def hook(_row_id: int) -> None:
        locked.append(service._create_lock.locked())
        raise RuntimeError("scheduler went away")

    service.hooks.schedule = hook
    used_before = harness.repo.queries_used_since(harness.clock() - timedelta(hours=1))
    result = service.create(PAYLOADS[kind][0])
    assert result.status == "scheduler_off" and locked == [True]
    assert _active(harness, kind) is None
    (row,) = getattr(harness.repo, f"list_{kind}s_since")(harness.clock() - timedelta(days=1))
    assert row.status == "failed" and row.error_summary == SCHEDULER_OFF[kind]
    assert harness.repo.queries_used_since(harness.clock() - timedelta(hours=1)) == used_before
    assert harness.source.calls == []


@pytest.mark.parametrize("kind", ["comparison", "exploration"])
def test_compensation_failure_is_logged_and_still_scheduler_off(
    harness: Harness,
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:  # C-87
    service = getattr(harness.services, kind)
    service.hooks.scheduler_running = lambda: True

    def schedule_fails(_row_id: int) -> None:
        raise RuntimeError("scheduler went away")

    def finish_fails(*_args: Any, **_kwargs: Any) -> None:
        raise sqlite3.OperationalError("database is locked")

    service.hooks.schedule = schedule_fails
    monkeypatch.setattr(service._repo, f"finish_{kind}", finish_fails)
    with caplog.at_level(logging.ERROR):
        result = service.create(PAYLOADS[kind][0])
    assert result.status == "scheduler_off" and result.message == SCHEDULER_OFF[kind]
    assert "could not be marked failed" in caplog.text
    assert not service._create_lock.locked()


# ---- W5: path ids beyond SQLite's range are 404 (C-84) ----------------------------------

OUT_OF_RANGE = [2**63, 10**30, -(2**63) - 1, 2**63 - 1, 0]
WRITE_METHODS = {"POST", "PUT", "DELETE"}
# A valid body for every write route, so in-range ids reach the "not found" branch.
WRITE_BODY = {"enabled": True}
WATCH_PAGE_MISSING = "找不到此監看，可能已被刪除。"
WATCH_API_MISSING = "找不到此監看"


def id_routes(app: Any) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if "_id}" in path:
            for method in sorted(set(getattr(route, "methods", None) or ()) - {"HEAD"}):
                found.append((method, path))
    return found


def _url(path: str, value: object) -> str:
    return re.sub(r"\{[a-z_]+_id\}", str(value), path)


def _missing_text(path: str, api: bool) -> str:
    if "/comparisons/" in path:
        return COMPARISON_NOT_FOUND
    if "/explorations/" in path:
        return EXPLORATION_NOT_FOUND
    return WATCH_API_MISSING if api else WATCH_PAGE_MISSING


def test_max_row_id_is_defined_once() -> None:  # C-84
    hits = [
        path
        for path in SRC.rglob("*.py")
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.match(r"\s*MAX_ROW_ID\s*=", line)
    ]
    assert hits == [SRC / "web" / "server.py"]
    assert server.MAX_ROW_ID == 2**63 - 1


def test_every_id_route_is_covered(harness: Harness) -> None:  # C-84
    routes = id_routes(harness.client.app)
    assert len(routes) == 11
    source = (SRC / "web" / "server.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    handlers = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(d, ast.Call)
            and d.args
            and isinstance(d.args[0], ast.Constant)
            and "_id}" in str(d.args[0].value)
            for d in node.decorator_list
        )
    ]
    assert len(handlers) == 11
    for handler in handlers:  # the bound check is the first statement
        first = handler.body[0]
        assert isinstance(first, ast.If) and "_row_id_ok" in ast.unparse(first.test), handler.name


@pytest.mark.parametrize("value", OUT_OF_RANGE)
def test_out_of_range_ids_are_404_on_every_route(harness: Harness, value: int) -> None:  # C-84
    before = all_counts(harness)
    for method, path in id_routes(harness.client.app):
        api = path.startswith("/api/")
        write = method in WRITE_METHODS
        response = harness.client.request(
            method,
            _url(path, value),
            headers=CLIENT_HEADERS if write else None,
            json=WRITE_BODY if write and method != "DELETE" else None,
        )
        where = f"{method} {path} {value}"
        assert response.status_code == 404, where
        message = _missing_text(path, api)
        if api:
            assert response.json() == {"ok": False, "errors": {"_": message}}, where
            if not write:
                assert response.headers["cache-control"] == "no-store", where
        else:
            assert message in response.text, where
    assert all_counts(harness) == before


@pytest.mark.parametrize("value", [2**63, 10**30])
def test_out_of_range_writes_without_header_stay_403(harness: Harness, value: int) -> None:
    for method, path in id_routes(harness.client.app):  # C-84
        if method in WRITE_METHODS:
            response = harness.client.request(method, _url(path, value), json={})
            assert response.status_code == 403, f"{method} {path}"


def test_non_integer_ids_stay_422(harness: Harness) -> None:  # C-84
    for method, path in id_routes(harness.client.app):
        write = method in WRITE_METHODS
        response = harness.client.request(
            method,
            _url(path, "abc"),
            headers=CLIENT_HEADERS if write else None,
            json=WRITE_BODY if write and method != "DELETE" else None,
        )
        assert response.status_code == 422, f"{method} {path}"


def test_largest_id_still_reaches_the_service(harness: Harness) -> None:  # C-84
    assert server._row_id_ok(1) and server._row_id_ok(2**63 - 1)
    assert not server._row_id_ok(0) and not server._row_id_ok(2**63)
    watch_id = harness.create_watch()
    assert harness.client.get(f"/watches/{watch_id}").status_code == 200


# ---- W6: estimate per stay length equals the server's cell count (C-88) ----------------

TODAYS = [date(2026, 10, 25), date(2026, 11, 30), date(2026, 12, 31), date(2027, 1, 31)]
TODAYS.append(date(2028, 2, 29))
FIXED_WEEKDAYS: list[tuple[int, ...]] = [ALL_WEEKDAYS, (4,), (4, 5), (0, 6)]


def _weekday_sets() -> list[tuple[int, ...]]:
    rng = random.Random(1101)
    extra = [tuple(sorted(rng.sample(range(7), rng.randint(1, 7)))) for _ in range(20)]
    return FIXED_WEEKDAYS + extra


def _at(harness: Harness, today: date) -> None:
    # 04:00 UTC is noon in Asia/Taipei: the same calendar day.
    harness.clock.now = datetime(today.year, today.month, today.day, 4, tzinfo=UTC)


def _js_estimate(
    quota: dict[str, Any],
    months: list[str],
    trip_type: str,
    trip_days: int | None,
    weekdays: tuple[int, ...],
) -> int:
    """What app.js adds up: the by-trip row for a round trip of 1-30 days when the month
    has one, the plain row otherwise."""
    by_trip = quota["weekday_counts_by_trip"]
    total = 0
    for month in months:
        row = quota["weekday_counts"][month]
        if (
            trip_type == "round_trip"
            and trip_days is not None
            and 1 <= trip_days <= 30
            and month in by_trip
        ):
            row = by_trip[month][str(trip_days)]
        total += sum(row[w] for w in weekdays)
    return total


def test_none_trip_days_is_the_fd10_count() -> None:  # C-88
    for today in TODAYS:
        for year, month in exploration_months(today):
            plain = month_weekday_counts(year, month, today)
            assert month_weekday_counts(year, month, today, None) == plain
            assert month_weekday_counts(year, month, today, trip_days=None) == plain


@pytest.mark.parametrize("today", TODAYS)
def test_by_trip_table_shape(harness: Harness, today: date) -> None:  # C-88
    _at(harness, today)
    quota = harness.services.exploration_views.explore_page()["quota"]
    base, by_trip = quota["weekday_counts"], quota["weekday_counts_by_trip"]
    assert len(by_trip) <= 2 and set(by_trip) <= set(base)
    for key in base:
        year, month = int(key[:4]), int(key[5:])
        differs = list(month_weekday_counts(year, month, today, 30)) != base[key]
        assert (key in by_trip) == differs, key
    for rows in by_trip.values():
        assert list(rows) == [str(n) for n in range(1, 31)]
        assert all(len(row) == 7 for row in rows.values())


@pytest.mark.parametrize("today", TODAYS)
def test_estimate_equals_range_pairs(harness: Harness, today: date) -> None:  # C-88
    _at(harness, today)
    quota = harness.services.exploration_views.explore_page()["quota"]
    months = exploration_months(today)
    trips: list[tuple[str, int | None]] = [("one_way", None)]
    trips += [("round_trip", n) for n in range(1, 31)]
    weekday_sets = _weekday_sets()
    checked = 0
    for start in range(len(months)):
        for span in (1, 2, 3):
            chosen = months[start : start + span]
            if len(chosen) < span:
                continue
            (year, month), (end_year, end_month) = chosen[0], chosen[-1]
            keys = [f"{y:04d}-{m:02d}" for y, m in chosen]
            for trip_type, trip_days in trips:
                for weekdays in weekday_sets:
                    spec = ExplorationSpec(
                        "TPE",
                        "NRT",
                        trip_type,  # type: ignore[arg-type]
                        year,
                        month,
                        trip_days,
                        None,
                        end_year=end_year if span > 1 else None,
                        end_month=end_month if span > 1 else None,
                        depart_weekdays=weekdays,
                    )
                    expected = len(range_pairs(spec, today))
                    estimate = _js_estimate(quota, keys, trip_type, trip_days, weekdays)
                    assert estimate == expected, (today, keys, trip_type, trip_days, weekdays)
                    checked += 1
    assert checked > 20_000


def test_explore_page_carries_the_by_trip_table(harness: Harness) -> None:  # C-88
    page = harness.client.get("/explore").text
    match = re.search(r"data-weekday-counts-by-trip='([^']*)'", page)
    assert match is not None
    table = json.loads(html.unescape(match.group(1)))
    assert (
        table
        == harness.services.exploration_views.explore_page()["quota"]["weekday_counts_by_trip"]
    )
    assert list(table) == ["2027-09"]  # today 2026-10-25: only the last option month


def test_explore_page_stays_fast(harness: Harness) -> None:  # C-88
    views = harness.services.exploration_views
    views.explore_page()
    best = min(_timed(views.explore_page) for _ in range(5))
    assert best < 0.1, best


def _timed(call: Any) -> float:
    started = time.perf_counter()
    call()
    return time.perf_counter() - started


# ---- W7: over-limit message with the real numbers (C-89) --------------------------------


def test_too_many_cells_message_shape() -> None:  # C-89
    text = exploration_too_many_cells(32, 31)
    assert "32" in text and "31" in text and text.endswith(EXPLORATION_TOO_MANY_CELLS)
    assert exploration_too_many_cells(93, 31).endswith(EXPLORATION_TOO_MANY_CELLS)


def test_samples_are_static_texts_without_banned_phrases() -> None:  # C-89
    texts = all_static_texts()
    for sample in (exploration_too_many_cells(32, 31), exploration_too_many_cells(93, 31)):
        assert sample in texts
        assert not any(phrase in sample for phrase in BANNED_PHRASES)


def test_32_cells_rejected_with_numbers_31_allowed(harness: Harness) -> None:  # C-89
    set_limit(harness, 200)
    exploration = harness.services.exploration
    exploration.hooks.scheduler_running = lambda: True
    exploration.hooks.schedule = lambda _row_id: None
    no_friday = {"month": "2026-10", "month_to": "2026-11", "depart_weekdays": [0, 1, 2, 3, 5, 6]}
    over = harness.client.post(
        "/api/explorations", json={**DECEMBER, **no_friday}, headers=CLIENT_HEADERS
    )
    assert over.status_code == 422
    message = over.json()["errors"]["month_to"]
    assert "32" in message and "31" in message and message.endswith(EXPLORATION_TOO_MANY_CELLS)
    no_monday = {**no_friday, "depart_weekdays": [1, 2, 3, 4, 5, 6]}
    ok = harness.client.post(
        "/api/explorations", json={**DECEMBER, **no_monday}, headers=CLIENT_HEADERS
    )
    assert ok.status_code == 202


def test_limit_comes_from_max_cells(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness.services.exploration, "_max_cells", 20)  # C-89
    response = harness.client.post("/api/explorations", json=DECEMBER, headers=CLIENT_HEADERS)
    assert response.status_code == 422
    assert response.json()["errors"] == {"month_to": exploration_too_many_cells(31, 20)}


def test_over_limit_text_for_the_page_is_unchanged(harness: Harness) -> None:  # C-89
    data = harness.services.exploration_views.explore_page()
    assert data["over_limit_text"] == EXPLORATION_TOO_MANY_CELLS


# ---- W8: idempotent job removal (C-90) ----------------------------------------------------


def test_remove_job_if_present_is_the_only_removal() -> None:  # C-90
    scheduler_dir = SRC / "scheduler"
    definitions = [
        path
        for path in scheduler_dir.rglob("*.py")
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.match(r"\s*def _remove_job_if_present\(", line)
    ]
    assert definitions == [scheduler_dir / "jobs.py"]
    assert ".remove()" not in (scheduler_dir / "jobs.py").read_text(encoding="utf-8")


def test_target_test_runs_on_a_future_clock() -> None:  # C-90
    source = (APP_DIR / "tests" / "test_retention.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    (function,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "test_scheduler_jobs_and_next_run_time"
    ]
    body = ast.unparse(function)
    assert "FakeClock(datetime.now(UTC).replace(microsecond=0) + timedelta(days=1))" in body


def test_job_removal_tolerates_jobs_that_are_already_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-90
    clock = FakeClock(datetime.now(UTC).replace(microsecond=0) + timedelta(days=1))
    built = assemble(
        Config(db_path=tmp_path / "s.db"),
        sources=[ScriptedSource(clock)],
        notifier=FakeNotifier(),
        clock=clock,
    )
    scheduler = built.scheduler
    depart = clock().date() + timedelta(days=40)
    created = built.services.watches.create(
        {
            "destination": "NRT",
            "trip_type": "round_trip",
            "date_mode": "fixed",
            "depart_date": depart.isoformat(),
            "return_date": (depart + timedelta(days=5)).isoformat(),
            "budget": 12000,
        }
    )
    assert created.ok and created.watch_id is not None
    watch_id = created.watch_id
    try:
        scheduler.start(FakeLock(held=True))
        scheduler.trigger_command_scan(watch_id)
        assert any(job.id.startswith("watch:") for job in scheduler.scheduler.get_jobs())
        calls: list[str] = []

        def gone(job_id: str, jobstore: str | None = None) -> None:
            calls.append(job_id)
            raise JobLookupError(job_id)

        monkeypatch.setattr(scheduler.scheduler, "remove_job", gone)
        scheduler.on_watch_changed(watch_id)
        scheduler.on_watch_deleted(watch_id)
        scheduler.sync_all()
        scheduler.sync_all(startup=True)
        assert f"watch:{watch_id}" in calls and len(calls) >= 4
    finally:
        scheduler.shutdown()


# ---- version consistency (C-92) ------------------------------------------------------------


def test_version_is_consistent_everywhere() -> None:  # C-92
    pyproject = tomllib.loads((APP_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    changelog = (APP_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## \[([^\]]+)\]", changelog, re.MULTILINE)
    released = [h for h in headings if h.lower() != "unreleased"]
    assert released, headings
    versions = {
        importlib.metadata.version("flight-deals"),
        flight_deals.__version__,
        pyproject["project"]["version"],
        released[0],
    }
    assert versions == {"0.1.0"}


def test_version_is_not_shown_in_the_app() -> None:  # C-92
    for path in SRC.rglob("*"):
        if path.suffix not in (".py", ".html", ".js") or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if path == SRC / "__init__.py":
            assert text.count("__version__") == 1
            continue
        assert "__version__" not in text, path
        assert "metadata.version" not in text and "importlib.metadata" not in text, path
