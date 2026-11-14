"""N-195: the 季末 REBALANCE writes TOTAL_DEPLOY and never the cash pool (R-1′).

Before N-195 the REBALANCE wrote its result back with ``set_capital``, which
also wrote ``STATE_CASH`` -- the value it had read before loading the bars.
That write moved no money; its only effect was that a settlement committed
between the read and the write lost its cash movement. The recomputation now
writes the three TOTAL_DEPLOY keys through ``set_total_deploy`` instead.

These tests pin, in order of the spec (N195-T1～T7): the sequential result is
unchanged, the SQL it sends to ``playbook_state``, a deterministic interleaving
with a concurrent settlement, the user's capital entry point still writing
cash, ``set_capital`` writing exactly what it wrote before, the call sites, and
a book with no cash key at all.
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.playbook import service as service_module
from app.playbook import store as store_module
from app.playbook.models import Directive
from app.playbook.service import CONFIRMATION_SOURCE, REBALANCE_SOURCE, PlaybookService
from app.playbook.store import (
    STATE_CASH,
    STATE_TOTAL_DEPLOY,
    STATE_TOTAL_DEPLOY_SET_AT,
    STATE_TOTAL_DEPLOY_SOURCE,
    PlaybookStore,
)
from tests.api_helpers import FakePriceService, recent_bars
from tests.same_day_helpers import evaluation_of

SERIES_END = date(2026, 8, 14)
QUARTER_END = date(2026, 8, 11)
SETTLE_DAY = date(2026, 8, 12)
HISTORY = 40
CLOSE = Decimal("100")
HELD_SHARES = 100
START_CASH = Decimal("500000.25")

TOTAL_DEPLOY_KEYS = (STATE_TOTAL_DEPLOY, STATE_TOTAL_DEPLOY_SET_AT, STATE_TOTAL_DEPLOY_SOURCE)
APP_ROOT = Path(service_module.__file__).resolve().parents[1]


@dataclass
class Desk:
    service: PlaybookService
    store: PlaybookStore
    db_path: Path


def _service(store: PlaybookStore) -> PlaybookService:
    prices = FakePriceService()
    prices.seed("2330", recent_bars([float(CLOSE)] * HISTORY, symbol="2330", end=SERIES_END))
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=SERIES_END))
    return PlaybookService(
        store=store,
        market_resolver={"TW": prices},
        index_resolver={"TW": index, "US": index},
    )


def _hold(store: PlaybookStore, *, shares: int = HELD_SHARES) -> None:
    """Batch 1 of 2330 open with ``shares`` left and a cost; batches 2-3 planned."""
    store.ensure_batches(["2330"], batches_per_target=3)
    batch = store.get_batch("2330", 1)
    assert batch is not None
    store.save_batch(
        batch.model_copy(
            update={
                "status": "open",
                "entry_date": date(2026, 7, 1),
                "cost": Decimal("80"),
                "shares": shares,
                "remaining_shares": shares,
                "peak_close": CLOSE,
            }
        )
    )


@pytest.fixture
def desk(tmp_path: Path) -> Iterator[Desk]:
    db_path = tmp_path / "playbook.db"
    store = PlaybookStore(db_path=db_path)
    _hold(store)
    store.set_capital(cash=START_CASH, total_deploy=Decimal("350000"), source="initial")
    yield Desk(service=_service(store), store=store, db_path=db_path)


def _state_map(db_path: Path) -> dict[str, str]:
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute("SELECT key, value FROM playbook_state").fetchall()
    return {str(key): str(value) for key, value in rows}


def _expected_total_deploy(store: PlaybookStore, cash: Decimal, deployed: Decimal) -> Decimal:
    return (cash + deployed) * store.active_params(QUARTER_END).deploy_ratio


class _RecordingConnection(sqlite3.Connection):
    """Records every statement it is handed, with its parameters and its connection.

    ``hook`` runs once, just before the first write to ``playbook_state`` is sent
    -- i.e. before the implicit ``BEGIN`` of that write, so this connection holds
    no lock while it runs.
    """

    calls: list[tuple[int, str, tuple[Any, ...]]] = []
    traced: list[tuple[int, str]] = []
    hook: Callable[[], None] | None = None
    opened = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        cls = type(self)
        cls.opened += 1
        # A serial, not id(): a closed connection's id is reused by the next one.
        self.serial = serial = cls.opened
        self.set_trace_callback(lambda sql: cls.traced.append((serial, sql)))

    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
        cls = type(self)
        if cls.hook is not None and _is_state_write(sql):
            hook, cls.hook = cls.hook, None
            hook()
        cls.calls.append((self.serial, sql, tuple(parameters)))
        return super().execute(sql, parameters)


def _is_state_write(sql: str) -> bool:
    head = sql.lstrip().upper()
    return head.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")) and "PLAYBOOK_STATE" in head


def _record(
    monkeypatch: pytest.MonkeyPatch,
    store: PlaybookStore,
    db_path: Path,
    *,
    hook: Callable[[], None] | None = None,
) -> type[_RecordingConnection]:
    _RecordingConnection.calls = []
    _RecordingConnection.traced = []
    _RecordingConnection.opened = 0
    _RecordingConnection.hook = hook
    monkeypatch.setattr(
        store,
        "_connect",
        lambda: sqlite3.connect(db_path, timeout=5, factory=_RecordingConnection),
    )
    return _RecordingConnection


# --- T1 sequential -----------------------------------------------------------------


def test_t1_rebalance_writes_the_same_total_deploy_and_leaves_the_cash_verbatim(
    desk: Desk,
) -> None:
    before = _state_map(desk.db_path)
    started = datetime.now(UTC)

    result = desk.service.rebalance(today=QUARTER_END)

    after = _state_map(desk.db_path)
    expected = _expected_total_deploy(desk.store, START_CASH, CLOSE * HELD_SHARES)
    assert result.status == "ok"
    assert result.new_total_deploy == expected
    assert after[STATE_TOTAL_DEPLOY] == str(expected)
    assert after[STATE_TOTAL_DEPLOY_SOURCE] == REBALANCE_SOURCE
    stamped = datetime.fromisoformat(after[STATE_TOTAL_DEPLOY_SET_AT])
    assert stamped.tzinfo is not None
    assert started <= stamped <= datetime.now(UTC)
    # The cash string is the one that was there, byte for byte.
    assert after[STATE_CASH] == before[STATE_CASH] == str(START_CASH)
    assert {key: value for key, value in after.items() if key not in TOTAL_DEPLOY_KEYS} == {
        key: value for key, value in before.items() if key not in TOTAL_DEPLOY_KEYS
    }


# --- T2 SQL trace ------------------------------------------------------------------


@pytest.mark.parametrize("overshoot", [False, True], ids=["normal", "overshoot"])
def test_t2_rebalance_sends_three_total_deploy_upserts_and_nothing_with_the_cash_key(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, overshoot: bool
) -> None:
    if overshoot:
        # 1,000 cash + 10,000 held = 11,000; x 70% = 7,700 < the 10,000 held.
        desk.store.set_cash(Decimal("1000"))
    recorder = _record(monkeypatch, desk.store, desk.db_path)

    result = desk.service.rebalance(today=QUARTER_END)

    assert result.status == "ok"
    assert (result.overshoot is not None) is overshoot
    state_writes = [call for call in recorder.calls if _is_state_write(call[1])]
    assert len(state_writes) == 3
    upserts = [sql.lstrip().upper() for _, sql, _ in state_writes]
    assert all(sql.startswith("INSERT INTO PLAYBOOK_STATE") for sql in upserts)
    assert all("ON CONFLICT(KEY) DO UPDATE" in sql for sql in upserts)
    assert [params[0] for _, _, params in state_writes] == list(TOTAL_DEPLOY_KEYS)
    for _, _, params in state_writes:
        assert STATE_CASH not in params
    assert not any(STATE_CASH in params for _, _, params in recorder.calls)
    # C4: one connection, one transaction for the three keys.
    (conn_id,) = {conn for conn, _, _ in state_writes}
    on_that_conn = [sql for conn, sql in recorder.traced if conn == conn_id]
    assert on_that_conn[0] == "BEGIN "
    assert on_that_conn[-1] == "COMMIT"
    assert on_that_conn.count("BEGIN ") == 1 and on_that_conn.count("COMMIT") == 1
    # The overshoot line is still logged, once, exactly as before.
    logged = [row for row in desk.store.directive_log() if row["rule_id"] == "REBALANCE"]
    assert len(logged) == (1 if overshoot else 0)
    assert len(result.directives) == (1 if overshoot else 0)


# --- T3 deterministic interleaving -------------------------------------------------


def _line(*, batch_no: int, action: str, rule_id: str, shares: int) -> Directive:
    return Directive(
        symbol="2330",
        batch_no=batch_no,
        action=action,  # type: ignore[arg-type]
        shares=shares,
        rule_id=rule_id,  # type: ignore[arg-type]
        rule_summary="N-195 concurrent settlement",
        data_date=QUARTER_END,
        execution_date=SETTLE_DAY,
        reference_price=CLOSE,
        limit_low=None,
        limit_high=None,
        limit_note="",
        data_status="fresh",
        source="test",
    )


#: (line B settles, its cash movement).
_CONCURRENT_SETTLEMENTS = {
    "s1_sell_40": (_line(batch_no=1, action="sell", rule_id="S1", shares=40), CLOSE * 40),
    "planned_buy_100": (_line(batch_no=2, action="buy", rule_id="R1", shares=100), -CLOSE * 100),
}


@pytest.mark.parametrize("case", sorted(_CONCURRENT_SETTLEMENTS))
def test_t3_a_settlement_committed_mid_rebalance_keeps_its_cash_movement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    db_path = tmp_path / "playbook.db"
    store_a = PlaybookStore(db_path=db_path)
    _hold(store_a)
    store_a.set_capital(cash=START_CASH, total_deploy=Decimal("350000"), source="initial")
    store_b = PlaybookStore(db_path=db_path)
    service_a = _service(store_a)
    line, delta = _CONCURRENT_SETTLEMENTS[case]
    # B settles the way settle_pending does: the line is logged, then claimed,
    # then applied to the book with its log row id.
    store_b.record_directives(evaluation_of(store_b, [line]))
    (pending,) = store_b.pending_directives()
    fired: list[Decimal] = []

    def settle_on_b() -> None:
        # A has read the batches and the cash (:1535, :1538) and has not begun
        # its write; B settles and commits without waiting on a lock.
        assert store_b.claim_directive(pending.directive_id, status="executed", open_price=CLOSE)
        store_b.settle(
            pending.directive.model_copy(update={"status": "executed"}),
            fill_price=CLOSE,
            directive_id=pending.directive_id,
        )
        fired.append(store_b.portfolio_state().cash)

    _record(monkeypatch, store_a, db_path, hook=settle_on_b)

    result = service_a.rebalance(today=QUARTER_END)

    assert fired == [START_CASH + delta]  # the hook ran, once, before A wrote
    state = store_b.portfolio_state()
    assert state.cash == START_CASH + delta
    # A's figure is computed from what A read: the cash and batch 1 before B.
    expected = _expected_total_deploy(store_a, START_CASH, CLOSE * HELD_SHARES)
    assert result.new_total_deploy == expected
    assert state.total_deploy == expected
    assert state.total_deploy_source == REBALANCE_SOURCE


# --- T4 the capital entry point still writes cash -----------------------------------


def test_t4_confirm_rules_still_writes_the_declared_cash(desk: Desk) -> None:
    desk.service.confirm_rules(capital=Decimal("1200000"), today=QUARTER_END)

    state = _state_map(desk.db_path)
    assert state[STATE_CASH] == "1200000"
    assert state[STATE_TOTAL_DEPLOY_SOURCE] == CONFIRMATION_SOURCE
    assert Decimal(state[STATE_TOTAL_DEPLOY]) == Decimal("1200000") * (
        desk.store.active_params(QUARTER_END).deploy_ratio
    )


# --- T5 set_capital writes what it wrote before ---------------------------------------


def test_t5_set_capital_writes_the_same_four_keys_and_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "playbook.db"
    store = PlaybookStore(db_path=db_path)
    at = datetime(2026, 8, 11, 6, 30, 15, 123456, tzinfo=UTC)
    cash = Decimal("1234567.50")
    total_deploy = Decimal("864197.250")
    recorder = _record(monkeypatch, store, db_path)

    store.set_capital(cash=cash, total_deploy=total_deploy, source="initial", at=at)

    # The pre-N-195 body, spelled out: the same keys, the same strings, in order.
    expected = {
        STATE_CASH: str(cash),
        STATE_TOTAL_DEPLOY: str(total_deploy),
        STATE_TOTAL_DEPLOY_SET_AT: at.isoformat(),
        STATE_TOTAL_DEPLOY_SOURCE: "initial",
    }
    assert [params for _, _, params in recorder.calls] == [
        (key, value) for key, value in expected.items()
    ]
    assert _state_map(db_path) == expected


def test_t5_set_total_deploy_writes_only_the_three_keys_in_the_same_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "playbook.db"
    store = PlaybookStore(db_path=db_path)
    at = datetime(2026, 8, 11, 6, 30, 15, 123456, tzinfo=UTC)
    recorder = _record(monkeypatch, store, db_path)

    store.set_total_deploy(total_deploy=Decimal("864197.250"), source="initial", at=at)

    assert [params for _, _, params in recorder.calls] == [
        (STATE_TOTAL_DEPLOY, "864197.250"),
        (STATE_TOTAL_DEPLOY_SET_AT, at.isoformat()),
        (STATE_TOTAL_DEPLOY_SOURCE, "initial"),
    ]
    assert len({conn for conn, _, _ in recorder.calls}) == 1
    traced = [sql for _, sql in recorder.traced]
    assert traced[0] == "BEGIN " and traced[-1] == "COMMIT"
    assert STATE_CASH not in _state_map(db_path)


# --- T6 call sites (AST) ------------------------------------------------------------------


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


def test_t6_set_capital_is_called_only_from_confirm_rules() -> None:
    owners: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for call in _calls_named(tree, "set_capital"):
            node: ast.AST = call
            while node in parents and not isinstance(node, ast.FunctionDef):
                node = parents[node]
            owners.append(node.name if isinstance(node, ast.FunctionDef) else str(path))
    assert owners == ["confirm_rules"]


def test_t6_rebalance_makes_one_set_total_deploy_call_and_no_cash_write() -> None:
    tree = _function_tree(PlaybookService.rebalance)

    (call,) = _calls_named(tree, "set_total_deploy")
    assert "cash" not in {keyword.arg for keyword in call.keywords}
    assert _calls_named(tree, "set_capital") == []
    assert _calls_named(tree, "set_cash") == []
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "STATE_CASH" not in names


def test_t6_set_total_deploy_and_its_helper_never_name_the_cash_key() -> None:
    for function in (PlaybookStore.set_total_deploy, store_module._total_deploy_state):
        tree = _function_tree(function)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert "STATE_CASH" not in names
        assert _calls_named(tree, "set_cash") == []
        assert _calls_named(tree, "set_capital") == []


# --- T7 no cash key at all ------------------------------------------------------------------


def test_t7_rebalance_on_a_book_without_a_cash_key_does_not_create_one(tmp_path: Path) -> None:
    db_path = tmp_path / "playbook.db"
    store = PlaybookStore(db_path=db_path)
    _hold(store)
    assert STATE_CASH not in _state_map(db_path)

    result = _service(store).rebalance(today=QUARTER_END)

    assert result.status == "ok"
    assert result.new_total_deploy == _expected_total_deploy(
        store, Decimal("0"), CLOSE * HELD_SHARES
    )
    state = _state_map(db_path)
    assert STATE_CASH not in state
    assert state[STATE_TOTAL_DEPLOY_SOURCE] == REBALANCE_SOURCE
    assert store.portfolio_state().cash == Decimal("0")
