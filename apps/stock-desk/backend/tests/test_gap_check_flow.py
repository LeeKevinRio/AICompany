"""Flow, output-path and read-only tests of ``scripts/gap_check.py``.

Authority: ADR-0030 supplement 8 point 5 (c), as read and tightened by supplement 10 point 7.

Every test runs on ``tmp_path`` worlds (:mod:`tests.gap_check_world`): a synthetic "main"
database with OHLCV values and other tables, a fake backend folder, a fake home, a fake git, a
synthetic calendar and a fake clock. The real ``<backend>/data/``, ``.env`` and the network are
never touched (an autouse guard turns any socket connect into a failing assertion).
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
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
    FakeGit,
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


REPORT_NAME = "2026-11-20-補充十修訂版與三句STOP判定RC265至RC274-風控.md"


UV_REPORT_NAME = "2026-11-20-補充十一E1確認與缺少uv提示定稿RC305至RC312-風控.md"


def report_path(name: str = REPORT_NAME) -> Path:
    """A risk-control report (found under ``work/reviews``)."""
    override = os.environ.get("GAP_CHECK_RC_REPORT") if name == REPORT_NAME else None
    if override:
        return Path(override)
    for folder in Path(__file__).resolve().parents:
        candidate = folder / "work" / "reviews" / name
        if candidate.is_file():
            return candidate
    raise AssertionError(f"the risk-control report was not found: work/reviews/{name}")


def report_sentences() -> dict[str, set[str]]:
    """Item label (``S-1`` ...) to the set of ``定稿全文`` texts below its ``項目：`` line."""
    lines = report_path().read_text(encoding="utf-8").splitlines()
    found: dict[str, set[str]] = {}
    for index, line in enumerate(lines):
        match = re.match(r"項目：(S-[0-9])\b", line)
        if match:
            following = lines[index + 1]
            prefix = "定稿全文：`"
            assert following.startswith(prefix) and following.endswith("`"), following
            found.setdefault(match.group(1), set()).add(following[len(prefix) : -1])
    return found


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


def test_only_the_one_select_runs_on_the_copy_no_pragma_and_nothing_on_main(
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
    assert statements == [gc.SELECT_SQL]  # one statement in all: no PRAGMA, nothing else
    assert not any("PRAGMA" in statement.upper() for statement in statements)
    assert not hasattr(gc, "READ_ONLY_PRAGMA")
    main_uri = f"{world.db.resolve().as_uri()}?mode=ro&immutable=1"
    copy_path = str(world.work / "copy" / "stock-desk.db")
    copy_uri = Path(copy_path).resolve().as_uri() + "?mode=ro&immutable=1"
    assert targets == [main_uri, copy_path, copy_uri]


def test_the_header_names_supplement_10_point_7_as_part_of_the_authority() -> None:
    assert "supplement 8 point 5" in gc.__doc__ and "supplement 10 point 7" in gc.__doc__


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
    assert [ast.unparse(n.args[0]) for n in executes] == ["SELECT_SQL"]  # no PRAGMA
    assert all(len(n.args) == 1 for n in executes)  # no parameters, no second form
    assert not any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in ("executemany", "executescript")
        for n in ast.walk(tree)
    )  # fmt: skip
    assert _sqlish_strings(tree) == [gc.SELECT_SQL]


SQLISH = re.compile(r"(?i)\b(select|insert|update|delete|create|drop|attach|from)\b|price_bars")


def _sqlish_strings(tree: ast.Module) -> list[str]:
    """String constants (not docstrings) with SQL-like words; only S-1 is let through verbatim.

    The risk-control sentence S-1 contains the word "delete" as prose and is pinned verbatim to
    the report by another test, so it alone is excluded; every other fixed sentence is checked.
    """
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and id(n) not in docstrings
        and n.value != STOPS["db_in_use"]
        and SQLISH.search(n.value)
    ]


@pytest.mark.parametrize("word", ["select", "delete"])
def test_the_sql_guard_has_teeth_against_another_fixed_sentence_with_a_sql_word(word: str) -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    old = "STOP: the cache copy holds no TWII rows."
    assert source.count(old) == 1
    tampered = ast.parse(source.replace(old, f"STOP: {word} the cache copy."))
    assert _sqlish_strings(tampered) == [gc.SELECT_SQL, f"STOP: {word} the cache copy."]
    assert _sqlish_strings(_tree()) == [gc.SELECT_SQL]


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
    for name, git, kind in (
        ("a", FakeGit(unusable=True), "git_unusable"),
        ("b", FakeGit(dirty=True), "git_dirty"),
        ("c", FakeGit(published=False), "head_unpublished"),
        ("d", FakeGit(head="not-a-hash"), "git_unusable"),
    ):
        world = make_world(tmp_path / name)
        only_stop(world, capsys, kind, git=git)


class _PathAwareGit:
    """A fake git whose ``status`` reports a change only for a path the status call names."""

    def __init__(self, dirty_paths: set[str]) -> None:
        self.dirty_paths = dirty_paths
        self.status_calls: list[list[str]] = []
        self.inner = FakeGit()

    def __call__(self, cwd: Path, args: Any) -> tuple[int, bytes]:
        if list(args)[:1] == ["status"]:
            self.status_calls.append(list(args))
            named = list(args)[list(args).index("--") + 1 :]
            hit = sorted(self.dirty_paths & set(named))
            return 0, "".join(f" M {x}\n" for x in hit).encode()
        return self.inner(cwd, args)


def test_the_clean_check_names_the_launcher_beside_the_backend_folder() -> None:
    assert gc.CLEAN_PATHS == ("app", "tests", "scripts", "uv.lock", "../gap-check.bat")


def test_stop_when_gap_check_bat_has_uncommitted_changes(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path)
    git = _PathAwareGit({"../gap-check.bat"})
    only_stop(world, capsys, "git_dirty", git=git)
    assert git.status_calls and "../gap-check.bat" in git.status_calls[0]


def test_a_clean_launcher_does_not_stop_and_the_other_paths_still_do(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path / "a")
    code, lines, _err = run(world, capsys, git=_PathAwareGit(set()))
    assert code == 0 and lines[-1].startswith("result=")
    for index, path in enumerate(gc.CLEAN_PATHS[:-1]):
        other = make_world(tmp_path / f"b{index}")
        only_stop(other, capsys, "git_dirty", git=_PathAwareGit({path}))


def _real_git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-C", str(cwd), *args],
        check=True, capture_output=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )  # fmt: skip


def test_real_git_reports_a_changed_or_untracked_launcher_through_the_clean_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    backend = repo / "backend"
    for folder in ("app", "tests", "scripts"):
        (backend / folder).mkdir(parents=True)
        (backend / folder / "x.py").write_text("x = 1\n", "utf-8")
    (backend / "uv.lock").write_text("lock\n", "utf-8")
    (repo / "gap-check.bat").write_bytes(b"@echo off\r\n")
    _real_git(repo, "init", "-q")
    _real_git(repo, "add", "-A")
    _real_git(repo, "commit", "-q", "-m", "init")
    status = ["status", "--porcelain", "--untracked-files=all", "--", *gc.CLEAN_PATHS]
    assert gc.run_git(backend, status) == (0, b"")
    (repo / "gap-check.bat").write_bytes(b"@echo off\r\nrem changed\r\n")
    code, out = gc.run_git(backend, status)
    assert code == 0 and out.split() == [b"M", b"gap-check.bat"]  # porcelain: root-relative
    _real_git(repo, "checkout", "--", "gap-check.bat")
    assert gc.run_git(backend, status) == (0, b"")
    (repo / "other.txt").write_text("not a clean path\n", "utf-8")  # outside the named paths
    assert gc.run_git(backend, status) == (0, b"")


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


def test_stop_a_copy_of_the_main_database_could_not_be_made(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path, write_db=False)
    world.db.write_bytes(b"this is not a database" * 100)
    only_stop(world, capsys, "copy_failed")


def test_stop_the_copy_has_no_cache_table(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path, write_db=False)
    write_main_db(world.db, [], with_table=False)
    only_stop(world, capsys, "copy_unreadable")


def test_stop_the_cache_holds_no_twii_row(tmp_path: Path, capsys: Any) -> None:
    world = make_world(tmp_path, write_db=False)
    write_main_db(world.db, [])
    only_stop(world, capsys, "no_rows")


@pytest.mark.parametrize(
    "bad",
    [
        "2026/11/02", "20261102", "2026-13-01", "", "2026-11-02T00:00",
        "２０２６-１１-０２",  # fullwidth digits
        "٢٠٢٦-١١-٠٢",  # Arabic-Indic digits
    ],
)  # fmt: skip
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


@pytest.mark.parametrize(
    ("item", "kind"),
    [("S-1", "db_in_use"), ("S-2", "copy_unreadable"), ("S-3", "copy_failed")],
)
def test_the_three_stops_are_the_risk_control_sentences_verbatim(item: str, kind: str) -> None:
    found = report_sentences()
    assert set(found) == {"S-1", "S-2", "S-3"}
    assert len(found[item]) == 1  # every occurrence of the item in the report is identical
    (sentence,) = found[item]
    assert STOPS[kind] == sentence  # not one character different


def test_the_old_cg2_wording_is_gone_and_the_stop_kinds_are_the_expected_set() -> None:
    assert "db_unreadable" not in STOPS
    assert "the main database could not be read" not in "\n".join(STOPS.values())
    assert set(STOPS) == {
        "env_db_path", "env_file_db_path", "no_db", "port_listening", "work_in_git",
        "git_unusable", "git_dirty", "head_unpublished", "db_in_use", "copy_failed",
        "copy_unreadable", "no_rows", "unparseable_row", "copy_not_deleted",
    }  # fmt: skip


def test_the_fixed_sentences_are_ascii_without_values_and_the_new_one_tells_the_coordinator() -> (
    None
):
    assert all(s.isascii() and "\n" not in s for s in gc.FIXED_SENTENCES)
    assert STOPS["copy_unreadable"].endswith(
        "Do not change any setting or file yourself; tell the coordinator."
    )
    assert STOPS["copy_failed"].endswith(
        "Do not change any setting or file yourself; tell the coordinator."
    )
    assert STOPS["db_in_use"].endswith("tell the coordinator and do not run this again.")
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


def test_a_live_wal_writer_stops_the_run_before_any_connection_is_opened(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Replaces the former "plain mode=ro with a live -wal" tests: that path no longer exists.
    world = make_world(tmp_path, write_db=False)
    writer = write_main_db(world.db, ["2026-11-02", "2026-11-03"], wal=True, keep_open=True)
    assert writer is not None
    connects = _count_connects(monkeypatch)
    try:
        names = _names(world.db.parent)
        assert {"stock-desk.db-wal", "stock-desk.db-shm"} <= set(names)
        before = _state(world.db.parent)
        only_stop(world, capsys, "db_in_use")
        assert connects == []  # no connection of any kind was opened
        assert _names(world.db.parent) == names  # no side file added or removed
        assert _state(world.db.parent) == before  # bytes and mtime of every file
    finally:
        writer.close()


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
def test_a_wal_or_journal_beside_the_main_database_stops_with_no_connection_and_no_copy(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    world = make_world(tmp_path)
    Path(f"{world.db}{suffix}").write_bytes(b"x")
    before = _state(world.db.parent)
    connects = _count_connects(monkeypatch)
    only_stop(world, capsys, "db_in_use")
    assert connects == [] and _state(world.db.parent) == before
    assert not world.work.exists() or not any(world.work.iterdir())


def _count_connects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def refusing(database: Any, *_a: Any, **_k: Any) -> sqlite3.Connection:
        seen.append(str(database))
        raise AssertionError("a connection was opened")

    monkeypatch.setattr(gc.sqlite3, "connect", refusing)
    return seen


OLD_NS = 1_000_000_000_000_000_000  # an mtime far in the past, so any later write differs


def _grow(db: Path, real_connect: Any) -> None:
    with closing(real_connect(str(db))) as conn:
        conn.executemany(
            "INSERT INTO price_bars_cache VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(f"Z{i}", "TW", "2026-11-02", "1", "1", "1", "1", 1, "TWD", "y", "a", "b")
             for i in range(3000)],
        )  # fmt: skip
        conn.commit()


def _touch_same_size(db: Path, real_connect: Any) -> None:
    size = db.stat().st_size
    with closing(real_connect(str(db))) as conn:
        conn.execute("UPDATE portfolio SET cash = '1111111.11'")  # same length as the old value
        conn.commit()
    assert db.stat().st_size == size  # the write really is a same-size, mtime-only one


def _side_wal(db: Path, _real_connect: Any) -> None:
    Path(f"{db}-wal").write_bytes(b"x")


def _side_journal(db: Path, _real_connect: Any) -> None:
    Path(f"{db}-journal").write_bytes(b"x")


MUTATIONS = {
    "size": _grow,
    "mtime_only": _touch_same_size,
    "wal_appears": _side_wal,
    "journal_appears": _side_journal,
}


def _mutate_during_backup(
    monkeypatch: pytest.MonkeyPatch, world: World, how: str, *, then_fail: bool = False
) -> None:
    """Change the main database while the backup runs: between the source open and the copy."""
    real_connect = sqlite3.connect
    calls: list[str] = []

    def connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        calls.append(str(database))
        if len(calls) == 2:  # the second connection is the copy's: the backup is under way
            MUTATIONS[how](world.db, real_connect)
            if then_fail:
                raise sqlite3.OperationalError("synthetic failure while copying")
        conn: sqlite3.Connection = real_connect(database, *args, **kwargs)
        return conn

    monkeypatch.setattr(gc.sqlite3, "connect", connect)


@pytest.mark.parametrize("how", sorted(MUTATIONS))
def test_a_change_of_the_main_database_during_the_copy_deletes_the_copy_then_stops(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    world = make_world(tmp_path)
    os.utime(world.db, ns=(OLD_NS, OLD_NS))
    _mutate_during_backup(monkeypatch, world, how)
    events: list[str] = []
    copy_dir = world.work / "copy"

    def remover(path: Path) -> None:
        events.append(f"delete:{path.name}")
        gc.remove_path(path)

    real_say = gc.say

    def say(text: str) -> None:
        events.append("say")
        assert not copy_dir.exists()  # the copy is gone before the stop is shown
        real_say(text)

    monkeypatch.setattr(gc, "say", say)
    code, lines, err = run(world, capsys, remover=remover)
    assert (code, lines, err) == (3, [STOPS["db_in_use"]], "")
    assert events[-1] == "say" and "delete:stock-desk.db" in events
    assert events.index("say") == len(events) - 1  # nothing was shown before the deletes
    assert not any(x.startswith(("result=", "months_", "period_")) for x in lines)
    assert world.calendar.urls == [] and not world.opened
    no_residue(world)


@pytest.mark.parametrize("how", sorted(MUTATIONS))
def test_when_the_delete_also_fails_the_copy_stop_is_shown_not_the_changed_file_stop(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    world = make_world(tmp_path)
    os.utime(world.db, ns=(OLD_NS, OLD_NS))
    _mutate_during_backup(monkeypatch, world, how)

    def remover(path: Path) -> None:
        if path.name == "stock-desk.db":
            raise PermissionError("locked")
        gc.remove_path(path)

    code, lines, err = run(world, capsys, remover=remover)
    assert (code, lines, err) == (3, [COPY_STOP], "")
    assert STOPS["db_in_use"] not in lines
    assert world.calendar.urls == [] and not world.opened
    assert not list(world.work_root.glob("*/" + gc.PASTE_BACK_NAME))


@pytest.mark.parametrize("how", sorted(MUTATIONS))
def test_a_failed_backup_with_a_changed_main_database_shows_the_changed_file_stop(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    world = make_world(tmp_path)
    os.utime(world.db, ns=(OLD_NS, OLD_NS))
    _mutate_during_backup(monkeypatch, world, how, then_fail=True)
    only_stop(world, capsys, "db_in_use")


def test_a_failed_backup_with_an_unchanged_main_database_is_the_copy_could_not_be_made(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path)
    before = _state(world.db.parent)

    def failing(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        raise sqlite3.OperationalError("synthetic: no space left")

    monkeypatch.setattr(gc.sqlite3, "connect", failing)
    only_stop(world, capsys, "copy_failed")
    assert _state(world.db.parent) == before


def test_the_main_database_is_signed_by_stat_before_and_after_and_never_opened_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "main" / "stock-desk.db"
    write_main_db(db, ["2026-11-02"])
    signatures: list[Any] = []
    real = gc.file_signature

    def spy(path: Path) -> Any:
        signatures.append(real(path))
        return signatures[-1]

    monkeypatch.setattr(gc, "file_signature", spy)
    gc.make_copy(db, tmp_path / "copy")
    assert len(signatures) == 2 and signatures[0] == signatures[1]
    assert signatures[0] == (db.stat().st_size, db.stat().st_mtime_ns)


def test_the_main_database_uri_is_always_read_only_and_immutable(tmp_path: Path) -> None:
    db = tmp_path / "stock-desk.db"
    write_main_db(db, ["2026-11-02"])
    expected = f"{db.resolve().as_uri()}?mode=ro&immutable=1"
    assert gc.db_uri(db) == expected
    for suffix in ("-wal", "-journal"):  # no plain mode=ro branch remains
        Path(f"{db}{suffix}").write_bytes(b"x")
        assert gc.db_uri(db) == expected
    uri_parts = [
        n.value
        for n in ast.walk(_tree())
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "mode=ro" in n.value
        and n.value.lstrip().startswith("?")
    ]  # fmt: skip
    assert uri_parts == ["?mode=ro&immutable=1"]  # the only place a URI query is written


# --- measured premise of the stat and side-file check (supplement 10 point 7) -------------


def _sig(db: Path) -> tuple[int, int]:
    info = db.stat()
    return info.st_size, info.st_mtime_ns


def _wal_db(db: Path) -> None:
    with closing(sqlite3.connect(str(db))) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t (a TEXT)")
        conn.execute("INSERT INTO t VALUES ('x')")
        conn.commit()


def test_measured_in_wal_mode_a_writer_that_begins_to_write_makes_a_wal_file_appear(
    tmp_path: Path,
) -> None:
    db = tmp_path / "stock-desk.db"
    _wal_db(db)
    assert _names(tmp_path) == ["stock-desk.db"] and not gc.has_side_files(db)
    before = _sig(db)
    writer = sqlite3.connect(str(db))
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO t VALUES ('y')")
        assert gc.has_side_files(db)  # the side-file check sees the writer ...
        assert _sig(db) == before  # ... while the stat comparison alone would not
        writer.commit()
        assert gc.has_side_files(db) and _sig(db) == before  # committed, not yet checkpointed
    finally:
        writer.close()


def test_measured_in_wal_mode_a_write_finished_inside_the_window_changes_the_stat(
    tmp_path: Path,
) -> None:
    db = tmp_path / "stock-desk.db"
    _wal_db(db)
    os.utime(db, ns=(OLD_NS, OLD_NS))
    before = _sig(db)
    with closing(sqlite3.connect(str(db))) as writer:
        writer.execute("INSERT INTO t VALUES ('y')")
        writer.commit()
    assert not gc.has_side_files(db)  # the last connection closed: checkpointed, -wal removed
    assert _sig(db) != before  # the checkpoint wrote the main file: the stat comparison sees it


def test_measured_in_rollback_mode_a_writer_makes_a_journal_and_a_commit_changes_the_stat(
    tmp_path: Path,
) -> None:
    db = tmp_path / "stock-desk.db"
    with closing(sqlite3.connect(str(db))) as conn:
        conn.execute("CREATE TABLE t (a TEXT)")
        conn.execute("INSERT INTO t VALUES ('aaaa')")
        conn.commit()
    os.utime(db, ns=(OLD_NS, OLD_NS))
    before = _sig(db)
    writer = sqlite3.connect(str(db))
    try:
        writer.execute("BEGIN")
        writer.execute("UPDATE t SET a = 'bbbb'")
        assert gc.has_side_files(db) and _sig(db) == before  # -journal seen, stat not yet
        writer.commit()
    finally:
        writer.close()
    assert not gc.has_side_files(db)  # the journal is gone again ...
    assert _sig(db)[0] == before[0] and _sig(db)[1] != before[1]  # ... same size, new mtime


def test_known_limit_a_same_size_write_that_restores_the_mtime_is_not_detected(
    tmp_path: Path,
) -> None:
    # A limit of the method, written down rather than hidden: nothing in a (size, mtime) pair or
    # in the absence of side files can tell a same-size in-place write that also restores the
    # file's mtime from no write at all. It needs a deliberate utime call; an ordinary write moves
    # the mtime (measured: 200 back-to-back commits gave 200 different mtime_ns values).
    db = tmp_path / "stock-desk.db"
    with closing(sqlite3.connect(str(db))) as conn:
        conn.execute("CREATE TABLE t (a TEXT)")
        conn.execute("INSERT INTO t VALUES ('aaaa')")
        conn.commit()
    os.utime(db, ns=(OLD_NS, OLD_NS))
    before = _sig(db)
    with closing(sqlite3.connect(str(db))) as writer:
        writer.execute("UPDATE t SET a = 'bbbb'")
        writer.commit()
    os.utime(db, ns=(OLD_NS, OLD_NS))
    assert not gc.has_side_files(db) and _sig(db) == before
    with closing(sqlite3.connect(gc.db_uri(db), uri=True)) as reader:
        assert reader.execute("SELECT a FROM t").fetchall() == [("bbbb",)]  # it did change


# --- the launcher ---------------------------------------------------------------------------------

BAT = BACKEND.parent / "gap-check.bat"
# Frozen copy of apps/stock-desk/pipeline-acceptance.bat taken from commit
# d6816eb9d6a6ecda1d5aaa6c86e8d2a4b7a41425 (product/stock-desk), git blob
# 5b0b271e52f100a7f8584fe7e1ec9889c4cee717 (LF bytes, as stored in git; the old tests read the
# CRLF checkout, so the helper below restores CRLF in memory).
# It is a comparison baseline only. It is the single copy in the whole product line, it must never
# be updated, it does not represent any existing tool, and it must not be used to bring a tool
# back. The sha256 test pins it; the .gitattributes next to it marks it -text (no conversion).
PRECEDENT_BAT = BACKEND / "tests" / "fixtures" / "pipeline_acceptance_bat_frozen.txt"
PRECEDENT_SHA256 = "07265206e00c2dd6466c7a319d68484aad1634e7f64c1662638b7d506a43b4ad"
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


UV_MISSING_LINES = (
    "  echo [MISSING] uv was not found. Do not install or update anything yourself.",
    "  echo Tell the coordinator.",
)
ERROR_LINE = "  echo [ERROR] Cannot find the backend folder next to this file."
ERROR_SENTENCE_LINE = (
    "  echo Do not move or change any file or folder yourself; tell the coordinator."
)
ERROR_REPORT_NAME = "2026-11-20-兩份CEO文件判定RC313至RC324-風控.md"


def _backend_error_sentence_from_report() -> str:
    lines = report_path(ERROR_REPORT_NAME).read_text(encoding="utf-8").splitlines()
    found: set[str] = set()
    for index, line in enumerate(lines):
        if line.startswith("項目：RC-318"):
            following = lines[index + 1]
            assert following.startswith("定稿全文：`") and following.endswith("`")
            found.add(following[len("定稿全文：`") : -1])
    assert len(found) == 1
    return found.pop()


def test_the_bat_adds_the_risk_control_sentence_below_the_unchanged_backend_error_line() -> None:
    sentence = _backend_error_sentence_from_report()
    lines = BAT.read_bytes().decode("ascii").split("\r\n")
    at = lines.index(ERROR_LINE)
    assert lines[at + 1] == f"  echo {sentence}"
    assert lines[at + 2] == "  goto fail"
    assert sum(1 for x in lines if "[ERROR]" in x) == 1


def _uv_sentence_from_report() -> str:
    lines = report_path(UV_REPORT_NAME).read_text(encoding="utf-8").splitlines()
    found: set[str] = set()
    for index, line in enumerate(lines):
        if line.startswith("項目：RC-310"):
            following = lines[index + 1]
            assert following.startswith("定稿全文：`") and following.endswith("`")
            found.add(following[len("定稿全文：`") : -1])
    assert len(found) == 1
    return found.pop()


def test_the_bat_prints_the_risk_control_uv_sentence_verbatim_and_no_install_hint() -> None:
    sentence = _uv_sentence_from_report()
    lines = BAT.read_bytes().decode("ascii").split("\r\n")
    at = lines.index("where uv >nul 2>nul")
    assert lines[at + 1] == "if errorlevel 1 ("
    assert lines[at + 2] == f"  echo {sentence}"
    assert lines[at + 3] == "  echo Tell the coordinator."
    assert lines[at + 4] == "  goto fail"
    text = "\n".join(lines)
    assert "http" not in text and "install from" not in text and "run this script again" not in text
    assert sum(1 for x in lines if "[MISSING]" in x) == 1


def _precedent_lines() -> list[str]:
    raw = PRECEDENT_BAT.read_bytes()
    assert b"\r" not in raw  # stored with LF; CRLF is restored in memory only
    return raw.decode("ascii").replace("\n", "\r\n").split("\r\n")


def test_the_frozen_precedent_is_unchanged() -> None:
    assert hashlib.sha256(PRECEDENT_BAT.read_bytes()).hexdigest() == PRECEDENT_SHA256


def test_git_does_not_convert_the_frozen_precedent() -> None:
    result = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", str(PRECEDENT_BAT)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "text: unset" in result.stdout and "eol: unspecified" in result.stdout, result.stdout


def test_the_bat_matches_the_pipeline_acceptance_launcher_except_its_own_lines() -> None:
    lines = BAT.read_bytes().decode("ascii").split("\r\n")
    other = _precedent_lines()
    commands = [x for x in lines if not x.startswith("REM")]
    assert not any("/dev/null" in x for x in commands)
    assert "where uv >nul 2>nul" in lines
    own = {"title stock-desk gap-check", COMMAND, *UV_MISSING_LINES, ERROR_SENTENCE_LINE}
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
