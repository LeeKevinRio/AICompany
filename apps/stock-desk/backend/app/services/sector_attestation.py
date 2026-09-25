"""NE-7's CI half: the local build attestation ``ci_passed_commit`` (ADR-0012 D-8, C-36, T-22).

Build time (``scripts/attest_sector_gate.py``): on a clean working tree only,
run the NE-7 CI test set (pytest marker ``sector_ne7``). All green -> write
``app/_build/ci_attestation.json`` with ``ci_passed_commit``, ``suite_hash``
and ``passed_at``; anything else -> delete the old file. The file is
git-ignored.

Judge time (the scheduler's ``services.sector_board``): :func:`verify` answers
"is the code running now the code that passed?". Each of the following, on its
own, fails it -- and a failure is NE-7 for that statistics row:

* ``git_unreadable`` -- ``git rev-parse HEAD`` / ``git status`` cannot run;
* ``dirty_worktree`` -- ``git status --porcelain`` is not empty;
* ``attestation_missing`` -- no readable attestation file;
* ``commit_mismatch`` -- ``running_commit != ci_passed_commit``;
* ``suite_hash_mismatch`` -- the NE-7 test files on disk hash differently.

Read time (the API process): the deployed ``ci_passed_commit`` is read once at
process start by :mod:`app.services.sector_runtime` and handed to
:mod:`app.sectors.gate`, which compares it with each row's ``running_commit``
(C-24: the gate itself reads nothing).

This is a local self-attestation, not an external CI signature: it stops an
untested commit or an edited tree, not deliberate forgery (ADR-0012
Consequences). Nothing here talks to GitHub or any network.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

#: ``apps/stock-desk/backend`` (this file is ``app/services/sector_attestation.py``).
BACKEND_ROOT: Final = Path(__file__).resolve().parents[2]
#: Where the attestation lives, relative to the backend root (git-ignored).
ATTESTATION_RELATIVE: Final = Path("app") / "_build" / "ci_attestation.json"
#: The pytest marker selecting the NE-7 CI set (T-5..T-9, T-13 CI halves, T-15).
NE7_MARKER: Final = "sector_ne7"
TESTS_DIRNAME: Final = "tests"

GIT_UNREADABLE: Final = "git_unreadable"
DIRTY_WORKTREE: Final = "dirty_worktree"
ATTESTATION_MISSING: Final = "attestation_missing"
COMMIT_MISMATCH: Final = "commit_mismatch"
SUITE_HASH_MISMATCH: Final = "suite_hash_mismatch"

_GIT_TIMEOUT_SECONDS: Final = 20


@dataclass(frozen=True)
class Attestation:
    ci_passed_commit: str
    suite_hash: str
    passed_at: str


@dataclass(frozen=True)
class AttestationCheck:
    """The judge-time answer. ``ok`` iff ``problems`` is empty."""

    running_commit: str | None
    ci_passed_commit: str | None
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


class GitProbe(Protocol):
    """The two facts the check needs from git; ``None`` when git cannot answer."""

    def head(self) -> str | None: ...

    def is_clean(self) -> bool | None: ...


class SubprocessGit:
    """:class:`GitProbe` over the ``git`` executable, run in ``root``."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _run(self, *args: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", *args],
                cwd=self._root,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout if done.returncode == 0 else None

    def head(self) -> str | None:
        out = self._run("rev-parse", "HEAD")
        commit = out.strip() if out is not None else ""
        return commit or None

    def is_clean(self) -> bool | None:
        out = self._run("status", "--porcelain")
        return None if out is None else out.strip() == ""


def attestation_path(root: Path = BACKEND_ROOT) -> Path:
    return root / ATTESTATION_RELATIVE


# ---------------------------------------------------------------------------
# suite_hash: the NE-7 test files, listed and hashed
# ---------------------------------------------------------------------------


def _uses_marker(path: Path) -> bool:
    """The file applies ``pytest.mark.sector_ne7`` (in code, not merely in a string)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.Attribute) and node.attr == NE7_MARKER for node in ast.walk(tree)
    )


def _local_imports(path: Path, tests_root: Path) -> set[Path]:
    """``tests.*`` modules ``path`` imports (helpers the NE-7 tests stand on)."""
    found: set[Path] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        for name in names:
            parts = name.split(".")
            if parts[0] != TESTS_DIRNAME or len(parts) < 2:
                continue
            candidate = tests_root.joinpath(*parts[1:]).with_suffix(".py")
            if candidate.is_file():
                found.add(candidate)
    return found


def suite_files(root: Path = BACKEND_ROOT) -> tuple[Path, ...]:
    """Every file the NE-7 set runs on: marked test files, ``conftest.py``, their helpers.

    A test file is in the set when its code applies the marker; the ``tests.*``
    modules those files import are followed transitively, so editing a helper
    changes the hash as surely as editing a test.
    """
    tests_root = root / TESTS_DIRNAME
    if not tests_root.is_dir():
        return ()
    selected = {path for path in tests_root.rglob("test_*.py") if _uses_marker(path)}
    conftest = tests_root / "conftest.py"
    if conftest.is_file():
        selected.add(conftest)
    queue = list(selected)
    while queue:
        for helper in _local_imports(queue.pop(), tests_root):
            if helper not in selected:
                selected.add(helper)
                queue.append(helper)
    return tuple(sorted(selected))


def hash_files(files: Iterable[Path], root: Path) -> str:
    """SHA-256 over each file's root-relative POSIX path and bytes, in path order."""
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big") + relative)
        digest.update(len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


def suite_hash(root: Path = BACKEND_ROOT) -> str:
    return hash_files(suite_files(root), root)


# ---------------------------------------------------------------------------
# The attestation file
# ---------------------------------------------------------------------------


def read_attestation(path: Path) -> Attestation | None:
    """The attestation at ``path``; ``None`` when absent or malformed (fail closed)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    fields = ("ci_passed_commit", "suite_hash", "passed_at")
    values = [data.get(name) for name in fields]
    if not all(isinstance(value, str) and value for value in values):
        return None
    commit, hashed, passed_at = (str(value) for value in values)
    return Attestation(ci_passed_commit=commit, suite_hash=hashed, passed_at=passed_at)


def write_attestation(path: Path, attestation: Attestation) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ci_passed_commit": attestation.ci_passed_commit,
        "suite_hash": attestation.suite_hash,
        "passed_at": attestation.passed_at,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def remove_attestation(path: Path) -> bool:
    """Delete the attestation; ``True`` if a file was there."""
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


# ---------------------------------------------------------------------------
# Judge time
# ---------------------------------------------------------------------------


def verify(
    root: Path = BACKEND_ROOT,
    *,
    git: GitProbe | None = None,
    path: Path | None = None,
) -> AttestationCheck:
    """Whether the running code is the attested code (every failing reason is listed)."""
    probe = git if git is not None else SubprocessGit(root)
    attestation = read_attestation(path if path is not None else attestation_path(root))
    running = probe.head()
    clean = probe.is_clean()
    problems: list[str] = []
    if running is None or clean is None:
        problems.append(GIT_UNREADABLE)
    if clean is False:
        problems.append(DIRTY_WORKTREE)
    if attestation is None:
        problems.append(ATTESTATION_MISSING)
    else:
        if running is not None and running != attestation.ci_passed_commit:
            problems.append(COMMIT_MISMATCH)
        if suite_hash(root) != attestation.suite_hash:
            problems.append(SUITE_HASH_MISMATCH)
    return AttestationCheck(
        running_commit=running,
        ci_passed_commit=attestation.ci_passed_commit if attestation is not None else None,
        problems=tuple(problems),
    )
