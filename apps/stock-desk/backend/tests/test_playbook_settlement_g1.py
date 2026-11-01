"""G1: a buy only fills a ``planned`` batch (ADR-0035 Decision 6′, CEO #88).

K1／K2 close the same-預定執行日 duplicates; they cannot close the cross-day one
(V4). A line whose 預定執行日 had no bar stays pending, the next 排程日 issues a
new line for the same still-planned batch, that one fills -- and when the
missing bar is back-filled later the old line used to fill too, paying for the
batch twice (qa N-176 額外觀察 2). A batch is bought once in its life, so the
claim now refuses a buy whose batch already left ``planned``: nothing moves,
the line stays pending and ``unsettled`` names it with
``SETTLEMENT_BATCH_ALREADY_FILLED_NOTE`` (風控 CEO #87 回審 二-2). N172-T17,
T20, T21 and 風控 第 8 點.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.interface import PriceBar
from app.playbook import wording
from app.playbook.models import BatchStatus
from app.playbook.store import PlaybookStore
from tests.api_helpers import recent_bars
from tests.same_day_helpers import (
    ONE_BUY_COST,
    ONE_BUY_SHARES,
    START_CASH,
    TUESDAY,
    WEDNESDAY,
    Desk,
    buy_line,
    log_like_before_n172a,
    log_rows,
    open_desk,
    rule_rows,
)

THURSDAY = date(2026, 8, 13)
FRIDAY = date(2026, 8, 14)
NEXT_FRIDAY = date(2026, 8, 21)
LONG_END = date(2026, 10, 2)


def _weekdays(symbol: str, *, skip: date | None) -> list[PriceBar]:
    """Flat weekday-only bars to ``LONG_END``; ``skip`` had no session (or no data yet)."""
    return [
        bar
        for bar in recent_bars([100.0] * 100, symbol=symbol, end=LONG_END)
        if bar.date.weekday() < 5 and bar.date != skip
    ]


def _filled_reason(*, state: BatchStatus, execution_date: date = WEDNESDAY) -> str:
    return wording.SETTLEMENT_BATCH_ALREADY_FILLED_NOTE.format(
        symbol="2330",
        batch_no=1,
        shares=ONE_BUY_SHARES,
        rule_id="R1",
        execution_date=execution_date.isoformat(),
        batch_state=wording.SETTLEMENT_BATCH_STATES[state],
    )


@pytest.fixture
def desk(tmp_path: Path) -> Desk:
    return open_desk(tmp_path / "playbook.db")


# --- N172-T17: the late back-fill no longer pays twice ---------------------------------


def test_a_back_filled_bar_does_not_buy_an_already_filled_batch_again(tmp_path: Path) -> None:
    """T17: Tue R1 (Wed has no bar), Thu R1 again, Fri fills, then Wed's bar arrives."""
    desk = open_desk(tmp_path / "playbook.db", seed=True)
    for ladder, symbol in ((desk.prices, "2330"), (desk.index, "^TWII")):
        ladder.seed(symbol, _weekdays(symbol, skip=WEDNESDAY))
    desk.service.evaluate_today(today=TUESDAY)
    desk.service.evaluate_today(today=THURSDAY)
    assert [row[4] for row in rule_rows(desk.store.db_path, "R1", "buy")] == [
        WEDNESDAY.isoformat(),
        FRIDAY.isoformat(),
    ]
    friday = desk.service.settle_pending(today=FRIDAY)
    assert (friday.executed, len(friday.unsettled)) == (1, 1)
    filled = desk.store.portfolio_state().cash
    assert filled == START_CASH - ONE_BUY_COST

    desk.prices.seed("2330", _weekdays("2330", skip=None))  # the provider back-fills Wed
    late = desk.service.settle_pending(today=NEXT_FRIDAY)

    assert desk.store.portfolio_state().cash == filled  # paid once
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    assert (batch.status, batch.shares) == ("open", ONE_BUY_SHARES)
    assert late.executed == 0
    assert [line.reason for line in late.unsettled] == [_filled_reason(state="open")]
    assert late.warnings[0] == _filled_reason(state="open")
    assert late.warnings[1] == wording.SETTLEMENT_SUMMARY.format(
        settled_on=NEXT_FRIDAY.isoformat(), executed=0, missed=0, pending=1
    )
    # Not claimed, not MISSED: still pending, and listed again by the next run.
    assert rule_rows(desk.store.db_path, "R1", "buy")[0][5:] == (0, "pending")
    again = desk.service.settle_pending(today=NEXT_FRIDAY + timedelta(days=3))
    assert [line.reason for line in again.unsettled] == [_filled_reason(state="open")]


# --- 風控 第 8 點: the three batch states, and planned ----------------------------------


@pytest.mark.parametrize("state", ["open", "closed", "skipped"])
def test_the_reason_names_the_batch_state(desk: Desk, state: BatchStatus) -> None:
    log_like_before_n172a(desk.store, [buy_line()])
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    desk.store.save_batch(batch.model_copy(update={"status": state}))
    before = (desk.store.get_batch("2330", 1), desk.store.portfolio_state().cash)

    result = desk.service.settle_pending(today=WEDNESDAY)

    assert result.settled == []
    assert [line.reason for line in result.unsettled] == [_filled_reason(state=state)]
    assert (desk.store.get_batch("2330", 1), desk.store.portfolio_state().cash) == before


def test_a_refused_line_keeps_its_place_next_to_a_line_without_a_price(desk: Desk) -> None:
    """Each unsettled line keeps its own reason, in log order: G1's, then 尚無開盤價."""
    saturday = date(2026, 8, 15)  # after the last seeded bar
    log_like_before_n172a(desk.store, [buy_line(), buy_line(batch_no=2, execution_date=saturday)])
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    desk.store.save_batch(batch.model_copy(update={"status": "open"}))

    result = desk.service.settle_pending(today=saturday)

    assert [line.directive.batch_no for line in result.unsettled] == [1, 2]
    assert result.unsettled[0].reason == _filled_reason(state="open")
    assert result.unsettled[1].reason == wording.SETTLEMENT_NO_OPEN_PRICE.format(
        symbol="2330", execution_date=saturday.isoformat(), status="fresh", source="fake"
    )


def test_a_planned_batch_fills_and_never_gets_the_reason(desk: Desk) -> None:
    """T20 / 第 8 點: the ordinary single fill is untouched by G1."""
    log_like_before_n172a(desk.store, [buy_line()])

    result = desk.service.settle_pending(today=WEDNESDAY)

    assert (result.executed, result.unsettled) == (1, [])
    assert not [warning for warning in result.warnings if "不是待買進狀態" in warning]
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and (batch.status, batch.shares) == ("open", ONE_BUY_SHARES)
    assert desk.store.portfolio_state().cash == START_CASH - ONE_BUY_COST


def test_a_planned_batch_miss_still_counts(desk: Desk) -> None:
    """T20: a MISSED buy of a planned batch is claimed and counted as before (E-2)."""
    log_like_before_n172a(desk.store, [buy_line(reference="120")])  # opens at 100

    result = desk.service.settle_pending(today=WEDNESDAY)

    assert (result.executed, result.missed, result.unsettled) == (0, 1, [])
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and (batch.status, batch.missed_count) == ("planned", 1)


def test_a_sell_is_not_held_back_by_g1(desk: Desk) -> None:
    """G1 is about buys only: a sell of an open batch settles as before."""
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    desk.store.save_batch(
        batch.model_copy(
            update={"status": "open", "shares": 300, "remaining_shares": 300, "cost": Decimal(90)}
        )
    )
    sell = buy_line().model_copy(update={"action": "sell", "rule_id": "P1", "shares": 100})
    log_like_before_n172a(desk.store, [sell])

    result = desk.service.settle_pending(today=WEDNESDAY)

    assert result.executed == 1
    after = desk.store.get_batch("2330", 1)
    assert after is not None and after.remaining_shares == 200


def test_two_same_day_duplicates_from_before_n172a_buy_once(desk: Desk) -> None:
    """D-F (未結算重複列): the twin of a filled line is now refused, not paid again."""
    log_like_before_n172a(desk.store, [buy_line()])
    log_like_before_n172a(desk.store, [buy_line()])

    result = desk.service.settle_pending(today=WEDNESDAY)

    assert result.executed == 1
    assert [line.reason for line in result.unsettled] == [_filled_reason(state="open")]
    assert desk.store.portfolio_state().cash == START_CASH - ONE_BUY_COST


# --- N172-T21: two kinds of "the claim changed no row" -----------------------------------


def test_the_store_tells_a_refused_claim_from_a_taken_one(desk: Desk) -> None:
    log_like_before_n172a(desk.store, [buy_line(), buy_line()])
    first, second = desk.store.pending_directives()
    assert desk.store.claim_directive(
        first.directive_id, status="executed", open_price=Decimal(100)
    )
    desk.store.settle(first.directive.model_copy(update={"status": "executed"}))

    # Taken: the row is settled -- whatever its batch is now.
    assert not desk.store.claim_directive(
        first.directive_id, status="executed", open_price=Decimal(100)
    )
    assert desk.store.batch_blocking_claim(first.directive_id) is None
    # Refused by G1: unsettled, a buy, its batch open.
    assert not desk.store.claim_directive(
        second.directive_id, status="executed", open_price=Decimal(100)
    )
    assert desk.store.batch_blocking_claim(second.directive_id) == "open"
    assert [row[5:] for row in log_rows(desk.store.db_path)] == [(1, "executed"), (0, "pending")]


def test_a_row_another_settlement_took_is_not_reported_as_g1(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T21: a stale pending list names a row that is settled now and whose batch is open.

    Both conditions of G1's refusal look alike from the ``rowcount``; this one is
    "someone else settled it", so it is skipped silently as before -- no G1
    reason, no second fill.
    """
    log_like_before_n172a(desk.store, [buy_line()])
    stale = desk.store.pending_directives(on_or_before=WEDNESDAY)
    desk.service.settle_pending(today=WEDNESDAY)  # the other settlement
    cash = desk.store.portfolio_state().cash
    monkeypatch.setattr(desk.store, "pending_directives", lambda **_: stale)

    result = desk.service.settle_pending(today=WEDNESDAY)

    assert (result.settled, result.unsettled) == ([], [])
    assert desk.store.portfolio_state().cash == cash


def test_a_missing_batch_row_is_not_refused(tmp_path: Path) -> None:
    """G1 guards a batch that exists and left ``planned``; with no batch row there is
    nothing to protect, so the claim behaves as before (``settle`` moves nothing)."""
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    log_like_before_n172a(store, [buy_line()])
    (pending,) = store.pending_directives()

    assert store.claim_directive(pending.directive_id, status="executed", open_price=Decimal(100))
    assert store.batch_blocking_claim(pending.directive_id) is None
