"""Evidence runs for the "A8 + sell-created cash key -> 1-share R1 buy" inference.

State A8: the rule set is confirmed (``confirm_rule_set`` committed) but
``total_deploy`` was never written (``set_capital`` never ran). A reading of the
code predicted that a settled sell would create the cash key, and that the next
evaluation would then size an R1 buy from ``total_deploy = "0"``, giving 1 share.
Nobody had run it; these tests run it and assert what actually happens.

Entry points used (all production): ``PlaybookStore.confirm_rule_set``,
``ensure_batches``, ``set_capital`` (control only), ``PlaybookService.evaluate_today``
and ``settle_pending``.

Directly seeded (no product path reaches it without a capital write):
the open batch ``2330#1`` via ``store.save_batch`` -- an open batch needs a prior
buy, and a buy needs cash, which A8 does not have.

Offline and dated: fake price services, explicit ``today`` on every call, and a
database under pytest's ``tmp_path``.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from app.playbook.models import PlaybookEvaluation
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import FakePriceService
from tests.playbook_helpers import confirm_rule_set
from tests.same_day_helpers import THURSDAY, TUESDAY, WEDNESDAY, bars, hold

SOLD = "2330"
TARGET = "2317"
#: Price of the held symbol on sell day and settlement day (cost 100); fires a P3 sell.
SELL_OPEN = 120.0
HELD_SHARES = 300
SOLD_SHARES = 100  # what the engine actually sells (rule P3) on the sell day


class Scene:
    def __init__(self, db_path: Path, *, sell: bool, capital: bool) -> None:
        self.db_path = db_path
        self.store = PlaybookStore(db_path=db_path)
        prices = FakePriceService()
        index = FakePriceService()
        index.seed("^TWII", bars("^TWII", 20000.0))
        # Without a sell the held symbol stays flat at its cost, so no S/P rule fires.
        drop = {TUESDAY: SELL_OPEN, WEDNESDAY: SELL_OPEN} if sell else None
        prices.seed(SOLD, bars(SOLD, 100.0, drop))
        prices.seed(TARGET, bars(TARGET, 100.0))
        self.service = PlaybookService(
            store=self.store,
            market_resolver={"TW": prices},
            index_resolver={"TW": index, "US": index},
        )
        confirm_rule_set(self.store)
        self.store.ensure_batches([SOLD, TARGET], batches_per_target=3)
        hold(self.store, SOLD, 1, shares=HELD_SHARES, cost="100")
        if capital:
            self.store.set_capital(
                cash=Decimal("1000000"), total_deploy=Decimal("1000000"), source="initial"
            )

    def state_keys(self) -> dict[str, str]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute("SELECT key, value FROM playbook_state").fetchall()
        return {str(k): str(v) for k, v in rows}

    def sell_day(self) -> PlaybookEvaluation:
        return self.service.evaluate_today(today=TUESDAY)

    def settle_sell(self) -> None:
        self.service.settle_pending(today=WEDNESDAY)

    def target_buys(self, evaluation: PlaybookEvaluation) -> list[tuple[str, str, int, int | None]]:
        return [
            (line.rule_id, line.action, line.shares, line.batch_no)
            for line in evaluation.directives
            if line.symbol == TARGET and line.action == "buy"
        ]


def test_a8_precondition_has_no_total_deploy_and_no_cash(tmp_path: Path) -> None:
    scene = Scene(tmp_path / "pb.db", sell=True, capital=False)

    keys = scene.state_keys()

    assert "rule_set_confirmed_at" in keys
    assert "total_deploy" not in keys
    assert "cash" not in keys


def test_c_a8_settled_sell_creates_cash_key(tmp_path: Path) -> None:
    scene = Scene(tmp_path / "pb.db", sell=True, capital=False)
    sell_day = scene.sell_day()
    sells = [
        (line.symbol, line.rule_id, line.shares)
        for line in sell_day.directives
        if line.action == "sell"
    ]
    assert "cash" not in scene.state_keys()

    scene.settle_sell()

    keys = scene.state_keys()
    assert sells == [(SOLD, "P3", SOLD_SHARES)]
    assert "total_deploy" not in keys
    assert "cash" in keys
    assert Decimal(keys["cash"]) == Decimal(str(SELL_OPEN)) * SOLD_SHARES


def test_a_a8_cash_from_sell_then_evaluation_commits_one_share_r1_buy(tmp_path: Path) -> None:
    scene = Scene(tmp_path / "pb.db", sell=True, capital=False)
    sell_day = scene.sell_day()
    # No cash key yet: the sell-day buys are all dropped by the cash floor.
    assert scene.target_buys(sell_day) == []
    scene.settle_sell()
    assert "total_deploy" not in scene.state_keys()

    evaluation = scene.service.evaluate_today(today=THURSDAY)

    assert scene.target_buys(evaluation) == [("R1", "buy", 1, 1)]
    # The row is committed to the log and is pending, not merely displayed.
    pending = [
        (item.directive.symbol, item.directive.batch_no, item.directive.shares)
        for item in scene.store.pending_directives()
        if item.directive.action == "buy"
    ]
    assert (TARGET, 1, 1) in pending
    assert "total_deploy" not in scene.state_keys()


def test_b_a8_without_cash_key_buys_are_all_dropped(tmp_path: Path) -> None:
    scene = Scene(tmp_path / "pb.db", sell=False, capital=False)
    assert "cash" not in scene.state_keys()

    evaluation = scene.service.evaluate_today(today=THURSDAY)

    assert [line for line in evaluation.directives if line.action == "buy"] == []
    assert scene.store.pending_directives() == []
    assert "cash" not in scene.state_keys()
    assert "total_deploy" not in scene.state_keys()


def test_d_control_with_total_deploy_r1_buy_is_sized_from_it(tmp_path: Path) -> None:
    scene = Scene(tmp_path / "pb.db", sell=True, capital=True)

    sell_day = scene.sell_day()

    # Same close (100), same symbol, same batch 1 as test (a), but total_deploy exists:
    # 1,000,000 / 5 targets / 3 batches // 100 = 666 shares (instead of 1).
    assert scene.target_buys(sell_day) == [("R1", "buy", 666, 1)]
    scene.settle_sell()
    thursday = scene.service.evaluate_today(today=THURSDAY)
    # By Thursday batch 1 is filled, so the next R1 is batch 2, also 666.
    assert scene.target_buys(thursday) == [("R1", "buy", 666, 2)]
