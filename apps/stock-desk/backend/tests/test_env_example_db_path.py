"""CI-only guard: ``apps/stock-desk/.env.example`` must not activate ``STOCK_DESK_DB_PATH``.

Background: setting ``STOCK_DESK_DB_PATH`` on a host that records forecasts makes the
forecast recorder skip every run, so the template must never ship it as an active line.

The file-reading test is deliberately narrow (CEO decision 2026-11-21, scope: one test,
CI only, one fixed path ``<backend>/../.env.example``, reports only presence / comment
status of ``STOCK_DESK_DB_PATH`` and never any file content). Outside CI it is skipped
before any file is opened. The pure-function tests below only feed fake strings.
"""

from __future__ import annotations

import os
import re
import warnings
from collections.abc import Iterable
from pathlib import Path

import pytest

_NAME = "STOCK_DESK_DB_PATH"
_ACTIVE_RE = re.compile(r"^\s*(?:export\s+)?" + _NAME + r"\s*=")
# <backend>/tests/<this file> -> <backend> -> its parent holds .env.example
_ENV_EXAMPLE = Path(__file__).resolve().parents[1].parent / ".env.example"


def scan_env_lines(lines: Iterable[str]) -> tuple[bool, bool]:
    """Return ``(has_active_line, has_comment_line)`` for the variable name."""
    has_active = False
    has_comment = False
    for line in lines:
        if _ACTIVE_RE.match(line):
            has_active = True
        elif line.lstrip().startswith("#") and _NAME in line:
            has_comment = True
    return has_active, has_comment


def _inspect_env_example(path: Path) -> tuple[bool, bool] | None:
    """Read ``path`` and keep only booleans; ``None`` if missing or unreadable."""
    if not path.is_file():
        return None
    try:
        return scan_env_lines(path.read_text(encoding="utf-8-sig").splitlines())
    except (OSError, UnicodeDecodeError):
        return None


def test_env_example_has_no_active_db_path_ci_only() -> None:
    """Fail in CI if ``.env.example`` has an active ``STOCK_DESK_DB_PATH`` line.

    CEO decision 2026-11-21, scope: runs only when GITHUB_ACTIONS == "true", reads only
    the fixed path ``<backend>/../.env.example``, and reports only fixed strings
    (no line content, no line numbers). Skipped before opening any file otherwise.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        pytest.skip("CI-only check (GITHUB_ACTIONS is not 'true')")
    result = _inspect_env_example(_ENV_EXAMPLE)
    if result is None:
        pytest.fail(".env.example is missing or unreadable")
    has_active, has_comment = result
    if has_active:
        pytest.fail(".env.example has an active STOCK_DESK_DB_PATH line")
    if has_comment:
        warnings.warn("env.example: STOCK_DESK_DB_PATH appears only in comments", stacklevel=1)
    else:
        warnings.warn("env.example: STOCK_DESK_DB_PATH not present", stacklevel=1)


def test_scan_absent() -> None:
    assert scan_env_lines(["FOO=1", "", "BAR="]) == (False, False)


def test_scan_comment_only() -> None:
    assert scan_env_lines(["# STOCK_DESK_DB_PATH=x", "  #STOCK_DESK_DB_PATH"]) == (False, True)


def test_scan_active_line() -> None:
    assert scan_env_lines(["  STOCK_DESK_DB_PATH =", "# STOCK_DESK_DB_PATH"]) == (True, True)


def test_scan_export_form() -> None:
    assert scan_env_lines(["export STOCK_DESK_DB_PATH=./x"]) == (True, False)


def test_scan_similar_name_is_not_active() -> None:
    assert scan_env_lines(["STOCK_DESK_DB_PATH_OTHER=1"]) == (False, False)


def test_inspect_missing_file_returns_none(tmp_path: Path) -> None:
    assert _inspect_env_example(tmp_path / "absent") is None
