"""Structural guards of the sector package (ADR-0012 T-1, T-17).

T-1 (C-1..C-5, C-17):

* every file under ``app/sectors`` is listed and every listed name resolves;
* C-1: all ``app.*`` modules reachable from the pure core sit inside the
  whitelist; ``store`` may add ``app.data.cache`` and take only
  ``resolve_db_path`` from it;
* C-2: none of the forbidden packages is reachable, and ``httpx`` is not
  imported in any form (plain, ``from``, ``importlib`` / ``__import__`` or a
  string naming it);
* C-3: advice, playbook, kelly, portfolio, alerts and signals never reach
  ``app.sectors``;
* C-5: the future ``app.api.sectors`` router's direct imports (wave 3);
* C-17: no score / rating vocabulary and no advice-engine field name in any
  identifier, attribute or string of ``app/sectors`` (docstrings excluded).

T-17 (C-24, C-20): ``gate.py`` / ``coverage.py`` / ``sector_eval.py`` read no
environment or configuration, ``gate.py`` does not import ``sqlite3``, and
``gate_status`` is assigned only in ``app/sectors/gate.py``.

Every scan has a teeth test proving it can fail.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.import_graph import (
    APP_ROOT,
    imported_modules,
    module_path,
    offenders,
    reachable_app_modules,
)

SECTORS_ROOT = APP_ROOT / "sectors"

PURE_CORE = (
    "app.sectors",
    "app.sectors.definition",
    "app.sectors.models",
    "app.sectors.universe",
    "app.sectors.index",
    "app.sectors.ranking",
    "app.sectors.constituents",
    "app.sectors.coverage",
    "app.sectors.gate",
)
STORE = "app.sectors.store"
GUARDED_MODULES = (*PURE_CORE, STORE)

#: C-1 whitelist for the pure core.
WHITELIST = frozenset(
    {"app.data.panel", "app.data.interface", "app.data.calendar", "app.positions.sectors"}
)
#: The one extra module the store may reach, and the one name it may take from it.
STORE_EXTRA = frozenset({"app.data.cache"})
STORE_CACHE_NAMES = frozenset({"resolve_db_path"})

#: C-2: never reachable from app.sectors.
FORBIDDEN_FROM_SECTORS = (
    "app.advice",
    "app.signals",
    "app.backtest",
    "app.directory",
    "app.research",
    "app.playbook",
    "app.kelly",
    "app.portfolio",
    "app.alerts",
    "app.api",
    "app.services",
    "app.data.providers",
    "app.data.service",
    "app.data.http",
)

#: C-3: packages that must never reach app.sectors.
NO_SECTORS_PACKAGES = ("advice", "playbook", "kelly", "portfolio", "alerts", "signals")

#: C-5: forbidden direct imports of the sectors router.
ROUTER = "app.api.sectors"
ROUTER_FORBIDDEN = (
    "app.advice",
    "app.signals",
    "app.backtest",
    "app.research",
    "app.data.service",
    "app.services.market",
    "app.portfolio",
)


def _real_modules(names: set[str]) -> set[str]:
    """Drop ``module.Symbol`` entries: only names that resolve to a source file."""
    return {name for name in names if module_path(name) is not None}


def _outside_whitelist(reachable: set[str], extra: frozenset[str] = frozenset()) -> list[str]:
    allowed = WHITELIST | extra
    return sorted(
        name
        for name in _real_modules(reachable)
        if not (name == "app.sectors" or name.startswith("app.sectors.")) and name not in allowed
    )


# ---------------------------------------------------------------------------
# T-1: coverage of the guard itself
# ---------------------------------------------------------------------------


def test_every_guarded_module_resolves() -> None:
    for module in GUARDED_MODULES:
        assert module_path(module) is not None, module
    for module in (*WHITELIST, *STORE_EXTRA):
        assert module_path(module) is not None, module


def test_every_sectors_file_is_guarded() -> None:
    on_disk = {
        "app.sectors" if path.stem == "__init__" else f"app.sectors.{path.stem}"
        for path in SECTORS_ROOT.glob("*.py")
    }
    assert on_disk == set(GUARDED_MODULES), sorted(on_disk ^ set(GUARDED_MODULES))
    assert not [p for p in SECTORS_ROOT.iterdir() if p.is_dir() and p.name != "__pycache__"]


# ---------------------------------------------------------------------------
# C-1 / C-2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", PURE_CORE)
def test_pure_core_reaches_only_the_whitelist(module: str) -> None:
    found = _outside_whitelist(reachable_app_modules((module,)))
    assert found == [], f"{module} reaches {found} (ADR-0012 C-1)"


def test_store_reaches_only_the_whitelist_plus_the_cache_path() -> None:
    found = _outside_whitelist(reachable_app_modules((STORE,)), STORE_EXTRA)
    assert found == [], f"{STORE} reaches {found} (ADR-0012 C-1)"


def test_store_takes_only_resolve_db_path_from_the_cache() -> None:
    path = module_path(STORE)
    assert path is not None
    taken: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module == "app.data.cache":
            taken |= {alias.name for alias in node.names}
        if isinstance(node, ast.Import):
            assert all(alias.name != "app.data.cache" for alias in node.names)
    assert taken == STORE_CACHE_NAMES


@pytest.mark.parametrize("forbidden", FORBIDDEN_FROM_SECTORS)
def test_sectors_never_reach_a_forbidden_package(forbidden: str) -> None:
    reachable = reachable_app_modules(GUARDED_MODULES)
    assert offenders(reachable, forbidden) == [], f"app.sectors reaches {forbidden}"


def test_whitelist_scan_has_teeth() -> None:
    assert _outside_whitelist(reachable_app_modules(("app.api.advice",))) != []
    assert offenders(reachable_app_modules(("app.api.advice",)), "app.advice") != []


# ---------------------------------------------------------------------------
# C-2: httpx in any form
# ---------------------------------------------------------------------------

_HTTPX_PATTERNS = (
    re.compile(r"^\s*import\s+httpx\b", re.MULTILINE),
    re.compile(r"^\s*from\s+httpx\b", re.MULTILINE),
    re.compile(r"\bimportlib\b"),
    re.compile(r"\b__import__\b"),
)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """``id()`` of every docstring constant (prose may name what code must not use)."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    ids.add(id(body[0].value))
    return ids


def _httpx_hits(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    hits = [pattern.pattern for pattern in _HTTPX_PATTERNS if pattern.search(source)]
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "httpx" in node.value and id(node) not in docstrings:
                hits.append(f"string {node.value!r}")
    return hits


def test_no_httpx_in_any_form_under_sectors() -> None:
    for path in sorted(SECTORS_ROOT.glob("*.py")):
        assert _httpx_hits(path) == [], path.name


@pytest.mark.parametrize(
    "source",
    [
        "import httpx\n",
        "from httpx import Client\n",
        "import importlib\nclient = importlib.import_module('x')\n",
        "mod = __import__('os')\n",
        "NAME = 'httpx'\n",
    ],
)
def test_httpx_scan_has_teeth(tmp_path: Path, source: str) -> None:
    path = tmp_path / "leak.py"
    path.write_text(source, encoding="utf-8")
    assert _httpx_hits(path) != []


# ---------------------------------------------------------------------------
# C-3 / C-5
# ---------------------------------------------------------------------------


def _package_modules(package: str) -> tuple[str, ...]:
    root = APP_ROOT / package
    return tuple(
        f"app.{package}" if path.stem == "__init__" else f"app.{package}.{path.stem}"
        for path in sorted(root.glob("*.py"))
    )


@pytest.mark.parametrize("package", NO_SECTORS_PACKAGES)
def test_other_packages_never_reach_sectors(package: str) -> None:
    roots = _package_modules(package)
    assert roots, package
    assert offenders(reachable_app_modules(roots), "app.sectors") == []


@pytest.mark.skipif(module_path(ROUTER) is None, reason="app.api.sectors lands in wave 3")
def test_router_direct_imports() -> None:  # pragma: no cover - activates in wave 3
    path = module_path(ROUTER)
    assert path is not None
    direct = imported_modules(path, ROUTER)
    for forbidden in ROUTER_FORBIDDEN:
        assert offenders(direct, forbidden) == [], forbidden


# ---------------------------------------------------------------------------
# C-17: no score / rating vocabulary
# ---------------------------------------------------------------------------

FORBIDDEN_WORDS = frozenset({"score", "scores", "rating", "ratings"})
FORBIDDEN_NAMES = frozenset(
    {"AdviceCard", "matched_rules", "direction_weights", "ACTION_DIRECTION"}
)


def _words(name: str) -> set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return {word.lower() for word in re.split(r"[^A-Za-z0-9]+", spaced) if word}


def _code_names(path: Path) -> set[str]:
    """Identifiers, attributes, aliases, keywords and non-docstring strings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_nodes(tree)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.split(".")[-1])
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                names.add(node.value)
    return names


def _vocabulary_hits(path: Path) -> list[str]:
    hits: list[str] = []
    for name in _code_names(path):
        if name in FORBIDDEN_NAMES or _words(name) & FORBIDDEN_WORDS:
            hits.append(name)
    return sorted(hits)


def test_no_score_or_rating_vocabulary_in_sectors() -> None:
    for path in sorted(SECTORS_ROOT.glob("*.py")):
        assert _vocabulary_hits(path) == [], path.name


@pytest.mark.parametrize(
    "source",
    [
        "sector_score = 1\n",
        "def rating(): pass\n",
        "class MomentumScore: pass\n",
        "x = row['matched_rules']\n",
        "from app.advice.engine import AdviceCard\n",
        "f(scores=[1])\n",
    ],
)
def test_vocabulary_scan_has_teeth(tmp_path: Path, source: str) -> None:
    path = tmp_path / "leak.py"
    path.write_text(source, encoding="utf-8")
    assert _vocabulary_hits(path) != []


def test_vocabulary_scan_ignores_ordinary_words() -> None:
    assert not _words("operating_generating_rank_scope") & FORBIDDEN_WORDS


# ---------------------------------------------------------------------------
# T-17: C-24 no bypass switch
# ---------------------------------------------------------------------------

NO_CONFIG_FILES = (
    APP_ROOT / "sectors" / "gate.py",
    APP_ROOT / "sectors" / "coverage.py",
    APP_ROOT / "backtest" / "sector_eval.py",
)
FORBIDDEN_IMPORTS = ("os", "dotenv", "configparser", "tomllib", "yaml", "app.settings")


def _config_hits(path: Path, *, forbid_sqlite: bool) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    banned = (*FORBIDDEN_IMPORTS, *(("sqlite3",) if forbid_sqlite else ()))

    def banned_module(name: str) -> bool:
        return any(name == b or name.startswith(f"{b}.") for b in banned)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += [alias.name for alias in node.names if banned_module(alias.name)]
        elif isinstance(node, ast.ImportFrom) and node.module and banned_module(node.module):
            hits.append(node.module)
        elif isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
            hits.append(node.attr)
        elif isinstance(node, ast.Name) and node.id in {"environ", "getenv"}:
            hits.append(node.id)
    return hits


def test_gate_and_coverage_read_no_environment_or_configuration() -> None:
    scanned = 0
    for path in NO_CONFIG_FILES:
        if not path.exists():  # sector_eval.py lands in wave 2
            continue
        scanned += 1
        assert _config_hits(path, forbid_sqlite=path.name == "gate.py") == [], path.name
    assert scanned >= 2


@pytest.mark.parametrize(
    "source",
    [
        "import os\nX = os.environ.get('X')\n",
        "from os import getenv\n",
        "import yaml\n",
        "from app.settings.store import SettingsStore\n",
        "import sqlite3\n",
        "import tomllib\n",
    ],
)
def test_config_scan_has_teeth(tmp_path: Path, source: str) -> None:
    path = tmp_path / "gate.py"
    path.write_text(source, encoding="utf-8")
    assert _config_hits(path, forbid_sqlite=True) != []


# ---------------------------------------------------------------------------
# T-17: C-20 gate_status is composed in gate.py only
# ---------------------------------------------------------------------------

GATE_FILE = APP_ROOT / "sectors" / "gate.py"


def _gate_status_assignments(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines: list[int] = []

    def is_target(target: ast.AST) -> bool:
        if isinstance(target, ast.Name):
            return target.id == "gate_status"
        if isinstance(target, ast.Attribute):
            return target.attr == "gate_status"
        if isinstance(target, ast.Subscript):
            key = target.slice
            return isinstance(key, ast.Constant) and key.value == "gate_status"
        if isinstance(target, ast.Tuple | ast.List):
            return any(is_target(element) for element in target.elts)
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(is_target(t) for t in node.targets):
            lines.append(node.lineno)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign) and node.value is not None:
            if is_target(node.target):
                lines.append(node.lineno)
        elif isinstance(node, ast.Dict):
            if any(isinstance(k, ast.Constant) and k.value == "gate_status" for k in node.keys):
                lines.append(node.lineno)
        elif isinstance(node, ast.keyword) and node.arg == "gate_status":
            lines.append(node.lineno)
        elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setattr":
            args = node.args
            if (
                len(args) >= 2
                and isinstance(args[1], ast.Constant)
                and args[1].value == "gate_status"
            ):
                lines.append(node.lineno)
    return lines


def test_gate_status_is_assigned_only_in_gate_py() -> None:
    offenders_found = {
        str(path.relative_to(APP_ROOT)): hits
        for path in APP_ROOT.rglob("*.py")
        if path != GATE_FILE and (hits := _gate_status_assignments(path))
    }
    assert offenders_found == {}
    assert _gate_status_assignments(GATE_FILE) != []


@pytest.mark.parametrize(
    "source",
    [
        "payload = {'gate_status': 'passed'}\n",
        "Response(gate_status='passed')\n",
        "row.gate_status = 'failed'\n",
        "gate_status: str = 'passed'\n",
        "data['gate_status'] = 'passed'\n",
        "setattr(row, 'gate_status', 'passed')\n",
    ],
)
def test_gate_status_scan_has_teeth(tmp_path: Path, source: str) -> None:
    path = tmp_path / "leak.py"
    path.write_text(source, encoding="utf-8")
    assert _gate_status_assignments(path) != []
