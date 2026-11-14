"""Forbidden hindsight sources (ADR-0030 D-3 point 5, D-9 S-5): text scan plus import graph.

``app/forecast/**`` and ``app/outlook/**`` (and ``app/data/session_calendar.py``,
the core's one ``app/data`` module) never name ``price_bars_cache``,
``dividend_events`` or ``_hindsight_view`` -- in code, strings or comments --
and neither import nor reach ``app.demo``, ``app.backtest`` or ``app.research``.
Every scan has a teeth test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.import_graph import APP_ROOT, imported_modules, offenders, reachable_app_modules

FORBIDDEN_NAMES = ("price_bars_cache", "dividend_events", "_hindsight_view")
FORBIDDEN_PACKAGES = ("app.demo", "app.backtest", "app.research")

CORE_FILES = sorted(
    [
        *(APP_ROOT / "forecast").rglob("*.py"),
        *(APP_ROOT / "outlook").rglob("*.py"),
        APP_ROOT / "data" / "session_calendar.py",
    ]
)


def _module(path: Path) -> str:
    parts = list(path.relative_to(APP_ROOT.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _named(text: str) -> list[str]:
    return [name for name in FORBIDDEN_NAMES if name in text]


def _imports_of(source: str, module: str, tmp_path: Path) -> set[str]:
    path = tmp_path / "probe.py"
    path.write_text(source, encoding="utf-8")
    return imported_modules(path, module)


def _dynamic_imports(source: str) -> list[str]:
    """``__import__`` / ``importlib`` uses: ways around an ``import`` statement scan."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id == "__import__":
            found.append("__import__")
        elif isinstance(node, ast.Import | ast.ImportFrom):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            found += [n for n in names if n and n.split(".")[0] == "importlib"]
    return found


def test_the_scan_covers_the_new_core_modules() -> None:
    names = {path.relative_to(APP_ROOT).as_posix() for path in CORE_FILES}
    assert {"forecast/store.py", "forecast/schema.py", "forecast/canonical.py"} <= names
    assert "data/session_calendar.py" in names
    assert "outlook/missing.py" in names


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda p: p.relative_to(APP_ROOT).as_posix())
def test_no_forbidden_identifier_appears(path: Path) -> None:
    assert _named(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda p: p.relative_to(APP_ROOT).as_posix())
def test_no_forbidden_package_is_imported(path: Path) -> None:
    imported = imported_modules(path, _module(path))
    assert [m for f in FORBIDDEN_PACKAGES for m in offenders(imported, f)] == []
    assert _dynamic_imports(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("package", FORBIDDEN_PACKAGES)
def test_no_forbidden_package_is_reachable(package: str) -> None:
    reachable = reachable_app_modules(tuple(_module(path) for path in CORE_FILES))
    assert offenders(reachable, package) == []


@pytest.mark.parametrize(
    "text",
    [
        "SELECT * FROM price_bars_cache",
        "# see dividend_events\n",
        "view = store._hindsight_view()",
    ],
)
def test_the_identifier_scan_has_teeth(text: str) -> None:
    assert _named(text) != []


@pytest.mark.parametrize(
    "source",
    [
        "from app.backtest import engine\n",
        "import app.demo.seed\n",
        "from ..research import notes\n",  # relative, from app.forecast.probe
        "from app import research\n",
    ],
)
def test_the_import_scan_has_teeth(source: str, tmp_path: Path) -> None:
    imported = _imports_of(source, "app.forecast.probe", tmp_path)
    assert [m for f in FORBIDDEN_PACKAGES for m in offenders(imported, f)] != []


@pytest.mark.parametrize(
    "source", ["mod = __import__('app.demo')\n", "import importlib\n", "from importlib import x\n"]
)
def test_the_dynamic_import_scan_has_teeth(source: str) -> None:
    assert _dynamic_imports(source) != []


def test_the_reachability_scan_has_teeth() -> None:
    # The scheduler reaches the data layer that owns the cache table.
    assert offenders(reachable_app_modules(("app.scheduler",)), "app.data") != []
