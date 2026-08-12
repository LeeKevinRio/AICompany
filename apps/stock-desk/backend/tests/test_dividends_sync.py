"""Offline tests for the ``python -m app.dividends.sync`` CLI.

Everything here runs against ``httpx.MockTransport`` and temp SQLite files --
never the real network -- per the data-source-integration skill's rule.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.data.http import RateLimitedClient
from app.dividends.providers import TWSE_OPENAPI_BASE_URL, TwseDividendAdapter
from app.dividends.store import DividendEventStore
from app.dividends.sync import main, sync_dividends

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_NAME = "twse_openapi_twt48u_all.json"
AS_OF = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def _fixture() -> list[object]:
    return json.loads((FIXTURES_DIR / FIXTURE_NAME).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _ok_client(payload: list[object]) -> RateLimitedClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return RateLimitedClient(
        base_url=TWSE_OPENAPI_BASE_URL,
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )


def _client_factory(
    payload: list[object] | None, *, status: int = 200, unreachable: bool = False
) -> object:
    def build(*args: object, **kwargs: object) -> RateLimitedClient:
        def handler(request: httpx.Request) -> httpx.Response:
            if unreachable:
                raise httpx.ConnectError("connection refused", request=request)
            return httpx.Response(status, json=payload if payload is not None else [])

        return RateLimitedClient(
            base_url=str(kwargs.get("base_url", "")),
            min_interval_seconds=0.0,
            max_retries=0,
            transport=httpx.MockTransport(handler),
            sleep_fn=lambda _s: None,
        )

    return build


def test_sync_writes_the_parseable_events(tmp_path: Path) -> None:
    store = DividendEventStore(db_path=tmp_path / "d.db")
    result = sync_dividends(
        store=store,
        adapter=TwseDividendAdapter(client=_ok_client(_fixture())),
        synced_at=AS_OF,
    )
    assert result.ok is True
    assert store.count() == 4
    assert len(store.events_for("2330", "TW")) == 1


def test_sync_is_idempotent(tmp_path: Path) -> None:
    """The upstream dataset is an announcement calendar, not a rolling window
    of results, but the same rule applies: reruns accumulate, not duplicate."""
    store = DividendEventStore(db_path=tmp_path / "d.db")
    for _ in range(3):
        sync_dividends(
            store=store,
            adapter=TwseDividendAdapter(client=_ok_client(_fixture())),
            synced_at=AS_OF,
        )
    assert store.count() == 4


def test_sync_never_deletes_rows_a_later_response_no_longer_lists(tmp_path: Path) -> None:
    """The predict table is additive: a symbol dropping off a later response
    (its ex-date passed, or it was pulled) must not erase what was stored."""
    store = DividendEventStore(db_path=tmp_path / "d.db")
    sync_dividends(
        store=store,
        adapter=TwseDividendAdapter(client=_ok_client(_fixture())),
        synced_at=AS_OF,
    )
    assert store.count() == 4

    only_one_row = [row for row in _fixture() if row.get("Code") == "2330"]  # type: ignore[union-attr]
    sync_dividends(
        store=store,
        adapter=TwseDividendAdapter(client=_ok_client(only_one_row)),
        synced_at=AS_OF,
    )
    assert store.count() == 4  # nothing was deleted, only the "2330" row refreshed


def test_main_prints_network_guidance_instead_of_traceback_when_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "app.dividends.sync.RateLimitedClient", _client_factory(None, unreachable=True)
    )
    exit_code = main(["--db-path", str(tmp_path / "d.db")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "有網路的機器" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


def test_main_prints_schema_guidance_when_the_endpoint_is_wrong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-200 despite a verified endpoint means the upstream likely changed."""
    monkeypatch.setattr("app.dividends.sync.RateLimitedClient", _client_factory([], status=404))
    exit_code = main(["--db-path", str(tmp_path / "d.db")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "覆核" in captured.err
    assert "有網路的機器" not in captured.err
    assert "Traceback" not in captured.out


def test_main_succeeds_and_writes_db_when_reachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("app.dividends.sync.RateLimitedClient", _client_factory(_fixture()))
    db_path = tmp_path / "d.db"
    exit_code = main(["--db-path", str(db_path)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "twse_openapi_dividend" in captured.out
    # Partial coverage is printed, not swallowed.
    assert "略過 3 列" in captured.out
    assert DividendEventStore(db_path=db_path).count() == 4
