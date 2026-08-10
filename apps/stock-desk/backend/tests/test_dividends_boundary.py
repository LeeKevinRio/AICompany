"""Structural guard: 還原價 must never reach valuation or the risk limits.

``app.dividends.adjust`` documents the boundary in prose -- back-adjusted prices
are a measurement device for backtest returns, while position valuation,
portfolio totals and every risk cap keep using the raw close. The approved
disclosure sentence (``DIVIDEND_METHOD_NOTE``) states the same thing to the
user: 「持倉市值與風險上限一律仍用原始收盤價」.

Prose and a promise to the user are not enforcement, so this module reads the
import graph instead: starting from the valuation / limits modules, nothing
reachable may import ``app.dividends``. It is a static scan of ``import``
statements only -- cheap, no application import required -- which is enough
because a module cannot use adjusted prices it never imports.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"

#: The forbidden package. Anything under it produces adjusted prices.
FORBIDDEN_PACKAGE = "app.dividends"

#: Entry points of the valuation / risk-limit path named in the boundary docs.
GUARDED_MODULES = (
    "app.portfolio.valuation",
    "app.portfolio.summary",
    "app.advice.limits",
    "app.advice.book_limits",
)


def _module_path(module: str) -> Path | None:
    """The source file for ``app.x.y``, module or package, or ``None``."""
    if module != "app" and not module.startswith("app."):
        return None
    relative = Path(*module.split(".")[1:])
    candidate = APP_ROOT / relative.with_suffix(".py")
    if candidate.is_file():
        return candidate
    package = APP_ROOT / relative / "__init__.py"
    return package if package.is_file() else None


def _imported_modules(source: Path, module: str) -> set[str]:
    """The ``app.*`` modules ``source`` imports, absolute and relative forms."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                # Relative import: rebuild the absolute name from the package
                # the file lives in, so a `from ..dividends import x` cannot
                # slip past the scan.
                parts = module.split(".")
                anchor = parts if source.name == "__init__.py" else parts[:-1]
                prefix = anchor[: len(anchor) - node.level + 1]
                base = ".".join([*prefix, base]) if base else ".".join(prefix)
            if base:
                found.add(base)
                found.update(f"{base}.{alias.name}" for alias in node.names)
    return {name for name in found if name == "app" or name.startswith("app.")}


def _reachable_app_modules(roots: tuple[str, ...]) -> set[str]:
    """Every ``app.*`` module reachable from ``roots`` through imports."""
    seen: set[str] = set()
    queue = list(roots)
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        path = _module_path(module)
        if path is None:  # a symbol imported from a module, not a module itself
            continue
        queue.extend(_imported_modules(path, module) - seen)
    return seen


def test_the_scan_actually_resolves_the_guarded_modules() -> None:
    """A typo in a module name would make every other assertion vacuous."""
    for module in GUARDED_MODULES:
        assert _module_path(module) is not None, module


def test_valuation_and_limits_never_reach_the_dividend_package() -> None:
    reachable = _reachable_app_modules(GUARDED_MODULES)
    offenders = sorted(
        module
        for module in reachable
        if module == FORBIDDEN_PACKAGE or module.startswith(f"{FORBIDDEN_PACKAGE}.")
    )
    assert offenders == [], (
        f"{FORBIDDEN_PACKAGE} is reachable from the valuation / risk-limit path "
        f"via {offenders}; 持倉市值與風險上限必須一律使用原始收盤價。"
    )


def test_the_scan_has_teeth_on_a_module_that_does_import_dividends() -> None:
    """``app.api.backtest`` legitimately imports the package -- the scan sees it."""
    reachable = _reachable_app_modules(("app.api.backtest",))
    assert any(module.startswith(FORBIDDEN_PACKAGE) for module in reachable)
