"""Structural rules of the NM-5 outlook modules (risk RC-130; TA Q1, Q2, G1; ADR-0030 K-2, K-6).

* RC-130 / K-10 / S-6: the recorder's entry has no such parameter; the ``app/outlook``
  functions with a T / ``as_of`` / clock parameter are not referenced from any
  other ``app/`` module (one exception, ``late_cutoff_at``, see its cell); the
  recorder-facing entries have no such parameter; the decision-session cut is
  never named outside ``app/outlook``;
* TA Q2: the engine compares W, theta and the completeness as ``Fraction`` --
  no raw ``theta`` / ``min_completeness`` / ``weight`` in a comparison, and each
  is wrapped in ``Fraction(...)``;
* TA G1: ``engine.py`` holds no rule parameter: no float literal at all, and
  its int literals are the freeze pack 2.3 window lengths plus 0 and 1;
* TA Q1: ``app/`` holds no second expression parser (string splitting on
  ``or`` / ``and``, ``eval``, ``exec``, ``literal_eval``) and one ``holds``;
* K-2: ``app.outlook`` reaches none of the forbidden packages.

Every scan has a teeth test fed with a source string that breaks it.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import get_args

import pytest

from app.advice.engine import COMPARISON_OPS
from app.dirdef.rules import ComparisonOp
from app.forecast.recorder import record_forecasts
from app.outlook.engine import _OPS, PIT_ITEM, compute_outlook
from app.outlook.inputs import capture_market_snapshot
from tests.import_graph import APP_ROOT, offenders, reachable_app_modules

OUTLOOK_ROOT = APP_ROOT / "outlook"

#: Parameter names that would let a caller choose the decision session or the clock.
TIME_PARAMS = frozenset(
    {"t", "T", "as_of", "data_as_of", "decision_date", "clock", "now", "today", "when"}
)

#: The one outlook function with a session parameter that ``app/forecast/store.py``
#: may call: it maps a record's own T to its write cutoff (D-3 point 3). It reads
#: no bar, computes no label and cannot choose T.
ALLOWED_OUTSIDE = frozenset({"late_cutoff_at"})


def _sources(root: Path) -> dict[str, str]:
    return {
        path.relative_to(APP_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*.py"))
    }


def _time_param_functions(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            args = node.args
            names = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
            if names & TIME_PARAMS:
                found.add(node.name)
    return found


def _referenced_names(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
    return names


def _outside_outlook() -> dict[str, str]:
    return {p: s for p, s in _sources(APP_ROOT).items() if not p.startswith("outlook/")}


# --- RC-130 ------------------------------------------------------------------------------------


def test_the_recorder_entry_takes_no_time_parameter() -> None:
    # NM-5 third batch: the recorder exists; K-10 / S-6 hold on its entry (the full
    # signature and call-site checks are in tests/test_forecast_recorder.py).
    assert (APP_ROOT / "forecast" / "recorder.py").exists()
    assert set(inspect.signature(record_forecasts).parameters) & TIME_PARAMS == set()


def test_the_time_parameter_functions_are_the_known_ones() -> None:
    found = set().union(*(_time_param_functions(s) for s in _sources(OUTLOOK_ROOT).values()))
    assert found == {
        "late_cutoff_at",
        "_cut_snapshot",
        "snapshot_view",
        "evaluate_outlook",
        "compute_baselines",
        "_cut_and_compute",
        "_item",  # builds a MissingItem dated T; private to engine.py
    }


def test_no_other_app_module_references_an_outlook_time_parameter_function() -> None:
    functions = set().union(*(_time_param_functions(s) for s in _sources(OUTLOOK_ROOT).values()))
    used = {
        path: sorted(hits)
        for path, source in _outside_outlook().items()
        if (hits := (_referenced_names(source) & functions) - ALLOWED_OUTSIDE)
    }
    assert used == {}
    holders = {
        path
        for path, source in _outside_outlook().items()
        if _referenced_names(source) & ALLOWED_OUTSIDE
    }
    assert holders == {"forecast/store.py"}


def test_the_reference_scan_has_teeth() -> None:
    assert "evaluate_outlook" in _referenced_names(
        "from app.outlook.engine import evaluate_outlook\n"
    )
    assert "_cut_and_compute" in _referenced_names("engine._cut_and_compute(x, d)\n")
    assert _time_param_functions("def f(bars, *, clock): ...\n") == {"f"}
    assert _time_param_functions("def g(bars, *, size): ...\n") == set()


@pytest.mark.parametrize("function", [capture_market_snapshot, compute_outlook])
def test_the_recorder_facing_entries_take_no_time_parameter(function: object) -> None:
    assert callable(function)
    assert set(inspect.signature(function).parameters) & TIME_PARAMS == set()


def test_the_decision_session_cut_is_never_named_outside_outlook() -> None:
    named = {
        path
        for path, source in _outside_outlook().items()
        if "_cut_snapshot" in source or "_cut_and_compute" in source
    }
    assert named == set()


# --- TA Q2: Fraction comparisons ---------------------------------------------------------------

RAW_NUMBERS = frozenset({"theta", "min_completeness", "weight"})


def _raw_comparisons(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare):
            for operand in (node.left, *node.comparators):
                if any(
                    isinstance(sub, ast.Attribute) and sub.attr in RAW_NUMBERS
                    for sub in ast.walk(operand)
                    if not _inside_fraction(operand, sub)
                ):
                    found.append(ast.unparse(node))
    return found


def _inside_fraction(root: ast.AST, target: ast.AST) -> bool:
    for node in ast.walk(root):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "Fraction"
            and any(target is sub for arg in node.args for sub in ast.walk(arg))
        ):
            return True
    return False


def _fraction_wrapped(source: str) -> set[str]:
    return {
        arg.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Fraction"
        for arg in node.args
        if isinstance(arg, ast.Attribute)
    }


def test_the_engine_compares_w_theta_and_completeness_as_fractions() -> None:
    source = (OUTLOOK_ROOT / "engine.py").read_text(encoding="utf-8")
    assert _raw_comparisons(source) == []
    assert RAW_NUMBERS <= _fraction_wrapped(source)


@pytest.mark.parametrize(
    "probe",
    [
        "ok = abs(w) < ruleset.aggregation.theta\n",
        "ok = share < rs.aggregation.min_completeness\n",
        "ok = r.weight >= 1\n",
    ],
)
def test_the_fraction_scan_has_teeth(probe: str) -> None:
    assert _raw_comparisons(probe) != []


def test_the_fraction_scan_accepts_a_wrapped_operand() -> None:
    assert _raw_comparisons("ok = abs(w) < Fraction(ruleset.aggregation.theta)\n") == []


# --- TA G1: no rule parameter in the engine ---------------------------------------------------

#: Freeze pack 2.3 window lengths, plus 0 and 1 (indices, ``exp(x) - 1``).
ENGINE_INTS = frozenset({0, 1, 3, 5, 20, 60, 120})


def _numeric_literals(source: str) -> list[object]:
    return [
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    ]


def test_the_engine_holds_no_rule_parameter_value() -> None:
    literals = _numeric_literals((OUTLOOK_ROOT / "engine.py").read_text(encoding="utf-8"))
    assert [v for v in literals if isinstance(v, float)] == []
    assert set(literals) <= ENGINE_INTS
    # theta (2), the vote thresholds and the gate (0.5, 1.5) and the weights (1.0)
    # live in the rule files only.
    assert {2, 0.5, 1.5} & set(literals) == set()


@pytest.mark.parametrize("probe", ["if abs(w) < 2: pass\n", "x = z > 0.5\n", "g = r <= 1.5\n"])
def test_the_literal_scan_has_teeth(probe: str) -> None:
    literals = _numeric_literals(probe)
    assert [v for v in literals if isinstance(v, float)] or not set(literals) <= ENGINE_INTS


# --- TA Q1: one condition language ---------------------------------------------------------------

PARSER_PATTERN = re.compile(
    r"""\.split\(\s*["']\s*(or|and|OR|AND|\|\||&&)\s*["']|\beval\(|\bexec\(|literal_eval"""
)


def test_app_has_no_second_expression_parser() -> None:
    hits = {path for path, source in _sources(APP_ROOT).items() if PARSER_PATTERN.search(source)}
    assert hits == set()


@pytest.mark.parametrize(
    "probe",
    [
        'parts = text.split(" or ")',
        "parts = text.split(' and ')",
        "value = eval(expr)",
        "value = ast.literal_eval(expr)",
    ],
)
def test_the_parser_scan_has_teeth(probe: str) -> None:
    assert PARSER_PATTERN.search(probe)


def _comparison_table_keys(source: str, name: str) -> set[str]:
    """The string keys of the module-level dict literal bound to ``name``."""
    for node in ast.parse(source).body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        if isinstance(target, ast.Name) and target.id == name:
            assert isinstance(value, ast.Dict)
            return {
                key.value
                for key in value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
    raise AssertionError(f"{name} is not bound at module level")


def test_the_outlook_and_advice_comparison_tables_have_one_key_set() -> None:
    # qa medium (2026-11-15): K-2 forbids outlook importing app.advice, so the two
    # operator tables are separate; their keys must stay the same set, and equal
    # to the rule model's ComparisonOp literal.
    outlook = _comparison_table_keys((OUTLOOK_ROOT / "engine.py").read_text("utf-8"), "_OPS")
    advice = _comparison_table_keys(
        (APP_ROOT / "advice" / "engine.py").read_text("utf-8"), "COMPARISON_OPS"
    )
    assert outlook == advice == set(_OPS) == set(COMPARISON_OPS) == set(get_args(ComparisonOp))
    assert len(outlook) == 8


def test_the_comparison_table_scan_has_teeth() -> None:
    assert _comparison_table_keys('T = {"gt": f, "lt": g}\n', "T") == {"gt", "lt"}
    with pytest.raises(AssertionError):
        _comparison_table_keys("U = 1\n", "T")


def test_pit_item_is_defined_once_and_names_the_ledger_column() -> None:
    # ADR-0030 supplement 2 point 4; TA 2026-11-15 qa check.
    assert PIT_ITEM == "inputs_max_fetched_at"
    holders = {
        path
        for path, source in _sources(APP_ROOT).items()
        if re.search(r"^\s*PIT_ITEM\b[^=\n]*=", source, re.M)
    }
    assert holders == {"outlook/engine.py"}
    literal = {
        path
        for path, source in _sources(APP_ROOT / "outlook").items()
        if '"inputs_max_fetched_at"' in source
    }
    assert literal == {"outlook/engine.py"}


def test_holds_is_defined_once() -> None:
    holders = {
        path
        for path, source in _sources(APP_ROOT).items()
        if re.search(r"^def holds\(", source, re.M)
    }
    assert holders == {"outlook/engine.py"}


# --- K-2 -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "package",
    [
        "app.api",
        "app.demo",
        "app.positions",
        "app.portfolio",
        "app.backtest",
        "app.research",
        "app.sectors",
        "app.data.market_panel",
        "app.ops_alert",
        "app.forecast",
        "app.advice",
        "app.services",
    ],
)
def test_the_outlook_reaches_none_of_the_forbidden_packages(package: str) -> None:
    modules = tuple(
        "app.outlook." + path.stem
        for path in sorted(OUTLOOK_ROOT.glob("*.py"))
        if path.stem != "__init__"
    )
    assert offenders(reachable_app_modules(modules), package) == []
