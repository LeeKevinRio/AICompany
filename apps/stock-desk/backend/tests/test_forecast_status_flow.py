"""Tests for ``scripts/forecast_status.py`` and ``forecast-status.bat`` (ADR-0030 supplement 11).

Covers S-21a as far as it can be checked on the current product line (the ``status`` output of
the old ``report``); the items that need the wired ``report`` (latest run, the two F-2 sentences,
the two missing-day notes in part one) come with the wiring PR.

Every ledger is a ``tmp_path`` file built by the real recorder over synthetic bars
(``tests/test_forecast_report.py``); the "main database path" function of the script is
monkeypatched to it. The real ``<backend>/data/``, ``.env``, the network and ``work/`` (except
the two risk-control reports the sentence test reads) are never touched.
"""

from __future__ import annotations

import ast
import builtins
import difflib
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import pytest

from app.forecast import report
from app.forecast.store import ForecastStore
from tests.forecast_status_world import (
    SCRIPT_PATH,
    STAMP_FOLDER,
    World,
    fs,
    make_world,
    recording,
    reference,
    run,
)
from tests.test_forecast_report import (
    LABEL_WORDS,
    NOW,
    Ledger,
    _publish,
    _records,
    _tamper,
    d4_violations,
)

BACKEND = Path(__file__).resolve().parents[1]
BAT = BACKEND.parent / "forecast-status.bat"
# Frozen copy of apps/stock-desk/pipeline-acceptance.bat taken from commit
# d6816eb9d6a6ecda1d5aaa6c86e8d2a4b7a41425 (product/stock-desk), git blob
# 5b0b271e52f100a7f8584fe7e1ec9889c4cee717 (LF bytes, as stored in git; the old tests read the
# CRLF checkout, so the helper below restores CRLF in memory).
# It is a comparison baseline only. It is the single copy in the whole product line, it must never
# be updated, it does not represent any existing tool, and it must not be used to bring a tool
# back. The sha256 test pins it; the .gitattributes next to it marks it -text (no conversion).
PRECEDENT_BAT = BACKEND / "tests" / "fixtures" / "pipeline_acceptance_bat_frozen.txt"
PRECEDENT_SHA256: Final[str] = "07265206e00c2dd6466c7a319d68484aad1634e7f64c1662638b7d506a43b4ad"
UNEXPECTED: Final[str] = fs.UNEXPECTED
INTERRUPTED: Final[str] = fs.INTERRUPTED
SENTENCE_NAMES = (
    "STOP_ENV",
    "STOP_NOT_FOUND",
    "STOP_UNREADABLE",
    "STOP_IN_GIT",
    "UNEXPECTED",
    "INTERRUPTED",
    "SEPARATOR",
    "ACTION",
    "STOP_VERIFY",
)
SECRET = "secret-/home/someone/stock-desk.db-RuntimeError"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """One synthetic ledger per module (the recorder runs are the slow part); tests copy it."""
    with pytest.MonkeyPatch.context() as patch:
        root = tmp_path_factory.mktemp("forecast-status")
        yield Ledger(root, patch).path


@pytest.fixture
def world(built: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    return make_world(tmp_path, monkeypatch, built)


def saved(world: World) -> str:
    return world.status_file.read_text(encoding="utf-8-sig")


def _tree() -> ast.Module:
    return ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))


# --- the nine fixed sentences, against the risk-control reports ---------------------------------

REVIEWS = "work/reviews"
REPORT_RC291 = "2026-11-20-補充十一與退役通知判定RC284至RC297-風控.md"
REPORT_RC298 = "2026-11-20-補充十一增修確認與三句固定行RC298至RC302-風控.md"
#: constant name -> (report, the ``項目：`` line). The text is read from the next line, in backticks.  # noqa: E501
SOURCES: Final[dict[str, tuple[str, str]]] = {
    "STOP_ENV": (REPORT_RC291, "項目：RC-291 環境變數有 `STOCK_DESK_DB_PATH`（含空字串）"),
    "STOP_NOT_FOUND": (REPORT_RC291, "項目：RC-291 結束碼 4（主 DB 不是既有檔案）"),
    "STOP_UNREADABLE": (REPORT_RC291, "項目：RC-291 結束碼 3（讀不到，或 schema 不完整）"),
    "STOP_IN_GIT": (REPORT_RC291, "項目：RC-291 存檔資料夾在 git 工作樹內（沿用已核可句）"),
    "UNEXPECTED": (REPORT_RC291, "項目：RC-291 預期之外的錯誤（含其他結束碼、hooks）"),
    "INTERRUPTED": (REPORT_RC291, "項目：RC-291 被中斷"),
    "SEPARATOR": (
        REPORT_RC298,
        "項目：RC-298 分隔句（印在 status 段最後一行之後、verify 段第一行之前，每次都印）",
    ),
    "ACTION": (
        REPORT_RC298,
        "項目：RC-298 不一致時的行動句（只在 verify 結束碼為 1 時，印在 verify 段結語之後）",
    ),
    "STOP_VERIFY": (
        REPORT_RC298,
        "項目：RC-299 status 成功、verify 結束碼為 3 或 4 時，取代第二段的 STOP 句",
    ),
}


def report_file(name: str) -> Path:
    """A risk-control report under ``work/reviews`` (searched upwards from this file)."""
    for folder in Path(__file__).resolve().parents:
        candidate = folder / REVIEWS / name
        if candidate.is_file():
            return candidate
    raise AssertionError(f"the risk-control report was not found: {REVIEWS}/{name}")


def extract_sentence(path: Path, label: str) -> str:
    """The ``定稿全文`` text (inside backticks) on the line after the one ``項目：`` line."""
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = [i for i, line in enumerate(lines) if line == label]
    assert len(hits) == 1, f"the label is not found exactly once: {label!r} ({len(hits)})"
    following = lines[hits[0] + 1]
    prefix = "定稿全文：`"
    assert following.startswith(prefix) and following.endswith("`"), following
    return following[len(prefix) : -1]


REPORT_RC310 = "2026-11-20-補充十一E1確認與缺少uv提示定稿RC305至RC312-風控.md"
RC310_LABEL = (
    "項目：RC-310 `.bat` 找不到 `uv` 時的第一行（`forecast-status.bat` 與 `gap-check.bat` 共用；"
    "下一行固定為 `Tell the coordinator.`）"
)


def missing_uv() -> str:
    """The RC-310 sentence, extracted from the risk-control report (never typed here)."""
    return extract_sentence(report_file(REPORT_RC310), RC310_LABEL)


def test_rc310_the_missing_uv_line_is_the_risk_control_sentence_verbatim() -> None:
    lines = _bat_lines(BAT)
    assert lines[17] == "  echo " + missing_uv()  # line 18
    assert lines[18] == "  echo Tell the coordinator."  # line 19, unchanged
    assert missing_uv() == "[MISSING] uv was not found. Do not install or update anything yourself."
    assert not any("install from" in x or "http" in x for x in lines)


@pytest.mark.parametrize("name", SENTENCE_NAMES)
def test_the_fixed_sentence_is_the_risk_control_text_verbatim(name: str) -> None:
    report_name, label = SOURCES[name]
    expected = extract_sentence(report_file(report_name), label)
    assert getattr(fs, name) == expected


def test_the_hook_sentence_is_the_error_sentence_verbatim() -> None:
    report_name, label = SOURCES["UNEXPECTED"]
    expected = extract_sentence(report_file(report_name), label)
    hook = next(
        n for n in ast.walk(_tree()) if isinstance(n, ast.FunctionDef) and n.name == "_fixed_hook"
    )
    literals = [n.value for n in ast.walk(hook) if isinstance(n, ast.Constant)]
    assert expected + "\n" in literals


def test_the_nine_sentences_are_nine_different_texts_and_are_the_only_fixed_lines() -> None:
    texts = [getattr(fs, name) for name in SENTENCE_NAMES]
    assert len(set(texts)) == 9 and all(isinstance(t, str) and t for t in texts)
    assert set(SOURCES) == set(SENTENCE_NAMES)


def test_the_extraction_fails_on_a_missing_report_or_label(tmp_path: Path) -> None:
    with pytest.raises(AssertionError):
        report_file("no-such-report.md")
    sample = tmp_path / "r.md"
    sample.write_text("項目：A\n定稿全文：`x`\n\n項目：A\n定稿全文：`y`\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        extract_sentence(sample, "項目：B")
    with pytest.raises(AssertionError):
        extract_sentence(sample, "項目：A")  # twice
    sample.write_text("項目：A\n定稿全文：x\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        extract_sentence(sample, "項目：A")  # not in backticks
    sample.write_text("項目：A\n定稿全文：`x`\n", encoding="utf-8")
    assert extract_sentence(sample, "項目：A") == "x"


def test_the_error_and_stop_sentences_have_no_value_or_path() -> None:
    for name in SENTENCE_NAMES:
        text = getattr(fs, name)
        assert "\n" not in text and "\\" not in text and "/" not in text


# --- AST (S-21a: the script's own boundaries) ----------------------------------------------------


def _string_constants(tree: ast.AST) -> list[str]:
    return [
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def test_ast_the_only_subcommands_are_status_and_verify_and_verify_takes_only_all() -> None:
    strings = _string_constants(_tree())
    subcommands = {"status", "records", "compare", "verify"}
    assert sorted(s for s in strings if s in subcommands) == ["status", "verify"]
    assert strings.count("--all") == 1
    assert not any("claim" in s.lower() and s.startswith("-") for s in strings)
    assert sorted(s for s in strings if s.startswith("--")) == ["--all", "--db", "--db"]
    # The two argument lists are the only places the subcommands are named.
    lists = [n for n in ast.walk(_tree()) if isinstance(n, ast.List)]
    shapes = sorted(
        ast.unparse(n) for n in lists if any(s in ast.unparse(n) for s in ("'status'", "'verify'"))
    )
    assert shapes == ["['status', '--db', db]", "['verify', '--all', '--db', db]"]


def test_ast_the_script_does_not_read_sys_argv_or_take_a_parameter() -> None:
    tree = _tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert (node.value.id, node.attr) != ("sys", "argv")
        if isinstance(node, ast.Name):
            assert node.id not in {"argv", "argparse", "getopt"}
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    assert [a.arg for a in main.args.args] == [] and main.args.vararg is None
    assert [a.arg for a in main.args.kwonlyargs] == []
    called = [
        n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func) == "main"
    ]
    assert [ast.unparse(c) for c in called] == ["main()"]


def test_ast_imports_are_the_standard_library_and_report_only() -> None:
    allowed_stdlib = {
        "__future__", "collections.abc", "contextlib", "dataclasses", "datetime", "io",
        "logging", "os", "pathlib", "subprocess", "sys", "threading", "typing", "warnings",
    }  # fmt: skip
    found: list[str] = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append(f"{node.module}:{','.join(a.name for a in node.names)}")
    app_imports = [x for x in found if x.split(":")[0].split(".")[0] in {"app", "tests"}]
    assert app_imports == ["app.forecast:report"]
    assert not any("harness" in x or "tests" in x for x in found)
    others = {x.split(":")[0] for x in found} - {"app.forecast"}
    assert others <= allowed_stdlib, others - allowed_stdlib


def test_the_script_loads_no_other_forecast_module_than_report_and_its_dependencies() -> None:
    # At run time, in a clean interpreter: the harness and the tests package are never imported.
    code = (
        "import runpy, sys\n"
        f"sys.path.insert(0, {str(BACKEND)!r})\n"
        f"runpy.run_path({str(SCRIPT_PATH)!r}, run_name='loaded')\n"
        "bad = [m for m in sys.modules if m == 'tests' or m.startswith('tests.')"
        " or m.endswith('forecast_pipeline_harness')]\n"
        "sys.exit(3 if bad else 0)\n"
    )
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, timeout=120)
    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")


def test_ast_the_script_names_no_file_of_work_and_reads_no_env_file() -> None:
    strings = _string_constants(_tree())
    code_strings = [
        s for s in strings if not s.startswith("The one-click") and "\n" not in s.strip("\n")
    ]
    for text in code_strings:
        assert "work/" not in text and "work\\" not in text and "reviews" not in text
        assert ".env" not in text
    names = {n.id for n in ast.walk(_tree()) if isinstance(n, ast.Name)}
    assert not names & {"dotenv", "load_dotenv"}


def test_ast_there_is_one_screen_port_and_it_is_the_say_function() -> None:
    tree = _tree()
    owners: list[str] = []
    for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(func):
            if isinstance(node, ast.Attribute) and ast.unparse(node) in {
                "sys.stdout",
                "sys.stderr",
                "sys.__stdout__",
                "sys.__stderr__",
            }:
                owners.append(func.name)
            if isinstance(node, ast.Call) and ast.unparse(node.func) in {"print", "os.write"}:
                owners.append(func.name)
    assert sorted(set(owners)) == ["_fixed_hook", "say"] and owners.count("say") == 2
    assert not [n for n in tree.body if isinstance(n, ast.Expr) and "print" in ast.unparse(n)]


def test_e3_output_goes_only_through_sys_stdout_write_and_the_bat_has_no_chcp() -> None:
    tree = _tree()
    attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and ast.unparse(node.value) == "sys.stdout"
    }
    assert attributes == {"write", "flush"}  # no ``buffer``, no ``reconfigure``, no ``print``
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "print" not in names
    assert not [
        n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "reconfigure"
    ]
    assert not any(isinstance(n, ast.Name) and n.id == "print" for n in ast.walk(tree))
    assert "chcp" not in BAT.read_bytes().decode("ascii").lower()


def test_ast_say_is_called_only_by_the_stops_the_show_function_and_the_handlers() -> None:
    tree = _tree()
    callers: dict[str, int] = {}
    for func in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        count = sum(
            1 for n in ast.walk(func) if isinstance(n, ast.Call) and ast.unparse(n.func) == "say"
        )
        if count and func.name != "say":
            callers[func.name] = count
    assert callers == {"show": 1, "flow": 4, "main": 1}
    # The order of supplement 11: pre-checks, status, show part one, verify, show part two, save.
    flow = ast.unparse(
        next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "flow")
    )
    order = [
        flow.index(x)
        for x in (
            "ENV_VAR in env",
            "inside_git_work_tree(wanted)",
            "'status', '--db'",
            "show(state, first",
            "'verify', '--all'",
            "show(state, second",
            "save(state, wanted)",
            "opener(state.final)",
        )
    ]
    assert order == sorted(order)
    assert "mkdir" not in flow and "new_folder" not in flow  # the folder is made in ``save``
    save = ast.unparse(
        next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "save")
    )
    assert save.index("handle.write") < save.index("os.replace") < save.index("committed = True")


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

    hook_positions = [i for i, node in enumerate(body) if is_hook(node)]
    assert len(hook_positions) == 5
    first_use = next(
        i
        for i, node in enumerate(body)
        if isinstance(node, ast.ImportFrom)
        and ((node.module or "").split(".")[0] in ("app", "tests") or node.module == "pathlib")
        or ast.unparse(node).startswith("if (_BACKEND_DIR")
    )
    assert max(hook_positions) < first_use
    before = [n for n in body[: max(hook_positions)] if not is_hook(n)]
    assert type(before[0]).__name__ == "Expr"  # the module docstring
    assert [ast.unparse(n) for n in before if isinstance(n, ast.ImportFrom | ast.Import)] == [
        "from __future__ import annotations",
        "import logging",
        "import sys",
        "import threading",
        "import warnings",
    ]
    assert [n.name for n in before if isinstance(n, ast.FunctionDef)] == ["_fixed_hook"]
    assert len(before) == 1 + 5 + 1


def test_the_hook_prints_the_error_sentence_only(capsys: Any) -> None:
    fs._fixed_hook(RuntimeError, RuntimeError("偏多 secret"), None)
    captured = capsys.readouterr()
    assert captured.out == UNEXPECTED + "\n" and captured.err == ""


def test_the_main_database_is_derived_from_the_scripts_place() -> None:
    # Only the path is computed; nothing is opened.
    assert fs._BACKEND_DIR == BACKEND
    assert fs.main_db_path() == BACKEND / "data" / "stock-desk.db"
    assert SCRIPT_PATH.parent == BACKEND / "scripts"


# --- the pre-checks ------------------------------------------------------------------------------


class ConnectSpy:
    """Every ``sqlite3.connect`` target, and every file opened for writing."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.connects: list[str] = []
        self.writes: list[str] = []
        self.opens: list[str] = []
        original_connect = sqlite3.connect
        original_open = builtins.open

        def connect(database: Any, *args: Any, **kwargs: Any) -> Any:
            self.connects.append(str(database))
            return original_connect(database, *args, **kwargs)

        def spy_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if isinstance(file, str | os.PathLike):
                self.opens.append(str(os.fspath(file)))
                if any(c in mode for c in "wax+"):
                    self.writes.append(str(os.fspath(file)))
            return original_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", connect)
        monkeypatch.setattr(builtins, "open", spy_open)


@pytest.mark.parametrize("value", ["", "x.db", "/some/where.db"])
def test_stock_desk_db_path_set_stops_before_any_connection(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    spy = ConnectSpy(monkeypatch)
    code, out, err = run(world, capsys, env={fs.ENV_VAR: value}, report_main=recording(world))
    assert (code, out, err) == (3, fs.STOP_ENV + "\n", "")
    assert spy.connects == [] and world.calls == []
    assert world.residue() == [] and world.opened == []


def test_the_environment_is_read_from_the_process_by_default(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(fs.ENV_VAR, "")
    spy = ConnectSpy(monkeypatch)
    capsys.readouterr()
    code = fs.main(
        home=world.home, now=lambda: datetime(2026, 11, 20), report_main=recording(world)
    )
    assert (code, capsys.readouterr().out) == (3, fs.STOP_ENV + "\n")
    assert spy.connects == [] and world.calls == []


def test_a_status_folder_inside_a_git_work_tree_stops_before_anything_is_read(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    spy = ConnectSpy(monkeypatch)
    code, out, err = run(world, capsys, home=repo, report_main=recording(world))
    assert (code, out, err) == (3, fs.STOP_IN_GIT + "\n", "")
    assert spy.connects == [] and world.calls == [] and world.opened == []
    assert not (repo / fs.WORK_ROOT_NAME).exists()
    assert sorted(p.name for p in repo.iterdir()) == [".git"]


def test_a_status_folder_below_a_git_work_tree_also_stops(
    world: World, capsys: Any, tmp_path: Path
) -> None:
    home = tmp_path / "repo" / "deep" / "home"
    home.mkdir(parents=True)
    (tmp_path / "repo" / ".git").write_text("gitdir: elsewhere\n")  # a worktree's .git file
    code, out, _ = run(world, capsys, home=home, report_main=recording(world))
    assert (code, out) == (3, fs.STOP_IN_GIT + "\n")
    assert world.calls == [] and list(home.iterdir()) == []


# --- the happy path against ``report`` itself ----------------------------------------------------


def test_the_two_parts_are_the_report_outputs_verbatim_with_only_the_separator_between(
    world: World, capsys: Any
) -> None:
    code_status, status_text = reference(world, capsys, "status")
    code_verify, verify_text = reference(world, capsys, "verify", "--all")
    assert (code_status, code_verify) == (0, 0)
    code, out, err = run(world, capsys, report_main=recording(world))
    assert (code, err) == (0, "")
    assert out == status_text + fs.SEPARATOR + "\n" + verify_text
    assert out.index(fs.SEPARATOR) == len(status_text)
    assert out.endswith("verify：全部一致\n")
    assert out.startswith("執行狀態（只含執行狀態，不含任何標籤或對照）\n")
    assert world.calls == [
        ["status", "--db", str(world.db)],
        ["verify", "--all", "--db", str(world.db)],
    ]


def test_the_file_has_the_same_content_as_the_screen_in_utf8_sig_and_is_opened(
    world: World, capsys: Any
) -> None:
    code, out, _ = run(world, capsys)
    assert code == 0
    raw = world.status_file.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and not raw.startswith(b"\xef\xbb\xbf\xef\xbb\xbf")
    assert saved(world) == out
    assert world.opened == [world.status_file]
    assert [p.name for p in world.status_root.iterdir()] == [STAMP_FOLDER]
    assert [p.name for p in world.folder.iterdir()] == [fs.STATUS_NAME]


def test_a_second_run_gets_its_own_folder_and_never_overwrites_an_old_file(
    world: World, capsys: Any
) -> None:
    run(world, capsys)
    first = world.status_file.read_bytes()
    run(world, capsys)
    run(world, capsys)
    names = sorted(p.name for p in world.status_root.iterdir())
    assert names == [STAMP_FOLDER, f"{STAMP_FOLDER}-2", f"{STAMP_FOLDER}-3"]
    assert world.status_file.read_bytes() == first
    assert len(world.opened) == 3 and len(set(world.opened)) == 3


def test_the_main_database_is_only_read_and_nothing_is_written_outside_the_status_folder(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def snapshot() -> dict[str, tuple[bytes, int]]:
        return {
            str(p): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(world.root.rglob("*"))
            if p.is_file()
        }

    before = snapshot()
    spy = ConnectSpy(monkeypatch)
    code, _, err = run(world, capsys)
    assert (code, err) == (0, "")
    assert snapshot() == before  # bytes, mtimes and the set of files (no -wal, -shm, -journal)
    assert spy.connects and all(str(world.db) in target for target in spy.connects)
    assert all(
        target.startswith(str(world.status_root)) or not target.startswith(str(world.root))
        for target in spy.writes
    )
    assert [w for w in spy.writes if w.startswith(str(world.root))] == []
    assert [o for o in spy.opens if o.endswith(".env") or "/.env" in o] == []
    assert str(BACKEND) not in "".join(spy.writes)


def test_every_read_connection_refuses_a_write_while_it_is_open(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write is tried inside ``ForecastStore._read`` (the connection is closed afterwards)."""
    original = ForecastStore._read
    refusals: list[str] = []

    @contextmanager
    def probing(self: ForecastStore) -> Iterator[sqlite3.Connection]:
        with original(self) as conn:
            with pytest.raises(sqlite3.OperationalError) as refused:
                conn.execute("CREATE TABLE intruder (x)")
            refusals.append(str(refused.value))
            yield conn

    monkeypatch.setattr(ForecastStore, "_read", probing)
    code, _, err = run(world, capsys)
    assert (code, err) == (0, "")
    assert refusals and all("readonly" in text for text in refusals)
    with closing(sqlite3.connect(world.db)) as conn:  # nothing was created in the database
        assert (
            conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'intruder'").fetchone() is None
        )


def test_the_write_probe_has_teeth_on_a_connection_that_is_not_query_only(world: World) -> None:
    # Control: the same statement succeeds on a plain connection, so the probe above can fail.
    with closing(sqlite3.connect(world.db, isolation_level=None)) as conn:
        conn.execute("CREATE TABLE intruder (x)")
    with closing(sqlite3.connect(world.db, isolation_level=None)) as conn:
        conn.execute("PRAGMA query_only = ON")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("CREATE TABLE intruder_two (x)")


def test_verify_exit_1_is_shown_and_saved_with_the_action_sentence_after_the_closing_line(
    world: World, capsys: Any
) -> None:
    victim = _records(world.db)[0]
    other = "bearish" if victim["label"] != "bearish" else "bullish"
    _tamper(
        world.db,
        "forecast_record",
        "UPDATE forecast_record SET label = ? WHERE forecast_id = ?",
        (other, victim["forecast_id"]),
    )
    code_status, status_text = reference(world, capsys, "status")
    code_verify, verify_text = reference(world, capsys, "verify", "--all")
    assert (code_status, code_verify) == (0, report.EXIT_INCONSISTENT)
    code, out, err = run(world, capsys)
    assert (code, err) == (0, "")
    assert out == status_text + fs.SEPARATOR + "\n" + verify_text + fs.ACTION + "\n"
    lines = out.splitlines()
    assert lines[-2] == "verify：有不一致（F-3：停止記錄並查明）"
    assert lines[-1] == fs.ACTION
    assert saved(world) == out and world.opened == [world.status_file]
    assert fs.ACTION not in status_text + verify_text


def test_the_action_sentence_is_absent_when_everything_is_consistent(
    world: World, capsys: Any
) -> None:
    _, out, _ = run(world, capsys)
    assert fs.ACTION not in out and fs.STOP_VERIFY not in out


# --- status exit codes 3 and 4 -------------------------------------------------------------------


def test_status_exit_4_prints_only_the_fixed_sentence_runs_no_verify_and_writes_nothing(
    world: World, capsys: Any
) -> None:
    world.db.unlink()
    code_ref, _ = reference(world, capsys, "status")
    assert code_ref == report.EXIT_PATH_REFUSED
    code, out, err = run(world, capsys, report_main=recording(world))
    assert (code, out, err) == (3, fs.STOP_NOT_FOUND + "\n", "")
    assert [c[0] for c in world.calls] == ["status"]
    assert world.residue() == [] and world.opened == []


@pytest.mark.parametrize("damage", ["garbage", "no-schema"])
def test_status_exit_3_prints_only_the_fixed_sentence_runs_no_verify_and_writes_nothing(
    world: World, capsys: Any, damage: str
) -> None:
    if damage == "garbage":
        world.db.write_bytes(b"this is not a database " * 200)
    else:
        world.db.unlink()
        with closing(sqlite3.connect(world.db)) as conn:
            conn.execute("CREATE TABLE unrelated (x)")
            conn.commit()
    code_ref, _ = reference(world, capsys, "status")
    assert code_ref == report.EXIT_UNREADABLE
    code, out, err = run(world, capsys, report_main=recording(world))
    assert (code, out, err) == (3, fs.STOP_UNREADABLE + "\n", "")
    assert [c[0] for c in world.calls] == ["status"]
    assert world.residue() == [] and world.opened == []


# --- status ok, verify exit 3 / 4 ----------------------------------------------------------------


@pytest.mark.parametrize("verify_code", [3, 4])
def test_verify_exit_3_or_4_keeps_part_one_and_the_separator_then_the_stop_sentence(
    world: World, capsys: Any, verify_code: int
) -> None:
    _, status_text = reference(world, capsys, "status")

    def verify(argv: Sequence[str], *, clock: Any = None) -> int:
        print("a partial listing that must not be shown")
        print(f"refused: the ledger cannot be read ({SECRET})", file=sys.stderr)
        return verify_code

    code, out, err = run(world, capsys, report_main=recording(world, verify=verify))
    assert (code, err) == (3, "")  # E2: a STOP sentence is on the screen, so the tool ends with 3
    assert out == status_text + fs.SEPARATOR + "\n" + fs.STOP_VERIFY + "\n"
    assert saved(world) == out and world.opened == [world.status_file]
    assert "partial" not in out and SECRET not in saved(world)


# --- any other exit code, an exception, an interrupt ---------------------------------------------


def _raiser(exc: BaseException) -> Callable[..., int]:
    def raiser(argv: Sequence[str], *, clock: Any = None) -> int:
        print(f"on stdout: {SECRET}")
        print(f"on stderr: {SECRET}", file=sys.stderr)
        raise exc

    return raiser


def _returning(code: int) -> Callable[..., int]:
    def returning(argv: Sequence[str], *, clock: Any = None) -> int:
        print(f"on stdout: {SECRET}")
        print(f"on stderr: {SECRET}", file=sys.stderr)
        return code

    return returning


UNEXPECTED_CASES = [
    pytest.param(lambda: _returning(2), id="exit-2"),
    pytest.param(lambda: _returning(5), id="exit-5"),
    pytest.param(lambda: _returning(-1), id="exit-minus-1"),
    pytest.param(lambda: _raiser(RuntimeError(SECRET)), id="runtime-error"),
    pytest.param(lambda: _raiser(sqlite3.OperationalError(SECRET)), id="sqlite-error"),
    pytest.param(lambda: _raiser(SystemExit(2)), id="system-exit"),
    pytest.param(lambda: _raiser(MemoryError()), id="memory-error"),
]


def _shown_before(world: World, capsys: Any, stage: str) -> str:
    """What the screen already shows when the failure comes in ``stage`` (not taken back)."""
    if stage == "status":
        return ""
    _, status_text = reference(world, capsys, "status")
    return str(status_text + fs.SEPARATOR + "\n")


@pytest.mark.parametrize("stage", ["status", "verify"])
@pytest.mark.parametrize("make", UNEXPECTED_CASES)
def test_any_other_exit_code_or_exception_prints_the_error_sentence_and_leaves_no_file(
    world: World, capsys: Any, stage: str, make: Callable[[], Callable[..., int]]
) -> None:
    before = _shown_before(world, capsys, stage)
    seam = recording(world, **{stage: make()})
    code, out, err = run(world, capsys, report_main=seam)
    assert (code, out, err) == (1, before + UNEXPECTED + "\n", "")
    assert SECRET not in out and "Traceback" not in out
    assert world.residue() == [] and world.opened == []
    assert [c[0] for c in world.calls] == (
        ["status"] if stage == "status" else ["status", "verify"]
    )


@pytest.mark.parametrize("stage", ["status", "verify"])
def test_an_interrupt_prints_the_interrupted_sentence_and_leaves_no_file(
    world: World, capsys: Any, stage: str
) -> None:
    before = _shown_before(world, capsys, stage)
    seam = recording(world, **{stage: _raiser(KeyboardInterrupt())})
    code, out, err = run(world, capsys, report_main=seam)
    assert (code, out, err) == (2, before + INTERRUPTED + "\n", "")
    assert world.residue() == [] and world.opened == []


def test_argparse_usage_on_stderr_is_not_shown(world: World, capsys: Any) -> None:
    def bad(argv: Sequence[str], *, clock: Any = None) -> int:
        return int(report.main(["no-such-command"], clock=clock))

    code, out, err = run(world, capsys, report_main=recording(world, status=bad))
    assert (code, out, err) == (1, UNEXPECTED + "\n", "")  # SystemExit(2) is case (d)
    assert world.residue() == []


def test_the_report_stderr_is_on_neither_the_screen_nor_the_file(world: World, capsys: Any) -> None:
    def noisy(argv: Sequence[str], *, clock: Any = None) -> int:
        print(f"refused: --db is not an existing ledger file {SECRET}", file=sys.stderr)
        print(f"usage: {SECRET}", file=sys.stderr)
        return int(report.main(argv, clock=clock))

    _, status_text = reference(world, capsys, "status")
    _, verify_text = reference(world, capsys, "verify", "--all")
    code, out, err = run(world, capsys, report_main=recording(world, status=noisy, verify=noisy))
    assert (code, err) == (0, "")
    assert out == status_text + fs.SEPARATOR + "\n" + verify_text
    assert SECRET not in out and "refused" not in out and "usage" not in out
    assert SECRET not in saved(world)


@pytest.mark.parametrize("which", [3, 4])
def test_the_refusal_sentences_of_report_never_reach_the_screen(
    world: World, capsys: Any, which: int
) -> None:
    def refusing(argv: Sequence[str], *, clock: Any = None) -> int:
        print(f"refused: the ledger cannot be read ({SECRET})", file=sys.stderr)
        return which

    code, out, err = run(world, capsys, report_main=recording(world, status=refusing))
    expected = fs.STOP_NOT_FOUND if which == 4 else fs.STOP_UNREADABLE
    assert (code, out, err) == (3, expected + "\n", "")


# --- failures while writing: no incomplete file --------------------------------------------------


@pytest.mark.parametrize("failure", ["open", "write", "rename"])
def test_a_failure_while_writing_leaves_no_status_file_no_temporary_file_and_no_folder(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    _, status_text = reference(world, capsys, "status")
    _, verify_text = reference(world, capsys, "verify", "--all")
    shown = status_text + fs.SEPARATOR + "\n" + verify_text
    real_open = builtins.open

    def failing_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if failure == "open":
            raise OSError(SECRET)
        handle = real_open(file, mode, *args, **kwargs)
        handle.write("a half-written line")
        handle.flush()
        handle.close()
        raise OSError(SECRET)

    def failing_replace(*_args: Any) -> None:
        raise OSError(SECRET)

    if failure == "rename":
        monkeypatch.setattr(os, "replace", failing_replace)
    else:
        monkeypatch.setattr(fs, "open", failing_open, raising=False)
    code, out, err = run(world, capsys)
    assert (code, out, err) == (1, shown + UNEXPECTED + "\n", "")  # what was shown stays shown
    assert [p for p in world.residue() if p.is_file()] == []
    assert not world.folder.exists() and world.opened == []


def test_an_interrupt_during_the_rename_leaves_no_file_and_no_folder(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(*_args: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", interrupted)
    code, out, err = run(world, capsys)
    assert (code, err) == (2, "") and out.endswith(INTERRUPTED + "\n")
    assert world.residue() == [] and world.opened == []


def test_the_text_is_written_to_a_temporary_file_that_is_then_renamed(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    steps: list[tuple[str, bool, bool]] = []
    real_replace = os.replace

    def spy(src: Any, dst: Any) -> None:
        steps.append((Path(src).name, Path(src).exists(), Path(dst).exists()))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    code, out, _ = run(world, capsys)
    assert code == 0 and steps == [(fs.TEMP_NAME, True, False)]
    assert [p.name for p in world.folder.iterdir()] == [fs.STATUS_NAME]
    assert saved(world) == out


def test_a_status_root_that_cannot_be_made_is_the_error_sentence_after_the_shown_parts(
    world: World, capsys: Any
) -> None:
    _, status_text = reference(world, capsys, "status")
    _, verify_text = reference(world, capsys, "verify", "--all")
    world.status_root.write_text("a file where the folder should be")
    code, out, err = run(world, capsys)
    shown = status_text + fs.SEPARATOR + "\n" + verify_text
    assert (code, out, err) == (1, shown + UNEXPECTED + "\n", "")
    assert world.status_root.read_text() == "a file where the folder should be"


@pytest.mark.parametrize("failure", ["rename", "stage"])
@pytest.mark.parametrize("preexisting", ["empty-root", "root-with-old-run"])
def test_n3_a_failed_run_removes_only_what_it_created(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch, failure: str, preexisting: str
) -> None:
    world.status_root.mkdir()
    old_file = world.status_root / "20260101-000000" / fs.STATUS_NAME
    if preexisting == "root-with-old-run":
        old_file.parent.mkdir()
        old_file.write_bytes(b"an earlier run")
    if failure == "rename":

        def broken(*_args: Any) -> None:
            raise OSError(SECRET)

        monkeypatch.setattr(os, "replace", broken)
    else:  # the run fails after ``verify`` but its own folder was already made
        monkeypatch.setattr(fs, "open", broken_open, raising=False)
    code, out, err = run(world, capsys)
    assert (code, err) == (1, "") and out.endswith(UNEXPECTED + "\n")
    assert world.status_root.is_dir()  # it was there before, empty or not: it stays
    assert not world.folder.exists()  # the run's own folder is gone
    if preexisting == "root-with-old-run":
        assert old_file.read_bytes() == b"an earlier run"
    else:
        assert list(world.status_root.iterdir()) == []


def broken_open(*_args: Any, **_kwargs: Any) -> Any:
    raise OSError(SECRET)


def test_n3_a_failed_run_removes_every_folder_it_made_above_its_own(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deep = tmp_path / "newly" / "made" / "home"
    monkeypatch.setattr(fs, "open", broken_open, raising=False)
    code, out, err = run(world, capsys, home=deep)
    assert (code, err) == (1, "") and out.endswith(UNEXPECTED + "\n")
    assert not (tmp_path / "newly").exists()  # all three folders above the root were this run's


def test_n3_a_folder_that_existed_above_the_root_is_never_removed(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "kept" / "home"
    home.mkdir(parents=True)
    (home / "mine.txt").write_text("not the tool's")
    monkeypatch.setattr(fs, "open", broken_open, raising=False)
    code, _, _ = run(world, capsys, home=home)
    assert code == 1
    assert (home / "mine.txt").read_text() == "not the tool's"
    assert [p.name for p in home.iterdir()] == ["mine.txt"]


@pytest.mark.parametrize("exc", [OSError(SECRET), RuntimeError(SECRET), KeyboardInterrupt()])
def test_rc303_an_opener_that_fails_leaves_the_saved_file_the_screen_and_the_exit_code(
    world: World, capsys: Any, exc: BaseException
) -> None:
    def broken(path: Path) -> None:
        raise exc

    code, out, err = run(world, capsys, opener=broken)
    assert (code, err) == (0, "")
    assert saved(world) == out  # the file exists and is the screen, word for word
    assert UNEXPECTED not in out and INTERRUPTED not in out and "Traceback" not in out
    assert SECRET not in out and SECRET not in saved(world)
    assert [p.name for p in world.folder.iterdir()] == [fs.STATUS_NAME]


def test_no_opener_is_used_off_windows(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[Any] = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: started.append(a))
    capsys.readouterr()
    seams = world.seams()
    del seams["opener"]
    assert fs.main(**seams) == 0
    assert started == [] if sys.platform != "win32" else True


def test_the_windows_opener_is_notepad_on_the_status_file(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[Any] = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **k: started.append(args))
    fs.open_in_notepad(Path("C:/x/status.txt"))
    assert started == [["notepad.exe", str(Path("C:/x/status.txt"))]]


# --- D-4 and the poison: no label, baseline or hash on the screen --------------------------------


def _forbidden_values(db: Path) -> set[str]:
    rows = _records(db)
    values = {str(r["content_hash"]) for r in rows} | {str(r["label"]) for r in rows}
    for r in rows:
        baselines = json.loads(str(r["baseline_predictions_json"]))
        values |= {str(v["label"]) for v in baselines.values()}
        values |= {str(v["reason"]) for v in baselines.values() if "reason" in v}
    return values | set(LABEL_WORDS) | {"insufficient", "unavailable"}


def _passed_and_unpassed(db: Path) -> tuple[int, int]:
    today = report.taipei_date(NOW)
    flags = [report.has_passed(r["valid_until_session_estimate"], today) for r in _records(db)]
    return sum(flags), len(flags) - sum(flags)


def test_the_ledger_has_passed_records_with_labels_and_the_screen_still_has_none(
    world: World, capsys: Any
) -> None:
    passed, unpassed = _passed_and_unpassed(world.db)
    assert passed > 0 and unpassed > 0  # records that ``records`` / ``compare`` would label
    forbidden = _forbidden_values(world.db)
    assert any(len(v) == 64 for v in forbidden)  # the content hashes
    assert {str(r["label"]) for r in _records(world.db)} & {"bullish", "bearish", "range"}
    verdicts: list[str] = []
    for stage_code in (None, 1, 3):
        if stage_code is None:
            _, out, _ = run(world, capsys)
        else:
            _, out, _ = run(
                world,
                capsys,
                report_main=recording(world, verify=lambda *a, c=stage_code, **k: c),
            )
        verdicts.append(out)
        for value in forbidden:
            assert value not in out, value
    assert fs.ACTION in verdicts[1] and fs.STOP_VERIFY in verdicts[2]


def test_the_fixed_sentences_alone_contain_no_label_baseline_or_hash(world: World) -> None:
    forbidden = _forbidden_values(world.db)
    for name in SENTENCE_NAMES:
        for value in forbidden:
            assert value not in getattr(fs, name), (name, value)


@pytest.mark.parametrize("variant", ["consistent", "inconsistent", "verify-3"])
def test_the_whole_screen_passes_the_d4_checker(world: World, capsys: Any, variant: str) -> None:
    seam = recording(world)
    if variant == "inconsistent":
        victim = _records(world.db)[0]
        other = "bearish" if victim["label"] != "bearish" else "bullish"
        _tamper(
            world.db,
            "forecast_record",
            "UPDATE forecast_record SET label = ? WHERE forecast_id = ?",
            (other, victim["forecast_id"]),
        )
    elif variant == "verify-3":
        seam = recording(world, verify=lambda *a, **k: 3)
    _, out, _ = run(world, capsys, report_main=seam)
    hashes = {str(r["content_hash"]) for r in _records(world.db)}
    assert out.strip() and d4_violations(out.splitlines(), unpassed_hashes=hashes) == []
    for name in SENTENCE_NAMES:
        assert d4_violations([getattr(fs, name)], unpassed_hashes=hashes) == []


# --- the output is fixed text, however the process ends (real interpreter) -----------------------


def _driver(script: Path, body: str) -> str:
    return (
        "import runpy, sys, os, gc, sqlite3, threading, warnings\n"
        f"sys.path.insert(0, {str(BACKEND)!r})\n"
        f"_data = {str(BACKEND / 'data')!r}\n"
        "_connect = sqlite3.connect\n"
        "def _guard(database, *a, **k):\n"
        "    if _data in str(database):\n"
        "        raise SystemExit(99)\n"
        "    return _connect(database, *a, **k)\n"
        "sqlite3.connect = _guard\n"
        + body
        + f"runpy.run_path({str(script)!r}, run_name='__main__')\n"
    )


def _fake_backend(tmp_path: Path, built: Path) -> tuple[Path, Path, Path]:
    """A backend folder holding a copy of the script beside a synthetic ``data/stock-desk.db``."""
    backend = tmp_path / "backend"
    (backend / "scripts").mkdir(parents=True)
    (backend / "data").mkdir()
    script = backend / "scripts" / "forecast_status.py"
    script.write_bytes(SCRIPT_PATH.read_bytes())
    (backend / "data" / "stock-desk.db").write_bytes(built.read_bytes())
    home = tmp_path / "home"
    home.mkdir()
    return script, backend, home


def _child_env(home: Path, **extra: str) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {fs.ENV_VAR, "UV_ENV_FILE", "HOME", "USERPROFILE"}
    }
    env.update({"HOME": str(home), "USERPROFILE": str(home), **extra})
    return env


def _exec(driver: str, home: Path, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", driver],
        capture_output=True,
        timeout=300,
        cwd=cwd,
        env=_child_env(home),
    )


PUBLISH = "from tests.test_forecast_report import _publish\nimport pytest\n_publish(pytest.MonkeyPatch())\n"  # noqa: E501


def test_e2e_a_real_interpreter_run_on_a_synthetic_backend_shows_and_saves_the_two_parts(
    tmp_path: Path, built: Path
) -> None:
    script, backend, home = _fake_backend(tmp_path, built)
    done = _exec(_driver(script, PUBLISH), home, tmp_path)
    assert done.returncode == 0 and done.stderr == b""
    out = done.stdout.decode("utf-8")
    files = sorted(home.glob(f"{fs.WORK_ROOT_NAME}/*/{fs.STATUS_NAME}"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8-sig").replace("\r\n", "\n") == out.replace(
        "\r\n", "\n"
    )
    assert fs.SEPARATOR in out and out.splitlines()[0].startswith("執行狀態")
    assert out.splitlines()[-1] == "verify：全部一致"
    assert sorted(p.name for p in (backend / "data").iterdir()) == ["stock-desk.db"]
    assert sorted(p.name for p in backend.iterdir()) == ["data", "scripts"]


def test_n5_the_screen_equals_two_real_python_m_report_runs_word_for_word(
    tmp_path: Path, built: Path
) -> None:
    script, backend, home = _fake_backend(tmp_path, built)
    db = backend / "data" / "stock-desk.db"
    env = _child_env(home)
    tool = _exec(_driver(script, PUBLISH), home, tmp_path)
    assert tool.returncode == 0 and tool.stderr == b""
    status = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "app.forecast.report", "status", "--db", str(db)],
        capture_output=True, timeout=300, cwd=BACKEND, env=env,
    )  # fmt: skip
    assert status.returncode == 0 and status.stderr == b""
    # ``verify`` needs the synthetic registry published (as in every other test); the module is
    # still started as ``__main__`` of ``app.forecast.report``, which is what ``-m`` does.
    verify_driver = (
        "import runpy, sys\n"
        f"sys.path.insert(0, {str(BACKEND)!r})\n" + PUBLISH + "sys.argv = ['report', 'verify', "
        f"'--all', '--db', {str(db)!r}]\n"
        "runpy.run_module('app.forecast.report', run_name='__main__', alter_sys=True)\n"
    )
    verify = subprocess.run(
        [sys.executable, "-W", "ignore", "-X", "utf8", "-c", verify_driver],
        capture_output=True, timeout=300, cwd=tmp_path, env=env,
    )  # fmt: skip
    assert verify.returncode == 0 and verify.stderr == b""
    expected = status.stdout + (fs.SEPARATOR + "\n").encode() + verify.stdout
    assert tool.stdout.replace(b"\r\n", b"\n") == expected.replace(b"\r\n", b"\n")


def test_e2e_the_environment_variable_stops_a_real_interpreter(tmp_path: Path, built: Path) -> None:
    script, _, home = _fake_backend(tmp_path, built)
    env = _child_env(home, **{fs.ENV_VAR: ""})
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", _driver(script, PUBLISH)],
        capture_output=True, timeout=300, cwd=tmp_path, env=env,
    )  # fmt: skip
    assert (done.returncode, done.stderr) == (3, b"")
    assert done.stdout.decode().splitlines() == [fs.STOP_ENV]
    assert list(home.iterdir()) == []


FAILING = (
    "from app.forecast import report\n"
    "_real = report.main\n"
    "def boom(argv, *, clock=None):\n"
    "    if argv[0] != {stage!r}:\n"
    "        return _real(argv, clock=clock)\n"
    "    print('stdout secret 偏多'); print('stderr secret', file=sys.stderr)\n"
    "    warnings.warn('secret warning')\n"
    "    raise {exc}\n"
    "report.main = boom\n"
)


@pytest.mark.parametrize("stage", ["status", "verify"])
@pytest.mark.parametrize(
    ("exc", "sentence", "rc"),
    [
        ("RuntimeError('secret /etc/passwd')", UNEXPECTED, 1),
        ("KeyboardInterrupt()", INTERRUPTED, 2),
        ("SystemExit(2)", UNEXPECTED, 1),
    ],
)
def test_e2e_an_exception_or_an_interrupt_shows_only_what_was_shown_and_the_fixed_sentence(
    tmp_path: Path, built: Path, exc: str, sentence: str, rc: int, stage: str
) -> None:
    script, _, home = _fake_backend(tmp_path, built)
    body = PUBLISH + FAILING.format(exc=exc, stage=stage)
    done = _exec(_driver(script, body), home, tmp_path)
    assert (done.returncode, done.stderr) == (rc, b"")
    lines = done.stdout.decode().splitlines()
    assert lines[-1] == sentence
    if stage == "status":
        assert lines == [sentence]
    else:  # part one and the separator were shown; part two never is
        assert lines[-2] == fs.SEPARATOR and lines[0].startswith("執行狀態")
        assert lines.count(sentence) == 1
    assert b"secret" not in done.stdout and b"Traceback" not in done.stdout
    assert list(home.rglob("*")) == []  # no status.txt, no temporary file, no folder


def test_e2e_threads_warnings_unraisables_and_uncaught_errors_print_the_fixed_sentence() -> None:
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
        "import logging; logging.getLogger('x').error('secret log'); logging.warning('secret log')\n"  # noqa: E501
        "raise RuntimeError('secret uncaught')\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", driver], capture_output=True, text=True, timeout=120
    )
    assert done.stderr == ""
    assert done.stdout.splitlines() == [UNEXPECTED] * 3  # thread, unraisable, uncaught
    assert "secret" not in done.stdout and done.returncode != 0


def test_e2e_an_exception_in_a_thread_during_the_run_shows_only_the_fixed_sentence(
    tmp_path: Path, built: Path
) -> None:
    body = (
        "from app.forecast import report\n"
        "_real = report.main\n"
        "def threaded(argv, *, clock=None):\n"
        "    def boom():\n"
        "        raise RuntimeError('secret thread')\n"
        "    t = threading.Thread(target=boom); t.start(); t.join()\n"
        "    return _real(argv, clock=clock)\n"
        "report.main = threaded\n"
    )
    script, _, home = _fake_backend(tmp_path, built)
    done = _exec(_driver(script, PUBLISH + body), home, tmp_path)
    assert done.stderr == b"" and b"secret" not in done.stdout
    lines = done.stdout.decode().splitlines()
    # The hook runs inside the thread while ``report``'s stdout is caught, so its fixed sentence
    # is part of the caught text: two of them (one per command), nothing else leaks.
    assert lines.count(UNEXPECTED) == 2 and fs.SEPARATOR in lines


# --- the launcher --------------------------------------------------------------------------------

COMMAND = r"uv run --no-sync python -I -X utf8 scripts\forecast_status.py"
PRECEDENT_COMMAND = r"uv run --no-sync python -I -X utf8 scripts\pipeline_acceptance_real.py"


def _bat_lines(path: Path) -> list[str]:
    return path.read_bytes().decode("ascii").split("\r\n")


def test_the_bat_is_a_crlf_launcher_that_clears_uv_env_file_first() -> None:
    raw = BAT.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n") and b"\r\r" not in raw
    lines = _bat_lines(BAT)
    assert lines[0] == "@echo off"
    assert 'set "UV_ENV_FILE="' in lines
    assert lines.index('set "UV_ENV_FILE="') < lines.index(COMMAND)
    assert lines.count(COMMAND) == 1
    assert lines.index(COMMAND) < max(i for i, x in enumerate(lines) if x == "pause")
    assert 'cd /d "%BACKEND_DIR%"' in lines
    assert not any("STOCK_DESK" in x or ".env" in x for x in lines if not x.startswith("REM"))
    assert "%*" not in raw.decode("ascii") and "%1" not in raw.decode("ascii")  # no arguments


REPORT_RC318 = "2026-11-20-兩份CEO文件判定RC313至RC324-風控.md"


def backend_missing_extra() -> str:
    """The RC-318 sentence, extracted from the risk-control report (never typed here)."""
    lines = report_file(REPORT_RC318).read_text(encoding="utf-8").splitlines()
    hits = [i for i, x in enumerate(lines) if x.startswith("項目：RC-318 ")]
    assert len(hits) == 1, hits
    assert "`[ERROR] Cannot find the backend folder next to this file.`" in lines[hits[0]]
    following = lines[hits[0] + 1]
    assert following.startswith("定稿全文：`") and following.endswith("`"), following
    return following[len("定稿全文：`") : -1]


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


def test_the_bat_differs_from_the_precedent_only_in_the_listed_lines() -> None:
    new, old = _bat_lines(BAT), _precedent_lines()
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    changes = [
        (tuple(old[i1:i2]), tuple(new[j1:j2]))
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]
    assert changes == [
        (("title stock-desk pipeline-acceptance",), ("title stock-desk forecast-status",)),
        (
            (
                "REM One-click real-data pipeline acceptance: a thin launcher. All logic lives in",
                "REM backend\\scripts\\pipeline_acceptance_real.py (ADR-0030 supplement 6 and its addenda).",  # noqa: E501
                "REM The script copies the database files and reads only the copy; this launcher never",  # noqa: E501
            ),
            (
                "REM One-click forecast status report: a thin launcher. All logic lives in",
                "REM backend\\scripts\\forecast_status.py (ADR-0030 supplement 11 points 2 and 4).",
                "REM The script only reads the main database (no copy, no write); this launcher never",  # noqa: E501
            ),
        ),
        (  # RC-310 (the first line) and the line that asked the user to install and rerun
            (
                "  echo [MISSING] uv - install from https://docs.astral.sh/uv/getting-started/installation/",  # noqa: E501
                "  echo After installing, run this script again.",
            ),
            ("  echo " + missing_uv(), "  echo Tell the coordinator."),
        ),
        ((), ("  echo " + backend_missing_extra(),)),  # RC-318: added under the [ERROR] line
        ((PRECEDENT_COMMAND,), (COMMAND,)),
    ]
    # Seven lines differ from the precedent: 1 + 3 + 2 (RC-310) + 1 (RC-318) added is a new line.
    assert sum(len(o) for o, _ in changes) == 7 and sum(len(n) for _, n in changes) == 8
    assert len(new) == len(old) + 1
    assert not any("After installing" in x for x in new)
    assert "  echo Tell the coordinator." in new


def test_rc318_the_backend_error_line_is_followed_by_the_risk_control_sentence() -> None:
    sentence = backend_missing_extra()
    lines = _bat_lines(BAT)
    at = lines.index("  echo [ERROR] Cannot find the backend folder next to this file.")
    assert lines[at + 1] == "  echo " + sentence and lines[at + 2] == "  goto fail"
    # cmd ``echo`` prints a semicolon as it is; the line's bytes carry no cmd operator character.
    raw = lines[at + 1].encode("ascii")
    assert b";" in raw and not any(c in raw for c in b'&|<>^%!()"')
    assert raw.endswith(b"tell the coordinator.")


def test_the_bat_has_no_non_cmd_redirect_and_only_r2_lines_besides_its_own() -> None:
    lines = _bat_lines(BAT)
    commands = [x for x in lines if not x.startswith("REM")]
    assert not any("/dev/null" in x for x in commands)
    assert "where uv >nul 2>nul" in lines
    r2 = {x for x in _bat_lines(BAT.parent / "r2-probe.bat") if not x.startswith("REM")}
    own = {
        "title stock-desk forecast-status",
        'set "UV_ENV_FILE="',
        COMMAND,
        "  echo Tell the coordinator.",
        "  echo " + missing_uv(),
        "  echo " + backend_missing_extra(),
        "",
    }
    assert [x for x in commands if x not in r2 and x not in own] == []


def test_git_checks_the_bat_out_with_crlf() -> None:
    attributes = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", "apps/stock-desk/forecast-status.bat"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "text: set" in attributes and "eol: crlf" in attributes


def test_the_script_and_the_launcher_are_outside_app() -> None:
    assert SCRIPT_PATH.parent == BACKEND / "scripts" and BAT.parent == BACKEND.parent
    assert not (BACKEND / "app" / "forecast_status.py").exists()


_ = (_publish, STAMP_FOLDER, re)
