"""API tests for the security directory endpoints (no network)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_directory_store
from app.directory.models import DirectoryEntry
from app.directory.store import SecurityDirectoryStore
from app.main import app

AS_OF = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> SecurityDirectoryStore:
    return SecurityDirectoryStore(db_path=tmp_path / "directory.db")


@pytest.fixture
def client(store: SecurityDirectoryStore) -> Iterator[TestClient]:
    app.dependency_overrides[get_directory_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _entry(symbol: str, name: str) -> DirectoryEntry:
    return DirectoryEntry(symbol=symbol, name=name, market="TW", source="twse_openapi", as_of=AS_OF)


def test_resolve_hit_returns_symbol_name_market(
    client: TestClient, store: SecurityDirectoryStore
) -> None:
    store.upsert([_entry("2330", "台積電")])

    response = client.get("/api/directory/resolve/2330")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2330"
    assert body["name"] == "台積電"
    assert body["market"] == "TW"
    assert body["source"] == "twse_openapi"
    assert "as_of" in body


def test_resolve_miss_returns_404(client: TestClient, store: SecurityDirectoryStore) -> None:
    store.upsert([_entry("2330", "台積電")])

    response = client.get("/api/directory/resolve/9999X")

    assert response.status_code == 404


def test_resolve_on_empty_directory_returns_404(client: TestClient) -> None:
    response = client.get("/api/directory/resolve/2330")
    assert response.status_code == 404


def test_search_prefix_match(client: TestClient, store: SecurityDirectoryStore) -> None:
    store.upsert([_entry("3037", "欣興"), _entry("0050", "元大台灣50"), _entry("1330", "無關公司")])

    response = client.get("/api/directory/search", params={"q": "30"})

    assert response.status_code == 200
    body = response.json()
    symbols = [item["symbol"] for item in body["items"]]
    assert "3037" in symbols
    assert "1330" not in symbols
    assert body["directory_synced"] is True


def test_search_name_substring_match(client: TestClient, store: SecurityDirectoryStore) -> None:
    store.upsert([_entry("2330", "台積電")])

    response = client.get("/api/directory/search", params={"q": "台積電"})

    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["symbol"] == "2330"
    assert item["name"] == "台積電"
    assert item["market"] == "TW"


def test_search_default_limit_is_12_and_truncated_flag(
    client: TestClient, store: SecurityDirectoryStore
) -> None:
    store.upsert([_entry(f"1{i:03d}", f"電子公司{i}") for i in range(20)])

    response = client.get("/api/directory/search", params={"q": "電"})

    body = response.json()
    assert body["limit"] == 12
    assert len(body["items"]) == 12
    assert body["truncated"] is True


def test_search_limit_override(client: TestClient, store: SecurityDirectoryStore) -> None:
    store.upsert([_entry(f"1{i:03d}", f"電子公司{i}") for i in range(20)])

    response = client.get("/api/directory/search", params={"q": "電", "limit": 5})

    body = response.json()
    assert len(body["items"]) == 5
    assert body["limit"] == 5
    assert body["truncated"] is True


def test_search_on_empty_directory_returns_empty_with_honest_flag(client: TestClient) -> None:
    response = client.get("/api/directory/search", params={"q": "2330"})

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["directory_synced"] is False


def test_search_requires_nonempty_query(client: TestClient, store: SecurityDirectoryStore) -> None:
    store.upsert([_entry("2330", "台積電")])

    response = client.get("/api/directory/search", params={"q": ""})

    assert response.status_code == 422
