"""S-1 出口矩陣：四種狀態 × 三條出口，全部必須活著.

T7 proved one cell of this table (S1 on day 4 of an S3 freeze). 風控 S-1 asks for
the whole matrix, because 「凍結中不動作」 is the failure mode that would show up
in exactly the cells nobody wrote a test for:

============== =========== =========== ==============
狀態＼出口     S 系列停損  P 系列停利  EMERGENCY_EXIT
============== =========== =========== ==============
全凍結 (S3)    活躍        活躍        可執行
緊急出清後凍結 活躍        活躍        可執行
防守 (M1)      活躍        活躍        可執行
黑名單 (S2)    活躍        活躍        可執行
============== =========== =========== ==============

S-3 is the last row: a blacklist only closes the door on *buying*. The shares
that are still held keep every stop-loss and take-profit they had, which is the
whole reason a blacklisted symbol is not simply forgotten.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.playbook.models import (
    IndexSnapshot,
    PlaybookEvaluation,
    PortfolioState,
    SymbolState,
)
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests import playbook_helpers as helper
from tests.api_helpers import FakePriceService, recent_bars
from tests.playbook_helpers import TUESDAY

SERIES_END = date(2026, 8, 14)
HISTORY = 40
FREEZE_UNTIL = date(2026, 8, 19)

#: The four states an exit has to survive, as (portfolio, symbols, index).
STATES = ("frozen", "emergency_frozen", "defense", "blacklisted")


def _state(
    name: str,
) -> tuple[PortfolioState, dict[str, SymbolState], IndexSnapshot]:
    index = helper.index()
    portfolio = helper.portfolio()
    symbols: dict[str, SymbolState] = {}
    if name == "frozen":
        portfolio = helper.portfolio(freeze_until=FREEZE_UNTIL, freeze_reason="S3 組合熔斷")
    elif name == "emergency_frozen":
        portfolio = helper.portfolio(emergency_until=FREEZE_UNTIL)
    elif name == "defense":
        portfolio = helper.portfolio(defense_active=True)
        index = helper.index(close="18000", monthly_line="19000", days_below=3)
    elif name == "blacklisted":
        symbols = {
            "2330": SymbolState(
                symbol="2330", blacklisted=True, blacklist_until=FREEZE_UNTIL
            )
        }
    return portfolio, symbols, index


def _run(name: str, *, close: str, **batch_kwargs: object) -> PlaybookEvaluation:
    from app.playbook.engine import evaluate

    portfolio, symbols, index = _state(name)
    return evaluate(
        data_date=TUESDAY,
        calendar=helper.calendar(),
        params=helper.params(),
        index=index,
        markets={"2330": helper.market(close=close, ma25="100", bias25="5")},
        batches=[helper.batch(cost="100", shares=300, **batch_kwargs)],  # type: ignore[arg-type]
        symbols=symbols,
        portfolio=portfolio,
    )


@pytest.mark.parametrize("state", STATES)
def test_the_stop_loss_fires_in_every_state(state: str) -> None:
    evaluation = _run(state, close="89")
    sells = [item for item in evaluation.directives if item.rule_id == "S1"]
    assert sells, f"{state}：S1 停損被吞掉了"
    assert sells[0].action == "sell"
    assert sells[0].shares == 300
    assert sells[0].limit_low is None  # 停損不設滑價帶


@pytest.mark.parametrize("state", STATES)
def test_the_take_profit_fires_in_every_state(state: str) -> None:
    evaluation = _run(state, close="121")
    profits = [item for item in evaluation.directives if item.rule_id == "P1"]
    assert profits, f"{state}：P1 停利被吞掉了"
    assert profits[0].action == "sell"
    assert profits[0].shares == 100


@pytest.mark.parametrize("state", STATES)
def test_the_whole_symbol_stop_fires_in_every_state(state: str) -> None:
    """S2 是 S 系列裡唯一的整檔出口，同樣不受狀態影響."""
    evaluation = _run(state, close="84")
    stops = [item for item in evaluation.directives if item.rule_id == "S2"]
    assert stops, f"{state}：S2 整檔停損被吞掉了"
    assert stops[0].batch_no is None


# --- EMERGENCY_EXIT 欄：需要 service，因為出口是端點不是規則 ------------------


@dataclass
class Harness:
    service: PlaybookService
    store: PlaybookStore


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    prices = FakePriceService()
    prices.seed("2330", recent_bars([100.0] * HISTORY, symbol="2330", end=SERIES_END))
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII", end=SERIES_END))
    store.ensure_batches(["2330"], batches_per_target=3)
    batch = store.get_batch("2330", 1)
    assert batch is not None
    store.save_batch(
        batch.model_copy(
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
    yield Harness(
        service=PlaybookService(
            store=store,
            market_resolver={"TW": prices},
            index_resolver={"TW": index, "US": index},
        ),
        store=store,
    )


def _apply_state(store: PlaybookStore, name: str) -> None:
    if name == "frozen":
        store.freeze(until=FREEZE_UNTIL, reason="S3 組合熔斷")
    elif name == "emergency_frozen":
        store.freeze_emergency(until=FREEZE_UNTIL)
    elif name == "defense":
        store.set_defense(active=True, since=date(2026, 8, 5))
    elif name == "blacklisted":
        store.blacklist("2330", triggered_on=date(2026, 8, 5), until=FREEZE_UNTIL, rule_id="S2")


@pytest.mark.parametrize("state", STATES)
def test_the_emergency_exit_is_reachable_in_every_state(
    harness: Harness, state: str
) -> None:
    """EX-2/EX-4：緊急出口與鐵律④切割，任何狀態下都不得有等待期或前置條件."""
    _apply_state(harness.store, state)

    result = harness.service.emergency_exit(today=TUESDAY)

    assert result.total_shares == 300, f"{state}：EMERGENCY_EXIT 沒有出清"
    (directive,) = result.directives
    assert directive.action == "sell"
    assert directive.limit_low is None
    assert result.freeze_until > TUESDAY


# --- S-3 黑名單只封買進 -------------------------------------------------------


def test_a_blacklisted_symbol_still_gets_no_entry_but_keeps_its_exits() -> None:
    """S-3：黑名單只封買進，殘留持倉的 S／P 仍然活躍."""
    from app.playbook.engine import evaluate

    portfolio, symbols, index = _state("blacklisted")
    evaluation = evaluate(
        data_date=TUESDAY,
        calendar=helper.calendar(),
        params=helper.params(),
        index=index,
        markets={"2330": helper.market(close="121", ma25="100", bias25="5")},
        batches=[
            helper.batch(cost="100", shares=300),
            helper.planned(batch_no=2),
        ],
        symbols=symbols,
        portfolio=portfolio,
    )
    rules = [item.rule_id for item in evaluation.directives]
    assert rules == ["P1"]
    assert "R1" not in rules
    assert all(item.action != "buy" for item in evaluation.directives)
