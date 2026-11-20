"""The ``forecast_record:`` log lines (risk-compliance RC-331, RC-333 (a)).

* RC-331: ``recorder.DISK_DIFFERS_WARNING`` is, at run time, the text approved in
  the RC-331～RC-335 record (extracted from the record, never typed here), and
  the superseded wording with its imperative clause is gone from ``app/``;
* RC-333 (a): no string literal of ``app/`` starting with ``forecast_record:``
  is imperative (see the scan below and why it cannot pass vacuously).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app import scheduler as scheduler_module
from app.forecast import recorder as recorder_module
from tests import approved_copy

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_rc331_the_disk_differs_warning_is_the_approved_text() -> None:
    approved = approved_copy.disk_differs_line()
    assert recorder_module.DISK_DIFFERS_WARNING == approved
    assert approved.startswith("forecast_record: ") and approved.isascii()
    assert "\n" not in approved


def test_rc331_the_superseded_clause_is_gone_from_app() -> None:
    offenders = sorted(
        path.relative_to(APP_ROOT).as_posix()
        for path in APP_ROOT.rglob("*.py")
        if "restart the scheduler process to load them" in path.read_text(encoding="utf-8")
    )
    assert offenders == []


# --- RC-333 (a): no ``forecast_record:`` line tells the operator to do anything ------------------
#
# The scan reads every string literal of ``app/`` that starts with
# ``forecast_record:`` (implicitly concatenated literals arrive as one constant;
# the literal parts of an f-string are joined). A line is imperative when it
# contains "please", or when a clause -- the text after the prefix, or after any
# ``;``, ``.``, ``:``, ``,`` or ``(`` -- opens with a verb of an instruction. The
# clause-opening rule is what lets the noun "run" of "the run is skipped" pass
# while "run the bootstrap" is caught.
#
# Why it cannot pass vacuously: (1) the scan must find at least the ten lines
# defined today, each matched against the runtime value of its constant, so an
# empty or broken scan fails; (2) the teeth test feeds the superseded RC-331
# wording and other imperative lines through the same function and requires each
# to be flagged, and feeds the noun use of "run" and requires it not to be.

PREFIX = "forecast_record:"
IMPERATIVE_VERBS = (
    "restart",
    "rerun",
    "re-run",
    "run",
    "retry",
    "install",
    "reinstall",
    "uninstall",
    "delete",
    "remove",
    "close",
    "open",
    "start",
    "stop",
    "kill",
    "reboot",
    "tell",
    "contact",
    "ask",
    "check",
    "fix",
    "set",
    "unset",
    "update",
    "upgrade",
    "try",
    "wait",
    "do",
    "don't",
    "make",
    "use",
    "load",
    "reload",
)
_CLAUSE_VERB = re.compile(
    r"(?:^"
    + re.escape(PREFIX)
    + r"|[;.:,(])\s*(?:then\s+)?("
    + "|".join(re.escape(verb) for verb in IMPERATIVE_VERBS)
    + r")\b",
    flags=re.IGNORECASE,
)
_PLEASE = re.compile(r"\bplease\b", flags=re.IGNORECASE)


def imperative_findings(line: str) -> list[str]:
    """The imperative words of one ``forecast_record:`` line (empty when it states facts only)."""
    found = [match.group(1).lower() for match in _CLAUSE_VERB.finditer(line)]
    found += ["please"] * len(_PLEASE.findall(line))
    return found


def forecast_record_literals(sources: dict[str, str]) -> dict[str, str]:
    """Every string literal starting with ``forecast_record:`` -> the file that holds it."""
    found: dict[str, str] = {}
    for path, source in sources.items():
        tree = ast.parse(source)
        # The literal parts of an f-string are read with the f-string, not alone.
        parts = {
            id(part)
            for node in ast.walk(tree)
            if isinstance(node, ast.JoinedStr)
            for part in node.values
        }
        for node in ast.walk(tree):
            text: str | None = None
            if id(node) in parts:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
            elif isinstance(node, ast.JoinedStr):
                text = "".join(
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                )
            if text is not None and text.startswith(PREFIX):
                found[text] = path
    return found


def _app_sources() -> dict[str, str]:
    return {
        path.relative_to(APP_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(APP_ROOT.rglob("*.py"))
    }


#: The lines defined today, by their runtime value (the scan must find each of them).
KNOWN_LINES = (
    recorder_module.DISK_DIFFERS_WARNING,
    recorder_module.REVIEW_TRIGGER_WARNING,
    recorder_module.REVIEW_TRIGGER_CHECK_FAILED,
    scheduler_module.FORECAST_RECORD_REFRESH_FAILED,
    scheduler_module.FORECAST_RECORD_BAR_PREDATES_RUN,
    scheduler_module.FORECAST_RECORD_SERIES_ENDS_EARLY,
    *scheduler_module.FORECAST_RECORD_REFUSALS.values(),
)


def test_rc333_no_forecast_record_line_in_app_is_imperative() -> None:
    lines = forecast_record_literals(_app_sources())
    assert len(KNOWN_LINES) >= 10
    assert set(KNOWN_LINES) <= set(lines)  # the scan is not vacuous
    offenders = {line: imperative_findings(line) for line in lines if imperative_findings(line)}
    assert offenders == {}


def test_rc333_the_imperative_scan_has_teeth() -> None:
    flagged = (
        # The superseded RC-331 wording.
        "forecast_record: the sources or the runtime on disk differ from the loaded program;"
        " this run keeps the loaded provenance; restart the scheduler process to load them",
        "forecast_record: run the bootstrap first",
        "forecast_record: the database is locked; please close stock-desk",
        "forecast_record: the cache is stale, delete it",
        "forecast_record: the source failed. Retry later",
        "forecast_record: uv is missing (install it)",
        "forecast_record: Tell the coordinator",
    )
    for line in flagged:
        assert imperative_findings(line) != [], line
    stated = (
        "forecast_record: the live index refresh did not succeed; the run is skipped",
        "forecast_record: this run keeps the loaded provenance",
        "forecast_record: the run outcome is unchanged",
    )
    for line in stated:
        assert imperative_findings(line) == [], line


def test_rc333_the_literal_scan_finds_concatenated_and_f_string_lines() -> None:
    sources = {
        "a.py": 'X = (\n    "forecast_record: one;"\n    " restart it"\n)\n',
        "b.py": 'def f(n):\n    return f"forecast_record: {n} rows; delete them"\n',
        "c.py": 'Y = "scheduled job forecast_record: not at the start"\n',
    }
    found = forecast_record_literals(sources)
    assert set(found.values()) == {"a.py", "b.py"}
    assert all(imperative_findings(line) for line in found)
