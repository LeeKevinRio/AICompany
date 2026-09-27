"""``app.data.sqlite_util`` stays a leaf, and is the only place WAL is switched on (ADR-0012 v10).

Stores on three different database files (main, market, research) take
``enable_wal`` from it, so it must not become a path from one of them to
another's configuration or tables:

* it reaches no ``app.*`` module and imports only the standard library it
  needs -- no ``os``, ``dotenv``, ``app.settings`` or ``httpx``, no
  ``environ`` / ``getenv``, no ``sqlite3.connect`` of its own;
* nobody takes ``enable_wal`` from ``app.data.cache`` any more;
* no other module under ``app/`` issues ``PRAGMA journal_mode=WAL`` itself.

Every scan has a teeth test proving it can fail.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.import_graph import APP_ROOT, imported_modules, module_path, reachable_app_modules

LEAF = "app.data.sqlite_util"
TESTS_ROOT = Path(__file__).resolve().parent

#: Imports a leaf that every store may take must never make (K-1).
_BANNED_IMPORTS = ("os", "dotenv", "app.settings", "httpx")
#: Names through which a module reads its environment.
_BANNED_NAMES = frozenset({"environ", "getenv"})
#: A WAL switch written out rather than delegated to ``enable_wal``.
_WAL_PRAGMA = re.compile(r"journal_mode\s*=\s*wal", re.IGNORECASE)


def _leaf_path() -> Path:
    path = module_path(LEAF)
    assert path is not None, LEAF
    return path


def _docstring_nodes(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


def _leaf_violations(path: Path) -> list[str]:
    """Everything in ``path`` that a leaf helper must not do."""
    hits = [f"imports {name}" for name in sorted(imported_modules(path, LEAF))]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            for banned in _BANNED_IMPORTS:
                if name == banned or name.startswith(f"{banned}."):
                    hits.append(f"imports {name}")
        if isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            hits.append(f"uses {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in _BANNED_NAMES:
            hits.append(f"uses .{node.attr}")
        if isinstance(node, ast.alias) and node.name in _BANNED_NAMES:
            hits.append(f"imports {node.name}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            hits.append("calls .connect")
    return hits


def _wal_pragma_hits(path: Path) -> list[str]:
    """String literals in ``path`` (docstrings excluded) that switch WAL on directly."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_nodes(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and _WAL_PRAGMA.search(node.value)
    ]


def _takes_enable_wal_from_the_cache(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.data.cache"
        and any(alias.name == "enable_wal" for alias in node.names)
        for node in ast.walk(tree)
    )


# ---------------------------------------------------------------------------
# The leaf itself
# ---------------------------------------------------------------------------


def test_the_leaf_reaches_no_other_app_module() -> None:
    assert reachable_app_modules((LEAF,)) == {LEAF}


def test_the_leaf_reads_no_environment_and_opens_no_connection() -> None:
    assert _leaf_violations(_leaf_path()) == []


@pytest.mark.parametrize(
    "addition",
    [
        "from app.data.interface import Market",
        "import os",
        "from os import environ",
        "from dotenv import load_dotenv",
        "import app.settings.store",
        "import httpx",
        "import os.path",
        "_PATH = __import__('os').getenv('X')",
        "_CONN = sqlite3.connect(':memory:')",
    ],
)
def test_leaf_scan_has_teeth(tmp_path: Path, addition: str) -> None:
    leaked = tmp_path / "sqlite_util.py"
    leaked.write_text(_leaf_path().read_text(encoding="utf-8") + f"\n{addition}\n")
    assert _leaf_violations(leaked) != []


# ---------------------------------------------------------------------------
# Where WAL is switched on
# ---------------------------------------------------------------------------


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def test_nobody_takes_enable_wal_from_the_cache() -> None:
    found = [
        str(path)
        for root in (APP_ROOT, TESTS_ROOT)
        for path in _python_files(root)
        if _takes_enable_wal_from_the_cache(path)
    ]
    assert found == []


def test_cache_scan_has_teeth(tmp_path: Path) -> None:
    source = tmp_path / "store.py"
    source.write_text("from app.data.cache import BUSY_TIMEOUT_MS, enable_wal\n")
    assert _takes_enable_wal_from_the_cache(source)


def test_only_the_leaf_issues_the_wal_pragma() -> None:
    leaf = _leaf_path()
    found = {
        str(path.relative_to(APP_ROOT)): hits
        for path in _python_files(APP_ROOT)
        if path != leaf and (hits := _wal_pragma_hits(path))
    }
    assert found == {}


def test_wal_pragma_scan_has_teeth(tmp_path: Path) -> None:
    source = tmp_path / "store.py"
    source.write_text('"""Mentions PRAGMA journal_mode=WAL in prose only."""\n')
    assert _wal_pragma_hits(source) == []
    source.write_text('def f(conn):\n    conn.execute("PRAGMA journal_mode = wal")\n')
    assert _wal_pragma_hits(source) != []
