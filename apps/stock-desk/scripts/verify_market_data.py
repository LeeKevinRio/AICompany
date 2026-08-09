"""CEO 本機一鍵核實工具 -- stock-desk 六個市場資料 adapter 的真實連線驗證。

## 背景

`work/research/2026-08-09-stock-desk數據核實.md` 判定「資料源從未真實驗證」為
上線前致命缺口：本雲端開發環境的 egress policy 擋掉所有財經網域（TWSE、
TPEx、FinMind、台灣銀行、Alpha Vantage、Yahoo Finance），所以每個 adapter
的檔頭都寫著「依文件手工構造，未對照真實回應驗證」。這支工具就是讓 **有網路
的機器**（多半是 CEO 本機）能一次把該報告第 4.5 節 checklist 中「可自動化」
的項目都跑過一遍，產出可留存、可交回 data-engineer / qa-e2e 的驗證紀錄。

## 3 步驟開始使用

1. 準備憑證（可選，缺的來源會如實回報 FAIL，不會讓整個工具中斷）：
   ```bash
   export FINMIND_API_TOKEN=...        # FinMind 備援來源
   export ALPHA_VANTAGE_API_KEY=...    # Alpha Vantage 美股主來源
   export ALPHA_VANTAGE_DAILY_LIMIT=25 # 依 Alpha Vantage 當下方案填寫，非本工具臆測
   ```
2. 進入 backend 目錄，用專案既有的 uv 虛擬環境執行（沿用 `app.*` 的匯入路徑）：
   ```bash
   cd apps/stock-desk/backend
   uv run python ../scripts/verify_market_data.py
   ```
3. 看終端摘要，完整報告會寫到
   `work/research/驗證結果-<今天日期>.md`（也可用 `--output` 指定路徑）。

常用參數：`--tw-symbols 2330,0050,00631L,5483,2317`（抽樣標的，逗號分隔，
預設 `2330,0050,00631L`）、`--start`/`--end`（ISO 日期，預設抓最近約 10 個
日曆天，涵蓋至少 3 個交易日）、`--db-path`（可重複，追加要掃描 demo_synthetic
佔比的 SQLite 檔）。`--help` 看全部參數。

## 這支工具做什麼、不做什麼

做：
- 對 6 個既有 adapter（twse / tpex / finmind / bank_of_taiwan fx / alpha_vantage /
  yfinance）各打一次真實請求，用 PASS / FAIL / UNREACHABLE 三態分類：
  - `UNREACHABLE`：連線層失敗（DNS、逾時、連線被拒、proxy 擋下），代表這台機器
    根本連不到對方網域。
  - `FAIL`：連得到，但沒拿到可用資料（缺憑證、schema 不符、額度用罄、代號查無
    資料等），細節寫在 `detail` 欄位。
  - `PASS`：拿到至少一筆真實資料。
- 額外對 TWSE OpenAPI（`openapi.twse.com.tw`）與 TPEx OpenAPI
  （`tpex.org.tw/openapi`）根網域做輕量連線探測 -- 只探測「連不連得到」，
  不臆測其資料集路徑 schema（本工具不熟悉這兩個新端點的確切規格，落地前仍需
  data-engineer 依官方文件另行設計 adapter；ADR-0002 checklist 第 2 項）。
- 用「主來源（TWSE/TPEx STOCK_DAY，checklist 稱之為官方基準）vs. 備援來源
  （FinMind）」對同一批標的、同一段日期做逐筆比對，零容差（收盤價與成交量
  完全相等才算一致），藉此驗證兩個獨立資料管線是否互相印證 -- 這是本工具
  能做到、最接近「與 TWSE 官方數字核對」的自動化方式；若要肉眼核對 TWSE
  官網頁面本身，報告內會附上每一列的官方查詢頁 URL 供人工點開比對。
- 讀本機 SQLite（`price_bars_cache`、`positions`）算出 `demo_synthetic` 佔比
  -- 這一項不需要網路，在任何環境都能跑真的。
- 對槓桿 ETF 註冊表（`app.leverage.detect.KNOWN_LEVERAGED_ETF`）做結構性檢查
  （倍數/費用率是否落在常見範圍、`verified` 旗標統計）-- 同樣不需要網路。

不做（紅線 / 能力邊界）：
- 不會去抓發行人公開說明書 PDF 解析倍數/費用率 -- 沒有穩定的結構化 API，
  硬做只會是另一種「憑記憶寫死規格」，違反 data-engineer 紅線。報告會列出
  每一檔的發行人名稱，交 CEO 或 tech-writer 人工核對 PDF 後把
  `verified` 改 `True`。
- 不會把任何祕密寫進程式碼或報告 -- 憑證一律從環境變數讀，報告只記錄「有/無
  設定」。
- 不會改動任何既有 adapter 的行為；本工具只是呼叫既有的
  `app.data.providers.*` 類別，用真正的網路 transport（CEO 本機執行時）或
  測試用的 `httpx.MockTransport`（本倉庫的離線單元測試）。

## 測試

`apps/stock-desk/backend/tests/test_verify_market_data.py` 用既有的
`tests/fixtures/*` 合成 fixture（跟其他 adapter 契約測試共用同一批檔案）對
本模組的分類邏輯、比對邏輯、demo_synthetic 統計、槓桿註冊表檢查做離線驗證，
一律不打外網：

```bash
cd apps/stock-desk/backend
uv run pytest tests/test_verify_market_data.py -v
```
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

import httpx

# --------------------------------------------------------------------------
# Make ``app.*`` importable regardless of cwd / interpreter. When this script
# is run through the backend's uv-managed venv the package is already
# editable-installed, so this is a harmless no-op fallback in that case.
# --------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_STOCK_DESK_DIR = _SCRIPT_DIR.parent
_BACKEND_DIR = _STOCK_DESK_DIR / "backend"
_REPO_ROOT = _STOCK_DESK_DIR.parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ruff: noqa: E402  -- these must come after the sys.path bootstrap above.
import app.data.providers.alpha_vantage as _alpha_vantage_mod
import app.data.providers.finmind as _finmind_mod
from app.data.cache import DEFAULT_DB_PATH, resolve_db_path
from app.data.http import RateLimitedClient
from app.data.interface import DataStatus, PriceBar
from app.data.providers.alpha_vantage import ALPHA_VANTAGE_BASE_URL, AlphaVantageAdapter
from app.data.providers.finmind import FINMIND_BASE_URL, FinMindAdapter
from app.data.providers.fx import BOT_BASE_URL, BankOfTaiwanFxAdapter
from app.data.providers.tpex import TPEX_BASE_URL, TpexAdapter
from app.data.providers.twse import TWSE_BASE_URL, TwseAdapter
from app.data.providers.yfinance import YFINANCE_BASE_URL, YFinanceAdapter
from app.data.quota import QuotaLedger
from app.leverage.detect import KNOWN_LEVERAGED_ETF, REGISTRY_VERIFIED_ON

#: Credential env var names, referenced by name rather than re-exported
#: constants (ruff dislikes ``X as Y`` aliasing at module scope here) --
#: kept as module attribute lookups so a rename in the source adapter still
#: surfaces here instead of silently drifting.
ALPHA_VANTAGE_API_KEY_ENV_VAR = _alpha_vantage_mod.API_KEY_ENV_VAR
FINMIND_TOKEN_ENV_VAR = _finmind_mod.TOKEN_ENV_VAR

# --------------------------------------------------------------------------
# Shared vocabulary
# --------------------------------------------------------------------------


class Verdict(StrEnum):
    """The three-state outcome the dispatch order requires for every check."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNREACHABLE = "UNREACHABLE"


#: Bonus reachability-only probes for the OpenAPI migration targets flagged
#: in the market-researcher report (4.1/4.2) -- root pages only, never a
#: specific dataset path, so this never guesses an unverified endpoint shape.
BONUS_REACHABILITY_TARGETS: tuple[tuple[str, str], ...] = (
    ("twse_openapi_root", "https://openapi.twse.com.tw/"),
    ("tpex_openapi_root", "https://www.tpex.org.tw/openapi/"),
)


# --------------------------------------------------------------------------
# Reachability
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ReachabilityResult:
    reachable: bool
    detail: str


def _default_http_get(
    url: str, timeout: float, *, transport: httpx.BaseTransport | None = None
) -> httpx.Response:
    with httpx.Client(timeout=timeout, transport=transport) as client:
        return client.get(url, follow_redirects=True)


def check_reachability(
    url: str,
    *,
    timeout: float = 8.0,
    get_fn: Callable[[str, float], httpx.Response] | None = None,
) -> ReachabilityResult:
    """Probe whether ``url`` is reachable at all (TCP+TLS+HTTP round trip).

    Any HTTP status code (even 403/404) counts as "reachable" -- it means the
    connection layer worked. Only ``httpx.TransportError`` (DNS failure,
    connection refused, proxy CONNECT rejection, timeout, ...) means
    ``UNREACHABLE``.
    """
    getter = get_fn or _default_http_get
    try:
        response = getter(url, timeout)
    except httpx.TransportError as exc:
        return ReachabilityResult(
            reachable=False, detail=f"連線失敗（{exc.__class__.__name__}）：{exc}"
        )
    return ReachabilityResult(reachable=True, detail=f"HTTP {response.status_code}")


# --------------------------------------------------------------------------
# Adapter probes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AdapterProbeResult:
    name: str
    endpoint: str
    verdict: Verdict
    detail: str
    record_count: int
    as_of: datetime | None
    sample_bars: tuple[PriceBar, ...] = field(default_factory=tuple)


def classify_result(
    *,
    name: str,
    endpoint: str,
    credential_ok: bool,
    credential_hint: str,
    reachability: ReachabilityResult | None,
    bars: Sequence[PriceBar],
    status: DataStatus | None,
    reason: str | None,
    as_of: datetime | None,
) -> AdapterProbeResult:
    """Turn one adapter call's raw outcome into a PASS/FAIL/UNREACHABLE verdict."""
    if not credential_ok:
        return AdapterProbeResult(
            name=name,
            endpoint=endpoint,
            verdict=Verdict.FAIL,
            detail=f"缺少必要憑證環境變數：{credential_hint}（未嘗試發出請求）",
            record_count=0,
            as_of=None,
        )
    if reachability is not None and not reachability.reachable:
        return AdapterProbeResult(
            name=name,
            endpoint=endpoint,
            verdict=Verdict.UNREACHABLE,
            detail=reachability.detail,
            record_count=0,
            as_of=None,
        )
    if bars:
        return AdapterProbeResult(
            name=name,
            endpoint=endpoint,
            verdict=Verdict.PASS,
            detail=f"取得 {len(bars)} 筆資料，status={status}",
            record_count=len(bars),
            as_of=as_of,
            sample_bars=tuple(bars[:3]),
        )
    detail = reason or (f"status={status}，回應中無可用資料" if status else "無可用資料")
    return AdapterProbeResult(
        name=name,
        endpoint=endpoint,
        verdict=Verdict.FAIL,
        detail=detail,
        record_count=0,
        as_of=as_of,
    )


def _make_client(
    base_url: str,
    min_interval_seconds: float,
    *,
    transport: httpx.BaseTransport | None,
) -> RateLimitedClient:
    if transport is None:
        return RateLimitedClient(base_url=base_url, min_interval_seconds=min_interval_seconds)
    return RateLimitedClient(
        base_url=base_url,
        min_interval_seconds=min_interval_seconds,
        transport=transport,
        sleep_fn=lambda _seconds: None,
    )


def probe_twse(
    symbol: str,
    start: date,
    end: date,
    *,
    transport: httpx.BaseTransport | None = None,
    reachability: ReachabilityResult | None = None,
) -> AdapterProbeResult:
    client = _make_client(TWSE_BASE_URL, 0.5, transport=transport)
    adapter = TwseAdapter(client=client)
    try:
        result = adapter.get_daily_bars(symbol, start, end)
    finally:
        adapter.close()
    return classify_result(
        name="twse",
        endpoint=f"{TWSE_BASE_URL}/exchangeReport/STOCK_DAY",
        credential_ok=True,
        credential_hint="",
        reachability=reachability,
        bars=result.bars,
        status=result.status,
        reason=result.reason,
        as_of=result.as_of,
    )


def probe_tpex(
    symbol: str,
    start: date,
    end: date,
    *,
    transport: httpx.BaseTransport | None = None,
    reachability: ReachabilityResult | None = None,
) -> AdapterProbeResult:
    client = _make_client(TPEX_BASE_URL, 0.5, transport=transport)
    adapter = TpexAdapter(client=client)
    try:
        result = adapter.get_daily_bars(symbol, start, end)
    finally:
        adapter.close()
    return classify_result(
        name="tpex",
        endpoint=f"{TPEX_BASE_URL}/web/stock/aftertrading/daily_trading_info/st43_result.php",
        credential_ok=True,
        credential_hint="",
        reachability=reachability,
        bars=result.bars,
        status=result.status,
        reason=result.reason,
        as_of=result.as_of,
    )


def probe_finmind(
    symbol: str,
    start: date,
    end: date,
    *,
    transport: httpx.BaseTransport | None = None,
    reachability: ReachabilityResult | None = None,
) -> AdapterProbeResult:
    credential_ok = bool(os.environ.get(FINMIND_TOKEN_ENV_VAR))
    client = _make_client(FINMIND_BASE_URL, 0.3, transport=transport)
    adapter = FinMindAdapter(client=client)
    try:
        result = adapter.get_daily_bars(symbol, start, end)
    finally:
        adapter.close()
    return classify_result(
        name="finmind",
        endpoint=f"{FINMIND_BASE_URL}/api/v4/data?dataset=TaiwanStockPrice",
        credential_ok=credential_ok,
        credential_hint=FINMIND_TOKEN_ENV_VAR,
        reachability=reachability,
        bars=result.bars,
        status=result.status,
        reason=result.reason,
        as_of=result.as_of,
    )


def probe_fx(
    pair: str,
    start: date,
    end: date,
    *,
    transport: httpx.BaseTransport | None = None,
    reachability: ReachabilityResult | None = None,
) -> AdapterProbeResult:
    client = _make_client(BOT_BASE_URL, 0.5, transport=transport)
    adapter = BankOfTaiwanFxAdapter(client=client)
    try:
        result = adapter.get_daily_rates(pair, start, end)
    finally:
        adapter.close()
    # FxRateResult carries the same fields as ProviderResult minus `reason`;
    # PriceBar-shaped classify_result() is reused by treating rates as bars.
    return classify_result(
        name="bank_of_taiwan_fx",
        endpoint=f"{BOT_BASE_URL}/xrt/flcsv/0/<date>",
        credential_ok=True,
        credential_hint="",
        reachability=reachability,
        bars=result.rates,  # type: ignore[arg-type]
        status=result.status,
        reason=None,
        as_of=result.as_of,
    )


def probe_alpha_vantage(
    symbol: str,
    start: date,
    end: date,
    *,
    transport: httpx.BaseTransport | None = None,
    reachability: ReachabilityResult | None = None,
) -> AdapterProbeResult:
    credential_ok = bool(os.environ.get(ALPHA_VANTAGE_API_KEY_ENV_VAR))
    client = _make_client(ALPHA_VANTAGE_BASE_URL, 0.0, transport=transport)
    # Disposable, file-backed ledger in a throwaway temp dir: this diagnostic
    # run must never spend a slot out of the CEO's real, persisted daily
    # quota counter. A plain ``:memory:`` path will not do here -- QuotaLedger
    # opens a fresh sqlite3 connection per call, and every ``:memory:``
    # connection is its own independent, disconnected database.
    with tempfile.TemporaryDirectory(prefix="stock-desk-verify-quota-") as tmp_dir:
        ledger = QuotaLedger(db_path=Path(tmp_dir) / "diagnostic-quota.db")
        adapter = AlphaVantageAdapter(client=client, ledger=ledger)
        try:
            result = adapter.get_daily_bars(symbol, start, end)
        finally:
            adapter.close()
    return classify_result(
        name="alpha_vantage",
        endpoint=f"{ALPHA_VANTAGE_BASE_URL}/query?function=TIME_SERIES_DAILY",
        credential_ok=credential_ok,
        credential_hint=ALPHA_VANTAGE_API_KEY_ENV_VAR,
        reachability=reachability,
        bars=result.bars,
        status=result.status,
        reason=result.reason,
        as_of=result.as_of,
    )


def probe_yfinance_index(
    index_symbol: str,
    start: date,
    end: date,
    *,
    transport: httpx.BaseTransport | None = None,
    reachability: ReachabilityResult | None = None,
) -> AdapterProbeResult:
    client = _make_client(YFINANCE_BASE_URL, 1.0, transport=transport)
    adapter = YFinanceAdapter(client=client)
    try:
        result = adapter.get_index_daily_bars(index_symbol, start, end)
    finally:
        adapter.close()
    return classify_result(
        name="yfinance",
        endpoint=f"{YFINANCE_BASE_URL}/v8/finance/chart/{index_symbol}",
        credential_ok=True,
        credential_hint="",
        reachability=reachability,
        bars=result.bars,
        status=result.status,
        reason=result.reason,
        as_of=result.as_of,
    )


# --------------------------------------------------------------------------
# Zero-tolerance cross-source comparison (checklist 1 / 3 / 6)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ComparisonRow:
    symbol: str
    trade_date: date
    primary_close: Decimal | None
    backup_close: Decimal | None
    primary_volume: int | None
    backup_volume: int | None
    verdict: Verdict
    note: str


def compare_bars(
    symbol: str,
    primary_bars: Sequence[PriceBar],
    backup_bars: Sequence[PriceBar],
) -> list[ComparisonRow]:
    """Zero-tolerance close-price/volume comparison between two independent feeds.

    ``primary_bars`` is the exchange-direct feed (TWSE/TPEx STOCK_DAY, the
    checklist's "官方基準"); ``backup_bars`` is FinMind. Exact ``Decimal``/
    ``int`` equality is required for a PASS -- no rounding, no tolerance
    band, per the dispatch order's "零容差" requirement.
    """
    primary_by_date = {bar.date: bar for bar in primary_bars}
    backup_by_date = {bar.date: bar for bar in backup_bars}
    rows: list[ComparisonRow] = []
    for trade_date in sorted(set(primary_by_date) | set(backup_by_date)):
        primary = primary_by_date.get(trade_date)
        backup = backup_by_date.get(trade_date)
        if primary is None or backup is None:
            missing = "主來源" if primary is None else "備援來源"
            rows.append(
                ComparisonRow(
                    symbol=symbol,
                    trade_date=trade_date,
                    primary_close=primary.close if primary else None,
                    backup_close=backup.close if backup else None,
                    primary_volume=primary.volume if primary else None,
                    backup_volume=backup.volume if backup else None,
                    verdict=Verdict.FAIL,
                    note=f"{missing}缺少此日資料，無法比對",
                )
            )
            continue
        close_match = primary.close == backup.close
        volume_match = primary.volume == backup.volume
        if close_match and volume_match:
            rows.append(
                ComparisonRow(
                    symbol=symbol,
                    trade_date=trade_date,
                    primary_close=primary.close,
                    backup_close=backup.close,
                    primary_volume=primary.volume,
                    backup_volume=backup.volume,
                    verdict=Verdict.PASS,
                    note="一致",
                )
            )
            continue
        notes: list[str] = []
        if not close_match:
            notes.append(f"收盤價不同：{primary.close} vs {backup.close}")
        if not volume_match:
            unit_hint = ""
            if primary.volume and backup.volume:
                ratio = backup.volume / primary.volume
                if abs(ratio - 1000) < 50 or (ratio and abs(1 / ratio - 1000) < 50):
                    unit_hint = "（數量級接近 1000 倍，疑似股／張單位不一致，checklist 第 4 項）"
            notes.append(f"成交量不同：{primary.volume} vs {backup.volume}{unit_hint}")
        rows.append(
            ComparisonRow(
                symbol=symbol,
                trade_date=trade_date,
                primary_close=primary.close,
                backup_close=backup.close,
                primary_volume=primary.volume,
                backup_volume=backup.volume,
                verdict=Verdict.FAIL,
                note="；".join(notes),
            )
        )
    return rows


# --------------------------------------------------------------------------
# demo_synthetic ratio (local SQLite, no network -- runs anywhere)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoSyntheticReport:
    db_path: Path
    exists: bool
    error: str | None
    total_bars: int
    demo_bars: int
    demo_ratio: float
    total_positions: int
    demo_positions: int


def scan_demo_synthetic(db_path: Path) -> DemoSyntheticReport:
    """Report how much of ``db_path``'s cached data is offline demo output.

    Read-only: never mutates the database. Missing file/tables are reported
    as a clean zero-row result, never fabricated as "0% synthetic" (that
    would be a false confidence signal) -- ``exists``/``error`` distinguish
    "genuinely empty" from "could not be inspected".
    """
    if not db_path.exists():
        return DemoSyntheticReport(
            db_path=db_path,
            exists=False,
            error="檔案不存在",
            total_bars=0,
            demo_bars=0,
            demo_ratio=0.0,
            total_positions=0,
            demo_positions=0,
        )

    total_bars = demo_bars = total_positions = demo_positions = 0
    notes: list[str] = []
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
            cursor = conn.cursor()
            # Two independent try blocks on purpose: a DB missing one table
            # (e.g. a cache-only file) must not hide stats the other table
            # *did* yield -- a blanket failure here would be a worse, more
            # silent lie than reporting "this half could not be read".
            try:
                total_bars = _scalar(cursor, "SELECT COUNT(*) FROM price_bars_cache")
                demo_bars = _scalar(
                    cursor,
                    "SELECT COUNT(*) FROM price_bars_cache WHERE source = 'demo_synthetic'",
                )
            except sqlite3.Error as exc:
                notes.append(f"price_bars_cache 讀取失敗：{exc}")
            try:
                total_positions = _scalar(cursor, "SELECT COUNT(*) FROM positions")
                demo_positions = _scalar(
                    cursor,
                    "SELECT COUNT(*) FROM positions WHERE note LIKE '[demo_synthetic]%'",
                )
            except sqlite3.Error as exc:
                notes.append(f"positions 讀取失敗：{exc}")
    except sqlite3.Error as exc:
        return DemoSyntheticReport(
            db_path=db_path,
            exists=True,
            error=str(exc),
            total_bars=0,
            demo_bars=0,
            demo_ratio=0.0,
            total_positions=0,
            demo_positions=0,
        )
    ratio = (demo_bars / total_bars) if total_bars else 0.0
    return DemoSyntheticReport(
        db_path=db_path,
        exists=True,
        error="；".join(notes) or None,
        total_bars=total_bars,
        demo_bars=demo_bars,
        demo_ratio=ratio,
        total_positions=total_positions,
        demo_positions=demo_positions,
    )


def _scalar(cursor: sqlite3.Cursor, sql: str) -> int:
    cursor.execute(sql)
    row = cursor.fetchone()
    return int(row[0]) if row else 0


# --------------------------------------------------------------------------
# Leveraged-ETF registry structural check (no network -- runs anywhere)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LeverageRegistryRow:
    symbol: str
    leverage_factor: float
    expense_ratio_annual: float
    verified: bool
    issuer_note: str
    structural_issue: str | None


@dataclass(frozen=True)
class LeverageRegistryReport:
    registry_verified_on: str | None
    rows: tuple[LeverageRegistryRow, ...]
    total: int
    verified_count: int
    structural_issue_count: int


def check_leverage_registry() -> LeverageRegistryReport:
    """Structural sanity pass over the leveraged-ETF registry.

    This does **not** verify leverage factors / expense ratios against the
    issuer's prospectus (no reliable structured API exists for that -- see
    module docstring); it only catches obviously-broken data (zero/absurd
    leverage factor, out-of-range expense ratio) and tallies how many rows
    still carry ``verified=False``.
    """
    rows: list[LeverageRegistryRow] = []
    verified_count = 0
    for symbol, meta in sorted(KNOWN_LEVERAGED_ETF.items()):
        issue: str | None = None
        if meta.leverage_factor == 0:
            issue = "leverage_factor 為 0，結構不合理"
        elif not (-5.0 <= meta.leverage_factor <= 5.0):
            issue = f"leverage_factor={meta.leverage_factor:g} 超出常見槓桿倍數範圍 [-5, 5]"
        elif not (0.0 <= meta.expense_ratio_annual <= 0.05):
            issue = (
                f"expense_ratio_annual={meta.expense_ratio_annual:.4f} "
                "超出常見年費率範圍 [0, 0.05]"
            )
        if meta.verified:
            verified_count += 1
        rows.append(
            LeverageRegistryRow(
                symbol=symbol,
                leverage_factor=meta.leverage_factor,
                expense_ratio_annual=meta.expense_ratio_annual,
                verified=meta.verified,
                issuer_note=meta.source_note,
                structural_issue=issue,
            )
        )
    return LeverageRegistryReport(
        registry_verified_on=REGISTRY_VERIFIED_ON,
        rows=tuple(rows),
        total=len(rows),
        verified_count=verified_count,
        structural_issue_count=sum(1 for row in rows if row.structural_issue),
    )


# --------------------------------------------------------------------------
# Report rendering
# --------------------------------------------------------------------------

_MANUAL_TWSE_STOCK_DAY_URL = (
    "https://www.twse.com.tw/zh/trading/historical/stock-day.html?stockNo={symbol}"
)


def _verdict_badge(verdict: Verdict) -> str:
    return {"PASS": "PASS", "FAIL": "FAIL", "UNREACHABLE": "UNREACHABLE"}[verdict.value]


def render_report(
    *,
    generated_at: datetime,
    start: date,
    end: date,
    adapter_results: Sequence[AdapterProbeResult],
    bonus_reachability: Sequence[tuple[str, str, ReachabilityResult]],
    comparisons: dict[str, list[ComparisonRow]],
    demo_reports: Sequence[DemoSyntheticReport],
    leverage_report: LeverageRegistryReport,
) -> str:
    lines: list[str] = []
    lines.append("# Stock Desk 數據源驗證結果")
    lines.append("")
    lines.append(f"- **執行時間（UTC）**：{generated_at.isoformat()}")
    lines.append("- **執行工具**：`apps/stock-desk/scripts/verify_market_data.py`")
    lines.append(f"- **抽樣區間**：{start.isoformat()} ~ {end.isoformat()}")
    lines.append(
        "- **對應 checklist**：`work/research/2026-08-09-stock-desk數據核實.md` 第 4.5 節"
        " 第 1、2、3、4、6、8、9 項（第 5、7、10 項需人工判斷/文案上線，不在本工具範圍）"
    )
    lines.append("")

    lines.append("## 1. 六個 adapter 真實連線結果（checklist 第 1 項）")
    lines.append("")
    lines.append("| Adapter | Endpoint | 結果 | 細節 | 筆數 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for result in adapter_results:
        lines.append(
            f"| {result.name} | `{result.endpoint}` | **{_verdict_badge(result.verdict)}** "
            f"| {result.detail} | {result.record_count} |"
        )
    lines.append("")
    if bonus_reachability:
        lines.append("### 1.1 額外連線探測（OpenAPI 遷移路線，checklist 第 2 項）")
        lines.append("")
        lines.append("| 目標 | URL | 可連線 | 細節 |")
        lines.append("| --- | --- | --- | --- |")
        for name, url, reach in bonus_reachability:
            lines.append(f"| {name} | `{url}` | {reach.reachable} | {reach.detail} |")
        lines.append("")
        lines.append(
            "> 這兩項只探測根網域連線，不代表已驗證特定資料集路徑；"
            "TPEx legacy 端點若在第 1 節顯示 UNREACHABLE/FAIL，"
            "且這裡 `tpex_openapi_root` 顯示可連線，代表應改接 TPEx OpenAPI"
            "（checklist 第 2 項的行動判準）。"
        )
        lines.append("")

    lines.append("## 2. 主來源 vs FinMind 逐筆比對，零容差（checklist 第 3、4、6 項）")
    lines.append("")
    if not comparisons:
        lines.append("（未設定抽樣標的）")
    for symbol, rows in comparisons.items():
        lines.append(f"### {symbol}")
        lines.append("")
        manual_url = _MANUAL_TWSE_STOCK_DAY_URL.format(symbol=symbol)
        lines.append(f"人工核對連結（TWSE 官方歷史股價頁面）：{manual_url}")
        lines.append("")
        if not rows:
            lines.append("（雙邊皆無資料可比對，見上方 adapter 結果）")
            lines.append("")
            continue
        lines.append(
            "| 日期 | 主來源收盤 | FinMind 收盤 | 主來源成交量 | FinMind 成交量 | 結果 | 備註 |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for row in rows:
            lines.append(
                f"| {row.trade_date.isoformat()} | {row.primary_close} | {row.backup_close} "
                f"| {row.primary_volume} | {row.backup_volume} "
                f"| **{_verdict_badge(row.verdict)}** | {row.note} |"
            )
        lines.append("")

    lines.append("## 3. demo_synthetic 資料佔比（checklist 第 9 項，純本機讀取）")
    lines.append("")
    lines.append(
        "| DB 檔 | 狀態 | price_bars_cache 總筆數 | demo_synthetic 筆數 | 佔比 "
        "| positions 總筆數 | 帶示範標記筆數 |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for report in demo_reports:
        if not report.exists:
            lines.append(f"| `{report.db_path}` | 檔案不存在 | - | - | - | - | - |")
            continue
        status = f"部分讀取失敗：{report.error}" if report.error else "OK"
        lines.append(
            f"| `{report.db_path}` | {status} | {report.total_bars} | {report.demo_bars} "
            f"| {report.demo_ratio:.1%} | {report.total_positions} | {report.demo_positions} |"
        )
    lines.append("")
    lines.append(
        "> 佔比 100% 代表該 DB 目前完全沒有真實行情，只有離線示範資料——"
        "這是本工具唯一能誠實回報的狀態，不代表資料錯誤，代表尚未有真實資料寫入。"
    )
    lines.append("")

    lines.append("## 4. 槓桿 ETF 註冊表結構檢查（checklist 第 8 項，純本機檢查）")
    lines.append("")
    lines.append(
        f"註冊表 `verified_on`：{leverage_report.registry_verified_on or '（尚未查證，None）'}；"
        f"共 {leverage_report.total} 筆，其中 {leverage_report.verified_count} 筆已標記 verified，"
        f"{leverage_report.structural_issue_count} 筆有結構性疑慮。"
    )
    lines.append("")
    lines.append("| 代號 | 倍數 | 年費率 | verified | 結構檢查 | 發行人（供人工比對公開說明書） |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for registry_row in leverage_report.rows:
        issue = registry_row.structural_issue or "OK"
        lines.append(
            f"| {registry_row.symbol} | {registry_row.leverage_factor:g} "
            f"| {registry_row.expense_ratio_annual:.4f} | {registry_row.verified} | {issue} "
            f"| {registry_row.issuer_note} |"
        )
    lines.append("")
    lines.append(
        "> 本工具不會自動抓取/解析發行人 PDF；上表僅做「數字有沒有明顯壞掉」的結構檢查。"
        "要把 `verified` 從 False 改 True，仍需人工對照發行人公開說明書，交 data-engineer 更新"
        "`app/leverage/detect.py` 並填上 `REGISTRY_VERIFIED_ON`。"
    )
    lines.append("")

    lines.append("## 5. 尚未自動化、仍需人工的 checklist 項目")
    lines.append("")
    lines.append("- 第 5 項：除權息日跨日抽測（需挑選近期除息股，人工核對是否為未還原價）。")
    lines.append("- 第 7 項：台銀 FX 揭露文案是否已上線（文案審查，非資料驗證）。")
    lines.append("- 第 10 項：驗證紀錄需附可觀測證據（本報告即為紀錄，仍建議另存後端 log／截圖）。")
    lines.append("")

    overall_fail = any(r.verdict is not Verdict.PASS for r in adapter_results)
    lines.append("## 6. 總結")
    lines.append("")
    if overall_fail:
        lines.append(
            "**尚有 adapter 未達 PASS。** 上線前不得宣稱資料源已驗證，"
            "請依上表逐一排除 FAIL/UNREACHABLE 後重跑本工具。"
        )
    else:
        lines.append("六個 adapter 皆為 PASS，比對表亦無 FAIL——資料源真實性驗證通過。")
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CliArgs:
    start: date
    end: date
    tw_symbols: list[str]
    tpex_symbol: str
    us_symbol: str
    fx_pair: str
    index_symbol: str
    db_paths: list[Path]
    output: Path
    timeout: float


def _default_db_paths() -> list[Path]:
    candidates = [
        resolve_db_path(),
        _BACKEND_DIR / DEFAULT_DB_PATH.lstrip("./"),
        _BACKEND_DIR / "data" / "ceo-test.db",
    ]
    seen: list[Path] = []
    for candidate in candidates:
        resolved = candidate if candidate.is_absolute() else (_BACKEND_DIR / candidate).resolve()
        if resolved not in seen:
            seen.append(resolved)
    return seen


def parse_args(argv: Sequence[str] | None) -> CliArgs:
    today = date.today()
    parser = argparse.ArgumentParser(
        description="Stock Desk 六個市場資料 adapter 的 CEO 本機一鍵核實工具。",
    )
    parser.add_argument("--start", type=date.fromisoformat, default=today - timedelta(days=10))
    parser.add_argument("--end", type=date.fromisoformat, default=today)
    parser.add_argument("--tw-symbols", default="2330,0050,00631L")
    parser.add_argument("--tpex-symbol", default="5483")
    parser.add_argument("--us-symbol", default="AAPL")
    parser.add_argument("--fx-pair", default="USDTWD")
    parser.add_argument("--index-symbol", default="^TWII")
    parser.add_argument("--db-path", action="append", default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=8.0)
    ns = parser.parse_args(argv)

    db_paths = [Path(p) for p in ns.db_path] if ns.db_path else _default_db_paths()
    output = ns.output or (
        _REPO_ROOT / "work" / "research" / f"驗證結果-{today.isoformat()}.md"
    )
    return CliArgs(
        start=ns.start,
        end=ns.end,
        tw_symbols=[s.strip() for s in ns.tw_symbols.split(",") if s.strip()],
        tpex_symbol=ns.tpex_symbol,
        us_symbol=ns.us_symbol,
        fx_pair=ns.fx_pair,
        index_symbol=ns.index_symbol,
        db_paths=db_paths,
        output=output,
        timeout=ns.timeout,
    )


@dataclass(frozen=True)
class RunResult:
    markdown: str
    adapter_results: tuple[AdapterProbeResult, ...]
    comparisons: dict[str, list[ComparisonRow]]


def run(args: CliArgs, *, transport: httpx.BaseTransport | None = None) -> RunResult:
    """Execute every check and return the rendered Markdown report plus raw results."""

    def reach(url: str) -> ReachabilityResult:
        get_fn = (
            (lambda u, t: _default_http_get(u, t, transport=transport)) if transport else None
        )
        return check_reachability(url, timeout=args.timeout, get_fn=get_fn)

    twse_symbol = args.tw_symbols[0] if args.tw_symbols else "2330"

    adapter_results = [
        probe_twse(
            twse_symbol,
            args.start,
            args.end,
            transport=transport,
            reachability=reach(TWSE_BASE_URL),
        ),
        probe_tpex(
            args.tpex_symbol,
            args.start,
            args.end,
            transport=transport,
            reachability=reach(TPEX_BASE_URL),
        ),
        probe_finmind(
            twse_symbol,
            args.start,
            args.end,
            transport=transport,
            reachability=reach(FINMIND_BASE_URL),
        ),
        probe_fx(
            args.fx_pair,
            args.start,
            args.end,
            transport=transport,
            reachability=reach(BOT_BASE_URL),
        ),
        probe_alpha_vantage(
            args.us_symbol,
            args.start,
            args.end,
            transport=transport,
            reachability=reach(ALPHA_VANTAGE_BASE_URL),
        ),
        probe_yfinance_index(
            args.index_symbol,
            args.start,
            args.end,
            transport=transport,
            reachability=reach(YFINANCE_BASE_URL),
        ),
    ]

    bonus_reachability = [(name, url, reach(url)) for name, url in BONUS_REACHABILITY_TARGETS]

    comparisons: dict[str, list[ComparisonRow]] = {}
    for symbol in args.tw_symbols:
        twse_client = _make_client(TWSE_BASE_URL, 0.5, transport=transport)
        finmind_client = _make_client(FINMIND_BASE_URL, 0.3, transport=transport)
        twse_adapter = TwseAdapter(client=twse_client)
        finmind_adapter = FinMindAdapter(client=finmind_client)
        try:
            twse_result = twse_adapter.get_daily_bars(symbol, args.start, args.end)
            finmind_result = finmind_adapter.get_daily_bars(symbol, args.start, args.end)
        finally:
            twse_adapter.close()
            finmind_adapter.close()
        comparisons[symbol] = compare_bars(symbol, twse_result.bars, finmind_result.bars)

    demo_reports = [scan_demo_synthetic(path) for path in args.db_paths]
    leverage_report = check_leverage_registry()

    markdown = render_report(
        generated_at=datetime.now(UTC),
        start=args.start,
        end=args.end,
        adapter_results=adapter_results,
        bonus_reachability=bonus_reachability,
        comparisons=comparisons,
        demo_reports=demo_reports,
        leverage_report=leverage_report,
    )
    return RunResult(
        markdown=markdown,
        adapter_results=tuple(adapter_results),
        comparisons=comparisons,
    )


def _print_terminal_summary(report_markdown: str, output_path: Path) -> None:
    print("=" * 72)
    print("Stock Desk 數據源驗證 -- 終端摘要")
    print("=" * 72)
    for line in report_markdown.splitlines():
        if line.startswith("| ") or line.startswith("- **") or line.startswith("**"):
            print(line)
    print("-" * 72)
    print(f"完整報告已寫入：{output_path}")


def main(argv: Sequence[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    args = parse_args(argv)
    result = run(args, transport=transport)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.markdown, encoding="utf-8")
    _print_terminal_summary(result.markdown, args.output)
    any_not_pass = any(r.verdict is not Verdict.PASS for r in result.adapter_results)
    any_comparison_fail = any(
        row.verdict is Verdict.FAIL for rows in result.comparisons.values() for row in rows
    )
    return 1 if (any_not_pass or any_comparison_fail) else 0


if __name__ == "__main__":
    raise SystemExit(main())
