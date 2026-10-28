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
    # ``app.playbook.calendar`` moved to ``app.data.calendar`` (C4, 2026-08-13);
    # it is still scanned, just transitively, because ``service``/``engine``/
    # ``store`` import it -- ``reachable_app_modules`` follows the edge.
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


# --- 排程台 × 第 1 條 disclosure (N-155, ADR-0031 C-6/C-7, 風控 #68 裁決補充 R4) -----
#
# 修訂 D-2 (2) (CEO #68/#70): no risk cap constrains the 排程台, and nothing under
# app/playbook/ may read one. The single exception is the router, which may read
# cap 1's current value only to compose the disclosure. The guards below pin
# both halves: the package never gets near the settings, and the router uses the
# value in exactly two places.

#: The zero-dependency module holding the disclosure sentences.
DISCLOSURE_WORDING = "app.api.playbook_cap1_wording"

#: T-2: every ``app.*`` module the router may import directly. Adding one means
#: editing this guard, which is what puts the change in front of a reviewer.
ROUTER_ALLOWED_IMPORTS = frozenset(
    {
        "app.api.common",
        "app.api.deps",
        "app.playbook",
        "app.playbook.wording",
        "app.playbook.models",
        "app.playbook.service",
        DISCLOSURE_WORDING,
    }
)

#: T-4 / PD-3: names that would mean the playbook package touches a risk cap,
#: the cap-1 dependency, or the disclosure built from it.
RISK_CAP_IDENTIFIERS = (
    "max_position_weight",
    "RiskBudget",
    "risk_budget",
    "cap1_weight",
    "get_cap1_weight",
    "playbook_cap1_wording",
)

#: T-5: packages the playbook may not reach even transitively, with the reason
#: each one is out of bounds.
PLAYBOOK_FORBIDDEN_PACKAGES = {
    "app.settings": (
        "修訂 D-2 (2)：排程台模組不得讀取設定頁的任何上限值；第 1 條只能經 "
        "app.api.deps.get_cap1_weight 由 router 取得，且只用於組成揭露（ADR-0031）。"
    ),
    "app.api": (
        "ADR-0031 C-1/C-6：揭露在 API 層組成；app.playbook 回頭 import app.api "
        "等於讓排程台碰到第 1 條的值與揭露字面（R4）。"
    ),
}

#: The name of the cap-1 value inside the router (R4-1).
CAP1_NAME = "cap1_weight"
#: The ``Annotated`` alias the router declares the dependency with.
CAP1_DEP_ALIAS = "Cap1WeightDep"
#: The three endpoints that carry the disclosure (C-5).
DISCLOSURE_ENDPOINTS = frozenset({"today", "rule_set", "confirm_rules"})


def test_the_router_does_not_import_the_settings_package() -> None:
    """T-1 (C-6): the cap-1 value reaches the router through ``deps`` only."""
    path = module_path(GUARDED_ROUTER)
    assert path is not None
    found = offenders(imported_modules(path, GUARDED_ROUTER), "app.settings")
    assert found == [], f"{GUARDED_ROUTER} imports {found}; ADR-0031 C-6"


def test_the_router_imports_only_the_whitelisted_app_modules() -> None:
    """T-2: the router's direct ``app.*`` imports are a fixed whitelist.

    ``from m import name`` records both ``m`` and ``m.name``; a name that is not
    itself a module is judged by the module it was imported from.
    """
    path = module_path(GUARDED_ROUTER)
    assert path is not None
    unexpected = set()
    for name in imported_modules(path, GUARDED_ROUTER):
        module = name if module_path(name) is not None else name.rsplit(".", 1)[0]
        if module not in ROUTER_ALLOWED_IMPORTS:
            unexpected.add(name)
    assert unexpected == set(), sorted(unexpected)
    # Not vacuous: the disclosure module is among the imports actually made.
    assert DISCLOSURE_WORDING in imported_modules(path, GUARDED_ROUTER)


def test_the_disclosure_wording_imports_nothing_from_app() -> None:
    """T-3 (C-1, PD-1): the wording module is text and arithmetic, nothing else."""
    path = module_path(DISCLOSURE_WORDING)
    assert path is not None
    assert imported_modules(path, DISCLOSURE_WORDING) == set()


def test_no_risk_cap_identifier_is_used_in_the_playbook_source() -> None:
    """T-4 (PD-3): not a name, attribute, keyword or string key of a risk cap."""
    for path in sorted(Path(APP_ROOT / "playbook").glob("*.py")):
        used = _identifiers(path)
        for name in RISK_CAP_IDENTIFIERS:
            assert name not in used, f"{path.name} uses {name}; 修訂 D-2 (2)／R4"


def test_the_playbook_never_reaches_the_settings_or_the_api_package() -> None:
    """T-5: two more forbidden destinations for the transitive scan."""
    reachable = reachable_app_modules(GUARDED_MODULES)
    for package, reason in PLAYBOOK_FORBIDDEN_PACKAGES.items():
        found = offenders(reachable, package)
        assert found == [], f"{package} is reachable from the playbook via {found}; {reason}"


def test_the_settings_and_api_scans_have_teeth() -> None:
    """The T-5 scan does see both packages from a module that imports them."""
    reachable = reachable_app_modules(("app.api.advice",))
    assert offenders(reachable, "app.settings") != []
    assert offenders(reachable, "app.api") != []


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _is_compose_call(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "compose"
    )


def _is_cap1_depends(node: ast.AST) -> bool:
    """``Annotated[Decimal | None, Depends(get_cap1_weight)]``, and nothing looser."""
    if not (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Annotated"
        and isinstance(node.slice, ast.Tuple)
        and len(node.slice.elts) == 2
    ):
        return False
    depends = node.slice.elts[1]
    return (
        isinstance(depends, ast.Call)
        and isinstance(depends.func, ast.Name)
        and depends.func.id == "Depends"
        and len(depends.args) == 1
        and not depends.keywords
        and isinstance(depends.args[0], ast.Name)
        and depends.args[0].id == "get_cap1_weight"
    )


def _cap1_uses(tree: ast.Module) -> tuple[set[str], int, list[str]]:
    """Classify every occurrence of the cap-1 name in ``tree``.

    Returns the functions that take it as a parameter declared through the
    alias, the number of bare ``cap1_weight=cap1_weight`` arguments to a
    ``compose(...)`` call, and every other occurrence -- an ``if``, a
    comparison, arithmetic, a log call, another field, an attribute or a
    string all land there.
    """
    parents = _parents(tree)
    receivers: set[str] = set()
    compose_arguments = 0
    other: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.arg == CAP1_NAME:
            function = parents[parents[node]]
            annotated = (
                isinstance(node.annotation, ast.Name) and node.annotation.id == CAP1_DEP_ALIAS
            )
            if annotated and isinstance(function, ast.FunctionDef):
                receivers.add(function.name)
            else:
                other.append(f"parameter at line {node.lineno}")
        elif isinstance(node, ast.keyword) and node.arg == CAP1_NAME:
            bare = isinstance(node.value, ast.Name) and node.value.id == CAP1_NAME
            if bare and _is_compose_call(parents[node]):
                compose_arguments += 1
            else:
                other.append(f"keyword at line {node.value.lineno}")
        elif isinstance(node, ast.Name) and node.id == CAP1_NAME:
            parent = parents[node]
            passed = (
                isinstance(parent, ast.keyword)
                and parent.arg == CAP1_NAME
                and _is_compose_call(parents[parent])
            )
            if not passed:
                other.append(f"name at line {node.lineno}")
        elif isinstance(node, ast.Attribute) and node.attr == CAP1_NAME:
            other.append(f"attribute at line {node.lineno}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if CAP1_NAME in node.value:
                other.append(f"string at line {node.lineno}")
    return receivers, compose_arguments, other


def test_the_cap1_value_is_only_received_and_passed_to_compose() -> None:
    """R4-1: in the router the value appears in ``Depends`` and as ``compose``'s argument.

    修訂 D-2 (2) lets the router read cap 1 only to compose the disclosure; it
    may not enter any branch, comparison, arithmetic, log, state or record.
    """
    path = module_path(GUARDED_ROUTER)
    assert path is not None
    tree = ast.parse(path.read_text(encoding="utf-8"))

    receivers, compose_arguments, other = _cap1_uses(tree)
    assert other == [], other
    assert receivers == DISCLOSURE_ENDPOINTS
    assert compose_arguments == len(DISCLOSURE_ENDPOINTS)

    # The alias is declared once, as exactly the cap-1 dependency, and used for
    # those parameters only; the dependency is named in the alias and the import.
    alias_values = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == CAP1_DEP_ALIAS for t in node.targets)
    ]
    assert len(alias_values) == 1 and _is_cap1_depends(alias_values[0])
    alias_loads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == CAP1_DEP_ALIAS
        and isinstance(node.ctx, ast.Load)
    ]
    assert len(alias_loads) == len(DISCLOSURE_ENDPOINTS)
    dependency_names = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "get_cap1_weight"
    ]
    assert len(dependency_names) == 1
    assert "get_cap1_weight" in _identifiers(path)


def test_the_cap1_guard_has_teeth() -> None:
    """The classifier flags a branch, arithmetic, a log call and a second field."""
    snippet = ast.parse(
        "def today(service: ServiceDep, cap1_weight: Cap1WeightDep) -> None:\n"
        "    if cap1_weight is not None:\n"
        "        logger.info('%s', cap1_weight)\n"
        "    compose(cap1_weight=cap1_weight)\n"
        "    compose(cap1_weight=cap1_weight * 2)\n"
        "    return Response(cap1_weight=cap1_weight)\n"
    )
    receivers, compose_arguments, other = _cap1_uses(snippet)
    assert receivers == {"today"}
    assert compose_arguments == 1
    assert sorted(other) == sorted(
        [
            "name at line 2",
            "name at line 3",
            "keyword at line 5",
            "name at line 5",
            "keyword at line 6",
            "name at line 6",
        ]
    )
