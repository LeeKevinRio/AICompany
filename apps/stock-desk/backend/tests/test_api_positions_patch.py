"""API tests for ``PATCH /api/positions/{id}`` (庫存頁 inline edit; no network).

The partial write sends only ``quantity`` / ``avg_cost`` / ``note``; anything
else is refused, and a row stored before the market/currency rule existed must
stay readable and editable (tech-architect C4).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.alerts.models import AlertRuleInput
from app.alerts.store import AlertStore
from app.api.deps import (
    get_dividend_store,
    get_position_store,
    get_price_bar_cache,
    get_valuator,
)
from app.data.cache import PriceBarCache
from app.dividends.store import DividendEventStore
from app.kelly.models import KellyInputRecord
from app.kelly.store import KellyInputStore
from app.main import app
from app.portfolio.valuation import PositionValuator
from app.positions.models import QUANTITY_NOT_POSITIVE_MESSAGE, QUANTITY_REQUIRED_MESSAGE
from app.positions.store import PositionStore
from tests.alerts_helpers import price_rule
from tests.api_helpers import FakePriceService, UnavailableFxProvider, position_payload


@dataclass
class Harness:
    client: TestClient
    store: PositionStore


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    store = PositionStore(db_path=tmp_path / "positions.db")
    prices = FakePriceService()
    valuator = PositionValuator(
        market_services={"TW": prices, "US": prices}, fx_provider=UnavailableFxProvider()
    )
    dividends = DividendEventStore(db_path=tmp_path / "dividends.db")
    bars = PriceBarCache(db_path=tmp_path / "bars.db")
    app.dependency_overrides[get_position_store] = lambda: store
    app.dependency_overrides[get_valuator] = lambda: valuator
    app.dependency_overrides[get_dividend_store] = lambda: dividends
    app.dependency_overrides[get_price_bar_cache] = lambda: bars
    with TestClient(app) as client:
        yield Harness(client=client, store=store)
    app.dependency_overrides.clear()


def _create(client: TestClient, **overrides: object) -> dict[str, Any]:
    response = client.post("/api/positions", json=position_payload(note="台積電", **overrides))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _stored(client: TestClient, position_id: int) -> dict[str, Any]:
    items: list[dict[str, Any]] = client.get("/api/positions").json()["items"]
    return next(item for item in items if item["id"] == position_id)


def test_patch_returns_200_and_the_list_reflects_it(harness: Harness) -> None:
    created = _create(harness.client)

    response = harness.client.patch(
        f"/api/positions/{created['id']}",
        json={"quantity": "1500", "avg_cost": "612.25", "note": "加碼"},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["quantity"], body["avg_cost"], body["note"]) == ("1500", "612.25", "加碼")
    listed = _stored(harness.client, created["id"])
    assert listed == body
    unchanged = ("symbol", "market", "currency", "opened_at", "instrument_type", "sector")
    assert {key: listed[key] for key in unchanged} == {key: created[key] for key in unchanged}
    assert listed["created_at"] == created["created_at"]


def test_patch_zero_quantity_is_422_on_quantity_with_the_exact_sentence(
    harness: Harness,
) -> None:
    created = _create(harness.client)

    response = harness.client.patch(f"/api/positions/{created['id']}", json={"quantity": "0"})

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert [(tuple(err["loc"]), err["msg"]) for err in errors] == [
        (("body", "quantity"), QUANTITY_NOT_POSITIVE_MESSAGE)
    ]
    assert QUANTITY_NOT_POSITIVE_MESSAGE == "數量必須大於 0"
    assert _stored(harness.client, created["id"]) == created


@pytest.mark.parametrize(
    ("field", "value"),
    [("market", "US"), ("sector", "半導體業"), ("currency", "USD"), ("symbol", "2317")],
)
def test_patch_with_a_field_it_does_not_own_is_422_and_changes_nothing(
    harness: Harness, field: str, value: str
) -> None:
    created = _create(harness.client)

    response = harness.client.patch(
        f"/api/positions/{created['id']}", json={"quantity": "1", field: value}
    )

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert [(tuple(err["loc"]), err["type"]) for err in errors] == [
        (("body", field), "extra_forbidden")
    ]
    assert _stored(harness.client, created["id"]) == created


@pytest.mark.parametrize(
    ("field", "message"),
    [("quantity", QUANTITY_REQUIRED_MESSAGE), ("avg_cost", "平均成本不可空白")],
)
def test_patch_null_on_a_required_field_is_422(harness: Harness, field: str, message: str) -> None:
    created = _create(harness.client)

    response = harness.client.patch(f"/api/positions/{created['id']}", json={field: None})

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert [(tuple(err["loc"]), err["msg"]) for err in errors] == [(("body", field), message)]
    assert _stored(harness.client, created["id"]) == created


def test_patch_of_a_missing_position_is_404(harness: Harness) -> None:
    response = harness.client.patch("/api/positions/9999", json={"quantity": "1"})
    assert response.status_code == 404
    assert response.json()["detail"] == "找不到指定的部位"


def test_empty_patch_returns_the_row_without_advancing_updated_at(harness: Harness) -> None:
    created = _create(harness.client)

    response = harness.client.patch(f"/api/positions/{created['id']}", json={})

    assert response.status_code == 200
    assert response.json() == created


def test_empty_patch_of_a_missing_position_is_404(harness: Harness) -> None:
    """T-5: the empty-body shortcut still reports a missing row."""
    response = harness.client.patch("/api/positions/9999", json={})
    assert response.status_code == 404
    assert response.json()["detail"] == "找不到指定的部位"


def test_delete_leaves_the_alert_rule_and_kelly_input_for_the_same_symbol(
    harness: Harness,
) -> None:
    """T-18 / C6: DELETE is a hard delete of the holding and of nothing else."""
    created = _create(harness.client)
    alerts = AlertStore(harness.store.db_path)
    kelly = KellyInputStore(harness.store.db_path)
    alerts.create_rule(AlertRuleInput.model_validate(price_rule(symbol="2330")))
    kelly.upsert(
        KellyInputRecord(
            symbol="2330", market="TW", win_rate=0.55, payoff_ratio=1.5, source="manual"
        )
    )
    rules_before = alerts.list_rules()
    kelly_before = kelly.list_all()
    assert len(rules_before) == 1 and len(kelly_before) == 1

    response = harness.client.delete(f"/api/positions/{created['id']}")

    assert response.status_code == 204
    assert harness.client.get("/api/positions").json()["items"] == []
    assert alerts.list_rules() == rules_before
    assert kelly.list_all() == kelly_before


def test_a_legacy_mismatched_row_stays_readable_and_editable(harness: Harness) -> None:
    """C4: a TW+USD row written before the rule must not turn reads into 500s."""
    with closing(sqlite3.connect(harness.store.db_path)) as conn, conn:
        cursor = conn.execute(
            """
            INSERT INTO positions
                (symbol, market, quantity, avg_cost, currency, opened_at,
                 instrument_type, sector, note, created_at, updated_at)
            VALUES ('2330', 'TW', '100', '18.5', 'USD', '2024-01-02', 'stock',
                    NULL, NULL, '2024-01-02T00:00:00+00:00', '2024-01-02T00:00:00+00:00')
            """
        )
        legacy_id = cursor.lastrowid

    patched = harness.client.patch(f"/api/positions/{legacy_id}", json={"quantity": "200"})
    assert patched.status_code == 200
    assert (patched.json()["market"], patched.json()["currency"]) == ("TW", "USD")
    assert patched.json()["quantity"] == "200"

    listed = harness.client.get("/api/positions")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [legacy_id]

    summary = harness.client.get("/api/portfolio/summary")
    assert summary.status_code == 200
    assert [item["symbol"] for item in summary.json()["positions"]] == ["2330"]
