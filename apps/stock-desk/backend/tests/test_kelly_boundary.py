"""Structural guard: ``app/kelly`` reaches neither the risk layer nor the backtester.

約束 13/37 fix the dependency direction as ``advice <- api -> {kelly, backtest}``.
Two things rest on it:

* the single Kelly formula stays in ``app/advice/limits.py``. A storage module
  that could reach it would be one edit away from holding a second copy.
* the sample gate takes scalars. If it could take a ``BacktestResult`` it would
  start reading fill-level counts, which are inflated by the daily rebalance
  (ADR-0006 Context 事實 5) and would wave through samples that do not exist.

Prose is not enforcement, so this reads the import graph, mirroring
``tests/test_playbook_boundary.py``.
"""

from __future__ import annotations

from tests.import_graph import (
    APP_ROOT,
    imported_modules,
    module_path,
    offenders,
    reachable_app_modules,
)

#: Neither may be reachable from the Kelly package.
FORBIDDEN_PACKAGES = ("app.advice", "app.backtest")

GUARDED_MODULES = (
    "app.kelly",
    "app.kelly.models",
    "app.kelly.store",
    "app.kelly.sample_gate",
    "app.kelly.attempts",
)

#: The one module allowed to touch all three packages (D-8). It is checked
#: here only so a typo in the name cannot make the teeth test vacuous.
ASSEMBLY_POINT = "app.api.kelly"


def test_the_scan_actually_resolves_every_guarded_module() -> None:
    """A typo in a module name would make every other assertion vacuous."""
    for module in (*GUARDED_MODULES, ASSEMBLY_POINT):
        assert module_path(module) is not None, module


def test_every_kelly_module_is_listed_in_the_guard() -> None:
    """A new file under app/kelly/ must be added to GUARDED_MODULES."""
    on_disk = {
        f"app.kelly.{path.stem}" if path.stem != "__init__" else "app.kelly"
        for path in (APP_ROOT / "kelly").glob("*.py")
    }
    assert on_disk <= set(GUARDED_MODULES), sorted(on_disk - set(GUARDED_MODULES))


def test_the_kelly_package_never_reaches_the_advice_or_backtest_packages() -> None:
    reachable = reachable_app_modules(GUARDED_MODULES)
    for package in FORBIDDEN_PACKAGES:
        found = offenders(reachable, package)
        assert found == [], (
            f"{package} is reachable from app/kelly via {found}; "
            "約束 13/37：依賴方向為 advice <- api -> {kelly, backtest}。"
        )


def test_the_sample_gate_alone_imports_nothing_but_its_own_models() -> None:
    """The gate's scalar-only interface, stated as an import fact."""
    path = module_path("app.kelly.sample_gate")
    assert path is not None
    assert imported_modules(path, "app.kelly.sample_gate") <= {
        "app.kelly",
        "app.kelly.models",
        "app.kelly.models.KellyGateReasonCode",
    }


def test_the_scan_has_teeth_on_a_module_that_does_reach_both() -> None:
    """``app.api.backtest`` legitimately reaches the backtester -- the scan sees it."""
    reachable = reachable_app_modules(("app.api.backtest",))
    assert offenders(reachable, "app.backtest") != []
