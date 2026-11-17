"""The CG-2 one-click files: the read-only preflight and the registration (ADR-0030 supplement 4).

Two modes of one script (``python -I -X utf8 scripts/cg2_register.py preflight|register``):

* ``preflight`` -- read-only. Supplement 4 point 5 R-1 to R-4 and R-6, the supplement 7
  addendum 2 point 9 line-ending evidence, and the M-8 constants. A passing run writes one
  whitelisted paste-back file (``utf-8-sig``) and opens it in Notepad.
* ``register`` -- repeats the whole preflight, then in this order: the R-5 backup (SQLite backup
  API, outside the git work tree, never deleted), the typed R-8 answer, the call of
  ``python -I -X utf8 -m app.forecast.claims bootstrap --production`` in a child process, the exit
  code handling and the paste-back. This script itself opens no write connection to the main
  database: its only connections to it are read-only (``mode=ro``) ones -- R-4 and the backup's
  source -- and the only database it writes is the new backup file.

Boundaries:

* no import of ``app.forecast.claims``, ``store``, ``schema`` or ``recorder``; the registration is
  only ever the child process;
* the main database is never opened with ``open()``, never hashed, never stat-ed for a time, and
  nothing is ever deleted, renamed or replaced by this script (RC-181: after a refusal the file
  hash is no evidence about the database, so none is taken);
* the child's output is never forwarded: every line is checked against a closed set of shapes.

Screen guarantee (RC-162): the first statements of this file replace the three exception hooks
with one fixed sentence and silence warnings, before anything of ``app`` is imported; ``main``
catches ``BaseException`` and prints a fixed sentence only. Console output is ASCII. The paste-back
holds fixed text, counts, hashes, the commit and times -- no path and no identifier.

Copied (not imported) from ``scripts/pipeline_acceptance_real.py``: the hooks, ``say``,
``sha256_file``, ``run_git`` (plus a ``GIT_*`` environment clean-up), ``inside_git_work_tree``,
``port_is_listening``, ``env_file_sets_db_path``, ``core_autocrlf``, the ``ls-files --eol`` field
reading, the whitelist application and the paste-back writing and opening.
"""

# ruff: noqa: E402 -- the app imports must follow the sys.path step below.

from __future__ import annotations

import logging
import sys
import threading
import warnings


def _fixed_hook(*_args: object) -> None:
    """RC-162: whatever escapes, the screen shows this one sentence (no text, no traceback)."""
    sys.stdout.write("ERROR: unexpected failure. Do not run this again; tell the coordinator.\n")


sys.excepthook = _fixed_hook
threading.excepthook = _fixed_hook
sys.unraisablehook = _fixed_hook
warnings.simplefilter("ignore")
logging.disable(logging.CRITICAL)

from pathlib import Path

# Run as ``python -I scripts/cg2_register.py``: isolated mode puts neither the working directory
# nor this folder's parent on ``sys.path``, so the backend directory is added here -- only when it
# is the one holding ``app/`` -- before the ``app`` imports below. Silent on import.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if (_BACKEND_DIR / "app" / "__init__.py").is_file() and str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import argparse
import hashlib
import os
import re
import sqlite3
import subprocess
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Final, Literal, NoReturn, Protocol

from app.dirdef.definition import definition_logic_sha256, definition_sha256
from app.dirdef.rules import rules_logic_sha256
from app.forecast import canonical, definitions

# === constants (M-8: supplement 4 point 5) ======================================================

VERSION_LINE: Final = "cg2_oneclick version=1"
BACKEND_REL: Final = "apps/stock-desk/backend"
APP_REL: Final = f"{BACKEND_REL}/app"
#: This script and its two launchers: part of what R-1 requires to be clean (addendum 3 point 1).
SCRIPT_REL: Final = f"{BACKEND_REL}/scripts/cg2_register.py"
BAT_RELS: Final = ("apps/stock-desk/cg2-preflight.bat", "apps/stock-desk/cg2-register.bat")
PUBLISHED_REF: Final = "origin/product/stock-desk"
DB_NAME: Final = "stock-desk.db"
ENV_VAR: Final = "STOCK_DESK_DB_PATH"
ENV_KEY_PATTERN: Final = re.compile(r"^\s*STOCK_DESK_DB_PATH\s*=")
PORT: Final = 8000
#: The two ledger prefixes (``app.forecast.schema.LEDGER_PREFIXES``; a test keeps them equal).
LEDGER_PREFIXES: Final = ("forecast_", "plan_")
WORK_ROOT_NAME: Final = "stock-desk-cg2-registration"
BACKUP_DIR_NAME: Final = "backups"
PASTE_DIR_NAME: Final = "paste-backs"
RULES_VERSIONS: Final = ("outlook-market-v1.0-h3", "outlook-market-v1.0-h5")
DEFINITION_VERSION: Final = "dirdef-v1.0"


@dataclass(frozen=True)
class FrozenFile:
    """One frozen file: its role, its repo-relative path and the sha256 of its bytes."""

    role: Literal["h3", "h5", "prereg", "c8"]
    path: str
    sha256: str


@dataclass(frozen=True)
class RulesPin:
    """A published rule set: its horizon and the two registered hashes (M-5)."""

    horizon: int
    version: str
    rules_sha256: str
    rules_logic_sha256: str


@dataclass(frozen=True)
class Pins:
    """Everything the one-click fixes as constants (M-2 to M-5, the app tree of the CG-2 PR)."""

    frozen_files: tuple[FrozenFile, ...]
    #: The git tree id of ``app/`` in the CG-2 PR (R-1: ``app/`` has no diff since then).
    app_tree_id: str
    definition_version: str
    definition_sha256: str
    definition_logic_sha256: str
    rules: tuple[RulesPin, RulesPin]
    #: ``--review-refs`` of the registration: repo-relative records, passed space separated.
    review_refs: tuple[str, ...]

    def frozen(self, role: str) -> FrozenFile:
        return next(item for item in self.frozen_files if item.role == role)


REAL_PINS: Final = Pins(
    frozen_files=(
        FrozenFile(
            "prereg",
            "work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md",
            "7c45b0ba79e04a7a74a2b8bc91603cb0bfbd78101b51ab8403cc4ed45a4b406e",
        ),
        FrozenFile(
            "c8",
            "work/dispatch/2026-11-15-C8決策紀錄-F2B.md",
            "c942642c1958e6259545c4f64b4202fbafecf585f1f2cbe513961190af0ea54f",
        ),
        FrozenFile(
            "h3",
            f"{APP_REL}/outlook/rules/h3.yaml",
            "f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443",
        ),
        FrozenFile(
            "h5",
            f"{APP_REL}/outlook/rules/h5.yaml",
            "0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c",
        ),
    ),
    app_tree_id="9c157d8640fb97d7e90dc7edc3f5ff0252aa00d7",
    definition_version=DEFINITION_VERSION,
    definition_sha256="2a58bca61c647931ecaf56aa5d17e4bfffc048c30944f3550feceadbfdacc4d0",
    definition_logic_sha256="4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa",
    rules=(
        RulesPin(
            3,
            RULES_VERSIONS[0],
            "f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443",
            "ddd3c51a1cb9b30a3e957a5a98888ca48916deb35f66027f2f49e7b824f34484",
        ),
        RulesPin(
            5,
            RULES_VERSIONS[1],
            "0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c",
            "e5310b8e6ce14525e81616eedd4368d45a682cb8a4647129ea5617a41cedf1bb",
        ),
    ),
    # Final list (coordinator, addendum 3 point 4): records that approve or check the content.
    # The last two are written after the final review; until they are in HEAD the run time
    # check (check_review_refs) stops, which is the intended state.
    review_refs=(
        "work/reviews/2026-11-15-凍結包第2輪單項確認-風控.md",
        "work/reviews/2026-11-15-事先宣告v0.32套用單項確認-風控.md",
        "work/reviews/2026-11-15-C8決策紀錄檔確認-風控.md",
        "work/reviews/2026-11-17-CG2登記PR-M9核對M2M3M6-風控.md",
        "work/reviews/2026-11-17-CG2登記PR-M9最終審查-qa.md",
    ),
)

# === fixed sentences =============================================================================

_TELL: Final = " Do not change any setting or file yourself; tell the coordinator."

StopKey = Literal[
    "usage",
    "work_in_git",
    "env_db_path",
    "env_file_db_path",
    "no_db",
    "port_listening",
    "git_unusable",
    "git_dirty",
    "head_unpublished",
    "app_changed",
    "frozen_bytes",
    "frozen_eol",
    "hashes_differ",
    "banned_phrase",
    "ledger_objects",
    "db_unreadable",
    "backup_failed",
    "backup_integrity",
    "backup_has_ledger",
    "bad_answer",
    "claims_unreachable",
    "refused_3",
    "refused_4",
    "written_5",
    "written_unknown",
    "output_unverified",
    "preflight_mismatch",
    "review_refs_missing",
    "backup_mismatch",
    "claims_not_started",
]

#: (exit code, sentence). Exit 3: nothing was written. Exit 5: written, or not known to be not.
STOPS: Final[Mapping[StopKey, tuple[int, str]]] = MappingProxyType(
    {
        "usage": (
            3,
            "STOP: usage is cg2_register.py preflight or cg2_register.py register." + _TELL,
        ),
        "work_in_git": (
            3,
            "STOP: the work folder would be inside a git work tree." + _TELL,
        ),
        "env_db_path": (3, "STOP: STOCK_DESK_DB_PATH is set in the environment." + _TELL),
        "env_file_db_path": (
            3,
            "STOP: STOCK_DESK_DB_PATH is set in the .env file of the app." + _TELL,
        ),
        "no_db": (3, "STOP: stock-desk.db was not found at the default location." + _TELL),
        "port_listening": (
            3,
            "STOP: something is listening on port 8000. Close the stock-desk windows and run"
            " again. Do not change any setting or file.",
        ),
        "git_unusable": (3, "STOP: git could not be used on the code folder." + _TELL),
        "git_dirty": (
            3,
            "STOP: a file the registration depends on has uncommitted changes." + _TELL,
        ),
        "head_unpublished": (
            3,
            "STOP: this code version is not on origin/product/stock-desk." + _TELL,
        ),
        "app_changed": (
            3,
            "STOP: the app folder differs from the version this registration was prepared for."
            + _TELL,
        ),
        "frozen_bytes": (
            3,
            "STOP: a frozen file differs from the committed version or from its fixed hash."
            + _TELL,
        ),
        "frozen_eol": (
            3,
            "STOP: line endings or attributes of a frozen file differ from the repository." + _TELL,
        ),
        "hashes_differ": (
            3,
            "STOP: a rule set or definition hash differs from the fixed value." + _TELL,
        ),
        "banned_phrase": (
            3,
            "STOP: the banned phrase check found a hit in a rule set or the definition." + _TELL,
        ),
        "ledger_objects": (
            3,
            "STOP: the main database already holds forecast_ or plan_ objects." + _TELL,
        ),
        "db_unreadable": (
            3,
            "STOP: the main database could not be read in read-only mode." + _TELL,
        ),
        "backup_failed": (
            3,
            "STOP: the backup could not be made. Leave the backup folder as it is." + _TELL,
        ),
        "backup_integrity": (
            3,
            "STOP: the backup did not pass the integrity check. Leave the backup folder as it is."
            + _TELL,
        ),
        "backup_has_ledger": (
            3,
            "STOP: the backup holds forecast_ or plan_ objects. Leave the backup folder as it is."
            + _TELL,
        ),
        "bad_answer": (
            3,
            "STOP: the answer must be exactly 0 or 1. Nothing was registered. Do not"
            " change any setting or file yourself; tell the coordinator.",
        ),
        "claims_unreachable": (
            3,
            "STOP: the registration program could not be reached from this folder." + _TELL,
        ),
        "refused_3": (
            3,
            "STOP: the registration was refused (exit 3). No data was added, changed or deleted."
            + _TELL,
        ),
        "refused_4": (
            3,
            "STOP: the registration was refused (exit 4). No data was added, changed or deleted."
            + _TELL,
        ),
        "written_5": (
            5,
            "STOP: the registration was written but the check afterwards did not pass (exit 5)."
            " Do not run this again. Do not change any file. Tell the coordinator now.",
        ),
        "written_unknown": (
            5,
            "STOP: the registration program ended in an unexpected way. It is not known whether"
            " anything was written. Do not run this again. Do not change any file."
            " Tell the coordinator now.",
        ),
        "output_unverified": (
            5,
            "STOP: the registration finished but its output did not match what was expected."
            " Do not run this again. Do not change any file. Tell the coordinator now.",
        ),
        "preflight_mismatch": (
            3,
            "STOP: no preflight result that passed and matches this code version was"
            " found. Nothing was registered. Do not change any setting or file"
            " yourself; tell the coordinator.",
        ),
        "review_refs_missing": (
            3,
            "STOP: a review record the registration refers to is not in this code"
            " version. Nothing was registered. Do not change any setting or file"
            " yourself; tell the coordinator.",
        ),
        "backup_mismatch": (
            3,
            "STOP: the two backups are not identical. Leave the backup folder as it"
            " is. Nothing was registered. Do not change any setting or file yourself;"
            " tell the coordinator.",
        ),
        "claims_not_started": (
            3,
            "STOP: the registration program could not be started. Nothing was"
            " registered. Do not change any setting or file yourself; tell the"
            " coordinator.",
        ),
    }
)
#: The stops of addendum 3 (RC-200, RC-201): their sentences are the risk-final ones.
NEW_STOP_KEYS: Final = (
    "preflight_mismatch",
    "review_refs_missing",
    "backup_mismatch",
    "claims_not_started",
)
PROMPT_CLOSE: Final = (
    "Close the stock-desk backend, scheduler and frontend windows, then press Enter. "
)
PROMPT_SEEN: Final = (
    "Before this registration, have you seen any provisional comparison"
    " (whether any market outlook call turned out right or wrong, or how it"
    " compared with the baseline), from any source? Type 1 if you have, or 0"
    " if you have not, then press Enter: "
)
INTERRUPTED_SAFE: Final = "ERROR: interrupted; nothing was registered. No paste-back file was made."
INTERRUPTED_LATE: Final = (
    "ERROR: interrupted during the registration; it may have been written."
    " Do not run this again; tell the coordinator."
)
UNEXPECTED_SAFE: Final = (
    "ERROR: unexpected failure before the registration; nothing was registered."
    " No paste-back file was made. Tell the coordinator."
)
UNEXPECTED_LATE: Final = (
    "ERROR: unexpected failure during the registration; it may have been written."
    " Do not run this again; tell the coordinator."
)
#: Same text as the exception hooks at the top of this file.
HOOK_SENTENCE: Final = "ERROR: unexpected failure. Do not run this again; tell the coordinator."


class RunStop(Exception):
    """A stop: a closed ``key`` and its fixed sentence; the exit code comes from the table."""

    def __init__(self, key: StopKey, *, reason: str | None = None) -> None:
        if key not in STOPS:
            raise ValueError("unknown stop key")
        super().__init__(STOPS[key][1])
        self.key: StopKey = key
        self.exit_code: int = STOPS[key][0]
        #: Only for the two refusals of the registration program: a code of the closed set.
        self.reason: str | None = reason


def say(text: str) -> None:
    """Console output, ASCII only (cmd.exe handles other text unreliably)."""
    print(text.encode("ascii", "backslashreplace").decode("ascii"))


# === the whitelist ===============================================================================

_HEX64 = r"[0-9a-f]{64}"
_STAMP = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00"
_SCAN = r"hits 0 rules_strings \d+ definition_strings \d+ phrases \d+"
#: One entry per allowed shape; a line is shown or written only when it fullmatches one of them.
WHITELIST: Final[tuple[tuple[str, re.Pattern[str]], ...]] = tuple(
    (name, re.compile(pattern))
    for name, pattern in (
        ("version", re.escape(VERSION_LINE)),
        ("mode", r"mode=(preflight|register)"),
        ("script_sha256_lf", rf"script_sha256_lf={_HEX64}"),
        ("git_head", r"git_head=[0-9a-f]{40}"),
        ("git_clean", r"git_clean=yes"),
        ("core_autocrlf", r"core_autocrlf=(false|unset|input|true|other)"),
        ("head_published", r"head_published=yes"),
        ("app_unchanged", r"app_unchanged=yes"),
        ("code_digest", rf"code_digest={_HEX64}"),
        ("frozen_sha256", rf"frozen_(prereg|c8|h3|h5)_sha256={_HEX64}"),
        ("eol_check", r"eol_check=ok"),
        ("attr_check", r"attr_check=ok"),
        ("definition_sha256", rf"definition_sha256={_HEX64}"),
        ("definition_logic_sha256", rf"definition_logic_sha256={_HEX64}"),
        ("rules_sha256", rf"rules_sha256_h(3|5)={_HEX64}"),
        ("rules_logic_sha256", rf"rules_logic_sha256_h(3|5)={_HEX64}"),
        ("hashes_pinned", r"hashes_pinned=ok"),
        ("env_db_path", r"env_db_path=unset"),
        ("db_location", r"db_location=default"),
        ("port_8000_listening", r"port_8000_listening=no"),
        ("ledger_objects", r"ledger_objects=none"),
        ("banned_phrase_scan", rf"banned_phrase_scan_h(3|5)={_SCAN}"),
        ("preflight_result", r"preflight_result=PASS"),
        ("backup_integrity", r"backup_integrity=ok"),
        ("backup_ledger_objects", r"backup_ledger_objects=none"),
        ("backup_sha256", rf"backup_sha256={_HEX64}"),
        ("bootstrap", r"bootstrap=ok"),
        ("registered_rows", r"registered_rows=2"),
        ("frozen_commit", r"frozen_commit=[0-9a-f]{40}"),
        ("prereg_doc_sha256", rf"prereg_doc_sha256={_HEX64}"),
        ("registered_at", rf"registered_at_h(3|5)={_STAMP}"),
        ("provisional_results_seen", r"provisional_results_seen=[01]"),
        ("post_commit_check", r"post_commit_check=ok"),
        ("register_result", r"register_result=(DONE|UNCONFIRMED)"),
        ("done_at_utc", r"done_at_utc=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"),
    )
)


def on_whitelist(line: str) -> bool:
    return any(pattern.fullmatch(line) for _name, pattern in WHITELIST)


#: The registration program's refusal sentences (copies of ``claims.BOOTSTRAP_PATH_REFUSALS`` for
#: exit 4 and ``claims.BOOTSTRAP_REFUSALS`` for exit 3; a test keeps them equal). The script does
#: not import ``claims``. A refusal's stderr is never shown; it only selects a key of these tables.
REFUSALS_EXIT_4: Final[Mapping[str, str]] = MappingProxyType(
    {
        "db_missing": "refused: the production database is not at its default location",
        "db_not_default": "refused: the production database resolves to another location",
        "db_not_regular": "refused: the production database is not a regular file",
        "env_db_path": "refused: STOCK_DESK_DB_PATH is set in the environment",
        "env_file_db_path": "refused: STOCK_DESK_DB_PATH is set in the .env file of the app",
        "not_empty": "refused: the production database already holds forecast_ or plan_ objects",
        "horizons": "refused: the two claims must be the h3 then the h5 rule set",
        "replaces": "refused: a bootstrap claim replaces no claim",
    }
)
REFUSALS_EXIT_3: Final[Mapping[str, str]] = MappingProxyType(
    {
        "provisional": "refused: --provisional-results-seen must be typed as 0 or 1",
        "frozen_commit": "refused: --frozen-commit must be 40 lower-case hex digits",
        "prereg_path": "refused: --prereg-doc-path is not a repo-relative path",
        "prereg_sha256": "refused: --prereg-doc-sha256 must be 64 lower-case hex digits",
        "prereg_blob": "refused: the pre-registration blob cannot be read at --frozen-commit",
        "prereg_mismatch": "refused: the pre-registration blob does not match --prereg-doc-sha256",
        "review_refs": "refused: --review-refs must be repo-relative paths separated by spaces",
        "unpublished": "refused: a rule set or the definition is not published or is rejected",
        "phrases": "refused: a banned phrase is in a rule set or the definition",
        "store": "refused: the store refused the registration; nothing was written",
    }
)
REFUSAL_CODES: Final = (*REFUSALS_EXIT_4, *REFUSALS_EXIT_3, "unknown")
#: Screen only (never in a paste-back file): the reason line after a refusal's STOP sentence.
REFUSAL_PATTERN: Final = re.compile(r"refusal_reason=(" + "|".join(REFUSAL_CODES) + ")")


def refusal_reason(exit_code: int, stderr: str) -> str:
    """The code of the table line ``stderr`` equals (trailing newline removed), else ``unknown``.

    Exact comparison against the table of that exit code; the text itself is never shown.
    """
    table = REFUSALS_EXIT_4 if exit_code == 4 else REFUSALS_EXIT_3
    text = stderr.rstrip("\r\n")
    return next((key for key, sentence in table.items() if sentence == text), "unknown")


def on_screen(line: str) -> bool:
    """A line the screen may show: a whitelist line or the refusal reason line."""
    return on_whitelist(line) or REFUSAL_PATTERN.fullmatch(line) is not None


#: The 16 lines of a successful ``bootstrap --production``, in order (dev-lead's interface note).
CLI_OUTPUT_SHAPES: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern)
    for pattern in (
        r"bootstrap=ok",
        rf"banned_phrase_scan_h3={_SCAN}",
        rf"banned_phrase_scan_h5={_SCAN}",
        r"registered_rows=2",
        r"frozen_commit=[0-9a-f]{40}",
        rf"prereg_doc_sha256={_HEX64}",
        rf"definition_sha256={_HEX64}",
        rf"definition_logic_sha256={_HEX64}",
        rf"rules_sha256_h3={_HEX64}",
        rf"rules_logic_sha256_h3={_HEX64}",
        rf"registered_at_h3={_STAMP}",
        rf"rules_sha256_h5={_HEX64}",
        rf"rules_logic_sha256_h5={_HEX64}",
        rf"registered_at_h5={_STAMP}",
        r"provisional_results_seen=[01]",
        r"post_commit_check=ok",
    )
)


def verified_cli_lines(
    stdout: str, *, head: str, typed: str, pins: Pins, scans: Sequence[str]
) -> list[str] | None:
    """The 16 child output lines when each has its shape and its value is the expected one.

    The values checked against what this run knows: the frozen commit (R-1's ``HEAD``), the
    pre-registration hash, the definition and rule hashes (M-8 constants), the row count and the
    typed answer, and the two ``banned_phrase_scan`` lines, which must equal the ones this run's
    own preflight computed (``scans``). Anything else returns ``None`` (the caller stops: the
    database was written).
    """
    lines = stdout.splitlines()
    if len(lines) != len(CLI_OUTPUT_SHAPES):
        return None
    if not all(shape.fullmatch(line) for shape, line in zip(CLI_OUTPUT_SHAPES, lines, strict=True)):
        return None
    if list(lines[1:3]) != list(scans):
        return None
    h3, h5 = pins.rules
    expected = {
        "frozen_commit": head,
        "prereg_doc_sha256": pins.frozen("prereg").sha256,
        "definition_sha256": pins.definition_sha256,
        "definition_logic_sha256": pins.definition_logic_sha256,
        "rules_sha256_h3": h3.rules_sha256,
        "rules_logic_sha256_h3": h3.rules_logic_sha256,
        "rules_sha256_h5": h5.rules_sha256,
        "rules_logic_sha256_h5": h5.rules_logic_sha256,
        "provisional_results_seen": typed,
    }
    seen = dict(line.split("=", 1) for line in lines if line.split("=", 1)[0] in expected)
    return lines if seen == expected else None


# === git and files ===============================================================================

GitRunner = Callable[[Path, Sequence[str]], tuple[int, bytes]]


def run_git(cwd: Path, args: Sequence[str]) -> tuple[int, bytes]:
    """``git -C cwd args``: (return code, stdout bytes); 127 when git cannot run. Never prints.

    Every ``GIT_*`` variable is removed from git's environment and replace refs are ignored.
    """
    clean_env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    try:
        done = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "-C",
                str(cwd),
                *args,
            ],
            capture_output=True,
            timeout=120,
            check=False,
            env=clean_env,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, b""
    return done.returncode, done.stdout


def sha256_file(path: Path) -> str:
    """The sha256 of a file's bytes; the file is opened ``"rb"`` only. Never used on the main DB."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def core_autocrlf(cwd: Path, *, git: GitRunner = run_git) -> str:
    """``core.autocrlf`` as a closed word, for the paste-back only (never a judgement)."""
    code, out = git(cwd, ["config", "--get", "core.autocrlf"])
    value = out.decode("ascii", "ignore").strip().lower() if code == 0 else ""
    if not value:
        return "unset"
    return value if value in ("true", "false", "input") else "other"


def inside_git_work_tree(path: Path) -> bool:
    resolved = path.resolve()
    return any((folder / ".git").exists() for folder in (resolved, *resolved.parents))


def env_file_sets_db_path(env_file: Path) -> bool:
    """True when a line of the file starts with the key. Only the key is looked for."""
    if not env_file.is_file():
        return False
    with open(env_file, encoding="utf-8-sig", errors="ignore") as handle:
        return any(ENV_KEY_PATTERN.match(line) for line in handle)


def port_is_listening(port: int = PORT) -> bool:
    """One connect to 127.0.0.1 (the only socket use; imported here, not at module level)."""
    import socket

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


# === R-1, R-2: the checkout and the frozen files =================================================

_EOL_ROW = re.compile(rb"i/(\S+)\s+w/(\S+)\s+attr/(.*?)\s*\t(.*)", re.DOTALL)


@dataclass(frozen=True)
class CheckoutFacts:
    """What R-1 found: the repository top, ``HEAD`` and ``core.autocrlf`` (paste-back lines)."""

    top: Path
    head: str
    autocrlf: str


def check_r1(backend_dir: Path, pins: Pins, *, git: GitRunner) -> CheckoutFacts:
    """R-1: ``HEAD`` on ``origin/product/stock-desk``; ``app/`` and both documents clean and the
    ``app/`` tree the one of the CG-2 PR (the equivalent of "no diff since the merge commit").

    ``frozen_commit`` is the returned ``head``.
    """
    code, out = git(backend_dir, ["rev-parse", "--show-toplevel"])
    if code != 0 or not out.strip():
        raise RunStop("git_unusable")
    top = Path(out.decode("utf-8", "replace").strip())
    code, out = git(top, ["rev-parse", "HEAD"])
    head = out.decode("ascii", "ignore").strip()
    if code != 0 or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise RunStop("git_unusable")
    code, _ = git(top, ["merge-base", "--is-ancestor", "HEAD", PUBLISHED_REF])
    if code != 0:
        raise RunStop("head_unpublished")
    watched = [
        APP_REL,
        pins.frozen("prereg").path,
        pins.frozen("c8").path,
        SCRIPT_REL,
        *BAT_RELS,
    ]
    # A path marked assume-unchanged (``h``) or skip-worktree (``S``) hides its changes from
    # ``status``: every listed entry must carry the plain ``H`` (cached) tag.
    code, tags = git(top, ["ls-files", "-v", "-z", "--", *watched])
    entries = [entry for entry in tags.split(b"\0") if entry]
    if code != 0:
        raise RunStop("git_unusable")
    if not entries or any(not entry.startswith(b"H ") for entry in entries):
        raise RunStop("git_dirty")
    code, dirty = git(top, ["status", "--porcelain", "-z", "--untracked-files=all", "--", *watched])
    if code != 0:
        raise RunStop("git_unusable")
    if dirty.strip(b"\0 \n"):
        raise RunStop("git_dirty")
    code, tree = git(top, ["rev-parse", f"HEAD:{APP_REL}"])
    if code != 0 or tree.decode("ascii", "ignore").strip() != pins.app_tree_id:
        raise RunStop("app_changed")
    return CheckoutFacts(top=top, head=head, autocrlf=core_autocrlf(top, git=git))


def check_review_refs(top: Path, pins: Pins, *, git: GitRunner) -> None:
    """Every ``--review-refs`` path must exist in ``HEAD`` (``git cat-file -e``), else a stop.

    The paths go into the ledger for good; an absent record would be a dead reference.
    """
    for ref in pins.review_refs:
        code, _out = git(top, ["cat-file", "-e", f"HEAD:{ref}"])
        if code != 0:
            raise RunStop("review_refs_missing")


def check_r2(top: Path, pins: Pins, *, git: GitRunner) -> None:
    """R-2 (addendum 2 point 9): for each frozen file three pieces of evidence, or a stop.

    One: the sha256 of the raw work-tree bytes equals the sha256 of ``git cat-file blob
    HEAD:<path>`` and the fixed constant. Two: ``git ls-files --eol`` is ``i/lf w/lf
    attr/text eol=lf``. Three: ``git check-attr eol`` is ``lf``. Nothing is changed.
    """
    for item in pins.frozen_files:
        code, blob = git(top, ["cat-file", "blob", f"HEAD:{item.path}"])
        if code != 0:
            raise RunStop("frozen_bytes")
        try:
            worktree = (top / item.path).read_bytes()
        except OSError:
            raise RunStop("frozen_bytes") from None
        digests = {hashlib.sha256(worktree).hexdigest(), hashlib.sha256(blob).hexdigest()}
        if digests != {item.sha256}:
            raise RunStop("frozen_bytes")
    for item in pins.frozen_files:
        code, listing = git(top, ["ls-files", "-z", "--eol", "--", item.path])
        rows = [row for row in listing.split(b"\0") if row]
        found = _EOL_ROW.fullmatch(rows[0]) if len(rows) == 1 else None
        if code != 0 or found is None:
            raise RunStop("frozen_eol")
        index, work, attr = found.group(1), found.group(2), found.group(3).strip()
        if (index, work, attr) != (b"lf", b"lf", b"text eol=lf"):
            raise RunStop("frozen_eol")
        code, attrs = git(top, ["check-attr", "-z", "eol", "--", item.path])
        parts = attrs.split(b"\0")
        if code != 0 or len(parts) < 3 or (parts[1], parts[2]) != (b"eol", b"lf"):
            raise RunStop("frozen_eol")


# === M-8 hashes and R-6 ==========================================================================


def check_hashes_and_phrases(pins: Pins) -> list[str]:
    """M-8: the loaded definition and rule sets hash to the constants; R-6: zero banned phrases.

    Returns the two scan lines (the same text the registration CLI prints). The values come from
    the loaded ``app``; at run time that is this checkout's (:func:`loaded_app_is_backend`).
    """
    try:
        definition = definitions.get_definition(pins.definition_version)
        if (
            definition_sha256(definition) != pins.definition_sha256
            or definition_logic_sha256(definition) != pins.definition_logic_sha256
        ):
            raise RunStop("hashes_differ")
        scans: list[str] = []
        for pin in pins.rules:
            ruleset = definitions.get_ruleset(pin.version)
            entry = definitions.get_ruleset_entry(pin.version)
            sha = hashlib.sha256(definitions.get_rules_bytes(pin.version)).hexdigest()
            if (
                entry.horizon != pin.horizon
                or sha != pin.rules_sha256
                or rules_logic_sha256(ruleset) != pin.rules_logic_sha256
            ):
                raise RunStop("hashes_differ")
            scan = definitions.registration_phrase_scan(ruleset, definition)
            if scan.hits:
                raise RunStop("banned_phrase")
            scans.append(
                f"banned_phrase_scan_h{pin.horizon}=hits {len(scan.hits)}"
                f" rules_strings {scan.rules_strings} definition_strings"
                f" {scan.definition_strings} phrases {scan.phrases}"
            )
    except (definitions.UnpublishedVersionError, definitions.PublishedVersionRejectedError):
        raise RunStop("hashes_differ") from None
    return scans


def loaded_app_is_backend(backend_dir: Path) -> bool:
    """True when the ``app`` this process loaded is ``<backend>/app`` (the M-8 values are its)."""
    return canonical.APP_ROOT == (backend_dir / "app").resolve()


# === R-3, R-4: the main database =================================================================


def main_db_uri(db: Path) -> str:
    """The read-only URI of the main database: ``mode=ro``, plus ``immutable=1`` without side files.

    A ``mode=ro`` connection to a WAL database creates a ``-wal`` and a ``-shm`` beside it when
    they are absent. With neither a ``-wal`` nor a ``-journal`` the database file alone holds every
    committed row, so ``immutable=1`` reads it with no side file and no lock. With either present
    it must be read through SQLite (they may hold rows not yet in the file), so ``immutable`` is
    not used. The same rule as ``copy_uri`` of the acceptance script.
    """
    path = Path(db).resolve()
    query = "mode=ro"
    if not any(path.with_name(f"{path.name}{suffix}").exists() for suffix in ("-wal", "-journal")):
        query += "&immutable=1"
    return f"{path.as_uri()}?{query}"


_LEDGER_SQL: Final = "SELECT type, name FROM sqlite_master WHERE " + " OR ".join(
    f"substr(lower({column}), 1, {len(prefix)}) = '{prefix}'"
    for prefix in LEDGER_PREFIXES
    for column in ("name", "tbl_name")
)


def ledger_objects_present(conn: sqlite3.Connection) -> bool:
    """True when any object's name or table, case-insensitively, starts with a ledger prefix.

    The rule of ``app.forecast.schema._ledger_objects`` (supplement 7 point 3): the implicit
    ``sqlite_autoindex_`` indexes are part of their table and do not count by themselves.
    """
    return any(
        not (str(kind) == "index" and str(name).startswith("sqlite_autoindex_"))
        for kind, name in conn.execute(_LEDGER_SQL).fetchall()
    )


def check_r4(db: Path) -> None:
    """R-4: a ``mode=ro`` connection; stops when any ledger object is there (nothing is changed)."""
    try:
        with closing(sqlite3.connect(main_db_uri(db), uri=True)) as conn:
            conn.execute("PRAGMA query_only=ON")
            present = ledger_objects_present(conn)
    except sqlite3.Error:
        raise RunStop("db_unreadable") from None
    if present:
        raise RunStop("ledger_objects")


def check_r3(backend_dir: Path, *, env: Mapping[str, str], port_check: Callable[[], bool]) -> Path:
    """R-3: no ``STOCK_DESK_DB_PATH`` (environment, ``.env`` -- key only), the default database
    is there, and nothing listens on port 8000. Returns the default database path."""
    if ENV_VAR in env:
        raise RunStop("env_db_path")
    if env_file_sets_db_path(backend_dir.parent / ".env"):
        raise RunStop("env_file_db_path")
    db = backend_dir / "data" / DB_NAME
    if not db.is_file():
        raise RunStop("no_db")
    if port_check():
        raise RunStop("port_listening")
    return db


# === R-5: the backup =============================================================================


@dataclass(frozen=True)
class Backup:
    """The finished backup: its file (never shown) and the sha256 recorded for CG-3."""

    path: Path
    sha256: str


def backup_file_name(stamp: str) -> str:
    """The first backup's file name (the instruction names it; the verifier checks it)."""
    return f"stock-desk-before-cg2-{stamp}.db"


def verify_file_name(stamp: str) -> str:
    """The second backup's file name (RC-209)."""
    return f"stock-desk-before-cg2-{stamp}-verify.db"


def _backup_once(db: Path, target: Path) -> Backup:
    """R-5: a consistent copy by the SQLite backup API; the source is opened read-only.

    ``target`` is reserved first (``"xb"``: an existing file stops). Then the backup is read back
    through a read-only immutable connection: ``integrity_check`` must be ``ok`` and no ledger
    object may be in it. The sha256 is taken before and after that read and must not change. The
    backup is never deleted, not even when a check fails.
    """
    try:
        with open(target, "xb"):
            pass
        with closing(sqlite3.connect(main_db_uri(db), uri=True)) as source:
            with closing(sqlite3.connect(str(target))) as dest:
                source.backup(dest)
    except (sqlite3.Error, OSError):
        raise RunStop("backup_failed") from None
    if any(target.with_name(f"{target.name}{s}").exists() for s in ("-wal", "-shm", "-journal")):
        raise RunStop("backup_failed")
    before = sha256_file(target)
    try:
        with closing(sqlite3.connect(f"{target.as_uri()}?mode=ro&immutable=1", uri=True)) as conn:
            verdict = conn.execute("PRAGMA integrity_check").fetchall()
            has_ledger = ledger_objects_present(conn)
    except sqlite3.Error:
        raise RunStop("backup_integrity") from None
    if [tuple(row) for row in verdict] != [("ok",)]:
        raise RunStop("backup_integrity")
    if has_ledger:
        raise RunStop("backup_has_ledger")
    if sha256_file(target) != before:
        raise RunStop("backup_failed")
    return Backup(path=target, sha256=before)


def make_backup(db: Path, folder: Path, stamp: str) -> Backup:
    """Two backups taken one after the other by the same rule; their sha256 must be equal.

    A source that no lock protects (``immutable=1`` takes none) could be written by another
    process while it is copied; two equal copies in a row show that it was not (addendum 3
    point 3). A difference is a stop (``backup_mismatch``). Both files stay; the recorded
    sha256 is the one both have.
    """
    first = _backup_once(db, folder / backup_file_name(stamp))
    second = _backup_once(db, folder / verify_file_name(stamp))
    if first.sha256 != second.sha256:
        raise RunStop("backup_mismatch")
    return first


# === the registration child ======================================================================


@dataclass(frozen=True)
class CliResult:
    """The child's exit code and its captured output (never shown)."""

    code: int
    stdout: str
    stderr: str


class ClaimsRunner(Protocol):
    """The two things the flow needs of the registration program (a seam for tests)."""

    def probe(self) -> Path | None:
        """The backend folder the program derives its target from, or ``None``."""

    def start(self, args: Sequence[str]) -> Any:
        """Start ``bootstrap`` with ``args`` (after ``-m app.forecast.claims``); ``OSError`` if it
        cannot be started. Nothing has been registered until this returns."""

    def finish(self, handle: Any) -> CliResult:
        """Wait for the started program; :class:`ClaimsTimeout` when it did not end in time."""


class ClaimsTimeout(Exception):
    """The registration program did not end in time and was killed: the result is unknown."""


PROBE_CODE: Final = "from app.forecast import claims; print(claims.BACKEND_DIR)"
RUN_TIMEOUT_SECONDS: Final = 600


class SubprocessClaims:
    """The real runner: the same interpreter, ``-I -X utf8``, working directory the backend.

    ``-I`` puts neither the working directory nor ``PYTHONPATH`` on ``sys.path``, so ``app`` must
    be the one the environment's editable install of this backend provides. :meth:`probe` asks the
    child which backend folder it would act on, and the flow stops unless it is this one.
    """

    def __init__(self, backend_dir: Path) -> None:
        self.backend_dir = backend_dir

    def _argv(self, *tail: str) -> list[str]:
        return [sys.executable, "-I", "-X", "utf8", *tail]

    def probe(self) -> Path | None:
        try:
            done = subprocess.run(
                self._argv("-c", PROBE_CODE),
                cwd=self.backend_dir,
                capture_output=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        text = done.stdout.decode("utf-8", "replace").strip()
        return Path(text) if done.returncode == 0 and text else None

    def start(self, args: Sequence[str]) -> Any:
        return subprocess.Popen(
            self._argv("-m", "app.forecast.claims", *args),
            cwd=self.backend_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def finish(self, handle: Any) -> CliResult:
        try:
            out, err = handle.communicate(timeout=RUN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            handle.kill()
            handle.communicate()
            raise ClaimsTimeout from None
        except BaseException:
            handle.kill()
            raise
        return CliResult(
            handle.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
        )


def bootstrap_args(*, head: str, typed: str, pins: Pins) -> list[str]:
    """The arguments of ``bootstrap --production`` (dev-lead's interface note).

    ``--frozen-commit`` is R-1's ``HEAD`` of this run; the typed answer goes in unchanged; no
    ``--replaces-claim-id`` and no database path (the program's target is fixed).
    """
    prereg = pins.frozen("prereg")
    return [
        "bootstrap",
        "--production",
        "--rules-version",
        pins.rules[0].version,
        "--rules-version",
        pins.rules[1].version,
        "--definition-version",
        pins.definition_version,
        "--frozen-commit",
        head,
        "--prereg-doc-path",
        prereg.path,
        "--prereg-doc-sha256",
        prereg.sha256,
        "--review-refs",
        " ".join(pins.review_refs),
        "--provisional-results-seen",
        typed,
    ]


# === the flow ====================================================================================

Mode = Literal["preflight", "register"]


@dataclass
class State:
    """What the end of an abnormal run needs to know."""

    #: True from just before the registration program is started: from then on it may be written.
    late: bool = False
    backup_sha256: str | None = None
    #: The lines known so far (for the paste-back of a written-but-unchecked registration).
    lines: list[str] = field(default_factory=list)
    paste_dir: Path | None = None
    stamp: str = ""


@dataclass
class Seams:
    """Everything a test replaces; the batch files pass none of it."""

    env: Mapping[str, str]
    port_check: Callable[[], bool]
    git: GitRunner
    ask: Callable[[str], str]
    opener: Callable[[Path], object] | None
    now: Callable[[], datetime]
    utc_now: Callable[[], datetime]
    claims: ClaimsRunner
    pins: Pins
    app_check: Callable[[Path], bool]


def _utc_stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def prechecks(backend_dir: Path, seams: Seams) -> tuple[CheckoutFacts, Path, list[str], list[str]]:
    """R-3, R-1, R-2, M-8 with R-6, then R-4. Returns the facts, the database, the lines, the scans.

    Read-only: the only contact with the main database is R-4's ``mode=ro`` connection.
    """
    pins = seams.pins
    db = check_r3(backend_dir, env=seams.env, port_check=seams.port_check)
    facts = check_r1(backend_dir, pins, git=seams.git)
    check_r2(facts.top, pins, git=seams.git)
    check_review_refs(facts.top, pins, git=seams.git)
    if not seams.app_check(backend_dir):
        raise RunStop("app_changed")
    try:
        digest = canonical.code_digest(backend_dir / "app")
    except OSError:
        raise RunStop("app_changed") from None
    scans = check_hashes_and_phrases(pins)
    check_r4(db)
    script_lf = canonical.normalised_source(Path(__file__).read_bytes())
    h3, h5 = pins.rules
    lines = [
        f"script_sha256_lf={hashlib.sha256(script_lf).hexdigest()}",
        f"git_head={facts.head}",
        "git_clean=yes",
        f"core_autocrlf={facts.autocrlf}",
        "head_published=yes",
        "app_unchanged=yes",
        f"code_digest={digest}",
        *(f"frozen_{item.role}_sha256={item.sha256}" for item in pins.frozen_files),
        "eol_check=ok",
        "attr_check=ok",
        f"definition_sha256={pins.definition_sha256}",
        f"definition_logic_sha256={pins.definition_logic_sha256}",
        f"rules_sha256_h3={h3.rules_sha256}",
        f"rules_logic_sha256_h3={h3.rules_logic_sha256}",
        f"rules_sha256_h5={h5.rules_sha256}",
        f"rules_logic_sha256_h5={h5.rules_logic_sha256}",
        "hashes_pinned=ok",
        "env_db_path=unset",
        "db_location=default",
        "port_8000_listening=no",
        "ledger_objects=none",
    ]
    return facts, db, lines, scans


def check_preflight_binding(paste_dir: Path, *, head: str, script_sha256: str) -> None:
    """The register run needs a passed preflight of this very code version (addendum 3 point 2).

    The newest ``preflight-*.txt`` (the time stamp in the name orders them) is read as text. A stop
    when it cannot be read, when any line is off the whitelist, when ``preflight_result=PASS`` is
    missing, or when its ``git_head`` or ``script_sha256_lf`` is not this run's.
    """
    try:
        newest = max(paste_dir.glob("preflight-*.txt"), key=lambda path: path.name)
        text = newest.read_bytes().decode("utf-8-sig")
    except (ValueError, OSError, UnicodeDecodeError):
        raise RunStop("preflight_mismatch") from None
    lines = text.splitlines()
    wanted = {"preflight_result=PASS", f"git_head={head}", f"script_sha256_lf={script_sha256}"}
    if not lines or not all(on_whitelist(line) for line in lines) or not wanted <= set(lines):
        raise RunStop("preflight_mismatch")


def write_paste_back(
    state: State, lines: list[str], *, name: str, opener: Callable[[Path], object] | None
) -> None:
    """Write ``lines`` (all on the whitelist) as ``utf-8-sig``, show them, open the file."""
    if not all(on_whitelist(line) for line in lines) or state.paste_dir is None:
        raise RuntimeError("a paste-back line is not on the whitelist")  # a bug; fixed sentence
    target = state.paste_dir / name
    with open(target, "x", encoding="utf-8-sig") as handle:
        handle.write("\n".join(lines) + "\n")
    for line in lines:
        say(line)
    if opener is None and sys.platform == "win32":
        opener = getattr(os, "startfile", None)
    if opener is not None:
        try:
            opener(target)
        except OSError:
            pass  # the file is in the paste-back folder; the instruction says where


def flow(state: State, mode: Mode, *, backend_dir: Path, home: Path, seams: Seams) -> int:
    """The whole run; returns the exit code. ``state`` carries what an abnormal end needs."""
    root = home / WORK_ROOT_NAME
    stamp = seams.now().strftime("%Y%m%d-%H%M%S")
    state.stamp = stamp
    seams.ask(PROMPT_CLOSE)
    if inside_git_work_tree(root):
        raise RunStop("work_in_git")
    pins = seams.pins
    facts, db, lines, scans = prechecks(backend_dir, seams)
    header = [VERSION_LINE, f"mode={mode}"]
    paste_dir = root / PASTE_DIR_NAME
    state.paste_dir = paste_dir
    if mode == "register":
        script_line = next(line for line in lines if line.startswith("script_sha256_lf="))
        check_preflight_binding(
            paste_dir, head=facts.head, script_sha256=script_line.partition("=")[2]
        )
    probed = seams.claims.probe()  # both modes: the preflight covers it too
    if probed is None or probed.resolve() != backend_dir.resolve():
        raise RunStop("claims_unreachable")
    if mode == "preflight":
        done = [*header, *lines, *scans, "preflight_result=PASS"]
        done.append(f"done_at_utc={_utc_stamp(seams.utc_now())}")
        paste_dir.mkdir(parents=True, exist_ok=True)
        write_paste_back(state, done, name=f"preflight-{stamp}.txt", opener=seams.opener)
        return 0

    # --- register ---
    backups = root / BACKUP_DIR_NAME
    backups.mkdir(parents=True, exist_ok=True)
    paste_dir.mkdir(parents=True, exist_ok=True)
    backup = make_backup(db, backups, stamp)  # R-5 (two equal copies), RC-181
    state.backup_sha256 = backup.sha256
    backup_lines = [
        "backup_integrity=ok",
        "backup_ledger_objects=none",
        f"backup_sha256={backup.sha256}",
    ]
    state.lines = [*header, *lines, *backup_lines]
    try:
        typed = seams.ask(PROMPT_SEEN)  # R-8: typed, no default, no loop, passed on unchanged
    except EOFError:
        typed = ""
    if typed not in ("0", "1"):
        raise RunStop("bad_answer")
    if seams.port_check():  # the typing took time: nothing may have started in the meantime
        raise RunStop("port_listening")
    args = bootstrap_args(head=facts.head, typed=typed, pins=pins)
    try:
        handle = seams.claims.start(args)
    except OSError:
        raise RunStop("claims_not_started") from None
    state.late = True  # from here the database may be written
    try:
        result = seams.claims.finish(handle)
    except ClaimsTimeout:
        raise RunStop("written_unknown") from None
    if result.code == 3:
        state.late = False
        raise RunStop("refused_3", reason=refusal_reason(3, result.stderr))
    if result.code == 4:
        state.late = False
        raise RunStop("refused_4", reason=refusal_reason(4, result.stderr))
    if result.code == 5:
        raise RunStop("written_5")
    if result.code != 0:
        raise RunStop("written_unknown")
    cli_lines = verified_cli_lines(
        result.stdout, head=facts.head, typed=typed, pins=pins, scans=scans
    )
    if cli_lines is None:
        raise RunStop("output_unverified")
    done = [*state.lines, *cli_lines, "register_result=DONE"]
    done.append(f"done_at_utc={_utc_stamp(seams.utc_now())}")
    write_paste_back(state, done, name=f"register-{stamp}.txt", opener=seams.opener)
    return 0


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    """An argparse parser that never prints (RC-162): errors and ``--help`` are one stop."""

    def error(self, message: str) -> NoReturn:
        raise _UsageError


def _abnormal_tail(state: State) -> None:
    """After any end other than success: the backup sha256 (a whitelisted line), if one exists."""
    if state.backup_sha256 is not None:
        say(f"backup_sha256={state.backup_sha256}")


def main(argv: Sequence[str] | None = None, **injected: Any) -> int:
    """Run one mode; the screen shows whitelisted lines or one fixed sentence (RC-162).

    Exit codes: 0 done; 1 unexpected failure and 2 interrupted, both before the registration
    program started (nothing written); 3 stopped, nothing written; 5 the registration started
    and its result cannot be confirmed (interrupted, failed or timed out after the start too):
    it must not be run again. ``injected`` are the
    test seams (``env``, ``port_check``, ``git``, ``ask``, ``opener``, ``now``, ``utc_now``,
    ``claims``, ``pins``, ``app_check``); the batch files pass none of them.
    """
    state = State()
    code = 1
    try:
        parser = _Parser(prog="cg2_register.py", add_help=False)
        parser.add_argument("mode", choices=("preflight", "register"))
        # TEST ONLY: the batch files never pass these two (the tests that read the launchers
        # assert the exact command, which has no argument beyond the mode).
        parser.add_argument("--backend-dir", default=None)
        parser.add_argument("--home", default=None)
        try:
            args = parser.parse_args(argv)
        except _UsageError:
            raise RunStop("usage") from None
        backend = Path(args.backend_dir) if args.backend_dir else _BACKEND_DIR
        home = Path(args.home) if args.home else Path.home()
        seams = Seams(
            env=injected.get("env", os.environ),
            port_check=injected.get("port_check", port_is_listening),
            git=injected.get("git", run_git),
            ask=injected.get("ask", input),
            opener=injected.get("opener"),
            now=injected.get("now", datetime.now),
            utc_now=injected.get("utc_now", lambda: datetime.now(UTC)),
            claims=injected.get("claims") or SubprocessClaims(backend),
            pins=injected.get("pins", REAL_PINS),
            app_check=injected.get("app_check", loaded_app_is_backend),
        )
        code = flow(state, args.mode, backend_dir=backend, home=home, seams=seams)
    except RunStop as stop:
        say(str(stop))
        if stop.reason is not None:
            say(f"refusal_reason={stop.reason}")
        code = stop.exit_code
        if stop.exit_code == 5 and state.late:
            _write_unchecked_paste_back(state, injected)
        _abnormal_tail(state)
    except KeyboardInterrupt:
        say(INTERRUPTED_LATE if state.late else INTERRUPTED_SAFE)
        code = 5 if state.late else 2
        if state.late:
            _write_unchecked_paste_back(state, injected)
        _abnormal_tail(state)
    except BaseException:  # noqa: BLE001 - a fixed sentence only, never the exception or a path
        say(UNEXPECTED_LATE if state.late else UNEXPECTED_SAFE)
        code = 5 if state.late else 1
        if state.late:
            _write_unchecked_paste_back(state, injected)
        _abnormal_tail(state)
    return code


def _write_unchecked_paste_back(state: State, injected: Mapping[str, Any]) -> None:
    """A registration that was written but not confirmed: the lines known so far, marked as such.

    Best effort and silent: the screen already holds the stop sentence.
    """
    try:
        utc_now = injected.get("utc_now", lambda: datetime.now(UTC))
        lines = [*state.lines, "register_result=UNCONFIRMED"]
        lines.append(f"done_at_utc={_utc_stamp(utc_now())}")
        if state.paste_dir is None or not all(on_whitelist(line) for line in lines):
            return
        with open(state.paste_dir / f"register-{state.stamp}.txt", "x", encoding="utf-8-sig") as fh:
            fh.write("\n".join(lines) + "\n")
    except BaseException:  # noqa: BLE001 - best effort
        pass


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI tests
    raise SystemExit(main())
