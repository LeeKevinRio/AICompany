"""Flow, output-path and read-only tests of ``scripts/gap_check.py`` (supplement 8 point 5 (c)).

Every test runs on ``tmp_path`` worlds (:mod:`tests.gap_check_world`): a synthetic "main"
database with OHLCV values and other tables, a fake backend folder, a fake home, a fake git, a
synthetic calendar and a fake clock. The real ``<backend>/data/``, ``.env`` and the network are
never touched (an autouse guard turns any socket connect into a failing assertion).
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tests.gap_check_world import (
    BACKEND,
    HEAD,
    POISON,
    SCRIPT_PATH,
    FakeCalendar,
    World,
    load_script,
    main_db_state,
    make_world,
    write_main_db,
)

gc: Any = load_script()
UNEXPECTED: str = gc.UNEXPECTED
INTERRUPTED: str = gc.INTERRUPTED
STOPS: dict[str, str] = dict(gc.STOP_SENTENCES)
COPY_STOP = STOPS["copy_not_deleted"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    yield


def run(world: World, capsys: Any, **override: Any) -> tuple[int, list[str], str]:
    code = gc.main(world.args(), **world.seams(**override))
    captured = capsys.readouterr()
    return code, captured.out.splitlines(), captured.err


def values(lines: list[str]) -> dict[str, str]:
    return dict(line.split("=", 1) for line in lines if "=" in line)


def no_residue(world: World) -> None:
    assert not any(world.work_root.glob("*/copy")), "a copy is left"
    assert not list(world.work_root.glob("*/" + gc.PASTE_BACK_NAME)), "a paste-back is left"


def assert_closed(lines: list[str]) -> None:
    assert lines and all(gc.is_screen_line(line) and line.isascii() for line in lines), lines


def only_stop(world: World, capsys: Any, kind: str, **override: Any) -> None:
    code, lines, err = run(world, capsys, **override)
    assert (code, lines, err) == (3, [STOPS[kind]], "")
    assert world.calendar.urls == [] and not world.opened
    no_residue(world)


# --- the happy run -------------------------------------------------------------------------------


def test_the_happy_run_prints_the_whitelisted_lines_and_writes_the_same_file(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path)
    code, lines, err = run(world, capsys)
    assert (code, err) == (0, "")
    assert_closed(lines)
    shown = values(lines)
    assert lines[0] == "gap_check version=1" and lines[-1] == "result=no_gaps_found"
    assert shown["git_head"] == HEAD and shown["calendar_source"] == "twse_mi_5mins_hist"
    assert (shown["period_start"], shown["period_end"]) == ("2025-07-07", "2026-11-18")
    assert shown["months_unchecked"] == "none" and len(shown["months_checked"].split(",")) == 17
    paste = world.work / gc.PASTE_BACK_NAME
    raw = paste.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
    assert raw.decode("utf-8-sig").splitlines() == lines
    assert world.opened == [paste]
    assert not (world.work / "copy").exists()


def test_the_script_hash_is_the_lf_normalised_source_hash(tmp_path: Path, capsys: Any) -> None:
    import hashlib

    world = make_world(tmp_path)
    _code, lines, _err = run(world, capsys)
    data = SCRIPT_PATH.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    assert values(lines)["script_sha256_lf"] == hashlib.sha256(data).hexdigest()


def test_the_period_comes_from_the_run_date_not_from_any_record(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path, run_date=date(2026, 3, 2))
    shown = values(run(world, capsys)[1])
    assert (shown["period_start"], shown["period_end"]) == ("2024-10-18", "2026-03-01")


def test_a_gap_a_cache_only_day_and_an_uncovered_day_are_listed_by_date_only(
    tmp_path: Path, capsys: Any
) -> None:
    gap = date(2026, 4, 15)
    world = make_world(
        tmp_path,
        missing_in_cache=[gap],
        extra_in_cache=["2026-10-10"],
        cache_from=date(2025, 8, 1),
        bad_months=["2025-09"],
    )
    code, lines, _err = run(world, capsys)
    shown = values(lines)
    assert code == 0 and shown["result"] == "gaps_found"
    assert shown["official_not_in_cache_dates"] == "2026-04-15"
    assert shown["official_not_in_cache_count"] == "1"
    assert shown["cache_not_in_official_dates"] == "2026-10-10"
    assert shown["cache_range_start"] == "2025-08-01"
    assert shown["cache_not_covered_count"] == "19"  # 2025-07-07 .. 2025-07-31, weekdays
    assert shown["months_unchecked"] == "2025-09"
    assert_closed(lines)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"bad_months": [f"{y:04d}-{m:02d}" for y, m in gc.months_between(
            date(2025, 7, 7), date(2026, 11, 18))]}, "calendar_unavailable"),
        ({"missing_in_cache": [date(2026, 4, 15)], "bad_months": ["2025-09", "2025-10"]},
         "gaps_found"),
        ({"extra_in_cache": ["2026-10-10"]}, "gaps_found"),
        ({"cache_from": date(2025, 9, 1)}, "no_gaps_in_checked_months"),
        ({"bad_months": ["2026-03", "2025-12"]}, "no_gaps_in_checked_months"),
        ({}, "no_gaps_found"),
    ],
)  # fmt: skip
def test_the_flow_gives_the_result_code_of_each_ruling_case(
    tmp_path: Path, capsys: Any, kwargs: dict[str, Any], expected: str
) -> None:
    world = make_world(tmp_path, holidays=[date(2026, 10, 10)], **kwargs)
    if "extra_in_cache" in kwargs:
        assert date(2026, 10, 10) not in world.official
    _code, lines, _err = run(world, capsys)
    assert values(lines)["result"] == expected


# --- no non-date value may reach the output -----------------------------------------------------


def test_no_price_label_cash_holding_or_claim_reaches_the_screen_or_the_file(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path, missing_in_cache=[date(2026, 4, 15)])
    # The synthetic main database holds OHLCV values and other tables full of poison.
    with closing(sqlite3.connect(str(world.db))) as conn:
        assert conn.execute("SELECT count(*) FROM portfolio").fetchone() == (1,)
        assert conn.execute("SELECT open FROM price_bars_cache LIMIT 1").fetchone() == (POISON[0],)
    _code, lines, _err = run(world, capsys)
    text = "\n".join(lines) + "\n" + (world.work / gc.PASTE_BACK_NAME).read_text("utf-8-sig")
    for poison in (*POISON, "claim", "bullish", "label", "close", "volume", "record", "open"):
        assert poison not in text, poison
    # Every value is a date, a month, a count, a hash, the source code or a result code.
    for line in lines:
        key, _eq, value = line.partition("=")
        assert key in {
            "gap_check version", "git_head", "script_sha256_lf", "calendar_source",
            "period_start", "period_end", "months_checked", "months_unchecked",
            "cache_range_start", "cache_range_end", "cache_not_covered_count",
            "cache_not_covered_dates", "official_not_in_cache_count",
            "official_not_in_cache_dates", "cache_not_in_official_count",
            "cache_not_in_official_dates", "result",
        }  # fmt: skip
        assert re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}|[a-z_0-9]+|[0-9,\-]+|none", value), line


def test_the_database_files_and_the_data_folder_are_unchanged_after_the_run(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path)
    before = main_db_state(world)
    listing = sorted(p.name for p in world.db.parent.iterdir())
    run(world, capsys)
    assert main_db_state(world) == before
    assert sorted(p.name for p in world.db.parent.iterdir()) == listing


def test_only_the_one_select_and_the_readonly_pragma_run_and_only_on_main_and_the_copy(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path)
    statements: list[str] = []
    targets: list[str] = []
    real_connect = sqlite3.connect

    def spying(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        targets.append(str(database))
        conn: sqlite3.Connection = real_connect(database, *args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(gc.sqlite3, "connect", spying)
    code, _lines, _err = run(world, capsys)
    assert code == 0
    assert statements.count(gc.SELECT_SQL) == 1
    assert set(statements) <= {gc.SELECT_SQL, gc.READ_ONLY_PRAGMA}
    main_uri = f"{world.db.resolve().as_uri()}?mode=ro&immutable=1"
    copy_path = str(world.work / "copy" / "stock-desk.db")
    copy_uri = Path(copy_path).resolve().as_uri() + "?mode=ro&immutable=1"
    assert targets == [main_uri, copy_path, copy_uri]


def test_the_copy_lives_under_the_gap_check_work_folder_outside_any_git_work_tree(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path)
    seen: list[Path] = []
    real_make = gc.make_copy

    def spy(main_db: Path, copy_dir: Path) -> Path:
        seen.append(copy_dir)
        return real_make(main_db, copy_dir)  # type: ignore[no-any-return]

    monkeypatch.setattr(gc, "make_copy", spy)
    run(world, capsys)
    assert seen == [world.work / "copy"]
    assert not gc.inside_git_work_tree(seen[0])
    assert gc.WORK_ROOT_NAME == "stock-desk-gap-check"
    assert gc.WORK_ROOT_NAME not in {
        "stock-desk-pipeline-acceptance",
        "stock-desk-cg2-registration",
    }


# --- the SQL and the imports (AST) ---------------------------------------------------------------


def _tree() -> ast.Module:
    return ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))


def test_ast_the_sql_is_exactly_one_select_of_trade_date_from_the_cache_for_twii() -> None:
    assert gc.SELECT_SQL == "SELECT trade_date FROM price_bars_cache WHERE symbol = '^TWII'"
    assert ";" not in gc.SELECT_SQL and sqlite3.complete_statement(gc.SELECT_SQL + ";")
    tree = _tree()
    executes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "execute"
    ]
    assert sorted(ast.unparse(n.args[0]) for n in executes) == ["READ_ONLY_PRAGMA", "SELECT_SQL"]
    assert all(len(n.args) == 1 for n in executes)  # no parameters, no second form
    assert not any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in ("executemany", "executescript")
        for n in ast.walk(tree)
    )  # fmt: skip
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    sqlish = re.compile(r"(?i)\b(select|insert|update|delete|create|drop|attach|from)\b|price_bars")
    hits = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and id(n) not in docstrings
        and sqlish.search(n.value)
    ]
    assert hits == [gc.SELECT_SQL]


def test_the_select_names_the_real_cache_columns() -> None:
    cache_source = (BACKEND / "app" / "data" / "cache.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS price_bars_cache" in cache_source
    assert re.search(r"^\s+symbol TEXT NOT NULL,", cache_source, re.M)
    assert re.search(r"^\s+trade_date TEXT NOT NULL,", cache_source, re.M)


STDLIB = {
    "__future__", "argparse", "collections", "contextlib", "dataclasses", "datetime", "gc",
    "hashlib", "http", "json", "logging", "os", "pathlib", "re", "shutil", "socket", "sqlite3",
    "subprocess", "sys", "threading", "time", "types", "typing", "urllib", "warnings",
}  # fmt: skip


def test_ast_the_script_imports_only_the_standard_library_and_nothing_of_app() -> None:
    roots: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            roots.add((node.module or "").split(".")[0])
    assert roots <= STDLIB, roots - STDLIB
    assert not {"app", "tests"} & roots
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "app.forecast" not in source.replace("``app.forecast``", "")
    assert "import app" not in source and "from app" not in source


def test_an_isolated_import_is_silent_and_loads_nothing_of_app_or_tests() -> None:
    driver = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('g', {str(SCRIPT_PATH)!r})\n"
        "sys.modules['g'] = m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "banned = ('app', 'tests', 'httpx', 'requests')\n"
        "bad = [n for n in sys.modules if n.split('.')[0] in banned]\n"
        "sys.stdout.write('BAD ' + ','.join(bad) if bad else 'CLEAN')\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", driver], capture_output=True, text=True, timeout=120
    )
    assert (done.stdout, done.stderr, done.returncode) == ("CLEAN", "", 0)


def test_ast_the_env_file_is_only_searched_for_the_key_never_read_for_values() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert source.count('".env"') == 1  # only the one path of the key search in preflight
    tree = _tree()
    func = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "env_file_sets_db_path"
    )
    assert "ENV_KEY_PATTERN.match(line)" in ast.unparse(func)
    assert "read_text" not in ast.unparse(func) and ".read(" not in ast.unparse(func)


def test_the_env_file_values_are_never_shown_and_only_the_key_stops(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path)
    (world.backend.parent / ".env").write_text("API_KEY=TOPSECRETVALUE\nOTHER=1\n", "utf-8")
    code, lines, _err = run(world, capsys)
    assert code == 0 and "TOPSECRETVALUE" not in "\n".join(lines)
    (world.backend.parent / ".env").write_text("  STOCK_DESK_DB_PATH = /x\n", "utf-8")
    world2 = make_world(tmp_path / "w2")
    (world2.backend.parent / ".env").write_text("  STOCK_DESK_DB_PATH = /x\n", "utf-8")
    only_stop(world2, capsys, "env_file_db_path")


# --- the preflight stops ------------------------------------------------------------------------


def test_stop_env_db_path(tmp_path: Path, capsys: Any) -> None:
    only_stop(make_world(tmp_path), capsys, "env_db_path", env={"STOCK_DESK_DB_PATH": "x"})


def test_stop_no_db_at_the_default_location(tmp_path: Path, capsys: Any) -> None:
    only_stop(make_world(tmp_path, write_db=False), capsys, "no_db")


def test_stop_port_listening(tmp_path: Path, capsys: Any) -> None:
    only_stop(make_world(tmp_path), capsys, "port_listening", port_check=lambda: True)


def test_stop_work_folder_inside_a_git_work_tree(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path)
    (world.home / ".git").mkdir()
    only_stop(world, capsys, "work_in_git")


def test_stop_git_unusable_dirty_and_unpublished(tmp_path: Path, capsys: Any) -> None:
    from tests.gap_check_world import FakeGit

    for name, git, kind in (
        ("a", FakeGit(unusable=True), "git_unusable"),
        ("b", FakeGit(dirty=True), "git_dirty"),
        ("c", FakeGit(published=False), "head_unpublished"),
        ("d", FakeGit(head="not-a-hash"), "git_unusable"),
    ):
        world = make_world(tmp_path / name)
        only_stop(world, capsys, kind, git=git)


def test_the_real_port_check_asks_only_loopback_8000(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[Any] = []

    def refuse(address: Any, timeout: float) -> None:
        asked.append((address, timeout))
        raise OSError("closed")

    monkeypatch.setattr(socket, "create_connection", refuse)
    assert gc.port_is_listening() is False and asked == [(("127.0.0.1", 8000), 1.0)]

    class Ok:
        def __enter__(self) -> Ok:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: Ok())
    assert gc.port_is_listening() is True


# --- the reading stops -------------------------------------------------------------------------


def test_stop_the_main_database_cannot_be_read(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path, write_db=False)
    world.db.write_bytes(b"this is not a database" * 100)
    only_stop(world, capsys, "db_unreadable")


def test_stop_the_copy_has_no_cache_table(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path, write_db=False)
    write_main_db(world.db, [], with_table=False)
    only_stop(world, capsys, "copy_unreadable")


def test_stop_the_cache_holds_no_twii_row(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path, write_db=False)
    write_main_db(world.db, [])
    only_stop(world, capsys, "no_rows")


@pytest.mark.parametrize("bad", ["2026/11/02", "20261102", "2026-13-01", "", "2026-11-02T00:00"])
def test_stop_a_trade_date_that_is_not_a_plain_iso_date(
    tmp_path: Path, capsys: Any, bad: str
) -> None:
    world = make_world(tmp_path, write_db=False)
    write_main_db(world.db, ["2026-11-02", bad])
    only_stop(world, capsys, "unparseable_row")


def test_stop_a_non_text_trade_date(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path, write_db=False)
    write_main_db(world.db, ["2026-11-02"])
    with closing(sqlite3.connect(str(world.db))) as conn:
        conn.execute("DROP TABLE price_bars_cache")
        conn.execute("CREATE TABLE price_bars_cache (symbol TEXT, trade_date)")
        conn.execute("INSERT INTO price_bars_cache VALUES ('^TWII', 20261102)")
        conn.commit()
    only_stop(world, capsys, "unparseable_row")


# --- deletion before output (RC-220) ---------------------------------------------------------


def test_the_copy_is_deleted_before_the_calendar_is_asked_and_before_the_first_result_line(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path)
    events: list[str] = []
    copy_dir = world.work / "copy"

    def remover(path: Path) -> None:
        events.append(f"delete:{path.name}")
        gc.remove_path(path)

    def get(url: str) -> tuple[int, bytes]:
        events.append("fetch")
        assert not copy_dir.exists()
        return world.calendar(url)

    real_say = gc.say

    def say(text: str) -> None:
        events.append("say")
        assert not copy_dir.exists()
        real_say(text)

    monkeypatch.setattr(gc, "say", say)
    code, _lines, _err = run(world, capsys, remover=remover, get=get)
    assert code == 0
    first_say = events.index("say")
    assert events.index("fetch") < first_say
    assert max(i for i, e in enumerate(events) if e.startswith("delete:")) < events.index("fetch")
    assert events[-1] == "say" and "delete:copy" in events and "delete:stock-desk.db" in events


def test_a_copy_with_side_files_is_deleted_with_them(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path)
    real_read = gc.read_trade_dates

    def read_then_leave_side_files(copy_path: Path) -> list[date]:
        days = real_read(copy_path)
        for suffix in ("-wal", "-shm", "-journal"):
            Path(f"{copy_path}{suffix}").write_bytes(b"x")
        return days  # type: ignore[no-any-return]

    monkeypatch.setattr(gc, "read_trade_dates", read_then_leave_side_files)
    deleted: list[str] = []

    def remover(path: Path) -> None:
        deleted.append(path.name)
        gc.remove_path(path)

    code, _lines, _err = run(world, capsys, remover=remover)
    assert code == 0 and not (world.work / "copy").exists()
    assert {"stock-desk.db-wal", "stock-desk.db-shm", "stock-desk.db-journal"} <= set(deleted)


@pytest.mark.parametrize("stuck", ["stock-desk.db", "stock-desk.db-shm", "copy"])
def test_an_injected_delete_failure_stops_and_no_result_line_is_printed(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch, stuck: str
) -> None:
    world = make_world(tmp_path)
    real_make = gc.make_copy

    def with_shm(main_db: Path, copy_dir: Path) -> Path:
        target = real_make(main_db, copy_dir)
        Path(f"{target}-shm").write_bytes(b"x")
        return target  # type: ignore[no-any-return]

    monkeypatch.setattr(gc, "make_copy", with_shm)

    def remover(path: Path) -> None:
        if path.name == stuck:
            raise PermissionError("locked")
        gc.remove_path(path)

    code, lines, err = run(world, capsys, remover=remover)
    assert (code, err) == (3, "")
    assert lines == [COPY_STOP]  # the stop sentence, once, and nothing else
    assert not any(line.startswith(("result=", "months_", "period_")) for line in lines)
    assert world.calendar.urls == [] and not world.opened
    assert not list(world.work_root.glob("*/" + gc.PASTE_BACK_NAME))


def test_the_delete_is_retried_five_times_with_pauses(tmp_path: Path) -> None:
    attempts: list[int] = []
    pauses: list[float] = []

    def remover(_path: Path) -> None:
        attempts.append(1)
        raise PermissionError("locked")

    assert gc.delete_with_retry(tmp_path / "x", remover, pauses.append) is False
    assert len(attempts) == 5 and pauses == [0.5] * 4


def test_a_copy_left_by_an_earlier_run_is_swept_and_other_folders_are_left(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path)
    old = world.work_root / "20261118-090000"
    (old / "copy").mkdir(parents=True)
    (old / "copy" / "stock-desk.db").write_bytes(b"old")
    (old / gc.PASTE_BACK_NAME).write_text("kept", "utf-8")
    other = world.work_root / "notes"
    other.mkdir()
    (other / "copy").mkdir()
    code, _lines, _err = run(world, capsys)
    assert code == 0 and not (old / "copy").exists()
    assert (old / gc.PASTE_BACK_NAME).read_text("utf-8") == "kept"
    assert (other / "copy").exists()


def test_an_earlier_copy_that_cannot_be_deleted_stops(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path)
    old = world.work_root / "20261118-090000"
    (old / "copy").mkdir(parents=True)
    (old / "copy" / "stock-desk.db").write_bytes(b"old")

    def remover(path: Path) -> None:
        if "20261118-090000" in str(path):
            raise PermissionError("locked")
        gc.remove_path(path)

    code, lines, _err = run(world, capsys, remover=remover)
    assert (code, lines) == (3, [COPY_STOP])
    assert world.calendar.urls == []


# --- the screen guarantee (RC-162 / RC-158a / RC-158c) --------------------------------------


def test_an_unexpected_error_prints_the_fixed_sentence_only(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path)

    def boom(_url: str) -> tuple[int, bytes]:
        raise RuntimeError("secret label 31415.926")

    code, lines, err = run(world, capsys, get=boom)
    assert (code, lines, err) == (1, [UNEXPECTED], "")
    no_residue(world)


def test_bad_arguments_are_the_fixed_sentence_and_nothing_on_stderr(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path)
    code = gc.main(["--bogus", "x"], **world.seams())
    captured = capsys.readouterr()
    assert (code, captured.out.splitlines(), captured.err) == (1, [UNEXPECTED], "")


def test_a_line_outside_the_whitelist_is_never_shown() -> None:
    for bad in ("open=1.5", "claim_id=abc", "result=ok", "T=2026-11-18", "records=5", "x", ""):
        assert not gc.is_screen_line(bad)
        with pytest.raises(RuntimeError):
            gc.say(bad)
    with pytest.raises(RuntimeError):
        gc.say("result=gaps_foundé")


def test_a_rendered_line_outside_the_whitelist_aborts_before_anything_is_printed(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path)
    monkeypatch.setattr(gc, "CALENDAR_SOURCE", "other_source")
    code, lines, err = run(world, capsys)
    assert (code, lines, err) == (1, [UNEXPECTED], "")
    no_residue(world)


def test_a_failing_print_leaves_no_paste_back_and_the_fixed_sentence(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path)
    calls: list[str] = []
    real_say = gc.say

    def flaky(text: str) -> None:
        calls.append(text)
        if len(calls) == 3:
            raise BrokenPipeError()
        real_say(text)

    monkeypatch.setattr(gc, "say", flaky)
    code, lines, _err = run(world, capsys)
    assert code == 1 and lines[-1] == UNEXPECTED
    assert not list(world.work_root.glob("*/" + gc.PASTE_BACK_NAME)) and not world.opened


def test_every_stop_screen_is_closed(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path)
    for kind in ("env_db_path", "port_listening"):
        override = (
            {"env": {"STOCK_DESK_DB_PATH": "x"}} if kind == "env_db_path"
            else {"port_check": lambda: True}
        )  # fmt: skip
        _code, lines, _err = run(world, capsys, **override)
        assert_closed(lines)


def test_the_fixed_sentences_are_ascii_without_values_and_the_new_one_tells_the_coordinator() -> (
    None
):
    assert all(s.isascii() and "\n" not in s for s in gc.FIXED_SENTENCES)
    assert STOPS["copy_unreadable"].endswith(
        "Do not change any setting or file yourself; tell the coordinator."
    )
    assert STOPS["db_unreadable"].endswith(
        "Do not change any setting or file yourself; tell the coordinator."
    )
    assert (
        gc.UNEXPECTED
        == "ERROR: unexpected failure; no paste-back file was made. Tell the coordinator."
    )


def test_ast_the_hooks_are_the_first_effective_statements() -> None:
    body = _tree().body

    def is_hook(node: ast.stmt) -> bool:
        return (
            isinstance(node, ast.Assign)
            and ast.unparse(node.targets[0])
            in ("sys.excepthook", "threading.excepthook", "sys.unraisablehook")
        ) or (
            isinstance(node, ast.Expr)
            and ast.unparse(node.value)
            in ("warnings.simplefilter('ignore')", "logging.disable(logging.CRITICAL)")
        )

    hooks = [i for i, node in enumerate(body) if is_hook(node)]
    assert len(hooks) == 5
    first_other_import = next(
        i
        for i, node in enumerate(body)
        if isinstance(node, ast.Import | ast.ImportFrom)
        and ast.unparse(node)
        not in (
            "from __future__ import annotations",
            "import logging",
            "import sys",
            "import threading",
            "import warnings",
        )
    )
    assert max(hooks) < first_other_import
    before = [n for n in body[:first_other_import] if not is_hook(n)]
    assert [ast.unparse(n) for n in before if isinstance(n, ast.Import | ast.ImportFrom)] == [
        "from __future__ import annotations",
        "import logging",
        "import sys",
        "import threading",
        "import warnings",
    ]
    assert [n.name for n in before if isinstance(n, ast.FunctionDef)] == ["_fixed_hook"]


def test_the_hook_sentence_is_the_error_sentence(capsys: Any) -> None:
    gc._fixed_hook(RuntimeError, RuntimeError("secret"), None)
    captured = capsys.readouterr()
    assert captured.out == UNEXPECTED + "\n" and captured.err == ""


# --- end to end in a real subprocess: all of stdout and stderr are captured ---------------------

DRIVER = textwrap.dedent(
    """
    import importlib.util, logging, sys, threading, warnings
    from pathlib import Path
    sys.path.insert(0, {backend!r})
    from tests.gap_check_world import make_world
    spec = importlib.util.spec_from_file_location("gap_check_sub", {script!r})
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gap_check_sub"] = mod
    spec.loader.exec_module(mod)  # installs the real hooks, as running the script does
    root, scenario = Path(sys.argv[1]), sys.argv[2]
    world = make_world(root)
    over = {{}}
    base_get = world.calendar
    state = {{"first": True}}
    def get(url):
        if scenario == "error":
            raise RuntimeError("secret label 31415.926")
        if scenario == "interrupt_fetch":
            raise KeyboardInterrupt()
        if scenario == "thread":
            def boom():
                raise RuntimeError("secret in thread")
            t = threading.Thread(target=boom); t.start(); t.join()
        if scenario == "warn":
            warnings.warn("secret warning")
            logging.getLogger("x").error("secret log")
            logging.getLogger().warning("secret root log")
        if scenario == "unraisable" and state["first"]:
            state["first"] = False
            class Bad:
                def __del__(self):
                    raise RuntimeError("secret in del")
            b = Bad(); del b
        return base_get(url)
    over["get"] = get
    if scenario == "interrupt_compare":
        def boom(*a, **k):
            raise KeyboardInterrupt()
        mod.compare = boom
    if scenario in ("interrupt_delete", "interrupt_delete_stuck"):
        def remover(path):
            if scenario == "interrupt_delete_stuck" or state["first"]:
                state["first"] = False
                raise KeyboardInterrupt()
            mod.remove_path(path)
        over["remover"] = remover
    code = mod.main(world.args(), **world.seams(**over))
    sys.exit(code)
    """
)


def _drive(tmp_path: Path, scenario: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    env = {k: v for k, v in os.environ.items() if k != "STOCK_DESK_DB_PATH"}
    code = DRIVER.format(backend=str(BACKEND), script=str(SCRIPT_PATH))
    done = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code, str(tmp_path), scenario],
        capture_output=True, text=True, timeout=300, cwd=BACKEND, env=env,
    )  # fmt: skip
    return done, tmp_path / "home" / "stock-desk-gap-check"


def _paste_backs(root: Path) -> list[Path]:
    return list(root.glob("*/paste-back.txt")) if root.exists() else []


def _copies(root: Path) -> list[Path]:
    return list(root.glob("*/copy")) if root.exists() else []


def test_e2e_a_normal_end_every_line_of_stdout_is_whitelisted_and_stderr_is_empty(
    tmp_path: Path,
) -> None:
    done, root = _drive(tmp_path, "ok")
    lines = done.stdout.splitlines()
    assert (done.returncode, done.stderr) == (0, "")
    assert_closed(lines)
    assert values(lines)["result"] == "no_gaps_found"
    (paste,) = _paste_backs(root)
    assert paste.read_bytes().decode("utf-8-sig").splitlines() == lines
    assert _copies(root) == []


@pytest.mark.parametrize("scenario", ["warn", "thread", "unraisable"])
def test_e2e_warnings_thread_errors_and_unraisables_never_show_their_text(
    tmp_path: Path, scenario: str
) -> None:
    done, root = _drive(tmp_path, scenario)
    lines = done.stdout.splitlines()
    assert done.stderr == "" and "secret" not in done.stdout
    assert_closed(lines)
    assert done.returncode == 0
    if scenario != "warn":
        assert UNEXPECTED in lines  # the hook's fixed sentence, once per event
    assert _copies(root) == []


def test_e2e_an_error_is_the_fixed_sentence(tmp_path: Path) -> None:
    done, root = _drive(tmp_path, "error")
    assert (done.returncode, done.stdout.splitlines(), done.stderr) == (1, [UNEXPECTED], "")
    assert _paste_backs(root) == [] and _copies(root) == []


@pytest.mark.parametrize("scenario", ["interrupt_fetch", "interrupt_compare", "interrupt_delete"])
def test_e2e_an_interrupt_in_fetching_comparing_or_deleting_is_the_fixed_sentence(
    tmp_path: Path, scenario: str
) -> None:
    done, root = _drive(tmp_path, scenario)
    assert (done.returncode, done.stdout.splitlines(), done.stderr) == (2, [INTERRUPTED], "")
    assert _paste_backs(root) == [] and _copies(root) == []


def test_e2e_an_interrupt_while_deleting_that_leaves_the_copy_shows_the_copy_stop(
    tmp_path: Path,
) -> None:
    done, root = _drive(tmp_path, "interrupt_delete_stuck")
    lines = done.stdout.splitlines()
    assert done.stderr == "" and done.returncode == 3
    assert lines[0] == INTERRUPTED and lines[-1] == COPY_STOP
    assert_closed(lines)
    assert not any(x.startswith("result=") for x in lines)
    assert _paste_backs(root) == []


def test_e2e_a_stop_through_a_real_isolated_interpreter(tmp_path: Path) -> None:
    # The path the batch file takes: python -I from an unrelated folder, a real stdin.
    world = make_world(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "STOCK_DESK_DB_PATH"}
    env["STOCK_DESK_DB_PATH"] = "x"
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", str(SCRIPT_PATH), *world.args()],
        input="\n", capture_output=True, text=True, timeout=300, cwd=tmp_path, env=env,
    )  # fmt: skip
    assert done.returncode == 3 and done.stderr == ""
    assert [x.removeprefix(gc.PROMPT) for x in done.stdout.splitlines()] == [STOPS["env_db_path"]]
    assert not world.work_root.exists() or not any(world.work_root.iterdir())


# --- read-only evidence for the backup source connection (hand-over report) -----------------------


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def _state(folder: Path) -> dict[str, tuple[bytes, int]]:
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(folder.iterdir())}


def test_backup_source_without_a_wal_file_adds_and_changes_no_side_file(tmp_path: Path) -> None:
    db = tmp_path / "main" / "stock-desk.db"
    write_main_db(db, ["2026-11-02", "2026-11-03"], wal=True)  # WAL mode, cleanly closed
    assert _names(db.parent) == ["stock-desk.db"]
    before = _state(db.parent)
    copy = gc.make_copy(db, tmp_path / "copy")
    assert _state(db.parent) == before
    assert _names(copy.parent) == ["stock-desk.db"]
    assert len(gc.read_trade_dates(copy)) == 2


def test_contrast_a_plain_readonly_connection_to_a_wal_database_does_add_side_files(
    tmp_path: Path,
) -> None:
    db = tmp_path / "main" / "stock-desk.db"
    write_main_db(db, ["2026-11-02"], wal=True)
    with closing(sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        conn.execute("SELECT count(*) FROM price_bars_cache").fetchall()
        assert {"stock-desk.db-shm", "stock-desk.db-wal"} <= set(
            _names(db.parent)
        )  # why immutable=1


def test_backup_source_with_a_live_wal_keeps_the_db_and_wal_bytes_and_reads_the_wal_rows(
    tmp_path: Path,
) -> None:
    db = tmp_path / "main" / "stock-desk.db"
    writer = write_main_db(db, ["2026-11-02", "2026-11-03"], wal=True, keep_open=True)
    assert writer is not None
    try:
        writer.execute(
            "INSERT INTO price_bars_cache VALUES"
            " ('^TWII','TW','2026-11-04','1','1','1','1',1,'TWD','yfinance','a','b')"
        )
        writer.commit()
        names = _names(db.parent)
        assert {"stock-desk.db-wal", "stock-desk.db-shm"} <= set(names)
        before = _state(db.parent)
        copy = gc.make_copy(db, tmp_path / "copy")
        after = _state(db.parent)
        assert _names(db.parent) == names  # no side file added or removed
        for name in ("stock-desk.db", "stock-desk.db-wal"):
            assert after[name] == before[name]  # bytes and mtime
        assert sorted(d.isoformat() for d in gc.read_trade_dates(copy)) == [
            "2026-11-02", "2026-11-03", "2026-11-04"
        ]  # fmt: skip
        assert _names(copy.parent) == ["stock-desk.db"]
    finally:
        writer.close()


def test_backup_source_with_a_wal_and_no_shm_changes_neither_db_nor_wal(tmp_path: Path) -> None:
    live = tmp_path / "live" / "stock-desk.db"
    writer = write_main_db(live, ["2026-11-02"], wal=True, keep_open=True)
    assert writer is not None
    crashed = tmp_path / "crashed"
    crashed.mkdir()
    try:
        shutil.copy(live, crashed / "stock-desk.db")
        shutil.copy(f"{live}-wal", crashed / "stock-desk.db-wal")
    finally:
        writer.close()
    before = _state(crashed)
    copy = gc.make_copy(crashed / "stock-desk.db", tmp_path / "copy")
    after = _state(crashed)
    for name in ("stock-desk.db", "stock-desk.db-wal"):
        assert after[name] == before[name]
    assert set(after) - set(before) <= {"stock-desk.db-shm"}  # at most the wal-index is created
    assert [d.isoformat() for d in gc.read_trade_dates(copy)] == ["2026-11-02"]


# --- the launcher ---------------------------------------------------------------------------------

BAT = BACKEND.parent / "gap-check.bat"
COMMAND = r"uv run --no-sync python -I -X utf8 scripts\gap_check.py"


def test_the_bat_is_a_crlf_launcher_that_clears_uv_env_file_first() -> None:
    raw = BAT.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n") and b"\r\r" not in raw
    lines = raw.decode("ascii").split("\r\n")
    assert lines[0] == "@echo off"
    assert 'set "UV_ENV_FILE="' in lines
    assert lines.index('set "UV_ENV_FILE="') < lines.index(COMMAND)
    assert lines.count(COMMAND) == 1
    assert lines.index(COMMAND) < max(i for i, x in enumerate(lines) if x == "pause")
    assert 'cd /d "%BACKEND_DIR%"' in lines
    assert not any("STOCK_DESK" in x or ".env" in x for x in lines if not x.startswith("REM"))
    assert not any(a in COMMAND for a in ("--backend-dir", "--home"))


def test_the_bat_matches_the_pipeline_acceptance_launcher_except_its_own_lines() -> None:
    lines = BAT.read_bytes().decode("ascii").split("\r\n")
    other = (BAT.parent / "pipeline-acceptance.bat").read_bytes().decode("ascii").split("\r\n")
    commands = [x for x in lines if not x.startswith("REM")]
    assert not any("/dev/null" in x for x in commands)
    assert "where uv >nul 2>nul" in lines
    own = {"title stock-desk gap-check", COMMAND}
    theirs = {x for x in other if not x.startswith("REM")}
    assert [x for x in commands if x not in theirs and x not in own] == []


def test_the_launcher_names_the_script_that_exists() -> None:
    assert SCRIPT_PATH.is_file() and SCRIPT_PATH.name in COMMAND


def test_the_flow_asks_only_the_fixed_calendar_once_per_month_with_the_rate_limit(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path)
    run(world, capsys)
    assert isinstance(world.calendar, FakeCalendar)
    assert len(world.calendar.urls) == 17 == len(set(world.calendar.urls))
    prefix = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?response=json&date="
    assert all(u.startswith(prefix) for u in world.calendar.urls)
    assert len(world.clock.sleeps) == 16 and all(s > 0 for s in world.clock.sleeps)
