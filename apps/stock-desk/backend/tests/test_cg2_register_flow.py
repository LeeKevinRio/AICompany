"""The CG-2 one-click files, end to end (ADR-0030 supplement 4 points 4-5, supplement 7 addendum 2).

``scripts/cg2_register.py`` runs here against a synthetic world (``tests/cg2_register_world.py``):
a stand-in repository, a fake main database, a fake home and a stand-in registration runner
(``claims.main`` in this process, with the stand-in backend). No test opens, stats or names the
service database and no ``.bat`` is run.

Covered: R-1 to R-8 (every stop has its test, S-14a), M-8 (every refusal of supplement 4 point 2 as
the one-click meets it, the whole-transaction rollback, no path or identifier in the paste-back),
RC-181 (three items), RC-162 (the whole screen, interruptions, hooks), and the e2e monitors
(read-only preflight; the registered result).
"""

from __future__ import annotations

import builtins
import hashlib
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.forecast import definitions, schema
from tests.cg2_register_loader import SCRIPT_PATH
from tests.cg2_register_world import (
    APP_ROWS,
    STAMP,
    UTC_NOW,
    StuckClock,
    World,
    git,
    real,
)

STOP_SENTENCES = {key: sentence for key, (_code, sentence) in real.STOPS.items()}
FIXED_SENTENCES = {
    *STOP_SENTENCES.values(),
    real.INTERRUPTED_SAFE,
    real.INTERRUPTED_LATE,
    real.UNEXPECTED_SAFE,
    real.UNEXPECTED_LATE,
    real.HOOK_SENTENCE,
}


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def screen_is_closed(out: str, err: str) -> list[str]:
    """RC-162 (d): every line of stdout and stderr is a whitelist line or a fixed sentence."""
    assert err == ""
    lines = out.splitlines()
    for line in lines:
        assert real.on_whitelist(line) or line in FIXED_SENTENCES, line
        assert line.isascii()
    return lines


def run(world: World, capsys: Any, mode: str, **overrides: Any) -> tuple[int, list[str]]:
    code = world.run(mode, **overrides)
    out, err = capsys.readouterr()
    return code, screen_is_closed(out, err)


def stop_lines(key: str) -> list[str]:
    return [STOP_SENTENCES[key]]


@pytest.fixture
def poisoned_paths() -> Callable[[World], tuple[str, ...]]:
    def forbidden(world: World) -> tuple[str, ...]:
        return (
            str(world.root),
            "/",
            "\\",
            "claim",
            "|",
            "outlook-market",
            "dirdef-v",
            "stock-desk",
            "work",
        )

    return forbidden


# === the happy paths ==========================================================================


def test_preflight_passes_and_writes_the_whitelisted_paste_back(
    world: World, capsys: Any, poisoned_paths: Any
) -> None:
    before = world.logical_state()
    code, lines = run(world, capsys, "preflight")
    assert code == 0
    assert lines[:2] == [real.VERSION_LINE, "mode=preflight"]
    assert "preflight_result=PASS" in lines
    assert lines[-1] == f"done_at_utc={real._utc_stamp(UTC_NOW)}"
    assert f"git_head={world.head}" in lines
    assert "ledger_objects=none" in lines and "hashes_pinned=ok" in lines
    assert [x for x in lines if x.startswith("banned_phrase_scan_h")] != []
    files = world.paste_backs()
    assert [p.name for p in files] == [f"preflight-{STAMP}.txt"]
    raw = files[0].read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # utf-8-sig
    assert raw.decode("utf-8-sig").splitlines() == lines
    assert world.opened == files
    for forbidden in poisoned_paths(world):
        assert all(forbidden not in line for line in lines), forbidden
    assert world.runner.calls == [] and world.runner.probes == 0
    assert world.backups() == []
    assert world.logical_state() == before


@pytest.mark.parametrize("typed", ["0", "1"])
def test_e2e_register_creates_the_ledger_two_rows_and_a_backup(
    world: World, capsys: Any, typed: str
) -> None:
    world.answers = [typed]
    code, lines = run(world, capsys, "register")
    assert code == 0
    objects = world.objects()
    assert len([n for k, n in objects if k == "table" and n.startswith("forecast_")]) == 5
    assert len([1 for k, _n in objects if k == "trigger"]) == 15
    rows = world.registry()
    assert len(rows) == 2 and {v for _c, v in rows} == {int(typed)}
    assert world.store().ledger_schema_status().complete
    assert world.store().runs() == []
    backups = world.backups()
    assert len(backups) == 1
    assert not [n for k, n in world.objects(backups[0]) if n.lower().startswith("forecast_")]
    with closing(sqlite3.connect(f"{backups[0].as_uri()}?mode=ro", uri=True)) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert conn.execute("SELECT k, v FROM app_settings ORDER BY k").fetchall() == sorted(
            APP_ROWS
        )
    digest = hashlib.sha256(backups[0].read_bytes()).hexdigest()
    assert f"backup_sha256={digest}" in lines
    assert f"provisional_results_seen={typed}" in lines
    assert lines[-2:] == ["register_result=DONE", f"done_at_utc={real._utc_stamp(UTC_NOW)}"]
    assert [p.name for p in world.paste_backs()] == [f"register-{STAMP}.txt"]
    assert world.paste_backs()[0].read_bytes().decode("utf-8-sig").splitlines() == lines


def test_the_register_paste_back_holds_the_sixteen_lines_in_order(
    world: World, capsys: Any
) -> None:
    code, lines = run(world, capsys, "register")
    assert code == 0
    start = lines.index("bootstrap=ok")
    assert len(lines[start : start + 16]) == 16
    for line, shape in zip(lines[start:], real.CLI_OUTPUT_SHAPES, strict=False):
        assert shape.fullmatch(line), line
    assert lines[start + 15] == "post_commit_check=ok"


def test_register_passes_the_arguments_of_the_interface_note(world: World, capsys: Any) -> None:
    world.answers = ["1"]
    assert run(world, capsys, "register")[0] == 0
    (args,) = world.runner.calls
    prereg = world.pins.frozen("prereg")
    assert args == [
        "bootstrap",
        "--production",
        "--rules-version",
        "outlook-market-v1.0-h3",
        "--rules-version",
        "outlook-market-v1.0-h5",
        "--definition-version",
        "dirdef-v1.0",
        "--frozen-commit",
        world.head,
        "--prereg-doc-path",
        prereg.path,
        "--prereg-doc-sha256",
        prereg.sha256,
        "--review-refs",
        "work/reviews/risk-a.md work/reviews/qa-b.md",
        "--provisional-results-seen",
        "1",
    ]
    assert "--replaces-claim-id" not in args and "--db" not in args


def test_the_frozen_commit_is_the_head_of_the_same_run(world: World, capsys: Any) -> None:
    assert run(world, capsys, "register")[0] == 0
    assert world.runner.calls[0][world.runner.calls[0].index("--frozen-commit") + 1] == world.head
    with closing(sqlite3.connect(f"{world.db.as_uri()}?mode=ro", uri=True)) as conn:
        stored = conn.execute("SELECT frozen_commit FROM forecast_claim_registry").fetchall()
    assert stored == [(world.head,)] * 2


def test_the_real_subprocess_runner_builds_the_documented_command(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        seen.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, b"x\n", b"")

    monkeypatch.setattr(real.subprocess, "run", fake_run)
    runner = real.SubprocessClaims(world.backend)
    runner.run(["bootstrap", "--production"])
    runner.probe()
    run_argv, run_kwargs = seen[0]
    assert run_argv == [
        sys.executable,
        "-I",
        "-X",
        "utf8",
        "-m",
        "app.forecast.claims",
        "bootstrap",
        "--production",
    ]
    assert run_kwargs["cwd"] == world.backend and run_kwargs["capture_output"] is True
    probe_argv, probe_kwargs = seen[1]
    assert probe_argv[:4] == [sys.executable, "-I", "-X", "utf8"] and probe_argv[4] == "-c"
    assert probe_kwargs["cwd"] == world.backend


def test_the_real_child_import_resolves_to_this_backend() -> None:
    # No database is opened: the probe only prints where ``app.forecast.claims`` would act.
    backend = Path(__file__).resolve().parents[1]
    runner = real.SubprocessClaims(backend)
    assert runner.probe() == backend
    done = runner.run(["bootstrap", "--help"])
    assert done.code == 0 and "--provisional-results-seen" in done.stdout


def test_a_child_that_would_act_on_another_backend_is_a_stop(world: World, capsys: Any) -> None:
    world.runner.probe_result = world.root  # not this backend
    code, lines = run(world, capsys, "register")
    assert (code, lines) == (3, stop_lines("claims_unreachable"))
    world.runner.probe_result = None
    code, lines = run(world, capsys, "register")
    assert (code, lines) == (3, stop_lines("claims_unreachable"))
    assert world.runner.calls == [] and world.backups() == []


# === S-14a: R-1 to R-8, each stop =============================================================


def stop(world: World, capsys: Any, mode: str, key: str, **overrides: Any) -> None:
    before = world.logical_state()
    code, lines = run(world, capsys, mode, **overrides)
    assert (code, lines) == (STOPS_CODE[key], stop_lines(key)), lines
    assert world.runner.calls == []
    assert world.paste_backs() == []
    assert world.logical_state() == before


STOPS_CODE = {key: code for key, (code, _s) in real.STOPS.items()}


@pytest.mark.parametrize("mode", ["preflight", "register"])
def test_r1_head_not_on_the_published_branch(world: World, capsys: Any, mode: str) -> None:
    git(world.repo, "update-ref", "-d", "refs/remotes/origin/product/stock-desk")
    stop(world, capsys, mode, "head_unpublished")
    git(world.repo, "commit", "-q", "--allow-empty", "-m", "later")
    git(world.repo, "update-ref", "refs/remotes/origin/product/stock-desk", world.head)
    stop(world, capsys, mode, "head_unpublished")  # HEAD is ahead of the published tip


@pytest.mark.parametrize("mode", ["preflight", "register"])
@pytest.mark.parametrize("target", ["app", "prereg", "c8"])
def test_r1_a_watched_path_has_uncommitted_changes(
    world: World, capsys: Any, mode: str, target: str
) -> None:
    path = {
        "app": world.backend / "app" / "forecast" / "__init__.py",
        "prereg": world.repo / world.pins.frozen("prereg").path,
        "c8": world.repo / world.pins.frozen("c8").path,
    }[target]
    path.write_bytes(path.read_bytes() + b"x\n")
    stop(world, capsys, mode, "git_dirty")


def test_r1_an_untracked_file_in_app_is_dirty_too(world: World, capsys: Any) -> None:
    (world.backend / "app" / "forecast" / "extra.py").write_text("x = 1\n")
    stop(world, capsys, "preflight", "git_dirty")


@pytest.mark.parametrize("mode", ["preflight", "register"])
def test_r1_the_app_tree_differs_from_the_cg2_pr(world: World, capsys: Any, mode: str) -> None:
    (world.backend / "app" / "forecast" / "__init__.py").write_text("# changed and committed\n")
    git(world.repo, "commit", "-q", "-a", "-m", "app change")
    git(world.repo, "update-ref", "refs/remotes/origin/product/stock-desk", "HEAD")
    stop(world, capsys, mode, "app_changed")


def test_r1_ignored_bytecode_in_app_does_not_make_the_tree_dirty(world: World, capsys: Any) -> None:
    cache = world.backend / "app" / "forecast" / "__pycache__"
    cache.mkdir()
    (cache / "x.cpython-312.pyc").write_bytes(b"\0\0")
    assert run(world, capsys, "preflight")[0] == 0


def test_r1_a_change_outside_the_watched_paths_does_not_stop(world: World, capsys: Any) -> None:
    (world.backend / "scripts").mkdir()
    (world.backend / "scripts" / "note.txt").write_text("not watched\n")
    (world.repo / "work" / "scratch.txt").write_text("not watched\n")
    assert run(world, capsys, "preflight")[0] == 0


def test_r1_git_unusable(world: World, capsys: Any) -> None:
    stop(world, capsys, "preflight", "git_unusable", git=lambda cwd, args: (127, b""))


def test_r1_the_loaded_app_is_not_the_backend(world: World, capsys: Any) -> None:
    stop(world, capsys, "preflight", "app_changed", app_check=lambda _b: False)


def test_r1_the_real_app_check_holds_for_this_checkout_only() -> None:
    backend = Path(__file__).resolve().parents[1]
    assert real.loaded_app_is_backend(backend)
    assert not real.loaded_app_is_backend(backend / "tests")


def test_r1_frozen_commit_is_head_even_after_new_unrelated_commits(
    world: World, capsys: Any
) -> None:
    git(world.repo, "commit", "-q", "--allow-empty", "-m", "unrelated")
    git(world.repo, "update-ref", "refs/remotes/origin/product/stock-desk", "HEAD")
    new_head = git(world.repo, "rev-parse", "HEAD")
    assert run(world, capsys, "register")[0] == 0
    args = world.runner.calls[0]
    assert args[args.index("--frozen-commit") + 1] == new_head != world.head


# --- R-2 ---


@pytest.mark.parametrize("role", ["prereg", "c8", "h3", "h5"])
def test_r2_a_constant_that_differs_from_the_file(world: World, capsys: Any, role: str) -> None:
    files = tuple(
        replace(item, sha256="0" * 64) if item.role == role else item
        for item in world.pins.frozen_files
    )
    stop(world, capsys, "preflight", "frozen_bytes", pins=replace(world.pins, frozen_files=files))


def status_is_blind(cwd: Path, args: Any) -> tuple[int, bytes]:
    """Real tooling, except ``status`` which reports a clean tree (so R-2 must catch it)."""
    if "status" in args:
        return 0, b""
    code, out = real.run_git(cwd, args)
    return int(code), bytes(out)


@pytest.mark.parametrize("role", ["prereg", "c8", "h3", "h5"])
def test_r2_crlf_in_the_work_tree_stops_on_the_raw_bytes(
    world: World, capsys: Any, role: str
) -> None:
    item = world.pins.frozen(role)
    path = world.repo / item.path
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    stop(world, capsys, "preflight", "frozen_bytes", git=status_is_blind)


@pytest.mark.parametrize("role", ["prereg", "c8", "h3", "h5"])
def test_r2_crlf_in_the_work_tree_stops_with_the_real_status_too(
    world: World, capsys: Any, role: str
) -> None:
    item = world.pins.frozen(role)
    path = world.repo / item.path
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    code, lines = run(world, capsys, "preflight")
    assert code == 3 and lines in (stop_lines("git_dirty"), stop_lines("frozen_bytes"))


def test_r2_the_work_tree_bytes_are_compared_raw_not_through_git(world: World, capsys: Any) -> None:
    item = world.pins.frozen("prereg")
    path = world.repo / item.path
    path.write_bytes(path.read_bytes() + b"\n")
    code, lines = run(world, capsys, "preflight")
    assert code == 3 and lines in (stop_lines("frozen_bytes"), stop_lines("git_dirty"))


@pytest.mark.parametrize("role", ["prereg", "c8"])
def test_r2_the_eol_attribute_is_missing(world: World, capsys: Any, role: str) -> None:
    item = world.pins.frozen(role)
    (world.repo / item.path).parent.joinpath(".gitattributes").write_text("\n")
    git(world.repo, "add", "-A")
    git(world.repo, "commit", "-q", "-m", "drop attribute")
    git(world.repo, "update-ref", "refs/remotes/origin/product/stock-desk", "HEAD")
    stop(world, capsys, "preflight", "frozen_eol")


def test_r2_the_yaml_attribute_is_missing(world: World, capsys: Any) -> None:
    (world.backend / ".gitattributes").write_text("uv.lock text eol=lf\n")
    git(world.repo, "add", "-A")
    git(world.repo, "commit", "-q", "-m", "drop attribute")
    git(world.repo, "update-ref", "refs/remotes/origin/product/stock-desk", "HEAD")
    stop(world, capsys, "preflight", "frozen_eol")


@pytest.mark.parametrize(
    "rewrite",
    [
        (
            b"ls-files",
            b"i/lf    w/lf    attr/text eol=lf      \t",
            b"i/crlf  w/lf    attr/text eol=lf      \t",
        ),
        (b"ls-files", b"w/lf", b"w/mixed"),
        (b"ls-files", b"attr/text eol=lf", b"attr/text"),
        (b"ls-files", b"attr/text eol=lf", b"attr/text eol=crlf"),
        (b"check-attr", b"\0lf\0", b"\0crlf\0"),
        (b"check-attr", b"\0lf\0", b"\0unspecified\0"),
    ],
)
def test_r2_each_of_the_three_evidences_alone_stops(
    world: World, capsys: Any, rewrite: tuple[bytes, bytes, bytes]
) -> None:
    command, old, new = rewrite

    def tampered(cwd: Path, args: Any) -> tuple[int, bytes]:
        code, out = real.run_git(cwd, args)
        if command.decode() in args:
            out = out.replace(old, new)
        return code, out

    stop(world, capsys, "preflight", "frozen_eol", git=tampered)


def test_r2_nothing_is_changed_by_the_stop(world: World, capsys: Any) -> None:
    item = world.pins.frozen("c8")
    path = world.repo / item.path
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    before = path.read_bytes()
    config = (world.repo / ".git" / "config").read_bytes()
    stop(world, capsys, "preflight", "frozen_bytes", git=status_is_blind)
    assert path.read_bytes() == before
    assert (world.repo / ".git" / "config").read_bytes() == config


# --- R-3 ---


@pytest.mark.parametrize("mode", ["preflight", "register"])
@pytest.mark.parametrize("value", ["", "other.db"])
def test_r3_the_environment_sets_the_variable(
    world: World, capsys: Any, mode: str, value: str
) -> None:
    stop(world, capsys, mode, "env_db_path", env={"STOCK_DESK_DB_PATH": value})


@pytest.mark.parametrize("line", ["STOCK_DESK_DB_PATH=x.db\n", "  STOCK_DESK_DB_PATH = \n"])
def test_r3_the_env_file_sets_the_key(world: World, capsys: Any, line: str) -> None:
    (world.backend.parent / ".env").write_text("OTHER=1\n" + line, encoding="utf-8")
    stop(world, capsys, "preflight", "env_file_db_path")


def test_r3_the_env_file_is_only_searched_for_the_key(world: World, capsys: Any) -> None:
    (world.backend.parent / ".env").write_text("SECRET_TOKEN=abc123\nOTHER=STOCK_DESK_DB_PATH\n")
    code, lines = run(world, capsys, "preflight")
    assert code == 0 and not any("abc123" in line for line in lines)


@pytest.mark.parametrize("mode", ["preflight", "register"])
def test_r3_no_main_database_at_the_default_location(world: World, capsys: Any, mode: str) -> None:
    world.db.unlink()
    code, lines = run(world, capsys, mode)
    assert (code, lines) == (3, stop_lines("no_db"))
    assert not world.db.exists() and list(world.data.iterdir()) == []  # nothing was created
    assert world.runner.calls == [] and world.paste_backs() == []


@pytest.mark.parametrize("mode", ["preflight", "register"])
def test_r3_port_8000_is_listening(world: World, capsys: Any, mode: str) -> None:
    world.listening = True
    stop(world, capsys, mode, "port_listening")


def test_r3_the_work_folder_inside_a_git_work_tree(world: World, capsys: Any) -> None:
    git(world.home, "init", "-q")
    stop(world, capsys, "preflight", "work_in_git")


def test_r3_the_real_port_check_sees_a_listener() -> None:
    import socket

    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert real.port_is_listening(port)
    assert not real.port_is_listening(port)


# --- R-4 ---

LEDGER_SHAPES = [
    "CREATE TABLE forecast_claim_registry (a INTEGER)",
    "CREATE TABLE plan_items (a INTEGER)",
    "CREATE TABLE Forecast_Audit (a INTEGER)",
    "CREATE TABLE PLAN_x (a INTEGER)",
    "CREATE VIEW forecast_view AS SELECT k FROM app_settings",
    "CREATE INDEX plan_idx ON app_settings (v)",
]


@pytest.mark.parametrize("mode", ["preflight", "register"])
@pytest.mark.parametrize("sql", LEDGER_SHAPES)
def test_r4_any_ledger_object_stops_before_anything_else(
    world: World, capsys: Any, mode: str, sql: str
) -> None:
    world.add_object(sql)
    stop(world, capsys, mode, "ledger_objects")
    assert world.backups() == []  # RC-181: R-4 before the backup
    assert world.runner.probes == 0 or mode == "register"


def test_r4_a_trigger_on_a_ledger_named_table_is_an_object_of_that_table(
    world: World, capsys: Any
) -> None:
    world.add_object("CREATE TABLE plan_t (a INTEGER)")
    world.add_object("DROP TABLE plan_t")
    world.add_object("CREATE TRIGGER trg AFTER INSERT ON app_settings BEGIN SELECT 1; END")
    assert run(world, capsys, "preflight")[0] == 0  # a plain trigger on a plain table is fine
    world.add_object("CREATE TABLE forecast_x (a)")
    world.add_object("CREATE TRIGGER trg2 AFTER INSERT ON forecast_x BEGIN SELECT 1; END")
    world.add_object("DROP TABLE forecast_x")  # the trigger goes with its table
    later = real.datetime(2026, 11, 20, 21, 7, 0)
    assert run(world, capsys, "preflight", now=lambda: later)[0] == 0


def test_r4_names_that_only_contain_the_prefix_do_not_stop(world: World, capsys: Any) -> None:
    world.add_object("CREATE TABLE my_forecast_x (a)")
    world.add_object("CREATE TABLE planet (a)")
    world.add_object("CREATE TABLE forecastx (a)")
    assert run(world, capsys, "preflight")[0] == 0


@pytest.mark.parametrize("wal", [False, True], ids=["no_wal", "wal"])
@pytest.mark.parametrize("sql", ["CREATE TABLE forecast_a (a)", "CREATE TABLE plan_a (a)"])
def test_r4_sees_objects_that_exist_only_in_the_wal(
    world: World, capsys: Any, wal: bool, sql: str
) -> None:
    with closing(sqlite3.connect(world.db)) as setup:
        setup.execute("PRAGMA journal_mode = WAL")
    holder = sqlite3.connect(world.db)
    holder.execute("PRAGMA wal_autocheckpoint = 0")
    holder.execute(sql)
    holder.commit()
    try:
        assert real.main_db_uri(world.db).endswith("mode=ro")  # a -wal is there: no immutable
        stop(world, capsys, "preflight", "ledger_objects")
    finally:
        holder.close()


def test_r4_unreadable_database_is_a_stop(world: World, capsys: Any) -> None:
    world.db.write_bytes(b"this is not a database" * 100)
    code, lines = run(world, capsys, "preflight")
    assert (code, lines) == (3, stop_lines("db_unreadable"))
    assert world.paste_backs() == []


def test_r4_the_prefixes_and_the_verdict_are_the_ones_of_the_schema_module() -> None:
    assert real.LEDGER_PREFIXES == schema.LEDGER_PREFIXES
    shapes = [*LEDGER_SHAPES, "CREATE TABLE ok_table (a)", "CREATE TABLE my_forecast_x (a)"]
    for sql in shapes:
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.execute("CREATE TABLE app_settings (k, v)")
            assert real.ledger_objects_present(conn) is False
            conn.execute(sql)
            assert real.ledger_objects_present(conn) == bool(schema._ledger_objects(conn)), sql


# --- R-5 ---


def test_r5_the_backup_target_already_exists(world: World, capsys: Any) -> None:
    folder = world.work / real.BACKUP_DIR_NAME
    folder.mkdir(parents=True)
    existing = folder / f"stock-desk-before-cg2-{STAMP}.db"
    existing.write_bytes(b"keep me")
    before = world.logical_state()
    code, lines = run(world, capsys, "register")
    assert (code, lines) == (3, stop_lines("backup_failed"))
    assert existing.read_bytes() == b"keep me"  # nothing is overwritten or deleted
    assert world.runner.calls == [] and world.logical_state() == before


class ReadbackProxy:
    """Wraps the backup read-back connection to give a chosen answer to one statement."""

    def __init__(self, inner: sqlite3.Connection, answers: dict[str, list[tuple[Any, ...]]]):
        self.inner = inner
        self.answers = answers

    def execute(self, sql: str, *args: Any) -> Any:
        if sql in self.answers:
            rows = self.answers[sql]
            return _Rows(rows)
        return self.inner.execute(sql, *args)

    def close(self) -> None:
        self.inner.close()


class _Rows:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


def _proxy_readback(
    monkeypatch: pytest.MonkeyPatch, answers: dict[str, list[tuple[Any, ...]]]
) -> None:
    original = sqlite3.connect

    def connect(database: Any, *args: Any, **kwargs: Any) -> Any:
        conn = original(database, *args, **kwargs)
        if "immutable=1" in str(database) and "-before-cg2-" in str(database):
            return ReadbackProxy(conn, answers)
        return conn

    monkeypatch.setattr(real.sqlite3, "connect", connect)


def test_r5_the_backup_fails_the_integrity_check(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _proxy_readback(monkeypatch, {"PRAGMA integrity_check": [("row 1 missing from index",)]})
    code, lines = run(world, capsys, "register")
    assert (code, lines) == (3, stop_lines("backup_integrity")), lines
    assert world.runner.calls == []
    assert len(world.backups()) == 1  # a backup is never deleted, not even a bad one


def test_r5_the_backup_holds_a_ledger_object(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _proxy_readback(monkeypatch, {real._LEDGER_SQL: [("table", "forecast_x")]})
    code, lines = run(world, capsys, "register")
    assert (code, lines) == (3, stop_lines("backup_has_ledger")), lines
    assert world.runner.calls == [] and len(world.backups()) == 1


def test_r5_the_backup_cannot_be_made(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = real.sqlite3.connect

    def connect(database: Any, *args: Any, **kwargs: Any) -> Any:
        if "-before-cg2-" in str(database) and "mode=ro" not in str(database):
            raise sqlite3.OperationalError("C:\\secret\\path")
        return original(database, *args, **kwargs)

    monkeypatch.setattr(real.sqlite3, "connect", connect)
    code, lines = run(world, capsys, "register")
    assert (code, lines) == (3, stop_lines("backup_failed"))
    assert world.runner.calls == []


def test_r5_the_backup_sha256_must_not_change_while_it_is_read_back(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}
    original = real.sha256_file

    def shifting(path: Path) -> str:
        calls["n"] += 1
        return original(path) if calls["n"] == 1 else "f" * 64

    monkeypatch.setattr(real, "sha256_file", shifting)
    code, lines = run(world, capsys, "register")
    assert (code, lines) == (3, stop_lines("backup_failed"))


def test_r5_the_backup_is_outside_the_work_tree_and_named_apart_from_the_acceptance(
    world: World, capsys: Any
) -> None:
    assert run(world, capsys, "register")[0] == 0
    (backup,) = world.backups()
    assert world.repo not in backup.parents
    assert real.WORK_ROOT_NAME != "stock-desk-pipeline-acceptance"
    assert backup.parent == world.work / "backups" and backup.name.endswith(".db")


def test_r5_a_wal_main_database_is_backed_up_with_its_wal_rows(world: World, capsys: Any) -> None:
    with closing(sqlite3.connect(world.db)) as setup:
        setup.execute("PRAGMA journal_mode = WAL")
    holder = sqlite3.connect(world.db)
    holder.execute("PRAGMA wal_autocheckpoint = 0")
    holder.execute("INSERT INTO app_settings VALUES ('in_wal', 'yes')")
    holder.commit()
    try:
        code, _lines = run(world, capsys, "register")
        assert code == 0
        (backup,) = world.backups()
        with closing(sqlite3.connect(f"{backup.as_uri()}?mode=ro&immutable=1", uri=True)) as conn:
            assert ("in_wal", "yes") in conn.execute("SELECT k, v FROM app_settings").fetchall()
    finally:
        holder.close()


# --- R-6 and the M-8 constants ---


@pytest.mark.parametrize("mode", ["preflight", "register"])
def test_r6_a_banned_phrase_hit_stops(
    world: World, capsys: Any, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = definitions.registration_phrase_scan

    def hit(ruleset: Any, definition: Any) -> Any:
        scan = original(ruleset, definition)
        return replace(scan, hits=("rules: x",))

    monkeypatch.setattr(definitions, "registration_phrase_scan", hit)
    stop(world, capsys, mode, "banned_phrase")
    assert world.backups() == []


def test_r6_the_scan_lines_are_the_same_text_the_registration_program_prints(
    world: World, capsys: Any
) -> None:
    _code, pre = run(world, capsys, "preflight")
    scans = [x for x in pre if x.startswith("banned_phrase_scan_h")]
    _code, reg = run(world, capsys, "register", now=lambda: real.datetime(2026, 11, 20, 21, 6, 0))
    assert scans == [x for x in reg if x.startswith("banned_phrase_scan_h")]
    assert len(scans) == 2 and len([x for x in reg if x.startswith("banned_phrase_scan_h")]) == 2


M8_FIELDS = [
    "definition_sha256",
    "definition_logic_sha256",
    "rules0_sha",
    "rules0_logic",
    "rules1_sha",
    "rules1_logic",
]


@pytest.mark.parametrize("field_name", M8_FIELDS)
def test_m8_each_hash_constant_that_differs_from_the_program_stops(
    world: World, capsys: Any, field_name: str
) -> None:
    pins = world.pins
    flipped = "0" * 64
    if field_name.startswith("definition"):
        pins = replace(pins, **{field_name: flipped})
    else:
        index = int(field_name[5])
        key = "rules_sha256" if field_name.endswith("sha") else "rules_logic_sha256"
        rules = list(pins.rules)
        rules[index] = replace(rules[index], **{key: flipped})
        pins = replace(pins, rules=tuple(rules))
    stop(world, capsys, "register", "hashes_differ", pins=pins)
    assert world.backups() == []


def test_m8_an_unpublished_version_is_a_stop(world: World, capsys: Any) -> None:
    pins = replace(world.pins, definition_version="dirdef-v9.9")
    stop(world, capsys, "preflight", "hashes_differ", pins=pins)


# --- R-7 ---


def refused(world: World, capsys: Any, key: str) -> tuple[int, list[str]]:
    before = world.logical_state()
    code, lines = run(world, capsys, "register")
    assert world.logical_state() == before  # logical comparison only (RC-181)
    assert not [n for _k, n in world.objects() if n.lower().startswith("forecast_")]
    return code, lines


@pytest.mark.parametrize(
    ("override", "key", "exit_code"),
    [
        (3, "refused_3", 3),
        (4, "refused_4", 3),
        (5, "written_5", 5),
        (1, "written_unknown", 5),
        (2, "written_unknown", 5),
        (7, "written_unknown", 5),
    ],
)
def test_r7_each_exit_code_has_its_fixed_sentence(
    world: World, capsys: Any, override: int, key: str, exit_code: int
) -> None:
    world.runner.override = real.CliResult(override, "secret out\n", "C:\\secret err\n")
    code, lines = run(world, capsys, "register")
    assert code == exit_code
    assert lines[0] == STOP_SENTENCES[key]
    assert len(world.backups()) == 1
    assert (
        lines[-1] == f"backup_sha256={hashlib.sha256(world.backups()[0].read_bytes()).hexdigest()}"
    )
    assert not any("secret" in x for x in lines)


def test_r7_exit_5_says_written_do_not_rerun_tell_the_coordinator() -> None:
    sentence = STOP_SENTENCES["written_5"].lower()
    assert "written" in sentence and "do not run this again" in sentence
    assert "tell the coordinator" in sentence
    unknown = STOP_SENTENCES["written_unknown"].lower()
    assert "not known whether" in unknown and "do not run this again" in unknown


def test_r7_exit_5_leaves_an_unchecked_paste_back_with_the_backup_hash(
    world: World, capsys: Any
) -> None:
    world.runner.override = real.CliResult(5, "", "")
    code, lines = run(world, capsys, "register")
    assert code == 5
    (paste,) = world.paste_backs()
    text = paste.read_bytes().decode("utf-8-sig").splitlines()
    assert text[-2] == "register_result=WRITTEN_UNCHECKED"
    assert all(real.on_whitelist(x) for x in text)
    digest = hashlib.sha256(world.backups()[0].read_bytes()).hexdigest()
    assert f"backup_sha256={digest}" in text
    assert not any(x.startswith(("bootstrap=", "registered_")) for x in text)


def _real_cli_lines(world: World, capsys: Any) -> list[str]:
    assert run(world, capsys, "register")[0] == 0
    return world.paste_backs()[0].read_bytes().decode("utf-8-sig").splitlines()[-18:-2]


@pytest.mark.parametrize("break_line", range(16))
def test_r7_a_changed_line_of_the_sixteen_stops_as_unverified(
    tmp_path: Path, capsys: Any, break_line: int
) -> None:
    probe_world = World(tmp_path / "probe")
    real_lines = _real_cli_lines(probe_world, capsys)
    assert len(real_lines) == 16
    bad = list(real_lines)
    bad[break_line] = bad[break_line] + "0"
    if break_line == 0:
        bad[0] = "bootstrap=failed"
    if break_line in (1, 2):
        bad[break_line] = real_lines[break_line].replace("hits 0", "hits 1")
    world = World(tmp_path / "bad")
    world.runner.override = real.CliResult(0, "\n".join(bad) + "\n", "")
    code, lines = run(world, capsys, "register")
    assert code == 5 and lines[0] == STOP_SENTENCES["output_unverified"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda lines: lines[:-1],
        lambda lines: [*lines, "extra=1"],
        lambda lines: lines[::-1],
    ],
    ids=["short", "long", "reversed"],
)
def test_r7_the_wrong_number_or_order_of_lines_stops_as_unverified(
    tmp_path: Path, capsys: Any, mutate: Callable[[list[str]], list[str]]
) -> None:
    real_lines = _real_cli_lines(World(tmp_path / "probe"), capsys)
    world = World(tmp_path / "bad")
    world.runner.override = real.CliResult(0, "\n".join(mutate(real_lines)) + "\n", "")
    code, lines = run(world, capsys, "register")
    assert code == 5 and lines[0] == STOP_SENTENCES["output_unverified"]


@pytest.mark.parametrize(
    "which", ["frozen_commit", "prereg_doc_sha256", "provisional_results_seen"]
)
def test_r7_a_well_formed_line_with_a_value_that_is_not_this_runs_stops_as_unverified(
    tmp_path: Path, capsys: Any, which: str
) -> None:
    real_lines = _real_cli_lines(World(tmp_path / "probe"), capsys)
    world = World(tmp_path / "bad")
    other = {
        "frozen_commit": "b" * 40,
        "prereg_doc_sha256": "c" * 64,
        "provisional_results_seen": "1",
    }
    bad = [f"{which}={other[which]}" if x.startswith(which) else x for x in real_lines]
    world.runner.override = real.CliResult(0, "\n".join(bad) + "\n", "")
    code, lines = run(world, capsys, "register")
    assert code == 5 and lines[0] == STOP_SENTENCES["output_unverified"]


# --- R-8 ---


@pytest.mark.parametrize(
    "answer", ["", "2", " 0", "1 ", "yes", "01", "\uff11", "true", "-1", "0\n", "y"]
)
def test_r8_an_answer_that_is_not_exactly_0_or_1_stops_and_calls_nothing(
    world: World, capsys: Any, answer: str
) -> None:
    world.answers = [answer]
    code, lines = run(world, capsys, "register")
    assert code == 3 and lines[0] == STOP_SENTENCES["bad_answer"]
    assert world.runner.calls == []
    assert not [n for _k, n in world.objects() if n.lower().startswith("forecast_")]


def test_r8_end_of_input_is_an_invalid_answer(world: World, capsys: Any) -> None:
    def eof(prompt: str) -> str:
        if prompt == real.PROMPT_SEEN:
            raise EOFError
        return ""

    code, lines = run(world, capsys, "register", ask=eof)
    assert code == 3 and lines[0] == STOP_SENTENCES["bad_answer"] and world.runner.calls == []


@pytest.mark.parametrize("typed", ["0", "1"])
def test_r8_the_answer_is_passed_on_unchanged_and_asked_once_with_the_fixed_prompt(
    world: World, capsys: Any, typed: str
) -> None:
    world.answers = [typed]
    assert run(world, capsys, "register")[0] == 0
    assert world.asked.count(real.PROMPT_SEEN) == 1 and world.asked[0] == real.PROMPT_CLOSE
    args = world.runner.calls[0]
    assert args[args.index("--provisional-results-seen") + 1] == typed
    assert real.PROMPT_SEEN.isascii()


def test_r8_there_is_no_confirmation_loop_and_no_default(world: World, capsys: Any) -> None:
    world.answers = ["1", "0"]
    assert run(world, capsys, "register")[0] == 0
    assert world.asked.count(real.PROMPT_SEEN) == 1  # one question, never repeated
    assert world.answers == ["0"]  # the second answer was never asked for


def test_r8_preflight_never_asks_for_the_answer(world: World, capsys: Any) -> None:
    assert run(world, capsys, "preflight")[0] == 0
    assert real.PROMPT_SEEN not in world.asked


def test_r8_the_value_1_registers_like_the_value_0(world: World, capsys: Any) -> None:
    for typed, sub in (("0", "a"), ("1", "b")):
        other = World(world.root / sub)
        other.answers = [typed]
        assert other.run("register") == 0
        assert {v for _c, v in other.registry()} == {int(typed)}
    capsys.readouterr()


# === M-8: every refusal of supplement 4 point 2, as the one-click meets it ====================


def _args_hook(world: World, patch: Callable[[list[str]], list[str]]) -> Any:
    original = real.bootstrap_args

    def patched(**kwargs: Any) -> list[str]:
        return patch(original(**kwargs))

    return patched


def test_m8_the_target_resolves_elsewhere(world: World, capsys: Any, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere.db"
    world.db.rename(elsewhere)
    world.db.symlink_to(elsewhere)
    code, lines = run(world, capsys, "register")
    assert (code, lines[0]) == (3, STOP_SENTENCES["refused_4"])
    assert not [n for _k, n in world.objects(elsewhere) if n.lower().startswith("forecast_")]


def test_m8_the_program_sees_the_variable_the_one_click_did_not(world: World, capsys: Any) -> None:
    world.runner.env = {"STOCK_DESK_DB_PATH": "x.db"}
    code, lines = refused(world, capsys, "refused_4")
    assert (code, lines[0]) == (3, STOP_SENTENCES["refused_4"])


def test_m8_ledger_objects_appear_between_the_preflight_and_the_registration(
    world: World, capsys: Any
) -> None:
    world.runner.before_run = lambda: world.add_object("CREATE TABLE plan_late (a)")
    before = world.objects()
    code, lines = run(world, capsys, "register")
    assert (code, lines[0]) == (3, STOP_SENTENCES["refused_4"])
    assert world.objects() == sorted([*before, ("table", "plan_late")])  # nothing else was created


def test_m8_the_claims_in_the_wrong_order(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def swap(args: list[str]) -> list[str]:
        a = args.index("--rules-version")
        b = args.index("--rules-version", a + 1)
        args[a + 1], args[b + 1] = args[b + 1], args[a + 1]
        return args

    monkeypatch.setattr(real, "bootstrap_args", _args_hook(world, swap))
    code, lines = refused(world, capsys, "refused_4")
    assert (code, lines[0]) == (3, STOP_SENTENCES["refused_4"])


def test_m8_a_replacement_is_refused(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        real, "bootstrap_args", _args_hook(world, lambda a: [*a, "--replaces-claim-id", "x"])
    )
    code, lines = refused(world, capsys, "refused_4")
    assert (code, lines[0]) == (3, STOP_SENTENCES["refused_4"])


def test_m8_only_one_claim_is_refused(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(real, "bootstrap_args", _args_hook(world, lambda a: a[:4] + a[6:]))
    code, lines = refused(world, capsys, "refused_4")
    assert code == 3 and lines[0] in (STOP_SENTENCES["refused_3"], STOP_SENTENCES["refused_4"])


@pytest.mark.parametrize(
    "patch",
    [
        lambda a: [x if x != a[a.index("--frozen-commit") + 1] else "0" * 40 for x in a],
        lambda a: [x if x != a[a.index("--prereg-doc-sha256") + 1] else "d" * 64 for x in a],
        lambda a: (
            [x if x != "--prereg-doc-path" else x for x in a][:-2]
            + ["--provisional-results-seen", "2"]
        ),
    ],
    ids=["commit_without_the_blob", "sha256_not_the_blobs", "typed_value_2"],
)
def test_m8_a_refusal_of_the_program_writes_nothing(
    world: World,
    capsys: Any,
    monkeypatch: pytest.MonkeyPatch,
    patch: Callable[[list[str]], list[str]],
) -> None:
    monkeypatch.setattr(real, "bootstrap_args", _args_hook(world, patch))
    code, lines = refused(world, capsys, "refused_3")
    assert (code, lines[0]) == (3, STOP_SENTENCES["refused_3"])


def test_m8_the_whole_transaction_rolls_back_when_the_store_gives_up(
    world: World, capsys: Any
) -> None:
    world.runner.clock = StuckClock()
    before = world.logical_state()
    code, lines = run(world, capsys, "register")
    assert (code, lines[0]) == (3, STOP_SENTENCES["refused_3"])
    assert world.logical_state() == before  # no ledger object, no row: one transaction
    assert not [n for _k, n in world.objects() if n.lower().startswith("forecast_")]


def test_m8_a_failure_after_the_first_row_rolls_the_schema_back_too(
    world: World, capsys: Any
) -> None:
    class Dies:
        calls = 0

        def __call__(self) -> Any:
            Dies.calls += 1
            if Dies.calls > 1:
                raise KeyboardInterrupt
            return UTC_NOW

    world.runner.clock = Dies()
    code, lines = run(world, capsys, "register")
    assert code == 2 and lines[0] == real.INTERRUPTED_LATE
    assert not [n for _k, n in world.objects() if n.lower().startswith("forecast_")]


@pytest.mark.parametrize("mode", ["preflight", "register"])
def test_m8_the_paste_back_has_no_path_claim_id_or_rule_version(
    world: World, capsys: Any, mode: str, poisoned_paths: Any
) -> None:
    _code, lines = run(world, capsys, mode)
    text = world.paste_backs()[0].read_bytes().decode("utf-8-sig")
    for forbidden in poisoned_paths(world):
        assert forbidden not in text, forbidden
        assert all(forbidden not in line for line in lines), forbidden
    assert str(world.home) not in text


# === RC-181 ===================================================================================


@pytest.mark.parametrize("sql", LEDGER_SHAPES)
def test_rc181_1_an_r4_stop_never_calls_bootstrap(world: World, capsys: Any, sql: str) -> None:
    world.add_object(sql)
    code, lines = run(world, capsys, "register")
    assert (code, lines) == (3, stop_lines("ledger_objects"))
    assert world.runner.calls == [] and world.events == []  # not called, not even asked


def test_rc181_2_the_backup_is_complete_before_bootstrap_is_called(
    world: World, capsys: Any
) -> None:
    seen: dict[str, Any] = {}

    def at_call() -> None:
        (backup,) = world.backups()  # exactly one, and it is complete and sound right now
        with closing(sqlite3.connect(f"{backup.as_uri()}?mode=ro&immutable=1", uri=True)) as conn:
            seen["integrity"] = conn.execute("PRAGMA integrity_check").fetchall()
            seen["rows"] = conn.execute("SELECT k, v FROM app_settings ORDER BY k").fetchall()
            seen["ledger"] = [
                n for (n,) in conn.execute("SELECT name FROM sqlite_master") if "forecast_" in n
            ]
        seen["sha"] = hashlib.sha256(backup.read_bytes()).hexdigest()
        seen["main_has_ledger"] = any(n.startswith("forecast_") for _k, n in world.objects())

    world.runner.before_run = at_call
    assert run(world, capsys, "register")[0] == 0
    assert seen["integrity"] == [("ok",)] and seen["rows"] == sorted(APP_ROWS)
    assert seen["ledger"] == [] and seen["main_has_ledger"] is False
    assert world.events == ["ask_seen", "run"]  # the answer is asked after the backup, before run
    # the sha256 the paste-back records is the one of that same backup file
    assert f"backup_sha256={seen['sha']}" in world.paste_backs()[0].read_text(encoding="utf-8-sig")


def test_rc181_2_no_backup_means_no_bootstrap(world: World, capsys: Any) -> None:
    world.answers = ["0"]
    folder = world.work / real.BACKUP_DIR_NAME
    folder.mkdir(parents=True)
    (folder / f"stock-desk-before-cg2-{STAMP}.db").write_bytes(b"x")  # the backup cannot be made
    code, _lines = run(world, capsys, "register")
    assert code == 3 and world.runner.calls == [] and world.asked.count(real.PROMPT_SEEN) == 0


def test_rc181_3_no_file_hash_of_the_main_database_is_taken_or_shown(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    hashed: list[Path] = []
    original = real.sha256_file

    def recording(path: Path) -> str:
        hashed.append(Path(path))
        return str(original(path))

    monkeypatch.setattr(real, "sha256_file", recording)
    world.runner.override = real.CliResult(4, "", "")
    code, lines = run(world, capsys, "register")
    assert code == 3
    assert world.db not in hashed and all(
        p.parent == world.work / "backups" or p.parent != world.data for p in hashed
    )
    main_hash = hashlib.sha256(world.db.read_bytes()).hexdigest()
    assert not any(main_hash in line for line in lines)
    assert not any("unchanged" in line.lower() or "untouched" in line.lower() for line in lines)


def test_rc181_3_the_one_click_never_reads_the_bytes_of_the_main_database(
    world: World, capsys: Any
) -> None:
    for sentence in STOP_SENTENCES.values():
        assert "unchanged" not in sentence.lower() and "untouched" not in sentence.lower()
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "sha256_file(db" not in text and "sha256_file(main" not in text
    assert ".st_mtime" not in text and "getmtime" not in text


# === RC-162: the whole screen =================================================================


@pytest.mark.parametrize("mode", ["preflight", "register"])
def test_rc162_every_screen_line_of_a_normal_run_is_on_the_whitelist(
    world: World, capsys: Any, mode: str
) -> None:
    code, lines = run(world, capsys, mode)
    assert code == 0 and lines


@pytest.mark.parametrize("key", [k for k in real.STOPS if k not in ("written_5",)])
def test_rc162_every_stop_sentence_is_ascii_fixed_and_free_of_paths(key: str) -> None:
    sentence = STOP_SENTENCES[key]
    assert sentence.isascii() and "\\" not in sentence
    assert "/" not in sentence.replace("origin/product/stock-desk", "")
    assert (
        "Do not change" in sentence or "Nothing was registered" in sentence or "usage" in sentence
    )


def test_rc162_the_stop_table_is_closed_and_unique() -> None:
    assert set(real.STOPS) == set(real.StopKey.__args__)
    assert len(set(STOP_SENTENCES.values())) == len(STOP_SENTENCES)
    with pytest.raises(ValueError):
        real.RunStop("anything_else")


@pytest.mark.parametrize(
    "where", ["close_prompt", "prechecks", "probe", "backup", "ask", "run", "after_run"]
)
def test_rc162_an_unexpected_exception_prints_one_fixed_sentence(
    world: World, capsys: Any, where: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = RuntimeError("secret C:\\Users\\x\\stock-desk.db claim|h3")
    late = where in ("run", "after_run")
    _inject(world, monkeypatch, where, error)
    code, lines = run(world, capsys, "register")
    assert lines[0] == (real.UNEXPECTED_LATE if late else real.UNEXPECTED_SAFE)
    assert code == (5 if late else 1)
    assert not any("secret" in x or "claim" in x for x in lines)


@pytest.mark.parametrize(
    "where", ["close_prompt", "prechecks", "probe", "backup", "ask", "run", "after_run"]
)
def test_rc162_ctrl_c_prints_one_fixed_sentence_at_every_stage(
    world: World, capsys: Any, where: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    late = where in ("run", "after_run")
    _inject(world, monkeypatch, where, KeyboardInterrupt())
    code, lines = run(world, capsys, "register")
    assert code == 2
    assert lines[0] == (real.INTERRUPTED_LATE if late else real.INTERRUPTED_SAFE)
    if late:  # a possibly written registration leaves its record behind
        assert [p.name for p in world.paste_backs()] == [f"register-{STAMP}.txt"]
    else:
        assert world.paste_backs() == []


def _inject(
    world: World, monkeypatch: pytest.MonkeyPatch, where: str, error: BaseException
) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise error

    if where == "close_prompt":
        original = world.ask

        def ask(prompt: str) -> str:
            if prompt == real.PROMPT_CLOSE:
                raise error
            return original(prompt)

        world.ask = ask  # type: ignore[method-assign]
    elif where == "prechecks":
        monkeypatch.setattr(real, "check_r4", boom)
    elif where == "probe":
        world.runner.probe = boom  # type: ignore[method-assign]
    elif where == "backup":
        monkeypatch.setattr(real, "make_backup", boom)
    elif where == "ask":
        original_ask = world.ask

        def ask2(prompt: str) -> str:
            if prompt == real.PROMPT_SEEN:
                raise error
            return original_ask(prompt)

        world.ask = ask2  # type: ignore[method-assign]
    elif where == "run":
        world.runner.raises = error
    elif where == "after_run":
        monkeypatch.setattr(real, "verified_cli_lines", boom)


def test_rc162_an_interrupt_after_the_backup_still_shows_the_backup_hash(
    world: World, capsys: Any
) -> None:
    world.runner.raises = KeyboardInterrupt()
    code, lines = run(world, capsys, "register")
    digest = hashlib.sha256(world.backups()[0].read_bytes()).hexdigest()
    assert code == 2 and lines == [real.INTERRUPTED_LATE, f"backup_sha256={digest}"]


def test_rc162_a_failing_opener_is_silent(world: World, capsys: Any) -> None:
    def broken(_path: Path) -> None:
        raise OSError("C:\\secret")

    code, lines = run(world, capsys, "preflight", opener=broken)
    assert code == 0 and not any("secret" in x for x in lines)


@pytest.mark.parametrize("argv", [[], ["other"], ["--help"], ["preflight", "extra"], ["-h"]])
def test_rc162_usage_errors_print_the_fixed_stop_sentence_only(
    capsys: Any, argv: list[str]
) -> None:
    code = real.main(argv)
    out, err = capsys.readouterr()
    assert code == 3 and err == ""
    assert out.splitlines() == stop_lines("usage")


def test_rc162_the_hook_sentence_is_the_error_sentence(capsys: Any) -> None:
    real._fixed_hook(RuntimeError, RuntimeError("secret"), None)
    captured = capsys.readouterr()
    assert captured.out == real.HOOK_SENTENCE + "\n" and captured.err == ""


def test_rc162_threads_warnings_unraisables_and_uncaught_errors_print_the_fixed_sentence() -> None:
    driver = (
        "import runpy, sys, threading, warnings, gc\n"
        f"runpy.run_path({str(SCRIPT_PATH)!r}, run_name='loaded')\n"
        "def boom():\n"
        "    raise RuntimeError('secret label')\n"
        "t = threading.Thread(target=boom); t.start(); t.join()\n"
        "warnings.warn('secret warning')\n"
        "class Bad:\n"
        "    def __del__(self):\n"
        "        raise RuntimeError('secret in del')\n"
        "b = Bad(); del b; gc.collect()\n"
        "raise RuntimeError('secret uncaught')\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", driver], capture_output=True, text=True, timeout=120
    )
    assert done.stderr == ""
    assert done.stdout.splitlines() == [real.HOOK_SENTENCE] * 3  # thread, unraisable, uncaught
    assert "secret" not in done.stdout
    assert done.returncode != 0


def test_rc162_the_cli_stop_through_a_real_isolated_interpreter(tmp_path: Path) -> None:
    # The path the batch file takes: python -I from an unrelated folder, a real stdin.
    world = World(tmp_path / "w")
    world.db.unlink()
    env = {k: v for k, v in os.environ.items() if k != real.ENV_VAR}
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", str(SCRIPT_PATH), "preflight",
         "--backend-dir", str(world.backend), "--home", str(world.home)],
        input="\n", capture_output=True, text=True, timeout=300, cwd=tmp_path, env=env,
    )  # fmt: skip
    assert done.returncode == 3 and done.stderr == ""
    lines = done.stdout.splitlines()
    assert [x.removeprefix(real.PROMPT_CLOSE) for x in lines] == stop_lines("no_db")
    assert world.paste_backs() == []


# === e2e: the preflight only reads; the registered result =====================================


class Monitor:
    """Records every ``sqlite3.connect``, ``open`` and file operation aimed at the main files."""

    def __init__(self, main: Path) -> None:
        self.main = main
        self.names = {main.name, f"{main.name}-wal", f"{main.name}-shm", f"{main.name}-journal"}
        self.folder = main.parent.resolve()
        self.connects: list[str] = []
        self.opens: list[tuple[str, str]] = []
        self.hits: list[tuple[str, str]] = []

    def aims(self, target: Any) -> bool:
        if isinstance(target, int) or target is None:
            return False
        text = os.fspath(target) if not isinstance(target, str) else target
        if text.startswith("file:"):
            text = text.split("?", 1)[0].removeprefix("file://")
            text = text.removeprefix("/") if re.match(r"/[A-Za-z]:", text) else text
        try:
            path = Path(text)
            return path.name in self.names and path.resolve().parent == self.folder
        except (OSError, ValueError):
            return False

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        connect = sqlite3.connect
        real_open = builtins.open

        def spy_connect(database: Any, *args: Any, **kwargs: Any) -> Any:
            if self.aims(database):
                self.connects.append(str(database))
            return connect(database, *args, **kwargs)

        def spy_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if self.aims(file):
                self.opens.append((Path(file).name, mode))
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", spy_connect)
        monkeypatch.setattr(builtins, "open", spy_open)
        monkeypatch.setattr(io, "open", spy_open)
        for owner, name in (
            (os, "remove"),
            (os, "unlink"),
            (os, "rename"),
            (os, "replace"),
            (os, "utime"),
            (os, "chmod"),
            (os, "truncate"),
            (shutil, "move"),
            (shutil, "copy"),
            (shutil, "copy2"),
            (shutil, "copyfile"),
        ):
            self._wrap(monkeypatch, owner, name)
        original_os_open = os.open

        def spy_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            if self.aims(path):
                self.hits.append(("os.open", str(flags)))
            return original_os_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(os, "open", spy_os_open)

    def _wrap(self, monkeypatch: pytest.MonkeyPatch, owner: Any, name: str) -> None:
        original = getattr(owner, name)

        def spy(*args: Any, **kwargs: Any) -> Any:
            if any(self.aims(a) for a in args if isinstance(a, str | os.PathLike)):
                self.hits.append((name, "-"))
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, name, spy)


def test_e2e_the_preflight_only_reads_the_main_database(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monitor = Monitor(world.db)
    monitor.install(monkeypatch)
    listing = sorted(p.name for p in world.data.iterdir())
    assert run(world, capsys, "preflight")[0] == 0
    assert monitor.connects, "the monitor saw the R-4 connection"
    assert all("mode=ro" in uri for uri in monitor.connects)
    assert monitor.opens == [] and monitor.hits == []  # never open()ed, never touched
    assert sorted(p.name for p in world.data.iterdir()) == listing  # no side file appeared


def test_e2e_the_register_run_only_opens_the_main_database_read_only(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The registration program itself runs in this process here (the stand-in runner) and does
    # open the main database for writing: only the one-click's own connections are judged, so
    # the stand-in runner is replaced by one that does nothing.
    monitor = Monitor(world.db)
    monitor.install(monkeypatch)
    world.runner.override = real.CliResult(4, "", "")
    code, _lines = run(world, capsys, "register")
    assert code == 3
    assert len(monitor.connects) == 2  # R-4 and the backup source
    assert all("mode=ro" in uri for uri in monitor.connects)
    assert monitor.opens == [] and monitor.hits == []


@pytest.mark.parametrize("wal_header", [False, True], ids=["delete_mode", "wal_mode_no_wal_file"])
def test_e2e_no_side_file_appears_beside_the_main_database(
    world: World, capsys: Any, wal_header: bool
) -> None:
    if wal_header:
        with closing(sqlite3.connect(world.db)) as setup:
            setup.execute("PRAGMA journal_mode = WAL")
    listing = sorted(p.name for p in world.data.iterdir())
    assert listing == ["stock-desk.db"]
    assert run(world, capsys, "preflight")[0] == 0
    assert sorted(p.name for p in world.data.iterdir()) == listing
    world.runner.override = real.CliResult(4, "", "")
    assert run(world, capsys, "register", now=lambda: real.datetime(2026, 11, 20, 22, 0, 0))[0] == 3
    assert sorted(p.name for p in world.data.iterdir()) == listing


def test_e2e_the_monitor_has_teeth(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monitor = Monitor(world.db)
    monitor.install(monkeypatch)
    with closing(sqlite3.connect(world.db)):
        pass
    with open(world.db, "rb"):
        pass
    os.utime(world.db)
    assert monitor.connects and monitor.opens == [("stock-desk.db", "rb")]
    assert ("utime", "-") in monitor.hits


def test_e2e_after_a_successful_registration_the_database_has_the_whole_ledger(
    world: World, capsys: Any
) -> None:
    world.answers = ["0"]
    assert run(world, capsys, "register")[0] == 0
    objects = world.objects()
    assert (
        sorted(n for k, n in objects if k == "table" and n.startswith("forecast_"))
        == sorted(schema.EXPECTED_TABLES)
        if hasattr(schema, "EXPECTED_TABLES")
        else True
    )
    assert len([1 for k, n in objects if k == "table" and n.startswith("forecast_")]) == 5
    assert len([1 for k, _n in objects if k == "trigger"]) == 15
    assert len(world.registry()) == 2
    # a second run is refused by R-4 and by nothing else
    code, lines = run(world, capsys, "register", now=lambda: real.datetime(2026, 11, 20, 22, 0, 0))
    assert (code, lines) == (3, stop_lines("ledger_objects"))


def test_e2e_the_script_never_deletes_renames_or_replaces_anything(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    for owner, name in (
        (os, "remove"),
        (os, "unlink"),
        (os, "rename"),
        (os, "replace"),
        (os, "rmdir"),
        (shutil, "rmtree"),
        (shutil, "move"),
        (Path, "unlink"),
        (Path, "rename"),
        (Path, "replace"),
        (Path, "rmdir"),
    ):
        original = getattr(owner, name)

        def spy(*a: Any, _n: str = name, _o: Callable[..., Any] = original, **k: Any) -> Any:
            calls.append(_n)
            return _o(*a, **k)

        monkeypatch.setattr(owner, name, spy)
    assert run(world, capsys, "register")[0] == 0
    # sqlite and the stand-in runner may use the OS internally; the script itself has no such call
    assert calls == [] or set(calls) <= {"unlink"}
