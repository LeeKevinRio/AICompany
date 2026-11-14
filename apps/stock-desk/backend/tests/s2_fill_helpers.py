"""Builders shared by the N-177a S2 fill tests (ADR-0041, N-177 規格修訂一).

Offline like :mod:`tests.same_day_helpers`: every store is a fresh file under
``tmp_path`` and every line is logged the way ``/today`` logged before N-172a,
then claimed and settled the way ``_settle_pending`` does.
"""

from __future__ import annotations

import ast
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.playbook import store as store_module
from app.playbook.models import BatchState, Directive
from app.playbook.store import FILL_MOVES_TABLE, PlaybookStore
from tests.same_day_helpers import (
    START_CASH,
    TUESDAY,
    WEDNESDAY,
    buy_line,
    log_like_before_n172a,
)

#: app/, the tree the write-point checks read (N177-T18, T19).
APP_ROOT = Path(store_module.__file__).resolve().parents[1]


# --- builders ---------------------------------------------------------------------------


def s2_line(
    shares: int,
    *,
    symbol: str = "2330",
    data_date: date = TUESDAY,
    execution_date: date = WEDNESDAY,
    reference: str = "80",
) -> Directive:
    """An S2 shaped like the engine's: whole symbol, no batch, no band (engine.py S2)."""
    return Directive(
        symbol=symbol,
        batch_no=None,
        action="sell",
        shares=shares,
        rule_id="S2",
        rule_summary="S2 整檔停損",
        data_date=data_date,
        execution_date=execution_date,
        reference_price=Decimal(reference),
        limit_low=None,
        limit_high=None,
        limit_note="停損無滑價帶",
        data_status="fresh",
        source="fake",
    )


def stop_line(batch_no: int, shares: int, *, rule_id: str = "S1") -> Directive:
    """A per-batch stop sell of ``batch_no`` due on Wednesday, no band."""
    return buy_line(batch_no=batch_no, shares=shares).model_copy(
        update={"action": "sell", "rule_id": rule_id, "limit_low": None, "limit_high": None}
    )


def fresh_store(tmp_path: Path, name: str = "playbook.db") -> PlaybookStore:
    store = PlaybookStore(db_path=tmp_path / name)
    store.ensure_batches(["2330"], batches_per_target=3)
    store.set_capital(cash=START_CASH, total_deploy=START_CASH, source="initial")
    return store


def log_one(store: PlaybookStore, line: Directive) -> int:
    """Append ``line`` to the log and return its row id."""
    before = {item.directive_id for item in store.pending_directives()}
    log_like_before_n172a(store, [line])
    (new,) = [
        item.directive_id for item in store.pending_directives() if item.directive_id not in before
    ]
    return new


def claim_and_settle(store: PlaybookStore, line: Directive, price: str) -> int:
    """What ``_settle_pending`` does for one line that filled at ``price``."""
    directive_id = log_one(store, line)
    assert store.claim_directive(directive_id, status="executed", open_price=Decimal(price))
    store.settle(
        line.model_copy(update={"status": "executed"}),
        fill_price=Decimal(price),
        directive_id=directive_id,
    )
    return directive_id


def moves(db_path: Path) -> list[tuple[Any, ...]]:
    """``(directive_id, symbol, batch_no, shares_moved, price, source)`` of every audit row."""
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(
            "SELECT directive_id, symbol, batch_no, shares_moved, price, source "
            f"FROM {FILL_MOVES_TABLE} ORDER BY id"
        ).fetchall()


def state_map(db_path: Path) -> dict[str, str]:
    with closing(sqlite3.connect(db_path)) as conn:
        return {str(k): str(v) for k, v in conn.execute("SELECT key, value FROM playbook_state")}


def batch_cells(store: PlaybookStore) -> list[dict[str, Any]]:
    """Every batch row, every column (``updated_at`` aside)."""
    return [batch.model_dump() for batch in store.list_batches()]


def dump(db_path: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every ``playbook_*`` table, every row."""
    with closing(sqlite3.connect(db_path)) as conn:
        names = [
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'playbook_%' "
                "ORDER BY name"
            )
        ]
        return {name: conn.execute(f"SELECT * FROM {name}").fetchall() for name in names}


def directive_row(db_path: Path, directive_id: int) -> tuple[Any, ...]:
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute(
            "SELECT settled, status FROM playbook_directives WHERE id = ?", (directive_id,)
        ).fetchone()
    assert row is not None
    return tuple(row)


def cash(store: PlaybookStore) -> Decimal:
    return store.portfolio_state().cash


def batch(store: PlaybookStore, batch_no: int, symbol: str = "2330") -> BatchState:
    found = store.get_batch(symbol, batch_no)
    assert found is not None
    return found


def trace(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    """``(connection number, sql)`` of every statement from here on."""
    statements: list[tuple[int, str]] = []
    real_connect = sqlite3.connect
    opened = iter(range(10_000))

    def tracing(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        number = next(opened)
        conn.set_trace_callback(lambda sql: statements.append((number, sql)))
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracing)
    return statements


_BOOK_TABLES = ("playbook_batches", "playbook_state", FILL_MOVES_TABLE)
_WRITES = ("INSERT", "UPDATE", "DELETE", "REPLACE")


def assert_one_locked_transaction(statements: list[tuple[int, str]]) -> None:
    """Every read and write of the book on one connection, between BEGIN IMMEDIATE and COMMIT."""
    book = [
        (index, number, sql)
        for index, (number, sql) in enumerate(statements)
        if any(table in sql for table in _BOOK_TABLES)
    ]
    assert book
    (lock,) = [index for index, (_, sql) in enumerate(statements) if sql == "BEGIN IMMEDIATE"]
    number = statements[lock][0]
    commit = next(
        index
        for index, (owner, sql) in enumerate(statements)
        if index > lock and owner == number and sql == "COMMIT"
    )
    assert all(owner == number and lock < index < commit for index, owner, _ in book)
    assert not [sql for _, sql in statements if "INSERT OR REPLACE INTO playbook_batches" in sql]


# --- reading the source (T18, T19) ------------------------------------------------------


def enclosing(tree: ast.AST) -> Iterator[tuple[str, ast.AST]]:
    """Every node with the name of the innermost def or module-level assignment around it."""

    def walk(node: ast.AST, owner: str) -> Iterator[tuple[str, ast.AST]]:
        for child in ast.iter_child_nodes(node):
            name = owner
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                name = child.name
            elif isinstance(child, ast.Assign) and owner == "<module>":
                name = ",".join(t.id for t in child.targets if isinstance(t, ast.Name))
            elif (
                isinstance(child, ast.AnnAssign)
                and owner == "<module>"
                and isinstance(child.target, ast.Name)
            ):
                name = child.target.id
            yield name, child
            yield from walk(child, name)

    yield from walk(tree, "<module>")


def sql_text(node: ast.AST) -> str | None:
    """The SQL an ``execute`` argument spells, ``{name}`` standing for each f-string field."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue):
                parts.append("{" + ast.unparse(value.value) + "}")
        return "".join(parts)
    return None


def app_trees() -> Iterator[tuple[Path, ast.Module]]:
    for path in sorted(APP_ROOT.rglob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def executed_sql() -> list[tuple[Path, str, str]]:
    found = []
    for path, tree in app_trees():
        for owner, node in enclosing(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"execute", "executemany", "executescript"}
                and node.args
            ):
                text = sql_text(node.args[0])
                if text is not None:
                    found.append((path, owner, " ".join(text.split())))
    return found


def set_columns(sql: str) -> set[str]:
    assignments = sql.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
    return {part.split("=", 1)[0].strip() for part in assignments.split(",")}


def calls(attr: str) -> list[tuple[str, str]]:
    return [
        (path.name, owner)
        for path, tree in app_trees()
        for owner, node in enclosing(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == attr)
            or (isinstance(node.func, ast.Name) and node.func.id == attr)
        )
    ]
