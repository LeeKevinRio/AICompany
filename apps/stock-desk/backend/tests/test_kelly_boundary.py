"""Structural guard on both directions of the ``app/kelly`` boundary.

約束 13/37 fix the dependency direction as ``advice <- api -> {kelly, backtest}``.
Two things rest on the outbound half (``app/kelly`` reaches neither the risk
layer nor the backtester):

* the single Kelly formula stays in ``app/advice/limits.py``. A storage module
  that could reach it would be one edit away from holding a second copy.
* the sample gate takes scalars. If it could take a ``BacktestResult`` it would
  start reading fill-level counts, which are inflated by the daily rebalance
  (ADR-0006 Context 事實 5) and would wave through samples that do not exist.

The inbound half is narrower than "never". tech-architect ratified one exception
on 2026-08-22 (`work/stock-desk-C5-Kelly-條件46裁決.md` 附註): ``app/advice/book.py``
imports ``app.kelly.models`` so that ageing has a single home (D-6), because
``app.kelly.models`` is pure data and pure functions -- no I/O, no cycle, and no
second copy of ``kelly_fraction``. What the exception does **not** cover is the
two modules that open the database, and 約束 12 excludes the whole Kelly package
from ``limits.py``: a risk cap that could read a store (or a clock) would be a
cap whose verdict depends on when it was asked. Both are asserted below.

Prose is not enforcement, so this reads the import graph, mirroring
``tests/test_playbook_boundary.py``.
"""

from __future__ import annotations

from pathlib import Path

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

#: Every module of the risk layer, as the roots of the inbound scan. The whole
#: package is guarded rather than the one file that holds the exception:
#: ``limits``/``context``/``engine``/``book_limits`` importing a store later
#: would be the same violation, and a guard aimed at one file would not see it.
ADVICE_MODULES = (
    "app.advice",
    "app.advice.book",
    "app.advice.book_limits",
    "app.advice.context",
    "app.advice.engine",
    "app.advice.limits",
    "app.advice.loader",
)

#: The two Kelly modules that touch SQLite. These are what the ratified
#: exception stops at: reaching either from the risk layer would put I/O behind
#: a pure function (ADR-0005 decision 5) and give a cap a database to consult.
KELLY_STORAGE_MODULES = ("app.kelly.store", "app.kelly.attempts")

#: 約束 12, in full: the risk-budget module gets *nothing* from ``app/kelly``,
#: not even the models its sibling ``book.py`` is allowed to import.
NO_KELLY_AT_ALL = "app.advice.limits"

#: The one module allowed to touch all three packages (D-8). It is checked
#: here only so a typo in the name cannot make the teeth test vacuous.
ASSEMBLY_POINT = "app.api.kelly"


def test_the_scan_actually_resolves_every_guarded_module() -> None:
    """A typo in a module name would make every other assertion vacuous."""
    for module in (*GUARDED_MODULES, *ADVICE_MODULES, *KELLY_STORAGE_MODULES, ASSEMBLY_POINT):
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


# ---------------------------------------------------------------------------
# The inbound half: what the risk layer may take from app/kelly
# ---------------------------------------------------------------------------


def test_every_advice_module_is_listed_in_the_guard() -> None:
    """A new file under app/advice/ must be added to ADVICE_MODULES.

    Without this the guard would silently stop covering the module most likely
    to want a store -- the newest one.
    """
    on_disk = {
        f"app.advice.{path.stem}" if path.stem != "__init__" else "app.advice"
        for path in (APP_ROOT / "advice").glob("*.py")
    }
    assert on_disk <= set(ADVICE_MODULES), sorted(on_disk - set(ADVICE_MODULES))


def test_the_risk_layer_never_reaches_the_kelly_storage_modules() -> None:
    """The boundary the ratified exception stops at, over the whole package.

    Transitive, so a store reached through a new intermediary is caught too, and
    over every root, so the exception stays confined to the models module.
    """
    reachable = reachable_app_modules(ADVICE_MODULES)
    for module in KELLY_STORAGE_MODULES:
        found = offenders(reachable, module)
        assert found == [], (
            f"{module} is reachable from app/advice via {found}; "
            "約束 12/37：風險層取得的是已算好年齡的輸入，不是可查詢的資料庫。"
        )


def test_the_ratified_exception_is_exactly_the_models_module() -> None:
    """``book.py`` may import ``app.kelly.models`` -- and that is the whole of it.

    Asserted positively as well as negatively so the guard cannot pass by the
    import disappearing: if ageing stopped coming from
    :func:`app.kelly.models.ageing_of`, it would be being re-derived somewhere,
    which is what D-6 gives that function one home to prevent.
    """
    path = module_path("app.advice.book")
    assert path is not None
    imported = imported_modules(path, "app.advice.book")

    assert "app.kelly.models" in imported
    assert {name for name in imported if name.startswith("app.kelly")} <= {
        "app.kelly.models",
        "app.kelly.models.KellyInputRow",
        "app.kelly.models.ageing_of",
    }


def test_the_risk_budget_module_takes_nothing_from_the_kelly_package() -> None:
    """約束 12 as a white-box fact, not a comment: zero, not "no stores"."""
    path = module_path(NO_KELLY_AT_ALL)
    assert path is not None

    direct = sorted(
        name for name in imported_modules(path, NO_KELLY_AT_ALL) if name.startswith("app.kelly")
    )
    assert direct == [], (
        f"{NO_KELLY_AT_ALL} imports {direct}；約束 12：limits.py 禁 import app/kelly。"
    )

    # And nothing it imports may drag the package in either -- the approved
    # sentences arrive from ``app.api.kelly_wording``, which imports nothing.
    transitive = offenders(reachable_app_modules((NO_KELLY_AT_ALL,)), "app.kelly")
    assert transitive == [], transitive


def test_the_inbound_scan_sees_a_plain_import_statement(tmp_path: Path) -> None:
    """Teeth on the hole this guard was rewritten to close.

    The previous version walked ``ast.ImportFrom`` only, so
    ``import app.kelly.store`` -- the form that does not name a symbol -- read as
    no import at all. ``imported_modules`` handles both node types; this drives a
    file written in that exact form to prove it, rather than trusting the helper.
    """
    source = tmp_path / "offender.py"
    source.write_text("import app.kelly.store\n", encoding="utf-8")

    assert "app.kelly.store" in imported_modules(source, "app.advice.offender")
