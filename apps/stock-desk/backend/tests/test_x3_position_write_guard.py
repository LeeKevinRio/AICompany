"""X-3b KX-9: every production write through ``PositionStore.create`` / ``update``.

``PositionStore.create`` and ``update`` accept a plain :class:`PositionInput`,
which carries no market/currency rule (ADR-0017 C3) -- deliberately, so a
legacy row stays readable and a test can still build one (PR-0 T1, ADR-0017
T-11). The rule therefore lives at the doors, and this module pins the doors:

* an AST scan of ``app/`` lists every call that could be one of the two store
  writes, and the list must equal :data:`KNOWN_WRITE_CALLS` -- a new caller
  fails here until someone classifies it (task X-3, X3-F2);
* each known caller's ``data`` argument must come from where its class says:
  a handler parameter typed :class:`PositionWriteInput`, the rows
  :func:`parse_import_csv` returned, or the demo seed's matched constants.

The store's signature is left alone on purpose (KX-9). Residual blind spots,
stated rather than hidden: a write reached through an alias
(``write = store.create``) or ``getattr``, or raw SQL against ``positions``,
is not a ``.create``/``.update`` call and is not seen by this scan.
"""

from __future__ import annotations

import ast
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.demo import seed as seed_module
from app.positions.csv_io import build_template_csv, parse_import_csv
from app.positions.models import PositionWriteInput, currency_matches_market
from tests.import_graph import APP_ROOT

#: Where each production store write lives, keyed by
#: ``(path under app/, enclosing function, method)``, and how its ``data``
#: argument is vouched for. A call found by the scan and absent here fails the
#: suite; so does an entry here whose call no longer exists.
KNOWN_WRITE_CALLS: dict[tuple[str, str, str], str] = {
    ("api/positions.py", "create_position", "create"): "write_input_parameter",
    ("api/positions.py", "update_position", "update"): "write_input_parameter",
    ("api/positions.py", "import_positions", "create"): "csv_import",
    ("demo/seed.py", "seed_demo", "create"): "demo_constants",
}

STORE_WRITE_METHODS = frozenset({"create", "update"})
#: Keyword names of ``PositionStore.update``; any of them on an ``.update``
#: call makes it a candidate even with fewer than two positional arguments.
_UPDATE_KEYWORDS = frozenset({"position_id", "data", "now"})


@dataclass(frozen=True)
class WriteCall:
    """One call that could be ``PositionStore.create`` / ``update``."""

    path: str
    function: str
    method: str
    lineno: int
    call: ast.Call
    scope: ast.AST

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.path, self.function, self.method)

    def where(self) -> str:
        return f"{self.path}:{self.lineno} {self.function}() .{self.method}(...)"


def _could_be_store_write(call: ast.Call, method: str) -> bool:
    """Over-approximate: ``.create(...)`` always; ``.update(...)`` unless its
    shape rules the store out (``dict.update(x)``, ``digest.update(b)``,
    ``values.update(k=v)`` take one positional argument or keywords only)."""
    if method == "create":
        return True
    if any(isinstance(arg, ast.Starred) for arg in call.args):
        return True
    if any(keyword.arg is None or keyword.arg in _UPDATE_KEYWORDS for keyword in call.keywords):
        return True
    return len(call.args) >= 2


class _Collector(ast.NodeVisitor):
    def __init__(self, path: str, module: ast.Module) -> None:
        self.path = path
        self.stack: list[tuple[str, ast.AST]] = [("<module>", module)]
        self.found: list[WriteCall] = []

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.stack.append((node.name, node))
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in STORE_WRITE_METHODS
            and _could_be_store_write(node, func.attr)
        ):
            name, scope = self.stack[-1]
            self.found.append(WriteCall(self.path, name, func.attr, node.lineno, node, scope))
        self.generic_visit(node)


def _module(root: Path, path: str) -> ast.Module:
    return ast.parse((root / path).read_text(encoding="utf-8"))


def scan_write_calls(root: Path) -> list[WriteCall]:
    calls: list[WriteCall] = []
    for file in sorted(root.rglob("*.py")):
        relative = file.relative_to(root).as_posix()
        module = ast.parse(file.read_text(encoding="utf-8"))
        collector = _Collector(relative, module)
        collector.visit(module)
        calls.extend(collector.found)
    return calls


def unregistered(calls: list[WriteCall], registry: dict[tuple[str, str, str], str]) -> list[str]:
    return [call.where() for call in calls if call.key not in registry]


def stale(calls: list[WriteCall], registry: dict[tuple[str, str, str], str]) -> list[str]:
    present = {call.key for call in calls}
    return [
        f"{path} {function}() .{method}"
        for path, function, method in registry
        if (path, function, method) not in present
    ]


def _data_argument(call: WriteCall) -> ast.expr | None:
    """The expression bound to ``data`` (``create(data)``, ``update(id, data)``)."""
    for keyword in call.call.keywords:
        if keyword.arg == "data":
            return keyword.value
    index = 0 if call.method == "create" else 1
    leading = call.call.args[: index + 1]
    if len(leading) > index and not any(isinstance(arg, ast.Starred) for arg in leading):
        return leading[index]
    return None


def _imports(module: ast.Module, source: str, name: str) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == source
        and any(alias.name == name and alias.asname is None for alias in node.names)
        for node in module.body
    )


def _loops_over(scope: ast.AST, target: str, call: ast.Call) -> list[ast.For]:
    """The ``for <target> in ...`` loops in ``scope`` whose body holds ``call``."""
    return [
        node
        for node in ast.walk(scope)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == target
        and any(inner is call for stmt in node.body for inner in ast.walk(stmt))
    ]


def _is_call_to(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name


def _bindings(scope: ast.AST, name: str) -> list[ast.Name]:
    """Every place ``scope`` assigns ``name`` (assignment, loop or walrus target)."""
    return [
        node
        for node in ast.walk(scope)
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Store)
    ]


def _loop_variable(call: WriteCall) -> tuple[str, ast.For] | str:
    """``(name, loop)`` when ``data`` is the target of the one loop around the call."""
    data = _data_argument(call)
    if not isinstance(data, ast.Name):
        return "data is not a loop variable"
    loops = _loops_over(call.scope, data.id, call.call)
    if len(loops) != 1 or _bindings(call.scope, data.id) != [loops[0].target]:
        return f"data {data.id!r} is not bound by exactly one loop around the write"
    return data.id, loops[0]


def _check_write_input_parameter(module: ast.Module, call: WriteCall) -> str | None:
    data = _data_argument(call)
    scope = call.scope
    if not isinstance(data, ast.Name) or not isinstance(
        scope, ast.FunctionDef | ast.AsyncFunctionDef
    ):
        return "data is not a parameter of the handler"
    params = scope.args.posonlyargs + scope.args.args + scope.args.kwonlyargs
    param = next((arg for arg in params if arg.arg == data.id), None)
    if param is None:
        return f"data {data.id!r} is not a parameter of {scope.name}()"
    if _bindings(scope, data.id):
        return f"parameter {data.id!r} is reassigned before the write"
    annotation = param.annotation
    if not (isinstance(annotation, ast.Name) and annotation.id == "PositionWriteInput"):
        return f"parameter {data.id!r} is not annotated PositionWriteInput"
    if not _imports(module, "app.positions.models", "PositionWriteInput"):
        return "PositionWriteInput is not the one from app.positions.models"
    return None


def _check_csv_import(module: ast.Module, call: WriteCall) -> str | None:
    found = _loop_variable(call)
    if isinstance(found, str):
        return found
    _, loop = found
    if not isinstance(loop.iter, ast.Name):
        return "the loop does not iterate over a list of parsed rows"
    rows = loop.iter.id
    sourced = [
        node
        for node in ast.walk(call.scope)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Tuple)
        and node.targets[0].elts
        and isinstance(node.targets[0].elts[0], ast.Name)
        and node.targets[0].elts[0].id == rows
        and _is_call_to(node.value, "parse_import_csv")
    ]
    if len(sourced) != 1:
        return f"{rows!r} is not the rows parse_import_csv(...) returned"
    first = sourced[0].targets[0]
    assert isinstance(first, ast.Tuple)
    if _bindings(call.scope, rows) != [first.elts[0]]:
        return f"{rows!r} is reassigned after parse_import_csv(...)"
    if not _imports(module, "app.positions.csv_io", "parse_import_csv"):
        return "parse_import_csv is not the one from app.positions.csv_io"
    return None


def _check_demo_constants(module: ast.Module, call: WriteCall) -> str | None:
    found = _loop_variable(call)
    if isinstance(found, str):
        return found
    name, loop = found
    if not _is_call_to(loop.iter, "_position_inputs"):
        return f"data {name!r} is not taken from _position_inputs(...)"
    builder = next(
        (
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "_position_inputs"
        ),
        None,
    )
    if builder is None:
        return "_position_inputs is not defined in the module"
    built = [
        node
        for node in ast.walk(builder)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"PositionInput", "PositionWriteInput"}
    ]
    if not built:
        return "_position_inputs builds no position"
    for node in built:
        keywords = {kw.arg: kw.value for kw in node.keywords}
        market, currency = keywords.get("market"), keywords.get("currency")
        if node.args or not (
            isinstance(market, ast.Name)
            and market.id == "DEMO_MARKET"
            and isinstance(currency, ast.Name)
            and currency.id == "DEMO_CURRENCY"
        ):
            return "a demo position is not built from DEMO_MARKET / DEMO_CURRENCY"
    return None


_CHECKS = {
    "write_input_parameter": _check_write_input_parameter,
    "csv_import": _check_csv_import,
    "demo_constants": _check_demo_constants,
}


def provenance_violations(
    root: Path, calls: list[WriteCall], registry: dict[tuple[str, str, str], str]
) -> list[str]:
    problems: list[str] = []
    for call in calls:
        kind = registry.get(call.key)
        if kind is None:
            continue
        problem = _CHECKS[kind](_module(root, call.path), call)
        if problem is not None:
            problems.append(f"{call.where()}: {problem}")
    return problems


# --- the real tree ---------------------------------------------------------


def test_every_store_write_in_app_is_a_known_caller() -> None:
    calls = scan_write_calls(APP_ROOT)
    assert unregistered(calls, KNOWN_WRITE_CALLS) == []
    assert stale(calls, KNOWN_WRITE_CALLS) == []


def test_each_known_caller_hands_the_store_a_checked_row() -> None:
    calls = scan_write_calls(APP_ROOT)
    assert provenance_violations(APP_ROOT, calls, KNOWN_WRITE_CALLS) == []


def test_the_demo_constants_are_a_matched_pair() -> None:
    assert currency_matches_market(seed_module.DEMO_MARKET, seed_module.DEMO_CURRENCY)


def test_the_csv_door_returns_only_write_model_rows_and_refuses_a_mismatch() -> None:
    template = build_template_csv()
    header = template.splitlines()[0]
    columns = header.split(",")

    def row(**cells: str) -> str:
        return ",".join(cells.get(column, "") for column in columns)

    base = {
        "quantity": "10",
        "avg_cost": "100",
        "opened_at": "2024-01-02",
        "instrument_type": "stock",
    }
    text = "\n".join(
        [
            header,
            row(symbol="2330", market="TW", currency="TWD", **base),
            row(symbol="AAPL", market="US", currency="USD", **base),
            row(symbol="MSFT", market="US", currency="TWD", **base),
            row(symbol="2317", market="TW", currency="USD", **base),
        ]
    )
    inputs, errors = parse_import_csv(text)
    assert [item.symbol for item in inputs] == ["2330", "AAPL"]
    assert all(type(item) is PositionWriteInput for item in inputs)
    assert all(currency_matches_market(item.market, item.currency) for item in inputs)
    assert sorted({error.field for error in errors}) == ["currency"]
    assert len(errors) == 2


def test_the_scan_sees_the_known_callers_it_claims_to() -> None:
    # Not vacuous: the four production writes are found where the registry says.
    keys = [call.key for call in scan_write_calls(APP_ROOT)]
    assert sorted(keys) == sorted(KNOWN_WRITE_CALLS)


# --- guard the guard -------------------------------------------------------


def _mirror(tmp_path: Path, *paths: str) -> Path:
    root = tmp_path / "app"
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(APP_ROOT / path, target)
    return root


def _rewrite(root: Path, path: str, old: str, new: str) -> None:
    file = root / path
    text = file.read_text(encoding="utf-8")
    assert old in text, f"fixture drifted: {old!r} not in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


@pytest.mark.parametrize(
    "source",
    [
        "def sneak(store, row):\n    store.create(row)\n",
        "def sneak(store, row):\n    store.update(1, row)\n",
        "def sneak(store, row):\n    store.update(1, data=row)\n",
        "def sneak(store, row):\n    store.update(position_id=1, data=row)\n",
        "def sneak(store, args):\n    store.update(*args)\n",
        "async def sneak(store, row):\n    store.create(row, now=None)\n",
        "class Sync:\n    def run(self, row):\n        self._store.create(row)\n",
    ],
)
def test_a_new_caller_is_caught(tmp_path: Path, source: str) -> None:
    root = tmp_path / "app"
    (root / "broker").mkdir(parents=True)
    (root / "broker" / "sync.py").write_text(source, encoding="utf-8")
    found = unregistered(scan_write_calls(root), KNOWN_WRITE_CALLS)
    assert len(found) == 1
    assert found[0].startswith("broker/sync.py:")


@pytest.mark.parametrize(
    "source",
    [
        "def f(d, x):\n    d.update(x)\n",
        "def f(digest, b):\n    digest.update(b)\n",
        "def f(values):\n    values.update(win_rate=1, payoff_ratio=2)\n",
        "def f(store, rule):\n    store.create_rule(rule)\n",
    ],
)
def test_ordinary_updates_are_not_mistaken_for_store_writes(tmp_path: Path, source: str) -> None:
    root = tmp_path / "app"
    root.mkdir()
    (root / "other.py").write_text(source, encoding="utf-8")
    assert scan_write_calls(root) == []


def test_a_removed_caller_leaves_a_stale_entry(tmp_path: Path) -> None:
    root = _mirror(tmp_path, "api/positions.py", "demo/seed.py")
    _rewrite(root, "api/positions.py", "    return store.create(body)\n", "    return body\n")
    assert stale(scan_write_calls(root), KNOWN_WRITE_CALLS) == [
        "api/positions.py create_position() .create"
    ]


@pytest.mark.parametrize(
    ("path", "old", "new"),
    [
        # POST accepting the rule-free base model.
        (
            "api/positions.py",
            "    body: PositionWriteInput,\n    store: StoreDep,\n) -> Position:\n"
            "    return store.create(body)",
            "    body: PositionInput,\n    store: StoreDep,\n) -> Position:\n"
            "    return store.create(body)",
        ),
        # PUT storing something other than the validated body.
        (
            "api/positions.py",
            "store.update(position_id, body)",
            "store.update(position_id, body.model_copy())",
        ),
        # CSV rows that did not come out of the importer.
        (
            "api/positions.py",
            "inputs, errors = parse_import_csv(text)",
            "inputs, errors = _lenient_parse(text)",
        ),
        # CSV rows reassigned after parsing.
        (
            "api/positions.py",
            "    for position in inputs:\n",
            "    inputs = [PositionInput(**p.model_dump()) for p in inputs]\n"
            "    for position in inputs:\n",
        ),
        # Demo seed with a currency that is not the paired constant.
        (
            "demo/seed.py",
            "avg_cost=anchor.close,\n                currency=DEMO_CURRENCY,",
            'avg_cost=anchor.close,\n                currency="USD",',
        ),
        # Demo seed writing something other than the built inputs.
        (
            "demo/seed.py",
            "for data in _position_inputs(bars_by_symbol):",
            "for data in _other_inputs(bars_by_symbol):",
        ),
    ],
)
def test_a_known_caller_that_loses_its_check_is_caught(
    tmp_path: Path, path: str, old: str, new: str
) -> None:
    root = _mirror(tmp_path, "api/positions.py", "demo/seed.py")
    _rewrite(root, path, old, new)
    calls = scan_write_calls(root)
    assert unregistered(calls, KNOWN_WRITE_CALLS) == []
    assert len(provenance_violations(root, calls, KNOWN_WRITE_CALLS)) == 1


def test_the_unmodified_mirror_is_clean(tmp_path: Path) -> None:
    # The mutations above are judged against this baseline, not against noise.
    root = _mirror(tmp_path, "api/positions.py", "demo/seed.py")
    calls = scan_write_calls(root)
    assert unregistered(calls, KNOWN_WRITE_CALLS) == []
    assert stale(calls, KNOWN_WRITE_CALLS) == []
    assert provenance_violations(root, calls, KNOWN_WRITE_CALLS) == []
