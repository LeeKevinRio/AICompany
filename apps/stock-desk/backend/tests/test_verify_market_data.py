"""Offline tests for the CEO-facing ``verify_market_data.py`` diagnostic tool.

Everything here runs against ``httpx.MockTransport`` and temp SQLite files --
never the real network -- per the data-source-integration skill's "測試一律
用 fixture 不打外網" rule. The fixtures reused below (``twse_stock_day_*``,
``tpex_daily_trading_*``, ``finmind_taiwan_stock_price_*``,
``bot_fx_usd_twd_*``, ``alpha_vantage_daily_*``, ``yfinance_chart_twii``) are
the same synthetic, documented-but-unverified files every other adapter
contract test in this directory already uses (see ``tests/fixtures/README.md``).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from app.data.cache import PriceBarCache
from app.data.quota import DAILY_LIMIT_ENV_VAR, SAFETY_MARGIN_ENV_VAR
from app.leverage.detect import KNOWN_LEVERAGED_ETF
from app.positions.models import PositionInput
from app.positions.store import PositionStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "verify_market_data.py"


def _load_script_module() -> ModuleType:
    """Import ``verify_market_data.py`` by path so it need not be a package."""
    spec = importlib.util.spec_from_file_location("verify_market_data", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vmd = _load_script_module()


def _fixture_json(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _fixture_text(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# check_reachability
# --------------------------------------------------------------------------


def test_check_reachability_pass_on_any_http_status() -> None:
    def get_fn(_url: str, _timeout: float) -> httpx.Response:
        return httpx.Response(403)

    result = vmd.check_reachability("https://example.invalid", get_fn=get_fn)
    assert result.reachable is True
    assert "403" in result.detail


def test_check_reachability_unreachable_on_transport_error() -> None:
    def get_fn(_url: str, _timeout: float) -> httpx.Response:
        raise httpx.ConnectError("boom", request=httpx.Request("GET", "https://example.invalid"))

    result = vmd.check_reachability("https://example.invalid", get_fn=get_fn)
    assert result.reachable is False
    assert "ConnectError" in result.detail


# --------------------------------------------------------------------------
# classify_result
# --------------------------------------------------------------------------


def test_classify_result_missing_credential_is_fail() -> None:
    result = vmd.classify_result(
        name="finmind",
        endpoint="https://api.finmindtrade.com/api/v4/data",
        credential_ok=False,
        credential_hint="FINMIND_API_TOKEN",
        reachability=None,
        bars=[],
        status=None,
        reason=None,
        as_of=None,
    )
    assert result.verdict is vmd.Verdict.FAIL
    assert "FINMIND_API_TOKEN" in result.detail


def test_classify_result_unreachable_short_circuits_before_bars_checked() -> None:
    reach = vmd.ReachabilityResult(reachable=False, detail="連線失敗：boom")
    result = vmd.classify_result(
        name="twse",
        endpoint="https://www.twse.com.tw/exchangeReport/STOCK_DAY",
        credential_ok=True,
        credential_hint="",
        reachability=reach,
        bars=[],
        status=None,
        reason=None,
        as_of=None,
    )
    assert result.verdict is vmd.Verdict.UNREACHABLE
    assert result.detail == "連線失敗：boom"


def test_classify_result_pass_when_bars_present() -> None:
    payload = _fixture_json("twse_stock_day_2330_202401.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    result = vmd.probe_twse(
        "2330",
        date(2024, 1, 1),
        date(2024, 1, 31),
        transport=httpx.MockTransport(handler),
        reachability=vmd.ReachabilityResult(reachable=True, detail="HTTP 200"),
    )
    assert result.verdict is vmd.Verdict.PASS
    assert result.record_count == 3


def test_classify_result_fail_when_reachable_but_no_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"stat": "查無資料"})

    result = vmd.probe_twse(
        "9999",
        date(2024, 1, 1),
        date(2024, 1, 31),
        transport=httpx.MockTransport(handler),
        reachability=vmd.ReachabilityResult(reachable=True, detail="HTTP 200"),
    )
    assert result.verdict is vmd.Verdict.FAIL
    assert result.record_count == 0


# --------------------------------------------------------------------------
# compare_bars (zero tolerance)
# --------------------------------------------------------------------------


def _bar(trade_date: date, close: str, volume: int, *, source: str) -> "vmd.PriceBar":
    from datetime import UTC, datetime
    from decimal import Decimal

    return vmd.PriceBar(
        symbol="2330",
        market="TW",
        date=trade_date,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=volume,
        currency="TWD",
        as_of=datetime.now(UTC),
        source=source,
    )


def test_compare_bars_all_match_is_pass() -> None:
    primary = [_bar(date(2024, 1, 2), "594.00", 41_393_088, source="twse")]
    backup = [_bar(date(2024, 1, 2), "594.00", 41_393_088, source="finmind")]
    rows = vmd.compare_bars("2330", primary, backup)
    assert len(rows) == 1
    assert rows[0].verdict is vmd.Verdict.PASS


def test_compare_bars_close_mismatch_is_fail() -> None:
    primary = [_bar(date(2024, 1, 2), "594.00", 41_393_088, source="twse")]
    backup = [_bar(date(2024, 1, 2), "600.00", 41_393_088, source="finmind")]
    rows = vmd.compare_bars("2330", primary, backup)
    assert rows[0].verdict is vmd.Verdict.FAIL
    assert "收盤價不同" in rows[0].note


def test_compare_bars_volume_unit_mismatch_flags_hint() -> None:
    primary = [_bar(date(2024, 1, 2), "594.00", 41_393, source="twse")]
    backup = [_bar(date(2024, 1, 2), "594.00", 41_393_000, source="finmind")]
    rows = vmd.compare_bars("2330", primary, backup)
    assert rows[0].verdict is vmd.Verdict.FAIL
    assert "股／張單位不一致" in rows[0].note


def test_compare_bars_missing_side_is_fail_not_silently_dropped() -> None:
    primary = [_bar(date(2024, 1, 2), "594.00", 41_393_088, source="twse")]
    rows = vmd.compare_bars("2330", primary, [])
    assert len(rows) == 1
    assert rows[0].verdict is vmd.Verdict.FAIL
    assert "缺少此日資料" in rows[0].note


# --------------------------------------------------------------------------
# scan_demo_synthetic (local SQLite, genuinely no network involved)
# --------------------------------------------------------------------------


def test_scan_demo_synthetic_missing_file_reports_clean_zero() -> None:
    report = vmd.scan_demo_synthetic(Path("/nonexistent/path/does-not-exist.db"))
    assert report.exists is False
    assert report.error == "檔案不存在"
    assert report.total_bars == 0


def test_scan_demo_synthetic_computes_ratio(tmp_path: Path) -> None:
    db_path = tmp_path / "scan-test.db"
    cache = PriceBarCache(db_path=db_path)
    real_bar = _bar(date(2024, 1, 2), "594.00", 41_393_088, source="twse")
    demo_bars = [
        _bar(date(2024, 1, 3), "100.00", 1_000, source="demo_synthetic"),
        _bar(date(2024, 1, 4), "101.00", 1_000, source="demo_synthetic"),
        _bar(date(2024, 1, 5), "102.00", 1_000, source="demo_synthetic"),
    ]
    cache.put([real_bar], source="twse")
    cache.put(demo_bars, source="demo_synthetic")

    store = PositionStore(db_path=db_path)
    store.create(
        PositionInput(
            symbol="2330",
            market="TW",
            quantity="100",
            avg_cost="590",
            currency="TWD",
            instrument_type="stock",
            note="[demo_synthetic] 示範持倉",
        )
    )
    store.create(
        PositionInput(
            symbol="0050",
            market="TW",
            quantity="10",
            avg_cost="150",
            currency="TWD",
            instrument_type="etf",
            note=None,
        )
    )

    report = vmd.scan_demo_synthetic(db_path)
    assert report.exists is True
    assert report.error is None
    assert report.total_bars == 4
    assert report.demo_bars == 3
    assert report.demo_ratio == pytest.approx(0.75)
    assert report.total_positions == 2
    assert report.demo_positions == 1


# --------------------------------------------------------------------------
# check_leverage_registry (local Python data, no network)
# --------------------------------------------------------------------------


def test_check_leverage_registry_matches_known_registry_size() -> None:
    report = vmd.check_leverage_registry()
    assert report.total == len(KNOWN_LEVERAGED_ETF)
    assert len(report.rows) == report.total
    # Every current entry is unverified per app/leverage/detect.py's provenance
    # notice -- this assertion will correctly start failing (a good thing) the
    # day data-engineer verifies a row against the issuer prospectus.
    assert report.verified_count == 0
    # None of the hand-authored rows should trip the structural sanity bounds.
    assert report.structural_issue_count == 0


# --------------------------------------------------------------------------
# End-to-end: run() through main(), fully offline via one shared MockTransport
# --------------------------------------------------------------------------


def _offline_transport() -> httpx.MockTransport:
    twse_payload = _fixture_json("twse_stock_day_2330_202401.json")
    tpex_payload = _fixture_json("tpex_daily_trading_5483_202401.json")
    finmind_payload = _fixture_json("finmind_taiwan_stock_price_2330.json")
    fx_csv = _fixture_text("bot_fx_usd_twd_20240102.csv")
    av_payload = _fixture_json("alpha_vantage_daily_aapl.json")
    yf_payload = _fixture_json("yfinance_chart_twii.json")

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        path = request.url.path
        if host == "www.twse.com.tw":
            if path == "/exchangeReport/STOCK_DAY":
                return httpx.Response(200, json=twse_payload)
            return httpx.Response(200, text="reachable")
        if host == "openapi.twse.com.tw":
            return httpx.Response(200, text="reachable")
        if host == "www.tpex.org.tw":
            if path.endswith("st43_result.php"):
                return httpx.Response(200, json=tpex_payload)
            return httpx.Response(200, text="reachable")
        if host == "api.finmindtrade.com":
            return httpx.Response(200, json=finmind_payload)
        if host == "rate.bot.com.tw":
            if path.startswith("/xrt/flcsv/"):
                return httpx.Response(200, text=fx_csv)
            return httpx.Response(200, text="reachable")
        if host == "www.alphavantage.co":
            return httpx.Response(200, json=av_payload)
        if host == "query1.finance.yahoo.com":
            return httpx.Response(200, json=yf_payload)
        raise AssertionError(f"unmapped host in offline test transport: {host}")

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _credentials_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(vmd.FINMIND_TOKEN_ENV_VAR, "fixture-test-token-not-real")
    monkeypatch.setenv(vmd.ALPHA_VANTAGE_API_KEY_ENV_VAR, "fixture-test-key-not-real")
    monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "25")
    monkeypatch.setenv(SAFETY_MARGIN_ENV_VAR, "0")


def test_run_end_to_end_all_pass_offline(tmp_path: Path) -> None:
    db_path = tmp_path / "scan.db"
    PriceBarCache(db_path=db_path).put(
        [_bar(date(2024, 1, 2), "594.00", 41_393_088, source="demo_synthetic")],
        source="demo_synthetic",
    )
    args = vmd.CliArgs(
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        tw_symbols=["2330"],
        tpex_symbol="5483",
        us_symbol="AAPL",
        fx_pair="USDTWD",
        index_symbol="^TWII",
        db_paths=[db_path],
        output=tmp_path / "report.md",
        timeout=5.0,
    )

    result = vmd.run(args, transport=_offline_transport())

    verdicts = {r.name: r.verdict for r in result.adapter_results}
    assert verdicts == {
        "twse": vmd.Verdict.PASS,
        "tpex": vmd.Verdict.PASS,
        "finmind": vmd.Verdict.PASS,
        "bank_of_taiwan_fx": vmd.Verdict.PASS,
        "alpha_vantage": vmd.Verdict.PASS,
        "yfinance": vmd.Verdict.PASS,
    }
    assert result.comparisons["2330"]
    assert all(row.verdict is vmd.Verdict.PASS for row in result.comparisons["2330"])
    assert "demo_synthetic" in result.markdown
    assert "100.0%" in result.markdown  # the single-row demo DB above is 100% synthetic


def test_main_writes_report_file_and_returns_zero_on_all_pass(tmp_path: Path) -> None:
    output_path = tmp_path / "驗證結果-test.md"
    db_path = tmp_path / "empty.db"
    argv = [
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--tw-symbols",
        "2330",
        "--tpex-symbol",
        "5483",
        "--us-symbol",
        "AAPL",
        "--index-symbol",
        "^TWII",
        "--db-path",
        str(db_path),
        "--output",
        str(output_path),
        "--timeout",
        "5",
    ]

    exit_code = vmd.main(argv, transport=_offline_transport())

    assert exit_code == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "Stock Desk 數據源驗證結果" in content
    assert "六個 adapter 皆為 PASS" in content


def test_main_returns_nonzero_when_a_source_is_unreachable(tmp_path: Path) -> None:
    """A transport that only answers TWSE simulates a partially-blocked network."""

    twse_payload = _fixture_json("twse_stock_day_2330_202401.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.twse.com.tw" and request.url.path == "/exchangeReport/STOCK_DAY":
            return httpx.Response(200, json=twse_payload)
        raise httpx.ConnectError("blocked", request=request)

    output_path = tmp_path / "report.md"
    argv = [
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-03",
        "--db-path",
        str(tmp_path / "empty.db"),
        "--output",
        str(output_path),
        "--timeout",
        "1",
    ]

    exit_code = vmd.main(argv, transport=httpx.MockTransport(handler))

    assert exit_code == 1
    content = output_path.read_text(encoding="utf-8")
    assert "UNREACHABLE" in content
