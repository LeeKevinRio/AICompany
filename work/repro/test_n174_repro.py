"""N-174 (c) reproduction: same-data_date replay flips to 凍結/防守, the queued R1 buy still settles.

Scratch file, NOT part of the repo. Run from ``apps/stock-desk/backend``::

    python -m pytest <this file> -p no:cacheprovider -rA -s

Scenario (tech-architect 2026-10-31, Q4 (c))
--------------------------------------------
* Call 1, ``today = TUESDAY`` (T, a 排程日): only part of the data has T. In the
  S3 variant the held symbol 2317 only has bars up to MONDAY (T-1); in the
  defense variant the index only has bars up to MONDAY. Mode is ``normal``, so R1
  queues a buy of 2330 batch 1 for 預定執行日 WEDNESDAY.
* Call 2, ``today = TUESDAY`` again: the missing T bar has arrived. S3 variant:
  2317 closes at 91 (-9% < -8%) and the portfolio freezes. Defense variant: the
  index's third consecutive close below its monthly line puts M1 defense on.
* Call 3, ``today = WEDNESDAY`` (T+1): ``settle_pending`` runs first.

The fake price service filters bars by the requested ``end`` (= ``today``), so
"the bar for T has not arrived yet" is staged by seeding a series capped at
MONDAY and re-seeding the full series before call 2.

Structure
---------
* ``test_expected_*``  assert the CORRECT behaviour ("the response and the book do
                       not contradict each other"). They FAIL while the defect
                       exists. No assertion is weakened.
* ``test_observe_*``   pin the OBSERVED numbers (pass while the defect exists) and
                       print them so the report quotes measured values.
* ``test_control_*``   comparison groups that must pass.

Offline: fake price services, DB under ``tmp_path``, every call pins ``today``.
Each test runs on both the service path and the HTTP path (``GET /today``).
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

from app.api.deps import get_cap1_weight, get_playbook_service
from app.data.interface import PriceBar
from app.main import app
from app.playbook import wording
from app.playbook.models import BatchState
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import CLIENT_HEADERS, FakePriceService, recent_bars
from tests.playbook_helpers import confirm_rule_set

SERIES_END = date(2026, 8, 14)  # Friday
SUNDAY = date(2026, 8, 9)
MONDAY = date(2026, 8, 10)  # T-1
TUESDAY = date(2026, 8, 11)  # T, 排程日
WEDNESDAY = date(2026, 8, 12)  # T+1
HISTORY = 40
START_CASH = Decimal("1000000")

HELD = "2317"
TARGET = "2330"


# --- series builders ----------------------------------------------------------


def _closes(base: float, overrides: dict[date, float]) -> list[float]:
    """``HISTORY`` consecutive daily closes ending ``SERIES_END`` with overrides."""
    closes = [base] * HISTORY
    for day, value in overrides.items():
        closes[HISTORY - 1 - (SERIES_END - day).days] = value
    return closes


def _cap(bars: list[PriceBar], last: date) -> list[PriceBar]:
    return [bar for bar in bars if bar.date <= last]


# --- harness ------------------------------------------------------------------


@dataclass
class Harness:
    scenario: str
    service: PlaybookService
    store: PlaybookStore
    prices: FakePriceService
    index: FakePriceService
    full: dict[str, list[PriceBar]]
    clock: dict[str, date] = field(default_factory=lambda: {"today": TUESDAY})


class ClockedService(PlaybookService):
    """Pins the clock for the HTTP path only; production code otherwise."""

    clock: dict[str, date]

    def evaluate_today(self, *, today: date | None = None):  # type: ignore[override]
        return super().evaluate_today(today=today or self.clock["today"])


@pytest.fixture(params=["s3", "defense"])
def scenario(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def harness(tmp_path: Path, scenario: str) -> Iterator[Harness]:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    confirm_rule_set(store)
    prices = FakePriceService()
    index = FakePriceService()
    clock = {"today": TUESDAY}

    full: dict[str, list[PriceBar]] = {}
    full[TARGET] = recent_bars([100.0] * HISTORY, symbol=TARGET, end=SERIES_END)
    held_overrides: dict[date, float] = {}
    index_overrides: dict[date, float] = {}
    if scenario == "s3":
        # 2317 loses 9% on T (-9% < s3_unrealized_pct -8%); S1 (0.90) is NOT hit.
        held_overrides = {d: 91.0 for d in (TUESDAY, WEDNESDAY, date(2026, 8, 13), SERIES_END)}
    else:
        # Index: closes below its own 20-day line on SUN, MON (2 days) and TUE (3 days).
        index_overrides = {
            SUNDAY: 19000.0,
            MONDAY: 18900.0,
            TUESDAY: 18800.0,
            WEDNESDAY: 18800.0,
            date(2026, 8, 13): 18800.0,
            SERIES_END: 18800.0,
        }
    full[HELD] = recent_bars(_closes(100.0, held_overrides), symbol=HELD, end=SERIES_END)
    full["^TWII"] = recent_bars(
        _closes(20000.0, index_overrides), symbol="^TWII", end=SERIES_END
    )

    store.ensure_batches([TARGET, HELD], batches_per_target=3)
    for batch_no in (1, 2, 3):
        store.save_batch(
            BatchState(
                symbol=HELD,
                batch_no=batch_no,
                status="open",
                entry_date=date(2026, 8, 3),
                cost=Decimal("100"),
                shares=100,
                remaining_shares=100,
                peak_close=Decimal("100"),
            )
        )
    store.set_capital(cash=START_CASH, total_deploy=Decimal("1000000"), source="initial")

    prices.seed(TARGET, full[TARGET])
    index.seed("^TWII", full["^TWII"])
    prices.seed(HELD, full[HELD])
    service = ClockedService(
        store=store,
        market_resolver={"TW": prices},
        index_resolver={"TW": index, "US": index},
    )
    service.clock = clock
    h = Harness(
        scenario=scenario,
        service=service,
        store=store,
        prices=prices,
        index=index,
        full=full,
        clock=clock,
    )
    stage_partial_data(h)
    yield h


def stage_partial_data(h: Harness) -> None:
    """Call-1 state of the world: T-1 is the newest bar for the part that lags."""
    if h.scenario == "s3":
        h.prices.seed(HELD, _cap(h.full[HELD], MONDAY))
    else:
        h.index.seed("^TWII", _cap(h.full["^TWII"], MONDAY))


def stage_full_data(h: Harness) -> None:
    """The lagging bar for T has arrived (call 2 onwards)."""
    h.prices.seed(HELD, h.full[HELD])
    h.index.seed("^TWII", h.full["^TWII"])


# --- uniform view over the two paths -----------------------------------------


@dataclass(frozen=True)
class View:
    mode: str
    warnings: tuple[str, ...]
    directives: tuple[tuple[str, str, str, int | None], ...]
    executed: int
    settled: tuple[tuple[str, str, str, int | None], ...]
    unsettled: int
    data_date: str

    @property
    def frozen_note(self) -> bool:
        label = wording.MODE_LABELS[self.mode]  # type: ignore[index]
        return wording.FROZEN_NOTE.format(mode=label) in self.warnings

    @property
    def lists_r1_buy(self) -> bool:
        return any(rule == "R1" and action == "buy" for rule, action, _s, _b in self.directives)


def _view_service(evaluation: Any) -> View:
    settlement = evaluation.settlement
    return View(
        mode=evaluation.mode,
        warnings=tuple(evaluation.warnings),
        directives=tuple(
            (d.rule_id, d.action, d.symbol, d.batch_no) for d in evaluation.directives
        ),
        executed=0 if settlement is None else settlement.executed,
        settled=tuple(
            (s.directive.rule_id, s.directive.action, s.directive.symbol, s.directive.batch_no)
            for s in (settlement.settled if settlement else [])
        ),
        unsettled=0 if settlement is None else len(settlement.unsettled),
        data_date=evaluation.data_date.isoformat(),
    )


def _view_http(body: dict[str, Any]) -> View:
    settlement = body["settlement"]

    def key(d: dict[str, Any]) -> tuple[str, str, str, int | None]:
        return d["rule_id"], d["action"], d["symbol"], d["batch_no"]

    return View(
        mode=body["mode"],
        warnings=tuple(body["warnings"]),
        directives=tuple(key(item["directive"]) for item in body["directives"]),
        executed=0 if settlement is None else settlement["executed"],
        settled=tuple(key(s["directive"]) for s in (settlement["settled"] if settlement else [])),
        unsettled=0 if settlement is None else len(settlement["unsettled"]),
        data_date=body["data_date"],
    )


@pytest.fixture(params=["service", "http"])
def call(request: pytest.FixtureRequest, harness: Harness) -> Iterator[Callable[[date], View]]:
    if request.param == "service":

        def via_service(day: date) -> View:
            return _view_service(harness.service.evaluate_today(today=day))

        yield via_service
        return

    app.dependency_overrides[get_playbook_service] = lambda: harness.service
    app.dependency_overrides[get_cap1_weight] = lambda: Decimal("0.10")
    with TestClient(app, headers=CLIENT_HEADERS) as client:

        def via_http(day: date) -> View:
            harness.clock["today"] = day
            response = client.get("/api/playbook/today")
            assert response.status_code == 200, response.text
            return _view_http(response.json())

        yield via_http
    app.dependency_overrides.clear()


# --- store helpers ------------------------------------------------------------


def r1_rows(h: Harness) -> list[dict[str, Any]]:
    return [
        row
        for row in h.store.directive_log()
        if row["rule_id"] == "R1" and row["action"] == "buy" and row["batch_no"] == 1
        and row["symbol"] == TARGET
    ]


def target_book(h: Harness) -> tuple[str, int, int, Decimal]:
    batch = h.store.get_batch(TARGET, 1)
    assert batch is not None
    return batch.status, batch.shares, batch.remaining_shares, h.store.portfolio_state().cash


@dataclass
class Replay:
    first: View
    second: View
    third: View
    rows_after_first: int
    rows_after_second: int
    pending_after_second: list[tuple[int, str, str, str, str]]
    book_before_settle: tuple[str, int, int, Decimal]
    book_after_settle: tuple[str, int, int, Decimal]
    r1_shares: int


def run_replay(h: Harness, call: Callable[[date], View]) -> Replay:
    first = call(TUESDAY)
    rows_after_first = len(r1_rows(h))
    stage_full_data(h)
    second = call(TUESDAY)
    rows_after_second = len(r1_rows(h))
    pending = [
        (
            p.directive_id,
            p.directive.rule_id,
            p.directive.action,
            p.directive.symbol,
            p.directive.execution_date.isoformat(),
        )
        for p in h.store.pending_directives()
    ]
    before = target_book(h)
    third = call(WEDNESDAY)
    after = target_book(h)
    rows = r1_rows(h)
    return Replay(
        first=first,
        second=second,
        third=third,
        rows_after_first=rows_after_first,
        rows_after_second=rows_after_second,
        pending_after_second=pending,
        book_before_settle=before,
        book_after_settle=after,
        r1_shares=rows[0]["shares"] if rows else 0,
    )


# --- expected: the response and the book must not contradict ------------------


def test_expected_flipped_replay_does_not_contradict_the_book(
    harness: Harness, call: Callable[[date], View]
) -> None:
    """Expected: if call 2 says 凍結/防守 ("R 進場不執行") and no longer lists the R1 buy,
    then that buy must not be executed at T+1.

    Either fix satisfies this: (i) the buy is cancelled/not settled, or (ii) call 2
    still lists the pending buy. The defect is the third case: note + no line + a
    settled buy.
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
    """Expected: cash only moves for a buy the latest response still lists."""
    replay = run_replay(harness, call)
    moved = START_CASH - replay.book_after_settle[3]
    listed = replay.second.lists_r1_buy
    assert moved == 0 or listed, f"cash moved by {moved} for a buy call 2 did not list"


# --- observe: pin the measured values ----------------------------------------


def test_observe_flipped_replay(
    harness: Harness,
    call: Callable[[date], View],
    scenario: str,
    request: pytest.FixtureRequest,
    capsys: pytest.CaptureFixture[str],
) -> None:
    replay = run_replay(harness, call)
    path = request.node.callspec.params["call"]
    tag = f"[OBSERVE {scenario}/{path}]"
    with capsys.disabled():
        print(f"\n{tag} call1 mode / data_date / directives:", replay.first.mode,
              replay.first.data_date, list(replay.first.directives))
        print(f"{tag} call1 frozen_note:", replay.first.frozen_note)
        print(f"{tag} call2 mode / data_date / directives:", replay.second.mode,
              replay.second.data_date, list(replay.second.directives))
        print(f"{tag} call2 FROZEN_NOTE present:", replay.second.frozen_note,
              "| lists R1 buy:", replay.second.lists_r1_buy)
        print(f"{tag} call2 warnings:", list(replay.second.warnings))
        print(f"{tag} R1 rows after call1/call2:", replay.rows_after_first,
              replay.rows_after_second)
        print(f"{tag} pending rows after call2 (id, rule, action, symbol, exec_date):",
              replay.pending_after_second)
        print(f"{tag} book before T+1 (status, shares, remaining, cash):",
              replay.book_before_settle)
        print(f"{tag} call3 (T+1) settlement executed:", replay.third.executed,
              "settled:", list(replay.third.settled), "unsettled:", replay.third.unsettled)
        print(f"{tag} call3 mode / FROZEN_NOTE present / directives:", replay.third.mode,
              replay.third.frozen_note, list(replay.third.directives))
        print(f"{tag} book after T+1 (status, shares, remaining, cash):",
              replay.book_after_settle, "| R1 shares:", replay.r1_shares,
              "| cash deducted:", START_CASH - replay.book_after_settle[3],
              "| expected cost 100 x shares:", Decimal(100) * replay.r1_shares)

    expected_mode = "frozen" if scenario == "s3" else "defense"
    assert replay.first.mode == "normal"
    assert replay.first.lists_r1_buy
    assert not replay.first.frozen_note
    assert replay.second.mode == expected_mode
    assert replay.second.frozen_note
    assert not replay.second.lists_r1_buy
    assert (replay.rows_after_first, replay.rows_after_second) == (1, 1)
    assert [(rule, action) for _i, rule, action, *_ in replay.pending_after_second] == [
        ("R1", "buy")
    ]
    assert replay.book_before_settle[0] == "planned"
    assert replay.third.executed == 1
    assert replay.third.mode == expected_mode
    assert replay.third.frozen_note
    assert replay.book_after_settle[0] == "open"
    assert replay.book_after_settle[3] == START_CASH - Decimal(100) * replay.r1_shares


# --- controls -----------------------------------------------------------------


def test_control_frozen_from_the_first_call_buys_nothing(
    harness: Harness, call: Callable[[date], View]
) -> None:
    """Control: complete data on the first call -> frozen/defense at once, no R1, no buy."""
    stage_full_data(harness)
    first = call(TUESDAY)
    assert first.mode in {"frozen", "defense"}
    assert first.frozen_note
    assert not first.lists_r1_buy
    assert r1_rows(harness) == []
    third = call(WEDNESDAY)
    assert third.executed == 0
    assert target_book(harness) == ("planned", 0, 0, START_CASH)


def test_control_flip_after_t_plus_1_open_is_not_a_contradiction(
    harness: Harness, call: Callable[[date], View]
) -> None:
    """Control (tech-architect case (a)): the flip only comes with T+1's own bar.

    Data is complete on every call (nothing lags); the lagging bar of the main
    scenario is replaced by a drop that first appears on WEDNESDAY. The buy executes
    at T+1 open, strictly before the close that triggers the freeze. Same response
    states the settlement and the new mode, and the order of events is consistent.
    (S3 variant: 2317 -> 60 on WED, enough to stay under -8% even after the new 2330
    batch dilutes the portfolio figure. Defense variant: 3rd close below the line on WED.)
    """
    if harness.scenario == "s3":
        harness.prices.seed(
            HELD,
            recent_bars(
                _closes(100.0, {d: 60.0 for d in (WEDNESDAY, date(2026, 8, 13), SERIES_END)}),
                symbol=HELD,
                end=SERIES_END,
            ),
        )
    else:
        harness.index.seed(
            "^TWII",
            recent_bars(
                _closes(
                    20000.0,
                    {
                        MONDAY: 19000.0,
                        TUESDAY: 18900.0,
                        WEDNESDAY: 18800.0,
                        date(2026, 8, 13): 18800.0,
                        SERIES_END: 18800.0,
                    },
                ),
                symbol="^TWII",
                end=SERIES_END,
            ),
        )
        harness.prices.seed(HELD, harness.full[HELD])
    first = call(TUESDAY)
    assert first.mode == "normal" and first.lists_r1_buy
    third = call(WEDNESDAY)
    assert third.executed == 1
    assert third.mode in {"frozen", "defense"}
    assert third.frozen_note
    assert target_book(harness)[0] == "open"
