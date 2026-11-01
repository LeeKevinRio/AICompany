"""判準 Z: when an unsettled EMERGENCY sell stops covering its batch (CEO #87／#89).

風控 2026-10-31 CEO #87 回審, 第四節 N-166 必改 1～3 and 6 (a)～(e), (h). A line
whose 預定執行日 E has no daily bar while a later day does can never be settled,
so it no longer covers its batch: the exit writes a new line and discloses the
old one with S10. Every other unsettled line -- E has a bar but nobody settled
it yet, nothing after E yet, the load failed -- still covers, and the repeat
answers with S1／S2 ＋ S3 exactly as before.

The settlement half (N1, N1b, N2) is ``tests/test_playbook_settlement_stale_exit.py``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.playbook import wording
from app.playbook.models import Directive
from app.playbook.service import exit_line_still_covers
from tests.api_helpers import recent_bars
from tests.exit_idempotency_helpers import (
    FREEZE_DAYS,
    FRIDAY,
    HISTORY,
    SERIES_END,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    Book,
    already_pending_message,
    emergency_rows,
    extended_note,
    gapped_bars,
    hold,
    legacy_exit_line,
    log_like_before_n166,
    open_book,
    unsettled_per_batch,
    until_for,
    weekdays_after,
)


def _line(execution_date: date) -> Directive:
    return Directive(
        symbol="2330",
        batch_no=1,
        action="sell",
        shares=300,
        rule_id="EMERGENCY",
        rule_summary="x",
        data_date=TUESDAY,
        execution_date=execution_date,
        reference_price=None,
        limit_low=None,
        limit_high=None,
        limit_note="",
        data_status="fresh",
        source="fake",
    )


def _result(*, batches: int, shares: int, executed_at: date) -> str:
    return wording.EMERGENCY_EXIT_RESULT.format(
        batches=batches,
        shares=shares,
        execution_date=weekdays_after(executed_at, 1).isoformat(),
        executed_at=executed_at.isoformat(),
        freeze_days=FREEZE_DAYS,
        until=until_for(executed_at).isoformat(),
    )


def _s10(*items: tuple[str, int, int, tuple[date, ...]]) -> str:
    stale = tuple(
        wording.ExitStale(symbol=symbol, batch_no=batch_no, shares=shares, dates=dates)
        for symbol, batch_no, shares, dates in items
    )
    return wording.EMERGENCY_EXIT_STALE_PENDING_NOTE.format(
        stale_batches=len(stale), stale_items=wording.stale_items(stale)
    )


@pytest.fixture
def book(tmp_path: Path) -> Book:
    """2330 held; its series has no bar on WEDNESDAY (E of a Tuesday exit)."""
    book = open_book(tmp_path / "playbook.db")
    book.prices.seed("2330", gapped_bars("2330", 100.0, missing={WEDNESDAY}))
    hold(book.store, "2330", 1, shares=300)
    return book


# --- the predicate itself ----------------------------------------------------------


@pytest.mark.parametrize(
    ("bar_days", "covers"),
    [
        ({TUESDAY, WEDNESDAY, THURSDAY}, True),  # (b) E has a bar, merely unsettled
        ({TUESDAY}, True),  # (c) nothing after E yet
        (set(), True),  # (d) load failed / empty series
        ({TUESDAY, THURSDAY}, False),  # (a) E missing, a later day present
        ({THURSDAY, FRIDAY}, False),  # window does not reach E: counts as missing
        ({WEDNESDAY}, True),  # only E itself
    ],
    ids=["E-has-bar", "nothing-after", "empty", "E-missing", "window-after-E", "only-E"],
)
def test_criterion_z(bar_days: set[date], covers: bool) -> None:
    bars = [bar for bar in recent_bars([100.0] * HISTORY, end=SERIES_END) if bar.date in bar_days]
    assert exit_line_still_covers(_line(WEDNESDAY), bars) is covers


# --- (a) E 日沒有日線、之後有日線 ------------------------------------------------------


def test_a_line_whose_day_never_traded_no_longer_covers(book: Book) -> None:
    """(a): 產生新列、出現 S10、歸屬語是 S5（RESULT 支沒有 S2 也一樣）."""
    first = book.service.emergency_exit(today=TUESDAY)
    assert [item.execution_date for item in first.directives] == [WEDNESDAY]

    again = book.service.emergency_exit(today=THURSDAY)

    assert [(item.symbol, item.execution_date) for item in again.directives] == [("2330", FRIDAY)]
    assert again.pending_directives == []
    assert again.attribution == wording.EXIT_ATTRIBUTION_MIXED
    assert again.message == (
        _result(batches=1, shares=300, executed_at=THURSDAY)
        + _s10(("2330", 1, 300, (WEDNESDAY,)))
        + extended_note(
            previous=until_for(TUESDAY), until=until_for(THURSDAY), executed_at=THURSDAY
        )
    )
    # 先前那列並未被取消：兩列都還在、都未結算。
    assert [row[3] for row in emergency_rows(book.store.db_path)] == [
        WEDNESDAY.isoformat(),
        FRIDAY.isoformat(),
    ]
    assert unsettled_per_batch(book.store.db_path) == {("2330", 1): 2}


def test_a_stale_batch_next_to_a_covered_one_is_ordered_s2_s3_s10_s6(book: Book) -> None:
    """RESULT＋S2＋S3＋S10＋S6；S2／S3 只算仍算覆蓋的列，S10 只講不算覆蓋的列."""
    hold(book.store, "2454", 1, shares=200)  # continuous series: its E has a bar
    book.service.emergency_exit(today=TUESDAY)

    again = book.service.emergency_exit(today=THURSDAY)

    assert [item.symbol for item in again.directives] == ["2330"]
    assert [item.symbol for item in again.pending_directives] == ["2454"]
    assert again.message == (
        _result(batches=1, shares=300, executed_at=THURSDAY)
        + wording.EMERGENCY_EXIT_PENDING_NOTE.format(
            pending_batches=1, pending_shares=200, pending_execution_dates=WEDNESDAY.isoformat()
        )
        + wording.EMERGENCY_EXIT_PENDING_PAST_DUE_NOTE.format(past_due_dates=WEDNESDAY.isoformat())
        + _s10(("2330", 1, 300, (WEDNESDAY,)))
        + extended_note(
            previous=until_for(TUESDAY), until=until_for(THURSDAY), executed_at=THURSDAY
        )
    )
    assert again.attribution == wording.EXIT_ATTRIBUTION_MIXED


# --- (b) 回歸：E 日有日線但還沒結算 ---------------------------------------------------


def test_b_a_line_whose_day_has_a_bar_still_covers_even_unsettled(tmp_path: Path) -> None:
    """(b) 判準 Z 條件 (2) 的回歸測試：沒有人跑結算時，E 日有日線的列仍算覆蓋.

    The exit never settles first. Without condition (2) a user who skipped
    ``/today`` for a day -- and very likely sold on E as told -- would be sent
    a second sell for the same batch (R10).
    """
    continuous = open_book(tmp_path / "playbook.db")
    hold(continuous.store, "2330", 1, shares=300)
    continuous.service.emergency_exit(today=TUESDAY)
    rows = emergency_rows(continuous.store.db_path)

    again = continuous.service.emergency_exit(today=THURSDAY)

    assert again.directives == []
    assert emergency_rows(continuous.store.db_path) == rows
    assert again.attribution == wording.EXIT_ATTRIBUTION_PRIOR
    assert again.message == (
        already_pending_message(
            batches=1,
            shares=300,
            execution_dates=WEDNESDAY.isoformat(),
            executed_at=THURSDAY,
            until=until_for(THURSDAY),
        )
        + wording.EMERGENCY_EXIT_PENDING_PAST_DUE_NOTE.format(past_due_dates=WEDNESDAY.isoformat())
        + extended_note(
            previous=until_for(TUESDAY), until=until_for(THURSDAY), executed_at=THURSDAY
        )
    )
    assert "至今未能結算" not in again.message


# --- (c) E 已過、之後還沒有日線；(d) 載入失敗 ----------------------------------------


def _s1_s3_s6_on_thursday() -> str:
    return (
        already_pending_message(
            batches=1,
            shares=300,
            execution_dates=WEDNESDAY.isoformat(),
            executed_at=THURSDAY,
            until=until_for(THURSDAY),
        )
        + wording.EMERGENCY_EXIT_PENDING_PAST_DUE_NOTE.format(past_due_dates=WEDNESDAY.isoformat())
        + extended_note(
            previous=until_for(TUESDAY), until=until_for(THURSDAY), executed_at=THURSDAY
        )
    )


def test_c_no_bar_after_the_day_yet_still_covers_and_takes_s3(book: Book) -> None:
    book.service.emergency_exit(today=TUESDAY)
    book.prices.seed("2330", recent_bars([100.0] * HISTORY, symbol="2330", end=TUESDAY))

    again = book.service.emergency_exit(today=THURSDAY)

    assert again.directives == []
    assert again.message == _s1_s3_s6_on_thursday()


def test_d_a_failed_load_still_covers(book: Book) -> None:
    """(d): 重複賣單的實害大於出口暫時被擋——載入失敗或序列為空時仍算覆蓋."""
    book.service.emergency_exit(today=TUESDAY)
    del book.prices.bars["2330"]

    again = book.service.emergency_exit(today=THURSDAY)

    assert again.directives == []
    assert unsettled_per_batch(book.store.db_path) == {("2330", 1): 1}
    assert again.message == _s1_s3_s6_on_thursday()


# --- (e) 第三次出清 -----------------------------------------------------------------


def test_e_a_third_exit_still_discloses_the_stale_line(book: Book) -> None:
    """(e): 較晚那列覆蓋了批次（S1），舊列仍是 pending → 仍列 S10；它不進 S1 的日期."""
    book.service.emergency_exit(today=TUESDAY)
    book.service.emergency_exit(today=THURSDAY)  # stale -> new line for FRIDAY

    third = book.service.emergency_exit(today=THURSDAY)

    assert third.directives == []
    assert [item.execution_date for item in third.pending_directives] == [FRIDAY]
    assert third.attribution == wording.EXIT_ATTRIBUTION_PRIOR
    assert third.message == already_pending_message(
        batches=1,
        shares=300,
        execution_dates=FRIDAY.isoformat(),
        executed_at=THURSDAY,
        until=until_for(THURSDAY),
    ) + _s10(("2330", 1, 300, (WEDNESDAY,)))
    assert len(emergency_rows(book.store.db_path)) == 2


# --- (h) S10 股數不翻倍 ---------------------------------------------------------------


def test_h_s10_counts_the_batch_once_with_its_remaining_shares(book: Book) -> None:
    """(h): 兩列不算覆蓋的舊列（各寫 300 股），批次只剩 200 股 → 「1 批…200 股」."""
    book.service.emergency_exit(today=TUESDAY)
    book.service.emergency_exit(today=TUESDAY)  # same day: covered, no second line
    # A pre-N-166 duplicate of the same Tuesday line, then a partial fill.
    log_like_before_n166(book.store, [legacy_exit_line("2330", 300, execution_date=WEDNESDAY)])
    hold(book.store, "2330", 1, shares=300, remaining=200)

    again = book.service.emergency_exit(today=THURSDAY)

    assert [(item.symbol, item.shares) for item in again.directives] == [("2330", 200)]
    s10 = _s10(("2330", 1, 200, (WEDNESDAY, WEDNESDAY)))
    assert s10 in again.message
    assert (
        "另有 1 批的先前出清賣出指令至今未能結算："
        "2330第 1 批 200 股（未能結算的指令預定執行日 2026-08-12）"
    ) in again.message
    assert "600 股" not in again.message and "2 批" not in again.message
    assert again.total_shares == 200
