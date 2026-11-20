"""The one-click forecast status report: ``report status`` then ``report verify --all``.

Authority: ADR-0030 supplement 11 points 2 and 4 (S-21a); fixed sentences RC-291, RC-298, RC-299.

What it does (one run, started by ``forecast-status.bat``): two pre-checks, then the two read-only
commands of :mod:`app.forecast.report` on the main database
``<backend>/data/stock-desk.db`` (the folder of this script's parent; no path, no argument is
taken from the command line or the environment), then one output: the screen and
``~/stock-desk-status/<time>/status.txt`` (``utf-8-sig``, opened in Notepad) carry the same text.

Pre-checks (only these two): ``STOCK_DESK_DB_PATH`` in the process environment (even empty) stops
before any connection is opened; a status folder inside a git work tree stops before anything is
read or written. ``.env`` is never read; no port or git-cleanliness check.

Order (supplement 11 point 2, kept in :func:`flow`): the environment check, the status folder and
its git check (nothing is created yet), ``status`` (stdout and stderr caught in memory), its part
one and the separator shown, ``verify --all`` (caught the same way), part two shown, then what was
shown is written to a temporary file that is renamed to ``status.txt``, then Notepad. Cases
(``status`` code, ``verify`` code):

* status 3 / 4 -> only the RC-291 STOP sentence; ``verify`` is not run; no file;
* status 0, verify 0 / 1 -> part one, the separator, part two (and, for 1, the action sentence);
  file written and opened;
* status 0, verify 3 / 4 -> part one, the separator, the RC-299 STOP sentence; file written;
* anything else (other exit code, ``SystemExit``, any exception, an interrupt, a failed write)
  -> the RC-291 ERROR sentence after whatever was already shown; no ``status.txt`` and no
  temporary file is left. A failure to open Notepad after the rename is silent (RC-303).

Everything ``report`` writes to stderr (``refused: ...``, argparse usage) is caught and dropped:
it is on neither the screen nor in the file. The output of ``report`` is never edited, filtered
or reordered; the only lines added are the fixed sentences below.

Screen guarantee (RC-158a, RC-162): the first statements of this file replace the three
exception hooks with the fixed ERROR sentence and silence warnings and logging; ``main`` catches
``BaseException``; no traceback, path or exception text is ever shown.

Boundaries: standard library plus ``app.forecast.report`` only (no harness, no ``tests``, no other
``app.forecast`` module, nothing under ``work/``); no network; nothing is written inside the
repository (``apps/stock-desk/``); the main database is only read, through ``report`` and the
store's read-only path (never copied); no schedule is created.
"""

# ruff: noqa: E402 -- the imports must follow the exception hooks (RC-162).

from __future__ import annotations

import logging
import sys
import threading
import warnings


def _fixed_hook(*_args: object) -> None:
    """RC-162: whatever escapes, the screen shows this one sentence (no text, no traceback)."""
    sys.stdout.write("ERROR: unexpected failure. Tell the coordinator.\n")


sys.excepthook = _fixed_hook
threading.excepthook = _fixed_hook
sys.unraisablehook = _fixed_hook
warnings.simplefilter("ignore")
logging.disable(logging.CRITICAL)

from pathlib import Path

# Run as ``python -I scripts/forecast_status.py``: isolated mode puts neither the working
# directory nor this folder's parent on ``sys.path``, so the backend directory is added here --
# only when it is the one holding ``app/`` -- before the ``app`` import below. Silent on import.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if (_BACKEND_DIR / "app" / "__init__.py").is_file() and str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import io
import os
import subprocess
from collections.abc import Callable, Iterable, Mapping
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from app.forecast import report

DB_NAME: Final = "stock-desk.db"
WORK_ROOT_NAME: Final = "stock-desk-status"
STATUS_NAME: Final = "status.txt"
TEMP_NAME: Final = "status.txt.tmp"
STAMP_FORMAT: Final = "%Y%m%d-%H%M%S"
ENV_VAR: Final = "STOCK_DESK_DB_PATH"
#: The ``report`` exit codes this script distinguishes (ADR-0030 D-1; report.py module docstring).
CODE_OK: Final = 0
CODE_INCONSISTENT: Final = 1
CODE_UNREADABLE: Final = 3
CODE_PATH_REFUSED: Final = 4
#: The exit codes of this script (the launcher shows a note for any non-zero one).
EXIT_DONE: Final = 0
EXIT_ERROR: Final = 1
EXIT_INTERRUPTED: Final = 2
EXIT_STOP: Final = 3

# Fixed sentences, verbatim from the risk-control reports (RC-291 in
# 2026-11-20-補充十一與退役通知判定RC284至RC297-風控.md; RC-298 and RC-299 in
# 2026-11-20-補充十一增修確認與三句固定行RC298至RC302-風控.md), extracted by script.
STOP_ENV: Final = (
    "STOP: STOCK_DESK_DB_PATH is set in the environment. Do not change "
    "any setting or file yourself; tell the coordinator."
)
STOP_NOT_FOUND: Final = (
    "STOP: stock-desk.db was not found at the default location. Do not "
    "change any setting or file yourself; tell the coordinator."
)
STOP_UNREADABLE: Final = (
    "STOP: the execution status could not be read from the database, "
    "so nothing was shown. Do not change any setting or file yourself; "
    "tell the coordinator."
)
STOP_IN_GIT: Final = "STOP: the work folder would be inside a git work tree."
UNEXPECTED: Final = "ERROR: unexpected failure. Tell the coordinator."
INTERRUPTED: Final = "ERROR: interrupted. You can run this again."
SEPARATOR: Final = (
    "以下是第二段：重算核對（verify）。這一段只檢查每筆紀錄能否以快照重"
    "算出相同內容，不顯示任何判斷，也不是績效。"
)
ACTION: Final = (
    "上一行的「停止記錄並查明」由 coordinator 安排，不是請您操作：請不"
    "要自己停止程式，也不要刪改資料或設定；把這份內容整段貼回，並告訴 c"
    "oordinator。"
)
STOP_VERIFY: Final = (
    "STOP: the recomputation check could not be read from the "
    "database, so it was not shown. Do not change any setting or file "
    "yourself; tell the coordinator."
)

ReportMain = Callable[..., int]


@dataclass
class State:
    """What the cleanup of an abnormal end needs to know."""

    #: Everything shown so far, in order: the file receives exactly this text.
    shown: list[str] = field(default_factory=list)
    folder: Path | None = None
    temp: Path | None = None
    final: Path | None = None
    #: True once the temporary file was renamed to ``status.txt`` (RC-303: nothing after it fails).
    committed: bool = False


def say(text: str) -> None:
    """The one place that writes to the screen (besides the hook above)."""
    sys.stdout.write(text)
    sys.stdout.flush()


def main_db_path() -> Path:
    """The main database, derived from this script's place: ``<backend>/data/stock-desk.db``."""
    return _BACKEND_DIR / "data" / DB_NAME


def inside_git_work_tree(path: Path) -> bool:
    resolved = path.resolve()
    return any((folder / ".git").exists() for folder in (resolved, *resolved.parents))


def run_report(
    report_main: ReportMain, args: Iterable[str], clock: Callable[[], datetime] | None
) -> tuple[int, str]:
    """One ``report`` command: (exit code, its stdout). Its stderr is read and dropped."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = report_main(list(args), clock=clock)
    return code, out.getvalue()


def work_folder(home: Path, now: datetime) -> Path:
    return home / WORK_ROOT_NAME / now.strftime(STAMP_FORMAT)


def new_folder(wanted: Path) -> Path:
    """Create a folder that did not exist (a run in the same second gets a numbered one)."""
    for number in range(1, 100):
        candidate = wanted if number == 1 else wanted.with_name(f"{wanted.name}-{number}")
        try:
            candidate.mkdir(parents=True)
        except FileExistsError:
            continue
        return candidate
    raise FileExistsError("no free folder")


def show(state: State, text: str) -> None:
    """Part of the result leaves the process: onto the screen, and into what the file will hold."""
    say(text)
    state.shown.append(text)


def save(state: State, wanted: Path) -> None:
    """Write what was shown to a temporary file, then rename it to ``status.txt``."""
    state.folder = new_folder(wanted)
    state.temp = state.folder / TEMP_NAME
    state.final = state.folder / STATUS_NAME
    with open(state.temp, "w", encoding="utf-8-sig") as handle:
        handle.write("".join(state.shown))
    os.replace(state.temp, state.final)
    state.committed = True


def open_in_notepad(path: Path) -> None:
    subprocess.Popen(["notepad.exe", str(path)])


def flow(state: State, injected: Mapping[str, Any]) -> int:
    """The supplement 11 order: pre-checks, ``status``, ``verify``, then one write; exit code."""
    env: Mapping[str, str] = injected.get("env", os.environ)
    if ENV_VAR in env:
        say(STOP_ENV + "\n")
        return EXIT_STOP
    now: datetime = injected.get("now", datetime.now)()
    wanted = work_folder(injected.get("home", Path.home()), now)
    if inside_git_work_tree(wanted):
        say(STOP_IN_GIT + "\n")
        return EXIT_STOP
    report_main: ReportMain = injected.get("report_main", report.main)
    clock: Callable[[], datetime] | None = injected.get("clock")
    db = str(main_db_path())

    code, first = run_report(report_main, ["status", "--db", db], clock)
    if code == CODE_PATH_REFUSED:
        say(STOP_NOT_FOUND + "\n")
        return EXIT_STOP
    if code == CODE_UNREADABLE:
        say(STOP_UNREADABLE + "\n")
        return EXIT_STOP
    if code != CODE_OK:
        raise RuntimeError("unexpected exit code")
    show(state, first + SEPARATOR + "\n")

    code, second = run_report(report_main, ["verify", "--all", "--db", db], clock)
    if code in (CODE_UNREADABLE, CODE_PATH_REFUSED):
        show(state, STOP_VERIFY + "\n")
    elif code == CODE_OK:
        show(state, second)
    elif code == CODE_INCONSISTENT:
        show(state, second + ACTION + "\n")
    else:
        raise RuntimeError("unexpected exit code")

    save(state, wanted)
    opener: Callable[[Path], object] | None = injected.get("opener")
    if opener is None and sys.platform == "win32":
        opener = open_in_notepad
    if opener is not None and state.final is not None:
        try:
            opener(state.final)
        except BaseException:  # noqa: BLE001 - RC-303: the file is saved; stay silent
            pass
    return EXIT_DONE


def cleanup(state: State) -> None:
    """An abnormal end before the rename leaves no file, no temporary file and no folder."""
    if state.committed:
        return
    if state.temp is not None:
        state.temp.unlink(missing_ok=True)
    if state.final is not None:
        state.final.unlink(missing_ok=True)
    if state.folder is not None:
        state.folder.rmdir()
        try:
            state.folder.parent.rmdir()  # the status root, when this run was the first to make it
        except OSError:
            pass  # it holds the folders of earlier runs


def main(**injected: Any) -> int:
    """Run the report; the screen shows the report or one fixed sentence (RC-162, RC-291).

    ``injected`` are the test seams (``env``, ``home``, ``now``, ``clock``, ``report_main``,
    ``opener``); the launcher passes none of them and this script reads no command line.
    """
    state = State()
    try:
        return flow(state, injected)
    except KeyboardInterrupt:
        sentence, code = INTERRUPTED, EXIT_INTERRUPTED
    except BaseException:  # noqa: BLE001 - a fixed sentence only, never the exception or a path
        sentence, code = UNEXPECTED, EXIT_ERROR
    try:
        cleanup(state)
    except BaseException:  # noqa: BLE001 - best effort; the sentence below is what matters
        pass
    try:
        say(sentence + "\n")
    except BaseException:  # noqa: BLE001 - nothing left to show
        pass
    return code


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI tests
    raise SystemExit(main())
