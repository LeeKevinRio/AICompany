"""ADR-0012 T-18 / C-15: forward returns, labels and cost deductions live in two files.

AST scan of every module under ``app/``: a function, variable, attribute,
dataclass field or parameter whose name matches ``forward_return*``,
``excess_gross``, ``excess_net``, ``label_return*`` or ``round_trip_cost`` may
only be *defined* in ``app/backtest/basket.py``, ``app/backtest/sector_eval.py``,
``app/research/**`` -- plus the pre-v4 whitelist ``app/backtest/event_study.py``
(its ``forward_returns`` is unreachable from ``app.sectors`` by C-2).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.import_graph import APP_ROOT

PATTERN = re.compile(
    r"^(forward_return\w*|excess_gross|excess_net|label_return\w*|round_trip_cost)$"
)
ALLOWED_FILES = frozenset(
    {"backtest/basket.py", "backtest/sector_eval.py", "backtest/event_study.py"}
)
ALLOWED_DIRS = ("research",)


def _targets(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, ast.Tuple | ast.List):
        return [name for element in node.elts for name in _targets(element)]
    if isinstance(node, ast.Starred):
        return _targets(node.value)
    return []


def defined_names(path: Path) -> set[str]:
    """Names this file defines: functions, classes, assignments, fields, parameters."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(_targets(target))
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            names.update(_targets(node.target))
        elif isinstance(node, ast.NamedExpr):
            names.update(_targets(node.target))
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.For | ast.AsyncFor | ast.comprehension):
            names.update(_targets(node.target))
        elif isinstance(node, ast.alias) and node.asname:
            names.add(node.asname)
    return names


def offenders(root: Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if str(relative) in ALLOWED_FILES or (relative.parts and relative.parts[0] in ALLOWED_DIRS):
            continue
        hits = sorted(name for name in defined_names(path) if PATTERN.match(name))
        if hits:
            found[str(relative)] = hits
    return found


def test_label_and_cost_identifiers_are_defined_only_in_the_allowed_files() -> None:
    assert offenders(APP_ROOT) == {}


def test_the_allowed_files_really_define_them() -> None:
    basket = defined_names(APP_ROOT / "backtest" / "basket.py")
    evaluator = defined_names(APP_ROOT / "backtest" / "sector_eval.py")
    assert {"round_trip_cost", "excess_gross", "excess_net", "forward_return"} <= basket
    assert {"excess_net"} <= evaluator
    assert "forward_returns" in defined_names(APP_ROOT / "backtest" / "event_study.py")


@pytest.mark.parametrize(
    "source",
    [
        "def forward_returns(x):\n    return x\n",
        "excess_net = 1.0\n",
        "class Row:\n    round_trip_cost: float\n",
        "class Row:\n    def __init__(self):\n        self.label_return_5 = 0.0\n",
        "def f(excess_gross):\n    return excess_gross\n",
        "a, forward_return_h = 1, 2\n",
    ],
)
def test_identifier_scan_has_teeth(tmp_path: Path, source: str) -> None:
    (tmp_path / "sectors").mkdir()
    (tmp_path / "sectors" / "leak.py").write_text(source, encoding="utf-8")
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "fine.py").write_text("excess_net = 1\n", encoding="utf-8")
    assert list(offenders(tmp_path)) == ["sectors/leak.py"]


def test_identifier_scan_ignores_uses_that_define_nothing(tmp_path: Path) -> None:
    (tmp_path / "reader.py").write_text("value = sample.excess_net\n", encoding="utf-8")
    assert offenders(tmp_path) == {}
