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
    SectorProfileFetchResult,
    TpexDirectoryAdapter,
    TwseDirectoryAdapter,
    TwseSectorProfileAdapter,
)
from app.directory.sector_backfill import SectorBackfillReport
from app.directory.sector_resolve import SectorResolution
from app.directory.store import SecurityDirectoryStore
from app.directory.sync import (
    _all_unreachable,
    _print_backfill_report,
    _print_sector_sync_result,
    main,
    run_sector_verification,
    sync_directory,
    sync_sectors,
)
from app.positions.models import PositionInput
from app.positions.store import PositionStore

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
    # Code 91 resolves to 存託憑證, which TWSE_SECTORS now contains (CEO ruling
    # 2026-08-12), so it must surface in the matched section -- not as an
    # official_only gap.
    matched_section = markdown.split("## 雙方一致")[1].split("## 官方有、本地清單沒有")[0]
    official_only_section = markdown.split("## 官方有、本地清單沒有")[1].split("## ")[0]
    assert "- 存託憑證" in matched_section
    assert "存託憑證" not in official_only_section
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


# --------------------------------------------------------------------------
# Sector persistence: the 產業別 pass writes onto the rows the symbol sources wrote
# --------------------------------------------------------------------------


def _add_position(store: PositionStore, **overrides: object) -> int:
    payload: dict[str, object] = {
        "symbol": "2330",
        "market": "TW",
        "quantity": "1000",
        "avg_cost": "600",
        "currency": "TWD",
        "instrument_type": "stock",
    }
    payload.update(overrides)
    return store.create(PositionInput.model_validate(payload)).id


def _synced_store(tmp_path: Path) -> SecurityDirectoryStore:
    store = SecurityDirectoryStore(db_path=tmp_path / "directory.db")
    twse = TwseDirectoryAdapter(
        client=_ok_client(TWSE_OPENAPI_BASE_URL, _fixture_json("twse_openapi_stock_day_all.json"))
    )
    tpex = TpexDirectoryAdapter(
        client=_ok_client(
            TPEX_OPENAPI_BASE_URL, _fixture_json("tpex_openapi_mainboard_daily_close_quotes.json")
        )
    )
    sync_directory(store=store, twse_adapter=twse, tpex_adapter=tpex, synced_at=AS_OF)
    return store


def test_sync_sectors_writes_resolved_categories_onto_existing_rows(tmp_path: Path) -> None:
    store = _synced_store(tmp_path)
    adapter = TwseSectorProfileAdapter(
        client=_ok_client(TWSE_OPENAPI_BASE_URL, _fixture_json("twse_openapi_t187ap03_l.json"))
    )

    result, resolution, matched = sync_sectors(store=store, sector_adapter=adapter)

    assert result.ok is True
    assert resolution is not None
    # 2330/24 -> 半導體業 is the only fixture company also present in the
    # symbol/name fixture, so exactly one directory row can be matched.
    assert matched == 1
    entry = store.resolve("2330")
    assert entry is not None
    assert entry.sector == "半導體業"
    assert entry.sector_source == "twse_openapi_t187ap03_L"


def test_sync_sectors_leaves_etf_and_otc_rows_without_a_category(tmp_path: Path) -> None:
    store = _synced_store(tmp_path)
    adapter = TwseSectorProfileAdapter(
        client=_ok_client(TWSE_OPENAPI_BASE_URL, _fixture_json("twse_openapi_t187ap03_l.json"))
    )

    sync_sectors(store=store, sector_adapter=adapter)

    for symbol in ("0050", "5483"):
        entry = store.resolve(symbol)
        assert entry is not None
        assert entry.sector is None


def test_sync_sectors_drops_the_unknown_code_row(tmp_path: Path) -> None:
    store = _synced_store(tmp_path)
    adapter = TwseSectorProfileAdapter(
        client=_ok_client(TWSE_OPENAPI_BASE_URL, _fixture_json("twse_openapi_t187ap03_l.json"))
    )

    _result, resolution, _matched = sync_sectors(store=store, sector_adapter=adapter)

    assert resolution is not None
    assert resolution.unknown_codes == ("99",)
    assert all(a.symbol != "9921" for a in resolution.assignments)


def test_sync_sectors_unreachable_leaves_the_directory_untouched(tmp_path: Path) -> None:
    store = _synced_store(tmp_path)
    adapter = TwseSectorProfileAdapter(client=_unreachable_client(TWSE_OPENAPI_BASE_URL))

    result, resolution, matched = sync_sectors(store=store, sector_adapter=adapter)

    assert result.ok is False
    assert resolution is None
    assert matched == 0
    assert store.count() == 8  # AC-2: the symbol/name rows still stand
    assert store.sector_count() == 0


# --------------------------------------------------------------------------
# --backfill-sectors -- offline, never overwrites
# --------------------------------------------------------------------------


def test_backfill_sectors_flag_fills_only_empty_tw_holdings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "directory.db"
    store = _synced_store(tmp_path)
    sync_sectors(
        store=store,
        sector_adapter=TwseSectorProfileAdapter(
            client=_ok_client(TWSE_OPENAPI_BASE_URL, _fixture_json("twse_openapi_t187ap03_l.json"))
        ),
    )
    positions = PositionStore(db_path=db_path)
    empty_id = _add_position(positions, symbol="2330")
    manual_id = _add_position(positions, symbol="3037", sector="其他業")
    etf_id = _add_position(positions, symbol="0050", instrument_type="etf")

    exit_code = main(["--db-path", str(db_path), "--backfill-sectors"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "補上 2330 -> 半導體業" in captured.out
    assert "不覆蓋" in captured.out
    filled = positions.get(empty_id)
    manual = positions.get(manual_id)
    etf = positions.get(etf_id)
    assert filled is not None and manual is not None and etf is not None
    assert filled.sector == "半導體業"
    assert manual.sector == "其他業"  # manual value survives
    assert etf.sector is None  # no category in the directory, so still empty


def test_backfill_sectors_flag_needs_no_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag must not construct an HTTP client at all -- it reads SQLite only."""

    def _explode(*args: object, **kwargs: object) -> RateLimitedClient:
        raise AssertionError("--backfill-sectors must not open a network client")

    monkeypatch.setattr("app.directory.sync.RateLimitedClient", _explode)

    assert main(["--db-path", str(tmp_path / "directory.db"), "--backfill-sectors"]) == 0


def test_main_runs_the_sector_pass_and_backfill_in_one_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One `python -m app.directory.sync` covers 目錄 + 產業別 + 回填."""
    stock_day_all = _fixture_json("twse_openapi_stock_day_all.json")
    profile = _fixture_json("twse_openapi_t187ap03_l.json")
    tpex_payload = _fixture_json("tpex_openapi_mainboard_daily_close_quotes.json")

    def fake_rate_limited_client(*args: object, **kwargs: object) -> RateLimitedClient:
        base_url = str(kwargs.get("base_url", ""))

        def handler(request: httpx.Request) -> httpx.Response:
            if "openapi.twse.com.tw" not in base_url:
                return httpx.Response(200, json=tpex_payload)
            payload = profile if "t187ap03_L" in request.url.path else stock_day_all
            return httpx.Response(200, json=payload)

        return RateLimitedClient(
            base_url=base_url,
            min_interval_seconds=0.0,
            transport=httpx.MockTransport(handler),
            sleep_fn=lambda _s: None,
        )

    monkeypatch.setattr("app.directory.sync.RateLimitedClient", fake_rate_limited_client)

    db_path = tmp_path / "directory.db"
    positions = PositionStore(db_path=db_path)
    position_id = _add_position(positions, symbol="2330")

    exit_code = main(["--db-path", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "twse_openapi_t187ap03_L" in captured.out
    assert "持倉產業別回填" in captured.out
    store = SecurityDirectoryStore(db_path=db_path)
    assert store.count() == 8
    assert store.sector_count() == 1
    stored = positions.get(position_id)
    assert stored is not None
    assert stored.sector == "半導體業"


# --------------------------------------------------------------------------
# CLI reporting: every drop/skip must be printed with its own reason
# --------------------------------------------------------------------------


def test_sector_sync_report_names_every_drop_reason(capsys: pytest.CaptureFixture[str]) -> None:
    result = SectorProfileFetchResult(
        entries=(),
        ok=True,
        reason=None,
        source="twse_openapi_t187ap03_L",
        as_of=AS_OF,
    )
    resolution = SectorResolution(
        assignments=(),
        blank_code_rows=2,
        unknown_code_rows=3,
        unknown_codes=("98", "99"),
        outside_closed_list_rows=1,
        outside_closed_list_names=("尚未納入清單的產業",),
        duplicate_symbol_rows=4,
    )

    _print_sector_sync_result(result, resolution, 0)

    out = capsys.readouterr().out
    assert "略過 3 筆：產業別代碼不在對照表中（98、99）" in out
    assert "不以猜測值寫入" in out
    assert "略過 1 筆：代碼可解析但名稱不在" in out
    assert "尚未納入清單的產業" in out
    assert "略過 2 筆：該列產業別欄為空。" in out
    assert "略過 4 筆：同一代號重複出現，只取第一筆。" in out


def test_sector_sync_report_states_when_the_source_is_unusable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = SectorProfileFetchResult(
        entries=(),
        ok=False,
        reason="連線失敗（ConnectError）",
        source="twse_openapi_t187ap03_L",
        as_of=AS_OF,
    )

    _print_sector_sync_result(result, None, 0)

    out = capsys.readouterr().out
    assert "FAIL/UNREACHABLE" in out
    assert "連線失敗" in out
    # AC-2: the failure must be scoped, not read as "the whole sync is void".
    assert "目錄的代號/名稱資料不受影響" in out


def test_backfill_report_prints_every_skip_reason(capsys: pytest.CaptureFixture[str]) -> None:
    report = SectorBackfillReport(
        filled=(("2330", "半導體業"),),
        skipped_already_set=2,
        skipped_not_tw=3,
        skipped_not_in_directory=4,
        skipped_directory_has_no_sector=5,
        skipped_invalid_directory_sector=6,
    )

    _print_backfill_report(report)

    out = capsys.readouterr().out
    assert "檢視 21 檔，補上 1 檔，跳過 20 檔" in out
    assert "補上 2330 -> 半導體業" in out
    assert "跳過 2 檔：已有產業別，不覆蓋（手動填的值優先）。" in out
    assert "跳過 3 檔：非台股持倉" in out
    assert "跳過 4 檔：證券目錄查無此代號。" in out
    assert "跳過 5 檔：目錄有此代號但沒有產業別" in out
    assert "跳過 6 檔：目錄中的產業別不在目前封閉清單內" in out
