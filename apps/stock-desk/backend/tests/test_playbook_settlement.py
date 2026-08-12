"""T+1 結算接線 (CEO 裁決七): the book actually moves, and moves only once.

The qa review's BLOCKING finding was that ``settle`` had no production caller:
the engine decided lines forever and the ledger never advanced, so the same
batch was re-issued every day. These tests drive the wired path -- evaluate,
settle against the 預定執行日 opening price, look at the book -- and pin the two
properties that make it safe to call from ``GET /today`` on every request:
replay does not deduct twice, and a missing opening price is reported rather
than invented.

Offline and dated: the fake price service returns the same fixed bars whatever
the clock says, and every call passes ``today`` explicitly, so a test that
passes today passes on a Sunday in December too.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import FakePriceService, recent_bars
from tests.playbook_helpers import confirm_rule_set

#: The seeded series ends on this Friday, so a settlement run "on Wednesday"
#: still finds Wednesday's bar without depending on the real date.
SERIES_END = date(2026, 8, 14)
#: 排程日 (週二) used as the 依據資料日.
TUESDAY = date(2026, 8, 11)
#: Its 預定執行日.
WEDNESDAY = date(2026, 8, 12)
HISTORY = 40


@dataclass
class Harness:
    service: PlaybookService
    store: PlaybookStore
    prices: FakePriceService


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    # 風控 R2: the rules have to be the user's own before a line may be produced.
    confirm_rule_set(store)
    prices = FakePriceService()
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=SERIES_END))
    yield Harness(
        service=PlaybookService(
            store=store,
            market_resolver={"TW": prices},
            index_resolver={"TW": index, "US": index},
        ),
        store=store,
        prices=prices,
    )


def _seed(harness: Harness, symbol: str, closes: list[float]) -> None:
    harness.prices.seed(symbol, recent_bars(closes, symbol=symbol, end=SERIES_END))


def _flat_with(day: date, value: float, *, base: float = 100.0) -> list[float]:
    """A flat series of ``HISTORY`` days whose bar on ``day`` is ``value``.

    ``recent_bars`` opens every bar at its close, so this is how a test says
    "the market opened at 110 on the 預定執行日".
    """
    closes = [base] * HISTORY
    closes[HISTORY - 1 - (SERIES_END - day).days] = value
    return closes


def _fund(harness: Harness, *, cash: str = "1000000", deploy: str = "1000000") -> None:
    harness.store.set_capital(
        cash=Decimal(cash), total_deploy=Decimal(deploy), source="initial"
    )


def _entry_day(harness: Harness, closes: list[float]) -> None:
    """Seed one symbol, fund the book and run the 依據資料日 evaluation."""
    harness.store.ensure_batches(["2330"], batches_per_target=3)
    _seed(harness, "2330", closes)
    _fund(harness)
    evaluation = harness.service.evaluate_today(today=TUESDAY)
    assert [item.rule_id for item in evaluation.directives] == ["R1"]


# --- the wiring itself ------------------------------------------------------


def test_a_filled_entry_reaches_the_book_and_moves_the_cash(harness: Harness) -> None:
    _entry_day(harness, [100.0] * HISTORY)

    result = harness.service.settle_pending(today=WEDNESDAY)

    assert result.executed == 1 and result.missed == 0
    batch = harness.store.get_batch("2330", 1)
    assert batch is not None
    assert batch.status == "open"
    assert batch.remaining_shares == 666
    assert batch.cost == Decimal("100")
    assert batch.entry_date == WEDNESDAY
    # 666 x 100 left the cash pool; 鐵律① now reads a balance that advanced.
    assert harness.store.portfolio_state().cash == Decimal("933400")


def test_an_open_outside_the_band_is_missed_and_moves_nothing(harness: Harness) -> None:
    """T9 through the wired path: 開盤 110 > 參考價 100 ×1.02."""
    _entry_day(harness, _flat_with(WEDNESDAY, 110.0))

    result = harness.service.settle_pending(today=WEDNESDAY)

    assert result.missed == 1 and result.executed == 0
    batch = harness.store.get_batch("2330", 1)
    assert batch is not None
    assert batch.status == "planned"
    assert batch.remaining_shares == 0
    assert batch.missed_count == 1
    assert harness.store.portfolio_state().cash == Decimal("1000000")


def test_settling_twice_does_not_deduct_twice(harness: Harness) -> None:
    """防重放：the second run settles nothing and the book is untouched."""
    _entry_day(harness, [100.0] * HISTORY)
    first = harness.service.settle_pending(today=WEDNESDAY)
    cash_after_first = harness.store.portfolio_state().cash

    second = harness.service.settle_pending(today=WEDNESDAY)

    assert first.executed == 1
    assert second.settled == []
    assert harness.store.portfolio_state().cash == cash_after_first
    assert harness.store.get_batch("2330", 1).remaining_shares == 666  # type: ignore[union-attr]


def test_a_settled_line_is_flagged_in_the_log_with_its_open_price(
    harness: Harness,
) -> None:
    """風控 R16: the log says what happened, when, and at which price."""
    _entry_day(harness, [100.0] * HISTORY)
    harness.service.settle_pending(today=WEDNESDAY)

    (row,) = [item for item in harness.store.directive_log() if item["rule_id"] == "R1"]
    assert row["settled"] == 1
    assert row["status"] == "executed"
    assert Decimal(row["settled_open_price"]) == Decimal("100")
    assert row["settled_at"]
    assert harness.store.pending_directives() == []


def test_a_line_with_no_opening_price_is_named_not_guessed(harness: Harness) -> None:
    """風控 R5: 無開盤價的標的誠實列出未結算，帳本不動."""
    _entry_day(harness, [100.0] * HISTORY)
    # Settle "on" the 依據資料日 itself: the 預定執行日 has no bar yet.
    result = harness.service.settle_pending(today=TUESDAY)

    assert result.settled == []
    assert result.unsettled == []  # not due at all, so not even listed
    assert harness.store.get_batch("2330", 1).status == "planned"  # type: ignore[union-attr]

    # A line that *is* due but whose symbol produced no bar is listed with its
    # status and source, and stays pending for the next run.
    harness.prices.bars.pop("2330")
    due = harness.service.settle_pending(today=WEDNESDAY)
    assert due.settled == []
    assert len(due.unsettled) == 1
    assert "尚無日線開盤價" in due.unsettled[0].reason
    assert len(harness.store.pending_directives()) == 1


def test_today_settles_yesterday_before_it_evaluates(harness: Harness) -> None:
    """The ``/today`` path is the wiring: one call, book first, table after."""
    _entry_day(harness, [100.0] * HISTORY)

    evaluation = harness.service.evaluate_today(today=WEDNESDAY)

    assert evaluation.settlement is not None
    assert evaluation.settlement.executed == 1
    # The snapshot is computed after settlement, so it already shows the fill.
    (row,) = [item for item in evaluation.snapshot if item.batch_no == 1]
    assert row.status == "open"
    assert row.remaining_shares == 666
    # Idempotent: a second call settles nothing new.
    again = harness.service.evaluate_today(today=WEDNESDAY)
    assert again.settlement is not None
    assert again.settlement.settled == []


def test_emergency_exit_closes_the_book_once_it_settles(harness: Harness) -> None:
    """CEO 裁決六 + T+1：出清指令結算後，帳本上的批次確實 closed."""
    harness.store.ensure_batches(["2330"], batches_per_target=3)
    _seed(harness, "2330", [100.0] * HISTORY)
    _fund(harness, cash="0")
    harness.store.save_batch(
        harness.store.get_batch("2330", 1).model_copy(  # type: ignore[union-attr]
            update={
                "status": "open",
                "entry_date": date(2026, 7, 1),
                "cost": Decimal("100"),
                "shares": 300,
                "remaining_shares": 300,
                "peak_close": Decimal("100"),
            }
        )
    )

    result = harness.service.emergency_exit(today=TUESDAY)
    assert result.total_shares == 300
    # Before settlement the shares are still on the book: a decision is not a fill.
    assert harness.store.get_batch("2330", 1).status == "open"  # type: ignore[union-attr]

    settled = harness.service.settle_pending(today=WEDNESDAY)

    assert settled.executed == 1
    batch = harness.store.get_batch("2330", 1)
    assert batch is not None
    assert batch.status == "closed"
    assert batch.remaining_shares == 0
    # 300 x 100 came back into the pool.
    assert harness.store.portfolio_state().cash == Decimal("30000")


def test_a_deferral_line_is_never_queued_for_settlement(harness: Harness) -> None:
    """順延／跳過不是委託單，沒有 T+1 結果可結算，也不該算成一次 MISSED."""
    harness.store.ensure_batches(["2330"], batches_per_target=3)
    _seed(harness, "2330", _flat_with(TUESDAY, 110.0))  # 漲幅觸發 R2 順延
    _fund(harness)
    evaluation = harness.service.evaluate_today(today=TUESDAY)
    assert [item.rule_id for item in evaluation.directives] == ["R2"]

    assert harness.store.pending_directives() == []
    result = harness.service.settle_pending(today=WEDNESDAY)
    assert result.settled == [] and result.unsettled == []
    assert harness.store.get_batch("2330", 1).missed_count == 0  # type: ignore[union-attr]


def test_the_replay_guard_is_the_claim_and_not_the_caller(harness: Harness) -> None:
    """A second claim on the same log row fails, whoever asks."""
    _entry_day(harness, [100.0] * HISTORY)
    (pending,) = harness.store.pending_directives()

    first = harness.store.claim_directive(
        pending.directive_id, status="executed", open_price=Decimal("100")
    )
    second = harness.store.claim_directive(
        pending.directive_id, status="executed", open_price=Decimal("100")
    )

    assert first is True
    assert second is False


# --- E-2 MISSED 重試上限對齊 R3 ---------------------------------------------


def test_three_missed_entries_skip_the_batch(harness: Harness) -> None:
    """CEO 裁決 E-2: MISSED 累計 3 次比照 R3 跳過本批."""
    harness.store.ensure_batches(["2330"], batches_per_target=3)
    _seed(harness, "2330", [100.0] * HISTORY)
    _fund(harness)
    batch = harness.store.get_batch("2330", 1)
    assert batch is not None
    harness.store.save_batch(batch.model_copy(update={"missed_count": 3}))

    evaluation = harness.service.evaluate_today(today=TUESDAY)

    (directive,) = evaluation.directives
    assert directive.rule_id == "R3"
    assert directive.action == "skip"
    assert "MISSED" in directive.rule_summary
    assert "batch_skipped" in [effect.kind for effect in evaluation.effects]
