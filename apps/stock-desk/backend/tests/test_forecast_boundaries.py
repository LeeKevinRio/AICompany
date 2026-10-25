"""Structural boundaries of the B1 leaf modules (ADR-0027 D-1; ADR-0029 D-1).

* single definitions: ``threshold_inputs`` / ``labeled_snapshot_violations``
  only in ``band.py`` (FL-72 (n)); ``ThresholdViolation`` /
  ``THRESHOLD_VIOLATION_ORDER`` only in ``errors.py`` (C1);
* import rules: ``errors.py`` and ``ops_alert/model.py`` import the standard
  library only; ``band.py`` the standard library plus exactly
  ``from app.forecast.errors import THRESHOLD_VIOLATION_ORDER, ThresholdViolation``
  with no re-export (C2); ``outlook/missing.py`` the standard library and
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
import sys
from pathlib import Path

import pytest

from tests.import_graph import (
    APP_ROOT,
    imported_modules,
    offenders,
    reachable_app_modules,
)

FORECAST_ROOT = APP_ROOT / "forecast"
OUTLOOK_ROOT = APP_ROOT / "outlook"
OPS_ALERT_ROOT = APP_ROOT / "ops_alert"

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


def _band_import_violations(source: str) -> list[str]:
    """band.py's rule: stdlib, plus exactly the C2 line, and no re-export."""
    tree = ast.parse(source)
    found: list[str] = []
    app_imports = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (
            node.level or _top_level(node.module or "") == "app"
        ):
            app_imports += 1
            names = {alias.name for alias in node.names}
            if node.level or node.module != BAND_APP_MODULE or names != BAND_APP_NAMES:
                found.append(f"app import {node.module} {sorted(names)}")
            if any(alias.asname is not None for alias in node.names):
                found.append("aliased import")
        elif isinstance(node, ast.Import) and any(
            _top_level(alias.name) == "app" for alias in node.names
        ):
            app_imports += 1
            found.append("plain app import")
        elif isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                found.append("__all__")
    if app_imports != 1:
        found.append(f"{app_imports} app imports")
    rest = "\n".join(
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        and not (isinstance(node, ast.ImportFrom) and _top_level(node.module or "") == "app")
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


def test_the_scanned_packages_hold_exactly_the_b1_modules() -> None:
    # A new module in these packages must come with its own boundary rules.
    holders = sorted(
        path.relative_to(APP_ROOT).as_posix()
        for root in (FORECAST_ROOT, OUTLOOK_ROOT, OPS_ALERT_ROOT)
        for path in root.rglob("*.py")
    )
    assert holders == [
        "forecast/__init__.py",
        "forecast/band.py",
        "forecast/errors.py",
        "ops_alert/__init__.py",
        "ops_alert/model.py",
        "outlook/__init__.py",
        "outlook/missing.py",
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
        pytest.param(
            C2_LINE + "if TYPE_CHECKING:\n    from app.dirdef import DirectionDefinition\n",
            False,
            id="type-checking-import",
        ),
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
