"""Tests for the /health endpoint."""

from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_has_all_fields() -> None:
    body = client.get("/health").json()
    assert set(body.keys()) == {"status", "service", "as_of"}
    assert body["status"] == "ok"
    assert body["service"] == "backend"


def test_health_as_of_is_parseable_iso8601() -> None:
    body = client.get("/health").json()
    # Must be parseable as an ISO8601 timestamp.
    parsed = datetime.fromisoformat(body["as_of"])
    # A timezone-aware UTC timestamp is expected per the data convention.
    assert parsed.tzinfo is not None


def test_cors_allows_frontend_dev_origin() -> None:
    # The frontend dev server (http://localhost:3000) must be allowed to call
    # the API cross-origin.
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_preflight_on_positions_endpoint() -> None:
    response = client.options(
        "/api/positions",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
