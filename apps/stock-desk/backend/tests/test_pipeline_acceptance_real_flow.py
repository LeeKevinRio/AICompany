"""Tests for the outer flow of ``scripts/pipeline_acceptance_real.py`` (ADR-0030 supplement 6).

The S-13b / S-13c / S-13d items each have tests here; the table of test names is in the
hand-over report. Everything runs on ``tmp_path`` worlds (:mod:`tests.pipeline_real_world`): a
synthetic "main" database, a fake backend folder, a fake home and a fake git. The real
``<backend>/data/``, ``.env`` and the network are never touched.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import io
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args
from urllib.parse import unquote, urlparse

import pytest

from app.forecast import recorder
from app.forecast.canonical import content_sha256
from app.outlook import inputs
from tests import forecast_pipeline_harness as harness
from tests.forecast_pipeline_harness import AcceptanceResult, Failure, render_summary
from tests.pipeline_real_world import (
    HEAD,
    LOCK_BYTES,
    FakeGit,
    World,
    flipped_return,
    make_world,
    real,
    yfinance_bars,
)

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND / "scripts" / "pipeline_acceptance_real.py"
UNEXPECTED = real.UNEXPECTED
INTERRUPTED = real.INTERRUPTED
ALL_STOPS = {
    **dict(real.OUTER_STOP_SENTENCES),
    **dict(real.STOP_SENTENCES),
}
FIXED_SENTENCES = {*ALL_STOPS.values(), UNEXPECTED, INTERRUPTED}
POISON = (
    "偏多",
    "偏空",
    "震盪",
    "insufficient",
    "unavailable",
    "bullish",
    "bearish",
    "range",
    "符合",
    "不一致",
    "B1",
    "B2",
    "B6",
    "B8",
    "T=",
    "claim_id",
    "session 數",
)


def decode(line: str) -> str:
    """The original text of a console line (the console shows non-ASCII as ``\\uXXXX``)."""
    assert line.isascii()
    return line.encode("ascii").decode("unicode_escape")


def on_whitelist(text: str) -> bool:
    return any(pattern.fullmatch(text) for _name, pattern in real.WHITELIST)


def assert_screen_is_closed(lines: list[str], err: str) -> None:
    """RC-162 (d): every console line is a whitelist line or a fixed sentence; nothing on stderr."""
    assert err == ""
    for line in lines:
        text = decode(line).removeprefix(real.PROMPT)
        assert on_whitelist(text) or text in FIXED_SENTENCES, text


def no_residue(world: World) -> None:
    for sub in ("copy", "p0", "p1"):
        assert not (world.work / sub).exists()


def hexless(lines: list[str]) -> list[str]:
    """The paste-back with every hash and every run count masked."""
    masked = [re.sub(r"[0-9a-f]{64}", "H", line) for line in lines]
    masked = [re.sub(r"(執行次數：.*?)=\d+", r"\1=N", line) for line in masked]
    return [re.sub(r"=\d+", "=N", line) if line.startswith("執行次數") else line for line in masked]


# --- the monitor of every file operation (addendum point 1 (b), RC-158a, TA C-1) -----------------


@dataclass
class Monitor:
    """Records the operations on the protected files and every ``sqlite3.connect`` target."""

    protected: list[Path]
    hits: list[tuple[str, str]] = field(default_factory=list)
    connects: list[Path] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    def hit(self, target: object) -> bool:
        if isinstance(target, int) or target is None:
            return False
        try:
            path = Path(str(os.fspath(target)))  # type: ignore[call-overload]
        except TypeError:
            return False
        for mine in self.protected:
            if path == mine:
                return True
            try:
                if path.exists() and mine.exists() and os.path.samefile(path, mine):
                    return True
            except OSError:
                continue
        return False

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monitor = self
        original_open = builtins.open

        def spy_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if monitor.hit(file):
                monitor.hits.append(("open", mode))
            return original_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", spy_open)
        monkeypatch.setattr(io, "open", spy_open)

        original_os_open = os.open

        def spy_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            if monitor.hit(path):
                monitor.hits.append(("os.open", str(flags)))
            return original_os_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(os, "open", spy_os_open)

        def wrap_paths(owner: Any, name: str, positions: tuple[int, ...]) -> None:
            original = getattr(owner, name)

            def spy(*args: Any, **kwargs: Any) -> Any:
                if any(len(args) > i and monitor.hit(args[i]) for i in positions):
                    monitor.hits.append((name, ""))
                return original(*args, **kwargs)

            monkeypatch.setattr(owner, name, spy)

        for name in ("remove", "unlink", "utime", "chmod", "truncate", "stat_noop"):
            if hasattr(os, name):
                wrap_paths(os, name, (0,))
        for name in ("rename", "replace"):
            wrap_paths(os, name, (0, 1))
        wrap_paths(shutil, "move", (0, 1))
        for name in ("copy", "copy2", "copyfile", "copytree", "copymode", "copystat"):
            wrap_paths(shutil, name, (1,))
        if sys.platform == "win32":  # pragma: no cover - msvcrt exists on Windows only
            import msvcrt

            wrap_paths(msvcrt, "locking", ())

        original_connect = sqlite3.connect

        def spy_connect(database: Any, *args: Any, **kwargs: Any) -> Any:
            text = os.fspath(database)
            path = Path(unquote(urlparse(text).path)) if text.startswith("file:") else Path(text)
            monitor.connects.append(path)
            monitor.events.append("connect")
            return original_connect(database, *args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", spy_connect)

        original_copy = real.copy_db_files

        def spy_copy(*args: Any, **kwargs: Any) -> Any:
            done = original_copy(*args, **kwargs)
            monitor.events.append("copy_done")
            return done

        monkeypatch.setattr(real, "copy_db_files", spy_copy)


@dataclass
class Happy:
    """One full, monitored run on a synthetic world (shared by many tests)."""

    code: int
    out: list[str]
    err: str
    paste_back: list[str]
    world: World
    monitor: Monitor
    outputs: list[list[str]]
    copy_existed_at_first_run: list[bool]
    main_before: dict[Path, tuple[str, int]]
    main_after: dict[Path, tuple[str, int]]
    bars: list[Any]
    sockets_used: list[str]


def _digests(paths: list[Path]) -> dict[Path, tuple[str, int]]:
    return {
        p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in paths
        if p.exists()
    }


def full_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    bars: list[Any] | None = None,
    wal_tail: int = 0,
    monitor_files: bool = True,
) -> Happy:
    """A complete run: the monitor on, the socket replaced, the harness result observed."""
    series = bars if bars is not None else yfinance_bars()
    world = make_world(tmp_path, bars=series, wal_tail=wal_tail)
    before = _digests(world.main_files)
    monitor = Monitor(protected=world.main_files)
    outputs: list[list[str]] = []
    copy_existed: list[bool] = []
    used: list[str] = []

    def spy_acceptance(folder: Path, **kwargs: Any) -> Any:
        copy_existed.append((world.work / "copy").exists())
        found = harness.run_acceptance(folder, **kwargs)
        outputs.append(list(found.output))
        return found

    def refuse(*args: object, **kwargs: object) -> None:
        used.append("socket")
        raise AssertionError("network use")

    if monitor_files:
        monitor.install(monkeypatch)
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    code, out, err = world.run(capsys, acceptance=spy_acceptance)
    monkeypatch.undo()
    paste = world.work / "paste-back.txt"
    lines = paste.read_text(encoding="utf-8-sig").splitlines() if paste.exists() else []
    result = Happy(
        code, out, err, lines, world, monitor, outputs, copy_existed, before,
        _digests(world.main_files), series, used,
    )  # fmt: skip
    world.close()
    return result


@pytest.fixture(scope="module")
def happy(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Happy]:
    patcher = pytest.MonkeyPatch()
    root = tmp_path_factory.mktemp("happy")

    class _Capsys:
        """The module-scope stand-in of ``capsys``: pytest's own capture of this fixture's run."""

        def __init__(self) -> None:
            self._out = io.StringIO()
            self._err = io.StringIO()

        def readouterr(self) -> Any:
            class _Read:
                out = self._out.getvalue()
                err = self._err.getvalue()

            return _Read()

    stand_in = _Capsys()
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stand_in._out, stand_in._err
    try:
        run = full_run(root, patcher, stand_in, monitor_files=True)  # type: ignore[arg-type]
    finally:
        sys.stdout, sys.stderr = saved
        patcher.undo()
    yield run


# --- S-13b point 1: the e2e monitor (TA C-1) ----------


def test_the_happy_run_succeeds_on_synthetic_data(happy: Happy) -> None:
    assert happy.code == 0
    assert happy.err == ""
    assert happy.paste_back[-3:-2] == ["cleanup=ok"]
    assert "acceptance_result=PASS" in happy.paste_back
    assert happy.world.opened == [happy.world.work / "paste-back.txt"]


def test_e2e_the_main_database_is_only_opened_rb_and_never_connected(happy: Happy) -> None:
    hits = happy.monitor.hits
    assert hits, "the monitor saw no operation on the main files"
    assert set(hits) == {("open", "rb")}, hits
    protected = set(happy.monitor.protected)
    assert all(path not in protected for path in happy.monitor.connects)
    for path in happy.monitor.connects:
        for mine in protected:
            if path.exists() and mine.exists():
                assert not os.path.samefile(path, mine)


def test_e2e_every_connect_target_is_the_copy_or_a_ledger(happy: Happy) -> None:
    work = happy.world.work
    allowed = {
        work / "copy" / "stock-desk.db",
        work / "p0" / "pipeline-acceptance.db",
        work / "p1" / "pipeline-acceptance.db",
    }
    assert happy.monitor.connects, "the monitor saw no connection"
    assert set(happy.monitor.connects) <= allowed


def test_e2e_copy_check_is_done_before_the_first_connect(happy: Happy) -> None:
    events = happy.monitor.events
    assert events[0] == "copy_done"
    assert events.index("copy_done") < events.index("connect")


def test_the_main_database_files_are_unchanged_in_bytes_and_mtime(happy: Happy) -> None:
    # RC-167b: before and after, the three main files have the same sha256 and the same mtime.
    assert happy.main_before and happy.main_before == happy.main_after


def test_the_run_completes_with_the_socket_replaced(happy: Happy) -> None:
    assert happy.code == 0
    assert happy.sockets_used == []


def test_the_copy_is_gone_before_the_first_run_acceptance(happy: Happy) -> None:
    assert happy.copy_existed_at_first_run == [False, False]


def test_after_the_run_only_the_paste_back_file_is_left(happy: Happy) -> None:
    assert sorted(p.name for p in happy.world.work.iterdir()) == ["paste-back.txt"]


def test_the_copy_files_do_not_exist_after_the_run(happy: Happy) -> None:
    for name in real.DB_FILES:
        assert not (happy.world.work / "copy" / name).exists()


def test_the_monitor_has_teeth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    victim = tmp_path / "main.db"
    victim.write_bytes(b"x")
    other = tmp_path / "other.db"
    monitor = Monitor(protected=[victim])
    monitor.install(monkeypatch)
    with open(victim, "ab"):
        pass
    os.utime(victim)
    os.chmod(victim, 0o600)
    os.rename(victim, other)
    os.replace(other, victim)
    shutil.copyfile(other if other.exists() else victim, tmp_path / "c.db")
    shutil.copyfile(victim, victim.with_name("main.db-copy"))
    os.truncate(victim, 0)
    os.remove(victim)
    names = {name for name, _ in monitor.hits}
    assert {"open", "utime", "chmod", "rename", "replace", "truncate", "remove"} <= names
    assert ("open", "ab") in monitor.hits
    assert "copyfile" not in names  # a copy FROM the file is a read; only a destination counts


# --- S-13b point 1: imports and the (c) boundaries ---


def _script_tree() -> ast.Module:
    return ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))


def test_the_script_has_no_forbidden_import_in_ast_and_at_run_time(happy: Happy) -> None:
    banned = ("app.services", "app.data.cache", "app.data.service", "app.data.providers")
    found: set[str] = set()
    for node in ast.walk(_script_tree()):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    assert not {m for m in found if any(m == b or m.startswith(b + ".") for b in banned)}
    # At run time, in a clean interpreter, after the module was imported and the flow was reached.
    code = (
        "import runpy, sys\n"
        f"runpy.run_path({str(SCRIPT_PATH)!r})\n"
        f"banned = {banned!r}\n"
        "hits = [m for m in sys.modules if any(m == b or m.startswith(b + '.') for b in banned)]\n"
        "sys.exit(3 if hits else 0)\n"
    )
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, timeout=120)
    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")


def test_the_script_has_no_network_call_in_the_flow() -> None:
    tree = _script_tree()
    sockets = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "socket"
    ]
    assert [s.attr for s in sockets] == ["create_connection"]
    call = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "socket.create_connection"
    )
    assert ast.unparse(call.args[0]).startswith("('127.0.0.1'")


# --- S-13b point 2: the stamps and the SELECT ----------


def test_the_flow_injects_20_hundred_taipei_stamps(happy: Happy) -> None:
    # The reader's own test checks the rule; here the whole run read the bars it hashed.
    expected = real.bars_sha256(
        [b.model_copy(update={"as_of": real.injected_as_of(b.date)}) for b in happy.bars]
    )
    line = next(x for x in happy.paste_back if x.startswith("bars_sha256="))
    assert line == f"bars_sha256={expected}"


def test_the_only_select_never_names_as_of_or_fetched_at() -> None:
    assert "as_of" not in real._SELECT_SQL and "fetched_at" not in real._SELECT_SQL


# --- S-13d: the one connection runs only query_only and the one SELECT ---


def test_ast_the_connection_runs_only_query_only_and_the_select() -> None:
    tree = _script_tree()
    function = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == real.read_twii_bars.__name__
    )
    executes = [
        n
        for n in ast.walk(function)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "execute"
    ]
    assert [ast.unparse(c.args[0]) for c in executes] == ["'PRAGMA query_only=ON'", "_SELECT_SQL"]
    whole = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "execute"
    ]
    assert len(whole) == 2


def _wal_copy_dir(root: Path) -> Path:
    """A byte copy (3 files) of a synthetic WAL main database whose last bar is only in the -wal."""
    world = make_world(root, wal_tail=1)
    target = root / "walcopy"
    target.mkdir()
    for path in world.main_files:
        shutil.copyfile(path, target / path.name)
    world.close()
    return target


def test_wal_copy_reads_the_uncheckpointed_row_and_adds_only_a_shm(tmp_path: Path) -> None:
    # S-13d bullet 1 and RC-167c: .db and -wal bytes unchanged; only a -shm may appear; the row
    # that exists only in the -wal is read.
    copy_dir = _wal_copy_dir(tmp_path)
    copy = copy_dir / "stock-desk.db"
    wal = copy_dir / "stock-desk.db-wal"
    (copy_dir / "stock-desk.db-shm").unlink(missing_ok=True)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (copy, wal)}
    listing = {p.name for p in copy_dir.iterdir()}

    bars = real.read_twii_bars(copy)

    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (copy, wal)} == before
    assert {p.name for p in copy_dir.iterdir()} - listing <= {"stock-desk.db-shm"}
    series = yfinance_bars()
    assert bars[-1].date == series[-1].date  # the bar that only the -wal holds
    assert len(bars) == len(series)


def test_a_copy_without_wal_gets_immutable_and_no_side_file(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    assert world.main_files[0].exists() and not world.main_files[1].exists()
    copy = tmp_path / "plain" / "stock-desk.db"
    copy.parent.mkdir()
    shutil.copyfile(world.db, copy)
    assert real.copy_uri(copy).endswith("?mode=ro&immutable=1")
    listing = {p.name for p in copy.parent.iterdir()}
    assert real.read_twii_bars(copy)
    assert {p.name for p in copy.parent.iterdir()} == listing


def test_the_wal_decision_is_made_in_one_place_from_the_copy() -> None:
    # The WAL reading (addendum 2) lives in copy_uri alone, decided by the copy beside the path.
    tree = _script_tree()
    users = [
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef)
        and any(isinstance(m, ast.Constant) and m.value == "immutable=1" for m in ast.walk(n))
        or isinstance(n, ast.FunctionDef)
        and any(isinstance(m, ast.Constant) and m.value == "&immutable=1" for m in ast.walk(n))
    ]
    assert users == ["copy_uri"]


def test_e2e_a_wal_main_database_is_copied_read_and_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = full_run(tmp_path, monkeypatch, capsys, wal_tail=3)
    assert run.code == 0 and run.err == ""
    assert [x for x in run.paste_back if x.startswith("copy_check=")] == ["copy_check=SAME"] * 3
    expected = real.bars_sha256(
        [b.model_copy(update={"as_of": real.injected_as_of(b.date)}) for b in run.bars]
    )
    assert f"bars_sha256={expected}" in run.paste_back  # the three -wal-only bars are in it
    assert set(run.monitor.hits) == {("open", "rb")}
    assert run.main_before == run.main_after  # RC-167b with a real -wal and -shm
    assert len(run.main_before) == 3
    assert [p.name for p in run.world.work.iterdir()] == ["paste-back.txt"]


# --- S-13b point 1 (e): every stop has a test; the copy is gone after each ---


def _expect_stop(
    world: World, code: int, out: list[str], err: str, sentence: str, calls: list[object]
) -> None:
    assert (code, err) == (3, "")
    assert out == [sentence]
    assert calls == []  # the harness was not called
    assert not (world.work / "paste-back.txt").exists()
    no_residue(world)
    assert world.opened == []


@pytest.fixture
def spy() -> tuple[list[object], Callable[..., Any]]:
    calls: list[object] = []

    def acceptance(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        raise AssertionError("the harness must not run")

    return calls, acceptance


def test_stop_env_db_path(tmp_path: Path, capsys: Any, spy: Any) -> None:
    world = make_world(tmp_path)
    code, out, err = world.run(capsys, env={real.ENV_VAR: "x"}, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["env_db_path"], spy[0])


def test_stop_env_file_db_path(tmp_path: Path, capsys: Any, spy: Any) -> None:
    world = make_world(tmp_path)
    (world.backend.parent / ".env").write_text("OTHER=1\nSTOCK_DESK_DB_PATH = fake\n")
    code, out, err = world.run(capsys, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["env_file_db_path"], spy[0])


def test_the_env_file_is_only_searched_for_the_key(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# STOCK_DESK_DB_PATH=commented\nVALUE=STOCK_DESK_DB_PATH=x\n")
    assert real.env_file_sets_db_path(env) is False
    assert real.env_file_sets_db_path(tmp_path / "missing") is False


def test_stop_no_db(tmp_path: Path, capsys: Any, spy: Any) -> None:
    world = make_world(tmp_path)
    for path in world.main_files:
        path.unlink(missing_ok=True)
    code, out, err = world.run(capsys, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["no_db"], spy[0])


def test_stop_port_listening(tmp_path: Path, capsys: Any, spy: Any) -> None:
    world = make_world(tmp_path)
    code, out, err = world.run(capsys, port_check=lambda: True, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["port_listening"], spy[0])


def test_stop_work_folder_inside_a_git_work_tree(tmp_path: Path, capsys: Any, spy: Any) -> None:
    world = make_world(tmp_path)
    (tmp_path / "home" / ".git").mkdir()
    code, out, err = world.run(capsys, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["work_in_git"], spy[0])


def test_stop_git_unusable(tmp_path: Path, capsys: Any, spy: Any) -> None:
    world = make_world(tmp_path)
    world.git = FakeGit(world.backend, unusable=True)
    code, out, err = world.run(capsys, git=world.git, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["git_unusable"], spy[0])


def test_stop_git_dirty(tmp_path: Path, capsys: Any, spy: Any) -> None:
    world = make_world(tmp_path)
    git = FakeGit(world.backend, dirty=True)
    code, out, err = world.run(capsys, git=git, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["git_dirty"], spy[0])


def test_stop_head_not_published(tmp_path: Path, capsys: Any, spy: Any) -> None:
    world = make_world(tmp_path)
    git = FakeGit(world.backend, published=False)
    code, out, err = world.run(capsys, git=git, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["head_unpublished"], spy[0])


def test_stop_eol_second_evidence(tmp_path: Path, capsys: Any, spy: Any) -> None:
    world = make_world(tmp_path)
    git = FakeGit(world.backend, crlf=True)
    code, out, err = world.run(capsys, git=git, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["eol_differs"], spy[0])


def test_stop_eol_bytes_differ_from_the_blob(tmp_path: Path, capsys: Any, spy: Any) -> None:
    world = make_world(tmp_path)
    (world.backend / "uv.lock").write_bytes(LOCK_BYTES.replace(b"\n", b"\r\n"))
    code, out, err = world.run(capsys, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["eol_differs"], spy[0])


def test_stop_copy_changed_while_copying(
    tmp_path: Path, capsys: Any, spy: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path)
    original = real._copy_bytes

    def tamper(source: Path, target: Path) -> None:
        original(source, target)
        with open(target, "ab") as handle:  # the COPY differs from its source
            handle.write(b"x")

    monkeypatch.setattr(real, "_copy_bytes", tamper)
    code, out, err = world.run(capsys, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["copy_changed"], spy[0])


def test_stop_copy_presence_differs(
    tmp_path: Path, capsys: Any, spy: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path, wal_tail=1)
    original = real._copy_bytes

    def lose(source: Path, target: Path) -> None:
        original(source, target)
        if target.name.endswith("-wal"):
            target.unlink()

    monkeypatch.setattr(real, "_copy_bytes", lose)
    code, out, err = world.run(capsys, acceptance=spy[1])
    world.close()
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["copy_changed"], spy[0])


def test_stop_guard_never_refuses(
    tmp_path: Path, capsys: Any, spy: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path)
    monkeypatch.setattr(real, "refuse_production", lambda *a, **k: None)
    code, out, err = world.run(capsys, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["guard_failed"], spy[0])


def test_stop_guard_refuses_the_ledger_too(
    tmp_path: Path, capsys: Any, spy: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path)

    def always(*args: object, **kwargs: object) -> None:
        raise real.HarnessRefused("x")

    monkeypatch.setattr(real, "refuse_production", always)
    code, out, err = world.run(capsys, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.OUTER_STOP_SENTENCES["guard_failed"], spy[0])


def test_the_guard_counter_example_holds_on_a_synthetic_backend(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    assert real.refusal_guard_holds(
        backend_dir=world.backend, work=world.work, cwd=world.root, env={}
    )


@pytest.mark.parametrize(
    "kind", ["no_rows", "unparseable_row", "demo_source", "foreign_source", "cache_short"]
)
def test_stop_of_the_reader_and_the_depth(tmp_path: Path, capsys: Any, spy: Any, kind: str) -> None:
    kwargs: dict[str, Any] = {}
    if kind == "no_rows":
        kwargs["bars"] = [b.model_copy(update={"symbol": "2330"}) for b in yfinance_bars(5)]
    elif kind == "demo_source":
        kwargs["last_source"] = "demo_synthetic"
    elif kind == "foreign_source":
        kwargs["last_source"] = "twse_snapshot"
    elif kind == "cache_short":
        kwargs["bars"] = yfinance_bars(120)
    world = make_world(tmp_path, **kwargs)
    if kind == "unparseable_row":
        with closing(sqlite3.connect(world.db)) as conn, conn:
            conn.execute("UPDATE price_bars_cache SET close = 'x' WHERE rowid = 5")
    code, out, err = world.run(capsys, acceptance=spy[1])
    _expect_stop(world, code, out, err, real.STOP_SENTENCES[kind], spy[0])


# --- RC-158c: the copy cannot be deleted ---


def _failing_remover(names: tuple[str, ...]) -> Callable[[Path], None]:
    def remover(path: Path) -> None:
        if path.name in names or path.name == "copy":
            raise PermissionError("locked")
        real.remove_path(path)

    return remover


def test_rc158c_a_copy_that_cannot_be_deleted_stops_before_the_harness(
    tmp_path: Path, capsys: Any, spy: Any
) -> None:
    world = make_world(tmp_path)
    code, out, err = world.run(
        capsys, remover=_failing_remover(("stock-desk.db",)), acceptance=spy[1]
    )
    assert code == 3 and err == ""
    assert out == [real.OUTER_STOP_SENTENCES["copy_not_deleted"]]
    assert out[0].isascii()
    assert spy[0] == []
    assert not (world.work / "paste-back.txt").exists()


def test_rc158c_only_the_shm_cannot_be_deleted(tmp_path: Path, capsys: Any, spy: Any) -> None:
    # Addendum 2 point 2 (d): a left-over -shm of the copy is the same stop.
    world = make_world(tmp_path, wal_tail=1)
    code, out, err = world.run(
        capsys, remover=_failing_remover(("stock-desk.db-shm",)), acceptance=spy[1]
    )
    world.close()
    assert code == 3 and err == ""
    assert out == [real.OUTER_STOP_SENTENCES["copy_not_deleted"]]
    assert spy[0] == []


def test_the_delete_is_retried_five_times_with_pauses(tmp_path: Path) -> None:
    target = tmp_path / "f"
    target.write_bytes(b"x")
    attempts: list[Path] = []
    pauses: list[float] = []

    def remover(path: Path) -> None:
        attempts.append(path)
        raise PermissionError("locked")

    assert real.delete_with_retry(target, remover, pauses.append) is False
    assert len(attempts) == 5 and pauses == [0.5] * 4
    seen: list[int] = []

    def flaky(path: Path) -> None:
        seen.append(1)
        if len(seen) < 3:
            raise PermissionError("locked")
        real.remove_path(path)

    assert real.delete_with_retry(target, flaky, lambda _s: None) is True
    assert not target.exists()


def test_a_copy_left_by_an_earlier_run_that_cannot_be_deleted_stops(
    tmp_path: Path, capsys: Any, spy: Any
) -> None:
    world = make_world(tmp_path)
    old = world.home / real.WORK_ROOT_NAME / "20260101-000000" / "copy"
    old.mkdir(parents=True)
    (old / "stock-desk.db").write_bytes(b"old")
    code, out, err = world.run(
        capsys, remover=_failing_remover(("stock-desk.db",)), acceptance=spy[1]
    )
    assert (code, err) == (3, "")
    assert out == [real.OUTER_STOP_SENTENCES["copy_not_deleted"]]
    assert spy[0] == []


# --- S-13b point 3: the result object, residue, the work folder ---


def test_ast_the_result_is_only_read_for_passed_and_rendered(happy: Happy) -> None:
    tree = _script_tree()
    function = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_ruleset"
    )
    attributes = [
        n.attr
        for n in ast.walk(function)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "result"
    ]
    assert attributes == ["passed"]
    renders = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "render_summary"
    ]
    assert len(renders) == 1 and ast.unparse(renders[0].args[0]) == "result"
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "result":
            assert node in ast.walk(function), "``result`` is used outside run_ruleset"
    assert {"where", "output", "failures", "compared", "matches", "records"}.isdisjoint(
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    )


def test_residue_of_earlier_runs_is_swept_and_other_folders_are_left(
    tmp_path: Path, capsys: Any, spy: Any
) -> None:
    world = make_world(tmp_path)
    root = world.home / real.WORK_ROOT_NAME
    old = root / "20260101-000000"
    for sub in ("copy", "p0", "p1"):
        (old / sub).mkdir(parents=True)
        (old / sub / "x.db").write_bytes(b"x")
    (old / "paste-back.txt").write_text("old paste back")
    keep = [
        root / "notes" / "p0" / "keep.txt",
        root / "20260101" / "copy" / "keep.txt",
        root / "20260101-000000-x" / "p1" / "keep.txt",
        root / "20260102-000000" / "other" / "keep.txt",
    ]
    for path in keep:
        path.parent.mkdir(parents=True)
        path.write_text("keep")
    bars = yfinance_bars()
    calls: list[int] = []

    def fake(folder: Path, **kwargs: Any) -> Any:
        calls.append(1)
        return AcceptanceResult(rules=kwargs["rules"].name, window=(), ledger_sha256="a" * 64)

    code, out, err = world.run(capsys, read_bars=lambda _p: bars, acceptance=fake)
    assert code == 0 and err == ""
    for sub in ("copy", "p0", "p1"):
        assert not (old / sub).exists()
    assert (old / "paste-back.txt").read_text() == "old paste back"
    assert all(p.read_text() == "keep" for p in keep)
    assert "cleanup=ok" in [decode(x) for x in out]


def test_a_stale_ledger_folder_that_cannot_be_deleted_reports_cleanup_failed(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path)
    old = world.home / real.WORK_ROOT_NAME / "20260101-000000" / "p0"
    old.mkdir(parents=True)
    bars = yfinance_bars()

    def fake(folder: Path, **kwargs: Any) -> Any:
        return AcceptanceResult(rules=kwargs["rules"].name, window=(), ledger_sha256="a" * 64)

    def remover(path: Path) -> None:
        if path == old:
            raise PermissionError("locked")
        real.remove_path(path)

    code, out, err = world.run(capsys, read_bars=lambda _p: bars, acceptance=fake, remover=remover)
    assert code == 0
    assert "cleanup=FAILED" in out


# --- S-13b point 4: the whitelist ---

H64 = "0123456789abcdef" * 4
WHITELIST_SAMPLES: dict[str, tuple[list[str], list[str]]] = {
    "header_1": ([harness.HEADER[0]], [harness.HEADER[0] + "x"]),
    "header_2": ([harness.HEADER[1]], [""]),
    "version": (["pipeline_acceptance_real version=1"], ["pipeline_acceptance_real version=2"]),
    "script_sha256_lf": ([f"script_sha256_lf={H64}"], [f"script_sha256_lf={H64[:-1]}"]),
    "harness_sha256_lf": ([f"harness_sha256_lf={H64}"], [f"harness_sha256_lf={H64}0"]),
    "git_head": ([f"git_head={'b' * 40}"], [f"git_head={'b' * 39}", f"git_head={'B' * 40}"]),
    "git_clean": (["git_clean=yes"], ["git_clean=no"]),
    "core_autocrlf": (
        [f"core_autocrlf={v}" for v in ("false", "unset", "input", "true", "other")],
        ["core_autocrlf=maybe", "core_autocrlf="],
    ),
    "eol_check": (["eol_check=ok"], ["eol_check=FAILED"]),
    "code_digest": ([f"code_digest={H64}"], ["code_digest=abc"]),
    "lockfile_sha256": ([f"lockfile_sha256={H64}"], ["lockfile_sha256="]),
    "definition_sha256": ([f"definition_sha256={H64}"], ["definition_sha256=x"]),
    "definition_logic_sha256": ([f"definition_logic_sha256={H64}"], ["definition_logic_sha256="]),
    "db_location": (["db_location=default"], ["db_location=C:\\x"]),
    "port_8000_listening": (["port_8000_listening=no"], ["port_8000_listening=yes"]),
    "copy_check": (
        ["copy_check=SAME", "copy_check=absent_both"],
        ["copy_check=DIFFERENT", "copy_check=PRESENCE_DIFFERS"],
    ),
    "refusal_guard": (["refusal_guard=ok"], ["refusal_guard=failed"]),
    "cache_depth": (["cache_depth=sufficient"], ["cache_depth=short", "cache_depth=336"]),
    "bars_sources": (["bars_sources=yfinance"], ["bars_sources=yfinance,demo", "bars_sources=x"]),
    "bars_sha256": ([f"bars_sha256={H64}"], [f"bars_sha256={H64}\n"]),
    "ruleset_result": (
        ["管線驗收 P-0：通過", "管線驗收 P-1：失敗"],
        ["管線驗收 P-2：通過", "管線驗收 P-0：偏多"],
    ),
    "run_counts": (
        ["執行次數：ok=21", "執行次數：error=1，ok=20"],
        ["執行次數：偏多=1", "執行次數：ok=x", "執行次數："],
    ),
    "failure_kinds": (
        ["失敗種類：無", "失敗種類：label_differs", "失敗種類：label_differs，vacuous_equality"],
        ["失敗種類：bullish", "失敗種類：label_differs, vacuous_equality", "失敗種類："],
    ),
    "ledger_sha256": ([f"暫存帳 sha256：{H64}"], ["暫存帳 sha256：12"]),
    "output_sha256": ([f"輸出 sha256：{H64}"], ["輸出 sha256：筆數"]),
    "acceptance_result": (
        ["acceptance_result=PASS", "acceptance_result=FAIL"],
        ["acceptance_result=ok"],
    ),
    "cleanup": (["cleanup=ok", "cleanup=FAILED"], ["cleanup=failed"]),
    "summary_lines_dropped": (
        ["summary_lines_dropped=0", "summary_lines_dropped=12"],
        ["summary_lines_dropped=-1"],
    ),
    "done_at_utc": (
        ["done_at_utc=2026-11-16T02:30:00Z"],
        ["done_at_utc=2026-11-16", "done_at_utc=today"],
    ),
}


def test_every_whitelist_shape_has_a_sample() -> None:
    assert {name for name, _p in real.WHITELIST} == set(WHITELIST_SAMPLES)


@pytest.mark.parametrize("name", [name for name, _p in real.WHITELIST])
def test_whitelist_shape(name: str) -> None:
    accepted, rejected = WHITELIST_SAMPLES[name]
    pattern = dict(real.WHITELIST)[name]
    for line in accepted:
        assert pattern.fullmatch(line), line
        assert real.apply_whitelist([line]) == ([line], 0)
    for line in rejected:
        assert not pattern.fullmatch(line), line


def test_unrelated_lines_are_dropped_and_counted_and_the_window_line_is_not_counted() -> None:
    lines = [
        "管線驗收 P-0：通過",
        "視窗定案 session 數：21",
        "筆數：5",
        "標籤：偏多",
        "失敗位置：claim_id=1 T=2026-01-01",
        "",
        "執行次數：ok=21",
    ]
    kept, dropped = real.apply_whitelist(lines)
    assert kept == ["管線驗收 P-0：通過", "執行次數：ok=21"]
    assert dropped == 4


def test_e2e_extra_summary_lines_are_dropped_counted_and_never_shown(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path)
    bars = yfinance_bars()

    def fake(folder: Path, **kwargs: Any) -> Any:
        return AcceptanceResult(rules=kwargs["rules"].name, window=(), ledger_sha256="a" * 64)

    def noisy(found: Any) -> list[str]:
        return [*render_summary(found), "筆數：5", "標籤：偏多"]

    original = real.render_summary
    real.render_summary = noisy
    try:
        code, out, err = world.run(capsys, read_bars=lambda _p: bars, acceptance=fake)
    finally:
        real.render_summary = original
    text = "\n".join(decode(x) for x in out)
    assert code == 0 and "筆數" not in text and "偏多" not in text
    # per rule set: 2 noisy lines + the empty run-counts line of the stub = 3
    assert "summary_lines_dropped=6" in out


def test_the_window_line_is_neither_printed_nor_counted(happy: Happy) -> None:
    assert not any("視窗" in line or "session" in line for line in happy.paste_back)
    assert "summary_lines_dropped=0" in happy.paste_back
    assert [decode(x) for x in happy.out] == happy.paste_back


def test_paste_back_has_the_header_once_then_the_fixed_order(happy: Happy) -> None:
    lines = happy.paste_back
    assert lines[:2] == list(harness.HEADER)
    assert lines.count(harness.HEADER[0]) == 1
    names = [
        next(name for name, pattern in real.WHITELIST if pattern.fullmatch(line)) for line in lines
    ]
    assert names[:3] == ["header_1", "header_2", "version"]
    assert names[-4:] == ["acceptance_result", "cleanup", "summary_lines_dropped", "done_at_utc"]
    assert names.count("ruleset_result") == 2 and names.count("bars_sha256") == 1
    assert names.count("bars_sources") == 1 and names.count("copy_check") == 3


def test_the_paste_back_file_is_utf8_with_bom_and_the_screen_is_ascii(happy: Happy) -> None:
    raw = (happy.world.work / "paste-back.txt").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert all(line.isascii() for line in happy.out)
    assert any("\\u" in line for line in happy.out)


def test_the_paste_back_values_come_from_the_program_and_the_repository(happy: Happy) -> None:
    lines = dict(
        line.split("=", 1) for line in happy.paste_back if "=" in line and "：" not in line
    )
    assert lines["git_head"] == HEAD
    assert lines["code_digest"] == recorder.LOADED.code_digest
    assert lines["lockfile_sha256"] == recorder.LOADED.runtime["lockfile_sha256"]
    assert lines["core_autocrlf"] == "unset"
    script_lf = real.normalised_source(SCRIPT_PATH.read_bytes())
    assert lines["script_sha256_lf"] == hashlib.sha256(script_lf).hexdigest()
    harness_lf = real.normalised_source(Path(str(harness.__file__)).read_bytes())
    assert lines["harness_sha256_lf"] == hashlib.sha256(harness_lf).hexdigest()
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", lines["done_at_utc"])


def test_the_two_rule_sets_each_have_a_complete_group(happy: Happy) -> None:
    text = "\n".join(happy.paste_back)
    for name in ("P-0", "P-1"):
        assert f"管線驗收 {name}：通過" in text
    assert text.count("執行次數：ok=21") == 2
    assert text.count("失敗種類：無") == 2
    assert text.count("暫存帳 sha256：") == 2 and text.count("輸出 sha256：") == 2


def _independent_digest(bars: list[Any]) -> str:
    return content_sha256(
        [
            {
                "session_date": b.date,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "source": b.source,
                "as_of": real.injected_as_of(b.date),
                "fetched_at": real.injected_as_of(b.date),
            }
            for b in bars
        ]
    )


def test_bars_sha256_is_the_independent_content_sha256_printed_once(happy: Happy) -> None:
    printed = [x for x in happy.paste_back if x.startswith("bars_sha256=")]
    assert printed == [f"bars_sha256={_independent_digest(happy.bars)}"]
    calls = [
        n
        for n in ast.walk(_script_tree())
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "bars_sha256"
    ]
    assert len(calls) == 1  # one value, taken before the harness runs, shared by both rule sets


def test_bars_sources_is_the_closed_set(happy: Happy) -> None:
    assert [x for x in happy.paste_back if x.startswith("bars_sources=")] == [
        "bars_sources=yfinance"
    ]
    assert real.EXPECTED_SOURCE == "yfinance"


# --- poison, structure, labels ---


def test_poison_no_label_comparison_or_output_line_reaches_the_screen_or_the_file(
    happy: Happy,
) -> None:
    output_text = "\n".join(line for out in happy.outputs for line in out)
    # The fixture is meaningful: the full output holds labels, comparisons and dates.
    for word in ("bullish", "bearish", "range", "證據不足", "T=", "claim"):
        assert word in output_text, word
    shown = "\n".join([*happy.paste_back, *(decode(x) for x in happy.out), happy.err])
    for word in POISON:
        assert word not in shown, word
    for out in happy.outputs:
        for line in out:
            if len(line) > 8 and line not in harness.HEADER:
                assert line not in shown
                assert line.encode("unicode_escape").decode("ascii") not in "\n".join(happy.out)


def test_two_label_distributions_give_the_same_paste_back_but_hashes_and_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = full_run(tmp_path / "a", monkeypatch, capsys, monitor_files=False)
    second = full_run(
        tmp_path / "b",
        monkeypatch,
        capsys,
        bars=yfinance_bars(returns=flipped_return),
        monitor_files=False,
    )
    assert first.code == second.code == 0
    # The inputs really differ, and so do the outputs (so the labels differ) ...
    assert first.paste_back != second.paste_back

    def pick(run: Happy, key: str) -> list[str]:
        return [x for x in run.paste_back if x.startswith(key)]

    assert pick(first, "bars_sha256=") != pick(second, "bars_sha256=")
    assert pick(first, "輸出 sha256：") != pick(second, "輸出 sha256：")
    # ... yet apart from hashes and run counts the two paste-backs are line for line the same.

    def clean(run: Happy) -> list[str]:
        return [x for x in hexless(run.paste_back) if not x.startswith(("done_at_utc", "git_head"))]

    assert clean(first) == clean(second)
    assert len(first.paste_back) == len(second.paste_back)


def test_failure_kinds_are_deduplicated_sorted_and_carry_no_count() -> None:
    kinds = ["vacuous_equality", "label_differs", "vacuous_equality", "label_differs", "run_not_ok"]
    forward = AcceptanceResult(
        rules="P-0",
        window=(),
        failures=[Failure(k, f"w{i}") for i, k in enumerate(kinds)],  # type: ignore[arg-type]
    )
    backward = AcceptanceResult(
        rules="P-0",
        window=(),
        failures=[Failure(k, f"z{i}") for i, k in enumerate(reversed(kinds))],  # type: ignore[arg-type]
    )
    first = [x for x in render_summary(forward) if x.startswith("失敗種類")]
    second = [x for x in render_summary(backward) if x.startswith("失敗種類")]
    assert first == second == ["失敗種類：label_differs，run_not_ok，vacuous_equality"]
    assert real.apply_whitelist(first) == (first, 0)


def test_a_failing_harness_result_prints_only_kinds_and_never_where(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path)
    bars = yfinance_bars()

    def failing(folder: Path, **kwargs: Any) -> Any:
        return AcceptanceResult(
            rules=kwargs["rules"].name,
            window=(),
            failures=[
                Failure("vacuous_equality", "P-0 h3"),
                Failure("missing_code_not_in_set", "c1 T=2026-01-02"),
            ],
            ledger_sha256="a" * 64,
        )

    code, out, err = world.run(capsys, read_bars=lambda _p: bars, acceptance=failing)
    text = "\n".join(decode(x) for x in out)
    assert code == 0 and "acceptance_result=FAIL" in text
    assert "失敗種類：missing_code_not_in_set，vacuous_equality" in text
    assert "T=2026" not in text and "P-0 h3" not in text and "c1 T" not in text


# --- RC-162: interruptions, exceptions, hooks ---


def _single(out: list[str], err: str, sentence: str) -> None:
    assert err == ""
    assert out == [sentence]


def test_rc162_a_failing_harness_prints_only_the_fixed_sentence(
    tmp_path: Path, capsys: Any
) -> None:
    world = make_world(tmp_path)

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("偏多 secret label T=2026-01-02 /home/x")

    code, out, err = world.run(capsys, acceptance=boom)
    assert code == 1
    _single(out, err, UNEXPECTED)
    no_residue(world)
    assert not world.work.exists()


@pytest.mark.parametrize("stage", ["read", "harness", "cleanup", "wait"])
def test_rc162_a_keyboard_interrupt_prints_the_fixed_sentence_and_cleans_up(
    tmp_path: Path, capsys: Any, stage: str
) -> None:
    world = make_world(tmp_path)
    bars = yfinance_bars()
    fired: list[int] = []

    def read(_path: Path) -> list[Any]:
        raise KeyboardInterrupt

    def fake(folder: Path, **kwargs: Any) -> Any:
        (folder / "pipeline-acceptance.db").write_bytes(b"ledger")
        if stage == "harness":
            raise KeyboardInterrupt
        return AcceptanceResult(rules=kwargs["rules"].name, window=(), ledger_sha256="a" * 64)

    def remover(path: Path) -> None:
        if stage == "cleanup" and path.name == "p0" and not fired:
            fired.append(1)
            raise KeyboardInterrupt
        real.remove_path(path)

    def wait(_prompt: str) -> None:
        raise KeyboardInterrupt

    seams: dict[str, Any] = {"acceptance": fake, "remover": remover}
    seams["read_bars"] = read if stage == "read" else (lambda _p: bars)
    if stage == "wait":
        seams["wait"] = wait
    code, out, err = world.run(capsys, **seams)
    assert code == 2
    _single(out, err, INTERRUPTED)
    assert not (world.work / "paste-back.txt").exists()
    no_residue(world)
    assert world.opened == []


def test_rc162_an_interrupt_while_deleting_the_copy_is_the_fixed_sentence_too(
    tmp_path: Path, capsys: Any, spy: Any
) -> None:
    world = make_world(tmp_path)
    fired: list[int] = []

    def remover(path: Path) -> None:
        if path.name == "stock-desk.db" and not fired:
            fired.append(1)
            raise KeyboardInterrupt
        real.remove_path(path)

    code, out, err = world.run(capsys, remover=remover, acceptance=spy[1])
    assert code == 2
    _single(out, err, INTERRUPTED)
    assert spy[0] == []
    no_residue(world)


def test_rc162_the_normal_screen_is_closed(happy: Happy) -> None:
    assert_screen_is_closed(happy.out, happy.err)


def test_rc162_every_stop_screen_is_closed(tmp_path: Path, capsys: Any, spy: Any) -> None:
    world = make_world(tmp_path)
    code, out, err = world.run(capsys, port_check=lambda: True, acceptance=spy[1])
    assert_screen_is_closed(out, err)
    assert out == [real.OUTER_STOP_SENTENCES["port_listening"]]


def test_the_stop_and_error_sentences_are_fixed_ascii_without_values() -> None:
    for sentence in FIXED_SENTENCES:
        assert sentence.isascii() and "\\" not in sentence
        assert "/" not in sentence.replace("origin/product/stock-desk", "")
    assert set(real.OUTER_STOP_SENTENCES) == set(get_args(real.OuterStopKind))
    assert len(set(ALL_STOPS.values())) == len(ALL_STOPS)
    with pytest.raises(ValueError):
        real.RunStop("anything_else")


def test_ast_the_hooks_are_the_first_effective_statements() -> None:
    body = _script_tree().body

    def is_hook(node: ast.stmt) -> bool:
        return (
            isinstance(node, ast.Assign)
            and ast.unparse(node.targets[0])
            in ("sys.excepthook", "threading.excepthook", "sys.unraisablehook")
        ) or (
            isinstance(node, ast.Expr)
            and ast.unparse(node.value) == "warnings.simplefilter('ignore')"
        )

    hook_positions = [i for i, node in enumerate(body) if is_hook(node)]
    assert len(hook_positions) == 4
    first_use = next(
        i
        for i, node in enumerate(body)
        if isinstance(node, ast.ImportFrom)
        and ((node.module or "").split(".")[0] in ("app", "tests") or node.module == "pathlib")
        or ast.unparse(node).startswith("if (_BACKEND_DIR")
    )
    assert max(hook_positions) < first_use
    before = [n for n in body[: max(hook_positions)] if not is_hook(n)]
    kinds = [type(n).__name__ for n in before]
    assert kinds[0] == "Expr"  # the module docstring
    assert [ast.unparse(n) for n in before if isinstance(n, ast.ImportFrom | ast.Import)] == [
        "from __future__ import annotations",
        "import sys",
        "import threading",
        "import warnings",
    ]
    assert [n.name for n in before if isinstance(n, ast.FunctionDef)] == ["_fixed_hook"]
    assert len(before) == 1 + 4 + 1


def test_the_hook_sentence_is_the_error_sentence(capsys: Any) -> None:
    real._fixed_hook(RuntimeError, RuntimeError("偏多 secret"), None)
    captured = capsys.readouterr()
    assert captured.out == UNEXPECTED + "\n" and captured.err == ""


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
    assert done.stdout.splitlines() == [UNEXPECTED] * 3  # thread, unraisable, uncaught
    assert "secret" not in done.stdout
    assert done.returncode != 0


def test_the_cli_stop_through_a_real_isolated_interpreter(tmp_path: Path) -> None:
    # The path the batch file takes: python -I from an unrelated folder, a real stdin.
    world = make_world(tmp_path)
    world.db.unlink()
    for side in world.main_files:
        side.unlink(missing_ok=True)
    env = {k: v for k, v in os.environ.items() if k != real.ENV_VAR}
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", str(SCRIPT_PATH),
         "--backend-dir", str(world.backend), "--home", str(world.home)],
        input="\n", capture_output=True, text=True, timeout=300, cwd=tmp_path, env=env,
    )  # fmt: skip
    assert done.returncode == 3 and done.stderr == ""
    lines = done.stdout.splitlines()
    assert [x.removeprefix(real.PROMPT) for x in lines] == [real.OUTER_STOP_SENTENCES["no_db"]]
    assert not world.work.exists() or not any(world.work.iterdir())


# --- S-13c point 4 / RC-160c are above; S-13b "app/ cannot reach scripts" ---


def test_recorder_and_bars_sha256_use_the_same_snapshot_bar_object() -> None:
    # TA (i): one conversion, K-6. The recorder's path (capture_market_snapshot -> _classify) looks
    # up the module-level name that the script imported.
    assert real._snapshot_bar is inputs._snapshot_bar
    assert "_snapshot_bar" in inputs._classify.__code__.co_names
    assert inputs._classify.__globals__["_snapshot_bar"] is real._snapshot_bar
    bars = yfinance_bars(3)
    answer = harness.SyntheticAnswer(bars=bars)
    final, _dropped = inputs._classify(answer)
    assert final == [real._snapshot_bar(b) for b in bars]


def test_a_non_finite_value_is_the_fixed_error_sentence_and_the_harness_never_runs(
    tmp_path: Path, capsys: Any, spy: Any
) -> None:
    # TA (ii): no new stop kind; bars_sha256 raises before run_acceptance.
    world = make_world(tmp_path)
    bars = yfinance_bars()
    from decimal import Decimal

    bars[10] = bars[10].model_copy(update={"close": Decimal("NaN")})
    code, out, err = world.run(capsys, read_bars=lambda _p: bars, acceptance=spy[1])
    assert code == 1
    _single(out, err, UNEXPECTED)
    assert spy[0] == []


# --- the .bat ---


BAT = BACKEND.parent / "pipeline-acceptance.bat"
COMMAND = r"uv run --no-sync python -I -X utf8 scripts\pipeline_acceptance_real.py"


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
