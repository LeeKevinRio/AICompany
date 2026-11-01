"""Settlement side of 判準 Z: N1, N1b and N2 (風控 CEO #87 回審, N-166 必改 4, 6 (f)(g)).

When an exit line's 預定執行日 E never traded, the next exit writes a second
line for the batch (``tests/test_playbook_exit_stale_cover.py``). The book has
``min`` protection, so shares never move twice -- but two screens still mislead:

* the old line shows up in ``unsettled`` day after day as 「賣出 N 股、待結算」
  (N1 says why, and what the user should and should not do; N1b, when the batch
  is still held and nothing later covers it, says the exit can be re-submitted);
* once E's bar is backfilled, both lines count as executed while the book moved
  once (N2 names the line that moved nothing).

``PlaybookStore.settle`` is not changed for any of this.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.playbook import wording
from app.playbook.models import SettlementResult
from tests.api_helpers import recent_bars
from tests.exit_idempotency_helpers import (
    FRIDAY,
    HISTORY,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    Book,
    gapped_bars,
    hold,
    legacy_exit_line,
    log_like_before_n166,
    open_book,
)

MONDAY = date(2026, 8, 17)


def _no_open(execution_date: date, *, source: str = "fake") -> str:
    return wording.SETTLEMENT_NO_OPEN_PRICE.format(
        symbol="2330",
        execution_date=execution_date.isoformat(),
        status="fresh",
        source=source,
    )


def _n1(clause: str) -> str:
    return wording.SETTLEMENT_EXIT_STALE_NOTE.format(batch_clause=clause)


def _reasons(result: SettlementResult) -> list[str]:
    return [line.reason for line in result.unsettled]


@pytest.fixture
def book(tmp_path: Path) -> Book:
    """2330 held, no cash; its series never traded on WEDNESDAY."""
    book = open_book(tmp_path / "playbook.db")
    book.prices.seed("2330", gapped_bars("2330", 100.0, missing={WEDNESDAY}))
    hold(book.store, "2330", 1, shares=300)
    book.store.set_cash(Decimal("0"))
    return book


# --- (g) N1：舊列每天出現在 unsettled ----------------------------------------------


def test_g_an_unsettleable_exit_line_of_a_closed_batch_says_so_every_day(book: Book) -> None:
    """(g): 批次已 closed、舊列仍每天待結算 → N1「已無持股」接在 NO_OPEN_PRICE 之後."""
    book.service.emergency_exit(today=TUESDAY)  # E = WEDNESDAY, never traded
    book.service.emergency_exit(today=THURSDAY)  # 判準 Z -> new line for FRIDAY

    friday = book.service.settle_pending(today=FRIDAY)

    assert friday.executed == 1  # the FRIDAY line closed the batch
    batch = book.store.get_batch("2330", 1)
    assert batch is not None and batch.status == "closed"
    expected = _no_open(WEDNESDAY) + _n1(wording.SETTLEMENT_EXIT_STALE_CLOSED)
    assert _reasons(friday) == [expected]
    assert friday.warnings[0] == expected

    # The next day the same line is still listed, with the same disclosure.
    monday = book.service.settle_pending(today=MONDAY)
    assert _reasons(monday) == [expected]
    assert book.store.portfolio_state().cash == Decimal("30000")


def test_n1_names_the_later_exit_line_while_the_batch_is_still_held(book: Book) -> None:
    """批次仍 open、另有較晚的 EMERGENCY 列 → N1 的第二個值，列出其預定執行日."""
    book.service.emergency_exit(today=TUESDAY)
    book.service.emergency_exit(today=THURSDAY)  # new line for FRIDAY, not due yet

    thursday = book.service.settle_pending(today=THURSDAY)

    assert _reasons(thursday) == [
        _no_open(WEDNESDAY)
        + _n1(wording.SETTLEMENT_EXIT_STALE_LATER.format(later_dates=FRIDAY.isoformat()))
    ]


def test_n1b_says_the_exit_can_be_resubmitted_when_nothing_else_covers(book: Book) -> None:
    """N1b（可選，已核可）：批次仍持有、沒有較晚的 EMERGENCY 列 → 可再次提交全部出清."""
    book.service.emergency_exit(today=TUESDAY)

    thursday = book.service.settle_pending(today=THURSDAY)

    assert _reasons(thursday) == [_no_open(WEDNESDAY) + wording.SETTLEMENT_EXIT_STALE_REOPEN_NOTE]
    # ...and that is true: the exit now writes a new line for the batch.
    again = book.service.emergency_exit(today=THURSDAY)
    assert [item.batch_no for item in again.directives] == [1]


def test_no_n1_before_any_later_day_has_traded(book: Book) -> None:
    """判準 Z 條件 (1) 不成立（E 之後還沒有日線）→ 只有 NO_OPEN_PRICE，不加 N1／N1b."""
    book.prices.seed("2330", recent_bars([100.0] * HISTORY, symbol="2330", end=TUESDAY))
    book.service.emergency_exit(today=TUESDAY)

    thursday = book.service.settle_pending(today=THURSDAY)

    assert _reasons(thursday) == [_no_open(WEDNESDAY, source="fake")]


def test_a_buy_line_without_an_open_gets_no_exit_note(book: Book) -> None:
    """N1／N1b 只講 EMERGENCY 賣單."""
    line = legacy_exit_line("2330", 100, execution_date=WEDNESDAY).model_copy(
        update={"action": "buy", "rule_id": "R1"}
    )
    log_like_before_n166(book.store, [line])

    thursday = book.service.settle_pending(today=THURSDAY)

    assert _reasons(thursday) == [_no_open(WEDNESDAY)]


# --- (f) N2：後補 E 日的 bar ------------------------------------------------------------


def test_f_a_backfilled_day_settles_both_lines_but_moves_the_book_once(book: Book) -> None:
    """(f): 兩列都判定成交、現金只入帳一次，N2 點名沒有移動帳冊的那一筆，緊接在摘要之後."""
    book.service.emergency_exit(today=TUESDAY)  # E = WEDNESDAY
    book.service.emergency_exit(today=THURSDAY)  # FRIDAY line
    # WEDNESDAY's bar turns up after all.
    book.prices.seed("2330", recent_bars([100.0] * HISTORY, symbol="2330", end=FRIDAY))

    friday = book.service.settle_pending(today=FRIDAY)

    assert friday.executed == 2
    assert book.store.portfolio_state().cash == Decimal("30000")  # 300 × 100, once
    assert friday.warnings[-2] == wording.SETTLEMENT_SUMMARY.format(
        settled_on=FRIDAY.isoformat(), executed=2, missed=0, pending=0
    )
    assert friday.warnings[-1] == wording.SETTLEMENT_EXIT_NOTHING_MOVED_NOTE.format(
        count=1, exit_items=f"2330第 1 批（預定執行日 {FRIDAY.isoformat()}）"
    )


def test_n2_covers_same_day_duplicates_written_before_n166(tmp_path: Path) -> None:
    """N2 也適用 N-166 之前留下的同日重複列."""
    legacy = open_book(tmp_path / "legacy.db")
    hold(legacy.store, "2330", 1, shares=300)
    legacy.store.set_cash(Decimal("0"))
    log_like_before_n166(legacy.store, [legacy_exit_line("2330", 300)] * 2)

    wednesday = legacy.service.settle_pending(today=WEDNESDAY)

    assert wednesday.executed == 2
    assert legacy.store.portfolio_state().cash == Decimal("30000")
    assert wednesday.warnings[-1] == wording.SETTLEMENT_EXIT_NOTHING_MOVED_NOTE.format(
        count=1, exit_items=f"2330第 1 批（預定執行日 {WEDNESDAY.isoformat()}）"
    )


def test_no_n2_when_every_exit_line_moved_the_book(tmp_path: Path) -> None:
    plain = open_book(tmp_path / "plain.db")
    hold(plain.store, "2330", 1, shares=300)
    plain.service.emergency_exit(today=TUESDAY)

    wednesday = plain.service.settle_pending(today=WEDNESDAY)

    assert wednesday.executed == 1
    assert wednesday.warnings[-1].startswith("T+1 結算：")


@pytest.mark.parametrize("state", ["no-batch-row", "skipped", "open-without-shares"])
def test_no_exit_note_when_the_batch_state_supports_neither_sentence(
    book: Book, state: str
) -> None:
    """N1 只寫 closed／有較晚列兩種值，N1b 只寫仍持有股數的 open 批次；其餘不加註."""
    if state == "no-batch-row":
        book.prices.seed("2454", gapped_bars("2454", 50.0, missing={WEDNESDAY}))
        log_like_before_n166(book.store, [legacy_exit_line("2454", 200)])
        symbol = "2454"
    else:
        log_like_before_n166(book.store, [legacy_exit_line("2330", 300)])
        batch = book.store.get_batch("2330", 1)
        assert batch is not None
        update = {"status": "skipped"} if state == "skipped" else {"remaining_shares": 0}
        book.store.save_batch(batch.model_copy(update=update))
        symbol = "2330"

    thursday = book.service.settle_pending(today=THURSDAY)

    assert _reasons(thursday) == [
        wording.SETTLEMENT_NO_OPEN_PRICE.format(
            symbol=symbol,
            execution_date=WEDNESDAY.isoformat(),
            status="fresh",
            source="fake",
        )
    ]
