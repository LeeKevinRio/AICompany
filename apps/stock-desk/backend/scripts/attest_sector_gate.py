"""Build-time NE-7 attestation: ``ci_passed_commit`` (ADR-0012 D-8, C-36, T-22).

Run from ``apps/stock-desk/backend`` on a **clean** working tree::

    uv run python scripts/attest_sector_gate.py

1. Refuses (exit 2, nothing run, nothing written) when ``git status
   --porcelain`` is not empty or git cannot answer.
2. Runs the NE-7 CI set -- ``pytest -m sector_ne7`` (T-5..T-9 and T-13 CI
   halves, plus T-15).
3. All green -- at least one test, no failure, no error, **no skip** -> writes
   ``app/_build/ci_attestation.json`` (``ci_passed_commit``, ``suite_hash``,
   ``passed_at``; git-ignored) and exits 0. Anything else deletes the old file
   and exits 1, so a red run can never leave a stale green attestation behind.

The scheduler then treats the running code as tested only if it is exactly
this commit, on a clean tree, with the same NE-7 test files
(:func:`app.services.sector_attestation.verify`). This is a local
self-attestation, not an external CI signature (ADR-0012 Consequences).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import sector_attestation as attestation  # noqa: E402
from app.services.sector_attestation import Attestation, GitProbe  # noqa: E402


@dataclass(frozen=True)
class SuiteRun:
    """What one run of the NE-7 set reported."""

    returncode: int
    tests: int
    failures: int
    errors: int
    skipped: int

    @property
    def green(self) -> bool:
        return (
            self.returncode == 0
            and self.tests > 0
            and self.failures == 0
            and self.errors == 0
            and self.skipped == 0
        )


def parse_junit(report: Path, returncode: int) -> SuiteRun:
    """Totals of a pytest ``--junitxml`` report (a missing report counts as a failure)."""
    try:
        root = ElementTree.parse(report).getroot()
    except (OSError, ElementTree.ParseError):
        return SuiteRun(returncode=returncode or 1, tests=0, failures=0, errors=1, skipped=0)
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))

    def total(name: str) -> int:
        return sum(int(suite.get(name, "0")) for suite in suites)

    return SuiteRun(
        returncode=returncode,
        tests=total("tests"),
        failures=total("failures"),
        errors=total("errors"),
        skipped=total("skipped"),
    )


def run_ne7_suite(root: Path) -> SuiteRun:
    """``pytest -m sector_ne7`` in ``root``, totals read from a junit report."""
    with tempfile.TemporaryDirectory() as scratch:
        report = Path(scratch) / "ne7.xml"
        done = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-m",
                attestation.NE7_MARKER,
                "-q",
                "-p",
                "no:cacheprovider",
                f"--junitxml={report}",
            ],
            cwd=root,
            check=False,
        )
        return parse_junit(report, done.returncode)


def attest(
    root: Path,
    *,
    git: GitProbe,
    run_suite: Callable[[Path], SuiteRun],
    now: Callable[[], datetime],
    say: Callable[[str], None] = print,
) -> int:
    """The whole procedure; 0 = attested, 1 = not green (old file removed), 2 = refused."""
    path = attestation.attestation_path(root)
    head, clean = git.head(), git.is_clean()
    if head is None or clean is None:
        say("拒絕：讀不到 git，無法記錄 ci_passed_commit。")
        return 2
    if not clean:
        say("拒絕：工作樹不乾淨（git status --porcelain 非空），不產生 attestation。")
        return 2
    result = run_suite(root)
    if not result.green:
        removed = attestation.remove_attestation(path)
        say(
            f"NE-7 測試集合未全綠（tests={result.tests} failures={result.failures} "
            f"errors={result.errors} skipped={result.skipped} exit={result.returncode}）；"
            + ("已刪除舊的 attestation。" if removed else "未產生 attestation。")
        )
        return 1
    if git.head() != head or git.is_clean() is not True:
        attestation.remove_attestation(path)
        say("拒絕：測試期間 commit 或工作樹有變動，未產生 attestation。")
        return 1
    record = Attestation(
        ci_passed_commit=head,
        suite_hash=attestation.suite_hash(root),
        passed_at=now().isoformat(),
    )
    attestation.write_attestation(path, record)
    say(f"attested ci_passed_commit={record.ci_passed_commit} suite_hash={record.suite_hash}")
    return 0


def main() -> int:
    root = attestation.BACKEND_ROOT
    return attest(
        root,
        git=attestation.SubprocessGit(root),
        run_suite=run_ne7_suite,
        now=lambda: datetime.now(UTC),
    )


if __name__ == "__main__":
    raise SystemExit(main())
