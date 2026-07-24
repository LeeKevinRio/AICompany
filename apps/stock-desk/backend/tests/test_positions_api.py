"""API tests for position CRUD, CSV template, and CSV import (no network)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_position_store
from app.main import app
from app.positions.store import PositionStore


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    store = PositionStore(db_path=tmp_path / "positions.db")
    app.dependency_overrides[get_position_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _valid_payload() -> dict[str, object]:
    return {
        "symbol": "2330",
        "market": "TW",
        "quantity": "1000",
        "avg_cost": "600.5",
        "currency": "TWD",
        "opened_at": "2024-01-02",
        "instrument_type": "stock",
        "note": "台積電",
    }


def test_list_empty_has_items_and_as_of(client: TestClient) -> None:
    body = client.get("/api/positions").json()
    assert body["items"] == []
    assert "as_of" in body


def test_create_returns_201_and_position(client: TestClient) -> None:
    response = client.post("/api/positions", json=_valid_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["id"] >= 1
    assert body["symbol"] == "2330"
    # Decimal amounts must serialize as strings, not floats.
    assert body["quantity"] == "1000"
    assert body["avg_cost"] == "600.5"
    assert "created_at" in body and "updated_at" in body


def test_created_position_appears_in_list(client: TestClient) -> None:
    client.post("/api/positions", json=_valid_payload())
    items = client.get("/api/positions").json()["items"]
    assert len(items) == 1
    assert items[0]["symbol"] == "2330"


def test_create_invalid_quantity_returns_422_with_field(client: TestClient) -> None:
    payload = _valid_payload()
    payload["quantity"] = "0"
    response = client.post("/api/positions", json=payload)
    assert response.status_code == 422
    locs = [tuple(err["loc"]) for err in response.json()["detail"]]
    assert ("body", "quantity") in locs


def test_create_invalid_enum_returns_422(client: TestClient) -> None:
    payload = _valid_payload()
    payload["market"] = "JP"
    response = client.post("/api/positions", json=payload)
    assert response.status_code == 422
    locs = [tuple(err["loc"]) for err in response.json()["detail"]]
    assert ("body", "market") in locs


def test_create_future_opened_at_returns_422(client: TestClient) -> None:
    payload = _valid_payload()
    payload["opened_at"] = "2999-01-01"
    response = client.post("/api/positions", json=payload)
    assert response.status_code == 422
    locs = [tuple(err["loc"]) for err in response.json()["detail"]]
    assert ("body", "opened_at") in locs


def test_update_existing_position(client: TestClient) -> None:
    created = client.post("/api/positions", json=_valid_payload()).json()
    payload = _valid_payload()
    payload["quantity"] = "2000"
    response = client.put(f"/api/positions/{created['id']}", json=payload)
    assert response.status_code == 200
    assert response.json()["quantity"] == "2000"


def test_update_missing_position_returns_404(client: TestClient) -> None:
    response = client.put("/api/positions/9999", json=_valid_payload())
    assert response.status_code == 404


def test_delete_existing_then_missing(client: TestClient) -> None:
    created = client.post("/api/positions", json=_valid_payload()).json()
    assert client.delete(f"/api/positions/{created['id']}").status_code == 204
    assert client.delete(f"/api/positions/{created['id']}").status_code == 404


def test_template_csv_download_headers_and_body(client: TestClient) -> None:
    response = client.get("/api/positions/template.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("symbol,market,quantity")
    assert len(lines) == 3  # header + two example rows


def test_import_valid_and_invalid_rows(client: TestClient) -> None:
    csv_text = (
        "symbol,market,quantity,avg_cost,currency,opened_at,instrument_type,note\n"
        "2330,TW,1000,600.5,TWD,2024-01-02,stock,台積電\n"  # row 2: valid
        "AAPL,US,-5,180,USD,2024-03-15,stock,bad qty\n"  # row 3: quantity <= 0
        "0050,TW,500,50,JPY,2024-02-01,etf,bad currency\n"  # row 4: currency enum
        "AAPL,US,10,180,USD,2999-01-01,stock,future date\n"  # row 5: future date
    )
    response = client.post(
        "/api/positions/import",
        files={"file": ("positions.csv", csv_text, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    error_rows = {(err["row"], err["field"]) for err in body["errors"]}
    assert (3, "quantity") in error_rows
    assert (4, "currency") in error_rows
    assert (5, "opened_at") in error_rows
    # The one good row was still stored despite the bad rows around it.
    assert len(client.get("/api/positions").json()["items"]) == 1


def test_import_reports_chinese_reasons(client: TestClient) -> None:
    csv_text = (
        "symbol,market,quantity,avg_cost,currency,opened_at,instrument_type,note\n"
        "2330,TW,0,600,TWD,2024-01-02,stock,\n"
    )
    body = client.post(
        "/api/positions/import",
        files={"file": ("positions.csv", csv_text, "text/csv")},
    ).json()
    assert body["imported"] == 0
    reasons = [err["reason"] for err in body["errors"]]
    assert any("大於 0" in reason for reason in reasons)


def test_import_missing_header_column_is_rejected(client: TestClient) -> None:
    csv_text = "symbol,market,quantity\n2330,TW,1000\n"
    body = client.post(
        "/api/positions/import",
        files={"file": ("positions.csv", csv_text, "text/csv")},
    ).json()
    assert body["imported"] == 0
    assert body["errors"][0]["field"] == "header"
