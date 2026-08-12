"""API surface of the 排程台: today's directive table and the emergency exit.

Offline by construction: both the security ladder and the index ladder are
:class:`tests.api_helpers.FakePriceService` instances, so no request leaves the
process and no developer database is touched.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_playbook_service
from app.main import app
from app.playbook.service import PlaybookService
from app.playbook.store import PlaybookStore
from tests.api_helpers import FakePriceService, recent_bars
from tests.playbook_helpers import batch as make_batch

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
    assert "凍結至" in body["message"]

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
