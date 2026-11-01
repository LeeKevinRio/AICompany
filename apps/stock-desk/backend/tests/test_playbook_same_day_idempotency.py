"""Repeated evaluations of one 預定執行日 log each decision once (ADR-0035, N-172a).

``GET /today`` evaluates on every call. Before N-172a each call logged every
line again: two calls on a 排程日 queued two R1 buys for one batch and T+1 paid
for both (V1, qa 重現), an R2 day counted one deferral per call (V2), a P1 day
sold twice (V3), duplicated buys were MISSED together (V5). The first block is
qa's reproduction (``work/repro/test_n172_repro.py``) turned into the
regression suite -- its expected tests, now green, and its controls; the
observe tests that pinned the defect are gone (N172-T1). The rest is
N172-T2～T6, T8, T9, T15, T16, T18 and the guards of N172-C4/C5/C9/C10/C11.
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_cap1_reading, get_playbook_service
from app.api.playbook_cap1_wording import Cap1Reading
from app.main import app
from app.playbook import engine as engine_module
from app.playbook import service as service_module
from app.playbook import store as store_module
from app.playbook import wording
from app.playbook.models import StateEffect
from app.playbook.store import (
    LINE_BOUND_EFFECTS,
    R_SERIES_RULE_IDS,
    UNKEYED_RULE_IDS,
    PlaybookStore,
)
from tests.api_helpers import CLIENT_HEADERS
from tests.playbook_helpers import calendar
from tests.same_day_helpers import (
    MONDAY,
    ONE_BUY_COST,
    ONE_BUY_SHARES,
    START_CASH,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    Desk,
    bars,
    buy_line,
    capped,
    evaluation_of,
    hold,
    log_like_before_n172a,
    log_rows,
    open_desk,
    rule_rows,
    schedule_rows,
)


@pytest.fixture
def desk(tmp_path: Path) -> Desk:
    return open_desk(tmp_path / "playbook.db")


def _db(desk: Desk) -> Path:
    return desk.store.db_path


def _book(desk: Desk, batch_no: int = 1) -> tuple[int, int, str, Decimal]:
    batch = desk.store.get_batch("2330", batch_no)
    assert batch is not None
    return batch.shares, batch.remaining_shares, batch.status, desk.store.portfolio_state().cash


@pytest.fixture
def client(desk: Desk) -> Iterator[TestClient]:
    app.dependency_overrides[get_playbook_service] = lambda: desk.service
    app.dependency_overrides[get_cap1_reading] = lambda: Cap1Reading(
        weight=Decimal("0.10"), from_default=False
    )
    with TestClient(app, headers=CLIENT_HEADERS) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- N172-T1: qa's reproduction, expected (now green) and controls -----------------


def test_schedule_day_replay_queues_one_r1_row(desk: Desk) -> None:
    """Two evaluations on Tuesday queue ONE R1 buy for batch 1."""
    desk.service.evaluate_today(today=TUESDAY)
    desk.service.evaluate_today(today=TUESDAY)
    assert len(rule_rows(_db(desk), "R1", "buy")) == 1


def test_after_t_plus_1_the_book_equals_a_single_buy(desk: Desk) -> None:
    """After Wednesday's settlement the book equals a single buy."""
    desk.service.evaluate_today(today=TUESDAY)
    desk.service.evaluate_today(today=TUESDAY)
    desk.service.evaluate_today(today=WEDNESDAY)  # /today settles first

    shares, _remaining, status, cash = _book(desk)
    assert status == "open"
    assert shares == ONE_BUY_SHARES
    assert cash == START_CASH - ONE_BUY_COST


def test_get_today_twice_queues_one_row(desk: Desk, client: TestClient) -> None:
    """Two ``GET /today`` on Tuesday queue ONE R1 buy."""
    assert client.get("/api/playbook/today").status_code == 200
    assert client.get("/api/playbook/today").status_code == 200
    assert len(rule_rows(_db(desk), "R1", "buy")) == 1


def test_control_non_schedule_day_replay_writes_no_r1(desk: Desk) -> None:
    """Monday (not 週二／四) never produces R1, however often it is replayed."""
    for _ in range(3):
        desk.service.evaluate_today(today=MONDAY)
    assert rule_rows(_db(desk), "R1", "buy") == []
    assert desk.store.pending_directives() == []


def test_control_replay_after_settlement_does_not_duplicate(desk: Desk) -> None:
    """Tuesday once, Wednesday settles; Wednesday replays add nothing."""
    desk.service.evaluate_today(today=TUESDAY)
    desk.service.evaluate_today(today=WEDNESDAY)
    before = (len(rule_rows(_db(desk), "R1", "buy")), _book(desk))
    desk.service.evaluate_today(today=WEDNESDAY)
    desk.service.evaluate_today(today=WEDNESDAY)
    after = (len(rule_rows(_db(desk), "R1", "buy")), _book(desk))
    assert before == after
    assert before[0] == 1
    assert before[1][3] == START_CASH - ONE_BUY_COST


def test_control_single_tuesday_call_is_correct(desk: Desk) -> None:
    """The happy path: one call, one row, one buy (matches the existing suite)."""
    desk.service.evaluate_today(today=TUESDAY)
    desk.service.evaluate_today(today=WEDNESDAY)
    assert len(rule_rows(_db(desk), "R1", "buy")) == 1
    assert _book(desk)[0] == ONE_BUY_SHARES
    assert _book(desk)[3] == START_CASH - ONE_BUY_COST


# --- N172-T2 / T18: the morning after, and a 預定執行日 that did not trade ---------


def test_wednesday_morning_before_its_close_writes_no_new_row(desk: Desk) -> None:
    """T2: ``as_of`` Wednesday, bars only up to Tuesday -> same 預定執行日, zero new rows.

    The unfinished session is dropped by the data layer, so until Wednesday
    closes the 依據資料日 is still Tuesday (tech-architect [TA1]).
    """
    for symbol in ("2330", "^TWII"):
        ladder = desk.index if symbol == "^TWII" else desk.prices
        ladder.seed(symbol, capped(ladder.bars[symbol], TUESDAY))
    first = desk.service.evaluate_today(today=TUESDAY)
    rows = log_rows(_db(desk))
    morning = desk.service.evaluate_today(today=WEDNESDAY)

    assert morning.data_date == TUESDAY and morning.execution_date == WEDNESDAY
    assert log_rows(_db(desk)) == rows
    assert morning.directives == first.directives
    assert [(line.rule_id, line.action) for line in morning.directives] == [("R1", "buy")]
    assert morning.settlement is not None and len(morning.settlement.unsettled) == 1


def test_a_closed_execution_day_reevaluated_on_itself_keeps_one_row(desk: Desk) -> None:
    """T18: Tuesday's line is stamped Wednesday by the weekday fallback; Wednesday
    never trades. Re-evaluating on that closed day stamps the same 預定執行日 again,
    so the second line of the qa F7 run is no longer written."""
    for ladder, symbol in ((desk.prices, "2330"), (desk.index, "^TWII")):
        ladder.seed(symbol, [bar for bar in ladder.bars[symbol] if bar.date != WEDNESDAY])
    desk.service.evaluate_today(today=TUESDAY)
    desk.service.evaluate_today(today=WEDNESDAY)

    assert [row[4] for row in rule_rows(_db(desk), "R1", "buy")] == [WEDNESDAY.isoformat()]


# --- N172-T3 / T4: deferrals count once per day (V2) ---------------------------


def test_three_evaluations_on_a_chase_day_defer_once(desk: Desk) -> None:
    """T3: R2 不追價 three times on one 排程日 -> ``defer_count == 1``, still planned."""
    desk.prices.seed("2330", bars("2330", 100.0, {TUESDAY: 110.0}))
    for _ in range(3):
        evaluation = desk.service.evaluate_today(today=TUESDAY)
        assert [(line.rule_id, line.action) for line in evaluation.directives] == [("R2", "defer")]

    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    assert (batch.defer_count, batch.status) == (1, "planned")
    assert len(rule_rows(_db(desk), "R2", "defer")) == 1
    assert schedule_rows(_db(desk)) == [("2330", 1, WEDNESDAY.isoformat(), 1, "R2")]


def test_three_evaluations_on_an_index_gap_day_defer_once(desk: Desk) -> None:
    """T4: M1-1 指數缺漏 three times -> one M1 順延, ``defer_count == 1``, still planned."""
    desk.index.seed("^TWII", [])
    for _ in range(3):
        evaluation = desk.service.evaluate_today(today=TUESDAY)
        assert [(line.rule_id, line.action) for line in evaluation.directives] == [("M1", "defer")]
        # The list carries the M1 deferral, so its sentence is true (風控 二-3 第 3 點).
        assert wording.INDEX_DATA_GAP_DEFER_NOTE in evaluation.warnings

    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    assert (batch.defer_count, batch.status) == (1, "planned")
    assert len(rule_rows(_db(desk), "M1", "defer")) == 1


def test_a_third_deferral_skips_the_batch_once(desk: Desk) -> None:
    """The R3 skip and its two bound effects are written once, then K2 holds."""
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    desk.store.save_batch(batch.model_copy(update={"defer_count": 2}))
    desk.prices.seed("2330", bars("2330", 100.0, {TUESDAY: 110.0}))
    for _ in range(2):
        desk.service.evaluate_today(today=TUESDAY)

    assert [row[2:4] for row in log_rows(_db(desk))] == [("R3", "skip")]
    skipped = desk.store.get_batch("2330", 1)
    second = desk.store.get_batch("2330", 2)
    assert skipped is not None and second is not None
    assert (skipped.status, skipped.defer_count) == ("skipped", 3)
    assert (second.status, second.defer_count) == ("planned", 0)


# --- N172-T5 / T6: sells and misses (V3, V5) ------------------------------------


def test_a_p1_day_evaluated_twice_sells_once(desk: Desk) -> None:
    """T5: one P1 line; after settlement ``remaining_shares`` dropped once."""
    desk.prices.seed("2330", bars("2330", 125.0))
    for batch_no in (1, 2, 3):
        hold(desk.store, "2330", batch_no, shares=300)
    for _ in range(2):
        desk.service.evaluate_today(today=TUESDAY)

    assert len(rule_rows(_db(desk), "P1", "sell")) == 3  # one per batch
    assert {row[1] for row in rule_rows(_db(desk), "P1", "sell")} == {1, 2, 3}
    cash = desk.store.portfolio_state().cash
    desk.service.settle_pending(today=WEDNESDAY)
    for batch_no in (1, 2, 3):
        batch = desk.store.get_batch("2330", batch_no)
        assert batch is not None
        assert (batch.remaining_shares, batch.p1_done) == (200, True)
    assert desk.store.portfolio_state().cash == cash + Decimal("125") * 300


def test_a_buy_evaluated_twice_then_missed_counts_one_miss(desk: Desk) -> None:
    """T6: Wednesday opens outside the band -> one MISSED, ``missed_count == 1``."""
    desk.prices.seed("2330", bars("2330", 100.0, {WEDNESDAY: 110.0}))
    desk.service.evaluate_today(today=TUESDAY)
    desk.service.evaluate_today(today=TUESDAY)
    result = desk.service.settle_pending(today=WEDNESDAY)

    assert (result.executed, result.missed) == (0, 1)
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    assert (batch.missed_count, batch.status) == (1, "planned")


# --- N172-T8 / T9 ------------------------------------------------------------------


def test_a_stop_loss_first_missed_by_a_data_gap_is_written_once_the_data_is_back(
    tmp_path: Path,
) -> None:
    """T8: first run 2317 has no bar (停損無法評估); second run it is back and S1 fires."""
    desk = open_desk(tmp_path / "playbook.db", symbols=("2330", "2317"))
    hold(desk.store, "2317", 1, shares=300, cost="100")
    full = bars("2317", 100.0, {TUESDAY: 85.0})
    desk.prices.seed("2317", [])
    first = desk.service.evaluate_today(today=TUESDAY)
    assert not [line for line in first.directives if line.symbol == "2317"]

    desk.prices.seed("2317", full)
    second = desk.service.evaluate_today(today=TUESDAY)

    assert [(row[0], row[2], row[3]) for row in rule_rows(_db(desk), "S1", "sell")] == [
        ("2317", "S1", "sell")
    ]
    assert ("2317", "S1") in {(line.symbol, line.rule_id) for line in second.directives}


def test_a_skipped_first_batch_does_not_let_the_second_one_enter(desk: Desk) -> None:
    """T9: run 1 skips batch 1 (E-2 MISSED limit); run 2 would enter batch 2 -- K2 holds."""
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    desk.store.save_batch(batch.model_copy(update={"missed_count": 3}))
    first = desk.service.evaluate_today(today=TUESDAY)
    assert [(line.rule_id, line.action, line.batch_no) for line in first.directives] == [
        ("R3", "skip", 1)
    ]

    second = desk.service.evaluate_today(today=TUESDAY)

    assert second.directives == first.directives
    assert rule_rows(_db(desk), "R1", "buy") == []
    entered = desk.store.get_batch("2330", 2)
    assert entered is not None and entered.status == "planned"


# --- N172-T15 / T16 ------------------------------------------------------------------


def test_old_same_key_duplicates_are_listed_once(desk: Desk) -> None:
    """T15: two R1 rows written before N-172a for one K1 -> the response shows one line.

    The rows stay in the log (N172-C11); the earlier one (smallest id) is listed.
    """
    log_like_before_n172a(desk.store, [buy_line()])
    log_like_before_n172a(desk.store, [buy_line()])
    rows = log_rows(_db(desk))

    evaluation = desk.service.evaluate_today(today=TUESDAY)

    assert log_rows(_db(desk)) == rows
    assert [(line.rule_id, line.batch_no) for line in evaluation.directives] == [("R1", 1)]
    assert evaluation.directives[0].rule_summary == "R1 排程日進場"  # the logged one


def _body(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/playbook/today")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    # ``as_of`` is the wall-clock moment the response was rendered.
    body.pop("as_of")
    if body["settlement"] is not None:
        body["settlement"].pop("as_of")
    return body


def test_three_get_today_calls_answer_the_same_body(desk: Desk, client: TestClient) -> None:
    """T16: the same table on every refresh (R16), and the log holds one line."""
    first, second, third = (_body(client) for _ in range(3))

    assert first == second == third
    assert [item["directive"]["rule_id"] for item in first["directives"]] == ["R1"]
    assert len(log_rows(_db(desk))) == 1


# --- N172-C4: K1 and K2 leave EMERGENCY and REBALANCE alone -------------------------


def test_unkeyed_and_r_series_rule_ids_are_disjoint() -> None:
    assert set(UNKEYED_RULE_IDS) == {"EMERGENCY", "REBALANCE"}
    assert set(R_SERIES_RULE_IDS) == {"R1", "R2", "R3", "M1"}
    assert not set(UNKEYED_RULE_IDS) & set(R_SERIES_RULE_IDS)


def test_unkeyed_lines_are_never_dropped_by_the_evaluation_commit(desk: Desk) -> None:
    """An EMERGENCY or REBALANCE line passed through the commit is written every time."""
    exit_line = buy_line().model_copy(
        update={"rule_id": "EMERGENCY", "action": "sell", "rule_summary": "exit"}
    )
    rebalance = buy_line().model_copy(
        update={"rule_id": "REBALANCE", "action": "none", "batch_no": None, "shares": 0}
    )
    for _ in range(2):
        commit = desk.store.commit_evaluation(evaluation_of(desk.store, [exit_line, rebalance]))
        assert commit.written == [exit_line, rebalance]
        assert commit.logged == []  # not part of the /today list either
    assert len(log_rows(_db(desk))) == 4


def test_m1_lines_only_come_from_the_entry_pass() -> None:
    """N172-C4 guard: ``rule_id="M1"`` is only ever stamped by ``_defer_for_index_gap``.

    K2 counts M1 as an R-series decision. That holds only while the engine
    writes M1 lines from the entry pass alone; a future M1 line elsewhere (a
    sell, say) would be silently swallowed by K2, so this reads the source.
    """
    tree = ast.parse(inspect.getsource(engine_module))
    owners: set[str] = set()
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.keyword) or node.arg != "rule_id":
                continue
            names = {
                constant.value
                for constant in ast.walk(node.value)
                if isinstance(constant, ast.Constant)
            }
            if "M1" in names:
                owners.add(function.name)
    assert owners == {"_defer_for_index_gap"}


# --- N172-C5: line-bound effects go with their line; the rest are idempotent ----------


def test_a_blocked_line_does_not_apply_its_bound_effects(desk: Desk) -> None:
    """``defer_increment`` and ``batch_skipped`` of a line K2 refused change nothing."""
    first = desk.store.commit_evaluation(evaluation_of(desk.store, [buy_line()]))
    assert len(first.written) == 1
    skip = buy_line().model_copy(update={"rule_id": "R3", "action": "skip", "shares": 0})
    effects = [
        StateEffect(kind="defer_increment", symbol="2330", batch_no=1, value=3, note="x"),
        StateEffect(kind="batch_skipped", symbol="2330", batch_no=1, value=3, note="x"),
    ]

    second = desk.store.commit_evaluation(evaluation_of(desk.store, [skip], effects=effects))

    assert second.written == []
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    assert (batch.status, batch.defer_count) == ("planned", 0)


def test_evaluate_today_hands_no_line_bound_effect_to_apply_effects(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    real = desk.store.apply_effects

    def recording(effects: Any, **kwargs: Any) -> None:
        effects = list(effects)
        seen.extend(effect.kind for effect in effects)
        real(effects, **kwargs)

    monkeypatch.setattr(desk.store, "apply_effects", recording)
    desk.prices.seed("2330", bars("2330", 100.0, {TUESDAY: 110.0}))  # R2 順延
    desk.service.evaluate_today(today=TUESDAY)

    assert not set(seen) & LINE_BOUND_EFFECTS
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.defer_count == 1  # applied, under the lock


def _state(db_path: Path) -> dict[str, list[tuple[Any, ...]]]:
    with closing(sqlite3.connect(db_path)) as conn:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            for table in (
                "playbook_symbols",
                "playbook_blacklist",
                "playbook_state",
            )
        } | {
            "playbook_batches": conn.execute(
                "SELECT symbol, batch_no, status, defer_count, trailing_active "
                "FROM playbook_batches ORDER BY symbol, batch_no"
            ).fetchall()
        }


#: Every effect kind the evaluation applies outside the write lock (C5 表格).
_UNBOUND_EFFECTS: tuple[StateEffect, ...] = (
    StateEffect(kind="pause_symbol", symbol="2330", note="S1"),
    StateEffect(kind="resume_symbol", symbol="2330", note="S1 恢復"),
    StateEffect(kind="blacklist", symbol="2330", value=60, note="S2"),
    StateEffect(kind="freeze_portfolio", value=10, note="S3"),
    StateEffect(kind="defense_on", value=3, note="M1"),
    StateEffect(kind="defense_off", note="M1"),
    StateEffect(kind="emergency_exit", value=20, note="EMERGENCY"),
    StateEffect(kind="defer_reset", symbol="2330", note="S1 恢復"),
    StateEffect(kind="trailing_on", symbol="2330", batch_no=1, note="P2"),
)


def test_the_unbound_effect_table_covers_every_kind_but_bound_and_fill_dependent() -> None:
    kinds = set(StateEffect.model_fields["kind"].annotation.__args__)  # type: ignore[union-attr]
    covered = {effect.kind for effect in _UNBOUND_EFFECTS}
    assert covered == kinds - LINE_BOUND_EFFECTS - store_module.FILL_DEPENDENT_EFFECTS


@pytest.mark.parametrize("effect", _UNBOUND_EFFECTS, ids=lambda effect: effect.kind)
def test_each_unbound_effect_is_idempotent_for_one_data_date(
    tmp_path: Path, effect: StateEffect
) -> None:
    """C5: applying the same effect twice on one 依據資料日 equals applying it once."""
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    store.ensure_batches(["2330"], batches_per_target=3)
    batch = store.get_batch("2330", 1)
    assert batch is not None
    store.save_batch(batch.model_copy(update={"defer_count": 2}))
    days = calendar()

    store.apply_effects([effect], data_date=TUESDAY, calendar=days)
    once = _state(tmp_path / "playbook.db")
    store.apply_effects([effect], data_date=TUESDAY, calendar=days)

    assert _state(tmp_path / "playbook.db") == once


# --- N172-C9 / C10 / C11 ---------------------------------------------------------------


def test_the_schema_has_no_unique_index(desk: Desk) -> None:
    """C9: no UNIQUE index; a legacy file with duplicates must still open."""
    with closing(sqlite3.connect(_db(desk))) as conn:
        indexes = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name IN ('playbook_directives', 'playbook_schedule')"
        ).fetchall()
    assert [row for row in indexes if row[1] is not None and "UNIQUE" in row[1].upper()] == []
    assert not any("UNIQUE" in statement.upper() for statement in store_module._SCHEMA)
    log_like_before_n172a(desk.store, [buy_line(), buy_line()])
    PlaybookStore(db_path=_db(desk))  # reopening a file with duplicates still works


def test_the_untrue_idempotency_docstring_is_gone() -> None:
    """C10: the sentence tech-architect found untrue (`service.py:617-620` then)."""
    source = inspect.getsource(service_module.PlaybookService.evaluate_today)
    assert "It is idempotent, so calling this endpoint" not in source


def test_a_repeated_evaluation_neither_deletes_nor_updates_a_logged_line(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C11: the second run's SQL touches ``playbook_directives`` with SELECTs only."""
    desk.service.evaluate_today(today=TUESDAY)
    traced: list[str] = []
    real_connect = sqlite3.connect

    def tracing(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        conn.set_trace_callback(traced.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracing)
    desk.service.evaluate_today(today=TUESDAY)

    touching = [sql for sql in traced if "playbook_directives" in sql]
    assert touching
    assert [
        sql
        for sql in touching
        if sql.lstrip().upper().startswith(("UPDATE", "DELETE", "INSERT", "REPLACE"))
    ] == []


def test_a_new_decision_after_an_earlier_one_is_still_written(desk: Desk) -> None:
    """Resolution of K1 is the decision, not the day: a P1 on another batch is new."""
    desk.service.evaluate_today(today=TUESDAY)
    hold(desk.store, "2330", 2, shares=300, cost="80")  # P1: 100 >= 80 x 1.2
    second = desk.service.evaluate_today(today=TUESDAY)

    assert [(line.rule_id, line.batch_no) for line in second.directives] == [
        ("R1", 1),
        ("P1", 2),
    ]


def test_a_later_execution_day_is_a_new_decision(desk: Desk) -> None:
    """The keys carry the 預定執行日: Thursday's R1 for batch 2 is not Tuesday's."""
    desk.service.evaluate_today(today=TUESDAY)
    desk.service.evaluate_today(today=WEDNESDAY)  # settles batch 1
    thursday = desk.service.evaluate_today(today=THURSDAY)

    assert [(line.rule_id, line.batch_no) for line in thursday.directives] == [("R1", 2)]
    assert date.fromisoformat(rule_rows(_db(desk), "R1", "buy")[-1][4]) > THURSDAY
