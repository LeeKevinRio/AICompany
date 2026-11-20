"""The CG-2 registration one-click files stay retired (ADR-0030 supplement 9 point 1, S-19a).

* The two scripts and the two launchers do not exist, on disk or in the git index.
* No file git tracks under ``apps/stock-desk`` holds any of the four retired names,
  except this file (it has to spell them out) and the entries of
  :data:`PENDING_RULING`, each pending a tech-architect ruling.

The scan reads the working-tree bytes of ``git ls-files`` under ``apps/stock-desk``,
so untracked and ignored files (``.env``, ``data/*.db``, virtual environments,
caches) are never opened. ``work/`` lies outside ``apps/stock-desk`` and is not
scanned. The only path excluded is this file itself, by exact path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Final

BACKEND: Final = Path(__file__).resolve().parents[1]
STOCK_DESK: Final = BACKEND.parent
THIS_FILE: Final = Path(__file__).resolve()

#: The four retired files, relative to ``apps/stock-desk``.
RETIRED_FILES: Final = (
    "backend/scripts/cg2_register.py",
    "backend/scripts/verify_cg2_instruction.py",
    "cg2-preflight.bat",
    "cg2-register.bat",
)

#: The four names S-19a says grep must not find (case-sensitive, as grep does).
RETIRED_NAMES: Final = (
    b"cg2_register",
    b"cg2-register",
    b"cg2-preflight",
    b"verify_cg2_instruction",
)

#: Hits kept for now: path relative to ``apps/stock-desk`` -> the exact stripped lines.
#: Both are test function names where ``cg2_registers`` merely starts with a retired
#: name; neither refers to a retired file. Pending tech-architect ruling.
PENDING_RULING: Final[dict[str, frozenset[bytes]]] = {
    "backend/tests/test_dirdef_v1_0_fields.py": frozenset(
        {b"def test_cg2_registers_exactly_dirdef_v1_0_and_the_two_rule_sets() -> None:"}
    ),
    "backend/tests/test_outlook_rule_files.py": frozenset(
        {b"def test_cg2_registers_both_files_with_their_bytes_hash() -> None:"}
    ),
}


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--", "."],
        cwd=STOCK_DESK,
        capture_output=True,
        check=True,
    ).stdout
    return [name for name in out.decode("utf-8").split("\0") if name]


def _hits(root: Path, names: list[str], exclude: Path | None) -> dict[str, frozenset[bytes]]:
    """Map each file under ``root`` holding a retired name to its stripped hit lines."""
    found: dict[str, frozenset[bytes]] = {}
    for name in names:
        path = root / name
        if (exclude is not None and path.resolve() == exclude) or not path.is_file():
            continue
        lines = frozenset(
            line.strip()
            for line in path.read_bytes().splitlines()
            if any(retired in line for retired in RETIRED_NAMES)
        )
        if lines:
            found[name] = lines
    return found


def test_the_four_retired_files_do_not_exist() -> None:
    for name in RETIRED_FILES:
        assert not (STOCK_DESK / name).exists(), name
    tracked = set(_tracked_files())
    assert tracked.isdisjoint(RETIRED_FILES)


def test_no_tracked_file_names_a_retired_file_outside_the_pending_ruling_list() -> None:
    hits = _hits(STOCK_DESK, _tracked_files(), THIS_FILE)
    # Equality, not inclusion: a new hit fails, and so does a pending entry that is
    # gone (the list has to shrink with it).
    assert hits == PENDING_RULING


def test_the_scan_covers_this_folder_and_excludes_only_this_file() -> None:
    tracked = _tracked_files()
    relative = THIS_FILE.relative_to(STOCK_DESK).as_posix()
    # The scan sees the backend sources, the launchers and this file (once committed).
    assert "backend/pyproject.toml" in tracked and "dev-up.bat" in tracked
    # This file does hold every retired name, so excluding it is needed ...
    source = THIS_FILE.read_bytes()
    assert all(retired in source for retired in RETIRED_NAMES)
    # ... and it is the only file excluded: scanning with nothing excluded adds it alone.
    with_self = _hits(STOCK_DESK, [*tracked, relative], None)
    assert set(with_self) - set(PENDING_RULING) == {relative}


def test_the_scan_finds_each_retired_name(tmp_path: Path) -> None:
    for index, retired in enumerate(RETIRED_NAMES):
        (tmp_path / f"f{index}.txt").write_bytes(b"ok\n  see " + retired + b".x  \r\nok\n")
    (tmp_path / "clean.txt").write_bytes(b"cg2_registration dev-up.bat cg2\n")
    names = sorted(p.name for p in tmp_path.iterdir())
    hits = _hits(tmp_path, names, None)
    assert hits == {
        f"f{index}.txt": frozenset({b"see " + retired + b".x"})
        for index, retired in enumerate(RETIRED_NAMES)
    }


def test_the_scan_is_case_sensitive_and_skips_the_excluded_file(tmp_path: Path) -> None:
    (tmp_path / "upper.txt").write_bytes(b"CG2_REGISTER CG2-PREFLIGHT\n")
    (tmp_path / "self.py").write_bytes(b"cg2-register\n")
    (tmp_path / "other.py").write_bytes(b"cg2-register\n")
    names = ["upper.txt", "self.py", "other.py", "missing.txt"]
    hits = _hits(tmp_path, names, (tmp_path / "self.py").resolve())
    assert hits == {"other.py": frozenset({b"cg2-register"})}
