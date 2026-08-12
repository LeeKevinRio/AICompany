"""API surface of the 排程台: today's directive table and the emergency exit.

Offline by construction: both the security ladder and the index ladder are
:class:`tests.api_helpers.FakePriceService` instances, so no request leaves the
process and no developer database is touched.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_playbook_service
from app.main import app
from app.playbook.models import Directive, FastMarketState, PlaybookEvaluation
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import FakePriceService, recent_bars
from tests.playbook_helpers import batch as make_batch
from tests.playbook_helpers import confirm_rule_set

#: Enough history for MA25, the 20-day monthly line and the 20-day volatility.
HISTORY = 40


@dataclass
class PlaybookHarness:
    client: TestClient
    store: PlaybookStore
    prices: FakePriceService
    index: FakePriceService


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[PlaybookHarness]:
    store = PlaybookStore(db_path=tmp_path / "playbook.db")
    # 風控 R2: the rules have to be the user's own before a line may be produced.
    confirm_rule_set(store)
    prices = FakePriceService()
    index = FakePriceService()
    index.seed("^TWII", recent_bars([20000.0] * HISTORY, symbol="^TWII"))
    service = PlaybookService(
        store=store,
        market_resolver={"TW": prices},
        index_resolver={"TW": index, "US": index},
    )
    app.dependency_overrides[get_playbook_service] = lambda: service
    with TestClient(app) as client:
        yield PlaybookHarness(client=client, store=store, prices=prices, index=index)
    app.dependency_overrides.clear()


def _seed_symbol(harness: PlaybookHarness, symbol: str, closes: list[float]) -> None:
    harness.prices.seed(symbol, recent_bars(closes, symbol=symbol))


def test_today_returns_an_empty_table_when_nothing_is_held(
    harness: PlaybookHarness,
) -> None:
    response = harness.client.get("/api/playbook/today")
    assert response.status_code == 200
    body = response.json()
    assert body["directives"] == []
    assert body["snapshot"] == []
    assert body["mode"] in {"normal", "defense"}
    assert body["as_of"]


def test_today_reports_the_stop_loss_line_with_its_provenance(
    harness: PlaybookHarness,
) -> None:
    harness.store.ensure_batches(["2330"], batches_per_target=3)
    harness.store.save_batch(make_batch(cost="100", shares=300))
    _seed_symbol(harness, "2330", [100.0] * (HISTORY - 1) + [85.0])

    body = harness.client.get("/api/playbook/today").json()
    rules = [item["directive"]["rule_id"] for item in body["directives"]]
    assert "S1" in rules
    line = next(item for item in body["directives"] if item["directive"]["rule_id"] == "S1")
    assert "依據資料日" in line["line"]
    assert "預定執行日" in line["line"]
    assert line["directive"]["limit_low"] is None  # 停損不設滑價帶
    assert body["snapshot"][0]["symbol"] == "2330"
    assert body["rules_version"] == 1


def test_today_states_the_data_gap_instead_of_issuing_a_line(
    harness: PlaybookHarness,
) -> None:
    """鐵律⑤: a symbol with no bars produces a warning, never a directive."""
    harness.store.ensure_batches(["2330"], batches_per_target=3)
    harness.store.save_batch(make_batch(cost="100", shares=300))

    body = harness.client.get("/api/playbook/today").json()
    assert body["directives"] == []
    assert any("2330" in warning for warning in body["warnings"])


def test_emergency_exit_liquidates_everything_and_freezes_the_schedule(
    harness: PlaybookHarness,
) -> None:
    harness.store.ensure_batches(["2330", "2454"], batches_per_target=3)
    harness.store.save_batch(make_batch("2330", cost="100", shares=300))
    harness.store.save_batch(make_batch("2454", cost="50", shares=200))
    _seed_symbol(harness, "2330", [100.0] * HISTORY)
    _seed_symbol(harness, "2454", [50.0] * HISTORY)

    body = harness.client.post("/api/playbook/emergency-exit").json()
    assert body["total_shares"] == 500
    assert len(body["directives"]) == 2
    assert all(item["directive"]["action"] == "sell" for item in body["directives"])
    assert all(item["directive"]["limit_low"] is None for item in body["directives"])
    # 覆審定稿: 已受理（不是「已執行」），且暫停範圍限 R 系列、S/P 照常評估。
    assert body["message"].startswith("EMERGENCY_EXIT 已受理：")
    assert "R 系列（新倉進場）自 " in body["message"]
    assert "S/P 系列停損停利仍照常評估。" in body["message"]
    assert "已執行" not in body["message"]
    # 歸屬語與凍結第 N 日的模式句都在回應上，且模式句不是被存起來的快照。
    assert body["attribution"]
    assert "第 1/20 交易日" in body["mode_reason"]

    # The freeze is now the portfolio's state, and the mode says so.
    assert harness.store.portfolio_state().emergency_until is not None
    after = harness.client.get("/api/playbook/today").json()
    assert after["mode"] == "emergency_frozen"
    assert "緊急出清" in after["mode_label"]


def test_emergency_exit_takes_no_body_and_works_with_nothing_held(
    harness: PlaybookHarness,
) -> None:
    """風控 R11: the escape hatch is always reachable, even with an empty book."""
    body = harness.client.post("/api/playbook/emergency-exit").json()
    assert body["total_shares"] == 0
    assert body["directives"] == []
    assert "無持有批次" in body["message"]


def _weekdays_after(day: date, count: int) -> date:
    """``count`` weekdays after ``day`` -- the calendar's own forward fallback.

    Every day a freeze prediction walks is later than the last loaded bar, so
    the calendar answers from the weekday rule it documents for future dates.
    Restated here rather than imported so the expectation is an independent
    count, not the production helper checking itself.
    """
    cursor = day
    remaining = count
    while remaining:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            remaining -= 1
    return cursor


def test_today_carries_the_exit_confirmation_facts_before_any_exit_is_submitted(
    harness: PlaybookHarness,
) -> None:
    """契約缺口修補：核取句、凍結天數與預計恢復日在送出前就要拿得到."""
    body = harness.client.get("/api/playbook/today").json()

    block = body["exit_confirm"]
    assert block["freeze_days"] == 20
    assert block["freeze_until"] == _weekdays_after(date.today(), 20).isoformat()
    assert len(block["checks"]) == 4
    # 每一句都已渲染完成：留著 {placeholder} 就等於把渲染責任推回前端。
    assert not [check for check in block["checks"] if "{" in check]
    assert block["checks"][1] == (
        "送出後，R 系列（新倉進場）暫停 20 個交易日"
        f"（預計恢復日：{block['freeze_until']}，依交易日曆計算）。"
    )
    # 出口零摩擦：確認畫面上不得出現快市加註（EX-2）。
    assert not [check for check in block["checks"] if "快市" in check]


def test_the_exit_confirmation_days_follow_the_rule_parameter(
    harness: PlaybookHarness,
) -> None:
    """參數改 10 天，句中數字與預計恢復日跟著變——前端鏡射 20 天的缺口正是這個。"""
    confirm_rule_set(harness.store, emergency_freeze_trading_days=10)

    block = harness.client.get("/api/playbook/today").json()["exit_confirm"]

    assert block["freeze_days"] == 10
    assert block["freeze_until"] == _weekdays_after(date.today(), 10).isoformat()
    assert "暫停 10 個交易日" in block["checks"][1]
    assert "20 個交易日" not in block["checks"][1]


def test_the_exit_confirmation_predicts_the_freeze_the_exit_then_applies(
    harness: PlaybookHarness,
) -> None:
    """預告與實際必須是同一個計算：說 20 天就凍 20 天，說哪天恢復就哪天."""
    confirm_rule_set(harness.store, emergency_freeze_trading_days=10)
    predicted = harness.client.get("/api/playbook/today").json()["exit_confirm"]

    applied = harness.client.post("/api/playbook/emergency-exit").json()

    assert applied["freeze_until"] == predicted["freeze_until"]
    assert f"暫停 {predicted['freeze_days']} 交易日" in applied["message"]


def _log_a_pending_entry(
    harness: PlaybookHarness, *, execution_date: date, shares: int = 100
) -> None:
    """Put one due, unsettled buy line in the log.

    The endpoints run on the real clock, so a line whose 預定執行日 has already
    arrived is written directly rather than waiting a day for one.
    """
    harness.store.record_directives(
        PlaybookEvaluation(
            data_date=execution_date - timedelta(days=1),
            execution_date=execution_date,
            mode="normal",
            mode_reason="正常模式",
            is_schedule_day=True,
            fast_market=FastMarketState(
                active=False, annualized_vol_20d=None, large_move_days=0, reason=None
            ),
            rules_version=1,
            directives=[
                Directive(
                    symbol="2330",
                    batch_no=1,
                    action="buy",
                    shares=shares,
                    rule_id="R1",
                    rule_summary="R1 排程日進場",
                    data_date=execution_date - timedelta(days=1),
                    execution_date=execution_date,
                    reference_price=Decimal("100"),
                    limit_low=Decimal("98"),
                    limit_high=Decimal("102"),
                    limit_note="限價帶",
                    data_status="fresh",
                    source="fake",
                )
            ],
            effects=[],
            warnings=[],
            snapshot=[],
        )
    )


def test_settle_moves_the_book_and_refuses_to_do_it_twice(
    harness: PlaybookHarness,
) -> None:
    """BLOCKING 修復：結算有生產呼叫點，且重放不重複扣減."""
    harness.store.ensure_batches(["2330"], batches_per_target=3)
    harness.store.set_capital(
        cash=Decimal("1000000"), total_deploy=Decimal("0"), source="test"
    )
    _seed_symbol(harness, "2330", [100.0] * HISTORY)
    _log_a_pending_entry(harness, execution_date=date.today() - timedelta(days=1))

    body = harness.client.post("/api/playbook/settle").json()
    assert body["executed"] == 1
    assert body["missed"] == 0
    assert body["settled"][0]["open_price"] == "100.0"
    batch = harness.store.get_batch("2330", 1)
    assert batch is not None and batch.status == "open" and batch.remaining_shares == 100
    cash_after = harness.store.portfolio_state().cash

    again = harness.client.post("/api/playbook/settle").json()
    assert again["settled"] == []
    assert harness.store.get_batch("2330", 1).remaining_shares == 100  # type: ignore[union-attr]
    assert harness.store.portfolio_state().cash == cash_after


def test_settle_lists_a_line_it_could_not_price_instead_of_dropping_it(
    harness: PlaybookHarness,
) -> None:
    """風控 R5：沒有開盤價就誠實列為未結算，維持待結算."""
    harness.store.ensure_batches(["2330"], batches_per_target=3)
    _log_a_pending_entry(harness, execution_date=date.today() - timedelta(days=1))

    body = harness.client.post("/api/playbook/settle").json()

    assert body["settled"] == []
    assert len(body["unsettled"]) == 1
    assert "尚無日線開盤價" in body["unsettled"][0]["reason"]
    assert len(harness.store.pending_directives()) == 1


def test_today_settles_the_previous_day_before_building_the_table(
    harness: PlaybookHarness,
) -> None:
    """GET /today 開頭自動結算昨日待結指令（冪等）."""
    harness.store.ensure_batches(["2330"], batches_per_target=3)
    harness.store.set_capital(
        cash=Decimal("1000000"), total_deploy=Decimal("0"), source="test"
    )
    _seed_symbol(harness, "2330", [100.0] * HISTORY)
    _log_a_pending_entry(harness, execution_date=date.today() - timedelta(days=1))

    body = harness.client.get("/api/playbook/today").json()
    assert body["settlement"]["executed"] == 1
    assert harness.store.get_batch("2330", 1).status == "open"  # type: ignore[union-attr]

    again = harness.client.get("/api/playbook/today").json()
    assert again["settlement"]["settled"] == []
    assert harness.store.get_batch("2330", 1).remaining_shares == 100  # type: ignore[union-attr]


def test_rebalance_recomputes_the_locked_capital_and_states_an_overshoot(
    harness: PlaybookHarness,
) -> None:
    """D-1/D-2：季末重算雙向，超額落 directives，鎖定值帶來源與時間戳."""
    harness.store.ensure_batches(["2330"], batches_per_target=3)
    _seed_symbol(harness, "2330", [100.0] * HISTORY)
    batch = harness.store.get_batch("2330", 1)
    assert batch is not None
    harness.store.save_batch(
        batch.model_copy(
            update={
                "status": "open",
                "cost": Decimal("60"),
                "shares": 1000,
                "remaining_shares": 1000,
            }
        )
    )
    harness.store.set_capital(
        cash=Decimal("10000"), total_deploy=Decimal("500000"), source="initial"
    )

    body = harness.client.post("/api/playbook/rebalance").json()

    assert body["status"] == "ok"
    assert Decimal(body["new_total_deploy"]) == Decimal("77000")
    assert Decimal(body["overshoot"]) == Decimal("23000")
    assert any("【超額】" in warning for warning in body["warnings"])
    assert body["directives"][0]["directive"]["rule_id"] == "REBALANCE"
    state = harness.store.portfolio_state()
    assert state.total_deploy_source == "quarterly_rebalance"
    assert state.total_deploy_set_at is not None


def test_the_directive_log_records_every_line_the_endpoint_returned(
    harness: PlaybookHarness,
) -> None:
    """風控 R16: 每筆指令落檔（規則版本／觸發 id／輸入數據 as_of／輸出）."""
    harness.store.ensure_batches(["2330"], batches_per_target=3)
    harness.store.save_batch(make_batch(cost="100", shares=300))
    _seed_symbol(harness, "2330", [100.0] * (HISTORY - 1) + [85.0])

    harness.client.get("/api/playbook/today")
    rows = harness.store.directive_log()
    assert rows
    assert rows[0]["rule_id"] == "S1"
    assert rows[0]["rules_version"] == 1
    assert rows[0]["data_status"] == "fresh"
    assert Decimal(rows[0]["reference_price"]) == Decimal("85")
