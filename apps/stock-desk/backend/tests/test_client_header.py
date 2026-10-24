"""The cross-site write guard (:mod:`app.api.client_header`).

A browser lets any page send a body-less or multipart POST to localhost, and
CORS only hides the response. These tests pin that such a request is refused
*before* it reaches a router, while the frontend's own requests (which carry
the header after a CORS preflight) still go through.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.client_header import CLIENT_HEADER, MISSING_HEADER_DETAIL
from app.api.deps import get_playbook_service
from app.main import FRONTEND_DEV_ORIGIN, app


class _ExplodingService:
    """A playbook service that fails the test the moment any method is used."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"guarded request reached the service ({name})")


@pytest.fixture
def bare_client() -> Iterator[TestClient]:
    """A client that sends no custom header, like a cross-site form post."""
    app.dependency_overrides[get_playbook_service] = _ExplodingService
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/playbook/emergency-exit"),
        ("POST", "/api/playbook/rebalance"),
        ("POST", "/api/playbook/settle"),
        ("POST", "/api/alerts/events/1/ack"),
        ("POST", "/api/alerts/evaluate"),
        ("POST", "/api/positions/import"),
        ("PUT", "/api/settings"),
        ("DELETE", "/api/positions/1"),
    ],
)
def test_write_without_header_is_refused_before_the_router(
    bare_client: TestClient, method: str, path: str
) -> None:
    response = bare_client.request(method, path)

    assert response.status_code == 403
    assert response.json() == {"detail": MISSING_HEADER_DETAIL}


def test_multipart_form_post_is_refused(bare_client: TestClient) -> None:
    # The exact shape a hostile page can auto-submit: a multipart form.
    response = bare_client.post(
        "/api/positions/import",
        files={"file": ("x.csv", b"symbol,quantity\n2330,1000\n", "text/csv")},
    )

    assert response.status_code == 403


def test_safe_methods_need_no_header(bare_client: TestClient) -> None:
    assert bare_client.get("/health").status_code == 200
    assert bare_client.head("/health").status_code != 403


def test_write_with_header_reaches_the_router(bare_client: TestClient) -> None:
    # The exploding service proves the request got past the guard.
    with pytest.raises(AssertionError, match="reached the service"):
        bare_client.post("/api/playbook/emergency-exit", headers={CLIENT_HEADER: "1"})


def test_preflight_from_the_frontend_allows_the_header(bare_client: TestClient) -> None:
    response = bare_client.options(
        "/api/playbook/emergency-exit",
        headers={
            "Origin": FRONTEND_DEV_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": CLIENT_HEADER,
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_DEV_ORIGIN


def test_refusal_is_readable_by_the_frontend(bare_client: TestClient) -> None:
    # CORS wraps the guard, so the frontend can read the 403 instead of
    # seeing an opaque network error.
    response = bare_client.post("/api/alerts/evaluate", headers={"Origin": FRONTEND_DEV_ORIGIN})

    assert response.status_code == 403
    assert response.headers["access-control-allow-origin"] == FRONTEND_DEV_ORIGIN
