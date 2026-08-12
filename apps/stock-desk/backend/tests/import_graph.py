"""Static ``import`` scanner for structural boundary tests.

A boundary that only exists in prose is not enforced, so the guards read the
import graph instead: starting from a set of entry modules, walk every
``app.*`` module reachable through ``import`` statements and check that a
forbidden package is not among them. It is a source scan (``ast``), so nothing
has to be imported and no application wiring runs.

``tests/test_dividends_boundary.py`` predates this module and keeps its own copy
of the same walk; migrating it is a qa-automation call, not a reason to touch a
passing guard from here.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"


def module_path(module: str) -> Path | None:
    """The source file for ``app.x.y``, module or package, or ``None``."""
    if module != "app" and not module.startswith("app."):
        return None
    relative = Path(*module.split(".")[1:])
    candidate = APP_ROOT / relative.with_suffix(".py")
    if candidate.is_file():
        return candidate
    package = APP_ROOT / relative / "__init__.py"
    return package if package.is_file() else None


def imported_modules(source: Path, module: str) -> set[str]:
    """The ``app.*`` modules ``source`` imports, absolute and relative forms."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                # Relative import: rebuild the absolute name so a
                # `from ..advice import x` cannot slip past the scan.
                parts = module.split(".")
                anchor = parts if source.name == "__init__.py" else parts[:-1]
                prefix = anchor[: len(anchor) - node.level + 1]
                base = ".".join([*prefix, base]) if base else ".".join(prefix)
            if base:
                found.add(base)
                found.update(f"{base}.{alias.name}" for alias in node.names)
    return {name for name in found if name == "app" or name.startswith("app.")}


def reachable_app_modules(roots: tuple[str, ...]) -> set[str]:
    """Every ``app.*`` module reachable from ``roots`` through imports."""
    seen: set[str] = set()
    queue = list(roots)
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        path = module_path(module)
        if path is None:  # a symbol imported from a module, not a module itself
            continue
        queue.extend(imported_modules(path, module) - seen)
    return seen


def offenders(reachable: set[str], forbidden_package: str) -> list[str]:
    """The reachable modules that live inside ``forbidden_package``."""
    return sorted(
        module
        for module in reachable
        if module == forbidden_package or module.startswith(f"{forbidden_package}.")
    )
