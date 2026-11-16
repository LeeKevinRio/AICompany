"""``app.outlook.engine.MISSING_CODES``: the freeze pack 2.5 point 4 codes, defined once.

tech-architect's ruling (ADR-0030 supplement 5 point 3 (c), option A): four
rows, five codes, in the table's order; defined only in ``engine.py``; every
missing item ``engine.py`` builds names one of its constants (AST); and on
every synthetic result the codes are in the set, at most one ``E-VOL-*`` and
in non-decreasing table order. Synthetic data only.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal
from typing import get_args

import pytest

from app.outlook import engine
from app.outlook.basket import E_ADJ_COVERAGE
from app.outlook.engine import MISSING_CODES, evaluate_outlook
from app.outlook.inputs import SnapshotBar, late_cutoff_at
from app.outlook.volatility import E_VOL_DEGENERATE, E_VOL_SHORT, VolatilityMissingCode
from tests.import_graph import APP_ROOT
from tests.outlook_helpers import bars_from_closes, definition, fixture_bars, ruleset, with_close

#: The four rows of the 2.5 table, each with its codes (row 3: one rank, two codes).
ROWS: tuple[tuple[str, ...], ...] = (
    (engine.E_BARS_SHORT,),
    (engine.E_PRICE_UNUSABLE,),
    get_args(VolatilityMissingCode),
    (engine.E_PIT_UNVERIFIED,),
)
RANK = {code: rank for rank, row in enumerate(ROWS) for code in row}


# --- C1: the set ----------------------------------------------------------------------------


def test_the_set_is_four_rows_five_codes_in_table_order() -> None:
    assert MISSING_CODES == (
        engine.E_BARS_SHORT,
        engine.E_PRICE_UNUSABLE,
        E_VOL_SHORT,
        E_VOL_DEGENERATE,
        engine.E_PIT_UNVERIFIED,
    )
    assert tuple(code for row in ROWS for code in row) == MISSING_CODES
    assert len(ROWS) == 4 and len(MISSING_CODES) == len(set(MISSING_CODES)) == 5
    assert E_ADJ_COVERAGE not in MISSING_CODES


def test_the_set_is_defined_only_in_engine_py() -> None:
    owners = set()
    for path in sorted(APP_ROOT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            if any(isinstance(t, ast.Name) and t.id == "MISSING_CODES" for t in targets):
                owners.add(path.relative_to(APP_ROOT).as_posix())
    assert owners == {"outlook/engine.py"}


# --- C2: every missing item names one of the constants --------------------------------------

#: The constant names whose values make up :data:`MISSING_CODES`.
CODE_NAMES = frozenset(
    {"E_BARS_SHORT", "E_PRICE_UNUSABLE", "E_VOL_SHORT", "E_VOL_DEGENERATE", "E_PIT_UNVERIFIED"}
)


def _item_first_arguments(source: str) -> list[ast.expr]:
    return [
        node.args[0] if node.args else ast.Constant(None)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_item"
    ]


def _item_problems(source: str) -> list[str]:
    """Each ``_item(`` call whose first argument is not a name of :data:`CODE_NAMES`."""
    return [
        ast.unparse(arg)
        for arg in _item_first_arguments(source)
        if not (isinstance(arg, ast.Name) and arg.id in CODE_NAMES)
    ]


def test_every_missing_item_of_the_engine_names_a_code_constant() -> None:
    source = (APP_ROOT / "outlook" / "engine.py").read_text(encoding="utf-8")
    assert len(_item_first_arguments(source)) == 5
    assert _item_problems(source) == []
    # The names resolve to exactly the set's values.
    assert {getattr(engine, name) for name in CODE_NAMES} == set(MISSING_CODES)


def test_the_engine_compares_no_missing_code_as_a_string_literal() -> None:
    tree = ast.parse((APP_ROOT / "outlook" / "engine.py").read_text(encoding="utf-8"))
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value in MISSING_CODES
    ]
    # Only the three definitions in engine.py itself; the E-VOL-* ones come from volatility.
    assert sorted(literals) == sorted(
        [engine.E_BARS_SHORT, engine.E_PRICE_UNUSABLE, engine.E_PIT_UNVERIFIED]
    )


@pytest.mark.parametrize(
    "source",
    [
        "_item('E-VOL-SHORT', 'sigma_d', as_of=d)\n",
        "_item(sigma.missing_code, 'sigma_d', as_of=d)\n",
        "_item(E_ADJ_COVERAGE, 'x', as_of=d)\n",
        "_item(code='E-BARS-SHORT', item='index_bars', as_of=d)\n",
    ],
)
def test_the_item_scan_has_teeth(source: str) -> None:
    assert _item_problems(source) != []


# --- C3: every synthetic result -------------------------------------------------------------


def missing_list_problems(codes: Sequence[str]) -> list[str]:
    """2.5 point 4 on one record's codes: in the set, one ``E-VOL-*`` at most, table order."""
    found = [f"not in the set: {code}" for code in codes if code not in MISSING_CODES]
    volatility = [code for code in codes if code in get_args(VolatilityMissingCode)]
    if len(volatility) > 1:
        found.append("more than one E-VOL-*")
    ranks = [RANK[code] for code in codes if code in RANK]
    if ranks != sorted(ranks):
        found.append("not in table order")
    if len(set(codes)) != len(codes):
        found.append("a code twice")
    return found


def _cases() -> list[list[SnapshotBar]]:
    cases = [fixture_bars(name) for name in ("FX-A", "FX-B", "FX-C", "FX-D", "FX-E1", "FX-E2")]
    cases += [fixture_bars("FX-B")[-n:] for n in (1, 2, 30, 56, 61, 120, 121)]
    cases.append(bars_from_closes([10000.0] * 315))  # E-VOL-DEGENERATE
    cases.append(with_close(fixture_bars("FX-B"), 30, Decimal("0.0")))
    every = with_close(with_close(fixture_bars("FX-A")[-56:], 1, Decimal("0")), 5, Decimal("0"))
    every[-1] = replace(every[-1], fetched_at=late_cutoff_at(every[-1].session_date))
    cases.append(every)  # four rows at once
    pit = fixture_bars("FX-B")
    pit[-1] = replace(pit[-1], fetched_at=late_cutoff_at(pit[-1].session_date))
    cases.append(pit)
    return cases


def test_every_synthetic_result_keeps_the_codes_in_the_set_and_in_order() -> None:
    seen: set[str] = set()
    for bars in _cases():
        for horizon in (3, 5):
            evaluation = evaluate_outlook(
                bars,
                data_as_of=bars[-1].session_date,
                ruleset=ruleset(horizon),
                definition=definition(),
                horizon=horizon,
            )
            codes = [item.code for item in evaluation.missing]
            assert missing_list_problems(codes) == []
            seen |= set(codes)
    # The cases reach every code, so the checks above are not vacuous.
    assert seen == set(MISSING_CODES)


@pytest.mark.parametrize(
    ("codes", "problem"),
    [
        pytest.param([E_ADJ_COVERAGE], "not in the set", id="basket-code"),
        pytest.param([E_VOL_SHORT, E_VOL_DEGENERATE], "more than one E-VOL-*", id="two-vol"),
        pytest.param(
            [engine.E_PIT_UNVERIFIED, engine.E_BARS_SHORT], "not in table order", id="order"
        ),
        pytest.param([engine.E_BARS_SHORT, engine.E_BARS_SHORT], "a code twice", id="twice"),
    ],
)
def test_the_missing_list_check_has_teeth(codes: list[str], problem: str) -> None:
    assert any(p.startswith(problem) for p in missing_list_problems(codes))
