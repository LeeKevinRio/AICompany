"""The import scanner resolves every module name it is handed, the bare root included.

Also: no ``app/`` module reaches ``scripts/`` (ADR-0030 K-11; supplement 6 S-13b point 1).
"""

from __future__ import annotations

import ast

from tests.import_graph import APP_ROOT, module_path, reachable_app_modules

SCRIPTS_ROOT = APP_ROOT.parent / "scripts"


def test_the_bare_app_root_resolves_to_its_package_file() -> None:
    assert module_path("app") == APP_ROOT / "__init__.py"
    assert module_path("app.sectors") == APP_ROOT / "sectors" / "__init__.py"
    assert module_path("app.sectors.gate") == APP_ROOT / "sectors" / "gate.py"
    assert module_path("apple") is None
    assert module_path("app.no_such_module") is None


def test_walking_from_the_root_does_not_raise() -> None:
    assert "app" in reachable_app_modules(("app",))


# --- app/ does not reach scripts/ -----------------------------------------------------------


def _script_names() -> set[str]:
    """``scripts`` and every module stem under it (the folder is not a package)."""
    return {"scripts", *(p.stem for p in SCRIPTS_ROOT.rglob("*.py"))}


def script_imports(source: str, names: set[str]) -> set[str]:
    """The modules of ``names`` a source imports, statically or through a name string."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.split(".")[0] in names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            if node.module.split(".")[0] in names:
                found.add(node.module)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # importlib / runpy routes name the module or its file in a string.
            stem = node.value.split("/")[-1].removesuffix(".py").split(".")[0]
            if stem in names - {"scripts"} or node.value.startswith("scripts."):
                found.add(node.value)
    return found


def test_no_app_module_imports_the_scripts() -> None:
    names = _script_names()
    assert "pipeline_acceptance_real" in names
    sources = {p: p.read_text(encoding="utf-8") for p in APP_ROOT.rglob("*.py")}
    assert {p: hits for p, s in sources.items() if (hits := script_imports(s, names))} == {}


def test_the_script_import_scan_has_teeth() -> None:
    names = {"scripts", "pipeline_acceptance_real"}
    assert script_imports("import pipeline_acceptance_real\n", names)
    assert script_imports("from scripts.pipeline_acceptance_real import x\n", names)
    assert script_imports("import scripts\n", names)
    assert script_imports("runpy.run_path('scripts/pipeline_acceptance_real.py')\n", names)
    assert script_imports("importlib.import_module('pipeline_acceptance_real')\n", names)
    assert not script_imports("from app.forecast import report\n", names)
