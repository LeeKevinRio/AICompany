"""Pin the wording of the prerequisite and failure lines of ``dev-up.bat``.

The sentences are the risk-control approved texts (RC-336, RC-337 (a)); they are pinned here
verbatim as literals so that this test never depends on any file outside the app folder.
The batch file is only read as bytes; it is never executed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
BAT = BACKEND.parent / "dev-up.bat"

MISSING_GIT = "[MISSING] git was not found. Do not install or update anything yourself."
MISSING_UV = "[MISSING] uv was not found. Do not install or update anything yourself."
MISSING_NPM = "[MISSING] npm was not found. Do not install or update anything yourself."
CLOSING = "Tell the coordinator."
NOT_REPO_ERROR = "[ERROR] Not a git repo: !REPO_ROOT!"
FOLDER_SENTENCE = "Do not move or change any file or folder yourself; tell the coordinator."

# The failure lines that RC-337 (a) follows with one more action sentence.
RUNTIME_ERRORS = (
    "[ERROR] Branch switch failed",
    "[ERROR] Backend uv sync failed",
    "[ERROR] Frontend npm install failed",
)

# Lines outside the RC-336 scope: they must stay exactly as they were.
UNCHANGED_LINES = (
    "echo [ERROR] Cannot copy dev-up.bat to the temp folder - please send a screenshot to Claude",
    "echo [STOP] You have local changes to tracked files. Please tell Claude before continuing.",
    "echo [ERROR] git pull failed - please send a screenshot of the messages above to Claude",
    "echo [TIMEOUT] Backend did not become healthy in time. Check the error in the "
    "'stock-desk backend' window and send a screenshot to Claude.",
    "echo [TIMEOUT] Frontend did not start in time. Check the error in the "
    "'stock-desk frontend' window and send a screenshot to Claude.",
)

RESTRICTED = "()&|<>^%!"


def _lines() -> list[str]:
    return BAT.read_bytes().decode("ascii").split("\r\n")


def _echo_texts(lines: list[str]) -> list[str]:
    return [x.strip()[len("echo ") :] for x in lines if x.strip().startswith("echo ")]


def test_the_bat_is_ascii_with_crlf_only() -> None:
    raw = BAT.read_bytes()
    raw.decode("ascii")
    assert raw.count(b"\r\n") == raw.count(b"\n") == raw.count(b"\r")
    assert raw.endswith(b"\r\n")


@pytest.mark.parametrize(
    ("tool", "sentence"),
    [("git", MISSING_GIT), ("uv", MISSING_UV), ("npm", MISSING_NPM)],
)
def test_each_missing_tool_line_is_the_approved_sentence(tool: str, sentence: str) -> None:
    lines = _lines()
    at = lines.index(f"where {tool} >nul 2>nul")
    assert lines[at + 1] == "if errorlevel 1 ("
    assert lines[at + 2] == f"  echo {sentence}"
    assert lines[at + 3] == '  set "MISSING=1"'
    assert lines[at + 4] == ")"
    assert lines.count(f"  echo {sentence}") == 1


def test_the_missing_block_closes_with_the_coordinator_sentence() -> None:
    lines = _lines()
    at = lines.index("if defined MISSING (")
    assert lines[at + 1] == f"  echo {CLOSING}"
    assert lines[at + 2] == "  goto fail"
    assert lines[at + 3] == ")"


def test_the_missing_lines_have_no_url_and_no_install_hint() -> None:
    lines = _lines()
    missing = [x for x in lines if "[MISSING]" in x]
    assert len(missing) == 3
    assert not any("http" in x or "install from" in x for x in missing)
    text = "\n".join(lines)
    assert "After installing, run this script again." not in text
    assert "run this script again" not in text
    assert "http://localhost" in text  # the health probe and the status lines are untouched


def test_the_not_a_git_repo_error_is_followed_by_the_folder_sentence() -> None:
    lines = _lines()
    at = lines.index(f"  echo {NOT_REPO_ERROR}")
    assert lines[at + 1] == f"  echo {FOLDER_SENTENCE}"
    assert lines[at + 2] == "  goto fail"
    assert lines.count(f"  echo {FOLDER_SENTENCE}") == 1


@pytest.mark.parametrize("error", RUNTIME_ERRORS)
def test_each_runtime_failure_line_is_followed_by_the_coordinator_sentence(error: str) -> None:
    lines = _lines()
    candidates = [i for i, x in enumerate(lines) if x.strip() == f"echo {error}"]
    assert len(candidates) == 1
    at = candidates[0]
    indent = lines[at][: len(lines[at]) - len(lines[at].lstrip())]
    assert lines[at + 1] == f"{indent}echo {CLOSING}"
    assert lines[at + 2] == f"{indent}goto fail"


def test_the_coordinator_sentence_appears_exactly_the_expected_number_of_times() -> None:
    lines = _lines()
    # One closing line of the missing block, plus the three runtime failure lines.
    assert sum(1 for x in lines if x.strip() == f"echo {CLOSING}") == 1 + len(RUNTIME_ERRORS)


def test_the_fail_section_prints_no_sentence_of_its_own() -> None:
    lines = _lines()
    at = lines.index(":fail")
    assert lines[at : at + 4] == [":fail", "echo.", "pause", "exit /b 1"]


def test_the_new_echo_texts_hold_no_cmd_special_character() -> None:
    new_texts = {
        MISSING_GIT,
        MISSING_UV,
        MISSING_NPM,
        CLOSING,
        FOLDER_SENTENCE,
    }
    for text in new_texts:
        assert text.isascii()
        assert not any(c in text for c in RESTRICTED), text
    # Every echo that the file prints for these sentences, read back from the file itself.
    in_file = [
        t for t in _echo_texts(_lines()) if t in new_texts or t.startswith("Do not move or change")
    ]
    # three [MISSING] lines, four closing lines, one folder sentence
    assert len(in_file) == 3 + (1 + len(RUNTIME_ERRORS)) + 1
    assert not any(c in t for t in in_file for c in RESTRICTED)


@pytest.mark.parametrize("line", UNCHANGED_LINES)
def test_lines_outside_the_scope_are_verbatim_unchanged(line: str) -> None:
    lines = _lines()
    stripped = [x.strip() for x in lines]
    assert line.strip() in stripped
    assert stripped.count(line.strip()) == 1


def test_the_self_update_guard_is_untouched() -> None:
    lines = _lines()
    assert lines[:3] == ["@echo off", "setlocal enabledelayedexpansion", "title stock-desk dev-up"]
    assert "if not defined DEVUP_SRC_DIR (" in lines
    assert '  copy /y "%~f0" "%TEMP%\\stock-desk-dev-up.bat" >nul' in lines
