"""N-177 修訂一 R-α: every line that moves shares or cash reads and writes under one lock.

風控 RC-1: with S2 now booking, a per-batch sell that read its batch before a
concurrent S2 closed it wrote the stale row back -- the batch reopened and the
same shares were paid twice. ``settle`` now books a per-batch buy or sell in
:meth:`PlaybookStore._settle_batch_line` (``BEGIN IMMEDIATE``, read, write,
``COMMIT`` on one connection), counts a MISSED retry with one UPDATE, and the
writers outside settlement write their own column only. N177-T20 (the
per-batch half), T23～T29; T27 holds the old branch as a reference.
"""

from __future__ import annotations

import ast
import random
import re
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.data.cache import BUSY_TIMEOUT_MS
from app.playbook import store as store_module
from app.playbook.models import BatchState, BatchStatus, Directive, RuleId, StateEffect
from app.playbook.store import PlaybookStore
from tests import playbook_helpers as helper
from tests.s2_fill_helpers import (
    app_trees,
    assert_one_locked_transaction,
    batch,
    batch_cells,
    calls,
    cash,
    claim_and_settle,
    directive_row,
    enclosing,
    executed_sql,
    fresh_store,
    log_one,
    moves,
    s2_line,
    set_columns,
    state_map,
    stop_line,
    trace,
)
from tests.same_day_helpers import (
    START_CASH,
    TUESDAY,
    WEDNESDAY,
    buy_line,
    hold,
    log_like_before_n172a,
    open_desk,
)

#: The first write to the book: a batch row or a ``playbook_state`` key.
_BOOK_WRITE = re.compile(
    r"^\s*(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE|DELETE\s+FROM)\s+"
    r"(?:playbook_batches|playbook_state)\b",
    re.IGNORECASE,
)


# --- T19 (修訂一): where the book is written ----------------------------------------


def test_t19_only_the_settlement_helpers_write_shares() -> None:
    writers = {
        owner
        for _, owner, sql in executed_sql()
        if sql.startswith("UPDATE playbook_batches")
        and set_columns(sql) & {"shares", "remaining_shares"}
    }
    assert writers == {"_settle_s2_fill", "_settle_batch_line"}


def test_t19_only_the_s2_helper_appends_fill_moves() -> None:
    inserts = {
        owner
        for _, owner, sql in executed_sql()
        if sql.startswith(("INSERT INTO playbook_fill_moves", "INSERT INTO {FILL_MOVES_TABLE}"))
    }
    assert inserts == {"_settle_s2_fill"}


def test_t19_insert_or_replace_into_batches_is_save_batch_alone() -> None:
    replaces = [
        (path.name, owner)
        for path, owner, sql in executed_sql()
        if "INSERT OR REPLACE INTO playbook_batches" in sql
    ]
    assert replaces == [("store.py", "save_batch")]


def test_t19_cash_is_written_by_three_functions_and_add_cash_by_two_callers() -> None:
    cash_writers = {
        owner
        for _, tree in app_trees()
        for owner, node in enclosing(tree)
        if isinstance(node, ast.Dict)
        and any(isinstance(key, ast.Name) and key.id == "STATE_CASH" for key in node.keys)
    }
    assert cash_writers == {"set_cash", "set_capital", "_add_cash"}
    assert sorted(calls("_add_cash")) == sorted(
        [
            ("store.py", "_settle_s2_fill"),
            ("store.py", "_settle_batch_line"),
            ("store.py", "_settle_batch_line"),
        ]
    )


def test_t19_nothing_in_app_calls_save_batch_or_set_cash() -> None:
    assert calls("save_batch") == []
    assert calls("set_cash") == []


# --- T20 (per-batch half): one lock per buy or sell; MISSED is one UPDATE ---------------


def _claimed(store: PlaybookStore, line: Directive, price: str) -> tuple[Directive, int]:
    directive_id = log_one(store, line)
    assert store.claim_directive(directive_id, status="executed", open_price=Decimal(price))
    return line.model_copy(update={"status": "executed"}), directive_id


@pytest.mark.parametrize("action", ["buy", "sell"])
def test_t20_a_per_batch_fill_reads_and_writes_under_one_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    store = fresh_store(tmp_path)
    if action == "sell":
        hold(store, "2330", 1, shares=300)
    line = buy_line() if action == "buy" else stop_line(1, 100, rule_id="P1")
    executed, directive_id = _claimed(store, line, "100")
    statements = trace(monkeypatch)

    store.settle(executed, fill_price=Decimal(100), directive_id=directive_id)

    assert_one_locked_transaction(statements)
    stamp_reads = [i for i, (_, sql) in enumerate(statements) if "exit_stamped_on" in sql]
    begin = [sql for _, sql in statements].index("BEGIN IMMEDIATE")
    commit = [sql for _, sql in statements].index("COMMIT", begin)
    assert all(begin < i < commit for i in stamp_reads)
    assert len(stamp_reads) == (1 if action == "buy" else 0)


@pytest.mark.parametrize("action", ["buy", "sell"])
def test_t20_a_missed_line_is_one_increment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=300, missed_count=2)
    # A buy misses on a planned batch (G1 lets only those through); a sell on a held one.
    line = buy_line(batch_no=2) if action == "buy" else stop_line(1, 100, rule_id="P1")
    assert line.batch_no is not None
    counted = batch(store, line.batch_no).missed_count
    directive_id = log_one(store, line)
    assert store.claim_directive(directive_id, status="missed", open_price=Decimal(100))
    statements = trace(monkeypatch)

    store.settle(line.model_copy(update={"status": "missed"}), directive_id=directive_id)

    touching = [
        sql for _, sql in statements if "playbook_batches" in sql or "playbook_state" in sql
    ]
    (update,) = touching
    assert update.startswith("UPDATE playbook_batches SET missed_count = missed_count + 1,")
    assert "BEGIN IMMEDIATE" not in [sql for _, sql in statements]
    assert batch(store, line.batch_no).missed_count == counted + 1


# --- T23, T24: the RC-1 interleavings, made deterministic --------------------------------


def _hooked(store: PlaybookStore, hook: Callable[[], None]) -> None:
    """Run ``hook`` once, right before ``store``'s first write to a batch or to cash."""
    pending = [hook]

    class Hooked(sqlite3.Connection):
        def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
            if pending and _BOOK_WRITE.match(sql):
                pending.pop()()
            return super().execute(sql, parameters)

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(store.db_path, timeout=BUSY_TIMEOUT_MS / 1000, factory=Hooked)

    store._connect = connect  # type: ignore[method-assign]


class _Racer:
    """The other request: started by the hook, given 0.5 s, joined after the first ends."""

    def __init__(self, work: Callable[[], None]) -> None:
        self.errors: list[BaseException] = []
        self.thread = threading.Thread(target=self._run, args=(work,))
        self.started = False

    def _run(self, work: Callable[[], None]) -> None:
        try:
            work()
        except BaseException as error:  # pragma: no cover - re-raised in finish()
            self.errors.append(error)

    def start(self) -> None:
        self.started = True
        self.thread.start()
        self.thread.join(0.5)

    def finish(self) -> None:
        assert self.started  # the hook really ran
        self.thread.join(10)
        assert not self.thread.is_alive()
        if self.errors:
            raise self.errors[0]


def _race_desk(tmp_path: Path, s1_shares: int) -> tuple[PlaybookStore, PlaybookStore, Any]:
    """One batch of 100 at cost 100; a claimed S1 for A and a claimed S2 (100) for B."""
    db_path = tmp_path / "playbook.db"
    seed = fresh_store(tmp_path)
    hold(seed, "2330", 1, shares=100)
    s1, s1_id = _claimed(seed, stop_line(1, s1_shares), "90")
    s2, s2_id = _claimed(seed, s2_line(100), "80")
    first, second = PlaybookStore(db_path=db_path), PlaybookStore(db_path=db_path)

    def settle_s1(store: PlaybookStore) -> None:
        store.settle(s1, fill_price=Decimal(90), directive_id=s1_id)

    def settle_s2(store: PlaybookStore) -> None:
        store.settle(s2, fill_price=Decimal(80), directive_id=s2_id)

    return first, second, (settle_s1, settle_s2)


def _never_reopened(store: PlaybookStore) -> None:
    held = batch(store, 1)
    assert (held.status, held.remaining_shares) == ("closed", 0)
    assert not [b for b in store.list_batches() if b.status == "open" and b.remaining_shares > 0]


@pytest.mark.parametrize("s1_shares", [40, 100])
def test_t23_a_per_batch_sell_in_its_window_lets_s2_book_after_it(
    tmp_path: Path, s1_shares: int
) -> None:
    """A (S1) has read its batch and is about to write; B (S2) runs right then."""
    a, b, (settle_s1, settle_s2) = _race_desk(tmp_path, s1_shares)
    racer = _Racer(lambda: settle_s2(b))
    _hooked(a, racer.start)

    settle_s1(a)
    racer.finish()

    _never_reopened(a)
    rest = 100 - s1_shares
    assert cash(a) == START_CASH + Decimal(90) * s1_shares + Decimal(80) * rest
    assert [row[2:4] for row in moves(a.db_path)] == ([(1, rest)] if rest else [(None, 0)])


@pytest.mark.parametrize("s1_shares", [40, 100])
def test_t24_s2_in_its_window_lets_the_per_batch_sell_book_after_it(
    tmp_path: Path, s1_shares: int
) -> None:
    """RC-1 as 風控 wrote it: B (S2) closes the batch while A (S1) would read remaining=100."""
    a, b, (settle_s1, settle_s2) = _race_desk(tmp_path, s1_shares)
    racer = _Racer(lambda: settle_s1(a))
    _hooked(b, racer.start)

    settle_s2(b)
    racer.finish()

    _never_reopened(a)
    assert cash(a) == START_CASH + Decimal(80) * 100  # S1 booked 0
    assert [row[2:4] for row in moves(a.db_path)] == [(1, 100)]


# --- T25: settle never goes through the per-call helpers ---------------------------------

_SPIED = ("get_batch", "save_batch", "set_cash", "portfolio_state", "_exit_stamp", "list_batches")


def _spy(monkeypatch: pytest.MonkeyPatch, store: PlaybookStore) -> dict[str, int]:
    calls = dict.fromkeys(_SPIED, 0)
    for name in _SPIED:
        real = getattr(store, name)

        def spied(*args: Any, _name: str = name, _real: Any = real, **kwargs: Any) -> Any:
            calls[_name] += 1
            return _real(*args, **kwargs)

        monkeypatch.setattr(store, name, spied)
    return calls


_T25_CASES: list[tuple[str, Directive, str]] = [
    ("executed", buy_line(), "buy"),
    *[
        ("executed", stop_line(1, 100, rule_id=rule), f"sell-{rule}")
        for rule in ("S1", "P1", "P2", "P3", "EMERGENCY")
    ],
    ("missed", stop_line(1, 100), "missed-sell"),
    ("missed", buy_line(batch_no=2), "missed-buy"),
    ("executed", s2_line(300), "s2"),
]


@pytest.mark.parametrize(
    ("status", "line"), [case[:2] for case in _T25_CASES], ids=[case[2] for case in _T25_CASES]
)
def test_t25_settle_calls_none_of_the_per_call_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str, line: Directive
) -> None:
    store = fresh_store(tmp_path)
    if line.action == "sell":
        hold(store, "2330", 1, shares=300)
    directive_id = log_one(store, line)
    assert store.claim_directive(directive_id, status=status, open_price=Decimal(100))
    calls = _spy(monkeypatch, store)

    store.settle(
        line.model_copy(update={"status": status}),
        fill_price=Decimal(100),
        directive_id=directive_id,
    )

    assert calls == dict.fromkeys(_SPIED, 0)


# --- T26: the writers outside settlement -------------------------------------------------


def test_t26_i_a_stale_list_cannot_reopen_a_batch_s2_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=100)
    stale = store.list_batches()  # read before S2 closed batch 1
    claim_and_settle(store, s2_line(100), "80")
    monkeypatch.setattr(store, "list_batches", lambda: stale)

    store.roll_peak_closes({"2330": Decimal(150)})

    held = batch(store, 1)
    assert (held.status, held.remaining_shares, held.peak_close) == ("closed", 0, Decimal(100))


def test_t26_ii_trailing_on_and_defer_reset_leave_a_closed_batch_closed(tmp_path: Path) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=100, defer_count=2)
    claim_and_settle(store, s2_line(100), "80")

    store.apply_effects(
        [
            StateEffect(kind="trailing_on", symbol="2330", batch_no=1, note="P2"),
            StateEffect(kind="defer_reset", symbol="2330", note="R"),
        ],
        data_date=TUESDAY,
        calendar=helper.calendar(),
    )

    held = batch(store, 1)
    assert (held.status, held.remaining_shares) == ("closed", 0)
    assert (held.trailing_active, held.defer_count) == (True, 0)


def test_t26_iii_they_send_their_own_column_and_no_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=100, defer_count=2)
    hold(store, "2330", 2, shares=100, peak_close=Decimal(90))
    statements = trace(monkeypatch)

    store.roll_peak_closes({"2330": Decimal(150)})
    store.apply_effects(
        [
            StateEffect(kind="defer_reset", symbol="2330", note="R"),
            StateEffect(kind="trailing_on", symbol="2330", batch_no=1, note="P2"),
            StateEffect(kind="defer_increment", symbol="2330", batch_no=3, value=1, note="R2"),
            StateEffect(kind="batch_skipped", symbol="2330", batch_no=3, note="R3"),
        ],
        data_date=TUESDAY,
        calendar=helper.calendar(),
    )

    sql = [text for _, text in statements]
    assert "BEGIN IMMEDIATE" not in sql
    assert not [text for text in sql if "INSERT OR REPLACE" in text]
    writes = [
        text for text in sql if text.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert all(text.startswith("UPDATE playbook_batches SET ") for text in writes)
    assert [set_columns(text) for text in writes] == [
        {"peak_close", "updated_at"},
        {"peak_close", "updated_at"},
        {"defer_count", "updated_at"},
        {"trailing_active", "updated_at"},
        {"defer_count", "updated_at"},
        {"status", "updated_at"},
    ]
    assert all("status = 'open'" in text for text in writes[:2])
    assert batch(store, 3).status == "skipped"


@pytest.mark.parametrize(
    "changes",
    [{"remaining_shares": 0}, {"shares": 1}, {"status": "open"}, {"status": "closed"}],
)
def test_t26_iv_update_batch_refuses_anything_off_its_list(
    tmp_path: Path, changes: dict[str, Any]
) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=100)
    before = batch_cells(store)

    with pytest.raises(ValueError, match="_update_batch"):
        store._update_batch("2330", 1, changes)

    assert batch_cells(store) == before


# --- T27: the same values as the branch it replaced --------------------------------------


def legacy_settle(
    store: PlaybookStore,
    directive: Directive,
    *,
    fill_price: Decimal | None = None,
    directive_id: int | None = None,
) -> None:
    """``PlaybookStore.settle`` before N-177a, for a line that is not S2 (reference only)."""
    if directive.status == "missed" and directive.batch_no is not None:
        batch = store.get_batch(directive.symbol, directive.batch_no)
        if batch is not None:
            store.save_batch(batch.model_copy(update={"missed_count": batch.missed_count + 1}))
    if directive.status != "executed" or directive.batch_no is None:
        store._mark_schedule(directive)
        return
    batch = store.get_batch(directive.symbol, directive.batch_no)
    if batch is None:
        store._mark_schedule(directive)
        return
    price = fill_price if fill_price is not None else directive.reference_price
    price = price or Decimal("0")
    if directive.action == "buy":
        stamp = None if directive_id is None else store._exit_stamp(directive_id)
        batch = batch.model_copy(
            update={
                "status": "open",
                "entry_date": directive.execution_date,
                "cost": price,
                "shares": directive.shares,
                "remaining_shares": directive.shares,
                "peak_close": price,
                "entry_before_exit_on": batch.entry_before_exit_on if stamp is None else stamp,
            }
        )
        store.set_cash(store.portfolio_state().cash - price * Decimal(directive.shares))
    elif directive.action == "sell":
        moved = min(batch.remaining_shares, directive.shares)
        store.set_cash(store.portfolio_state().cash + price * Decimal(moved))
        remaining = max(0, batch.remaining_shares - directive.shares)
        changes: dict[str, Any] = {
            "remaining_shares": remaining,
            "status": "closed" if remaining == 0 else "open",
        }
        if directive.rule_id == "P1":
            changes["p1_done"] = True
        elif directive.rule_id == "P2":
            changes["p2_done"] = True
            changes["trailing_active"] = True
        elif directive.rule_id == "P3":
            changes["p3_last_date"] = directive.data_date
        batch = batch.model_copy(update=changes)
    store.save_batch(batch)
    store._mark_schedule(directive)


_STATUSES: tuple[BatchStatus, ...] = ("planned", "open", "closed", "skipped")
_SELL_RULES: tuple[RuleId, ...] = ("S1", "S3", "P1", "P2", "P3", "EMERGENCY")


def _random_book(rng: random.Random) -> list[BatchState]:
    book = []
    for batch_no in (1, 2, 3):
        shares = rng.choice([0, 1, 100, 300, 666])
        book.append(
            BatchState(
                symbol="2330",
                batch_no=batch_no,
                status=rng.choice(_STATUSES),
                entry_date=rng.choice([None, date(2026, 7, 1)]),
                cost=rng.choice([None, Decimal("0"), Decimal("98.5"), Decimal(100)]),
                shares=shares,
                remaining_shares=rng.randint(0, shares),
                peak_close=rng.choice([None, Decimal("101.25")]),
                p1_done=rng.random() < 0.5,
                p2_done=rng.random() < 0.5,
                p3_last_date=rng.choice([None, date(2026, 8, 3)]),
                trailing_active=rng.random() < 0.5,
                defer_count=rng.randint(0, 3),
                missed_count=rng.randint(0, 3),
                scheduled_date=rng.choice([None, date(2026, 8, 12)]),
                entry_before_exit_on=rng.choice([None, date(2026, 7, 30)]),
            )
        )
    return book


def _random_line(rng: random.Random) -> Directive:
    action = rng.choice(["buy", "sell"])
    reference = rng.choice([None, Decimal("99.5"), Decimal(100)])
    return buy_line(batch_no=1).model_copy(
        update={
            "batch_no": rng.choice([1, 2, 3, 9, None]),
            "action": action,
            "rule_id": "R1" if action == "buy" else rng.choice(_SELL_RULES),
            "shares": rng.choice([1, 100, 300, 666, 1000]),
            "reference_price": reference,
            "data_date": rng.choice([TUESDAY, date(2026, 8, 4)]),
            "status": rng.choice(["executed", "executed", "missed"]),
        }
    )


def _reset(
    store: PlaybookStore, book: list[BatchState], cash_value: str | None, stamp: date | None
) -> None:
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        for table in (
            "playbook_batches",
            "playbook_state",
            "playbook_directives",
            "playbook_schedule",
        ):
            conn.execute(f"DELETE FROM {table}")
        if cash_value is not None:
            conn.execute(
                "INSERT INTO playbook_state (key, value) VALUES ('cash', ?)", (cash_value,)
            )
        conn.execute(
            "INSERT INTO playbook_directives (id, created_at, rules_version, symbol, batch_no, "
            "action, shares, rule_id, rule_summary, data_date, execution_date, data_status, "
            "source, status, settled, exit_stamped_on) VALUES (7, 't', 1, '2330', 1, 'buy', 1, "
            "'R1', 's', '2026-08-11', '2026-08-12', 'fresh', 'fake', 'executed', 1, ?)",
            (None if stamp is None else stamp.isoformat(),),
        )
    for item in book:
        store.save_batch(item)


def test_t27_every_per_batch_line_writes_what_the_old_branch_wrote(tmp_path: Path) -> None:
    rng = random.Random(17727)
    new = PlaybookStore(db_path=tmp_path / "new.db")
    old = PlaybookStore(db_path=tmp_path / "old.db")
    seen: set[tuple[str, str, bool, bool]] = set()
    for _ in range(300):
        book = _random_book(rng)
        cash_value = rng.choice([None, "0", "1000000", "12345.67"])
        stamp = rng.choice([None, date(2026, 8, 5)])
        line = _random_line(rng)
        directive_id = rng.choice([None, 7])
        fill_price = rng.choice([None, Decimal("100.5"), Decimal(97)])
        for store in (new, old):
            _reset(store, book, cash_value, stamp)

        new.settle(line, fill_price=fill_price, directive_id=directive_id)
        legacy_settle(old, line, fill_price=fill_price, directive_id=directive_id)

        assert new.list_batches() == old.list_batches(), line
        assert state_map(new.db_path) == state_map(old.db_path), line
        held = line.batch_no is not None and any(b.batch_no == line.batch_no for b in book)
        seen.add((line.action, line.status, held, directive_id is not None and stamp is not None))
    # The draw reached every corner: both actions and outcomes, batch present or not, stamped.
    assert {(action, status, held) for action, status, held, _ in seen} >= {
        (action, status, held)
        for action in ("buy", "sell")
        for status in ("executed", "missed")
        for held in (True, False)
    }
    assert ("buy", "executed", True, True) in seen


# --- T28: transactions on /today ---------------------------------------------------------


def _locks(statements: list[tuple[int, str]]) -> int:
    return sum(1 for _, sql in statements if sql == "BEGIN IMMEDIATE")


def test_t28_a_today_with_nothing_filled_takes_one_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = open_desk(tmp_path / "playbook.db")
    statements = trace(monkeypatch)

    desk.service.evaluate_today(today=TUESDAY)

    assert _locks(statements) == 1


def test_t28_each_fill_takes_one_lock_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """k = 3 per-batch fills (one with no batch row), m = 1 S2, one MISSED: 1 + 3 + 1."""
    desk = open_desk(tmp_path / "playbook.db", symbols=("2330", "2454"))
    hold(desk.store, "2330", 2, shares=300)
    hold(desk.store, "2454", 1, shares=300)
    log_like_before_n172a(
        desk.store,
        [
            buy_line(),  # 2330 batch 1, planned: fills
            stop_line(2, 100, rule_id="P1"),
            stop_line(9, 100),  # no batch row: claimed, nothing to book
            s2_line(300, symbol="2454"),
            buy_line(symbol="2454", batch_no=2, reference="120"),  # opens at 100: MISSED
        ],
    )
    statements = trace(monkeypatch)

    run = desk.service.evaluate_today(today=WEDNESDAY)

    assert run.settlement is not None
    assert (run.settlement.executed, run.settlement.missed) == (4, 1)
    assert _locks(statements) == 1 + 3 + 1


# --- T29: a failure half way through a per-batch fill ------------------------------------


@pytest.mark.parametrize("action", ["buy", "sell"])
def test_t29_a_failing_cash_write_rolls_the_batch_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=300)
    line = buy_line(batch_no=2) if action == "buy" else stop_line(1, 100)
    executed, directive_id = _claimed(store, line, "100")
    before = (batch_cells(store), state_map(store.db_path))

    def failing(conn: sqlite3.Connection, delta: Decimal) -> None:
        raise RuntimeError("injected cash failure")

    monkeypatch.setattr(store_module, "_add_cash", failing)

    with pytest.raises(RuntimeError, match="injected cash failure"):
        store.settle(executed, fill_price=Decimal(100), directive_id=directive_id)

    assert (batch_cells(store), state_map(store.db_path)) == before
    with closing(sqlite3.connect(store.db_path, timeout=0)) as probe:
        probe.execute("BEGIN IMMEDIATE")  # no transaction was left holding the lock
        probe.execute("ROLLBACK")
    assert directive_row(store.db_path, directive_id) == (1, "executed")  # F2 (N-169)
