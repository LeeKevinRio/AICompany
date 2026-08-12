"""Offline tests for the ``python -m app.directory.sync`` CLI.

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
from app.directory.providers import (
    TPEX_OPENAPI_BASE_URL,
    TWSE_OPENAPI_BASE_URL,
    TpexDirectoryAdapter,
    TwseDirectoryAdapter,
    TwseSectorProfileAdapter,
)
from app.directory.store import SecurityDirectoryStore
from app.directory.sync import _all_unreachable, main, run_sector_verification, sync_directory

FIXTURES_DIR = Path(__file__).parent / "fixtures"
AS_OF = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _fixture_json(name: str) -> list[object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _ok_client(base_url: str, payload: list[object]) -> RateLimitedClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return RateLimitedClient(
        base_url=base_url,
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )


def _unreachable_client(base_url: str) -> RateLimitedClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return RateLimitedClient(
        base_url=base_url,
        min_interval_seconds=0.0,
        max_retries=0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )


def test_sync_directory_writes_both_sources(tmp_path: Path) -> None:
    store = SecurityDirectoryStore(db_path=tmp_path / "directory.db")
    twse = TwseDirectoryAdapter(
        client=_ok_client(TWSE_OPENAPI_BASE_URL, _fixture_json("twse_openapi_stock_day_all.json"))
    )
    tpex = TpexDirectoryAdapter(
        client=_ok_client(
            TPEX_OPENAPI_BASE_URL, _fixture_json("tpex_openapi_mainboard_daily_close_quotes.json")
        )
    )

    results = sync_directory(store=store, twse_adapter=twse, tpex_adapter=tpex, synced_at=AS_OF)

    assert all(result.ok for result in results)
    assert store.count() == 3 + 5  # 3 TWSE rows + 5 TPEx rows, blank row skipped
    assert store.resolve("2330") is not None
    assert store.resolve("5483") is not None


def test_sync_directory_is_idempotent(tmp_path: Path) -> None:
    store = SecurityDirectoryStore(db_path=tmp_path / "directory.db")

    def run_once() -> None:
        twse = TwseDirectoryAdapter(
            client=_ok_client(
                TWSE_OPENAPI_BASE_URL, _fixture_json("twse_openapi_stock_day_all.json")
            )
        )
        tpex = TpexDirectoryAdapter(
            client=_ok_client(
                TPEX_OPENAPI_BASE_URL,
                _fixture_json("tpex_openapi_mainboard_daily_close_quotes.json"),
            )
        )
        sync_directory(store=store, twse_adapter=twse, tpex_adapter=tpex, synced_at=AS_OF)

    run_once()
    run_once()
    run_once()

    assert store.count() == 8


def test_sync_directory_partial_failure_still_writes_the_working_source(tmp_path: Path) -> None:
    """AC-2: one source failing must not withhold the other's already-fetched rows."""
    store = SecurityDirectoryStore(db_path=tmp_path / "directory.db")
    twse = TwseDirectoryAdapter(
        client=_ok_client(TWSE_OPENAPI_BASE_URL, _fixture_json("twse_openapi_stock_day_all.json"))
    )
    tpex = TpexDirectoryAdapter(client=_unreachable_client(TPEX_OPENAPI_BASE_URL))

    results = sync_directory(store=store, twse_adapter=twse, tpex_adapter=tpex, synced_at=AS_OF)

    twse_result, tpex_result = results
    assert twse_result.ok is True
    assert tpex_result.ok is False
    assert "連線失敗" in (tpex_result.reason or "")
    # TWSE's rows landed even though TPEx failed.
    assert store.count() == 3
    assert store.resolve("2330") is not None
    assert store.resolve("5483") is None


def test_all_unreachable_true_only_when_both_are_network_failures(tmp_path: Path) -> None:
    store = SecurityDirectoryStore(db_path=tmp_path / "directory.db")
    twse = TwseDirectoryAdapter(client=_unreachable_client(TWSE_OPENAPI_BASE_URL))
    tpex = TpexDirectoryAdapter(client=_unreachable_client(TPEX_OPENAPI_BASE_URL))

    results = sync_directory(store=store, twse_adapter=twse, tpex_adapter=tpex, synced_at=AS_OF)

    assert _all_unreachable(results) is True


def test_all_unreachable_false_when_one_source_succeeds(tmp_path: Path) -> None:
    store = SecurityDirectoryStore(db_path=tmp_path / "directory.db")
    twse = TwseDirectoryAdapter(
        client=_ok_client(TWSE_OPENAPI_BASE_URL, _fixture_json("twse_openapi_stock_day_all.json"))
    )
    tpex = TpexDirectoryAdapter(client=_unreachable_client(TPEX_OPENAPI_BASE_URL))

    results = sync_directory(store=store, twse_adapter=twse, tpex_adapter=tpex, synced_at=AS_OF)

    assert _all_unreachable(results) is False


def test_main_prints_network_guidance_instead_of_traceback_when_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When outbound HTTPS is blocked (this sandbox's known limitation), the CLI
    must exit cleanly with clear guidance -- never an unhandled traceback."""

    def _raising_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def fake_rate_limited_client(*args: object, **kwargs: object) -> RateLimitedClient:
        return RateLimitedClient(
            base_url=str(kwargs.get("base_url", "")),
            min_interval_seconds=0.0,
            max_retries=0,
            transport=httpx.MockTransport(_raising_transport),
            sleep_fn=lambda _s: None,
        )

    monkeypatch.setattr("app.directory.sync.RateLimitedClient", fake_rate_limited_client)

    exit_code = main(["--db-path", str(tmp_path / "directory.db")])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "有網路的機器" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


def test_main_succeeds_and_writes_db_when_reachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    twse_payload = _fixture_json("twse_openapi_stock_day_all.json")
    tpex_payload = _fixture_json("tpex_openapi_mainboard_daily_close_quotes.json")

    def fake_rate_limited_client(*args: object, **kwargs: object) -> RateLimitedClient:
        base_url = str(kwargs.get("base_url", ""))
        payload = twse_payload if "openapi.twse.com.tw" in base_url else tpex_payload

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        return RateLimitedClient(
            base_url=base_url,
            min_interval_seconds=0.0,
            transport=httpx.MockTransport(handler),
            sleep_fn=lambda _s: None,
        )

    monkeypatch.setattr("app.directory.sync.RateLimitedClient", fake_rate_limited_client)

    db_path = tmp_path / "directory.db"
    exit_code = main(["--db-path", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "twse_openapi" in captured.out
    assert "tpex_openapi" in captured.out

    store = SecurityDirectoryStore(db_path=db_path)
    assert store.count() == 8


# --------------------------------------------------------------------------
# --verify-sectors -- never touches the SQLite store, never writes sectors.py
# --------------------------------------------------------------------------


def test_run_sector_verification_writes_report_and_returns_zero(tmp_path: Path) -> None:
    payload = _fixture_json("twse_openapi_t187ap03_l.json")
    adapter = TwseSectorProfileAdapter(client=_ok_client(TWSE_OPENAPI_BASE_URL, payload))
    output_path = tmp_path / "產業清單覆核.md"

    exit_code, result = run_sector_verification(adapter=adapter, output_path=output_path)

    assert exit_code == 0
    assert result.ok is True
    assert output_path.exists()
    markdown = output_path.read_text(encoding="utf-8")
    assert "不會被本工具自動修改" in markdown
    assert "存託憑證" in markdown  # official_only: code 91 has no TWSE_SECTORS match
    assert "99" in markdown  # UNKNOWN_CODE: code not in twse_sector_codes.py


def test_run_sector_verification_returns_one_and_no_file_when_unreachable(tmp_path: Path) -> None:
    adapter = TwseSectorProfileAdapter(client=_unreachable_client(TWSE_OPENAPI_BASE_URL))
    output_path = tmp_path / "產業清單覆核.md"

    exit_code, result = run_sector_verification(adapter=adapter, output_path=output_path)

    assert exit_code == 1
    assert result.ok is False
    assert not output_path.exists()


def test_main_verify_sectors_prints_guidance_and_exits_one_when_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _raising_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def fake_rate_limited_client(*args: object, **kwargs: object) -> RateLimitedClient:
        return RateLimitedClient(
            base_url=str(kwargs.get("base_url", "")),
            min_interval_seconds=0.0,
            max_retries=0,
            transport=httpx.MockTransport(_raising_transport),
            sleep_fn=lambda _s: None,
        )

    monkeypatch.setattr("app.directory.sync.RateLimitedClient", fake_rate_limited_client)

    exit_code = main(["--verify-sectors", "--sectors-output", str(tmp_path / "report.md")])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "有網路的機器" in captured.err
    assert "--verify-sectors" in captured.err
    assert "Traceback" not in captured.err
    assert not (tmp_path / "report.md").exists()


def test_main_verify_sectors_writes_report_when_reachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _fixture_json("twse_openapi_t187ap03_l.json")

    def fake_rate_limited_client(*args: object, **kwargs: object) -> RateLimitedClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        return RateLimitedClient(
            base_url=str(kwargs.get("base_url", "")),
            min_interval_seconds=0.0,
            transport=httpx.MockTransport(handler),
            sleep_fn=lambda _s: None,
        )

    monkeypatch.setattr("app.directory.sync.RateLimitedClient", fake_rate_limited_client)

    output_path = tmp_path / "產業清單覆核.md"
    exit_code = main(["--verify-sectors", "--sectors-output", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "twse_openapi_t187ap03_L" in captured.out
    assert output_path.exists()
    assert "產業清單覆核" in output_path.read_text(encoding="utf-8")
