"""季末 REBALANCE and the capital lock (CEO 裁決一 / 風控 D-1, D-2).

D-1 asks for a two-way recomputation -- a shrinking book lowers TOTAL_DEPLOY,
not only a growing one raises it -- and for an overshoot to be stated instead of
absorbed. D-2 asks the locked value to carry a timestamp and the source that
wrote it.

D-2 as revised by CEO #68 (風控 2026-10-28 #68 裁決（D-2 修訂／N-155 揭露規格）)
no longer asks that a playbook line stay inside cap 1 of
``app/advice/limits.py``: cap 1 does not constrain the 排程台, whose share
counts come only from the rule-set parameters the user confirmed, and the
conflict is disclosed instead (N-155). The last tests here pin the per-target
size formula the disclosure states; the invariance of the lines under any cap-1
setting is pinned in ``tests/test_playbook_cap1_d2.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.playbook.engine import planned_batch_shares
from app.playbook.models import BatchState, RuleParams
from app.playbook.service import REBALANCE_SOURCE, PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import FakePriceService, recent_bars

SERIES_END = date(2026, 8, 14)
QUARTER_END = date(2026, 8, 11)
HISTORY = 40


@dataclass
class Harness:
    service: PlaybookService
    store: PlaybookStore
    prices: FakePriceService


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
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


def _hold(harness: Harness, symbol: str, *, close: float, shares: int, cost: str) -> None:
    harness.store.ensure_batches([symbol], batches_per_target=3)
    harness.prices.seed(symbol, recent_bars([close] * HISTORY, symbol=symbol, end=SERIES_END))
    batch = harness.store.get_batch(symbol, 1)
    assert batch is not None
    harness.store.save_batch(
        batch.model_copy(
            update={
                "status": "open",
                "entry_date": date(2026, 7, 1),
                "cost": Decimal(cost),
                "shares": shares,
                "remaining_shares": shares,
                "peak_close": Decimal(str(close)),
            }
        )
    )


def test_a_bigger_book_raises_the_locked_total_deploy(harness: Harness) -> None:
    _hold(harness, "2330", close=150.0, shares=1000, cost="100")
    harness.store.set_capital(
        cash=Decimal("500000"), total_deploy=Decimal("455000"), source="initial"
    )

    result = harness.service.rebalance(today=QUARTER_END)

    assert result.status == "ok"
    # 500,000 cash + 150,000 stock = 650,000; x 70% = 455,000.
    assert result.total_assets == Decimal("650000")
    assert result.new_total_deploy == Decimal("455000.00")
    assert harness.store.portfolio_state().total_deploy == Decimal("455000.00")
    assert "TOTAL_DEPLOY" in result.message


def test_a_smaller_book_lowers_it_too(harness: Harness) -> None:
    """D-1 的雙向：總資產降時必須下修，不能只升不降."""
    _hold(harness, "2330", close=50.0, shares=1000, cost="100")
    harness.store.set_capital(
        cash=Decimal("100000"), total_deploy=Decimal("700000"), source="initial"
    )

    result = harness.service.rebalance(today=QUARTER_END)

    # 100,000 cash + 50,000 stock = 150,000; x 70% = 105,000 < 700,000.
    assert result.new_total_deploy == Decimal("105000.00")
    assert result.previous_total_deploy == Decimal("700000")
    assert harness.store.portfolio_state().total_deploy == Decimal("105000.00")


def test_an_overshoot_is_warned_about_and_logged_not_absorbed(harness: Harness) -> None:
    """D-1：超額不得靜默——顯著警示並落 directives."""
    _hold(harness, "2330", close=100.0, shares=1000, cost="60")
    harness.store.set_capital(
        cash=Decimal("10000"), total_deploy=Decimal("500000"), source="initial"
    )

    result = harness.service.rebalance(today=QUARTER_END)

    # 10,000 + 100,000 = 110,000 assets; deploy = 77,000 < the 100,000 held.
    assert result.overshoot == Decimal("23000.00")
    assert any("【超額】" in warning for warning in result.warnings)
    (directive,) = result.directives
    assert directive.rule_id == "REBALANCE"
    assert directive.action == "none"  # 本規則集沒有自動減碼條款
    assert "超額" in directive.rule_summary
    logged = [row for row in harness.store.directive_log() if row["rule_id"] == "REBALANCE"]
    assert len(logged) == 1


def test_a_book_that_cannot_be_valued_blocks_the_recomputation(harness: Harness) -> None:
    """鐵律⑤：缺一檔收盤價就不重算，並指名是哪一檔."""
    _hold(harness, "2330", close=100.0, shares=1000, cost="60")
    harness.prices.bars.pop("2330")
    harness.store.set_capital(
        cash=Decimal("10000"), total_deploy=Decimal("500000"), source="initial"
    )

    result = harness.service.rebalance(today=QUARTER_END)

    assert result.status == "insufficient_data"
    assert result.new_total_deploy is None
    assert "2330" in result.message
    assert harness.store.portfolio_state().total_deploy == Decimal("500000")


def test_the_locked_value_records_when_and_from_where(harness: Harness) -> None:
    """D-2：鎖定值落檔含時間戳與輸入來源."""
    _hold(harness, "2330", close=100.0, shares=100, cost="100")
    harness.store.set_capital(
        cash=Decimal("100000"), total_deploy=Decimal("77000"), source="initial"
    )
    assert harness.store.portfolio_state().total_deploy_source == "initial"

    harness.service.rebalance(today=QUARTER_END)

    state = harness.store.portfolio_state()
    assert state.total_deploy_source == REBALANCE_SOURCE
    assert state.total_deploy_set_at is not None
    assert state.total_deploy_set_at.tzinfo is not None


@pytest.mark.parametrize(
    ("n_targets", "expected"),
    [(5, Decimal("0.14")), (7, Decimal("0.10"))],
)
def test_each_target_is_sized_at_deploy_ratio_over_n_targets_of_total_assets(
    n_targets: int, expected: Decimal
) -> None:
    """修訂 D-2 (5) 測試 ①: per-target size = deploy_ratio / n_targets, exactly.

    Revised D-2 (CEO #68, 風控 2026-10-28 #68 裁決（D-2 修訂／N-155 揭露規格）):
    with the default rule set one symbol gets TOTAL_DEPLOY / 5, which is 20% of
    the deployed capital and, TOTAL_DEPLOY being 70% of total assets, 14% of
    total assets (cash included). Cap 1 measures something else -- the
    holding's share of the valued book, cash excluded -- and does not constrain
    these lines; that is disclosed rather than enforced, so this test pins the
    formula with ``==`` and compares it with no cap. ``n_targets=7`` lands
    exactly on 10%, the cap-1 default, to pin that boundary case as well.

    Run on the real sizing function, with a total and a close that divide
    exactly, so the equality is the formula's and not a rounding accident.
    """
    params = RuleParams(effective_date=date(2026, 1, 1), n_targets=n_targets)
    total_assets = Decimal("2100000")
    total_deploy = total_assets * params.deploy_ratio
    close = Decimal("100")

    batches = [
        BatchState(symbol="2330", batch_no=number, status="planned")
        for number in range(1, params.batches_per_target + 1)
    ]
    shares = sum(
        planned_batch_shares(
            batch_no=batch.batch_no,
            close=close,
            symbol_batches=batches,
            total_deploy=total_deploy,
            params=params,
        )
        for batch in batches
    )

    assert Decimal(shares) * close / total_assets == params.deploy_ratio / params.n_targets
    assert params.deploy_ratio / params.n_targets == expected
    # And the whole book stays under the cash floor's mirror image.
    assert params.deploy_ratio + params.cash_floor_ratio == Decimal("1")
