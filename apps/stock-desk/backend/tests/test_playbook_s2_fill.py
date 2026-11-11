"""N-177a: an S2 judged executed moves the book (ADR-0041, proposed).

Before N-177a :meth:`PlaybookStore.settle` returned on ``batch_no IS NULL``: the
S2 row was claimed as executed but no share left the book and no cash came in,
so the engine issued S2 again every day (F8). The S2 branch now sells the
symbol's eligible batches oldest first under one write lock and records every
move in ``playbook_fill_moves``. N177-T1～T21 (規格第 4.12 節, 修訂一 1.5).
"""

from __future__ import annotations

import ast
import inspect
import random
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.data.interface import PriceBar
from app.playbook import engine
from app.playbook import store as store_module
from app.playbook.models import BatchState, BatchStatus, SettlementResult
from app.playbook.store import (
    FILL_MOVE_SOURCE_REPAIR,
    FILL_MOVE_SOURCE_SETTLE,
    FILL_MOVES_TABLE,
    S2_ELIGIBLE_BATCH_SQL,
    S2_FILL_ENTRY,
    STATE_CASH,
    PlaybookStore,
    is_s2_fill,
    s2_fill_entry_sql,
)
from tests.api_helpers import recent_bars
from tests.exit_idempotency_helpers import legacy_exit_line
from tests.s2_fill_helpers import (
    assert_one_locked_transaction,
    batch,
    batch_cells,
    cash,
    claim_and_settle,
    directive_row,
    dump,
    enclosing,
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
    ONE_BUY_SHARES,
    START_CASH,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    Desk,
    bars,
    hold,
    log_like_before_n172a,
    open_desk,
)
from tests.seam_helpers import clocked_desk, serving

STORE_PY = Path(store_module.__file__)
FRIDAY = date(2026, 8, 14)

#: N177-C4 / C5, word for word (T18).
C4_TEXT = "s.status = 'executed' AND s.action = 'sell' AND s.rule_id = 'S2' AND s.batch_no IS NULL"
C5_TEXT = "b.status = 'open' AND b.remaining_shares > 0 AND b.cost IS NOT NULL"


# --- T1, T2: the fill -------------------------------------------------------------------


def test_t1_one_batch_s2_closes_it_books_the_cash_and_one_audit_row(tmp_path: Path) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=300)

    directive_id = claim_and_settle(store, s2_line(300), "80")

    held = batch(store, 1)
    assert (held.status, held.remaining_shares, held.shares) == ("closed", 0, 300)
    assert cash(store) == START_CASH + Decimal(80) * 300
    assert moves(store.db_path) == [(directive_id, "2330", 1, 300, "80", FILL_MOVE_SOURCE_SETTLE)]


def test_t2_many_batches_close_in_batch_order_with_one_cash_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = fresh_store(tmp_path)
    for batch_no, shares in ((3, 100), (1, 300), (2, 200)):
        hold(store, "2330", batch_no, shares=shares)
    statements = trace(monkeypatch)

    directive_id = claim_and_settle(store, s2_line(600), "75.5")

    assert [(b.batch_no, b.status, b.remaining_shares) for b in store.list_batches()] == [
        (1, "closed", 0),
        (2, "closed", 0),
        (3, "closed", 0),
    ]
    assert cash(store) == START_CASH + Decimal("75.5") * 600
    cash_writes = [sql for _, sql in statements if sql.startswith("INSERT INTO playbook_state")]
    assert len(cash_writes) == 1  # once, for Σmoved
    assert moves(store.db_path) == [
        (directive_id, "2330", batch_no, shares, "75.5", "settle")
        for batch_no, shares in ((1, 300), (2, 200), (3, 100))
    ]


# --- T3, T21: the real flow no longer re-issues S2 (F8) ----------------------------------


def _weekday_bars(
    symbol: str, *, base: float, crash_from: date | None, end: date
) -> list[PriceBar]:
    days = [end - timedelta(days=offset) for offset in range(150)]
    closes = [
        80.0 if crash_from is not None and day >= crash_from else base
        for day in sorted(days)
        if day.weekday() < 5
    ]
    weekdays = [day for day in sorted(days) if day.weekday() < 5]
    series = recent_bars(closes, symbol=symbol, end=weekdays[-1])
    return [bar.model_copy(update={"date": day}) for bar, day in zip(series, weekdays, strict=True)]


def _crashing_desk(tmp_path: Path, *, crash_from: date, end: date) -> Desk:
    desk = open_desk(tmp_path / "playbook.db")
    for batch_no in (1, 2, 3):
        hold(desk.store, "2330", batch_no, shares=300)
    desk.prices.seed("2330", _weekday_bars("2330", base=100.0, crash_from=crash_from, end=end))
    desk.index.seed("^TWII", _weekday_bars("^TWII", base=20000.0, crash_from=None, end=end))
    return desk


def _symbol_rows(db_path: Path) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(
            "SELECT id, rule_id, action, data_date, status FROM playbook_directives "
            "WHERE symbol = '2330' ORDER BY id"
        ).fetchall()


def test_t3_five_days_below_the_line_log_one_s2(tmp_path: Path) -> None:
    """T3: evaluate → settle each day for five trading days under 均成本 × s2_ratio."""
    days = [date(2026, 8, 10) + timedelta(days=offset) for offset in range(5)]  # Mon..Fri
    desk = _crashing_desk(tmp_path, crash_from=days[0], end=days[-1])

    for day in days:
        desk.service.evaluate_today(today=day)

    rows = _symbol_rows(desk.store.db_path)
    s2_rows = [row for row in rows if row[1] == "S2"]
    assert len(s2_rows) == 1
    (first,) = s2_rows
    assert first[3] == days[0].isoformat() and first[4] == "executed"
    later = [
        row for row in rows if row[3] >= days[1].isoformat() and str(row[1]).startswith(("S", "P"))
    ]
    assert later == []
    with closing(sqlite3.connect(desk.store.db_path)) as conn:
        (triggered_on,) = conn.execute(
            "SELECT triggered_on FROM playbook_blacklist WHERE symbol = '2330'"
        ).fetchone()
    assert triggered_on == days[0].isoformat()
    assert [b.status for b in desk.store.list_batches()] == ["closed"] * 3
    assert cash(desk.store) == START_CASH + Decimal(80) * 900


def test_t21_f8_an_executed_s2_is_not_issued_again_the_next_day(tmp_path: Path) -> None:
    """T21 (F8, qa N-177 重現 in its expected form): the S2 that filled leaves nothing to sell."""
    monday, tuesday = date(2026, 8, 10), date(2026, 8, 11)
    desk = _crashing_desk(tmp_path, crash_from=monday, end=tuesday)

    desk.service.evaluate_today(today=monday)
    second = desk.service.evaluate_today(today=tuesday)

    assert second.settlement is not None and second.settlement.executed == 1
    assert [line.rule_id for line in second.directives if line.symbol == "2330"] == []
    assert [row[1] for row in _symbol_rows(desk.store.db_path)] == ["S2"]
    assert sum(b.remaining_shares for b in desk.store.list_batches()) == 0
    # F8's other half: the cash came in, at Tuesday's open (80) × the S2's 900 shares.
    assert cash(desk.store) == START_CASH + Decimal(80) * 900


# --- T4, T5: the line's shares against the eligible total --------------------------------


def test_t4_fewer_shares_than_held_take_the_oldest_batches_first(tmp_path: Path) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=300)
    hold(store, "2330", 2, shares=300)
    line = s2_line(400)  # logged while batches 1 and 2 were held
    hold(store, "2330", 3, shares=200)  # a batch that entered after the evaluation
    before = sum(b.remaining_shares for b in store.list_batches())

    directive_id = claim_and_settle(store, line, "80")

    held = {b.batch_no: (b.status, b.remaining_shares) for b in store.list_batches()}
    assert held == {1: ("closed", 0), 2: ("open", 200), 3: ("open", 200)}
    assert sum(b.remaining_shares for b in store.list_batches()) == before - 400
    assert moves(store.db_path) == [
        (directive_id, "2330", 1, 300, "80", "settle"),
        (directive_id, "2330", 2, 100, "80", "settle"),
    ]
    assert cash(store) == START_CASH + Decimal(80) * 400


def test_t5_more_shares_than_held_move_only_what_is_held(tmp_path: Path) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=300)
    hold(store, "2330", 2, shares=300)
    line = s2_line(600)
    claim_and_settle(store, stop_line(1, 200), "85")  # an S1 settles first: batch 1 → 100

    directive_id = claim_and_settle(store, line, "80")

    assert [(b.status, b.remaining_shares) for b in store.list_batches()] == [
        ("closed", 0),
        ("closed", 0),
        ("planned", 0),
    ]
    assert moves(store.db_path) == [
        (directive_id, "2330", 1, 100, "80", "settle"),
        (directive_id, "2330", 2, 300, "80", "settle"),
    ]
    assert cash(store) == START_CASH + Decimal(85) * 200 + Decimal(80) * 400


# --- T6: S1 and S2 in one settlement, both orders ----------------------------------------


@pytest.mark.parametrize("s2_first", [False, True], ids=["s1-first", "s2-first"])
def test_t6_s1_and_s2_in_one_settlement(tmp_path: Path, s2_first: bool) -> None:
    desk = open_desk(tmp_path / "playbook.db")
    hold(desk.store, "2330", 1, shares=300)
    lines = [stop_line(1, 100), s2_line(300)]
    log_like_before_n172a(desk.store, lines[::-1] if s2_first else lines)

    result = desk.service.settle_pending(today=WEDNESDAY)

    assert result.executed == 2
    held = batch(desk.store, 1)
    assert (held.status, held.remaining_shares) == ("closed", 0)
    assert all(b.remaining_shares >= 0 for b in desk.store.list_batches())
    # Both fill at Wednesday's open of 100; S1 then S2 moves 100 + 200, S2 then S1 300 + 0.
    assert cash(desk.store) == START_CASH + Decimal(100) * 300
    ((_, _, batch_no, shares_moved, _, _),) = moves(desk.store.db_path)
    assert (batch_no, shares_moved) == (1, 300 if s2_first else 200)


# --- T7: parity with the engine's 均成本 set ---------------------------------------------


_STATUSES: tuple[BatchStatus, ...] = ("planned", "open", "closed", "skipped")


def _random_batch(rng: random.Random, symbol: str, batch_no: int) -> BatchState:
    status = rng.choice(_STATUSES)
    cost = rng.choice([None, Decimal(0), Decimal(rng.randint(1, 500)) / 4])
    remaining = rng.randint(0, 5) * rng.choice([0, 1, 100])
    return BatchState(
        symbol=symbol,
        batch_no=batch_no,
        status=status,
        cost=cost,
        shares=remaining,
        remaining_shares=remaining,
    )


def test_t7_the_eligible_batches_are_the_engines_average_cost_set(tmp_path: Path) -> None:
    rng = random.Random(177)
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    symbols = ("2330", "2454", "AAPL")
    for _ in range(500):
        with closing(sqlite3.connect(store.db_path)) as conn, conn:
            conn.execute("DELETE FROM playbook_batches")
        book = [
            _random_batch(rng, symbol, batch_no)
            for symbol in symbols
            for batch_no in range(1, rng.randint(1, 4) + 1)
        ]
        for item in book:
            store.save_batch(item)
        with closing(sqlite3.connect(store.db_path)) as conn:
            rows = conn.execute(
                "SELECT b.symbol, b.batch_no, b.remaining_shares FROM playbook_batches AS b "
                f"WHERE {S2_ELIGIBLE_BATCH_SQL} ORDER BY b.symbol, b.batch_no"
            ).fetchall()
        for symbol in symbols:
            own = [item for item in book if item.symbol == symbol]
            picked = [row for row in rows if row[0] == symbol]
            assert sum(int(row[2]) for row in picked) == engine._symbol_average_cost(own)[1]
            counted = {item.batch_no for item in own if engine._symbol_average_cost([item])[1]}
            assert {int(row[1]) for row in picked} == counted


# --- T8: what is never moved -------------------------------------------------------------


def test_t8_ineligible_batches_are_never_moved_or_audited(tmp_path: Path) -> None:
    store = fresh_store(tmp_path)
    kinds: list[tuple[int, BatchStatus, Decimal | None, int]] = [
        (1, "open", None, 100),  # cost NULL
        (2, "planned", Decimal(100), 100),
        (3, "skipped", Decimal(100), 100),
        (4, "closed", Decimal(100), 100),
        (5, "open", Decimal(100), 0),
        (6, "open", Decimal(100), 100),  # the only eligible one
    ]
    for batch_no, status, cost, remaining in kinds:
        store.save_batch(
            BatchState(
                symbol="2454",
                batch_no=batch_no,
                status=status,
                cost=cost,
                shares=remaining,
                remaining_shares=remaining,
            )
        )
    before = {b.batch_no: b for b in store.list_batches() if b.symbol == "2454"}

    directive_id = claim_and_settle(store, s2_line(600, symbol="2454"), "80")

    after = {b.batch_no: b for b in store.list_batches() if b.symbol == "2454"}
    assert {k: v for k, v in after.items() if k != 6} == {k: v for k, v in before.items() if k != 6}
    assert (after[6].status, after[6].remaining_shares) == ("closed", 0)
    assert moves(store.db_path) == [(directive_id, "2454", 6, 100, "80", "settle")]


# --- T9: a failure half way leaves nothing -----------------------------------------------


def test_t9_a_failure_inside_the_transaction_rolls_everything_back(tmp_path: Path) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=300)
    hold(store, "2330", 2, shares=300)
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute(
            f"CREATE TRIGGER injected BEFORE INSERT ON {FILL_MOVES_TABLE} "
            "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
    before = (batch_cells(store), state_map(store.db_path), moves(store.db_path))
    line = s2_line(600)
    directive_id = log_one(store, line)
    assert store.claim_directive(directive_id, status="executed", open_price=Decimal(80))

    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        store.settle(
            line.model_copy(update={"status": "executed"}),
            fill_price=Decimal(80),
            directive_id=directive_id,
        )

    assert (batch_cells(store), state_map(store.db_path), moves(store.db_path)) == before
    assert directive_row(store.db_path, directive_id) == (1, "executed")  # F2 (N-169)


# --- T10: replay -------------------------------------------------------------------------


def test_t10_a_second_settlement_moves_nothing_again(tmp_path: Path) -> None:
    desk = open_desk(tmp_path / "playbook.db")
    hold(desk.store, "2330", 1, shares=300)
    log_like_before_n172a(desk.store, [s2_line(300)])
    first = desk.service.settle_pending(today=WEDNESDAY)
    after = (batch_cells(desk.store), state_map(desk.store.db_path), moves(desk.store.db_path))

    second = desk.service.settle_pending(today=WEDNESDAY)

    assert (first.executed, second.executed, second.settled) == (1, 0, [])
    assert (batch_cells(desk.store), state_map(desk.store.db_path), moves(desk.store.db_path)) == (
        after
    )
    assert len(after[2]) == 1


# --- T11: /today and POST /settle book the same -------------------------------------------


def _pinned(desk: Desk, day: date) -> None:
    real = desk.service.settle_on_request

    def settle_on_request(*, today: date | None = None) -> SettlementResult:
        return real(today=today or day)

    desk.service.settle_on_request = settle_on_request  # type: ignore[method-assign]


def _booked(desk: Desk) -> tuple[Any, ...]:
    batches = [b.model_dump() for b in desk.store.list_batches()]
    return batches, cash(desk.store), [row[1:] for row in moves(desk.store.db_path)]


def test_t11_today_and_post_settle_book_the_same(tmp_path: Path) -> None:
    booked = []
    for name, via_today in (("today.db", True), ("settle.db", False)):
        desk = clocked_desk(tmp_path / name)
        hold(desk.store, "2330", 1, shares=300)
        hold(desk.store, "2330", 2, shares=200)
        log_like_before_n172a(desk.store, [s2_line(400)])
        desk.service.pinned = WEDNESDAY
        _pinned(desk, WEDNESDAY)
        with serving(desk) as client:
            if via_today:
                response = client.get("/api/playbook/today")
            else:
                response = client.post("/api/playbook/settle")
        assert response.status_code == 200
        booked.append(_booked(desk))

    assert booked[0] == booked[1]
    opening = str(Decimal("100.0"))  # the fake ladder's Wednesday open, as stored
    assert booked[0][2] == [
        ("2330", 1, 300, opening, "settle"),
        ("2330", 2, 100, opening, "settle"),
    ]


# --- T12, T13: zero moves and a line with no id --------------------------------------------


def test_t12_nothing_eligible_writes_one_zero_move_row_and_no_cash(tmp_path: Path) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=300, status="closed", remaining_shares=0)
    keys = set(state_map(store.db_path))
    before = state_map(store.db_path)[STATE_CASH]

    directive_id = claim_and_settle(store, s2_line(300), "80")

    assert moves(store.db_path) == [(directive_id, "2330", None, 0, "80", "settle")]
    assert state_map(store.db_path)[STATE_CASH] == before
    assert set(state_map(store.db_path)) == keys


def test_t12_a_book_with_no_cash_key_gets_none_for_a_zero_move(tmp_path: Path) -> None:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")

    claim_and_settle(store, s2_line(300), "80")

    assert STATE_CASH not in state_map(store.db_path)
    assert len(moves(store.db_path)) == 1


def test_t13_an_s2_without_its_log_row_id_is_refused_before_any_write(tmp_path: Path) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=300)
    line = s2_line(300)
    directive_id = log_one(store, line)
    assert store.claim_directive(directive_id, status="executed", open_price=Decimal(80))
    before = dump(store.db_path)

    with pytest.raises(ValueError, match="directive_id"):
        store.settle(line.model_copy(update={"status": "executed"}), fill_price=Decimal(80))

    assert dump(store.db_path) == before


# --- T14: the table ----------------------------------------------------------------------


def _insert_move(db_path: Path, batch_no: int | None, shares: int, source: str) -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            f"INSERT INTO {FILL_MOVES_TABLE} "
            "(directive_id, symbol, batch_no, shares_moved, price, source, created_at) "
            "VALUES (1, '2330', ?, ?, '80', ?, '2026-08-12T00:00:00+00:00')",
            (batch_no, shares, source),
        )


def _master(db_path: Path) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()


def test_t14_the_table_has_no_unique_index_or_trigger(tmp_path: Path) -> None:
    store = fresh_store(tmp_path)
    with closing(sqlite3.connect(store.db_path)) as conn:
        (table,) = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (FILL_MOVES_TABLE,)
        ).fetchone()
        attached = conn.execute(
            "SELECT type, name FROM sqlite_master WHERE tbl_name = ? AND type <> 'table'",
            (FILL_MOVES_TABLE,),
        ).fetchall()
    assert "UNIQUE" not in str(table).upper()
    assert "REFERENCES" not in str(table).upper()
    assert attached == []


@pytest.mark.parametrize(
    ("batch_no", "shares", "source"),
    [(None, 5, "settle"), (1, 0, "settle"), (1, 5, "x"), (None, 0, "x"), (1, -5, "settle")],
)
def test_t14_the_checks_refuse_a_malformed_row(
    tmp_path: Path, batch_no: int | None, shares: int, source: str
) -> None:
    store = fresh_store(tmp_path)

    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert_move(store.db_path, batch_no, shares, source)


@pytest.mark.parametrize(
    ("batch_no", "shares", "source"),
    [
        (None, 0, FILL_MOVE_SOURCE_SETTLE),
        (2, 5, FILL_MOVE_SOURCE_SETTLE),
        (2, 5, FILL_MOVE_SOURCE_REPAIR),
    ],
)
def test_t14_the_checks_accept_a_well_formed_row(
    tmp_path: Path, batch_no: int | None, shares: int, source: str
) -> None:
    store = fresh_store(tmp_path)

    _insert_move(store.db_path, batch_no, shares, source)

    assert len(moves(store.db_path)) == 1


def test_t14_opening_the_schema_twice_changes_nothing(tmp_path: Path) -> None:
    store = fresh_store(tmp_path)
    first = _master(store.db_path)

    store._init_schema()
    PlaybookStore(db_path=store.db_path)

    assert _master(store.db_path) == first


def test_t14_an_older_database_with_executed_s2_rows_opens_with_an_empty_table(
    tmp_path: Path,
) -> None:
    """C8: ``_init_schema`` back-fills nothing; the old S2 rows stay unaudited."""
    db_path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        for statement in store_module._SCHEMA[:-1]:  # the schema before N-177a
            conn.execute(statement)
        conn.execute(
            "INSERT INTO playbook_directives (created_at, rules_version, symbol, batch_no, "
            "action, shares, rule_id, rule_summary, data_date, execution_date, data_status, "
            "source, status, settled) VALUES ('t', 1, '2330', NULL, 'sell', 300, 'S2', 's', "
            "'2026-08-11', '2026-08-12', 'fresh', 'fake', 'executed', 1)"
        )
    with closing(sqlite3.connect(db_path)) as conn:
        assert FILL_MOVES_TABLE not in {
            str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master")
        }

    PlaybookStore(db_path=db_path)

    assert moves(db_path) == []


# --- T15: the columns a move leaves alone ------------------------------------------------


@pytest.mark.parametrize("shares", [300, 120], ids=["closes", "reduces"])
def test_t15_a_move_writes_remaining_status_and_updated_at_only(
    tmp_path: Path, shares: int
) -> None:
    store = fresh_store(tmp_path)
    hold(
        store,
        "2330",
        1,
        shares=300,
        peak_close=Decimal("123.4"),
        p1_done=True,
        p2_done=True,
        p3_last_date=date(2026, 8, 3),
        trailing_active=True,
        defer_count=2,
        missed_count=1,
        scheduled_date=date(2026, 7, 1),
        entry_before_exit_on=date(2026, 7, 30),
    )
    before = batch(store, 1)

    claim_and_settle(store, s2_line(shares), "80")

    after = batch(store, 1)
    left = 300 - shares
    assert after == before.model_copy(
        update={"remaining_shares": left, "status": "closed" if left == 0 else "open"}
    )


# --- T16: an EMERGENCY in flight when S2 fills -------------------------------------------


def test_t16_an_emergency_in_flight_moves_nothing_and_gets_n2(tmp_path: Path) -> None:
    """P-5(c): S2 closes the batch; the N-171 block drops it; the EMERGENCY later gets N2."""
    from app.playbook import wording

    desk = clocked_desk(tmp_path / "playbook.db")
    hold(desk.store, "2330", 1, shares=300)
    log_like_before_n172a(desk.store, [s2_line(300)])
    log_like_before_n172a(desk.store, [legacy_exit_line("2330", 300, execution_date=THURSDAY)])

    with serving(desk) as client:
        desk.service.pinned = TUESDAY
        before = client.get("/api/playbook/today").json()
        desk.service.pinned = WEDNESDAY
        after = client.get("/api/playbook/today").json()
    booked = (batch_cells(desk.store), cash(desk.store))
    thursday = desk.service.settle_pending(today=THURSDAY)

    assert [line["directive"]["batch_no"] for line in before["pending_exit_directives"]] == [1]
    assert after["pending_exit_directives"] == [] and after["pending_exit_block"] is None
    assert thursday.executed == 1
    assert (
        wording.SETTLEMENT_EXIT_NOTHING_MOVED_NOTE.format(
            count=1,
            exit_items=wording.SETTLEMENT_EXIT_ITEM.format(
                symbol="2330", batch_no=1, execution_date=THURSDAY.isoformat()
            ),
        )
        in thursday.warnings
    )
    assert (batch_cells(desk.store), cash(desk.store)) == booked  # the EMERGENCY moved 0
    assert [row[2:4] for row in moves(desk.store.db_path)] == [(1, 300)]


# --- T17: an earlier S2 filling between two evaluations ----------------------------------


def test_t17_a_later_s2_line_loses_w_b2ls_once_an_earlier_s2_filled(tmp_path: Path) -> None:
    """風控 A-3, first half: run 1 lists S2 #2 with W-B2LS on a labeled batch; the
    back-filled Wednesday bar then fills S2 #1 and closes the batch, so run 2's S2 #2
    line carries no W-B2LS family at all. N-188 adds its note to the second half."""
    from app.playbook import wording

    head = wording.ENTRY_BEFORE_EXIT_SYMBOL_NOTE.split("{", 1)[0]
    unmatched = wording.ENTRY_BEFORE_EXIT_SYMBOL_UNMATCHED_NOTE.split("{", 1)[0]
    desk = clocked_desk(tmp_path / "playbook.db")
    hold(desk.store, "2330", 1, shares=ONE_BUY_SHARES, entry_before_exit_on=TUESDAY)
    log_like_before_n172a(desk.store, [s2_line(ONE_BUY_SHARES)])  # S2 #1, due Wednesday
    crashed = bars("2330", 100.0, {THURSDAY: 80.0})
    desk.prices.seed("2330", [bar for bar in crashed if bar.date != WEDNESDAY])
    desk.service.pinned = THURSDAY

    with serving(desk) as client:
        first = client.get("/api/playbook/today").json()
        desk.prices.seed("2330", crashed)  # Wednesday's bar is back
        second = client.get("/api/playbook/today").json()

    (early,) = [line for line in first["directives"] if line["directive"]["rule_id"] == "S2"]
    assert str(early["entry_before_exit_note"]).startswith(head)  # the premise of the test
    (late,) = [line for line in second["directives"] if line["directive"]["rule_id"] == "S2"]
    assert late["directive"] == early["directive"]  # S2 #2, as logged
    assert late["entry_before_exit_note"] is None
    for line in second["directives"]:
        note = str(line["entry_before_exit_note"])
        assert head not in note and unmatched not in note
    assert (batch(desk.store, 1).status, len(moves(desk.store.db_path))) == ("closed", 1)


# --- T18: the constants ------------------------------------------------------------------


def test_t18_the_entry_and_the_eligible_set_read_word_for_word() -> None:
    assert s2_fill_entry_sql("s") == C4_TEXT
    assert S2_ELIGIBLE_BATCH_SQL == C5_TEXT
    assert tuple(S2_FILL_ENTRY) == ("executed", "sell", "S2")
    assert FILL_MOVES_TABLE == "playbook_fill_moves"
    with pytest.raises(ValueError, match="identifier"):
        s2_fill_entry_sql("s; DROP TABLE x")


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"status": "executed"}, True),
        ({"status": "pending"}, False),
        ({"status": "missed"}, False),
        ({"status": "executed", "batch_no": 1}, False),
        ({"status": "executed", "rule_id": "S1"}, False),
        ({"status": "executed", "action": "buy"}, False),
    ],
)
def test_t18_is_s2_fill_is_the_entry(changes: dict[str, Any], expected: bool) -> None:
    assert is_s2_fill(s2_line(300).model_copy(update=changes)) is expected


#: N-177a 停止點裁示（修訂五 S-1 (a)）: the ``"S2"`` values that are not S2's fill
#: entry. ``apply_effects`` writes it as the blacklist row's source record
#: (``self.blacklist(rule_id="S2")``), there since before N-177a and zero diff under
#: C3; it is no condition literal of C4 and may not be rewritten to cite
#: :data:`S2_FILL_ENTRY`. ``SETTLED_SINCE_RULE_IDS`` is N-190's one definition of the
#: S/P sell series (N-190 停止點裁示 E-3; 修訂五 T18 (iii), merged under C14), zero
#: diff. Each named place holds exactly one.
PRE_N177A_S2_VALUES = ("apply_effects", "SETTLED_SINCE_RULE_IDS")


def _string_owners(tree: ast.AST, value: str) -> list[str]:
    return sorted(
        owner
        for owner, node in enclosing(tree)
        if isinstance(node, ast.Constant) and node.value == value
    )


def test_t18_the_s2_literal_is_stated_once() -> None:
    """修訂五 T18: ``"S2"`` only at the named places, once each; no ``'S2'`` in SQL."""
    tree = ast.parse(STORE_PY.read_text(encoding="utf-8"))

    assert _string_owners(tree, "S2") == sorted(["S2_FILL_ENTRY", *PRE_N177A_S2_VALUES])
    (entry,) = [
        node
        for owner, node in enclosing(tree)
        if owner == "S2_FILL_ENTRY" and isinstance(node, ast.keyword) and node.arg == "rule_id"
    ]
    assert isinstance(entry.value, ast.Constant) and entry.value.value == "S2"
    sql_s2 = [
        owner
        for owner, node in enclosing(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "'S2'" in node.value
    ]
    assert sql_s2 == []
    eligible = [
        owner
        for owner, node in enclosing(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "remaining_shares > 0 AND b.cost IS NOT NULL" in node.value
    ]
    assert eligible == ["S2_ELIGIBLE_BATCH_SQL"]


def test_t18_the_blacklist_source_record_is_the_one_s2_in_apply_effects() -> None:
    """修訂五 T18 (ii): the value of ``rule_id=`` on the ``self.blacklist(...)`` call."""
    tree = ast.parse(STORE_PY.read_text(encoding="utf-8"))
    (apply_effects,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "apply_effects"
    ]
    s2_nodes = [
        node
        for node in ast.walk(apply_effects)
        if isinstance(node, ast.Constant) and node.value == "S2"
    ]
    recorded = [
        keyword.value
        for call in ast.walk(apply_effects)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "blacklist"
        for keyword in call.keywords
        if keyword.arg == "rule_id"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value == "S2"
    ]
    assert len(s2_nodes) == 1 and recorded == s2_nodes


def test_t18_executed_is_the_entry_and_the_per_batch_gate_only() -> None:
    """修訂五 T18 (追加): ``"executed"`` in ``S2_FILL_ENTRY`` and in settle's gate, once each."""
    tree = ast.parse(STORE_PY.read_text(encoding="utf-8"))

    assert _string_owners(tree, "executed") == ["S2_FILL_ENTRY", "settle"]
    (gate,) = [
        node
        for owner, node in enclosing(tree)
        if owner == "settle"
        and isinstance(node, ast.Compare)
        and any(isinstance(c, ast.Constant) and c.value == "executed" for c in node.comparators)
    ]
    assert ast.unparse(gate) == "directive.status != 'executed'"


# --- T20: one lock for the S2 branch -----------------------------------------------------


def test_t20_the_s2_branch_reads_and_writes_under_one_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = fresh_store(tmp_path)
    hold(store, "2330", 1, shares=300)
    hold(store, "2330", 2, shares=300)
    line = s2_line(400)
    directive_id = log_one(store, line)
    assert store.claim_directive(directive_id, status="executed", open_price=Decimal(80))
    statements = trace(monkeypatch)

    store.settle(
        line.model_copy(update={"status": "executed"}),
        fill_price=Decimal(80),
        directive_id=directive_id,
    )

    assert_one_locked_transaction(statements)
    eligible = [sql for _, sql in statements if S2_ELIGIBLE_BATCH_SQL in sql]
    assert len(eligible) == 1 and "ORDER BY b.batch_no ASC" in eligible[0]
    updates = [sql for _, sql in statements if sql.startswith("UPDATE playbook_batches")]
    assert len(updates) == 2
    assert all(
        set_columns(" ".join(sql.split())) == {"remaining_shares", "status", "updated_at"}
        for sql in updates
    )


def test_t20_the_s2_condition_reaches_settle_only_through_is_s2_fill() -> None:
    source = inspect.getsource(PlaybookStore.settle)
    assert "is_s2_fill(directive)" in source
    assert '"S2"' not in source and "'S2'" not in source
