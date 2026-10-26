"""FD-3 web additions: security headers on every response (C-29), scan-status (C-30)."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from flight_deals.web.server import SECURITY_HEADERS, SecurityHeadersMiddleware
from tests.conftest import CLIENT_HEADERS, Harness

STATUS_FIELDS = {"watch_id", "scan_run_id", "status", "started_at", "finished_at"}


def assert_security_headers(headers: object) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert headers[name] == value, name  # type: ignore[index]


# ---- C-29 security headers -----------------------------------------------------------


def test_untrusted_host_400_has_security_headers(harness: Harness) -> None:  # AC-H2, AC-H3
    response = harness.client.get("/", headers={"host": "evil.example"})
    assert response.status_code == 400 and response.text == "Invalid host header"
    assert_security_headers(response.headers)


def test_missing_client_header_403_has_security_headers(harness: Harness) -> None:  # AC-H1
    response = harness.client.post("/api/watches", json={})
    assert response.status_code == 403
    assert "X-Flight-Deals-Client" in response.json()["error"]
    assert_security_headers(response.headers)


def test_404_page_and_unknown_route_have_security_headers(harness: Harness) -> None:
    assert_security_headers(harness.client.get("/watches/999").headers)
    response = harness.client.get("/no-such-page")
    assert response.status_code == 404
    assert_security_headers(response.headers)


def test_422_has_security_headers(harness: Harness) -> None:
    response = harness.client.post("/api/watches", json={}, headers=CLIENT_HEADERS)
    assert response.status_code == 422
    assert_security_headers(response.headers)
    response = harness.client.get("/api/airports", params={"q": "x" * 40})
    assert response.status_code == 422
    assert_security_headers(response.headers)


def test_static_files_have_security_headers(harness: Harness) -> None:
    response = harness.client.get("/static/app.css")
    assert response.status_code == 200
    assert_security_headers(response.headers)


def test_normal_page_headers_unchanged(harness: Harness) -> None:
    assert_security_headers(harness.client.get("/").headers)


def test_route_set_header_is_not_overwritten() -> None:
    def own(_request: Request) -> PlainTextResponse:
        return PlainTextResponse("x", headers={"X-Frame-Options": "SAMEORIGIN"})

    app = Starlette(routes=[Route("/own", own)])
    app.add_middleware(SecurityHeadersMiddleware)
    response = TestClient(app).get("/own")
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert len(response.headers.get_list("X-Frame-Options")) == 1
    assert (
        response.headers["Content-Security-Policy"] == SECURITY_HEADERS["Content-Security-Policy"]
    )


# ---- C-30 scan-status ----------------------------------------------------------------


def test_scan_status_before_any_scan(harness: Harness) -> None:
    watch_id = harness.create_watch()
    response = harness.client.get(f"/api/watches/{watch_id}/scan-status")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "watch_id": watch_id,
        "scan_run_id": None,
        "status": None,
        "started_at": None,
        "finished_at": None,
    }


def test_scan_status_reports_latest_run_with_whitelisted_fields(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    harness.clock.advance(minutes=5)
    harness.scan(watch_id)
    latest = harness.repo.scan_runs_for_watch(watch_id)[0]
    response = harness.client.get(f"/api/watches/{watch_id}/scan-status")  # no client header
    body = response.json()
    assert set(body) == STATUS_FIELDS
    assert body["scan_run_id"] == latest.id and body["status"] == "ok"
    assert body["started_at"] == "2026-10-25T04:05:00+00:00"
    assert body["finished_at"] == "2026-10-25T04:05:00+00:00"
    assert response.headers["Cache-Control"] == "no-store"
    assert_security_headers(response.headers)


def test_scan_status_shows_running_run(harness: Harness) -> None:
    watch_id = harness.create_watch()
    watch = harness.repo.get_watch(watch_id)
    run_id = harness.repo.insert_scan_run(
        watch_id=watch_id,
        revision=watch.revision,
        trigger="manual",
        started_at=harness.clock(),
        sampled_pairs=[],
        total_pairs=1,
        limit_reached=False,
    )
    body = harness.client.get(f"/api/watches/{watch_id}/scan-status").json()
    assert body["scan_run_id"] == run_id and body["status"] == "running"
    assert body["finished_at"] is None


def test_scan_status_404_for_unknown_watch(harness: Harness) -> None:
    response = harness.client.get("/api/watches/999/scan-status")
    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_scan_status_is_read_only(harness: Harness, method: str) -> None:
    watch_id = harness.create_watch()
    response = harness.client.request(
        method, f"/api/watches/{watch_id}/scan-status", headers=CLIENT_HEADERS
    )
    assert response.status_code == 405


def test_scan_status_writes_nothing(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    db_path = harness.assembly.database.path

    def snapshot() -> tuple[object, ...]:
        with harness.assembly.database.connect() as conn:
            tables = [
                r["name"]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            ]
            return tuple(
                (t, tuple(tuple(row) for row in conn.execute(f"SELECT * FROM {t}")))
                for t in sorted(tables)
            )

    before = snapshot()
    for _ in range(3):
        assert harness.client.get(f"/api/watches/{watch_id}/scan-status").status_code == 200
    harness.client.get("/api/watches/999/scan-status")
    assert snapshot() == before and db_path.exists()
