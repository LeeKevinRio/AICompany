"""NE-7's CI half: build attestation and judge-time check (ADR-0012 D-8, C-36, T-22).

* build time (``scripts/attest_sector_gate.py``): refuses on a dirty tree or
  unreadable git; a red, empty or skipping NE-7 run writes nothing and deletes
  the old attestation; a green run writes commit, suite hash and time;
* judge time (:func:`app.services.sector_attestation.verify`): commit mismatch,
  missing attestation, suite-hash mismatch, unreadable git and a dirty tree each
  fail it **on its own**;
* read time: the API's ``ci_passed_commit`` is the attested commit only when the
  check passes, and a statistics row from another commit is NE-7;
* the suite hash covers the marked test files, ``conftest.py`` and the helpers
  they import, and nothing else;
* ``SubprocessGit`` against a real throw-away repository.

No test here runs the real NE-7 suite or reads the developer's repository state.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType

import pytest

from app.services import sector_attestation as att
from app.services.sector_attestation import (
    ATTESTATION_MISSING,
    COMMIT_MISMATCH,
    DIRTY_WORKTREE,
    GIT_UNREADABLE,
    SUITE_HASH_MISMATCH,
    Attestation,
    AttestationCheck,
    SubprocessGit,
)
from app.services.sector_runtime import load_gate_runtime, runtime_from_check

BACKEND = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "attest_sector_gate", BACKEND / "scripts" / "attest_sector_gate.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


SCRIPT = _script()


@dataclass
class FakeGit:
    head_value: str | None = "abc123"
    clean_value: bool | None = True

    def head(self) -> str | None:
        return self.head_value

    def is_clean(self) -> bool | None:
        return self.clean_value


def _root(tmp_path: Path) -> Path:
    """A miniature backend: two NE-7 test files, a helper chain, an unrelated test."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "conftest.py").write_text("# markers\n", encoding="utf-8")
    (tests / "helper_a.py").write_text("from tests.helper_b import B\nA = B\n", encoding="utf-8")
    (tests / "helper_b.py").write_text("B = 1\n", encoding="utf-8")
    (tests / "unused_helper.py").write_text("C = 1\n", encoding="utf-8")
    (tests / "test_one.py").write_text(
        "import pytest\nfrom tests.helper_a import A\n\n"
        "@pytest.mark.sector_ne7\ndef test_a() -> None:\n    assert A\n",
        encoding="utf-8",
    )
    (tests / "test_two.py").write_text(
        "import pytest\npytestmark = pytest.mark.sector_ne7\n", encoding="utf-8"
    )
    (tests / "test_other.py").write_text(
        "from tests.unused_helper import C\n\ndef test_c() -> None:\n    assert C\n",
        encoding="utf-8",
    )
    return tmp_path


GREEN = SCRIPT.SuiteRun(returncode=0, tests=35, failures=0, errors=0, skipped=0)


# ---------------------------------------------------------------------------
# suite_hash
# ---------------------------------------------------------------------------


def test_the_suite_is_the_marked_files_their_helpers_and_conftest(tmp_path: Path) -> None:
    root = _root(tmp_path)
    names = [path.relative_to(root).as_posix() for path in att.suite_files(root)]
    assert names == [
        "tests/conftest.py",
        "tests/helper_a.py",
        "tests/helper_b.py",
        "tests/test_one.py",
        "tests/test_two.py",
    ]


def test_the_suite_hash_moves_with_the_suite_and_only_with_it(tmp_path: Path) -> None:
    root = _root(tmp_path)
    before = att.suite_hash(root)
    (root / "tests" / "test_other.py").write_text("def test_c() -> None: ...\n", "utf-8")
    (root / "tests" / "unused_helper.py").write_text("C = 2\n", encoding="utf-8")
    assert att.suite_hash(root) == before
    (root / "tests" / "helper_b.py").write_text("B = 2\n", encoding="utf-8")
    assert att.suite_hash(root) != before


def test_the_real_suite_covers_the_ne7_files() -> None:
    names = {path.name for path in att.suite_files(BACKEND)}
    assert {
        "test_sector_eval.py",
        "test_sector_eval_lookahead.py",
        "test_sectors_pit_invariance.py",
        "test_panel_index_equivalence.py",
        "conftest.py",
        "sector_eval_helpers.py",
        "sectors_helpers.py",
    } <= names
    assert "test_api_sectors.py" not in names


# ---------------------------------------------------------------------------
# Build time (the script)
# ---------------------------------------------------------------------------


def test_a_green_run_writes_the_attestation(tmp_path: Path) -> None:
    root = _root(tmp_path)
    code = SCRIPT.attest(
        root, git=FakeGit(), run_suite=lambda _: GREEN, now=lambda: NOW, say=lambda _: None
    )
    assert code == 0
    written = json.loads(att.attestation_path(root).read_text(encoding="utf-8"))
    assert written == {
        "ci_passed_commit": "abc123",
        "suite_hash": att.suite_hash(root),
        "passed_at": NOW.isoformat(),
    }


@pytest.mark.parametrize(
    "result",
    [
        SCRIPT.SuiteRun(returncode=1, tests=35, failures=1, errors=0, skipped=0),
        SCRIPT.SuiteRun(returncode=1, tests=35, failures=0, errors=2, skipped=0),
        SCRIPT.SuiteRun(returncode=0, tests=35, failures=0, errors=0, skipped=1),
        SCRIPT.SuiteRun(returncode=5, tests=0, failures=0, errors=0, skipped=0),
    ],
    ids=["failure", "error", "skip", "nothing_collected"],
)
def test_anything_but_green_writes_nothing_and_deletes_the_old_file(
    tmp_path: Path, result: object
) -> None:
    root = _root(tmp_path)
    att.write_attestation(att.attestation_path(root), Attestation("old", "h", "t"))
    code = SCRIPT.attest(
        root, git=FakeGit(), run_suite=lambda _: result, now=lambda: NOW, say=lambda _: None
    )
    assert code == 1
    assert not att.attestation_path(root).exists()


@pytest.mark.parametrize(
    "git", [FakeGit(clean_value=False), FakeGit(head_value=None), FakeGit(clean_value=None)]
)
def test_a_dirty_tree_or_unreadable_git_is_refused_before_running(
    tmp_path: Path, git: FakeGit
) -> None:
    root = _root(tmp_path)
    ran: list[Path] = []

    def run(where: Path) -> object:
        ran.append(where)
        return GREEN

    code = SCRIPT.attest(root, git=git, run_suite=run, now=lambda: NOW, say=lambda _: None)
    assert code == 2 and ran == []
    assert not att.attestation_path(root).exists()


def test_a_tree_that_changes_during_the_run_is_not_attested(tmp_path: Path) -> None:
    root = _root(tmp_path)
    git = FakeGit()

    def run(_: Path) -> object:
        git.clean_value = False
        return GREEN

    code = SCRIPT.attest(root, git=git, run_suite=run, now=lambda: NOW, say=lambda _: None)
    assert code == 1 and not att.attestation_path(root).exists()


def test_the_junit_report_is_read_including_skips(tmp_path: Path) -> None:
    report = tmp_path / "r.xml"
    report.write_text(
        '<testsuites><testsuite name="pytest" tests="7" failures="0" errors="0" '
        'skipped="2"/></testsuites>',
        encoding="utf-8",
    )
    run = SCRIPT.parse_junit(report, 0)
    assert (run.tests, run.skipped, run.green) == (7, 2, False)
    missing = SCRIPT.parse_junit(tmp_path / "absent.xml", 0)
    assert not missing.green


# ---------------------------------------------------------------------------
# Judge time: five causes, each alone
# ---------------------------------------------------------------------------


def _attested(root: Path, commit: str = "abc123") -> None:
    att.write_attestation(
        att.attestation_path(root), Attestation(commit, att.suite_hash(root), NOW.isoformat())
    )


def test_a_matching_clean_attested_build_passes(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _attested(root)
    check = att.verify(root, git=FakeGit())
    assert check.ok and check.running_commit == check.ci_passed_commit == "abc123"


@pytest.mark.parametrize(
    ("git", "setup", "problem"),
    [
        (FakeGit(head_value="def456"), "attest", COMMIT_MISMATCH),
        (FakeGit(), "none", ATTESTATION_MISSING),
        (FakeGit(), "malformed", ATTESTATION_MISSING),
        (FakeGit(), "edit_suite", SUITE_HASH_MISMATCH),
        (FakeGit(head_value=None), "attest", GIT_UNREADABLE),
        (FakeGit(clean_value=None), "attest", GIT_UNREADABLE),
        (FakeGit(clean_value=False), "attest", DIRTY_WORKTREE),
    ],
)
def test_each_cause_alone_fails_the_check(
    tmp_path: Path, git: FakeGit, setup: str, problem: str
) -> None:
    root = _root(tmp_path)
    if setup in ("attest", "edit_suite"):
        _attested(root)
    if setup == "malformed":
        path = att.attestation_path(root)
        path.parent.mkdir(parents=True)
        path.write_text('{"ci_passed_commit": ""}', encoding="utf-8")
    if setup == "edit_suite":
        (root / "tests" / "test_one.py").write_text("# changed\n", encoding="utf-8")
    check = att.verify(root, git=git)
    assert check.problems == (problem,)
    assert not check.ok


# ---------------------------------------------------------------------------
# Read time
# ---------------------------------------------------------------------------


def test_the_api_gets_the_commit_only_when_the_check_passes(tmp_path: Path) -> None:
    ok = runtime_from_check(AttestationCheck("abc123", "abc123", ()))
    assert ok.ci_passed_commit == "abc123"
    bad = runtime_from_check(AttestationCheck("def456", "abc123", (COMMIT_MISMATCH,)))
    assert bad.ci_passed_commit is None
    # Unverified cost model and DE-5 stay unverified (NE-3, NE-1).
    assert ok.fee_verified_on is None and ok.de5_verified_on is None
    root = _root(tmp_path)
    _attested(root)
    assert load_gate_runtime(root, git=FakeGit()).ci_passed_commit == "abc123"
    assert load_gate_runtime(root, git=FakeGit(clean_value=False)).ci_passed_commit is None


def test_a_row_from_another_commit_is_ne7_at_read_time() -> None:
    from app.data.calendar import TradingCalendar
    from app.sectors import gate
    from app.sectors.definition import SECTOR_MOMENTUM_V1
    from app.sectors.gate import EvaluationWindow, GateInputs, PitStatus
    from tests.sector_board_helpers import stats_record

    def outcome(deployed: str | None) -> tuple[str, ...]:
        result = gate.evaluate(
            GateInputs(
                definition=SECTOR_MOMENTUM_V1,
                data_source="twse_snapshot",
                board_method_version=SECTOR_MOMENTUM_V1.method_version,
                board_invariant_violated=False,
                as_of_session=date(2029, 3, 12),
                calendar=TradingCalendar([date(2029, 3, 12)]),
                fee_verified_on=date(2026, 9, 1),
                de5_verified_on=date(2026, 9, 1),
                ci_passed_commit=deployed,
                pit_status=PitStatus(accumulation_start=date(2026, 1, 5), ok_sessions={}),
                window=EvaluationWindow(decision_dates=(), trading_days=()),
                stats_history=(stats_record("r1"),),
                approvals=(),
            )
        )
        return result.not_evaluated_reasons

    assert "lookahead_tests_failed" not in outcome("c0ffee")
    assert "lookahead_tests_failed" in outcome("another")
    assert "lookahead_tests_failed" in outcome(None)


# ---------------------------------------------------------------------------
# SubprocessGit against a real repository
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_subprocess_git_reads_head_and_cleanliness(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "init")
    probe = SubprocessGit(repo)
    head = probe.head()
    assert head is not None and len(head) == 40
    assert probe.is_clean() is True
    (repo / "b.txt").write_text("untracked\n", encoding="utf-8")
    assert probe.is_clean() is False
    outside = SubprocessGit(tmp_path / "not-a-repo")
    assert outside.head() is None and outside.is_clean() is None
