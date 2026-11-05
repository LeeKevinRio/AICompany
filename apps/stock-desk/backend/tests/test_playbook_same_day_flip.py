"""A same-day re-evaluation that turns 凍結／防守 keeps and discloses the first R1 (ADR-0035 S-α).

N-174(c): the first call on a 排程日 queued an R1 buy; a second call on the same
依據資料日, with the lagging bar now in, turned the book 凍結 (S3) or 防守 (M1)
and stopped listing the buy -- which T+1 then settled anyway (qa 重現). Under
S-α (CEO #83) the first decision stands, the page lists the logged line, and
``SAME_DAY_EARLIER_ENTRY_NOTE`` says what it is (CEO #86 合併門檻).

The first half is qa's reproduction (``work/repro/test_n174_repro.py``): its 8
expected tests, now green, and its 8 controls, on the service path and on
``GET /today`` (N172-T19); the observe test is gone. Then N172-T7 and 風控
CEO #87 回審 第 7、9、10、11 點 (二-1、二-3).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_cap1_reading, get_playbook_service
from app.api.playbook import TodayResponse, _to_response
from app.api.playbook_cap1_wording import Cap1Reading, compose
from app.data.interface import PriceBar
from app.main import app
from app.playbook import wording
from app.playbook.models import PlaybookEvaluation
from app.playbook.store import PlaybookStore
from tests.api_helpers import CLIENT_HEADERS, FakePriceService
from tests.same_day_helpers import (
    MONDAY,
    ONE_BUY_SHARES,
    SERIES_END,
    START_CASH,
    SUNDAY,
    TUESDAY,
    WEDNESDAY,
    ClockedService,
    Desk,
    bars,
    capped,
    hold,
    open_desk,
    rule_rows,
)

HELD = "2317"
TARGET = "2330"


# --- qa's harness (work/repro/test_n174_repro.py) ------------------------------------


@dataclass
class Harness:
    scenario: str
    service: ClockedService
    store: PlaybookStore
    prices: FakePriceService
    index: FakePriceService
    full: dict[str, list[PriceBar]]
    clock: dict[str, date] = field(default_factory=lambda: {"today": TUESDAY})


@pytest.fixture(params=["s3", "defense"])
def scenario(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def harness(tmp_path: Path, scenario: str) -> Harness:
    desk = open_desk(tmp_path / "playbook.db", symbols=(TARGET, HELD))
    full: dict[str, list[PriceBar]] = {TARGET: bars(TARGET, 100.0)}
    if scenario == "s3":
        # 2317 loses 9% on T (-9% < s3_unrealized_pct -8%); S1 (0.90) is NOT hit.
        held = {day: 91.0 for day in (TUESDAY, WEDNESDAY, date(2026, 8, 13), SERIES_END)}
        full[HELD] = bars(HELD, 100.0, held)
        full["^TWII"] = bars("^TWII", 20000.0)
    else:
        # Index closes below its 20-day line on SUN, MON (2 days) and TUE (3 days).
        below = {SUNDAY: 19000.0, MONDAY: 18900.0}
        below |= {day: 18800.0 for day in (TUESDAY, WEDNESDAY, date(2026, 8, 13), SERIES_END)}
        full[HELD] = bars(HELD, 100.0)
        full["^TWII"] = bars("^TWII", 20000.0, below)
    for batch_no in (1, 2, 3):
        hold(desk.store, HELD, batch_no, shares=100, entry_date=date(2026, 8, 3))
    desk.prices.seed(TARGET, full[TARGET])
    desk.prices.seed(HELD, full[HELD])
    desk.index.seed("^TWII", full["^TWII"])
    h = Harness(
        scenario=scenario,
        service=desk.service,
        store=desk.store,
        prices=desk.prices,
        index=desk.index,
        full=full,
    )
    stage_partial_data(h)
    return h


def stage_partial_data(h: Harness) -> None:
    """Call-1 state of the world: T-1 is the newest bar for the part that lags."""
    if h.scenario == "s3":
        h.prices.seed(HELD, capped(h.full[HELD], MONDAY))
    else:
        h.index.seed("^TWII", capped(h.full["^TWII"], MONDAY))


def stage_full_data(h: Harness) -> None:
    """The lagging bar for T has arrived (call 2 onwards)."""
    h.prices.seed(HELD, h.full[HELD])
    h.index.seed("^TWII", h.full["^TWII"])


@dataclass(frozen=True)
class View:
    mode: str
    warnings: tuple[str, ...]
    directives: tuple[tuple[str, str, str, int | None], ...]
    executed: int
    unsettled: int

    @property
    def frozen_note(self) -> bool:
        label = wording.MODE_LABELS[self.mode]  # type: ignore[index]
        return wording.FROZEN_NOTE.format(mode=label) in self.warnings

    @property
    def lists_r1_buy(self) -> bool:
        return any(rule == "R1" and action == "buy" for rule, action, _s, _b in self.directives)


def _view_service(evaluation: PlaybookEvaluation) -> View:
    settlement = evaluation.settlement
    return View(
        mode=evaluation.mode,
        warnings=tuple(evaluation.warnings),
        directives=tuple(
            (line.rule_id, line.action, line.symbol, line.batch_no)
            for line in evaluation.directives
        ),
        executed=0 if settlement is None else settlement.executed,
        unsettled=0 if settlement is None else len(settlement.unsettled),
    )


def _view_http(body: dict[str, Any]) -> View:
    settlement = body["settlement"]

    def key(line: dict[str, Any]) -> tuple[str, str, str, int | None]:
        return line["rule_id"], line["action"], line["symbol"], line["batch_no"]

    return View(
        mode=body["mode"],
        warnings=tuple(body["warnings"]),
        directives=tuple(key(item["directive"]) for item in body["directives"]),
        executed=0 if settlement is None else settlement["executed"],
        unsettled=0 if settlement is None else len(settlement["unsettled"]),
    )


@pytest.fixture(params=["service", "http"])
def call(request: pytest.FixtureRequest, harness: Harness) -> Iterator[Callable[[date], View]]:
    if request.param == "service":

        def via_service(day: date) -> View:
            return _view_service(harness.service.evaluate_today(today=day))

        yield via_service
        return

    app.dependency_overrides[get_playbook_service] = lambda: harness.service
    app.dependency_overrides[get_cap1_reading] = lambda: Cap1Reading(
        weight=Decimal("0.10"), from_default=False
    )
    with TestClient(app, headers=CLIENT_HEADERS) as client:

        def via_http(day: date) -> View:
            harness.service.pinned = day
            response = client.get("/api/playbook/today")
            assert response.status_code == 200, response.text
            return _view_http(response.json())

        yield via_http
    app.dependency_overrides.clear()


def _target_book(h: Harness) -> tuple[str, int, int, Decimal]:
    batch = h.store.get_batch(TARGET, 1)
    assert batch is not None
    return batch.status, batch.shares, batch.remaining_shares, h.store.portfolio_state().cash


@dataclass
class Replay:
    first: View
    second: View
    third: View
    book_after_settle: tuple[str, int, int, Decimal]


def run_replay(h: Harness, call: Callable[[date], View]) -> Replay:
    first = call(TUESDAY)
    stage_full_data(h)
    second = call(TUESDAY)
    third = call(WEDNESDAY)
    return Replay(first=first, second=second, third=third, book_after_settle=_target_book(h))


# --- N172-T19: expected (now green) ---------------------------------------------------


def test_expected_flipped_replay_does_not_contradict_the_book(
    harness: Harness, call: Callable[[date], View]
) -> None:
    """If call 2 says 凍結/防守 and no longer lists the R1 buy, T+1 must not execute it.

    Under S-α call 2 still lists the logged buy, so the defect case -- note, no
    line, a settled buy -- cannot arise.
    """
    replay = run_replay(harness, call)
    assert replay.second.mode in {"frozen", "defense"}
    says_not_executed = replay.second.frozen_note and not replay.second.lists_r1_buy
    executed_at_t1 = replay.book_after_settle[0] == "open"
    assert not (says_not_executed and executed_at_t1), (
        f"call 2 mode={replay.second.mode!r} with FROZEN_NOTE and no R1 line, "
        f"but T+1 settled it: book={replay.book_after_settle}"
    )


def test_expected_frozen_mode_move_no_cash_for_unlisted_buy(
    harness: Harness, call: Callable[[date], View]
) -> None:
    """Cash only moves for a buy the latest response still lists."""
    replay = run_replay(harness, call)
    moved = START_CASH - replay.book_after_settle[3]
    listed = replay.second.lists_r1_buy
    assert moved == 0 or listed, f"cash moved by {moved} for a buy call 2 did not list"


# --- N172-T19: controls ---------------------------------------------------------------


def test_control_frozen_from_the_first_call_buys_nothing(
    harness: Harness, call: Callable[[date], View]
) -> None:
    """Complete data on the first call -> frozen/defense at once, no R1, no buy."""
    stage_full_data(harness)
    first = call(TUESDAY)
    assert first.mode in {"frozen", "defense"}
    assert first.frozen_note
    assert not first.lists_r1_buy
    assert rule_rows(harness.store.db_path, "R1", "buy") == []
    third = call(WEDNESDAY)
    assert third.executed == 0
    assert _target_book(harness) == ("planned", 0, 0, START_CASH)


def test_control_flip_after_t_plus_1_open_is_not_a_contradiction(
    harness: Harness, call: Callable[[date], View]
) -> None:
    """The flip only comes with T+1's own bar: the buy fills at T+1's open, strictly
    before the close that triggers the freeze (tech-architect case (a))."""
    later = (WEDNESDAY, date(2026, 8, 13), SERIES_END)
    if harness.scenario == "s3":
        harness.prices.seed(HELD, bars(HELD, 100.0, {day: 60.0 for day in later}))
    else:
        below = {MONDAY: 19000.0, TUESDAY: 18900.0} | {day: 18800.0 for day in later}
        harness.index.seed("^TWII", bars("^TWII", 20000.0, below))
        harness.prices.seed(HELD, harness.full[HELD])
    first = call(TUESDAY)
    assert first.mode == "normal" and first.lists_r1_buy
    third = call(WEDNESDAY)
    assert third.executed == 1
    assert third.mode in {"frozen", "defense"}
    assert third.frozen_note
    assert _target_book(harness)[0] == "open"


# --- N172-T7: zero new rows, the R1 listed, the disclosure right after FROZEN_NOTE -----


def _entry_note(*lines: tuple[str, int, int]) -> str:
    return wording.SAME_DAY_EARLIER_ENTRY_NOTE.format(
        entry_count=len(lines),
        entry_items="、".join(
            wording.SAME_DAY_EARLIER_ENTRY_ITEM.format(
                symbol=symbol,
                batch_no=batch_no,
                shares=shares,
                rule_id="R1",
                execution_date=WEDNESDAY.isoformat(),
            )
            for symbol, batch_no, shares in lines
        ),
    )


def test_a_flipped_replay_writes_nothing_lists_the_buy_and_discloses_it(
    harness: Harness, call: Callable[[date], View]
) -> None:
    first = call(TUESDAY)
    rows = rule_rows(harness.store.db_path, "R1", "buy")
    stage_full_data(harness)
    second = call(TUESDAY)

    assert first.lists_r1_buy and not first.frozen_note
    assert rule_rows(harness.store.db_path, "R1", "buy") == rows and len(rows) == 1
    assert second.mode in {"frozen", "defense"}
    assert second.directives == first.directives
    label = wording.MODE_LABELS[second.mode]  # type: ignore[index]
    frozen = list(second.warnings).index(wording.FROZEN_NOTE.format(mode=label))
    assert second.warnings[frozen + 1] == _entry_note((TARGET, 1, ONE_BUY_SHARES))
    assert sum(warning.startswith("指令帳冊中有") for warning in second.warnings) == 1
    third = call(WEDNESDAY)
    assert third.executed == 1  # S-α: the first decision stands


# --- 風控 第 7 點: the five triggers, and the one that is not -------------------------


@pytest.fixture
def desk(tmp_path: Path) -> Desk:
    return open_desk(tmp_path / "playbook.db")


def test_entry_note_after_an_emergency_freeze(desk: Desk) -> None:
    """出清凍結: an exit after the first run turns the second one 緊急出清後凍結.

    ADR-0034 (N-168): the exit stamped the pending R1 buy, so W-B6 names it right
    after FROZEN_NOTE and ENTRY, which may not list it again, is not rendered
    (風控 2026-11-01 P4／P5).
    """
    desk.service.evaluate_today(today=TUESDAY)
    desk.service.emergency_exit(today=TUESDAY)
    second = desk.service.evaluate_today(today=TUESDAY)

    assert second.mode == "emergency_frozen"
    frozen = wording.FROZEN_NOTE.format(mode=wording.MODE_LABELS["emergency_frozen"])
    position = second.warnings.index(frozen)
    assert second.warnings[position + 1] == wording.PENDING_ENTRY_FROZEN_NOTE.format(
        entry_count=1,
        entry_items=wording.SAME_DAY_EARLIER_ENTRY_ITEM.format(
            symbol="2330",
            batch_no=1,
            shares=ONE_BUY_SHARES,
            rule_id="R1",
            execution_date=WEDNESDAY.isoformat(),
        ),
    )
    assert _entry_note(("2330", 1, ONE_BUY_SHARES)) not in second.warnings
    assert [(line.rule_id, line.action) for line in second.directives] == [("R1", "buy")]


def test_entry_note_on_an_index_gap_comes_first_and_drops_the_untrue_deferral(
    desk: Desk,
) -> None:
    """指數缺漏: 「當日不新開倉」 next to a logged buy. The engine's M1 deferral is
    blocked by K2, so INDEX_DATA_GAP_DEFER_NOTE is not true and goes (第 10 點)."""
    desk.service.evaluate_today(today=TUESDAY)
    desk.index.seed("^TWII", [])
    second = desk.service.evaluate_today(today=TUESDAY)

    assert second.mode == "normal"
    assert second.warnings[0] == _entry_note(("2330", 1, ONE_BUY_SHARES))
    assert wording.INDEX_DATA_GAP_NOTE.format(status="unavailable", source="none") in (
        second.warnings
    )
    assert wording.INDEX_DATA_GAP_DEFER_NOTE not in second.warnings
    assert rule_rows(desk.store.db_path, "M1", "defer") == []
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.defer_count == 0


def test_entry_note_when_the_second_run_would_defer_under_r2(desk: Desk) -> None:
    """R2 改判順延: the corrected Tuesday close is a chase; the first R1 stands."""
    desk.service.evaluate_today(today=TUESDAY)
    desk.prices.seed("2330", bars("2330", 100.0, {TUESDAY: 110.0}))
    second = desk.service.evaluate_today(today=TUESDAY)

    assert second.warnings[0] == _entry_note(("2330", 1, ONE_BUY_SHARES))
    assert [(line.rule_id, line.action) for line in second.directives] == [("R1", "buy")]
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.defer_count == 0


def test_no_entry_note_when_the_run_produced_the_same_buy(desk: Desk) -> None:
    """The engine's output holds a buy of the same K1 -> nothing to disclose."""
    desk.service.evaluate_today(today=TUESDAY)
    second = desk.service.evaluate_today(today=TUESDAY)

    assert not [warning for warning in second.warnings if warning.startswith("指令帳冊中有")]


def test_entry_note_lists_every_earlier_buy_once(tmp_path: Path) -> None:
    """Two symbols, two logged buys, one sentence counting both (N-168 item format)."""
    desk = open_desk(tmp_path / "playbook.db", symbols=("2330", "2454"))
    desk.service.evaluate_today(today=TUESDAY)
    for symbol in ("2330", "2454"):
        desk.prices.seed(symbol, bars(symbol, 100.0, {TUESDAY: 110.0}))
    second = desk.service.evaluate_today(today=TUESDAY)

    assert second.warnings[0] == _entry_note(
        ("2330", 1, ONE_BUY_SHARES), ("2454", 1, ONE_BUY_SHARES)
    )


# --- 風控 第 9 點: no_directive_note reads the logged list -----------------------------


def _response(evaluation: PlaybookEvaluation) -> TodayResponse:
    """The ``GET /today`` body for ``evaluation``, through the production mapping."""
    params = evaluation.params
    return _to_response(
        evaluation,
        cap1_disclosure=compose(
            rules_version=params.version,
            deploy_ratio=params.deploy_ratio,
            n_targets=params.n_targets,
            batches_per_target=params.batches_per_target,
            deploy_ratio_pct="70%",
            cap1_reading=Cap1Reading(weight=Decimal("0.10"), from_default=False),
        ),
    )


def test_no_rule_hit_note_is_not_stated_next_to_a_logged_stop_loss(desk: Desk) -> None:
    """Run 1 logs an S1 sell; the corrected close hits nothing on run 2 -- the page
    still lists the S1, so 「無任何規則命中，未產生指令」 may not appear."""
    hold(desk.store, "2330", 1, shares=300, cost="100")
    for batch_no in (2, 3):
        hold(desk.store, "2330", batch_no, shares=300, cost="50", p1_done=True, p2_done=True)
    desk.prices.seed("2330", bars("2330", 100.0, {TUESDAY: 85.0}))
    first = desk.service.evaluate_today(today=TUESDAY)
    assert [(line.rule_id, line.batch_no) for line in first.directives] == [("S1", 1)]

    desk.prices.seed("2330", bars("2330", 100.0))
    second = desk.service.evaluate_today(today=TUESDAY)

    assert second.rules_fully_evaluated  # the engine hit nothing this time
    response = _response(second)
    assert [item.directive.rule_id for item in response.directives] == ["S1"]
    assert response.no_directive_note is None


def test_no_rule_hit_note_still_shows_on_a_truly_empty_day(desk: Desk) -> None:
    """Control: nothing logged, nothing hit -> the sentence is there as before."""
    for batch_no in (1, 2, 3):
        hold(desk.store, "2330", batch_no, shares=300, cost="100")
    evaluation = desk.service.evaluate_today(today=TUESDAY)

    assert evaluation.directives == [] and evaluation.rules_fully_evaluated
    assert _response(evaluation).no_directive_note == wording.NO_RULE_HIT_NOTE


# --- 風控 第 10 點: shrink notes of a blocked R decision -------------------------------


def test_a_shrink_of_a_blocked_entry_is_not_stated(desk: Desk) -> None:
    """Run 2 reads less cash and would shrink the R1 to 350 股; the page lists run 1's
    666 股 line, so 「由 666 股縮減為 350 股」 is not true there."""
    desk.service.evaluate_today(today=TUESDAY)
    desk.store.set_cash(Decimal("50000"))  # budget 35,000 -> 350 股 at 100
    second = desk.service.evaluate_today(today=TUESDAY)

    shrink = "2330：" + wording.SHRINK_NOTE.format(planned=ONE_BUY_SHARES, actual=350)
    assert shrink not in second.warnings
    assert not [warning for warning in second.warnings if "鐵律①" in warning]
    assert [line.shares for line in second.directives] == [ONE_BUY_SHARES]


def test_a_cancellation_of_a_blocked_entry_is_not_stated(desk: Desk) -> None:
    """Run 2 would cancel the entry outright; the logged buy stands and is disclosed."""
    desk.service.evaluate_today(today=TUESDAY)
    desk.store.set_cash(Decimal("100"))
    second = desk.service.evaluate_today(today=TUESDAY)

    assert wording.SHRINK_TO_ZERO_NOTE.format(symbol="2330", batch_no=1) not in second.warnings
    assert second.warnings[0] == _entry_note(("2330", 1, ONE_BUY_SHARES))


def test_a_shrink_on_the_first_run_is_still_stated(tmp_path: Path) -> None:
    """Control: the run that writes the line keeps its own 鐵律① sentence."""
    desk = open_desk(tmp_path / "playbook.db", cash=Decimal("50000"))
    first = desk.service.evaluate_today(today=TUESDAY)

    assert "2330：" + wording.SHRINK_NOTE.format(planned=ONE_BUY_SHARES, actual=350) in (
        first.warnings
    )
    assert [line.shares for line in first.directives] == [350]


def test_the_index_gap_deferral_note_needs_an_m1_deferral_line(desk: Desk) -> None:
    """第 10 點, read literally: the note renders only when the list holds an M1 順延列.

    A third index-gap deferral is written as an R3 skip, not as an M1 順延, so the
    note is not rendered even on the run that wrote it -- approved as intended by
    風控 2026-11-01 解讀點 (b): that batch is skipped for good, not deferred.
    """
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None
    desk.store.save_batch(batch.model_copy(update={"defer_count": 2}))
    desk.index.seed("^TWII", [])
    first = desk.service.evaluate_today(today=TUESDAY)

    assert [(line.rule_id, line.action) for line in first.directives] == [("R3", "skip")]
    assert wording.INDEX_DATA_GAP_DEFER_NOTE not in first.warnings
    assert wording.INDEX_DATA_GAP_NOTE.format(status="unavailable", source="none") in (
        first.warnings
    )


# --- 風控 第 11 點: a data gap next to lines an earlier run logged ---------------------


def test_a_data_gap_after_a_logged_stop_loss_says_the_line_stands(tmp_path: Path) -> None:
    """Run 1 logs 2317's S1; run 2 has no 2317 data -- the gap sentence 「當日不產生指令」
    is followed by SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE."""
    desk = open_desk(tmp_path / "playbook.db", symbols=("2330", "2317"))
    hold(desk.store, "2317", 1, shares=300, cost="100")
    desk.prices.seed("2317", bars("2317", 100.0, {TUESDAY: 85.0}))
    first = desk.service.evaluate_today(today=TUESDAY)
    assert ("2317", "S1") in {(line.symbol, line.rule_id) for line in first.directives}

    desk.prices.seed("2317", [])
    second = desk.service.evaluate_today(today=TUESDAY)

    gap = wording.DATA_GAP_HOLDING_NOTE.format(symbol="2317", status="unavailable", source="none")
    position = second.warnings.index(gap)
    assert second.warnings[position + 1] == wording.SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE.format(
        symbol="2317", status="unavailable", line_count=1
    )
    assert ("2317", "S1") in {(line.symbol, line.rule_id) for line in second.directives}


def test_a_data_gap_after_a_logged_entry_says_both_sentences(desk: Desk) -> None:
    """標的資料缺漏 on the R1 symbol: the gap note, its follow-up, and the entry note."""
    desk.prices.seed("2454", bars("2454", 100.0))  # keeps the 依據資料日 on Tuesday
    desk.service.evaluate_today(today=TUESDAY)
    desk.prices.seed("2330", [])
    second = desk.service.evaluate_today(today=TUESDAY)

    gap = wording.DATA_GAP_NOTE.format(symbol="2330", status="unavailable", source="none")
    position = second.warnings.index(gap)
    assert second.warnings[position + 1] == wording.SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE.format(
        symbol="2330", status="unavailable", line_count=1
    )
    assert second.warnings[0] == _entry_note(("2330", 1, ONE_BUY_SHARES))


def test_no_follow_up_for_a_gap_symbol_without_logged_lines(tmp_path: Path) -> None:
    """Control: 2317 had nothing on the list, so its gap sentence stands alone."""
    desk = open_desk(tmp_path / "playbook.db", symbols=("2330", "2317"))
    hold(desk.store, "2317", 1, shares=300, cost="100")
    desk.prices.seed("2317", [])
    evaluation = desk.service.evaluate_today(today=TUESDAY)

    assert not [warning for warning in evaluation.warnings if "本次未重新評估這檔" in warning]
