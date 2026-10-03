"""Market/currency agreement on every write door except ``PATCH`` (no network).

``POST`` / ``PUT`` validate through ``PositionWriteInput`` and the CSV importer
restates the same rule, all with one sentence; ``PositionInput`` / ``Position``
carry no such rule so stored rows stay readable (tech-architect C3). Also pins
qa B2 for positions: a 422 ``msg`` is the sentence alone, with no
``"Value error, "`` prefix.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_position_store
from app.main import app
from app.positions.csv_io import RowError, parse_import_csv
from app.positions.models import (
    AVG_COST_NOT_POSITIVE_MESSAGE,
    AVG_COST_REQUIRED_MESSAGE,
    CURRENCY_MARKET_MISMATCH_MESSAGE,
    INDEX_SYMBOL_REJECTED_MESSAGE,
    MARKET_CURRENCY,
    QUANTITY_NOT_POSITIVE_MESSAGE,
    QUANTITY_REQUIRED_MESSAGE,
)
from app.positions.sectors import SECTOR_REJECTED_MESSAGE, SECTOR_US_REJECTED_MESSAGE
from app.positions.store import PositionStore
from tests.api_helpers import position_payload

_HEADER = "symbol,market,quantity,avg_cost,currency,opened_at,instrument_type,sector,note"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    store = PositionStore(db_path=tmp_path / "positions.db")
    app.dependency_overrides[get_position_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _payload(market: str, currency: str) -> dict[str, object]:
    symbol = "2330" if market == "TW" else "AAPL"
    return position_payload(symbol=symbol, market=market, currency=currency)


def _errors(response: Any) -> list[tuple[tuple[object, ...], str]]:
    return [(tuple(err["loc"]), err["msg"]) for err in response.json()["detail"]]


def test_the_rule_table_is_tw_twd_and_us_usd() -> None:
    assert dict(MARKET_CURRENCY) == {"TW": "TWD", "US": "USD"}


@pytest.mark.parametrize(("market", "currency"), [("TW", "USD"), ("US", "TWD")])
def test_post_with_a_mismatched_currency_is_422_on_currency(
    client: TestClient, market: str, currency: str
) -> None:
    response = client.post("/api/positions", json=_payload(market, currency))

    assert response.status_code == 422
    assert _errors(response) == [(("body", "currency"), CURRENCY_MARKET_MISMATCH_MESSAGE)]
    assert client.get("/api/positions").json()["items"] == []


@pytest.mark.parametrize(("market", "currency"), [("TW", "TWD"), ("US", "USD")])
def test_post_with_a_matching_currency_is_201(
    client: TestClient, market: str, currency: str
) -> None:
    response = client.post("/api/positions", json=_payload(market, currency))
    assert response.status_code == 201, response.text
    assert (response.json()["market"], response.json()["currency"]) == (market, currency)


def test_put_to_a_mismatched_currency_is_422_and_leaves_the_row(client: TestClient) -> None:
    created = client.post("/api/positions", json=_payload("TW", "TWD")).json()

    response = client.put(f"/api/positions/{created['id']}", json=_payload("TW", "USD"))

    assert response.status_code == 422
    assert _errors(response) == [(("body", "currency"), CURRENCY_MARKET_MISMATCH_MESSAGE)]
    assert client.get("/api/positions").json()["items"] == [created]


def test_put_moving_market_and_currency_together_is_accepted(client: TestClient) -> None:
    created = client.post("/api/positions", json=_payload("TW", "TWD")).json()
    response = client.put(f"/api/positions/{created['id']}", json=_payload("US", "USD"))
    assert response.status_code == 200
    assert (response.json()["market"], response.json()["currency"]) == ("US", "USD")


#: T-16: one case per position validator. ``loc`` is ``None`` for the
#: model-level ``_sector_is_tw_only``, whose location is the body itself.
_REFUSALS: list[tuple[str, str, dict[str, object], tuple[str, ...] | None, str]] = [
    ("post", "symbol_blank", {"symbol": "  "}, ("body", "symbol"), "股票代號不可空白"),
    (
        "post",
        "symbol_index",
        {"symbol": "^TWII"},
        ("body", "symbol"),
        INDEX_SYMBOL_REJECTED_MESSAGE,
    ),
    ("post", "quantity", {"quantity": "0"}, ("body", "quantity"), QUANTITY_NOT_POSITIVE_MESSAGE),
    ("post", "avg_cost", {"avg_cost": "-1"}, ("body", "avg_cost"), AVG_COST_NOT_POSITIVE_MESSAGE),
    (
        "post",
        "opened_at_future",
        {"opened_at": "2999-01-01"},
        ("body", "opened_at"),
        "建倉日期不可晚於今天",
    ),
    ("post", "sector_closed_list", {"sector": "自訂"}, ("body", "sector"), SECTOR_REJECTED_MESSAGE),
    (
        "post",
        "sector_tw_only",
        {"symbol": "AAPL", "market": "US", "currency": "USD", "sector": "半導體業"},
        None,
        SECTOR_US_REJECTED_MESSAGE,
    ),
    (
        "post",
        "currency_market",
        {"currency": "USD"},
        ("body", "currency"),
        CURRENCY_MARKET_MISMATCH_MESSAGE,
    ),
    (
        "patch",
        "patch_quantity",
        {"quantity": "0"},
        ("body", "quantity"),
        QUANTITY_NOT_POSITIVE_MESSAGE,
    ),
    (
        "patch",
        "patch_quantity_null",
        {"quantity": None},
        ("body", "quantity"),
        QUANTITY_REQUIRED_MESSAGE,
    ),
    (
        "patch",
        "patch_avg_cost",
        {"avg_cost": "0"},
        ("body", "avg_cost"),
        AVG_COST_NOT_POSITIVE_MESSAGE,
    ),
    (
        "patch",
        "patch_avg_cost_null",
        {"avg_cost": None},
        ("body", "avg_cost"),
        AVG_COST_REQUIRED_MESSAGE,
    ),
]


@pytest.mark.parametrize(
    ("method", "overrides", "loc", "message"),
    [case[0:1] + case[2:] for case in _REFUSALS],
    ids=[case[1] for case in _REFUSALS],
)
def test_position_422_msg_is_the_constant_verbatim(
    client: TestClient,
    method: str,
    overrides: dict[str, object],
    loc: tuple[str, ...] | None,
    message: str,
) -> None:
    """qa B2 / T-16: the ``msg`` is the sentence alone, no ``Value error,`` in front."""
    if method == "post":
        response = client.post("/api/positions", json=position_payload(**overrides))
    else:
        created = client.post("/api/positions", json=position_payload()).json()
        response = client.patch(f"/api/positions/{created['id']}", json=overrides)

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert [err["msg"] for err in errors] == [message]
    assert not errors[0]["msg"].startswith("Value error")
    if loc is not None:
        assert tuple(errors[0]["loc"]) == loc


def test_message_constants_keep_their_wording() -> None:
    assert QUANTITY_NOT_POSITIVE_MESSAGE == "數量必須大於 0"
    assert AVG_COST_NOT_POSITIVE_MESSAGE == "平均成本必須大於 0"


@pytest.mark.parametrize("note", ["", "   "])
def test_post_and_put_store_a_blank_note_as_null(client: TestClient, note: str) -> None:
    """T-17 / D-8: the same normalisation ``PATCH`` and the CSV apply."""
    created = client.post("/api/positions", json=position_payload(note=note))
    assert created.status_code == 201
    assert created.json()["note"] is None

    client.patch(f"/api/positions/{created.json()['id']}", json={"note": "暫存"})
    updated = client.put(f"/api/positions/{created.json()['id']}", json=position_payload(note=note))
    assert updated.status_code == 200
    assert updated.json()["note"] is None

    assert [item["note"] for item in client.get("/api/positions").json()["items"]] == [None]


def test_csv_mismatched_rows_fail_on_currency_and_the_rest_import() -> None:
    text = "\n".join(
        [
            _HEADER,
            "2330,TW,1000,600,TWD,2024-01-02,stock,,good tw",
            "2317,TW,100,100,USD,2024-01-02,stock,,bad tw",
            "AAPL,US,10,180,USD,2024-01-02,stock,,good us",
            "MSFT,US,5,300,TWD,2024-01-02,stock,,bad us",
        ]
    )

    inputs, errors = parse_import_csv(text)

    assert [(item.symbol, item.currency) for item in inputs] == [("2330", "TWD"), ("AAPL", "USD")]
    assert errors == [
        RowError(row=3, field="currency", reason=CURRENCY_MARKET_MISMATCH_MESSAGE),
        RowError(row=5, field="currency", reason=CURRENCY_MARKET_MISMATCH_MESSAGE),
    ]


def test_csv_bad_market_is_reported_once_not_again_as_a_mismatch() -> None:
    _, errors = parse_import_csv(f"{_HEADER}\n2330,JP,1,1,TWD,,stock,,")
    assert [error.field for error in errors] == ["market"]


def test_csv_import_endpoint_keeps_good_rows_when_one_mismatches(client: TestClient) -> None:
    """T-14 / C9: a mixed file is a 200 with a row error, never a 500."""
    text = "\n".join([_HEADER, "2330,TW,1000,600,TWD,,stock,,", "2317,TW,100,100,USD,,stock,,"])
    response = client.post(
        "/api/positions/import", files={"file": ("p.csv", text.encode(), "text/csv")}
    )
    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert response.json()["errors"] == [
        {"row": 3, "field": "currency", "reason": CURRENCY_MARKET_MISMATCH_MESSAGE}
    ]
