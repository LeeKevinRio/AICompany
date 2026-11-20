"""The CG-2 registration one-click files stay retired (ADR-0030 supplement 9 point 1, S-19a).

* The two scripts and the two launchers do not exist, on disk or in the git index.
* No file git tracks under ``apps/stock-desk`` refers to a retired file, by the
  discriminating pattern :data:`RETIRED_REFERENCE` (tech-architect reading,
  2026-11-20 topic 2). The only file excluded is this one, by exact path: it has
  to spell the retired names out.

The scan reads the working-tree bytes of ``git ls-files`` under ``apps/stock-desk``,
so untracked and ignored files (``.env``, ``data/*.db``, virtual environments,
caches) are never opened. ``work/`` lies outside ``apps/stock-desk`` and is not
scanned.
"""

from __future__ import annotations

import re
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

#: A reference to a retired file (case-sensitive, as grep is). ``cg2_register``
#: not followed by ``s`` covers the script (``cg2_register.py``, a bare module name
#: such as ``scripts.cg2_register``) and the retired test helpers and tests
#: (``cg2_register_world``, ``test_cg2_register_flow``, ...). It is stricter than
#: the example ``cg2_register\.py|cg2_register_`` and leaves out the same names.
RETIRED_REFERENCE: Final = re.compile(
    rb"cg2_register(?!s)|cg2-register|cg2-preflight|verify_cg2_instruction"
)

#: Out of scope: test names where ``cg2_registers`` only happens to start with
#: ``cg2_register``. They refer to no retired file and must not be renamed
#: (tech-architect, 2026-11-20 topic 2, note 2); the pattern above leaves them out.
NOT_A_REFERENCE: Final = {
    "backend/tests/test_dirdef_v1_0_fields.py": (
        b"def test_cg2_registers_exactly_dirdef_v1_0_and_the_two_rule_sets() -> None:"
    ),
    "backend/tests/test_outlook_rule_files.py": (
        b"def test_cg2_registers_both_files_with_their_bytes_hash() -> None:"
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
    """Map each file under ``root`` referring to a retired file to its stripped hit lines."""
    found: dict[str, frozenset[bytes]] = {}
    for name in names:
        path = root / name
        if (exclude is not None and path.resolve() == exclude) or not path.is_file():
            continue
        lines = frozenset(
            line.strip()
            for line in path.read_bytes().splitlines()
            if RETIRED_REFERENCE.search(line)
        )
        if lines:
            found[name] = lines
    return found


def test_the_four_retired_files_do_not_exist() -> None:
    for name in RETIRED_FILES:
        assert not (STOCK_DESK / name).exists(), name
    tracked = set(_tracked_files())
    assert tracked.isdisjoint(RETIRED_FILES)


def test_no_tracked_file_refers_to_a_retired_file() -> None:
    assert _hits(STOCK_DESK, _tracked_files(), THIS_FILE) == {}


def test_the_two_cg2_registers_test_names_are_still_there_and_out_of_scope() -> None:
    for name, line in NOT_A_REFERENCE.items():
        held = [x.strip() for x in (STOCK_DESK / name).read_bytes().splitlines()]
        assert line in held, name
        assert b"cg2_register" in line
        assert RETIRED_REFERENCE.search(line) is None


def test_the_scan_covers_this_folder_and_excludes_only_this_file() -> None:
    tracked = _tracked_files()
    relative = THIS_FILE.relative_to(STOCK_DESK).as_posix()
    assert "backend/pyproject.toml" in tracked and "dev-up.bat" in tracked
    # Every retired file name matches the pattern ...
    assert all(RETIRED_REFERENCE.search(name.encode()) for name in RETIRED_FILES)
    # ... this file holds them, so excluding it is needed, and it is the only file
    # excluded: scanning with nothing excluded adds this file alone.
    assert _hits(STOCK_DESK, sorted({*tracked, relative}), None).keys() == {relative}


def test_the_pattern_matches_each_retired_name(tmp_path: Path) -> None:
    probes = (
        b"cg2_register.py",
        b"tests.cg2_register_world",
        b"import scripts.cg2_register",
        b"cg2-register.bat",
        b"cg2-preflight.bat",
        b"verify_cg2_instruction",
    )
    for index, probe in enumerate(probes):
        (tmp_path / f"f{index}.txt").write_bytes(b"ok\n  see " + probe + b"  \r\nok\n")
    (tmp_path / "clean.txt").write_bytes(
        b"cg2_registration cg2_registers_x CG2_REGISTER dev-up.bat cg2-registry\n"
    )
    names = sorted(p.name for p in tmp_path.iterdir())
    assert _hits(tmp_path, names, None) == {
        f"f{index}.txt": frozenset({b"see " + probe}) for index, probe in enumerate(probes)
    }


def test_the_scan_is_case_sensitive_and_skips_the_excluded_file(tmp_path: Path) -> None:
    (tmp_path / "upper.txt").write_bytes(b"CG2-REGISTER CG2-PREFLIGHT\n")
    (tmp_path / "self.py").write_bytes(b"cg2-register\n")
    (tmp_path / "other.py").write_bytes(b"cg2-register\n")
    names = ["upper.txt", "self.py", "other.py", "missing.txt"]
    hits = _hits(tmp_path, names, (tmp_path / "self.py").resolve())
    assert hits == {"other.py": frozenset({b"cg2-register"})}
