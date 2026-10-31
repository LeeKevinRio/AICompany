"""N-176 (F7) reproduction: a 預定執行日 that turns out to be a closed day never settles.

Scratch file, NOT part of the repo. Run from ``apps/stock-desk/backend``::

    python -m pytest <this file> -p no:cacheprovider -rA -s

Scenario (tech-architect 2026-10-31, F7)
----------------------------------------
* T = TUESDAY 2026-08-11. The loaded series end on T, so every day after it is
  outside the observed range and ``TradingCalendar`` answers by the weekday rule
  (``app/data/calendar.py:74-85``, ``:91-93``): ``next_trading_day(T)`` is
  WEDNESDAY 2026-08-12 and the line is stamped ``execution_date = 2026-08-12``.
* WEDNESDAY turns out to be a closed day (typhoon day, say): the later price data
  simply have no 2026-08-12 bar. Every other weekday has one, through 2026-10-02.
* Settlement looks for ``bar.date == directive.execution_date``
  (``app/playbook/service.py:275-277``) and nothing else.

Bars are weekday-only (weekends dropped) with 2026-08-12 removed; the fake price
service filters by the requested ``end`` (= ``today``), so each call only sees the
bars that would have existed on that day.

Structure
---------
* ``test_expected_*``  assert the CORRECT behaviour (an order whose scheduled day had
                       no session is resolved once the market has traded again). They
                       FAIL while the defect exists. No assertion is weakened.
* ``test_observe_*``   pin the OBSERVED numbers (pass while the defect exists), print them.
* ``test_control_*``   comparison groups that must pass.

Offline: fake price services, DB under ``tmp_path``, every call pins ``today``.
Both an ordinary R1 buy and an EMERGENCY sell (pre-N-166 product line: two
transactions, no coverage test, no CEO-1 expiry rule) are exercised.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.data.calendar import TradingCalendar
from app.data.interface import PriceBar
from app.playbook.models import BatchState
from app.playbook.service import PlaybookService, build_calendar
from app.playbook.store import PlaybookStore
from tests.api_helpers import FakePriceService, recent_bars
from tests.playbook_helpers import confirm_rule_set

SERIES_END = date(2026, 10, 2)  # Friday
TUESDAY = date(2026, 8, 11)  # T, 排程日
HOLIDAY = date(2026, 8, 12)  # the 預定執行日 that is not traded
THURSDAY = date(2026, 8, 13)
FRIDAY = date(2026, 8, 14)
NEXT_FRIDAY = date(2026, 8, 21)
AFTER_FREEZE = date(2026, 9, 30)  # Wednesday, after the 20-trading-day freeze
HISTORY_DAYS = 100
START_CASH = Decimal("1000000")
HELD_SHARES = 300
HELD_COST = Decimal("100")
LATER_DAYS = [THURSDAY, FRIDAY, date(2026, 8, 17), NEXT_FRIDAY, AFTER_FREEZE, SERIES_END]


def weekday_bars(
    symbol: str, base: float, *, skip: date | None
) -> list[PriceBar]:
    """Flat weekday-only bars ending ``SERIES_END``; ``skip`` is a day with no session."""
    return [
        bar
        for bar in recent_bars([base] * HISTORY_DAYS, symbol=symbol, end=SERIES_END)
        if bar.date.weekday() < 5 and bar.date != skip
    ]


@dataclass
class Harness:
    service: PlaybookService
    store: PlaybookStore
    prices: FakePriceService
    index: FakePriceService
    holiday: date | None


def _build(tmp_path: Path, *, holiday: date | None, held: bool) -> Harness:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    confirm_rule_set(store)
    prices = FakePriceService()
    index = FakePriceService()
    prices.seed("2330", weekday_bars("2330", 100.0, skip=holiday))
    index.seed("^TWII", weekday_bars("^TWII", 20000.0, skip=holiday))
    store.ensure_batches(["2330"], batches_per_target=3)
    store.set_capital(cash=START_CASH, total_deploy=Decimal("1000000"), source="initial")
    if held:
        store.save_batch(
            BatchState(
                symbol="2330",
                batch_no=1,
                status="open",
                entry_date=date(2026, 8, 3),
                cost=HELD_COST,
                shares=HELD_SHARES,
                remaining_shares=HELD_SHARES,
                peak_close=HELD_COST,
            )
        )
    service = PlaybookService(
        store=store,
        market_resolver={"TW": prices},
        index_resolver={"TW": index, "US": index},
    )
    return Harness(service=service, store=store, prices=prices, index=index, holiday=holiday)


@pytest.fixture
def closed_day(tmp_path: Path) -> Harness:
    """R1 flow: batch 1 planned, 2026-08-12 never traded."""
    return _build(tmp_path, holiday=HOLIDAY, held=False)


@pytest.fixture
def closed_day_held(tmp_path: Path) -> Harness:
    """EMERGENCY flow: batch 1 open with 300 shares, 2026-08-12 never traded."""
    return _build(tmp_path, holiday=HOLIDAY, held=True)


@pytest.fixture
def normal_day(tmp_path: Path) -> Harness:
    """Control: every weekday trades, including 2026-08-12."""
    return _build(tmp_path, holiday=None, held=False)


@pytest.fixture
def normal_day_held(tmp_path: Path) -> Harness:
    return _build(tmp_path, holiday=None, held=True)


# --- helpers ------------------------------------------------------------------


def log(h: Harness, rule_id: str, action: str) -> list[tuple[int, str, int, str]]:
    """(id, execution_date, settled, status) of every matching log row."""
    return [
        (row["id"], row["execution_date"], row["settled"], row["status"])
        for row in h.store.directive_log()
        if row["rule_id"] == rule_id and row["action"] == action
    ]


def book(h: Harness) -> tuple[str, int, int, Decimal]:
    batch = h.store.get_batch("2330", 1)
    assert batch is not None
    return batch.status, batch.shares, batch.remaining_shares, h.store.portfolio_state().cash


def pending_on(h: Harness, day: date, rule_id: str) -> list[int]:
    return [
        item.directive_id
        for item in h.store.pending_directives(on_or_before=day)
        if item.directive.rule_id == rule_id and item.directive.execution_date == HOLIDAY
    ]


def settle_each(h: Harness, days: list[date]) -> list[tuple[date, int, int, int]]:
    """(day, executed, missed, unsettled) for each settle_pending run."""
    out = []
    for day in days:
        result = h.service.settle_pending(today=day)
        out.append((day, result.executed, result.missed, len(result.unsettled)))
    return out


def queue_r1(h: Harness) -> None:
    h.service.evaluate_today(today=TUESDAY)
    rows = log(h, "R1", "buy")
    assert len(rows) == 1
    assert rows[0][1] == HOLIDAY.isoformat()  # stamped by the weekday fallback


def queue_emergency(h: Harness) -> None:
    result = h.service.emergency_exit(today=TUESDAY)
    assert result.execution_date == HOLIDAY  # stamped by the weekday fallback
    assert result.total_shares == HELD_SHARES
    rows = log(h, "EMERGENCY", "sell")
    assert len(rows) == 1
    assert rows[0][1] == HOLIDAY.isoformat()


# --- calendar facts (the mechanism) ------------------------------------------


def _calendar_through(h: Harness, last: date) -> TradingCalendar:
    bars = [bar for bar in h.prices.bars["2330"] if bar.date <= last]
    return build_calendar(bars)


def test_observe_calendar_fallback_picks_the_closed_day(
    closed_day: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    cal_t = _calendar_through(closed_day, TUESDAY)
    cal_later = _calendar_through(closed_day, FRIDAY)
    with capsys.disabled():
        print("\n[OBSERVE calendar] known_range when series ends on T:", cal_t.known_range)
        print("[OBSERVE calendar] next_trading_day(T) with series ending on T:",
              cal_t.next_trading_day(TUESDAY), "| is_trading_day(HOLIDAY):",
              cal_t.is_trading_day(HOLIDAY))
        print("[OBSERVE calendar] known_range when series ends on FRI:", cal_later.known_range)
        print("[OBSERVE calendar] next_trading_day(T) with series ending on FRI:",
              cal_later.next_trading_day(TUESDAY), "| is_trading_day(HOLIDAY):",
              cal_later.is_trading_day(HOLIDAY))
    assert cal_t.next_trading_day(TUESDAY) == HOLIDAY
    assert cal_t.is_trading_day(HOLIDAY) is True  # weekday fallback, no observation
    assert cal_later.next_trading_day(TUESDAY) == THURSDAY
    assert cal_later.is_trading_day(HOLIDAY) is False  # observed absence


# --- R1 buy -------------------------------------------------------------------


def test_expected_r1_buy_on_closed_day_is_resolved_after_market_trades_again(
    closed_day: Harness,
) -> None:
    """Expected: once the market has traded on later days, an order whose scheduled
    day had no session is no longer waiting (settled, rolled or expired)."""
    queue_r1(closed_day)
    closed_day.service.settle_pending(today=NEXT_FRIDAY)
    assert pending_on(closed_day, NEXT_FRIDAY, "R1") == []


def test_observe_r1_buy_on_closed_day_never_settles(
    closed_day: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    queue_r1(closed_day)
    before = book(closed_day)
    runs = settle_each(closed_day, LATER_DAYS)
    after = book(closed_day)
    still = pending_on(closed_day, SERIES_END, "R1")
    last = closed_day.service.settle_pending(today=SERIES_END)
    with capsys.disabled():
        print("\n[OBSERVE R1] R1 log rows (id, exec_date, settled, status):",
              log(closed_day, "R1", "buy"))
        print("[OBSERVE R1] book before (status, shares, remaining, cash):", before)
        print("[OBSERVE R1] settle_pending runs (day, executed, missed, unsettled):")
        for run in runs:
            print("   ", run)
        print("[OBSERVE R1] book after 6 runs:", after)
        print("[OBSERVE R1] still pending on", SERIES_END, ":", still)
        print("[OBSERVE R1] last run warnings:", last.warnings)
    assert [(e, m, u) for _d, e, m, u in runs] == [(0, 0, 1)] * len(LATER_DAYS)
    assert before == after == ("planned", 0, 0, START_CASH)
    assert len(still) == 1
    assert log(closed_day, "R1", "buy")[0][2:] == (0, "pending")


def test_observe_r1_full_path_through_the_closed_day(
    closed_day: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    """evaluate_today on T, the closed day itself, then the next schedule day."""
    closed_day.service.evaluate_today(today=TUESDAY)
    snapshots: list[Any] = [("after T", log(closed_day, "R1", "buy"), book(closed_day))]
    wed = closed_day.service.evaluate_today(today=HOLIDAY)
    snapshots.append(("after closed Wed", log(closed_day, "R1", "buy"), book(closed_day)))
    thu = closed_day.service.evaluate_today(today=THURSDAY)
    snapshots.append(("after Thu", log(closed_day, "R1", "buy"), book(closed_day)))
    fri = closed_day.service.evaluate_today(today=FRIDAY)
    snapshots.append(("after Fri", log(closed_day, "R1", "buy"), book(closed_day)))
    with capsys.disabled():
        for name, rows, state in snapshots:
            print(f"\n[OBSERVE R1 full path] {name}: rows={rows} book={state}")
        for label, ev in (("closed Wed", wed), ("Thu", thu), ("Fri", fri)):
            assert ev.settlement is not None
            print(f"[OBSERVE R1 full path] {label}: data_date={ev.data_date} "
                  f"executed={ev.settlement.executed} unsettled={len(ev.settlement.unsettled)} "
                  f"directives={[(d.rule_id, d.action, d.batch_no) for d in ev.directives]}")
    # The stuck row never leaves the queue, whatever else happens.
    stuck = [row for row in log(closed_day, "R1", "buy") if row[1] == HOLIDAY.isoformat()]
    assert stuck and all(row[2:] == (0, "pending") for row in stuck)


def test_observe_r1_late_backfill_executes_the_stuck_row(
    closed_day: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    """Conditional hazard: if the missing bar is later back-filled (a provider gap rather
    than a real closure), the stale row is still settleable and buys again."""
    closed_day.service.evaluate_today(today=TUESDAY)  # stuck row, exec WED
    closed_day.service.evaluate_today(today=THURSDAY)  # re-issue, exec FRI
    closed_day.service.settle_pending(today=FRIDAY)  # the re-issue fills
    state_before = book(closed_day)
    closed_day.prices.seed("2330", weekday_bars("2330", 100.0, skip=None))  # back-fill
    late = closed_day.service.settle_pending(today=NEXT_FRIDAY)
    state_after = book(closed_day)
    with capsys.disabled():
        print("\n[OBSERVE R1 backfill] book after Fri fill (status, shares, remaining, cash):",
              state_before)
        print("[OBSERVE R1 backfill] late settle executed:", late.executed,
              "| book after:", state_after, "| cash deducted by the late run:",
              state_before[3] - state_after[3])
        print("[OBSERVE R1 backfill] R1 rows:", log(closed_day, "R1", "buy"))
    assert state_before[0] == "open"
    assert late.executed == 1
    assert state_before[3] - state_after[3] == Decimal("100") * state_before[1]


# --- EMERGENCY sell -----------------------------------------------------------


def test_expected_emergency_sell_on_closed_day_is_carried_out(closed_day_held: Harness) -> None:
    """Expected: the user's liquidation is carried out at the next available open --
    the batch ends up closed and the proceeds are in cash."""
    queue_emergency(closed_day_held)
    closed_day_held.service.settle_pending(today=NEXT_FRIDAY)
    status, _shares, remaining, cash = book(closed_day_held)
    assert (status, remaining) == ("closed", 0)
    assert cash == START_CASH + HELD_COST * HELD_SHARES


def test_expected_emergency_row_on_closed_day_does_not_stay_pending(
    closed_day_held: Harness,
) -> None:
    """Expected: no EMERGENCY sell is still waiting on a day that had no session."""
    queue_emergency(closed_day_held)
    closed_day_held.service.settle_pending(today=NEXT_FRIDAY)
    assert pending_on(closed_day_held, NEXT_FRIDAY, "EMERGENCY") == []


def test_observe_emergency_on_closed_day_is_pending_forever(
    closed_day_held: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    queue_emergency(closed_day_held)
    portfolio = closed_day_held.store.portfolio_state()
    before = book(closed_day_held)
    runs = settle_each(closed_day_held, LATER_DAYS)
    after = book(closed_day_held)
    still = pending_on(closed_day_held, SERIES_END, "EMERGENCY")
    with capsys.disabled():
        print("\n[OBSERVE EMERGENCY] emergency_until after the exit:", portfolio.emergency_until)
        print("[OBSERVE EMERGENCY] log rows (id, exec_date, settled, status):",
              log(closed_day_held, "EMERGENCY", "sell"))
        print("[OBSERVE EMERGENCY] book before (status, shares, remaining, cash):", before)
        print("[OBSERVE EMERGENCY] settle_pending runs (day, executed, missed, unsettled):")
        for run in runs:
            print("   ", run)
        print("[OBSERVE EMERGENCY] book after 6 runs:", after)
        print("[OBSERVE EMERGENCY] still pending on", SERIES_END, ":", still)
    assert [(e, m, u) for _d, e, m, u in runs] == [(0, 0, 1)] * len(LATER_DAYS)
    assert before == after == ("open", HELD_SHARES, HELD_SHARES, START_CASH)
    assert len(still) == 1
    assert log(closed_day_held, "EMERGENCY", "sell")[0][2:] == (0, "pending")


def test_observe_emergency_after_the_freeze_lapses(
    closed_day_held: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    """What the user sees 7 weeks later: freeze over, shares still open, row still pending."""
    queue_emergency(closed_day_held)
    freeze_until = closed_day_held.store.portfolio_state().emergency_until
    evaluation = closed_day_held.service.evaluate_today(today=AFTER_FREEZE)
    assert evaluation.settlement is not None
    held = [(row.batch_no, row.status, row.remaining_shares) for row in evaluation.snapshot
            if row.symbol == "2330"]
    with capsys.disabled():
        print("\n[OBSERVE EMERGENCY +7wk] emergency_until:", freeze_until,
              "| evaluated on:", AFTER_FREEZE)
        print("[OBSERVE EMERGENCY +7wk] mode:", evaluation.mode, "|", evaluation.mode_reason)
        print("[OBSERVE EMERGENCY +7wk] snapshot 2330 (batch, status, remaining):", held)
        print("[OBSERVE EMERGENCY +7wk] settlement executed / unsettled:",
              evaluation.settlement.executed, len(evaluation.settlement.unsettled))
        print("[OBSERVE EMERGENCY +7wk] unsettled reason:",
              [u.reason for u in evaluation.settlement.unsettled])
        print("[OBSERVE EMERGENCY +7wk] directives today:",
              [(d.rule_id, d.action, d.symbol, d.batch_no) for d in evaluation.directives])
    assert evaluation.mode == "normal"  # freeze lapsed
    assert (1, "open", HELD_SHARES) in held
    assert len(evaluation.settlement.unsettled) == 1


def test_observe_emergency_retry_resolves_batch_but_leaves_the_stuck_row(
    closed_day_held: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    """A second exit on THU (batch still shows shares) fills on FRI; the WED row stays."""
    queue_emergency(closed_day_held)
    second = closed_day_held.service.emergency_exit(today=THURSDAY)
    rows = log(closed_day_held, "EMERGENCY", "sell")
    runs = settle_each(closed_day_held, [FRIDAY, NEXT_FRIDAY])
    state = book(closed_day_held)
    stuck = pending_on(closed_day_held, SERIES_END, "EMERGENCY")
    # Back-fill the closed day: does the stale row move anything?
    closed_day_held.prices.seed("2330", weekday_bars("2330", 100.0, skip=None))
    late = closed_day_held.service.settle_pending(today=SERIES_END)
    state_late = book(closed_day_held)
    with capsys.disabled():
        print("\n[OBSERVE EMERGENCY retry] second exit execution_date:", second.execution_date,
              "total_shares:", second.total_shares)
        print("[OBSERVE EMERGENCY retry] rows (id, exec_date, settled, status):", rows)
        print("[OBSERVE EMERGENCY retry] settle runs (day, executed, missed, unsettled):", runs)
        print("[OBSERVE EMERGENCY retry] book after (status, shares, remaining, cash):", state)
        print("[OBSERVE EMERGENCY retry] stale row still pending:", stuck)
        print("[OBSERVE EMERGENCY retry] after back-fill: executed", late.executed,
              "| book:", state_late, "| cash delta:", state_late[3] - state[3])
    assert len(rows) == 2 and rows[1][1] == FRIDAY.isoformat()
    assert state == ("closed", HELD_SHARES, 0, START_CASH + HELD_COST * HELD_SHARES)
    assert len(stuck) == 1
    assert late.executed == 1
    assert state_late == state  # min()/max() guards: counted as executed, moved 0 shares


# --- controls -----------------------------------------------------------------


def test_control_r1_buy_settles_when_the_day_traded(normal_day: Harness) -> None:
    """Control: identical flow, 2026-08-12 traded -> the R1 buy fills on it."""
    normal_day.service.evaluate_today(today=TUESDAY)
    result = normal_day.service.settle_pending(today=HOLIDAY)
    assert result.executed == 1 and result.unsettled == []
    status, shares, remaining, cash = book(normal_day)
    assert (status, shares, remaining) == ("open", 666, 666)
    assert cash == START_CASH - Decimal("100") * 666


def test_control_emergency_sell_settles_when_the_day_traded(normal_day_held: Harness) -> None:
    """Control: identical flow, 2026-08-12 traded -> the exit fills on it."""
    normal_day_held.service.emergency_exit(today=TUESDAY)
    result = normal_day_held.service.settle_pending(today=HOLIDAY)
    assert result.executed == 1 and result.unsettled == []
    assert book(normal_day_held) == (
        "closed",
        HELD_SHARES,
        0,
        START_CASH + HELD_COST * HELD_SHARES,
    )


def test_control_not_yet_due_is_not_reported_unsettled(closed_day_held: Harness) -> None:
    """Control: on T itself the line is simply not due (execution_date > today)."""
    closed_day_held.service.emergency_exit(today=TUESDAY)
    result = closed_day_held.service.settle_pending(today=TUESDAY)
    assert result.settled == [] and result.unsettled == []


_ = Callable, Iterator  # keep imports used by type checkers
