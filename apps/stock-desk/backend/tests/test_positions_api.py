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


def test_create_rejects_an_index_symbol_with_422(client: TestClient) -> None:
    # ADR-0005 Q-6: ``^`` is the index namespace, which has its own series
    # service and no cost basis, no fills and no risk caps that mean anything.
    payload = _valid_payload()
    payload["symbol"] = "^GSPC"
    payload["market"] = "US"
    payload["currency"] = "USD"
    response = client.post("/api/positions", json=payload)
    assert response.status_code == 422
    errors = [err for err in response.json()["detail"] if tuple(err["loc"]) == ("body", "symbol")]
    assert errors, response.json()
    # The message has to say why, in a sentence that can be shown as-is.
    assert "指數代號" in errors[0]["msg"]
    assert "不可作為持倉標的" in errors[0]["msg"]
    assert client.get("/api/positions").json()["items"] == []


def test_update_rejects_an_index_symbol_with_422(client: TestClient) -> None:
    created = client.post("/api/positions", json=_valid_payload()).json()
    payload = _valid_payload()
    payload["symbol"] = "^TWII"
    response = client.put(f"/api/positions/{created['id']}", json=payload)
    assert response.status_code == 422
    # The stored position is untouched by the rejected write.
    assert client.get("/api/positions").json()["items"][0]["symbol"] == "2330"


def test_ordinary_symbols_are_unaffected_by_the_index_rule(client: TestClient) -> None:
    # Only a leading ``^`` is refused: the punctuation US tickers legitimately
    # carry, and TW numeric codes, must still go through untouched.
    for symbol in ("2330", "BRK.B", "BF-B", "0050"):
        payload = _valid_payload()
        payload["symbol"] = symbol
        assert client.post("/api/positions", json=payload).status_code == 201
    stored = [item["symbol"] for item in client.get("/api/positions").json()["items"]]
    assert stored == ["2330", "BRK.B", "BF-B", "0050"]


def test_import_rejects_an_index_row_without_failing_the_whole_file(
    client: TestClient,
) -> None:
    # The importer builds ``PositionInput`` only after its own field checks
    # pass, so the ``^`` guard has to exist on that path too -- otherwise this
    # request is a 500 rather than a row error.
    csv_text = (
        "symbol,market,quantity,avg_cost,currency,opened_at,instrument_type,note\n"
        "^GSPC,US,10,4000,USD,2024-03-15,etf,index\n"  # row 2: index symbol
        "AAPL,US,10,180,USD,2024-03-15,stock,ok\n"  # row 3: valid
    )
    response = client.post(
        "/api/positions/import",
        files={"file": ("positions.csv", csv_text, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    errors = [err for err in body["errors"] if err["row"] == 2]
    assert [err["field"] for err in errors] == ["symbol"]
    assert "指數代號" in errors[0]["reason"]
    assert [item["symbol"] for item in client.get("/api/positions").json()["items"]] == ["AAPL"]


def test_create_without_opened_at_returns_201_with_null(client: TestClient) -> None:
    payload = _valid_payload()
    del payload["opened_at"]
    response = client.post("/api/positions", json=payload)
    assert response.status_code == 201
    assert response.json()["opened_at"] is None
    # It survives the round trip through SQLite as a null, not a placeholder.
    assert client.get("/api/positions").json()["items"][0]["opened_at"] is None


def test_create_with_explicit_null_opened_at_returns_201(client: TestClient) -> None:
    payload = _valid_payload()
    payload["opened_at"] = None
    response = client.post("/api/positions", json=payload)
    assert response.status_code == 201
    assert response.json()["opened_at"] is None


def test_update_can_clear_opened_at(client: TestClient) -> None:
    created = client.post("/api/positions", json=_valid_payload()).json()
    payload = _valid_payload()
    payload["opened_at"] = None
    response = client.put(f"/api/positions/{created['id']}", json=payload)
    assert response.status_code == 200
    assert response.json()["opened_at"] is None


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


def test_import_accepts_blank_opened_at(client: TestClient) -> None:
    csv_text = (
        "symbol,market,quantity,avg_cost,currency,opened_at,instrument_type,note\n"
        "2330,TW,1000,600.5,TWD,,stock,沒填建倉日\n"  # row 2: blank open date
        "0050,TW,500,50,TWD,   ,etf,只有空白\n"  # row 3: whitespace only
    )
    response = client.post(
        "/api/positions/import",
        files={"file": ("positions.csv", csv_text, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 2
    assert body["errors"] == []
    items = client.get("/api/positions").json()["items"]
    assert [item["opened_at"] for item in items] == [None, None]


def test_import_still_rejects_malformed_and_future_opened_at(client: TestClient) -> None:
    csv_text = (
        "symbol,market,quantity,avg_cost,currency,opened_at,instrument_type,note\n"
        "2330,TW,1000,600.5,TWD,2024/01/02,stock,bad format\n"  # row 2
        "0050,TW,500,50,TWD,2999-01-01,etf,future\n"  # row 3
    )
    body = client.post(
        "/api/positions/import",
        files={"file": ("positions.csv", csv_text, "text/csv")},
    ).json()
    assert body["imported"] == 0
    reasons = {err["row"]: err["reason"] for err in body["errors"]}
    assert "YYYY-MM-DD" in reasons[2]
    assert reasons[3] == "建倉日期不可晚於今天"


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


# --- FR-12 sector -------------------------------------------------------------


def test_sectors_endpoint_lists_the_closed_twse_taxonomy(client: TestClient) -> None:
    body = client.get("/api/positions/sectors").json()
    assert body["taxonomy"] == "TWSE"
    assert body["markets"] == ["TW"]
    assert "半導體業" in body["items"]
    assert len(body["items"]) == len(set(body["items"]))  # no duplicate buckets


def test_create_with_a_listed_sector_returns_201_and_echoes_it(client: TestClient) -> None:
    payload = _valid_payload() | {"sector": "半導體業"}
    response = client.post("/api/positions", json=payload)
    assert response.status_code == 201
    assert response.json()["sector"] == "半導體業"
    assert client.get("/api/positions").json()["items"][0]["sector"] == "半導體業"


def test_create_without_a_sector_returns_201_with_null(client: TestClient) -> None:
    # AC-12.3: the field is optional and an unstated value stays unstated.
    response = client.post("/api/positions", json=_valid_payload())
    assert response.status_code == 201
    assert response.json()["sector"] is None


def test_create_with_free_text_sector_returns_422(client: TestClient) -> None:
    # AC-12.1: anything outside the list is refused rather than becoming a
    # bucket of its own.
    response = client.post("/api/positions", json=_valid_payload() | {"sector": "我的產業"})
    assert response.status_code == 422
    assert "產業別" in response.text
    assert client.get("/api/positions").json()["items"] == []


def test_us_position_cannot_carry_a_twse_sector(client: TestClient) -> None:
    # AC-12.6: the TW taxonomy is not applied to a US holding.
    us = _valid_payload() | {
        "symbol": "AAPL",
        "market": "US",
        "currency": "USD",
        "sector": "半導體業",
    }
    response = client.post("/api/positions", json=us)
    assert response.status_code == 422
    assert "美股" in response.text
    del us["sector"]
    assert client.post("/api/positions", json=us).status_code == 201


def test_update_can_set_and_clear_the_sector(client: TestClient) -> None:
    created = client.post("/api/positions", json=_valid_payload()).json()
    filled = client.put(
        f"/api/positions/{created['id']}", json=_valid_payload() | {"sector": "食品工業"}
    ).json()
    assert filled["sector"] == "食品工業"
    cleared = client.put(f"/api/positions/{created['id']}", json=_valid_payload()).json()
    assert cleared["sector"] is None


def test_template_csv_carries_the_sector_column_and_leaves_it_blank_for_us(
    client: TestClient,
) -> None:
    lines = client.get("/api/positions/template.csv").text.strip().splitlines()
    assert "sector" in lines[0].split(",")
    sector_index = lines[0].split(",").index("sector")
    assert lines[1].split(",")[sector_index] == "半導體業"
    assert lines[2].split(",")[sector_index] == ""  # the US example row


def test_import_accepts_a_listed_sector_and_rejects_only_the_bad_rows(
    client: TestClient,
) -> None:
    # AC-12.2: per-row validation, with the good rows still imported.
    csv_text = (
        "symbol,market,quantity,avg_cost,currency,opened_at,instrument_type,sector,note\n"
        "2330,TW,1000,600.5,TWD,2024-01-02,stock,半導體業,台積電\n"  # row 2: valid
        "2317,TW,500,100,TWD,2024-01-02,stock,,沒填產業\n"  # row 3: blank is fine
        "1101,TW,500,40,TWD,2024-01-02,stock,我的產業,自創\n"  # row 4: not on the list
        "AAPL,US,10,180,USD,2024-03-15,stock,半導體業,美股不適用\n"  # row 5: US
    )
    body = client.post(
        "/api/positions/import",
        files={"file": ("positions.csv", csv_text, "text/csv")},
    ).json()
    assert body["imported"] == 2
    errors = {err["row"]: err for err in body["errors"]}
    assert errors[4]["field"] == "sector" and "清單" in errors[4]["reason"]
    assert errors[5]["field"] == "sector" and "美股" in errors[5]["reason"]
    stored = client.get("/api/positions").json()["items"]
    assert [item["sector"] for item in stored] == ["半導體業", None]


def test_import_without_the_sector_column_still_works(client: TestClient) -> None:
    # Files built against the pre-FR-12 template stay importable; every row
    # simply has no sector stated.
    csv_text = (
        "symbol,market,quantity,avg_cost,currency,opened_at,instrument_type,note\n"
        "2330,TW,1000,600.5,TWD,2024-01-02,stock,舊版範本\n"
    )
    body = client.post(
        "/api/positions/import",
        files={"file": ("positions.csv", csv_text, "text/csv")},
    ).json()
    assert body["imported"] == 1
    assert body["errors"] == []
    assert client.get("/api/positions").json()["items"][0]["sector"] is None
