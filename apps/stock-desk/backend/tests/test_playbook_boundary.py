"""Structural guard: the playbook must never read the advice engine.

風控 required R4: the rule inputs are a hard whitelist that excludes every
output field of the advice engine (``action`` / ``confidence`` / ``weight`` /
``matched_rules`` / ``direction_weights``) -- 「違反即豁免自始不成立」. The
exemption that lets this module speak in instruction wording rests on the user
authoring every rule, so one advice-engine judgement flowing into a directive
would void it retroactively.

Mirrors ``tests/test_dividends_boundary.py``: prose and a promise are not
enforcement, so this reads the import graph. A module cannot use a judgement it
never imports, and the API router is included because that is where two
packages would most plausibly be stitched together.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.import_graph import (
    APP_ROOT,
    imported_modules,
    module_path,
    offenders,
    reachable_app_modules,
)

#: The forbidden package: everything under it produces advice-engine output.
FORBIDDEN_PACKAGE = "app.advice"

#: Every module of the playbook package. The deep scan runs from here.
GUARDED_MODULES = (
    "app.playbook",
    "app.playbook.engine",
    "app.playbook.service",
    "app.playbook.store",
    "app.playbook.models",
    "app.playbook.indicators",
    "app.playbook.calendar",
    "app.playbook.wording",
    "app.playbook.price_fields",
)

#: The router is checked on its **direct** imports only. It reaches the advice
#: package transitively through ``app.api.deps``, the dependency module every
#: router shares (the settings and alert stores reuse ``RiskBudget`` /
#: ``LIMIT_IDS`` from it), so a transitive scan there would measure FastAPI
#: wiring rather than this boundary. What matters is that the playbook router
#: itself neither imports nor renders anything the advice engine produced.
GUARDED_ROUTER = "app.api.playbook"

#: The advice engine's own output vocabulary. None of these names may appear as
#: an imported symbol in the playbook package.
ADVICE_OUTPUT_FIELDS = (
    "ACTION_DIRECTION",
    "AdviceCard",
    "AdviceEngine",
    "direction_weights",
    "matched_rules",
)


def test_the_scan_actually_resolves_every_guarded_module() -> None:
    """A typo in a module name would make every other assertion vacuous."""
    for module in (*GUARDED_MODULES, GUARDED_ROUTER):
        assert module_path(module) is not None, module


def test_every_playbook_module_is_listed_in_the_guard() -> None:
    """A new file under app/playbook/ must be added to GUARDED_MODULES."""
    on_disk = {
        f"app.playbook.{path.stem}" if path.stem != "__init__" else "app.playbook"
        for path in (APP_ROOT / "playbook").glob("*.py")
    }
    assert on_disk <= set(GUARDED_MODULES), sorted(on_disk - set(GUARDED_MODULES))


def test_the_playbook_never_reaches_the_advice_package() -> None:
    reachable = reachable_app_modules(GUARDED_MODULES)
    found = offenders(reachable, FORBIDDEN_PACKAGE)
    assert found == [], (
        f"{FORBIDDEN_PACKAGE} is reachable from the playbook via {found}; "
        "風控 R4：排程引擎不得取用建議引擎的任何輸出欄位，違反即豁免自始不成立。"
    )


def test_the_router_does_not_import_the_advice_package_directly() -> None:
    path = module_path(GUARDED_ROUTER)
    assert path is not None
    found = offenders(imported_modules(path, GUARDED_ROUTER), FORBIDDEN_PACKAGE)
    assert found == [], f"{GUARDED_ROUTER} imports {found}"


def _identifiers(path: Path) -> set[str]:
    """Every name the code actually uses -- docstrings and comments excluded."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
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
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # String literals count too: a field name could be read out of a
            # dict by key rather than by attribute.
            names.add(node.value)
    return names


def test_no_advice_output_field_name_is_used_in_the_playbook_source() -> None:
    """Belt and braces: not even a copied field name, let alone an import.

    Docstrings that *describe* the boundary are exempt (this file and the
    package docstring both have to name the fields to explain the rule); what is
    checked is the code -- identifiers, attributes and string keys.
    """
    for path in sorted(Path(APP_ROOT / "playbook").glob("*.py")):
        used = _identifiers(path)
        for field in ADVICE_OUTPUT_FIELDS:
            assert field not in used, f"{path.name} uses advice output {field}"


def test_the_scan_has_teeth_on_a_module_that_does_import_advice() -> None:
    """``app.api.advice`` legitimately imports the package -- the scan sees it."""
    reachable = reachable_app_modules(("app.api.advice",))
    assert offenders(reachable, FORBIDDEN_PACKAGE) != []
