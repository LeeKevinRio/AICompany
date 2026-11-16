"""The D-7 real-data pipeline acceptance: reading the ``^TWII`` bars (ADR-0030 supplement 6).

The outer flow (ADR-0030 supplement 6 and its addenda; ``main``): preflight,
a byte copy of the three database files with sha256 comparison, the refusal
guard self-check, the read of the copy (:func:`read_twii_bars`), deletion of the
copy, the depth stop, one :func:`run_acceptance` per placeholder rule set, the
whitelisted ``paste-back.txt`` and cleanup. The pure functions are:

* :func:`read_twii_bars` -- opens **only the copy it is given** (``sqlite3``
  URI ``mode=ro``, plus ``immutable=1`` when the copy has no ``-wal``;
  ``PRAGMA query_only``), SELECTs the eight columns of the
  ``^TWII`` / ``TW`` rows of ``price_bars_cache`` (never ``as_of`` or
  ``fetched_at``), maps each row the way ``PriceBarCache.get`` does and
  stamps ``as_of`` at 20:00 Taipei on the bar's own session, the rule of
  ``synthetic_series``' default;
* :func:`required_sessions` / :func:`check_depth` -- the depth stop:
  N_SNAPSHOT plus :data:`WINDOW_SESSIONS` sessions before the run date, both
  from program derivations;
* :func:`bars_sha256` -- ``app.forecast.canonical.content_sha256`` of the
  injected series (K-6; no serialisation of its own).

Every stop raises :class:`AcceptanceStop` with one kind of a closed set; the
exception carries a fixed sentence and no value, count or path.

Boundaries (supplement 6 point 1 (c), TA C-2): no import of ``app.services``,
``app.data.cache``, ``app.data.service`` or ``app.data.providers``; no network.
The scope of supplement 6 point 1 (b) is this script alone (risk RC-158b).

Screen guarantee (addendum point 5, RC-162): the first statements of this file
replace the three exception hooks with one fixed sentence and silence warnings,
before anything of ``app`` or the harness is imported; ``main`` catches
``BaseException`` and prints a fixed sentence only. Console output is ASCII.
"""

# ruff: noqa: E402 -- the app / tests imports must follow the sys.path step below.

from __future__ import annotations

import sys
import threading
import warnings


def _fixed_hook(*_args: object) -> None:
    """RC-162: whatever escapes, the screen shows this one sentence (no text, no traceback)."""
    sys.stdout.write(
        "ERROR: unexpected failure; no paste-back file was made. Tell the coordinator.\n"
    )


sys.excepthook = _fixed_hook
threading.excepthook = _fixed_hook
sys.unraisablehook = _fixed_hook
warnings.simplefilter("ignore")

from pathlib import Path

# Run as ``python -I scripts/pipeline_acceptance_real.py``: isolated mode puts
# neither the working directory nor this folder's parent on ``sys.path``, so
# the backend directory is added here -- only when it is the one holding
# ``app/`` -- before the ``app`` / ``tests`` imports below. Silent on import.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if (_BACKEND_DIR / "app" / "__init__.py").is_file() and str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import argparse
import gc
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from time import sleep as _sleep
from types import MappingProxyType
from typing import Any, Final, Literal, get_args

from app.advice.banned_phrases import BANNED_PHRASES
from app.data.interface import PriceBar
from app.dirdef.definition import (
    DirectionDefinition,
    definition_logic_sha256,
    definition_sha256,
)
from app.dirdef.rules import OutlookRuleSet, load_ruleset
from app.forecast import recorder, report
from app.forecast.canonical import content_sha256, normalised_source
from app.forecast.store import RunOutcome, system_clock
from app.outlook.engine import n_snapshot
from app.outlook.inputs import SERIES_SYMBOL, _snapshot_bar
from tests import forecast_pipeline_harness as harness
from tests.dirdef_helpers import dirdef_v1_0
from tests.forecast_pipeline_harness import (
    HEADER,
    HORIZONS,
    LEDGER_NAME,
    P0,
    P1,
    WINDOW_SESSIONS,
    FailureKind,
    HarnessRefused,
    PlaceholderRules,
    refuse_production,
    render_summary,
    run_acceptance,
)
from tests.outlook_helpers import TAIPEI

#: The market of the ``^TWII`` rows read.
SERIES_MARKET: Final = "TW"
#: The one source the real run accepts (supplement 6 point 1 (e); F-5 otherwise).
EXPECTED_SOURCE: Final = "yfinance"
#: Sources of the offline demo seeder start with this (a weekday grid, not a real series).
DEMO_SOURCE_PREFIX: Final = "demo"
#: Supplement 6 point 2: the injected stamp hour, equal to ``synthetic_series``' default.
STAMP_HOUR: Final = 20

#: The single SELECT of this script: the eight columns of supplement 6 point 1 (a).
_SELECT_SQL: Final = """
SELECT trade_date, open, high, low, close, volume, currency, source
FROM price_bars_cache
WHERE symbol = ? AND market = ?
ORDER BY trade_date ASC
"""

StopKind = Literal["no_rows", "unparseable_row", "demo_source", "foreign_source", "cache_short"]

#: One fixed ASCII sentence per stop kind; none carries a value, a count or a path.
STOP_SENTENCES: Final[Mapping[StopKind, str]] = MappingProxyType(
    {
        "no_rows": "STOP: the cache copy holds no TWII rows.",
        "unparseable_row": "STOP: a TWII row of the cache copy cannot be read.",
        "demo_source": "STOP: a TWII row of the cache copy comes from the demo seeder.",
        "foreign_source": "STOP: a TWII row of the cache copy is not from the expected source.",
        "cache_short": "STOP: the cache copy holds too few TWII sessions before today.",
    }
)


class AcceptanceStop(Exception):
    """A fail-closed stop of supplement 6 point 1 (e): a closed ``kind``, a fixed sentence."""

    def __init__(self, kind: StopKind) -> None:
        if kind not in get_args(StopKind):
            raise ValueError("unknown stop kind")
        super().__init__(STOP_SENTENCES[kind])
        self.kind: StopKind = kind


# --- reading the copy ---------------------------------------------------------------------


def injected_as_of(day: date) -> datetime:
    """Supplement 6 point 2: 20:00 Asia/Taipei on the bar's own session."""
    return datetime.combine(day, time(STAMP_HOUR), TAIPEI)


def _bar(row: Sequence[Any]) -> PriceBar:
    """One row as ``PriceBarCache.get`` builds it, with the injected ``as_of``."""
    trade_date, open_str, high_str, low_str, close_str, volume, currency, source = row
    day = date.fromisoformat(trade_date)
    return PriceBar(
        symbol=SERIES_SYMBOL,
        market=SERIES_MARKET,
        date=day,
        open=Decimal(open_str),
        high=Decimal(high_str),
        low=Decimal(low_str),
        close=Decimal(close_str),
        volume=volume,
        currency=currency,
        as_of=injected_as_of(day),
        source=source,
    )


def copy_uri(copy_path: Path) -> str:
    """The read-only URI of the copy: ``mode=ro``, plus ``immutable=1`` when it has no ``-wal``.

    The cache database is in WAL mode, and a ``mode=ro`` connection to a WAL
    database creates a ``-wal`` and a ``-shm`` beside it when they are absent.
    Without a ``-wal`` the database file alone holds every committed row, so
    ``immutable=1`` reads it with no side file and no lock. With a copied
    ``-wal`` it must be read (it may hold rows not yet checkpointed into the
    file), so ``immutable`` -- which ignores the WAL -- is not used.
    """
    path = Path(copy_path).resolve()
    query = "mode=ro"
    if not path.with_name(f"{path.name}-wal").exists():
        query += "&immutable=1"
    return f"{path.as_uri()}?{query}"


def read_twii_bars(copy_path: Path) -> list[PriceBar]:
    """The ``^TWII`` bars of the database copy at ``copy_path``, ascending, stamps injected.

    Opens ``copy_path`` read-only (:func:`copy_uri`; a missing file is an
    ``sqlite3.Error`` and is never created) and only through this one
    connection. Raises :class:`AcceptanceStop` when there is no row, when any
    row cannot be read (no row is skipped), when any row comes from the demo
    seeder, or when any row's source is not :data:`EXPECTED_SOURCE`.
    """
    with closing(sqlite3.connect(copy_uri(copy_path), uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute(_SELECT_SQL, (SERIES_SYMBOL, SERIES_MARKET)).fetchall()
    if not rows:
        raise AcceptanceStop("no_rows")
    bars: list[PriceBar] = []
    for row in rows:
        try:
            bars.append(_bar(row))
        except (InvalidOperation, ValueError, TypeError):
            # ``from None``: the parser's own text would carry the row's value.
            raise AcceptanceStop("unparseable_row") from None
    if any(bar.source.startswith(DEMO_SOURCE_PREFIX) for bar in bars):
        raise AcceptanceStop("demo_source")
    if any(bar.source != EXPECTED_SOURCE for bar in bars):
        raise AcceptanceStop("foreign_source")
    return bars


# --- depth ----------------------------------------------------------------------------------


def placeholder_rulesets(rules: Iterable[PlaceholderRules]) -> list[OutlookRuleSet]:
    """Every horizon of the placeholder rule sets, through the real loader."""
    rulesets: list[OutlookRuleSet] = []
    for placeholder in rules:
        for horizon in HORIZONS:
            data = placeholder.rule_bytes(horizon)
            rulesets.append(
                load_ruleset(
                    data,
                    rules_sha256=hashlib.sha256(data).hexdigest(),
                    banned_phrases=BANNED_PHRASES,
                )
            )
    return rulesets


def required_sessions(
    definition: DirectionDefinition, rules: Iterable[PlaceholderRules] = (P0, P1)
) -> int:
    """N_SNAPSHOT of the placeholder rule sets plus :data:`WINDOW_SESSIONS` (point 1 (e))."""
    return n_snapshot(definition=definition, rulesets=placeholder_rulesets(rules)) + WINDOW_SESSIONS


def check_depth(bars: Sequence[PriceBar], *, run_date: date, required: int) -> None:
    """Stop (``cache_short``) with fewer than ``required`` sessions before ``run_date``."""
    if len({bar.date for bar in bars if bar.date < run_date}) < required:
        raise AcceptanceStop("cache_short")


# --- input identity -------------------------------------------------------------------------


def bars_sha256(bars: Iterable[PriceBar]) -> str:
    """Supplement 6 point 4 (c): ``content_sha256`` of the injected series.

    Each bar enters as the snapshot bar the recorder builds from it
    (``app.outlook.inputs._snapshot_bar``: D-5 point 1, ``fetched_at`` equal to
    ``as_of`` per supplement 2 point 3); the serialisation is ``content_sha256``'s own.
    """
    return content_sha256(_snapshot_bar(bar).as_mapping() for bar in bars)


# === the outer flow (supplement 6 points 1-4, 7; addendum points 1, 3, 5; addendum 2) ==========

VERSION_LINE: Final = "pipeline_acceptance_real version=1"
WORK_ROOT_NAME: Final = "stock-desk-pipeline-acceptance"
DB_NAME: Final = "stock-desk.db"
#: The three files of the database, in the fixed order of the ``copy_check`` lines.
DB_FILES: Final = (DB_NAME, f"{DB_NAME}-wal", f"{DB_NAME}-shm")
#: What cleanup also removes beside the copy's three files (never expected to appear).
COPY_EXTRA_FILES: Final = (f"{DB_NAME}-journal",)
COPY_DIR: Final = "copy"
LEDGER_DIRS: Final = MappingProxyType({"P-0": "p0", "P-1": "p1"})
RUN_FOLDER_PATTERN: Final = re.compile(r"\d{8}-\d{6}")
PASTE_BACK_NAME: Final = "paste-back.txt"
PORT: Final = 8000
ENV_VAR: Final = "STOCK_DESK_DB_PATH"
ENV_KEY_PATTERN: Final = re.compile(r"^\s*STOCK_DESK_DB_PATH\s*=")
#: Files of the backend folder whose bytes must equal the repository's (supplement 6 point 7).
PINNED_FILES: Final = ("uv.lock",)
#: Folders and files of the backend folder that must be clean in git.
CLEAN_PATHS: Final = ("app", "tests", "scripts", "uv.lock")
PUBLISHED_REF: Final = "origin/product/stock-desk"
DELETE_ATTEMPTS: Final = 5
DELETE_PAUSE_SECONDS: Final = 0.5
PROMPT: Final = "Close the stock-desk backend, scheduler and frontend windows, then press Enter. "

OuterStopKind = Literal[
    "env_db_path",
    "env_file_db_path",
    "no_db",
    "port_listening",
    "work_in_git",
    "git_unusable",
    "git_dirty",
    "head_unpublished",
    "eol_differs",
    "copy_changed",
    "guard_failed",
    "copy_not_deleted",
]

#: Fixed ASCII sentences of the stops of the outer flow (no value, no path, no count).
#: The Chinese wording of each is in the CEO instruction's STOP table.
OUTER_STOP_SENTENCES: Final[Mapping[OuterStopKind, str]] = MappingProxyType(
    {
        "env_db_path": "STOP: STOCK_DESK_DB_PATH is set in the environment.",
        "env_file_db_path": "STOP: STOCK_DESK_DB_PATH is set in the .env file of the app.",
        "no_db": "STOP: stock-desk.db was not found at the default location.",
        "port_listening": (
            "STOP: something is listening on port 8000; close the stock-desk windows and run again."
        ),
        "work_in_git": "STOP: the work folder would be inside a git work tree.",
        "git_unusable": "STOP: git could not be used on the code folder.",
        "git_dirty": "STOP: the code folder has uncommitted changes.",
        "head_unpublished": "STOP: this code version is not on origin/product/stock-desk.",
        "eol_differs": (
            "STOP: line endings of a pinned file differ from the repository."
            " Tell the coordinator; do not change anything yourself."
        ),
        "copy_changed": "STOP: the database changed while copying; a service is still running.",
        "guard_failed": "STOP: the refusal guard self-check failed.",
        "copy_not_deleted": (
            "STOP: the database copy could not be deleted, so the check did not continue."
            " Remove the whole work folder without opening it, do not send it to anyone,"
            " and tell the coordinator."
        ),
    }
)
#: Same text as the exception hooks at the top of this file.
UNEXPECTED: Final = "ERROR: unexpected failure; no paste-back file was made. Tell the coordinator."
INTERRUPTED: Final = "ERROR: interrupted; no paste-back file was made."


class RunStop(Exception):
    """A stop of the outer flow: a closed ``kind`` and its fixed sentence."""

    def __init__(self, kind: OuterStopKind) -> None:
        if kind not in OUTER_STOP_SENTENCES:
            raise ValueError("unknown stop kind")
        super().__init__(OUTER_STOP_SENTENCES[kind])
        self.kind: OuterStopKind = kind


def say(text: str) -> None:
    """Console output, ASCII only (cmd.exe handles other text unreliably)."""
    print(text.encode("ascii", "backslashreplace").decode("ascii"))


# --- the paste-back whitelist (supplement 6 point 4 (a)) -----------------------------------------

_HEX64 = r"[0-9a-f]{64}"
_OUTCOME = "|".join(get_args(RunOutcome))
_KIND = "|".join(get_args(FailureKind))
#: One entry per allowed shape; a line is kept only when it fullmatches one of them.
WHITELIST: Final[tuple[tuple[str, re.Pattern[str]], ...]] = tuple(
    (name, re.compile(pattern))
    for name, pattern in (
        ("header_1", re.escape(HEADER[0])),
        ("header_2", re.escape(HEADER[1])),
        ("version", re.escape(VERSION_LINE)),
        ("script_sha256_lf", rf"script_sha256_lf={_HEX64}"),
        ("harness_sha256_lf", rf"harness_sha256_lf={_HEX64}"),
        ("git_head", r"git_head=[0-9a-f]{40}"),
        ("git_clean", r"git_clean=yes"),
        ("core_autocrlf", r"core_autocrlf=(false|unset|input|true|other)"),
        ("eol_check", r"eol_check=ok"),
        ("code_digest", rf"code_digest={_HEX64}"),
        ("lockfile_sha256", rf"lockfile_sha256={_HEX64}"),
        ("definition_sha256", rf"definition_sha256={_HEX64}"),
        ("definition_logic_sha256", rf"definition_logic_sha256={_HEX64}"),
        ("db_location", r"db_location=default"),
        ("port_8000_listening", r"port_8000_listening=no"),
        ("copy_check", r"copy_check=(SAME|absent_both)"),
        ("refusal_guard", r"refusal_guard=ok"),
        ("cache_depth", r"cache_depth=sufficient"),
        ("bars_sources", rf"bars_sources={re.escape(EXPECTED_SOURCE)}"),
        ("bars_sha256", rf"bars_sha256={_HEX64}"),
        ("ruleset_result", r"管線驗收 (P-0|P-1)：(通過|失敗)"),
        ("run_counts", rf"執行次數：({_OUTCOME})=\d+(，({_OUTCOME})=\d+)*"),
        ("failure_kinds", rf"失敗種類：(無|({_KIND})(，({_KIND}))*)"),
        ("ledger_sha256", rf"暫存帳 sha256：{_HEX64}"),
        ("output_sha256", rf"輸出 sha256：{_HEX64}"),
        ("acceptance_result", r"acceptance_result=(PASS|FAIL)"),
        ("cleanup", r"cleanup=(ok|FAILED)"),
        ("summary_lines_dropped", r"summary_lines_dropped=\d+"),
        ("done_at_utc", r"done_at_utc=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"),
    )
)
#: ``render_summary``'s window-size line: known and never printed (supplement 6 point 4 (b));
#: it is not counted as dropped.
KNOWN_UNPRINTED: Final = re.compile(r"視窗定案 session 數：\d+")


def apply_whitelist(lines: Iterable[str]) -> tuple[list[str], int]:
    """Keep the lines that fullmatch a whitelist shape; count the others (never print them).

    The known-unprinted window line is skipped and not counted.
    """
    kept: list[str] = []
    dropped = 0
    for line in lines:
        if KNOWN_UNPRINTED.fullmatch(line):
            continue
        if any(pattern.fullmatch(line) for _name, pattern in WHITELIST):
            kept.append(line)
        else:
            dropped += 1
    return kept, dropped


# --- git, line endings (supplement 6 point 7) ----------------------------------------------------

GitRunner = Callable[[Path, Sequence[str]], tuple[int, bytes]]


def run_git(cwd: Path, args: Sequence[str]) -> tuple[int, bytes]:
    """``git -C cwd args``: (return code, stdout bytes); 127 when git cannot run. Never prints."""
    try:
        done = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(cwd), *args],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, b""
    return done.returncode, done.stdout


_EOL_FIELDS = re.compile(rb"i/(\S+)\s+w/(\S+)")


def check_pinned_eol(base_dir: Path, paths: Sequence[str], *, git: GitRunner = run_git) -> bool:
    """True when every pinned file's work-tree bytes equal its ``HEAD`` blob (it changes nothing).

    Evidence one: the sha256 of the raw work-tree bytes against the sha256 of
    ``git cat-file blob HEAD:./<path>`` (no conversion). Evidence two:
    ``git ls-files --eol`` -- a line with ``w/crlf`` or ``w/mixed`` over ``i/lf`` fails too.
    Any git failure is a failure. ``paths`` are relative to ``base_dir``.
    """
    for rel in paths:
        code, blob = git(base_dir, ["cat-file", "blob", f"HEAD:./{rel}"])
        if code != 0:
            return False
        try:
            worktree = (base_dir / rel).read_bytes()
        except OSError:
            return False
        if hashlib.sha256(worktree).digest() != hashlib.sha256(blob).digest():
            return False
    code, listing = git(base_dir, ["ls-files", "--eol", "--", *paths])
    if code != 0:
        return False
    rows = listing.splitlines()
    if len(rows) != len(paths):
        return False
    for row in rows:
        found = _EOL_FIELDS.match(row)
        if found is None:
            return False
        index, work = found.group(1), found.group(2)
        if index == b"lf" and work in (b"crlf", b"mixed"):
            return False
    return True


def core_autocrlf(base_dir: Path, *, git: GitRunner = run_git) -> str:
    """``core.autocrlf`` as a closed word, for the paste-back only (never a judgement)."""
    code, out = git(base_dir, ["config", "--get", "core.autocrlf"])
    value = out.decode("ascii", "ignore").strip().lower() if code == 0 else ""
    if not value:
        return "unset"
    return value if value in ("true", "false", "input") else "other"


# --- files: hashing, copying, deleting -----------------------------------------------------------


def sha256_file(path: Path) -> str:
    """The sha256 of a file's bytes; the file is opened ``"rb"`` only."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_bytes(source: Path, target: Path) -> None:
    """A byte copy: the source is opened ``"rb"`` only, the target is a new file."""
    with open(source, "rb") as reader, open(target, "xb") as writer:
        for chunk in iter(lambda: reader.read(1 << 20), b""):
            writer.write(chunk)


def copy_db_files(source_dir: Path, copy_dir: Path) -> list[str]:
    """Byte-copy the three database files and compare them; return the three verdict lines.

    For each file: its sha256 before the copy, the copy, the sha256 of the copy, and the
    sha256 of the source after the copy; present or absent in both. Anything but all-equal
    stops (``copy_changed``). This finishes before any connection is opened (addendum 2
    point 2 (c)). The source files are only ever opened ``"rb"``.
    """
    copy_dir.mkdir(parents=True)
    verdicts: list[str] = []
    for name in DB_FILES:
        source, target = source_dir / name, copy_dir / name
        present = source.exists()
        before = sha256_file(source) if present else None
        if present:
            _copy_bytes(source, target)
        copied = sha256_file(target) if target.exists() else None
        after = sha256_file(source) if source.exists() else None
        if (present, before) != (target.exists(), copied) or before != after:
            raise RunStop("copy_changed")
        verdicts.append("SAME" if present else "absent_both")
    return [f"copy_check={verdict}" for verdict in verdicts]


Remover = Callable[[Path], None]


def remove_path(path: Path) -> None:
    """Delete a file or a folder tree; an absent path is fine."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def delete_with_retry(
    path: Path, remover: Remover = remove_path, pause: Callable[[float], None] = _sleep
) -> bool:
    """Delete ``path``: 5 tries, 0.5 s apart, ``gc.collect()`` first (Windows holds locks)."""
    for attempt in range(DELETE_ATTEMPTS):
        gc.collect()
        try:
            remover(path)
        except OSError:
            if attempt + 1 < DELETE_ATTEMPTS:
                pause(DELETE_PAUSE_SECONDS)
            continue
        return True
    return False


def delete_copy(
    copy_dir: Path, remover: Remover = remove_path, pause: Callable[[float], None] = _sleep
) -> None:
    """RC-158c / addendum 2 point 2 (d): delete the copy's files incl. ``-shm``, then its folder.

    Every file and the folder are tried; when any is left, stop with ``copy_not_deleted``.
    """
    if not copy_dir.exists():
        return
    left = False
    for name in (*DB_FILES, *COPY_EXTRA_FILES):
        if (copy_dir / name).exists() and not delete_with_retry(copy_dir / name, remover, pause):
            left = True
    if not delete_with_retry(copy_dir, remover, pause):
        left = True
    if left or copy_dir.exists():
        raise RunStop("copy_not_deleted")


def sweep_residue(
    root: Path, remover: Remover = remove_path, pause: Callable[[float], None] = _sleep
) -> bool:
    """Remove ``copy``, ``p0`` and ``p1`` left in earlier run folders; True when all are gone.

    Only folders this script makes (name ``YYYYMMDD-HHMMSS``) and only those three
    sub-folders are touched; a leftover copy that cannot be deleted stops (RC-158c).
    """
    clean = True
    if not root.is_dir():
        return clean
    for folder in sorted(root.iterdir()):
        if folder.is_symlink() or not folder.is_dir():
            continue
        if not RUN_FOLDER_PATTERN.fullmatch(folder.name):
            continue
        if (folder / COPY_DIR).exists():
            delete_copy(folder / COPY_DIR, remover, pause)
        for sub in LEDGER_DIRS.values():
            path = folder / sub
            if path.exists() and not delete_with_retry(path, remover, pause):
                clean = False
    return clean


# --- checks ---------------------------------------------------------------------------------------


def port_is_listening(port: int = PORT) -> bool:
    """One connect to 127.0.0.1 (the only socket use; imported here, not at module level)."""
    import socket

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def inside_git_work_tree(path: Path) -> bool:
    resolved = path.resolve()
    return any((folder / ".git").exists() for folder in (resolved, *resolved.parents))


def env_file_sets_db_path(env_file: Path) -> bool:
    """True when a line of the file starts with the key. Only the key is looked for."""
    if not env_file.is_file():
        return False
    with open(env_file, encoding="utf-8-sig", errors="ignore") as handle:
        return any(ENV_KEY_PATTERN.match(line) for line in handle)


@dataclass(frozen=True)
class Preflight:
    """What the preflight found, as the paste-back lines show it."""

    git_head: str
    autocrlf: str


def preflight(
    *,
    backend_dir: Path,
    work: Path,
    env: Mapping[str, str],
    port_check: Callable[[], bool],
    git: GitRunner,
) -> Preflight:
    """The checks that must hold before anything is copied; each failure is one fixed stop."""
    if ENV_VAR in env:
        raise RunStop("env_db_path")
    if env_file_sets_db_path(backend_dir.parent / ".env"):
        raise RunStop("env_file_db_path")
    if not (backend_dir / "data" / DB_NAME).is_file():
        raise RunStop("no_db")
    if port_check():
        raise RunStop("port_listening")
    if inside_git_work_tree(work):
        raise RunStop("work_in_git")
    code, _top = git(backend_dir, ["rev-parse", "--show-toplevel"])
    if code != 0:
        raise RunStop("git_unusable")
    code, dirty = git(
        backend_dir, ["status", "--porcelain", "--untracked-files=all", "--", *CLEAN_PATHS]
    )
    if code != 0:
        raise RunStop("git_unusable")
    if dirty.strip():
        raise RunStop("git_dirty")
    code, head = git(backend_dir, ["rev-parse", "HEAD"])
    commit = head.decode("ascii", "ignore").strip()
    if code != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RunStop("git_unusable")
    code, _ = git(backend_dir, ["merge-base", "--is-ancestor", "HEAD", PUBLISHED_REF])
    if code != 0:
        raise RunStop("head_unpublished")
    if not check_pinned_eol(backend_dir, PINNED_FILES, git=git):
        raise RunStop("eol_differs")
    return Preflight(git_head=commit, autocrlf=core_autocrlf(backend_dir, git=git))


def refusal_guard_holds(
    *, backend_dir: Path, work: Path, cwd: Path, env: Mapping[str, str]
) -> bool:
    """The counter-example self-check of the guard (it opens no file).

    The production database path must be refused; a ledger path in this run's folder must not.
    """
    production = backend_dir / "data" / DB_NAME
    try:
        refuse_production(production, backend_dir=backend_dir, cwd=cwd, env=env)
    except HarnessRefused:
        refused = True
    else:
        refused = False
    try:
        ledger = work / LEDGER_DIRS["P-0"] / LEDGER_NAME
        refuse_production(ledger, backend_dir=backend_dir, cwd=cwd, env=env)
    except HarnessRefused:
        allowed = False
    else:
        allowed = True
    return refused and allowed


# --- the runs ---------------------------------------------------------------------------

Acceptance = Callable[..., Any]


@dataclass
class RuleSetRun:
    """What one placeholder rule set's run leaves: verdict, summary, whether it was cleaned."""

    passed: bool
    summary: list[str]
    cleaned: bool


def run_ruleset(
    rules: PlaceholderRules,
    *,
    bars: Sequence[PriceBar],
    definition: DirectionDefinition,
    work: Path,
    backend_dir: Path,
    cwd: Path,
    env: Mapping[str, str],
    wall_clock: Callable[[], datetime],
    acceptance: Acceptance,
    remover: Remover,
    pause: Callable[[float], None],
) -> RuleSetRun:
    """One ``run_acceptance`` in its own folder; the folder is deleted afterwards.

    Of the result only ``passed`` is read, and :func:`render_summary` is called on it
    (supplement 6 point 3): the full output goes to no file, no console and no log.
    """
    folder = work / LEDGER_DIRS[rules.name]
    folder.mkdir()
    try:
        result = acceptance(
            folder,
            bars=bars,
            rules=rules,
            definition=definition,
            wall_clock=wall_clock,
            backend_dir=backend_dir,
            env=env,
            cwd=cwd,
        )
        passed = bool(result.passed)
        summary = render_summary(result)
        del result
    finally:
        cleaned = delete_with_retry(folder, remover, pause)
    return RuleSetRun(passed=passed, summary=summary, cleaned=cleaned)


@dataclass
class State:
    """What the cleanup of an abnormal end needs to know."""

    work: Path | None = None


def cleanup(state: State, remover: Remover, pause: Callable[[float], None]) -> None:
    """The safety net: remove ``copy``, ``p0``, ``p1`` of this run, then the folder if empty."""
    work = state.work
    if work is None or not work.exists():
        return
    try:
        delete_copy(work / COPY_DIR, remover, pause)
    except RunStop:
        pass  # the stop (if it matters) was raised where the copy was first deleted
    for sub in LEDGER_DIRS.values():
        if (work / sub).exists():
            delete_with_retry(work / sub, remover, pause)
    try:
        work.rmdir()  # fails (and is ignored) unless the folder is empty
    except OSError:
        pass


def flow(
    state: State,
    *,
    backend_dir: Path,
    home: Path,
    cwd: Path,
    env: Mapping[str, str],
    port_check: Callable[[], bool],
    git: GitRunner,
    wait: Callable[[str], object],
    opener: Callable[[Path], object] | None,
    now: Callable[[], datetime],
    wall_clock: Callable[[], datetime],
    read_bars: Callable[[Path], list[PriceBar]] | None,
    acceptance: Acceptance,
    remover: Remover,
    pause: Callable[[float], None],
) -> int:
    """The whole run; returns the exit code. Console output comes only at the very end."""
    reader = read_bars if read_bars is not None else read_twii_bars
    root = home / WORK_ROOT_NAME
    work = root / now().strftime("%Y%m%d-%H%M%S")
    wait(PROMPT)

    found = preflight(backend_dir=backend_dir, work=work, env=env, port_check=port_check, git=git)

    swept = sweep_residue(root, remover, pause)
    state.work = work
    work.mkdir(parents=True)
    copy_dir = work / COPY_DIR
    copy_lines = copy_db_files(backend_dir / "data", copy_dir)

    if not refusal_guard_holds(backend_dir=backend_dir, work=work, cwd=cwd, env=env):
        raise RunStop("guard_failed")

    try:
        bars = reader(copy_dir / DB_NAME)
    finally:
        delete_copy(copy_dir, remover, pause)  # RC-158c: before the first run_acceptance

    definition = dirdef_v1_0()
    check_depth(
        bars,
        run_date=report.taipei_date(wall_clock()),
        required=required_sessions(definition),
    )
    if sorted({bar.source for bar in bars}) != [EXPECTED_SOURCE]:
        raise AcceptanceStop("foreign_source")
    digest_of_bars = bars_sha256(bars)

    runs = [
        run_ruleset(
            rules,
            bars=bars,
            definition=definition,
            work=work,
            backend_dir=backend_dir,
            cwd=cwd,
            env=env,
            wall_clock=wall_clock,
            acceptance=acceptance,
            remover=remover,
            pause=pause,
        )
        for rules in (P0, P1)
    ]

    script_lf = normalised_source(Path(__file__).read_bytes())
    harness_lf = normalised_source(Path(str(harness.__file__)).read_bytes())
    lines = [
        *HEADER,
        VERSION_LINE,
        f"script_sha256_lf={hashlib.sha256(script_lf).hexdigest()}",
        f"harness_sha256_lf={hashlib.sha256(harness_lf).hexdigest()}",
        f"git_head={found.git_head}",
        "git_clean=yes",
        f"core_autocrlf={found.autocrlf}",
        "eol_check=ok",
        f"code_digest={recorder.LOADED.code_digest}",
        f"lockfile_sha256={recorder.LOADED.runtime['lockfile_sha256']}",
        f"definition_sha256={definition_sha256(definition)}",
        f"definition_logic_sha256={definition_logic_sha256(definition)}",
        "db_location=default",
        "port_8000_listening=no",
        *copy_lines,
        "refusal_guard=ok",
        "cache_depth=sufficient",
        f"bars_sources={EXPECTED_SOURCE}",
        f"bars_sha256={digest_of_bars}",
    ]
    for run in runs:
        # The two fixed header lines are printed once, at the top.
        lines += [line for line in run.summary if line not in HEADER]
    cleaned = swept and all(run.cleaned for run in runs)
    lines.append("acceptance_result=" + ("PASS" if all(run.passed for run in runs) else "FAIL"))
    lines.append("cleanup=" + ("ok" if cleaned else "FAILED"))

    kept, dropped = apply_whitelist(lines)
    kept += [f"summary_lines_dropped={dropped}", f"done_at_utc={_utc_stamp(datetime.now(UTC))}"]
    with open(work / PASTE_BACK_NAME, "w", encoding="utf-8-sig") as handle:
        handle.write("\n".join(kept) + "\n")
    for line in kept:
        say(line)
    if opener is None and sys.platform == "win32":
        opener = getattr(os, "startfile", None)
    if opener is not None:
        try:
            opener(work / PASTE_BACK_NAME)
        except OSError:
            pass  # the paste-back file is in the work folder; the instruction says where
    return 0


def _utc_stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: Sequence[str] | None = None, **injected: Any) -> int:
    """Run the acceptance; the screen shows whitelisted lines or one fixed sentence (RC-162).

    ``injected`` are the test seams (``env``, ``cwd``, ``port_check``, ``git``, ``wait``,
    ``opener``, ``now``, ``wall_clock``, ``read_bars``, ``acceptance``, ``remover``,
    ``pause``); the batch file passes none of them.
    """
    state = State()
    code = 1
    remover: Remover = injected.get("remover", remove_path)
    pause: Callable[[float], None] = injected.get("pause", _sleep)
    try:
        parser = argparse.ArgumentParser(prog="pipeline_acceptance_real.py")
        # Test-only overrides; the batch file never passes them.
        parser.add_argument("--backend-dir", default=None, help=argparse.SUPPRESS)
        parser.add_argument("--home", default=None, help=argparse.SUPPRESS)
        args = parser.parse_args(argv)
        backend = Path(args.backend_dir) if args.backend_dir else _BACKEND_DIR
        home = Path(args.home) if args.home else Path.home()
        try:
            code = flow(
                state,
                backend_dir=backend,
                home=home,
                cwd=injected.get("cwd", Path.cwd()),
                env=injected.get("env", os.environ),
                port_check=injected.get("port_check", port_is_listening),
                git=injected.get("git", run_git),
                wait=injected.get("wait", input),
                opener=injected.get("opener"),
                now=injected.get("now", datetime.now),
                wall_clock=injected.get("wall_clock", system_clock),
                read_bars=injected.get("read_bars"),
                acceptance=injected.get("acceptance", run_acceptance),
                remover=remover,
                pause=pause,
            )
        finally:
            cleanup(state, remover, pause)
    except (RunStop, AcceptanceStop) as stop:
        say(str(stop))
        code = 3
    except KeyboardInterrupt:
        say(INTERRUPTED)
        code = 2
    except BaseException:  # noqa: BLE001 - a fixed sentence only, never the exception or a path
        say(UNEXPECTED)
        code = 1
    try:
        cleanup(state, remover, pause)
    except BaseException:  # noqa: BLE001 - best effort; the next start sweeps what is left
        pass
    return code


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI tests
    raise SystemExit(main())
