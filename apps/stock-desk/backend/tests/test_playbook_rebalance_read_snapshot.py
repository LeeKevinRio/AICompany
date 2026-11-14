"""N-196: the 季末 REBALANCE values the book from one read taken after the bars load.

Before N-196 ``rebalance`` read the batches, loaded the bars -- network,
seconds -- and only then read the cash, on another connection. A sell settled
in between was counted twice: its shares by the first read, its cash by the
second (ADR-0041 R-3′). The batches and the cash now come from
:meth:`PlaybookStore.read_rebalance_inputs`, one DEFERRED read transaction run
after the bars are loaded; the first ``list_batches`` only decides which bars
to load.

These tests pin, in the order of the spec (N196-T2～T7; T1 is the existing
``test_playbook_rebalance.py`` and N195-T1～T7, unchanged): a deterministic
interleaving with a concurrent settlement, a batch that appears after the bars
were loaded, the snapshot of the read transaction itself, the SQL a rebalance
sends, the call sites, and the delegating store reads.
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.data.interface import Market, ProviderResult
from app.playbook import service as service_module
from app.playbook import store as store_module
from app.playbook import wording
from app.playbook.models import BatchState, Directive
from app.playbook.service import REBALANCE_SOURCE, PlaybookService
from app.playbook.store import (
    STATE_CASH,
    STATE_TOTAL_DEPLOY,
    STATE_TOTAL_DEPLOY_SET_AT,
    STATE_TOTAL_DEPLOY_SOURCE,
    PlaybookStore,
    RebalanceRead,
)
from tests.api_helpers import FakePriceService, recent_bars
from tests.same_day_helpers import evaluation_of

SERIES_END = date(2026, 8, 14)
QUARTER_END = date(2026, 8, 11)
SETTLE_DAY = date(2026, 8, 12)
HISTORY = 40
CLOSE = Decimal("100")
OPEN_PRICE = Decimal("95")
HELD_SHARES = 100
START_CASH = Decimal("500000")
START_TOTAL_DEPLOY = Decimal("350000")
SYMBOL = "2330"
LATE_SYMBOL = "2317"

TOTAL_DEPLOY_KEYS = (STATE_TOTAL_DEPLOY, STATE_TOTAL_DEPLOY_SET_AT, STATE_TOTAL_DEPLOY_SOURCE)
APP_ROOT = Path(service_module.__file__).resolve().parents[1]
_FULL_BATCH_READ = "FROM playbook_batches ORDER BY symbol, batch_no"
_WRITES = ("INSERT", "UPDATE", "DELETE", "REPLACE")


class HookedPrices(FakePriceService):
    """A fake price service that runs ``hook`` once, on the first request for ``SYMBOL``.

    The hook runs before the bars are returned, inside ``_load_symbol_bars``:
    after ``rebalance``'s first ``list_batches`` and before the read that
    values the book (before the ``portfolio_state`` read of the pre-N-196 code).
    """

    def __init__(self) -> None:
        super().__init__()
        self.hook: Callable[[], None] | None = None
        self.fired = 0

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        if self.hook is not None and symbol == SYMBOL:
            hook, self.hook = self.hook, None
            self.fired += 1
            hook()
        return super().get_daily_bars(symbol, market, start, end)


@dataclass
class Desk:
    """Store A runs the rebalance; store B, on the same file, is the concurrent writer."""

    service: PlaybookService
    store_a: PlaybookStore
    store_b: PlaybookStore
    prices: HookedPrices
    db_path: Path


def _hold(store: PlaybookStore) -> None:
    """Batch 1 of 2330 open with 100 left and a cost; batches 2-3 planned."""
    store.ensure_batches([SYMBOL], batches_per_target=3)
    batch = store.get_batch(SYMBOL, 1)
    assert batch is not None
    store.save_batch(
        batch.model_copy(
            update={
                "status": "open",
                "entry_date": date(2026, 7, 1),
                "cost": Decimal("80"),
                "shares": HELD_SHARES,
                "remaining_shares": HELD_SHARES,
                "peak_close": CLOSE,
            }
        )
    )


def _desk(tmp_path: Path) -> Desk:
    db_path = tmp_path / "playbook.db"
    store_a = PlaybookStore(db_path=db_path)
    _hold(store_a)
    store_a.set_capital(cash=START_CASH, total_deploy=START_TOTAL_DEPLOY, source="initial")
    store_b = PlaybookStore(db_path=db_path)
    prices = HookedPrices()
    for symbol in (SYMBOL, LATE_SYMBOL):
        prices.seed(symbol, recent_bars([float(CLOSE)] * HISTORY, symbol=symbol, end=SERIES_END))
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=SERIES_END))
    service = PlaybookService(
        store=store_a,
        market_resolver={"TW": prices},
        index_resolver={"TW": index, "US": index},
    )
    return Desk(service, store_a, store_b, prices, db_path)


def _state_map(db_path: Path) -> dict[str, str]:
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute("SELECT key, value FROM playbook_state").fetchall()
    return {str(key): str(value) for key, value in rows}


def _line(*, batch_no: int | None, action: str, rule_id: str, shares: int) -> Directive:
    return Directive(
        symbol=SYMBOL,
        batch_no=batch_no,
        action=action,  # type: ignore[arg-type]
        shares=shares,
        rule_id=rule_id,  # type: ignore[arg-type]
        rule_summary="N-196 concurrent settlement",
        data_date=QUARTER_END,
        execution_date=SETTLE_DAY,
        reference_price=CLOSE,
        limit_low=None,
        limit_high=None,
        limit_note="",
        data_status="fresh",
        source="test",
    )


def _settler(store: PlaybookStore, line: Directive) -> Callable[[], None]:
    """Log ``line`` on ``store`` now; the returned hook claims and settles it at the open.

    The way ``_settle_pending`` does it (the N195-T3 harness): logged, claimed,
    then applied to the book with its log row id -- one ``BEGIN IMMEDIATE``
    after R-α (N-177a).
    """
    store.record_directives(evaluation_of(store, [line]))
    (pending,) = store.pending_directives()

    def settle() -> None:
        assert store.claim_directive(pending.directive_id, status="executed", open_price=OPEN_PRICE)
        store.settle(
            pending.directive.model_copy(update={"status": "executed"}),
            fill_price=OPEN_PRICE,
            directive_id=pending.directive_id,
        )

    return settle


def _deployed(batches: list[BatchState]) -> Decimal:
    return sum(
        (
            CLOSE * Decimal(batch.remaining_shares)
            for batch in batches
            if batch.status == "open" and batch.remaining_shares > 0
        ),
        Decimal("0"),
    )


# --- T2 deterministic interleaving -----------------------------------------------------

#: (line B settles, its cash movement, shares it moves out of the held batch).
_CONCURRENT_SETTLEMENTS: dict[str, tuple[Directive, Decimal, int]] = {
    "i_s1_sell_40": (
        _line(batch_no=1, action="sell", rule_id="S1", shares=40),
        OPEN_PRICE * 40,
        40,
    ),
    "ii_s2_sell_100_closes": (
        _line(batch_no=None, action="sell", rule_id="S2", shares=100),
        OPEN_PRICE * 100,
        100,
    ),
    "iii_planned_buy_100": (
        _line(batch_no=2, action="buy", rule_id="R1", shares=100),
        -OPEN_PRICE * 100,
        0,
    ),
}


@pytest.mark.parametrize("case", sorted(_CONCURRENT_SETTLEMENTS))
def test_t2_a_settlement_committed_while_the_bars_load_is_counted_once(
    tmp_path: Path, case: str
) -> None:
    desk = _desk(tmp_path)
    line, delta, moved = _CONCURRENT_SETTLEMENTS[case]
    settle = _settler(desk.store_b, line)
    after_hook: dict[str, Any] = {}

    def hook() -> None:
        settle()
        # The book as it stands once B has committed, read by a third instance.
        fresh = PlaybookStore(db_path=desk.db_path)
        after_hook["batches"] = fresh.list_batches()
        after_hook["cash"] = fresh.portfolio_state().cash

    desk.prices.hook = hook

    result = desk.service.rebalance(today=QUARTER_END)

    assert desk.prices.fired == 1
    cash_after: Decimal = after_hook["cash"]
    assert cash_after == START_CASH + delta
    deployed = _deployed(after_hook["batches"])
    # The settlement landed: 60 left (i), the batch closed (ii), batch 2 opened (iii).
    held_after = CLOSE * (HELD_SHARES - moved) + (CLOSE * 100 if delta < 0 else Decimal("0"))
    assert deployed == held_after
    if case.startswith("ii_"):
        assert [b.status for b in after_hook["batches"] if b.batch_no == 1] == ["closed"]
    ratio = desk.store_a.active_params(QUARTER_END).deploy_ratio
    assert result.status == "ok"
    assert result.total_assets == cash_after + deployed
    assert result.deployed_value == deployed
    assert result.new_total_deploy == result.total_assets * ratio
    state = PlaybookStore(db_path=desk.db_path).portfolio_state()
    assert state.total_deploy == result.new_total_deploy
    assert state.total_deploy_source == REBALANCE_SOURCE
    # N-195: the rebalance leaves the cash B wrote.
    assert state.cash == START_CASH + delta
    if moved:
        # (i), (ii): the pre-N-196 figure counted the sold shares twice; not over it.
        pre_n196 = (START_CASH + OPEN_PRICE * moved + CLOSE * HELD_SHARES) * ratio
        assert result.new_total_deploy < pre_n196
    else:
        # (iii): the pre-N-196 figure missed the batch the buy opened.
        pre_n196 = (START_CASH + delta + CLOSE * HELD_SHARES) * ratio
        assert result.new_total_deploy > pre_n196


# --- T3 a held batch the bars were not loaded for ------------------------------------------


@pytest.mark.parametrize("late_status", ["open", "planned"])
def test_t3_a_batch_appearing_after_the_bars_load_is_refused_not_loaded(
    tmp_path: Path, late_status: str
) -> None:
    desk = _desk(tmp_path)
    after_hook: dict[str, dict[str, str]] = {}

    def hook() -> None:
        # Fixture write on B: a target the first read did not see.
        desk.store_b.ensure_batches([LATE_SYMBOL], batches_per_target=1)
        if late_status == "open":
            late = desk.store_b.get_batch(LATE_SYMBOL, 1)
            assert late is not None
            desk.store_b.save_batch(
                late.model_copy(
                    update={
                        "status": "open",
                        "entry_date": date(2026, 7, 1),
                        "cost": Decimal("50"),
                        "shares": 10,
                        "remaining_shares": 10,
                        "peak_close": CLOSE,
                    }
                )
            )
        after_hook["state"] = _state_map(desk.db_path)

    desk.prices.hook = hook

    result = desk.service.rebalance(today=QUARTER_END)

    assert desk.prices.fired == 1
    # The late symbol's bars are seeded but were never asked for: no second load.
    assert [call[0] for call in desk.prices.calls] == [SYMBOL]
    if late_status == "planned":
        assert result.status == "ok"
        assert result.deployed_value == CLOSE * HELD_SHARES
        return
    assert result.status == "insufficient_data"
    assert result.message == wording.REBALANCE_BLOCKED.format(symbols=LATE_SYMBOL)
    assert LATE_SYMBOL in result.message
    assert result.total_assets is None and result.new_total_deploy is None
    assert result.previous_total_deploy == START_TOTAL_DEPLOY
    state = _state_map(desk.db_path)
    for key in (*TOTAL_DEPLOY_KEYS, STATE_CASH):
        assert state[key] == after_hook["state"][key]
    assert state == after_hook["state"]
    assert [row for row in desk.store_a.directive_log() if row["rule_id"] == "REBALANCE"] == []


# --- T4 the snapshot of the read transaction ------------------------------------------------


def test_t4_both_reads_come_from_one_snapshot_and_the_writer_is_not_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = _desk(tmp_path)
    with closing(sqlite3.connect(desk.db_path)) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    settle = _settler(desk.store_b, _line(batch_no=1, action="sell", rule_id="S1", shares=40))
    real = store_module._read_all_batches
    fired: list[float] = []

    def wrapped(conn: sqlite3.Connection) -> list[BatchState]:
        batches = real(conn)
        # Only inside the DEFERRED read transaction, and only once: list_batches'
        # autocommit read, or a re-entrant call while the hook runs, passes through.
        if not fired and conn.in_transaction:
            fired.append(0.0)
            started = time.monotonic()
            settle()
            fired[0] = time.monotonic() - started
        return batches

    monkeypatch.setattr(store_module, "_read_all_batches", wrapped)

    read = desk.store_a.read_rebalance_inputs()

    assert len(fired) == 1
    assert fired[0] < 1.0  # B committed without waiting on A's read transaction
    held = next(batch for batch in read.batches if batch.batch_no == 1)
    assert held.remaining_shares == HELD_SHARES
    assert read.portfolio.cash == START_CASH
    fresh = PlaybookStore(db_path=desk.db_path)
    after = fresh.get_batch(SYMBOL, 1)
    assert after is not None and after.remaining_shares == HELD_SHARES - 40
    assert fresh.portfolio_state().cash == START_CASH + OPEN_PRICE * 40


# --- T5 SQL trace ---------------------------------------------------------------------------


def test_t5_one_state_select_inside_the_post_load_read_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = _desk(tmp_path)
    events: list[tuple[int, str]] = []
    opened = iter(range(1, 10_000))

    def connect() -> sqlite3.Connection:
        conn = sqlite3.connect(desk.db_path, timeout=5)
        serial = next(opened)
        conn.set_trace_callback(lambda sql: events.append((serial, sql)))
        return conn

    monkeypatch.setattr(desk.store_a, "_connect", connect)

    def mark_load() -> None:
        events.append((0, "-- bars load"))

    desk.prices.hook = mark_load

    result = desk.service.rebalance(today=QUARTER_END)

    assert result.status == "ok"
    load = events.index((0, "-- bars load"))
    before = events[:load]
    # Before the load: one full batch SELECT and nothing else on the book.
    assert [sql for _, sql in before if "playbook_" in sql and _FULL_BATCH_READ not in sql] == []
    assert len([sql for _, sql in before if _FULL_BATCH_READ in sql]) == 1
    state_selects = [
        (index, conn)
        for index, (conn, sql) in enumerate(events)
        if sql.lstrip().upper().startswith("SELECT") and "playbook_state" in sql
    ]
    assert len(state_selects) == 1
    ((state_at, serial),) = state_selects
    on_conn = [(index, sql) for index, (conn, sql) in enumerate(events) if conn == serial]
    assert on_conn[0][1] == "BEGIN"
    assert on_conn[-1][1] == "COMMIT"
    begin_at, commit_at = on_conn[0][0], on_conn[-1][0]
    assert load < begin_at < state_at < commit_at
    inside = [sql for index, sql in on_conn if begin_at < index < commit_at]
    assert len(inside) == 2
    assert _FULL_BATCH_READ in inside[0]
    assert "playbook_state" in inside[1]
    assert not [sql for sql in inside if sql.lstrip().upper().startswith(_WRITES)]
    assert not [sql for _, sql in on_conn if "IMMEDIATE" in sql.upper()]
    # After the load, the full batch SELECT runs only inside that transaction.
    after = events[load + 1 :]
    assert [conn for conn, sql in after if _FULL_BATCH_READ in sql] == [serial]


# --- T6 call sites (AST) ------------------------------------------------------------------------


def _calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == name)
            or (isinstance(node.func, ast.Name) and node.func.id == name)
        )
    ]


def _function_tree(function: Callable[..., Any]) -> ast.AST:
    return ast.parse(inspect.cleandoc("\n" + inspect.getsource(function)))


def _assigned(tree: ast.AST, name: str) -> list[ast.Assign]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    ]


def test_t6_rebalance_reads_once_before_and_once_after_the_bars_load() -> None:
    tree = _function_tree(PlaybookService.rebalance)

    (listed_call,) = _calls_named(tree, "list_batches")
    (load_call,) = _calls_named(tree, "_load_symbol_bars")
    (read_call,) = _calls_named(tree, "read_rebalance_inputs")
    assert listed_call.lineno < load_call.lineno < read_call.lineno
    for name in ("portfolio_state", "get_batch", "_state_map"):
        assert _calls_named(tree, name) == []
    # ``listed`` is bound once and used only inside the ``symbols`` expression.
    (listed_assign,) = _assigned(tree, "listed")
    assert listed_call in list(ast.walk(listed_assign.value))
    (symbols_assign,) = _assigned(tree, "symbols")
    in_symbols = list(ast.walk(symbols_assign.value))
    uses = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "listed" and isinstance(node.ctx, ast.Load)
    ]
    assert uses
    assert all(use in in_symbols for use in uses)
    # ``batches`` and ``portfolio`` are bound once, from the one read after the load.
    (book_assign,) = _assigned(tree, "book")
    assert read_call in list(ast.walk(book_assign.value))
    for name in ("batches", "portfolio"):
        (assign,) = _assigned(tree, name)
        value = assign.value
        assert isinstance(value, ast.Attribute) and value.attr == name
        assert isinstance(value.value, ast.Name) and value.value.id == "book"


def test_t6_read_rebalance_inputs_is_called_only_from_rebalance() -> None:
    owners: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for call in _calls_named(tree, "read_rebalance_inputs"):
            node: ast.AST = call
            while node in parents and not isinstance(node, ast.FunctionDef):
                node = parents[node]
            owners.append(node.name if isinstance(node, ast.FunctionDef) else str(path))
    assert owners == ["rebalance"]


def test_t6_read_rebalance_inputs_names_no_lock_and_no_write() -> None:
    functions: list[Callable[..., Any]] = [
        PlaybookStore.read_rebalance_inputs,
        store_module._read_all_batches,
        store_module._read_state_map,
        store_module._portfolio_from_state,
    ]
    for function in functions:
        tree = _function_tree(function)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value.upper()
                assert "IMMEDIATE" not in text
                assert not any(word in text for word in _WRITES), node.value
    tree = _function_tree(PlaybookStore.read_rebalance_inputs)
    # One connection; the two reads by name, batches first; no other self.* call.
    (batches_call,) = _calls_named(tree, "_read_all_batches")
    (state_call,) = _calls_named(tree, "_read_state_map")
    assert batches_call.lineno < state_call.lineno
    self_calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    ]
    assert self_calls == ["_connect"]


def test_t6_each_store_read_has_one_text_definition() -> None:
    source = Path(store_module.__file__).read_text(encoding="utf-8")
    assert source.count(_FULL_BATCH_READ) == 1
    assert source.count('"SELECT key, value FROM playbook_state"') == 1
    assert source.count("PortfolioState(") == 1


# --- T7 the store reads delegate and agree ----------------------------------------------------


def test_t7_one_read_equals_the_two_separate_reads(tmp_path: Path) -> None:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    store.ensure_batches([SYMBOL, LATE_SYMBOL, "0050"], batches_per_target=3)
    for symbol, batch_no, status, remaining in (
        (SYMBOL, 1, "open", 100),
        (SYMBOL, 2, "closed", 0),
        (LATE_SYMBOL, 1, "open", 30),
        (LATE_SYMBOL, 2, "open", 0),
    ):
        batch = store.get_batch(symbol, batch_no)
        assert batch is not None
        store.save_batch(
            batch.model_copy(
                update={
                    "status": status,
                    "entry_date": date(2026, 7, 1),
                    "cost": Decimal("80"),
                    "shares": 100,
                    "remaining_shares": remaining,
                    "peak_close": CLOSE,
                }
            )
        )
    store.set_capital(cash=Decimal("123.45"), total_deploy=Decimal("86.415"), source="initial")
    store.freeze(until=date(2026, 9, 1), reason="test")

    read = store.read_rebalance_inputs()

    assert read == RebalanceRead(store.list_batches(), store.portfolio_state())
    assert len(read.batches) == 9
    assert {batch.status for batch in read.batches} == {"open", "closed", "planned"}
    assert read.portfolio.cash == Decimal("123.45")
    assert read.portfolio.freeze_until == date(2026, 9, 1)


def test_t7_missing_keys_read_as_zero(tmp_path: Path) -> None:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    assert STATE_CASH not in _state_map(store.db_path)

    read = store.read_rebalance_inputs()

    assert read.batches == []
    assert read.portfolio.cash == Decimal("0")
    assert read.portfolio.total_deploy == Decimal("0")
    assert read.portfolio == store.portfolio_state()


def test_t7_errors_roll_back_and_raise_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    after_failure: list[str] = []
    boom = RuntimeError("state read failed")

    def failing(conn: sqlite3.Connection) -> dict[str, str]:
        assert conn.in_transaction
        conn.set_trace_callback(after_failure.append)
        raise boom

    monkeypatch.setattr(store_module, "_read_state_map", failing)

    with pytest.raises(RuntimeError) as raised:
        store.read_rebalance_inputs()

    assert raised.value is boom
    assert after_failure == ["ROLLBACK"]  # rolled back, then the connection closed
