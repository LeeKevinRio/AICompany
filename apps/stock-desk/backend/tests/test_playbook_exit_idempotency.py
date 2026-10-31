"""EMERGENCY_EXIT repeated: covered batches get no second sell (ADR-0033, N-166).

The functional half of ADR-0033 附錄 B (F-T1～F-T6 and the API test) and of the
風控 2026-10-31 review's 第 3 節 合併前條件: which of the three messages a repeat
answers with, which 歸屬語 goes with it, how the 恢復日 moves (CEO #77) and when
that is disclosed (S6/S7/S8/S9). The concurrent half -- several exits at once,
the lock, atomicity -- is ``tests/test_playbook_exit_race.py``.

Every message is asserted by exact equality against the approved constants
formatted by hand, so a clause that drifts, moves or doubles fails here.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_cap1_weight, get_playbook_service
from app.data.calendar import TradingCalendar
from app.main import app
from app.playbook import store as store_module
from app.playbook import wording
from app.playbook.engine import emergency_mode_reason
from app.playbook.models import Directive, FastMarketState, PlaybookEvaluation
from app.playbook.store import PlaybookStore
from tests import playbook_helpers as helper
from tests.api_helpers import CLIENT_HEADERS, FakePriceService, recent_bars
from tests.exit_idempotency_helpers import (
    FREEZE_DAYS,
    HELD,
    HISTORY,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    Book,
    already_pending_message,
    emergency_rows,
    extended_note,
    hold,
    hold_both,
    open_book,
    state_map,
    unsettled_per_batch,
    until_for,
    weekdays_after,
)
from tests.playbook_helpers import confirm_rule_set

#: A stored 恢復日 later than any submission here can compute (風控 F-c).
LATE = date(2026, 12, 31)


def _remaining(start: date, end: date) -> int:
    """Trading days in ``(start, end]`` on the weekday fallback every test here uses."""
    return TradingCalendar(()).trading_days_between(start, end)


@pytest.fixture
def book(tmp_path: Path) -> Book:
    return open_book(tmp_path / "playbook.db")


def _result_message(
    *, batches: int, shares: int, executed_at: date, until: date, kept: bool = False
) -> str:
    template = wording.EMERGENCY_EXIT_RESULT
    if kept:
        template = wording.freeze_kept_template(template)
    return template.format(
        batches=batches,
        shares=shares,
        execution_date=weekdays_after(executed_at, 1).isoformat(),
        executed_at=executed_at.isoformat(),
        freeze_days=FREEZE_DAYS,
        until=until.isoformat(),
    )


def _batches(store: PlaybookStore) -> list[Any]:
    return [batch.model_dump() for batch in store.list_batches()]


# --- F-T1 同日循序重複 -----------------------------------------------------------


def test_a_same_day_repeat_writes_nothing_and_answers_already_pending(book: Book) -> None:
    """F-T1 / 風控 第 3 節: 第二次零新列、S1 逐字、S4 歸屬語、狀態完全不變."""
    hold_both(book.store)
    first = book.service.emergency_exit(today=TUESDAY)
    log, state, batches = (
        book.store.directive_log(),
        state_map(book.store.db_path),
        _batches(book.store),
    )

    second = book.service.emergency_exit(today=TUESDAY)

    assert len(first.directives) == 2
    assert second.directives == []
    assert second.total_shares == 0
    assert second.message == already_pending_message(
        batches=2,
        shares=500,
        execution_dates=WEDNESDAY.isoformat(),
        executed_at=TUESDAY,
        until=until_for(TUESDAY),
    )
    assert second.attribution == wording.EXIT_ATTRIBUTION_PRIOR
    assert [(item.symbol, item.batch_no) for item in second.pending_directives] == [
        ("2330", 1),
        ("2454", 1),
    ]
    assert second.freeze_until == first.freeze_until == until_for(TUESDAY)
    # 同日重複不延長，也就不得出現 S6；沒有過期的先前指令，也不得出現 S3。
    assert "延後至" not in second.message
    assert "已過、仍未結算" not in second.message
    assert book.store.directive_log() == log
    assert state_map(book.store.db_path) == state
    assert _batches(book.store) == batches


# --- F-T2 EX-3：凍結期間新出現的持有批次仍可再出清 ----------------------------------


def test_a_batch_opened_after_a_settled_exit_is_liquidated_again(book: Book) -> None:
    """F-T2 (EX-3): 結算後再 seed 一個 open 批次，再次出清恰好替它寫一列."""
    hold_both(book.store)
    book.service.emergency_exit(today=TUESDAY)
    settled = book.service.settle_pending(today=WEDNESDAY)
    assert settled.executed == 2
    hold(book.store, "2330", 2, shares=100)

    again = book.service.emergency_exit(today=WEDNESDAY)

    assert [(item.symbol, item.batch_no, item.shares) for item in again.directives] == [
        ("2330", 2, 100)
    ]
    assert again.pending_directives == []
    assert again.attribution == wording.EXIT_ATTRIBUTION
    assert unsettled_per_batch(book.store.db_path) == {("2330", 2): 1}
    assert len(emergency_rows(book.store.db_path)) == 3
    # 凍結仍在進行中、恢復日往後移 → RESULT ＋ S6（CEO #77 須揭露）。
    assert again.message == _result_message(
        batches=1, shares=100, executed_at=WEDNESDAY, until=until_for(WEDNESDAY)
    ) + extended_note(
        previous=until_for(TUESDAY), until=until_for(WEDNESDAY), executed_at=WEDNESDAY
    )


# --- F-T3 隔天再按、先前指令未結算 ---------------------------------------------------


def test_a_next_day_repeat_extends_the_freeze_and_says_so(book: Book) -> None:
    """F-T3: 零新列、凍結日取 max（被延長），message 以 S6 結尾且舊值是鎖內讀到的."""
    hold_both(book.store)
    first = book.service.emergency_exit(today=TUESDAY)
    rows = emergency_rows(book.store.db_path)

    second = book.service.emergency_exit(today=WEDNESDAY)

    assert second.directives == []
    assert emergency_rows(book.store.db_path) == rows
    assert second.freeze_until == until_for(WEDNESDAY) > first.freeze_until
    assert book.store.portfolio_state().emergency_until == until_for(WEDNESDAY)
    s6 = extended_note(
        previous=first.freeze_until, until=until_for(WEDNESDAY), executed_at=WEDNESDAY
    )
    assert second.message == (
        already_pending_message(
            batches=2,
            shares=500,
            execution_dates=WEDNESDAY.isoformat(),
            executed_at=WEDNESDAY,
            until=until_for(WEDNESDAY),
        )
        + s6
    )
    assert second.message.endswith(s6)
    assert second.attribution == wording.EXIT_ATTRIBUTION_PRIOR


def test_a_past_due_pending_line_adds_the_past_due_note(book: Book) -> None:
    """S3: 先前指令的預定執行日已過、仍未結算 → 接在 S1 之後，S6 仍在最後."""
    hold_both(book.store)
    book.service.emergency_exit(today=TUESDAY)  # 預定執行日 WEDNESDAY，從未結算

    later = book.service.emergency_exit(today=THURSDAY)

    assert later.directives == []
    assert later.message == (
        already_pending_message(
            batches=2,
            shares=500,
            execution_dates=WEDNESDAY.isoformat(),
            executed_at=THURSDAY,
            until=until_for(THURSDAY),
        )
        + wording.EMERGENCY_EXIT_PENDING_PAST_DUE_NOTE.format(past_due_dates=WEDNESDAY.isoformat())
        + extended_note(
            previous=until_for(TUESDAY), until=until_for(THURSDAY), executed_at=THURSDAY
        )
    )


def test_no_past_due_note_when_every_pending_line_is_still_ahead(book: Book) -> None:
    hold_both(book.store)
    book.service.emergency_exit(today=TUESDAY)

    again = book.service.emergency_exit(today=WEDNESDAY)  # 預定執行日當天，未過

    assert "已過、仍未結算" not in again.message


# --- F-T4 / F-c 既有截止日晚於新算值 -------------------------------------------------


def test_a_later_stored_freeze_is_never_shortened_nor_rewritten(
    book: Book, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-T4 + S7: 凍結日不縮短、值沒變就不寫，message 改用 S7 且無「自…起暫停」."""
    # S8 only beyond freeze_days + 1 (風控 第二次裁示): this case must be past it.
    assert _remaining(TUESDAY, LATE) >= FREEZE_DAYS + 2
    hold_both(book.store)
    book.store.freeze_emergency(until=LATE)
    traced: list[str] = []
    real_connect = sqlite3.connect

    def tracing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        conn.set_trace_callback(traced.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracing_connect)
    result = book.service.emergency_exit(today=TUESDAY)
    monkeypatch.undo()

    assert result.freeze_until == LATE
    assert book.store.portfolio_state().emergency_until == LATE
    assert not [sql for sql in traced if "playbook_state" in sql and "INSERT" in sql.upper()]
    assert result.message == _result_message(
        batches=2, shares=500, executed_at=TUESDAY, until=LATE, kept=True
    )
    assert f"自 {TUESDAY.isoformat()} 起暫停" not in result.message
    assert wording.EMERGENCY_EXIT_FREEZE_KEPT_CLAUSE.format(until=LATE.isoformat()) in (
        result.message
    )
    assert "延後至" not in result.message  # S6 與 S7 不會同時成立
    assert result.mode_reason == wording.MODE_REASON_EMERGENCY_UNCOUNTED.format(
        until=LATE.isoformat()
    )


def test_f_c_replaces_the_freeze_clause_in_every_branch(book: Book) -> None:
    """S7 用於三支：RESULT、ALREADY_PENDING、EMPTY."""
    book.store.freeze_emergency(until=LATE)
    kept = wording.EMERGENCY_EXIT_FREEZE_KEPT_CLAUSE.format(until=LATE.isoformat())

    empty = book.service.emergency_exit(today=TUESDAY)
    hold_both(book.store)
    first = book.service.emergency_exit(today=TUESDAY)
    repeat = book.service.emergency_exit(today=TUESDAY)

    assert empty.message == wording.freeze_kept_template(wording.EMERGENCY_EXIT_EMPTY).format(
        until=LATE.isoformat()
    )
    assert first.message.endswith(kept)
    assert repeat.message == wording.freeze_kept_template(
        wording.EMERGENCY_EXIT_ALREADY_PENDING
    ).format(
        pending_batches=2,
        pending_shares=500,
        pending_execution_dates=WEDNESDAY.isoformat(),
        until=LATE.isoformat(),
    )
    for message in (empty.message, first.message, repeat.message):
        assert "起暫停" not in message
        assert message.count("S/P 系列停損停利仍照常評估。") == 1


def test_today_uses_the_uncounted_mode_line_and_the_kept_check(book: Book) -> None:
    """S8 (/today 在 remaining > freeze_days + 1 的日子) 與 S9 (核取句 2 的 F-c 版)."""
    assert _remaining(TUESDAY, LATE) >= FREEZE_DAYS + 2
    confirm_rule_set(book.store)
    book.store.freeze_emergency(until=LATE)

    evaluation = book.service.evaluate_today(today=TUESDAY)

    assert evaluation.mode == "emergency_frozen"
    assert evaluation.mode_reason == wording.MODE_REASON_EMERGENCY_UNCOUNTED.format(
        until=LATE.isoformat()
    )
    assert evaluation.exit_confirm is not None
    assert evaluation.exit_confirm.freeze_until == LATE
    assert evaluation.exit_confirm.checks[1] == wording.EXIT_CONFIRM_FREEZE_KEPT_CHECK.format(
        FREEZE_UNTIL=LATE.isoformat()
    )
    # 預告值＝實際值 (C-5) 在 F-c 下仍成立。
    assert book.service.emergency_exit(today=TUESDAY).freeze_until == LATE


def test_today_keeps_the_counted_mode_line_inside_the_freeze_length(book: Book) -> None:
    """S8 只限異常分支：正常出清後 /today 仍是「第 N/20」，核取句 2 仍是原句."""
    confirm_rule_set(book.store)
    book.service.emergency_exit(today=TUESDAY)

    evaluation = book.service.evaluate_today(today=TUESDAY)

    assert f"第 1/{FREEZE_DAYS} 交易日" in evaluation.mode_reason
    assert evaluation.exit_confirm is not None
    assert evaluation.exit_confirm.checks[1] == wording.EXIT_CONFIRM_CHECKS[1].format(
        freeze_days=FREEZE_DAYS, FREEZE_UNTIL=until_for(TUESDAY).isoformat()
    )


@pytest.mark.parametrize(
    ("behind", "counted"),
    [(0, True), (1, True), (2, False), (3, False)],
)
def test_the_uncounted_mode_line_starts_past_freeze_days_plus_one(
    behind: int, counted: bool
) -> None:
    """風控 第二次裁示 S8 邊界: 剩餘 = freeze_days+1 仍是計數句「第 1/N」, +2 起才是 S8.

    ``behind`` is how many trading days the 依據資料日 trails the submission day:
    one behind is the submission day before its own close, the commonest moment
    to look, and its 「第 1/20」 is true (the pause runs 自提交日起).
    """
    calendar = helper.calendar()
    until = calendar.shift(TUESDAY, FREEZE_DAYS)
    data_date = calendar.shift(TUESDAY, -behind) if behind else TUESDAY
    assert calendar.trading_days_between(data_date, until) == FREEZE_DAYS + behind

    line = emergency_mode_reason(
        calendar=calendar, data_date=data_date, until=until, freeze_days=FREEZE_DAYS
    )

    if counted:
        assert line == wording.mode_reason_emergency(
            frozen_day=1, freeze_days=FREEZE_DAYS, until=until
        )
        assert f"第 1/{FREEZE_DAYS}" in line
    else:
        assert line == wording.MODE_REASON_EMERGENCY_UNCOUNTED.format(until=until.isoformat())


@pytest.mark.parametrize("behind", [0, 1, 2])
def test_the_exit_and_the_same_day_today_state_the_same_mode_line(
    tmp_path: Path, behind: int
) -> None:
    """V-16 前提 (風控 第二次裁示 suggested): 同一函式、同一依據資料日，逐字相同.

    ``behind`` calendar days of missing bars before the submission day: none,
    the submission day before its close (counted 「第 1/20」), and two sessions
    behind (S8 on both).
    """
    end = THURSDAY - timedelta(days=behind)
    prices = FakePriceService()
    for symbol, _, _, close in HELD:
        prices.seed(symbol, recent_bars([close] * HISTORY, symbol=symbol, end=end))
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=end))
    lagging = open_book(tmp_path / "playbook.db", prices=prices, index=index)
    confirm_rule_set(lagging.store)
    hold_both(lagging.store)

    exit_line = lagging.service.emergency_exit(today=THURSDAY).mode_reason
    today_line = lagging.service.evaluate_today(today=THURSDAY).mode_reason

    assert exit_line == today_line
    if behind < 2:
        assert f"第 1/{FREEZE_DAYS} 交易日" in exit_line
    else:
        assert exit_line == wording.MODE_REASON_EMERGENCY_UNCOUNTED.format(
            until=until_for(THURSDAY).isoformat()
        )


# --- S6 渲染條件 ------------------------------------------------------------------


def test_an_exit_after_the_freeze_ran_out_claims_no_extension(book: Book) -> None:
    """凍結已過期後再出清：previous_until < as_of，不得出現 S6."""
    hold_both(book.store)
    book.store.freeze_emergency(until=date(2026, 8, 1))

    result = book.service.emergency_exit(today=TUESDAY)

    assert result.freeze_until == until_for(TUESDAY)
    assert result.message == _result_message(
        batches=2, shares=500, executed_at=TUESDAY, until=until_for(TUESDAY)
    )


def test_the_last_day_of_a_freeze_still_counts_as_running(book: Book) -> None:
    """as_of == previous_until 仍在凍結中 → 延長要揭露（S6 三條件之二是 <=）."""
    book.store.freeze_emergency(until=TUESDAY)

    result = book.service.emergency_exit(today=TUESDAY)

    assert result.message == wording.EMERGENCY_EXIT_EMPTY.format(
        executed_at=TUESDAY.isoformat(),
        freeze_days=FREEZE_DAYS,
        until=until_for(TUESDAY).isoformat(),
    ) + extended_note(previous=TUESDAY, until=until_for(TUESDAY), executed_at=TUESDAY)


def test_an_empty_book_repeated_next_day_discloses_the_extension(book: Book) -> None:
    """EMPTY ＋［S6］."""
    book.service.emergency_exit(today=TUESDAY)

    again = book.service.emergency_exit(today=WEDNESDAY)

    assert again.attribution is None
    assert again.message == wording.EMERGENCY_EXIT_EMPTY.format(
        executed_at=WEDNESDAY.isoformat(),
        freeze_days=FREEZE_DAYS,
        until=until_for(WEDNESDAY).isoformat(),
    ) + extended_note(
        previous=until_for(TUESDAY), until=until_for(WEDNESDAY), executed_at=WEDNESDAY
    )


# --- 部分覆蓋（RESULT 支 ＋ S2） ------------------------------------------------------


def test_a_partly_covered_book_gets_lines_only_for_the_rest(book: Book) -> None:
    """S2: {pending_shares} 是被覆蓋批次的 remaining_shares，不是先前指令的股數."""
    hold(book.store, "2330", 1, shares=300)
    book.service.emergency_exit(today=TUESDAY)
    # 先前那筆指令寫的是 300 股；此後批次只剩 200 股（例如 P1 已結算）。
    hold(book.store, "2330", 1, shares=300, remaining=200)
    hold(book.store, "2454", 1, shares=200)

    result = book.service.emergency_exit(today=TUESDAY)

    assert [(item.symbol, item.shares) for item in result.directives] == [("2454", 200)]
    assert [(item.symbol, item.shares) for item in result.pending_directives] == [("2330", 300)]
    assert result.total_shares == 200
    assert result.message == _result_message(
        batches=1, shares=200, executed_at=TUESDAY, until=until_for(TUESDAY)
    ) + wording.EMERGENCY_EXIT_PENDING_NOTE.format(
        pending_batches=1, pending_shares=200, pending_execution_dates=WEDNESDAY.isoformat()
    )
    assert result.attribution == wording.EXIT_ATTRIBUTION_MIXED


def test_a_partly_covered_book_with_a_past_due_line_adds_s3_after_s2(book: Book) -> None:
    """RESULT ＋ S2 ＋ S3 ＋ S6，順序固定."""
    hold(book.store, "2330", 1, shares=300)
    book.service.emergency_exit(today=TUESDAY)
    hold(book.store, "2454", 1, shares=200)

    result = book.service.emergency_exit(today=THURSDAY)

    assert result.message == (
        _result_message(batches=1, shares=200, executed_at=THURSDAY, until=until_for(THURSDAY))
        + wording.EMERGENCY_EXIT_PENDING_NOTE.format(
            pending_batches=1, pending_shares=300, pending_execution_dates=WEDNESDAY.isoformat()
        )
        + wording.EMERGENCY_EXIT_PENDING_PAST_DUE_NOTE.format(past_due_dates=WEDNESDAY.isoformat())
        + extended_note(
            previous=until_for(TUESDAY), until=until_for(THURSDAY), executed_at=THURSDAY
        )
    )


# --- 三支 message 與歸屬語的對應 -----------------------------------------------------


def test_each_branch_carries_its_own_attribution(tmp_path: Path) -> None:
    """風控 第 3 節 2: RESULT 無 pending→EXIT_ATTRIBUTION；有 pending→S5；
    ALREADY_PENDING→S4；EMPTY→None."""
    empty = open_book(tmp_path / "empty.db").service.emergency_exit(today=TUESDAY)

    plain = open_book(tmp_path / "plain.db")
    hold(plain.store, "2330", 1, shares=300)
    result = plain.service.emergency_exit(today=TUESDAY)
    pending_only = plain.service.emergency_exit(today=TUESDAY)
    hold(plain.store, "2454", 1, shares=200)
    mixed = plain.service.emergency_exit(today=TUESDAY)

    assert empty.attribution is None
    assert empty.message.startswith("EMERGENCY_EXIT 已受理：目前無持有批次")
    assert result.attribution == wording.EXIT_ATTRIBUTION
    assert pending_only.attribution == wording.EXIT_ATTRIBUTION_PRIOR
    assert mixed.attribution == wording.EXIT_ATTRIBUTION_MIXED


@pytest.mark.parametrize(
    ("new", "pending", "expected"),
    [
        (2, 0, wording.EXIT_ATTRIBUTION),
        (1, 1, wording.EXIT_ATTRIBUTION_MIXED),
        (0, 2, wording.EXIT_ATTRIBUTION_PRIOR),
        (0, 0, None),
    ],
)
def test_the_attribution_table(new: int, pending: int, expected: str | None) -> None:
    assert wording.emergency_exit_attribution(new_batches=new, pending_batches=pending) == expected


# --- F-T5 去重之後結算 ---------------------------------------------------------------


def test_settling_after_repeats_executes_each_batch_once(book: Book) -> None:
    """F-T5: executed 數等於批次數，現金只入帳一次."""
    hold_both(book.store)
    book.store.set_cash(Decimal("0"))
    for _ in range(3):
        book.service.emergency_exit(today=TUESDAY)

    settled = book.service.settle_pending(today=WEDNESDAY)

    assert settled.executed == 2
    assert book.store.portfolio_state().cash == Decimal("40000")  # 300×100 + 200×50
    assert {batch.status for batch in book.store.list_batches() if batch.batch_no == 1} == {
        "closed"
    }
    assert f"成交 {2} 筆" in settled.warnings[-1]


# --- F-T6 什麼都沒持有 ---------------------------------------------------------------


def test_an_empty_book_still_takes_the_empty_branch(book: Book) -> None:
    """F-T6: EMPTY 支逐字不變，同日重複也一樣（且不出現 S6）."""
    first = book.service.emergency_exit(today=TUESDAY)
    again = book.service.emergency_exit(today=TUESDAY)

    expected = wording.EMERGENCY_EXIT_EMPTY.format(
        executed_at=TUESDAY.isoformat(),
        freeze_days=FREEZE_DAYS,
        until=until_for(TUESDAY).isoformat(),
    )
    for result in (first, again):
        assert result.message == expected
        assert result.attribution is None
        assert result.directives == [] and result.pending_directives == []
    assert book.store.portfolio_state().emergency_until == until_for(TUESDAY)


# --- 既有 DB 已有 N-166 之前的重複列 ---------------------------------------------------


def _legacy_line(symbol: str, shares: int) -> Directive:
    return Directive(
        symbol=symbol,
        batch_no=1,
        action="sell",
        shares=shares,
        rule_id="EMERGENCY",
        rule_summary="legacy",
        data_date=TUESDAY,
        execution_date=WEDNESDAY,
        reference_price=None,
        limit_low=None,
        limit_high=None,
        limit_note="",
        data_status="fresh",
        source="fake",
    )


def _log_like_before_n166(store: PlaybookStore, lines: list[Directive]) -> None:
    store.record_directives(
        PlaybookEvaluation(
            data_date=TUESDAY,
            execution_date=WEDNESDAY,
            mode="emergency_frozen",
            mode_reason="legacy",
            is_schedule_day=True,
            fast_market=FastMarketState(
                active=False, annualized_vol_20d=None, large_move_days=0, reason=None
            ),
            rules_version=1,
            params=store.active_params(TUESDAY),
            directives=lines,
            effects=[],
            warnings=[],
            snapshot=[],
        )
    )


def test_duplicate_lines_from_before_n166_are_kept_and_counted_once(book: Book) -> None:
    """CEO-2 未裁前不清理；面向使用者的批數、股數不因重複列翻倍."""
    hold_both(book.store)
    doubled = [_legacy_line("2330", 300), _legacy_line("2454", 200)] * 2
    _log_like_before_n166(book.store, doubled)
    before = emergency_rows(book.store.db_path)
    assert len(before) == 4

    result = book.service.emergency_exit(today=TUESDAY)

    assert result.directives == []
    assert emergency_rows(book.store.db_path) == before  # 未清理、也未新增
    assert [(item.symbol, item.batch_no) for item in result.pending_directives] == [
        ("2330", 1),
        ("2454", 1),
    ]
    assert result.message == already_pending_message(
        batches=2,
        shares=500,
        execution_dates=WEDNESDAY.isoformat(),
        executed_at=TUESDAY,
        until=until_for(TUESDAY),
    )
    assert "1000 股" not in result.message and "4 批" not in result.message


# --- C-9: mode_reason、schema、state key ----------------------------------------------

#: ``playbook_*`` tables and their columns as they were before N-166.
PRE_N166_COLUMNS: dict[str, list[str]] = {
    "playbook_batches": [
        "symbol",
        "batch_no",
        "status",
        "entry_date",
        "cost",
        "shares",
        "remaining_shares",
        "peak_close",
        "p1_done",
        "p2_done",
        "p3_last_date",
        "trailing_active",
        "defer_count",
        "missed_count",
        "scheduled_date",
        "updated_at",
    ],
    "playbook_schedule": [
        "id",
        "symbol",
        "batch_no",
        "scheduled_date",
        "defer_count",
        "status",
        "rule_id",
        "updated_at",
    ],
    "playbook_rule_params": ["version", "payload", "submitted_at", "effective_date", "status"],
    "playbook_blacklist": ["symbol", "triggered_on", "until", "rule_id"],
    "playbook_symbols": ["symbol", "paused", "paused_since", "high_volatility"],
    "playbook_state": ["key", "value"],
    "playbook_directives": [
        "id",
        "created_at",
        "rules_version",
        "symbol",
        "batch_no",
        "action",
        "shares",
        "rule_id",
        "rule_summary",
        "data_date",
        "execution_date",
        "reference_price",
        "limit_low",
        "limit_high",
        "limit_note",
        "data_status",
        "source",
        "data_reason",
        "status",
        "settled",
        "settled_at",
        "settled_open_price",
    ],
}

#: The only indexes on those tables before N-166: SQLite's own, for the text
#: primary keys. No unique index on the directive log (ADR-0033 方案 (e) 未採).
PRE_N166_INDEXES = frozenset(
    {
        "sqlite_autoindex_playbook_batches_1",
        "sqlite_autoindex_playbook_blacklist_1",
        "sqlite_autoindex_playbook_symbols_1",
        "sqlite_autoindex_playbook_state_1",
    }
)

#: Every ``playbook_state`` key the store could write before N-166.
PRE_N166_STATE_KEYS = frozenset(
    {
        "cash",
        "total_deploy",
        "freeze_until",
        "freeze_reason",
        "emergency_until",
        "defense_active",
        "defense_since",
        "total_deploy_set_at",
        "total_deploy_source",
        "rule_set_confirmed_at",
        "rule_set_confirmed_version",
        "fast_market_active",
        "fast_market_vol",
        "fast_market_moves",
        "fast_market_reason",
        "fast_market_measured_on",
    }
)


def _every_scenario(book: Book) -> list[str]:
    """Run each branch once (incl. S6 and F-c) and return every mode_reason seen."""
    confirm_rule_set(book.store)
    hold_both(book.store)
    seen = [
        book.service.emergency_exit(today=TUESDAY).mode_reason,
        book.service.emergency_exit(today=TUESDAY).mode_reason,
        book.service.emergency_exit(today=WEDNESDAY).mode_reason,
        book.service.evaluate_today(today=WEDNESDAY).mode_reason,
    ]
    book.store.freeze_emergency(until=LATE)
    seen += [
        book.service.emergency_exit(today=THURSDAY).mode_reason,
        book.service.evaluate_today(today=THURSDAY).mode_reason,
    ]
    return seen


def test_no_mode_reason_mentions_an_extension_or_an_earlier_submission(book: Book) -> None:
    """風控 第 3 節: 任何 mode_reason 都不含「延後」，也不含「先前」 (C-9)."""
    for mode_reason in _every_scenario(book):
        assert "延後" not in mode_reason
        assert "先前" not in mode_reason


def test_the_exit_adds_no_column_table_or_state_key(book: Book) -> None:
    """S6/S8 不得新增 column、state key 或旗標；schema 與 N-166 之前相同."""
    before = set(state_map(book.store.db_path))
    _every_scenario(book)

    with closing(sqlite3.connect(book.store.db_path)) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'playbook_%' "
                "OR type = 'index' OR type = 'trigger'"
            )
        }
        columns = {
            table: [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]
            for table in PRE_N166_COLUMNS
        }
    assert names == set(PRE_N166_COLUMNS) | PRE_N166_INDEXES
    assert columns == PRE_N166_COLUMNS
    after = set(state_map(book.store.db_path))
    assert after <= PRE_N166_STATE_KEYS
    # confirm_rule_set and the evaluation write their own keys; the exits add
    # exactly one -- emergency_until -- and nothing else.
    assert "emergency_until" in after - before
    declared = {
        value
        for name, value in vars(store_module).items()
        if name.startswith("STATE_") and isinstance(value, str)
    }
    assert declared == PRE_N166_STATE_KEYS


def test_the_directive_log_stores_no_message_or_disclosure(book: Book) -> None:
    """S6 的事實只在當次 transaction 的記憶體中比對產生，log 裡沒有它."""
    _every_scenario(book)
    cells = [str(value) for row in book.store.directive_log() for value in row.values()]
    assert not [cell for cell in cells if "延後" in cell or "先前" in cell]


# --- API：一律 200 ----------------------------------------------------------------


@pytest.fixture
def client(book: Book) -> Iterator[TestClient]:
    app.dependency_overrides[get_playbook_service] = lambda: book.service
    app.dependency_overrides[get_cap1_weight] = lambda: Decimal("0.10")
    with TestClient(app, headers=CLIENT_HEADERS) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_two_posts_are_both_200_and_the_second_reports_the_pending_lines(
    book: Book, client: TestClient
) -> None:
    """附錄 B API 測試 / C-6 / C-7. The endpoint runs on the real clock."""
    for symbol, _, _, close in HELD:
        book.prices.seed(symbol, recent_bars([close] * HISTORY, symbol=symbol))
    book.index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII"))
    hold_both(book.store)

    first = client.post("/api/playbook/emergency-exit")
    second = client.post("/api/playbook/emergency-exit")

    assert first.status_code == second.status_code == 200
    assert len(first.json()["directives"]) == 2
    assert first.json()["pending_directives"] == []
    body = second.json()
    assert body["directives"] == []
    assert [item["directive"]["symbol"] for item in body["pending_directives"]] == ["2330", "2454"]
    assert all(item["line"] for item in body["pending_directives"])
    assert body["total_shares"] == 0
    assert body["message"].startswith("EMERGENCY_EXIT 已受理：本次未產生新的賣出指令。")
    assert body["attribution"] == wording.EXIT_ATTRIBUTION_PRIOR
    assert body["freeze_until"] == first.json()["freeze_until"]


def test_an_exit_while_frozen_with_a_later_stored_date_is_still_200(
    book: Book, client: TestClient
) -> None:
    book.store.freeze_emergency(until=LATE)

    for _ in range(2):
        response = client.post("/api/playbook/emergency-exit")
        assert response.status_code == 200
        assert response.json()["freeze_until"] == LATE.isoformat()


def test_the_exit_path_has_no_conflict_status_anywhere() -> None:
    """C-6: 不得以 409／任何 4xx 處理重複——出口路徑上連 HTTPException 都沒有."""
    root = Path(__file__).resolve().parents[1] / "app"
    for relative in ("api/playbook.py", "playbook/service.py", "playbook/store.py"):
        source = (root / relative).read_text(encoding="utf-8")
        assert "HTTPException" not in source, relative
        assert "status_code" not in source, relative
        assert "409" not in source, relative
