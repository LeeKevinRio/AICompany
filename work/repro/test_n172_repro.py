"""N-172 / F5 reproduction: repeated evaluation on a schedule day re-issues R1 buys.

Scratch file, NOT part of the repo. Run from ``apps/stock-desk/backend``::

    python -m pytest <this file> -p no:cacheprovider -rA -s

Structure
---------
* ``test_*_expected_*``      assert the CORRECT behaviour ("buy once"). They FAIL
                             while the defect exists. No assertion is weakened.
* ``test_observe_*``         pin the OBSERVED numbers (they pass while the defect
                             exists) and print them, so the report quotes
                             measured values rather than estimates.
* ``test_control_*``         non-schedule-day / already-settled replays. These must
                             pass: they show where duplication does NOT happen.

Offline: fake price services, DB under ``tmp_path``, every call pins ``today``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_cap1_weight, get_playbook_service
from app.main import app
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import CLIENT_HEADERS, FakePriceService, recent_bars
from tests.playbook_helpers import confirm_rule_set

SERIES_END = date(2026, 8, 14)  # Friday
MONDAY = date(2026, 8, 10)  # not a schedule day
TUESDAY = date(2026, 8, 11)  # schedule day (T)
WEDNESDAY = date(2026, 8, 12)  # T+1, not a schedule day
HISTORY = 40

START_CASH = Decimal("1000000")
ONE_BUY_SHARES = 666  # same figure as tests/test_playbook_settlement.py
ONE_BUY_COST = Decimal("100") * ONE_BUY_SHARES  # 66,600


class ClockedService(PlaybookService):
    """Pins the clock for the HTTP path only.

    ``GET /today`` calls ``service.evaluate_today()`` with no argument, i.e. the
    real clock (2026-10-31 is a Saturday). This subclass supplies the default
    ``today`` and changes nothing else; the route, response mapping and every
    store call are production code.
    """

    pinned: date = TUESDAY

    def evaluate_today(self, *, today: date | None = None):  # type: ignore[override]
        return super().evaluate_today(today=today or self.pinned)


@dataclass
class Harness:
    service: ClockedService
    store: PlaybookStore
    prices: FakePriceService


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    confirm_rule_set(store)
    prices = FakePriceService()
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=SERIES_END))
    prices.seed("2330", recent_bars([100.0] * HISTORY, symbol="2330", end=SERIES_END))
    store.ensure_batches(["2330"], batches_per_target=3)
    store.set_capital(cash=START_CASH, total_deploy=Decimal("1000000"), source="initial")
    service = ClockedService(
        store=store,
        market_resolver={"TW": prices},
        index_resolver={"TW": index, "US": index},
    )
    yield Harness(service=service, store=store, prices=prices)


def r1_buys(h: Harness, batch_no: int = 1) -> list[dict]:
    return [
        row
        for row in h.store.directive_log()
        if row["rule_id"] == "R1" and row["action"] == "buy" and row["batch_no"] == batch_no
    ]


def book(h: Harness) -> tuple[int, int, str, Decimal]:
    batch = h.store.get_batch("2330", 1)
    assert batch is not None
    return batch.shares, batch.remaining_shares, batch.status, h.store.portfolio_state().cash


# --- service level: evaluate_today -------------------------------------------


def test_schedule_day_replay_expected_one_r1_row(harness: Harness) -> None:
    """Expected: two evaluations on Tuesday queue ONE R1 buy for batch 1."""
    harness.service.evaluate_today(today=TUESDAY)
    harness.service.evaluate_today(today=TUESDAY)
    assert len(r1_buys(harness)) == 1


def test_t_plus_1_expected_book_equals_single_buy(harness: Harness) -> None:
    """Expected: after Wednesday settlement the book equals a single buy."""
    harness.service.evaluate_today(today=TUESDAY)
    harness.service.evaluate_today(today=TUESDAY)
    harness.service.evaluate_today(today=WEDNESDAY)  # /today settles first

    shares, _remaining, status, cash = book(harness)
    assert status == "open"
    assert shares == ONE_BUY_SHARES
    assert cash == START_CASH - ONE_BUY_COST


def test_observe_rows_and_book_after_two_calls(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    harness.service.evaluate_today(today=TUESDAY)
    rows_after_1 = len(r1_buys(harness))
    pending_after_1 = len(harness.store.pending_directives())
    harness.service.evaluate_today(today=TUESDAY)
    rows_after_2 = len(r1_buys(harness))
    pending_after_2 = len(harness.store.pending_directives())
    batch_before_settle = harness.store.get_batch("2330", 1)
    assert batch_before_settle is not None
    cash_before_settle = harness.store.portfolio_state().cash

    wed = harness.service.evaluate_today(today=WEDNESDAY)
    assert wed.settlement is not None
    shares, remaining, status, cash = book(harness)
    after_settle_rows = [
        (r["id"], r["shares"], r["status"], r["settled"]) for r in r1_buys(harness)
    ]
    with capsys.disabled():
        print("\n[OBSERVE 2 calls] R1 buy rows after call 1:", rows_after_1)
        print("[OBSERVE 2 calls] R1 buy rows after call 2:", rows_after_2)
        print("[OBSERVE 2 calls] pending after call 1/2:", pending_after_1, pending_after_2)
        print("[OBSERVE 2 calls] batch status before settle:", batch_before_settle.status)
        print("[OBSERVE 2 calls] cash before settle:", cash_before_settle)
        print("[OBSERVE 2 calls] Wednesday executed/missed:", wed.settlement.executed,
              wed.settlement.missed)
        print("[OBSERVE 2 calls] rows after settle (id, shares, status, settled):",
              after_settle_rows)
        print("[OBSERVE 2 calls] batch shares/remaining/status:", shares, remaining, status)
        print("[OBSERVE 2 calls] cash:", cash, " expected-if-once:", START_CASH - ONE_BUY_COST,
              " deducted:", START_CASH - cash, " ledger-implied shares:",
              (START_CASH - cash) / Decimal("100"))
    # Pin the observed (defective) outcome.
    assert (rows_after_1, rows_after_2) == (1, 2)
    assert (pending_after_1, pending_after_2) == (1, 2)
    assert wed.settlement.executed == 2
    assert (shares, remaining, status) == (ONE_BUY_SHARES, ONE_BUY_SHARES, "open")
    assert cash == START_CASH - 2 * ONE_BUY_COST


def test_observe_rows_grow_one_per_extra_call(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    counts = []
    for _ in range(5):
        harness.service.evaluate_today(today=TUESDAY)
        counts.append(len(r1_buys(harness)))
    wed = harness.service.evaluate_today(today=WEDNESDAY)
    assert wed.settlement is not None
    shares, _remaining, _status, cash = book(harness)
    with capsys.disabled():
        print("\n[OBSERVE N calls] R1 rows after calls 1..5:", counts)
        print("[OBSERVE N calls] Wednesday executed:", wed.settlement.executed)
        print("[OBSERVE N calls] batch shares:", shares, " cash:", cash,
              " deducted:", START_CASH - cash, " multiple of one buy:",
              (START_CASH - cash) / ONE_BUY_COST)
    assert counts == [1, 2, 3, 4, 5]
    assert shares == ONE_BUY_SHARES
    assert cash == START_CASH - 5 * ONE_BUY_COST


# --- HTTP level: GET /api/playbook/today -------------------------------------


@pytest.fixture
def client(harness: Harness) -> Iterator[TestClient]:
    app.dependency_overrides[get_playbook_service] = lambda: harness.service
    app.dependency_overrides[get_cap1_weight] = lambda: Decimal("0.10")
    with TestClient(app, headers=CLIENT_HEADERS) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_today_twice_expected_one_row(harness: Harness, client: TestClient) -> None:
    """Expected: two ``GET /today`` on Tuesday queue ONE R1 buy."""
    assert client.get("/api/playbook/today").status_code == 200
    assert client.get("/api/playbook/today").status_code == 200
    assert len(r1_buys(harness)) == 1


def test_observe_get_today_rows_and_book(
    harness: Harness, client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    body_rows = []
    counts = []
    for _ in range(3):
        response = client.get("/api/playbook/today")
        assert response.status_code == 200
        body = response.json()
        counts.append(len(r1_buys(harness)))
        body_rows.append(
            len(
                [
                    d
                    for d in body["directives"]
                    if d["directive"]["rule_id"] == "R1" and d["directive"]["action"] == "buy"
                ]
            )
        )
    # T+1: Wednesday's GET /today settles then evaluates.
    harness.service.pinned = WEDNESDAY
    wed_body = client.get("/api/playbook/today").json()
    shares, _remaining, status, cash = book(harness)
    with capsys.disabled():
        print("\n[OBSERVE HTTP] R1 buy rows in DB after GET 1..3:", counts)
        print("[OBSERVE HTTP] R1 buy lines inside each response body:", body_rows)
        print("[OBSERVE HTTP] Wednesday settlement executed:", wed_body["settlement"]["executed"])
        print("[OBSERVE HTTP] batch shares/status:", shares, status, " cash:", cash,
              " deducted:", START_CASH - cash)
    assert counts == [1, 2, 3]
    assert shares == ONE_BUY_SHARES
    assert cash == START_CASH - 3 * ONE_BUY_COST


# --- controls ----------------------------------------------------------------


def test_control_non_schedule_day_replay_writes_no_r1(harness: Harness) -> None:
    """Monday (not 週二／四) never produces R1, however often it is replayed."""
    for _ in range(3):
        harness.service.evaluate_today(today=MONDAY)
    assert r1_buys(harness) == []
    assert harness.store.pending_directives() == []


def test_control_replay_after_settlement_does_not_duplicate(harness: Harness) -> None:
    """Tuesday once, Wednesday settles; Wednesday replays add nothing."""
    harness.service.evaluate_today(today=TUESDAY)
    harness.service.evaluate_today(today=WEDNESDAY)
    before = (len(r1_buys(harness)), book(harness))
    harness.service.evaluate_today(today=WEDNESDAY)
    harness.service.evaluate_today(today=WEDNESDAY)
    after = (len(r1_buys(harness)), book(harness))
    assert before == after
    assert before[0] == 1
    assert before[1][3] == START_CASH - ONE_BUY_COST


def test_control_single_tuesday_call_is_correct(harness: Harness) -> None:
    """The happy path: one call, one row, one buy (matches the existing suite)."""
    harness.service.evaluate_today(today=TUESDAY)
    harness.service.evaluate_today(today=WEDNESDAY)
    assert len(r1_buys(harness)) == 1
    assert book(harness)[0] == ONE_BUY_SHARES
    assert book(harness)[3] == START_CASH - ONE_BUY_COST
