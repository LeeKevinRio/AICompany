"""Structural boundaries of the B1 and B2 modules (ADR-0027 D-1; ADR-0029 D-1).

B2 cells (``app/dirdef/``, ``definitions.py``, ``claims.py``, ``volatility.py``,
``basket.py``) are in the second half: FL-78 (a)-(d), (g), the
``object.__setattr__`` ban of (h), (i), the call-site part of (k), (l3), the
AST part of (e), FL-55, FL-75 (i) single definition, FL-56 import graph and the
B2D-3c/3d call-site and coverage-source cells, risk R-2 (no ``1 - x``). Import
scans resolve relative imports to absolute names and match ``app.dirdef`` as a
package, not a prefix (B2D-4b, qa M-3); caller scans see attribute calls too.

* single definitions: ``threshold_inputs`` / ``labeled_snapshot_violations``
  only in ``band.py`` (FL-72 (n)); ``ThresholdViolation`` /
  ``THRESHOLD_VIOLATION_ORDER`` only in ``errors.py`` (C1);
* import rules: ``errors.py`` and ``ops_alert/model.py`` import the standard
  library only; ``band.py`` the standard library plus exactly one
  ``app.forecast.*`` import,
  ``from app.forecast.errors import THRESHOLD_VIOLATION_ORDER, ThresholdViolation``,
  no alias, no re-export (C2), and otherwise only ``app.dirdef(.*)`` types
  (FL-72 (n), N-131; qa M-4); ``outlook/missing.py`` the standard library and
  ``pydantic``; ``band.py`` reaches neither ``scoring`` nor ``volatility``;
  ``app.outlook`` never reaches ``app.forecast``; ``app/forecast/**`` never
  names the DB path resolvers;
* ADR-0029 OA-1 / OA-2: ``app.forecast`` takes only ``app.ops_alert.model``;
  the step modules take nothing from ``app.ops_alert``; ``app.ops_alert`` and
  ``app.alerts`` stay apart; ``app.ops_alert`` reaches none of ``app.forecast``,
  ``app.settings``, ``app.api``.

Every scan has a teeth test fed with a source string that breaks the rule.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

from app.advice.loader import BANNED_PHRASES
from tests.import_graph import (
    APP_ROOT,
    imported_modules,
    offenders,
    reachable_app_modules,
)

FORECAST_ROOT = APP_ROOT / "forecast"
OUTLOOK_ROOT = APP_ROOT / "outlook"
OPS_ALERT_ROOT = APP_ROOT / "ops_alert"
DIRDEF_ROOT = APP_ROOT / "dirdef"

#: The one ``app.*`` import band.py may have (tech-architect C2).
BAND_APP_MODULE = "app.forecast.errors"
BAND_APP_NAMES = frozenset({"THRESHOLD_VIOLATION_ORDER", "ThresholdViolation"})

#: ADR-0029 D-1: modules that may not import anything from app.ops_alert.
STEP_MODULES = ("settlement", "scoring", "correction", "audit", "validation", "store")
#: What app.forecast may not import at all (ADR-0029 D-1, OA-1).
FORECAST_FORBIDDEN = ("httpx", "app.alerts", "app.push_channels")


def _top_level(module: str) -> str:
    return module.split(".")[0]


def _is_stdlib(module: str) -> bool:
    return _top_level(module) in sys.stdlib_module_names and _top_level(module) != "importlib"


def _import_violations(source: str, *, allowed_third_party: frozenset[str]) -> list[str]:
    """Imports outside the standard library (plus ``allowed_third_party``).

    Relative imports, ``importlib`` and ``__import__`` count as violations: they
    are the ways around a scan of ``import`` statements.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.append(f"relative import level {node.level}")
                continue
            modules = [node.module or ""]
        elif isinstance(node, ast.Name) and node.id == "__import__":
            found.append("__import__")
            continue
        else:
            continue
        for module in modules:
            if not (_is_stdlib(module) or _top_level(module) in allowed_third_party):
                found.append(module)
    return found


def _in_dirdef(module: str) -> bool:
    """``app.dirdef`` or one of its submodules (not a prefix match: ``app.dirdefx`` is not)."""
    return module == "app.dirdef" or module.startswith("app.dirdef.")


def _in_forecast(module: str) -> bool:
    return module == "app.forecast" or module.startswith("app.forecast.")


def _band_import_violations(source: str) -> list[str]:
    """band.py's rule (FL-72 (n), N-131): stdlib; exactly one ``app.forecast.*`` import,
    the C2 line with its two names and no alias; other ``app.*`` only ``app.dirdef(.*)``;
    no relative import and no re-export."""
    tree = ast.parse(source)
    found: list[str] = []
    forecast_imports = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                found.append(f"relative import level {node.level}")
                continue
            module = node.module or ""
            if _top_level(module) != "app":
                continue
            if _in_forecast(module):
                forecast_imports += 1
                names = {alias.name for alias in node.names}
                if module != BAND_APP_MODULE or names != BAND_APP_NAMES:
                    found.append(f"app.forecast import {module} {sorted(names)}")
                if any(alias.asname is not None for alias in node.names):
                    found.append("aliased import")
            elif not _in_dirdef(module):
                found.append(f"app import {module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _top_level(alias.name) != "app":
                    continue
                if _in_forecast(alias.name):
                    forecast_imports += 1
                    found.append("plain app.forecast import")
                elif not _in_dirdef(alias.name):
                    found.append(f"app import {alias.name}")
        elif isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                found.append("__all__")
    if forecast_imports != 1:
        found.append(f"{forecast_imports} app.forecast imports")
    rest = "\n".join(
        ast.unparse(node)
        for node in ast.walk(tree)
        if (isinstance(node, ast.Import) and all(_top_level(a.name) != "app" for a in node.names))
        or (
            isinstance(node, ast.ImportFrom)
            and not node.level
            and _top_level(node.module or "") != "app"
        )
    )
    found.extend(_import_violations(rest, allowed_third_party=frozenset()))
    return found


def _definitions(source: str, name: str) -> int:
    """How many times ``source`` binds ``name`` at any level (assign or ``type``)."""
    count = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            targets = [node.target]
        elif isinstance(node, ast.TypeAlias):
            targets = [node.name]
        elif isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            count += node.name == name
            continue
        else:
            continue
        count += sum(isinstance(t, ast.Name) and t.id == name for t in targets)
    return count


def _app_sources() -> dict[str, str]:
    return {
        path.relative_to(APP_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(APP_ROOT.rglob("*.py"))
    }


def _module_name(path: Path) -> str:
    relative = path.relative_to(APP_ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _modules_under(root: Path) -> tuple[str, ...]:
    return tuple(_module_name(path) for path in sorted(root.rglob("*.py")))


def _alert_import_violations(names: set[str]) -> list[str]:
    """OA-1: of app.ops_alert only the model; nothing from the forbidden list."""
    bad = [
        name
        for name in names
        if name.startswith("app.ops_alert")
        and name not in {"app.ops_alert", "app.ops_alert.model"}
        and not name.startswith("app.ops_alert.model.")
    ]
    bad += [name for name in names for f in FORECAST_FORBIDDEN if offenders({name}, f)]
    return sorted(bad)


def _imports_of_source(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


# --- Single definitions ----------------------------------------------------------------


def test_the_scanned_packages_hold_exactly_the_b1_and_b2_modules() -> None:
    # A new module in these packages must come with its own boundary rules.
    holders = sorted(
        path.relative_to(APP_ROOT).as_posix()
        for root in (FORECAST_ROOT, OUTLOOK_ROOT, OPS_ALERT_ROOT, DIRDEF_ROOT)
        for path in root.rglob("*.py")
    )
    assert holders == [
        "dirdef/__init__.py",
        "dirdef/definition.py",
        "dirdef/guard.py",
        "dirdef/hashing.py",
        "dirdef/registry.py",
        "dirdef/rules.py",
        "dirdef/strings.py",
        "forecast/__init__.py",
        "forecast/band.py",
        "forecast/claims.py",
        "forecast/definitions.py",
        "forecast/errors.py",
        "ops_alert/__init__.py",
        "ops_alert/model.py",
        "outlook/__init__.py",
        "outlook/basket.py",
        "outlook/missing.py",
        "outlook/volatility.py",
    ]


@pytest.mark.parametrize("name", ["threshold_inputs", "labeled_snapshot_violations"])
def test_threshold_functions_are_defined_once_in_band(name: str) -> None:
    holders = {path: n for path, text in _app_sources().items() if (n := _definitions(text, name))}
    assert holders == {"forecast/band.py": 1}


@pytest.mark.parametrize("name", sorted(BAND_APP_NAMES))
def test_the_violation_list_is_defined_once_in_errors(name: str) -> None:
    holders = {path: n for path, text in _app_sources().items() if (n := _definitions(text, name))}
    assert holders == {"forecast/errors.py": 1}


@pytest.mark.parametrize(
    "source",
    [
        pytest.param('ThresholdViolation = Literal["k_h_missing"]', id="assign"),
        pytest.param("THRESHOLD_VIOLATION_ORDER: tuple[str, ...] = ()", id="ann-assign"),
        pytest.param("THRESHOLD_VIOLATION_ORDER += ('extra',)", id="aug-assign"),
        pytest.param('type ThresholdViolation = Literal["k_h_missing"]', id="type-statement"),
    ],
)
def test_the_definition_scan_has_teeth(source: str) -> None:
    assert sum(_definitions(source, name) for name in BAND_APP_NAMES) == 1


# --- Import rules ------------------------------------------------------------------------


@pytest.mark.parametrize("path", [FORECAST_ROOT / "errors.py", OPS_ALERT_ROOT / "model.py"])
def test_leaf_modules_import_the_standard_library_only(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    assert _import_violations(source, allowed_third_party=frozenset()) == []


def test_missing_imports_the_standard_library_and_pydantic_only() -> None:
    source = (OUTLOOK_ROOT / "missing.py").read_text(encoding="utf-8")
    assert _import_violations(source, allowed_third_party=frozenset({"pydantic"})) == []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("from . import band", id="relative"),
        pytest.param("import importlib", id="importlib"),
        pytest.param("m = __import__('app.forecast.band')", id="dunder-import"),
        pytest.param("import httpx", id="third-party"),
        pytest.param("from app.forecast import errors", id="app-import"),
    ],
)
def test_the_standard_library_scan_has_teeth(source: str) -> None:
    assert _import_violations(source, allowed_third_party=frozenset({"pydantic"})) != []


def test_band_imports_the_standard_library_and_the_violation_list_only() -> None:
    source = (FORECAST_ROOT / "band.py").read_text(encoding="utf-8")
    assert _band_import_violations(source) == []


C2_LINE = "from app.forecast.errors import THRESHOLD_VIOLATION_ORDER, ThresholdViolation\n"


@pytest.mark.parametrize(
    ("source", "complies"),
    [
        pytest.param(
            "from app.forecast.errors import THRESHOLD_VIOLATION_ORDER, ThresholdViolation, "
            "exception_class_name\n",
            False,
            id="one-more-name",
        ),
        # FL-72 (n) / N-131: dirdef types are allowed beside the C2 line.
        pytest.param(
            C2_LINE + "if TYPE_CHECKING:\n    from app.dirdef import DirectionDefinition\n",
            True,
            id="type-checking-dirdef-import",
        ),
        pytest.param(
            C2_LINE + "from app.dirdef.definition import DirectionDefinition\n",
            True,
            id="dirdef-submodule-import",
        ),
        pytest.param(
            C2_LINE + "from app.outlook.volatility import sigma_d\n", False, id="non-dirdef-app"
        ),
        pytest.param(C2_LINE + "from app.dirdefx import y\n", False, id="dirdef-lookalike"),
        pytest.param(C2_LINE + "import app.outlook.volatility\n", False, id="plain-non-dirdef"),
        pytest.param(C2_LINE + "from . import errors\n", False, id="relative"),
        pytest.param(C2_LINE + "from app.forecast import claims\n", False, id="second-forecast"),
        pytest.param(C2_LINE + "import app.forecast.errors\n", False, id="plain-forecast"),
        pytest.param(
            "from app.forecast.errors import (\n"
            "    THRESHOLD_VIOLATION_ORDER as THRESHOLD_VIOLATION_ORDER,\n"
            "    ThresholdViolation,\n)\n",
            False,
            id="x-as-x",
        ),
        pytest.param(C2_LINE + '__all__ = ["ThresholdViolation"]\n', False, id="dunder-all"),
        pytest.param(C2_LINE + "import httpx\n", False, id="httpx"),
        pytest.param(
            C2_LINE + "from apscheduler.schedulers.blocking import BlockingScheduler\n",
            False,
            id="apscheduler",
        ),
        # A top-level name that merely starts with "app" is not ``app``; this is
        # the cell a ``startswith("app")`` filter would let through.
        pytest.param(C2_LINE + "from appdirs import user_data_dir\n", False, id="appdirs"),
        pytest.param("import math\n", False, id="line-missing"),
        pytest.param("import math\nimport struct\n" + C2_LINE, True, id="compliant"),
    ],
)
def test_the_band_import_rule_has_teeth(source: str, complies: bool) -> None:
    assert (_band_import_violations(source) == []) is complies


@pytest.mark.parametrize("module", ["app.forecast.scoring", "app.outlook.volatility"])
def test_band_reaches_neither_scoring_nor_volatility(module: str) -> None:
    assert offenders(reachable_app_modules(("app.forecast.band",)), module) == []


@pytest.mark.parametrize("name", ["resolve_db_path", "resolve_market_db_path"])
def test_forecast_does_not_mention_the_db_path_resolvers(name: str) -> None:
    holders = [
        path
        for path, text in _app_sources().items()
        if path.startswith("forecast/") and name in text
    ]
    assert holders == []


def test_the_db_path_scan_has_teeth() -> None:
    sources = {"forecast/store.py": "from app.data.db import resolve_db_path\n"}
    holders = [p for p, text in sources.items() if "resolve_db_path" in text]
    assert holders == ["forecast/store.py"]


def test_outlook_does_not_reach_forecast() -> None:
    reachable = reachable_app_modules(_modules_under(OUTLOOK_ROOT))
    assert offenders(reachable, "app.forecast") == []


def test_the_outlook_scan_has_teeth(tmp_path: Path) -> None:
    probe = tmp_path / "inputs.py"
    probe.write_text("from ..forecast import band\n", encoding="utf-8")
    assert offenders(imported_modules(probe, "app.outlook.inputs"), "app.forecast") != []


# --- ADR-0029 OA-1 / OA-2 ------------------------------------------------------------------


def test_forecast_takes_only_the_alert_model() -> None:
    for module in _modules_under(FORECAST_ROOT):
        path = APP_ROOT.parent / Path(*module.split("."))
        source_path = path / "__init__.py" if path.is_dir() else path.with_suffix(".py")
        assert _alert_import_violations(imported_modules(source_path, module)) == []
        source = source_path.read_text(encoding="utf-8")
        assert _alert_import_violations(_imports_of_source(source)) == []


@pytest.mark.parametrize("name", STEP_MODULES)
def test_step_modules_do_not_import_the_alert_package(name: str) -> None:
    # Not written yet in B1; the cell turns live the moment the module exists.
    path = FORECAST_ROOT / f"{name}.py"
    if not path.is_file():
        return
    names = _imports_of_source(path.read_text(encoding="utf-8"))
    assert [n for n in names if offenders({n}, "app.ops_alert")] == []
    assert _alert_import_violations(names) == []


def test_the_alert_import_scan_has_teeth() -> None:
    assert _alert_import_violations(_imports_of_source("from app.ops_alert.sink import S")) != []
    assert _alert_import_violations(_imports_of_source("import httpx")) == ["httpx"]
    assert _alert_import_violations(_imports_of_source("from app.alerts import notify")) != []
    assert (
        _alert_import_violations(_imports_of_source("from app.ops_alert.model import OpsAlert"))
        == []
    )


@pytest.mark.parametrize("package", ["app.forecast", "app.alerts", "app.settings", "app.api"])
def test_ops_alert_reaches_none_of_the_forbidden_packages(package: str) -> None:
    reachable = reachable_app_modules(_modules_under(OPS_ALERT_ROOT))
    assert offenders(reachable, package) == []


def test_alerts_do_not_reach_ops_alert() -> None:
    reachable = reachable_app_modules(_modules_under(APP_ROOT / "alerts"))
    assert offenders(reachable, "app.ops_alert") == []


# --- B2: app/dirdef (FL-78 (a)) ----------------------------------------------------------

#: Names that read files, the environment or the clock (FL-78 (a); D-1 dirdef row).
IO_NAMES = frozenset({"open", "getenv", "environ"})
IO_ATTRIBUTES = frozenset(
    {"read_text", "read_bytes", "resources", "environ", "getenv", "now", "today", "utcnow"}
)
IO_MODULES = frozenset({"importlib", "os", "sqlite3", "time", "pathlib", "io"})
#: Registry names; only their definition site and definitions.py may mention them.
REGISTRY_NAMES = ("PUBLISHED_DIRECTION_DEFINITIONS", "PUBLISHED_RULESETS")


def _path_module(path: str) -> tuple[str, bool]:
    """``"forecast/x.py"`` -> (``"app.forecast.x"``, is_package)."""
    parts = ["app", *path.removesuffix(".py").split("/")]
    if parts[-1] == "__init__":
        return ".".join(parts[:-1]), True
    return ".".join(parts), False


def _resolve(node: ast.ImportFrom, module: str, is_package: bool) -> str:
    """The absolute base of ``node``; relative levels resolved like ``tests/import_graph.py``."""
    base = node.module or ""
    if not node.level:
        return base
    parts = module.split(".")
    anchor = parts if is_package else parts[:-1]
    prefix = anchor[: len(anchor) - node.level + 1]
    return ".".join([*prefix, base]) if base else ".".join(prefix)


def _import_bases(source: str, module: str, is_package: bool = False) -> list[str]:
    """Absolute module names imported (``import`` names, ``from`` bases)."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append(_resolve(node, module, is_package))
    return found


def _imported_names(source: str, module: str, is_package: bool = False) -> set[str]:
    """Bases plus ``base.name`` for each ``from`` alias (so ``from app import dirdef`` counts)."""
    found = set(_import_bases(source, module, is_package))
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            base = _resolve(node, module, is_package)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def _dirdef_import_violations(
    source: str, module: str = "app.dirdef.probe", *, is_package: bool = False
) -> list[str]:
    """Standard library, pydantic, yaml, and ``app.dirdef(.*)`` only (B2D-4b).

    Relative imports are resolved against ``module`` (a package when
    ``is_package``) first, so ``from .rules`` inside the package is allowed and
    ``from ..forecast`` is not. Callers scanning a real file pass its module name:
    the default would resolve a file outside the package as if it were inside.
    """
    found: list[str] = []
    for name in _import_bases(source, module, is_package):
        if _top_level(name) == "app":
            if not _in_dirdef(name):
                found.append(name)
        elif not (_is_stdlib(name) or _top_level(name) in {"pydantic", "yaml"}):
            found.append(name)
    return found


def _io_violations(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id in IO_NAMES:
            found.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in IO_ATTRIBUTES:
            found.append(node.attr)
        elif isinstance(node, ast.Import):
            found += [a.name for a in node.names if _top_level(a.name) in IO_MODULES]
        elif isinstance(node, ast.ImportFrom) and _top_level(node.module or "") in IO_MODULES:
            found.append(node.module or "")
    return found


def _sources_under(root: Path) -> dict[str, str]:
    return {
        path.relative_to(APP_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*.py"))
    }


@pytest.mark.parametrize("path", sorted(DIRDEF_ROOT.rglob("*.py")), ids=lambda p: p.name)
def test_dirdef_imports_stdlib_pydantic_yaml_and_itself_only(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    module = _module_name(path)
    is_package = path.name == "__init__.py"
    assert _dirdef_import_violations(source, module, is_package=is_package) == []


def test_dirdef_reaches_no_other_app_package() -> None:
    reachable = reachable_app_modules(_modules_under(DIRDEF_ROOT))
    assert [m for m in reachable if not _in_dirdef(m)] == []


def test_the_dirdef_membership_test_is_not_a_prefix_match() -> None:
    assert _in_dirdef("app.dirdef") and _in_dirdef("app.dirdef.rules")
    assert not _in_dirdef("app.dirdefx") and not _in_dirdef("app.dirdef_x")


@pytest.mark.parametrize("path", sorted(DIRDEF_ROOT.rglob("*.py")), ids=lambda p: p.name)
def test_dirdef_does_no_file_environment_or_clock_access(path: Path) -> None:
    assert _io_violations(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("source", "complies"),
    [
        pytest.param("from app.forecast import band\n", False, id="app-forecast"),
        pytest.param("from .rules import x\n", True, id="relative-inside"),
        pytest.param("from ..forecast import band\n", False, id="relative-outside"),
        pytest.param("from .. import advice\n", False, id="relative-app"),
        pytest.param("import httpx\n", False, id="third-party"),
        pytest.param("from app.dirdefx import y\n", False, id="prefix-lookalike"),
        pytest.param("import yaml\nfrom pydantic import BaseModel\n", True, id="allowed"),
        pytest.param("from app.dirdef.guard import GuardedModel\n", True, id="own-package"),
    ],
)
def test_the_dirdef_import_rule_has_teeth(source: str, complies: bool) -> None:
    assert (_dirdef_import_violations(source) == []) is complies


def test_a_relative_import_outside_dirdef_resolves_to_its_own_package() -> None:
    # qa F-1: from app.outlook.volatility, ``.basket`` is app.outlook.basket, not dirdef.
    source = "from .basket import x\n"
    assert _dirdef_import_violations(source, "app.outlook.volatility") == ["app.outlook.basket"]
    assert _dirdef_import_violations(source, "app.forecast.claims") == ["app.forecast.basket"]


def test_a_package_file_resolves_relative_imports_from_itself() -> None:
    # qa F-6: in app/dirdef/__init__.py, ``.rules`` is app.dirdef.rules.
    source = "from .rules import load_ruleset\n"
    assert _dirdef_import_violations(source, "app.dirdef", is_package=True) == []
    assert _dirdef_import_violations(source, "app.dirdef", is_package=False) == ["app.rules"]


@pytest.mark.parametrize(
    "source",
    [
        "open('x')",
        "p.read_text()",
        "p.read_bytes()",
        "import importlib.resources",
        "from importlib import resources",
        "os.environ['X']",
        "datetime.now()",
        "import sqlite3",
    ],
)
def test_the_dirdef_io_scan_has_teeth(source: str) -> None:
    assert _io_violations(source) != []


# --- FL-78 (b)(c)(g)(l3): who imports dirdef, single definitions -------------------------


def _imports_dirdef(source: str, path: str) -> bool:
    module, is_package = _path_module(path)
    return any(_in_dirdef(name) for name in _imported_names(source, module, is_package))


def _dirdef_importers_outside(sources: dict[str, str]) -> set[str]:
    """Files outside forecast/, outlook/ and dirdef/ that import app.dirdef (FL-78 (b))."""
    return {
        path
        for path, text in sources.items()
        if _imports_dirdef(text, path) and not path.startswith(("forecast/", "outlook/", "dirdef/"))
    }


def test_only_forecast_and_outlook_import_dirdef() -> None:
    sources = _app_sources()
    assert {p for p, t in sources.items() if _imports_dirdef(t, p)}  # the scan sees importers
    assert _dirdef_importers_outside(sources) == set()


@pytest.mark.parametrize(
    ("path", "source", "caught"),
    [
        pytest.param("api/x.py", "from app.dirdef.rules import load_ruleset\n", True, id="abs"),
        pytest.param("api/x.py", "from ..dirdef import rules\n", True, id="relative"),
        pytest.param("sectors/__init__.py", "from ..dirdef import rules\n", True, id="pkg-rel"),
        pytest.param("api/x.py", "from app import dirdef\n", True, id="from-app"),
        pytest.param("api/x.py", "import app.dirdef.definition\n", True, id="plain"),
        pytest.param("api/x.py", "import app.dirdefx\n", False, id="lookalike"),
        pytest.param("outlook/x.py", "from app.dirdef import rules\n", False, id="allowed"),
    ],
)
def test_the_dirdef_importer_scan_has_teeth(path: str, source: str, caught: bool) -> None:
    assert (_dirdef_importers_outside({path: source}) == {path}) is caught


@pytest.mark.parametrize("name", REGISTRY_NAMES)
def test_the_registries_are_named_only_where_defined_and_in_definitions(name: str) -> None:
    holders = {path for path, text in _app_sources().items() if name in text}
    assert holders == {"dirdef/registry.py", "forecast/definitions.py"}


@pytest.mark.parametrize(
    ("name", "home"),
    [
        ("DirectionDefinition", "dirdef/definition.py"),
        ("OUTLOOK_RULE_FIELDS", "dirdef/rules.py"),
        ("PUBLISHED_DIRECTION_DEFINITIONS", "dirdef/registry.py"),
        ("PUBLISHED_RULESETS", "dirdef/registry.py"),
        ("string_values", "dirdef/strings.py"),
        ("definition_logic_sha256", "dirdef/definition.py"),
        ("definition_sha256", "dirdef/definition.py"),
        ("DEFINITION_NON_LOGIC_FIELDS", "dirdef/definition.py"),
        ("rules_logic_sha256", "dirdef/rules.py"),
        ("RULE_TEXT_FIELDS", "dirdef/rules.py"),
        ("load_ruleset", "dirdef/rules.py"),
        ("sigma_d", "outlook/volatility.py"),
        ("SigmaEstimate", "outlook/volatility.py"),
        ("basket_log_returns", "outlook/basket.py"),
        ("basket_hold_ratio", "outlook/basket.py"),
        ("claim_id", "forecast/claims.py"),
    ],
)
def test_b2_names_are_defined_once(name: str, home: str) -> None:
    # FL-78 (g), (l3); FL-55 (sigma_d); FL-75 (i) (SigmaEstimate). Functions count
    # ``def`` only (band.py has a local ``sigma_d`` value and registry.py a
    # ``definition_logic_sha256`` field); types and constants count every binding.
    count = _function_definitions if name[0].islower() else _definitions
    holders = {path: n for path, text in _app_sources().items() if (n := count(text, name))}
    assert holders == {home: 1}


def _function_definitions(source: str, name: str) -> int:
    return sum(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
        for node in ast.walk(ast.parse(source))
    )


def test_the_function_definition_scan_has_teeth() -> None:
    assert _function_definitions("def sigma_d(x):\n    pass\nsigma_d = 1\n", "sigma_d") == 1


def _is_call_to(node: ast.AST, name: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == name) or (
        isinstance(func, ast.Attribute) and func.attr == name
    )


def _callers(name: str, sources: dict[str, str]) -> set[str]:
    """Files calling ``name`` directly or as an attribute (``mod.name(...)``)."""
    return {
        path
        for path, text in sources.items()
        if any(_is_call_to(node, name) for node in ast.walk(ast.parse(text)))
    }


def test_both_scans_enumerate_through_the_one_function() -> None:
    # FL-78 (l3): the rule set validator and definitions.py both call string_values.
    assert _callers("string_values", _app_sources()) == {
        "dirdef/rules.py",
        "forecast/definitions.py",
    }
    rules_tree = ast.parse((DIRDEF_ROOT / "rules.py").read_text(encoding="utf-8"))
    scan = next(
        node
        for node in ast.walk(rules_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_scan_banned_phrases"
    )
    assert any(_is_call_to(n, "string_values") for n in ast.walk(scan))
    validator = next(
        node
        for node in ast.walk(rules_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_load_guards"
    )
    assert any(_is_call_to(n, "_scan_banned_phrases") for n in ast.walk(validator))


def test_the_caller_scan_has_teeth() -> None:
    sources = {
        "a.py": "string_values(x)\n",
        "b.py": "strings.string_values(x)\n",
        "c.py": "app.dirdef.strings.string_values(x)\n",
        "d.py": "other(string_values)\n",
        "e.py": "string_values_x(y)\n",
    }
    assert _callers("string_values", sources) == {"a.py", "b.py", "c.py"}


# --- FL-78 (h) object.__setattr__ ---------------------------------------------------------


def _object_setattr_uses(source: str) -> int:
    return sum(
        isinstance(node, ast.Attribute)
        and node.attr == "__setattr__"
        and isinstance(node.value, ast.Name)
        and node.value.id == "object"
        for node in ast.walk(ast.parse(source))
    )


@pytest.mark.parametrize("root", [DIRDEF_ROOT, FORECAST_ROOT, OUTLOOK_ROOT], ids=lambda r: r.name)
def test_no_object_setattr_in_dirdef_forecast_outlook(root: Path) -> None:
    assert {p: n for p, t in _sources_under(root).items() if (n := _object_setattr_uses(t))} == {}


def test_the_object_setattr_scan_has_teeth() -> None:
    assert _object_setattr_uses("object.__setattr__(self, 'x', 1)") == 1


# --- FL-78 (i)(k): banned phrase source, loader call sites, rule files ------------------


LOADER_MODULE = "app.advice.loader"


def _forecast_outlook_dirdef_sources() -> dict[str, str]:
    return {
        path: text
        for root in (FORECAST_ROOT, OUTLOOK_ROOT, DIRDEF_ROOT)
        for path, text in _sources_under(root).items()
    }


def _banned_phrase_importers(sources: dict[str, str]) -> dict[str, list[str]]:
    """Every way a file reaches ``BANNED_PHRASES``: the name imported (with its resolved
    module), the loader module imported, or ``x.BANNED_PHRASES`` read as an attribute."""
    found: dict[str, list[str]] = {}
    for path, text in sources.items():
        module, is_package = _path_module(path)
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom):
                base = _resolve(node, module, is_package)
                for alias in node.names:
                    if alias.name == "BANNED_PHRASES":
                        found.setdefault(path, []).append(base)
                    elif f"{base}.{alias.name}" == LOADER_MODULE:
                        found.setdefault(path, []).append(f"module {LOADER_MODULE}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == LOADER_MODULE:
                        found.setdefault(path, []).append(f"module {LOADER_MODULE}")
            elif isinstance(node, ast.Attribute) and node.attr == "BANNED_PHRASES":
                found.setdefault(path, []).append("attribute BANNED_PHRASES")
    return found


def test_only_definitions_imports_the_banned_phrases_from_the_advice_loader() -> None:
    assert _banned_phrase_importers(_forecast_outlook_dirdef_sources()) == {
        "forecast/definitions.py": [LOADER_MODULE]
    }


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "from app.advice import loader\nX = loader.BANNED_PHRASES\n",
            [f"module {LOADER_MODULE}", "attribute BANNED_PHRASES"],
            id="module-then-attribute",
        ),
        pytest.param(
            "import app.advice.loader\nX = app.advice.loader.BANNED_PHRASES\n",
            [f"module {LOADER_MODULE}", "attribute BANNED_PHRASES"],
            id="plain-module",
        ),
        pytest.param(
            "from ..advice.loader import BANNED_PHRASES\n", [LOADER_MODULE], id="relative"
        ),
        pytest.param(
            "from app.advice.loader import BANNED_PHRASES as P\n", [LOADER_MODULE], id="alias"
        ),
    ],
)
def test_the_banned_phrase_import_scan_has_teeth(source: str, expected: list[str]) -> None:
    found = _banned_phrase_importers({"outlook/probe.py": source})
    assert sorted(found["outlook/probe.py"]) == sorted(expected)


def test_the_loader_is_called_only_from_definitions_with_the_imported_phrases() -> None:
    assert _callers("load_ruleset", _app_sources()) == {"forecast/definitions.py"}
    tree = ast.parse((FORECAST_ROOT / "definitions.py").read_text(encoding="utf-8"))
    calls = [
        n for n in ast.walk(tree) if isinstance(n, ast.Call) and _is_call_to(n, "load_ruleset")
    ]
    assert len(calls) == 1
    keywords = {k.arg: k.value for k in calls[0].keywords}
    phrases = keywords["banned_phrases"]
    assert isinstance(phrases, ast.Name) and phrases.id == "BANNED_PHRASES"


def test_the_loader_call_site_scan_has_teeth() -> None:
    sources = {"outlook/x.py": "rules.load_ruleset(b, rules_sha256=h, banned_phrases=p)\n"}
    assert _callers("load_ruleset", sources) == {"outlook/x.py"}


def _constants_with_banned_phrases(source: str) -> list[str]:
    return [
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(phrase in node.value for phrase in BANNED_PHRASES)
    ]


@pytest.mark.parametrize("root", [DIRDEF_ROOT, OUTLOOK_ROOT], ids=lambda r: r.name)
def test_no_copy_of_a_banned_phrase_in_dirdef_or_outlook(root: Path) -> None:
    assert {
        p: c for p, t in _sources_under(root).items() if (c := _constants_with_banned_phrases(t))
    } == {}


def test_the_banned_copy_scan_has_teeth() -> None:
    assert _constants_with_banned_phrases(f"X = 'a{BANNED_PHRASES[0]}b'") != []


def test_the_rules_directory_holds_only_the_two_rule_files() -> None:
    rules_dir = OUTLOOK_ROOT / "rules"
    found = (
        {p.name for p in rules_dir.rglob("*") if p.suffix in {".yaml", ".yml"}}
        if rules_dir.exists()
        else set()
    )
    assert found <= {"h3.yaml", "h5.yaml"}
    assert found == set()  # B2: no rule file before the G-3 freeze


# --- definitions.py, claims.py, forecast/__init__.py --------------------------------------


def test_definitions_reads_no_environment_variable() -> None:
    source = (FORECAST_ROOT / "definitions.py").read_text(encoding="utf-8")
    names = {
        getattr(node, "id", None) or getattr(node, "attr", None)
        for node in ast.walk(ast.parse(source))
    }
    assert not names & {"environ", "getenv", "os"}


def test_the_getters_take_no_path() -> None:
    from app.forecast import definitions

    assert list(inspect.signature(definitions.get_definition).parameters) == ["definition_version"]
    assert list(inspect.signature(definitions.get_ruleset).parameters) == ["rules_version"]


def test_the_forecast_package_file_imports_nothing() -> None:
    source = (FORECAST_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert _imports_of_source(source) == set()


def test_claims_is_pure_for_now() -> None:
    path = FORECAST_ROOT / "claims.py"
    source = path.read_text(encoding="utf-8")
    assert _dirdef_import_violations(source, _module_name(path)) == []
    names = {getattr(n, "id", None) for n in ast.walk(ast.parse(source))}
    assert "__name__" not in names  # no ``if __name__ == "__main__"`` CLI block yet
    assert _io_violations(source) == []


# --- outlook: volatility, basket (FL-55, FL-56, FL-78 (e)) ---------------------------------


def test_volatility_imports_stdlib_and_the_dirdef_type_only() -> None:
    path = OUTLOOK_ROOT / "volatility.py"
    source = path.read_text(encoding="utf-8")
    assert _dirdef_import_violations(source, _module_name(path)) == []
    app_imports = {n for n in _imports_of_source(source) if _top_level(n) == "app"}
    assert app_imports == {"app.dirdef.definition", "app.dirdef.definition.DirectionDefinition"}


def test_basket_imports_stdlib_and_the_dirdef_type_only() -> None:
    path = OUTLOOK_ROOT / "basket.py"
    source = path.read_text(encoding="utf-8")
    assert _dirdef_import_violations(source, _module_name(path)) == []
    app_imports = {n for n in _imports_of_source(source) if _top_level(n) == "app"}
    assert app_imports == {"app.dirdef.definition", "app.dirdef.definition.DirectionDefinition"}


#: Names through which the sectors coverage threshold could be read (B2D-3c).
COVERAGE_NAMES = frozenset({"CoverageRules", "sector_coverage_threshold"})


def _coverage_reads(source: str) -> list[str]:
    return [
        name
        for node in ast.walk(ast.parse(source))
        if (name := getattr(node, "id", None) or getattr(node, "attr", None)) in COVERAGE_NAMES
    ]


@pytest.mark.parametrize("root", [FORECAST_ROOT, OUTLOOK_ROOT], ids=lambda r: r.name)
def test_the_basket_threshold_is_never_read_from_the_sectors_rules(root: Path) -> None:
    assert {p: r for p, t in _sources_under(root).items() if (r := _coverage_reads(t))} == {}


def test_the_coverage_read_scan_has_teeth() -> None:
    assert _coverage_reads("w = rules.CoverageRules().sector_coverage_threshold") != []


@pytest.mark.parametrize("module", ["app.outlook.basket", "app.outlook.volatility"])
@pytest.mark.parametrize(
    "package", ["app.sectors", "app.forecast", "app.positions", "app.portfolio", "app.advice"]
)
def test_basket_and_volatility_reach_none_of_the_forbidden_packages(
    module: str, package: str
) -> None:
    assert offenders(reachable_app_modules((module,)), package) == []


@pytest.mark.parametrize("package", ["app.positions", "app.portfolio", "app.advice.context"])
def test_outlook_does_not_reach_cost_data(package: str) -> None:
    # ADR-0027 D-15 point 5.
    assert offenders(reachable_app_modules(_modules_under(OUTLOOK_ROOT)), package) == []


def _sigma_call_violations(source: str) -> list[str]:
    """FL-78 (e): every sigma_d call passes ``definition=`` by keyword, not a literal."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", getattr(node.func, "attr", "")) == "sigma_d"
        ):
            continue
        keyword = {k.arg: k.value for k in node.keywords}.get("definition")
        if keyword is None or len(node.args) > 1:
            found.append("definition not by keyword")
        elif isinstance(keyword, ast.Constant):
            found.append("literal definition")
    return found


def _one_minus_uses(source: str) -> list[str]:
    """``1 - x`` expressions (risk R-2: compare retained weight with the constant itself)."""
    return [
        ast.unparse(node)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Sub)
        and isinstance(node.left, ast.Constant)
        and node.left.value == 1
    ]


def test_basket_never_computes_one_minus_the_threshold() -> None:
    assert _one_minus_uses((OUTLOOK_ROOT / "basket.py").read_text(encoding="utf-8")) == []


def _mentions_basket_weight(node: ast.AST) -> bool:
    return any(
        isinstance(sub, ast.Attribute) and sub.attr == "BASKET_MIN_MEMBER_WEIGHT"
        for sub in ast.walk(node)
    )


def _basket_weight_subtractions(source: str) -> list[str]:
    """Subtractions with the ``BASKET_MIN_MEMBER_WEIGHT`` attribute in either operand
    (C-10 (b), risk S-c; aliased forms are left to code review)."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
            if _mentions_basket_weight(node.left) or _mentions_basket_weight(node.right):
                found.append(ast.unparse(node))
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Sub):
            if _mentions_basket_weight(node.target) or _mentions_basket_weight(node.value):
                found.append(ast.unparse(node))
    return found


def test_no_subtraction_on_the_basket_weight_in_app() -> None:
    found = {p: u for p, t in _app_sources().items() if (u := _basket_weight_subtractions(t))}
    assert found == {}


@pytest.mark.parametrize(
    ("source", "caught"),
    [
        pytest.param("cap = 1 - definition.BASKET_MIN_MEMBER_WEIGHT", True, id="one-minus"),
        pytest.param("x = d.BASKET_MIN_MEMBER_WEIGHT - 0.1", True, id="left-operand"),
        pytest.param("x = 0.5 - (d.BASKET_MIN_MEMBER_WEIGHT * 1)", True, id="nested-right"),
        pytest.param("x -= d.BASKET_MIN_MEMBER_WEIGHT", True, id="aug-assign"),
        pytest.param("x = a.b.BASKET_MIN_MEMBER_WEIGHT - y", True, id="deep-attribute"),
        pytest.param("ok = kept / total < d.BASKET_MIN_MEMBER_WEIGHT", False, id="comparison"),
        pytest.param("kept = total - excluded", False, id="other-subtraction"),
    ],
)
def test_the_basket_weight_subtraction_scan_has_teeth(source: str, caught: bool) -> None:
    assert (_basket_weight_subtractions(source) != []) is caught


def test_the_one_minus_scan_has_teeth() -> None:
    assert _one_minus_uses("cap = 1 - definition.BASKET_MIN_MEMBER_WEIGHT") != []
    assert _one_minus_uses("cap = 1.0 - w") != []
    assert _one_minus_uses("kept = total - excluded") == []


def _basket_call_violations(source: str) -> list[str]:
    """B2D-3d: ``coverage_unknown`` and ``definition`` by keyword, ``definition`` not a literal."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not _is_call_to(node, "basket_log_returns"):
            continue
        assert isinstance(node, ast.Call)
        keywords = {k.arg: k.value for k in node.keywords}
        if len(node.args) > 3 or not {"coverage_unknown", "definition"} <= set(keywords):
            found.append("not by keyword")
        elif isinstance(keywords["definition"], ast.Constant):
            found.append("literal definition")
    return found


def test_every_basket_call_site_passes_its_keywords() -> None:
    assert {p: v for p, t in _app_sources().items() if (v := _basket_call_violations(t))} == {}


@pytest.mark.parametrize(
    ("source", "complies"),
    [
        ("basket_log_returns(m, s, w, c, d)", False),
        ("basket_log_returns(m, s, w, definition=d)", False),
        ("basket.basket_log_returns(m, s, w, coverage_unknown=c, definition=None)", False),
        ("basket_log_returns(m, s, w, coverage_unknown=c, definition=definition)", True),
    ],
)
def test_the_basket_call_scan_has_teeth(source: str, complies: bool) -> None:
    assert (_basket_call_violations(source) == []) is complies


def test_every_sigma_d_call_site_passes_the_definition_by_keyword() -> None:
    assert {p: v for p, t in _app_sources().items() if (v := _sigma_call_violations(t))} == {}


@pytest.mark.parametrize(
    ("source", "complies"),
    [
        ("sigma_d(xs, d)", False),
        ("sigma_d(xs)", False),
        ("volatility.sigma_d(xs, definition=None)", False),
        ("sigma_d(xs, definition=definition)", True),
    ],
)
def test_the_sigma_call_scan_has_teeth(source: str, complies: bool) -> None:
    assert (_sigma_call_violations(source) == []) is complies
