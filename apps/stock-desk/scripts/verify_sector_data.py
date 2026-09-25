"""CEO 本機查證工具 -- ADR-0012 族群動能資料層的四個懸而未決問題（DE-1'、DE-5、DE-2/DE-3、DE-11）。

## 為什麼是新腳本，不擴充既有 `verify_market_data.py`

`verify_market_data.py` 是 ADR-0002 checklist 的七個既有 adapter 一次性連線
驗證工具（PASS/FAIL/UNREACHABLE 三態、比對既有 adapter）。本腳本要查證的四
件事屬於 ADR-0012 這一輪新增、性質完全不同的問題：

- DE-1'／DE-5 是「payload 的欄位語意」問題（有沒有交易日欄位？`Change` 的基
  準是什麼？），不是「連不連得到」；
- DE-2/DE-3 要量測的是「單一標的全段歷史」的耗時與限流，既有工具只測近 10
  天的短區間；
- DE-11 需要 3 年歷史 + 除權息事件表做統計分布，既有工具完全没有這個維度。

硬塞進同一個檔案只會讓兩份 checklist 的關注點混在一起、難以各自維護；因此
另開一個檔案，import 既有 adapter／常數，不重造輪子。

## 3 步驟開始使用（Windows PowerShell）

```powershell
cd apps\\stock-desk\\backend
$env:FINMIND_API_TOKEN = "<你的 token>"
uv run python ..\\scripts\\verify_sector_data.py --de5-cases de5_cases.json
```

`--de5-cases` 是 DE-5 需要的人工輸入（見下方「DE-5 需要什麼」），沒有這個檔
案時 DE-5 一節會直接報告「需要什麼」而不是猜測結果。其餘三節（DE-1'、
DE-2/DE-3、DE-11）不需要額外輸入即可執行，但都需要能連上
`openapi.twse.com.tw` 與 `api.finmindtrade.com`（本沙盒的 egress 已知被擋，
必須在 CEO 本機或其他有網路的機器執行）。

完整報告預設寫到 `work/research/族群動能資料查證-<今天日期>.md`，可用
`--output` 指定路徑。

## 這支工具做什麼、不做什麼

做：
- DE-1'：抓一次 `STOCK_DAY_ALL`，檢查 payload 是否帶有可辨識的交易日欄位。
- DE-5：對 CEO 指定的既往除權息案例，抓當天個股 `STOCK_DAY`，比較 `Change`
  對「除權息參考價」與對「前一日收盤價」兩種假設何者相符。
- DE-2/DE-3：對一檔股票抓一段長區間的 FinMind 歷史，量測耗時，並檢查回應本
  身或 HTTP 狀態碼是否透露限流訊號。
- DE-11：用 FinMind `TaiwanStockDividend`（**資料集名稱本次未查證，是依公開
  生態圈慣例的猜測**，若回應形狀不符會如實報告，不會假造欄位）取得近 3 年
  除權息歷史，對今日上市名單（**已知有存活者偏差，見下方揭露**）估算每個
  交易日 L=5 窗的除權息排除比例。
- **bars 覆蓋率分母健檢**（qa-reviewer 第一波審查追加）：量測
  `|STOCK_DAY_ALL 代號 ∩ t187ap03_L 普通股| ÷ |t187ap03_L 普通股|` 的**實際
  值**——這就是 `app.services.pit_snapshot._capture_bars` 拿來跟 0.98 比較
  的同一個比率。每次執行都會把當天的比率追加寫進
  `work/research/族群動能資料查證-bars覆蓋率歷史.jsonl`（同一格式追加，不
  覆蓋），連續跑幾天就能看出「就算是正常交易日，STOCK_DAY_ALL 本來就涵蓋
  不到 98% 的普通股」是不是常態（例如當天無成交、暫停交易的股票不會出現
  在 STOCK_DAY_ALL），藉此判斷 0.98 門檻本身合不合理，而不只是驗證程式邏
  輯有沒有按門檻判斷。

不做：
- 不憑記憶寫死任何費率、額度或端點規格 -- 查不到就報告「未查證」。
- 不把 `FINMIND_API_TOKEN` 印到任何輸出或報告裡。
- 不用任何內插值填補查不到的資料；查不到就是查不到，原樣寫進報告。

## 已知限制（必須隨報告一併揭露）

DE-11 的估算使用**今日**的上市名單當作過去 3 年的母體代理，這與資料評估
§8.3 記錄的存活者偏差是同一個問題：已下市個股不會出現在分母也不會出現在
分子，估算出的排除比例可能偏低。這個限制無法在本腳本內解決（需要歷史下市
名單來源，目前不存在），只能如實揭露、不假裝精準。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

_SCRIPT_DIR = Path(__file__).resolve().parent
_STOCK_DESK_DIR = _SCRIPT_DIR.parent
_BACKEND_DIR = _STOCK_DESK_DIR / "backend"
_REPO_ROOT = _STOCK_DESK_DIR.parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ruff: noqa: E402  -- these must come after the sys.path bootstrap above.
from app.data.http import RateLimitedClient
from app.data.providers.finmind import DATA_PATH as FINMIND_DATA_PATH
from app.data.providers.finmind import FINMIND_BASE_URL, TOKEN_ENV_VAR
from app.data.providers.twse import STOCK_DAY_PATH, TWSE_BASE_URL
from app.directory.providers import (
    TWSE_OPENAPI_BASE_URL,
    TWSE_STOCK_LIST_PATH,
    TwseSectorProfileAdapter,
)
from app.directory.twse_sector_codes import TWSE_SECTOR_CODE_TO_NAME

# --------------------------------------------------------------------------
# DE-1': does STOCK_DAY_ALL carry a trading date field?
# --------------------------------------------------------------------------

#: Field names that would plausibly carry a trading date if TWSE ever adds
#: one to this dataset. Checked by presence only -- this never guesses a
#: value, only reports whether such a key exists in the real payload.
_CANDIDATE_DATE_KEYS = ("Date", "TradeDate", "TDate", "ODate", "公告日期", "資料日期")


@dataclass(frozen=True)
class De1Result:
    ok: bool
    detail: str


def check_de1_session_date(client: RateLimitedClient) -> De1Result:
    try:
        response = client.get(TWSE_STOCK_LIST_PATH)
    except httpx.TransportError as exc:
        return De1Result(False, f"連線失敗：{exc}")
    if response.status_code != httpx.codes.OK:
        return De1Result(False, f"HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        return De1Result(False, "回應非 JSON")
    if not isinstance(payload, list) or not payload:
        return De1Result(False, f"回應非預期形狀：{type(payload).__name__}")
    sample = payload[0]
    if not isinstance(sample, dict):
        return De1Result(False, "列不是物件")
    found = [key for key in _CANDIDATE_DATE_KEYS if key in sample]
    all_keys = sorted(sample.keys())
    if found:
        return De1Result(
            True,
            f"payload 帶有候選日期欄位 {found}；完整欄位：{all_keys}；"
            "**仍須人工確認這個欄位真的是交易日，不是出表日或其他日期**。",
        )
    return De1Result(
        False,
        f"payload 沒有任何候選日期欄位；完整欄位：{all_keys}；"
        "與 tests/fixtures/twse_openapi_stock_day_all.json 一致，DE-1' 結論"
        "維持「不帶交易日」，須依 ADR-0012 D-3 走 FinMind 交叉比對自證。",
    )


# --------------------------------------------------------------------------
# bars 覆蓋率分母健檢：STOCK_DAY_ALL 對 t187ap03_L 普通股的實際覆蓋率
# --------------------------------------------------------------------------

#: One JSON object per line, appended (never overwritten) so consecutive
#: daily runs build up a multi-day history without any manual bookkeeping.
_COVERAGE_LOG_FILENAME = "族群動能資料查證-bars覆蓋率歷史.jsonl"


@dataclass(frozen=True)
class CoverageRatioResult:
    ok: bool
    detail: str
    ratio: float | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


def _fetch_t187_common_stock_symbols(
    client: RateLimitedClient,
) -> tuple[set[str], str | None]:
    """The exact set ``TwseSnapshotAdapter`` uses as ``listing_common``
    (``security_type == "common_stock"``)."""
    result = TwseSectorProfileAdapter(client=client).fetch()
    if not result.ok:
        return set(), result.reason
    common: set[str] = set()
    for entry in result.entries:
        if entry.sector == "91":  # TDR, excluded from the common-stock population
            continue
        if entry.sector not in TWSE_SECTOR_CODE_TO_NAME:
            continue
        common.add(entry.symbol)
    return common, None


def check_bars_coverage_ratio(
    twse_client: RateLimitedClient, *, log_path: Path
) -> CoverageRatioResult:
    """Measure the real ``|STOCK_DAY_ALL ∩ t187 common| / |t187 common|`` ratio.

    This is the exact same ratio ``app.services.pit_snapshot._capture_bars``
    compares against ``BARS_OK_COVERAGE_MIN`` (0.98) -- qa-reviewer wave-1
    review asked for this precisely so CEO can see, from real data, whether a
    completely healthy trading day is even capable of reaching 98% (e.g. if
    suspended/no-trade symbols are routinely a few percent of the market,
    the gate would degrade to "partial" every single day and the threshold
    itself -- not the code -- would need revisiting).
    """
    stock_day_symbols = _fetch_listing_symbols(twse_client)
    if stock_day_symbols is None:
        return CoverageRatioResult(False, "STOCK_DAY_ALL 查詢失敗，無法量測覆蓋率")
    common_symbols, reason = _fetch_t187_common_stock_symbols(twse_client)
    if not common_symbols:
        return CoverageRatioResult(False, f"t187ap03_L 查詢失敗或無普通股列：{reason}")

    matched = len(set(stock_day_symbols) & common_symbols)
    ratio = matched / len(common_symbols)
    today = date.today()

    history: list[dict[str, Any]] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    history.append(json.loads(line))
                except ValueError:
                    continue
    record = {
        "date": today.isoformat(),
        "matched": matched,
        "common_stock_total": len(common_symbols),
        "ratio": round(ratio, 4),
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    history.append(record)

    detail = (
        f"今日（{today}）：{matched}/{len(common_symbols)} = {ratio:.4f}"
        f"（門檻 0.98，{'達標' if ratio >= 0.98 else '未達標，會被判 partial'}）。"
        f"累積 {len(history)} 天歷史紀錄於 {log_path}。"
    )
    return CoverageRatioResult(True, detail, ratio, history)


# --------------------------------------------------------------------------
# DE-5: is `Change` measured against the ex-dividend reference price?
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class De5Case:
    """One CEO-supplied, real, past ex-dividend day to check `Change` against.

    ``--de5-cases`` points at a JSON file: a list of objects with these four
    keys. ``prior_close`` is the previous trading day's actual close (CEO
    reads this off TWSE's own 個股歷史行情 page or ``STOCK_DAY``); this
    script does not fetch it itself because "the day before an ex-dividend
    day" is exactly the ambiguous case DE-5 is trying to resolve, and fetching
    it automatically would risk quietly encoding the same assumption the
    check exists to test.
    """

    symbol: str
    ex_date: date
    prior_close: Decimal
    cash_dividend: Decimal


def _load_de5_cases(path: Path) -> list[De5Case]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases: list[De5Case] = []
    for entry in raw:
        cases.append(
            De5Case(
                symbol=str(entry["symbol"]),
                ex_date=date.fromisoformat(entry["ex_date"]),
                prior_close=Decimal(str(entry["prior_close"])),
                cash_dividend=Decimal(str(entry["cash_dividend"])),
            )
        )
    return cases


@dataclass(frozen=True)
class De5CaseResult:
    case: De5Case
    ok: bool
    detail: str


def _fetch_stock_day_change(
    client: RateLimitedClient, symbol: str, target: date
) -> tuple[Decimal, Decimal] | None:
    """Return ``(close, change)`` for one symbol on one date via TWSE's per-symbol STOCK_DAY."""
    month_start = target.replace(day=1)
    try:
        response = client.get(
            STOCK_DAY_PATH,
            params={
                "response": "json",
                "date": month_start.strftime("%Y%m%d"),
                "stockNo": symbol,
            },
        )
    except httpx.TransportError:
        return None
    if response.status_code != httpx.codes.OK:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        return None
    for row in payload.get("data") or []:
        try:
            roc_year, month, day = (int(part) for part in row[0].split("/"))
            row_date = date(roc_year + 1911, month, day)
        except (ValueError, IndexError):
            continue
        if row_date != target:
            continue
        try:
            close = Decimal(str(row[6]).replace(",", ""))
            change_raw = str(row[7]).replace(",", "").replace("+", "")
            change = Decimal(change_raw)
        except (InvalidOperation, IndexError):
            return None
        return close, change
    return None


def check_de5_case(client: RateLimitedClient, case: De5Case) -> De5CaseResult:
    fetched = _fetch_stock_day_change(client, case.symbol, case.ex_date)
    if fetched is None:
        return De5CaseResult(case, False, f"查無 {case.symbol} 於 {case.ex_date} 的資料")
    close, change = fetched
    reference_price = case.prior_close - case.cash_dividend
    matches_reference = abs((close - reference_price) - change) <= Decimal("0.01")
    matches_raw_prior_close = abs((close - case.prior_close) - change) <= Decimal("0.01")
    detail = (
        f"close={close} change={change} prior_close={case.prior_close} "
        f"cash_dividend={case.cash_dividend} reference_price={reference_price} | "
        f"對「除權息參考價」相符={matches_reference}；對「前一日收盤價」相符={matches_raw_prior_close}"
    )
    if matches_reference and not matches_raw_prior_close:
        return De5CaseResult(case, True, detail + " => Change 以除權息參考價為基準")
    if matches_raw_prior_close and not matches_reference:
        return De5CaseResult(case, True, detail + " => Change 以前一日收盤價為基準（未還原）")
    return De5CaseResult(case, False, detail + " => 兩種假設都不吻合或都吻合，需人工複核")


# --------------------------------------------------------------------------
# DE-2 / DE-3: FinMind single-symbol full-history timing and rate limiting.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class De2De3Result:
    ok: bool
    elapsed_seconds: float
    row_count: int
    detail: str


def check_de2_de3(
    client: RateLimitedClient, symbol: str, start: date, end: date, token: str
) -> De2De3Result:
    started = time.monotonic()
    try:
        response = client.get(
            FINMIND_DATA_PATH,
            params={
                "dataset": "TaiwanStockPrice",
                "data_id": symbol,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "token": token,
            },
        )
    except httpx.TransportError as exc:
        return De2De3Result(False, time.monotonic() - started, 0, f"連線失敗：{exc}")
    elapsed = time.monotonic() - started
    if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
        return De2De3Result(False, elapsed, 0, "HTTP 429 -- 已被限流")
    if response.status_code != httpx.codes.OK:
        return De2De3Result(False, elapsed, 0, f"HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        return De2De3Result(False, elapsed, 0, "回應非 JSON")
    status = payload.get("status") if isinstance(payload, dict) else None
    rows = payload.get("data") if isinstance(payload, dict) else None
    row_count = len(rows) if isinstance(rows, list) else 0
    if status != 200:
        msg = payload.get("msg") if isinstance(payload, dict) else None
        return De2De3Result(
            False,
            elapsed,
            row_count,
            f"body status={status!r} msg={msg!r}（可能是限流或額度訊息）",
        )
    return De2De3Result(
        True,
        elapsed,
        row_count,
        f"{start}~{end} 共 {row_count} 列，耗時 {elapsed:.2f} 秒，單次請求成功、無限流跡象",
    )


# --------------------------------------------------------------------------
# DE-11: ex-dividend season magnitude (survivorship-biased estimate).
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class De11Result:
    ok: bool
    detail: str
    #: {candidate_threshold: {year: degraded_trading_days}}
    degraded_days_by_threshold: dict[str, dict[int, int]] = field(default_factory=dict)


def _fetch_listing_symbols(client: RateLimitedClient) -> list[str] | None:
    try:
        response = client.get(TWSE_STOCK_LIST_PATH)
    except httpx.TransportError:
        return None
    if response.status_code != httpx.codes.OK:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, list):
        return None
    return sorted({row["Code"] for row in payload if isinstance(row, dict) and row.get("Code")})


def _fetch_dividend_dates(
    client: RateLimitedClient, symbol: str, start: date, end: date, token: str
) -> list[date] | None:
    """FinMind ``TaiwanStockDividend``'s ex-dividend dates for one symbol.

    **Dataset name and field names are UNVERIFIED in this sandbox** (no
    egress). If the response shape does not match what is coded here, this
    returns ``None`` and the caller reports the mismatch honestly rather than
    guessing at alternate field names.
    """
    try:
        response = client.get(
            FINMIND_DATA_PATH,
            params={
                "dataset": "TaiwanStockDividend",
                "data_id": symbol,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "token": token,
            },
        )
    except httpx.TransportError:
        return None
    if response.status_code != httpx.codes.OK:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("status") != 200:
        return None
    rows = payload.get("data")
    if not isinstance(rows, list):
        return None
    dates: list[date] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_date = row.get("CashExDividendTradingDate") or row.get("date")
        if not raw_date:
            continue
        try:
            dates.append(date.fromisoformat(str(raw_date)))
        except ValueError:
            continue
    return dates


def check_de11(
    client: RateLimitedClient,
    *,
    token: str,
    years: int,
    symbol_limit: int | None,
    candidate_thresholds: Sequence[float] = (0.80, 0.85, 0.90),
) -> De11Result:
    symbols = _fetch_listing_symbols(client)
    if symbols is None:
        return De11Result(False, "無法取得上市名單（STOCK_DAY_ALL 失敗），DE-11 無法估算")
    if symbol_limit is not None:
        symbols = symbols[:symbol_limit]

    end = date.today()
    start = end - timedelta(days=365 * years)
    universe_size = len(symbols)
    if universe_size == 0:
        return De11Result(False, "上市名單為空，DE-11 無法估算")

    ex_dates_by_symbol: dict[str, list[date]] = {}
    failures = 0
    for symbol in symbols:
        dates = _fetch_dividend_dates(client, symbol, start, end, token)
        if dates is None:
            failures += 1
            continue
        ex_dates_by_symbol[symbol] = dates

    if not ex_dates_by_symbol:
        return De11Result(
            False,
            "TaiwanStockDividend 資料集完全查不到任何一檔的資料 -- 資料集名稱或欄位可能與本"
            "腳本假設的不同（未查證）。需要：(1) 確認 FinMind 是否真有這個 dataset、正確名稱"
            "為何；(2) 若不存在，需另尋歷史除權息來源才能完成 DE-11。",
        )

    # Approximate trading calendar as every weekday in range -- good enough
    # for a magnitude estimate; exact holidays do not change the conclusion
    # materially and this script does not want to hardcode a holiday table.
    trading_days = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            trading_days.append(day)
        day += timedelta(days=1)

    ratios_by_day: dict[date, float] = {}
    for t in trading_days:
        window_start = t - timedelta(days=7)  # ~5 trading days, generous calendar padding
        excluded = 0
        for dates in ex_dates_by_symbol.values():
            if any(window_start <= d <= t for d in dates):
                excluded += 1
        computable = universe_size - excluded
        ratios_by_day[t] = computable / universe_size

    degraded_days_by_threshold: dict[str, dict[int, int]] = {}
    for threshold in candidate_thresholds:
        by_year: dict[int, int] = defaultdict(int)
        for t, ratio in ratios_by_day.items():
            if ratio < threshold:
                by_year[t.year] += 1
        degraded_days_by_threshold[f"{threshold:.2f}"] = dict(sorted(by_year.items()))

    detail = (
        f"母體 {universe_size} 檔（{failures} 檔查詢失敗，略過）；"
        f"樣本區間 {start}~{end}；母體為**今日**上市名單，套用到過去（已知存活者偏差，"
        "見檔頭揭露）。中位數可計算比例："
        f"{statistics.median(ratios_by_day.values()):.4f}"
    )
    return De11Result(True, detail, degraded_days_by_threshold)


# --------------------------------------------------------------------------
# Report assembly
# --------------------------------------------------------------------------


def build_report(
    *,
    de1: De1Result,
    coverage: CoverageRatioResult | None,
    de5_cases: list[De5CaseResult],
    de5_note: str | None,
    de2_de3: De2De3Result | None,
    de11: De11Result | None,
    generated_at: datetime,
) -> str:
    lines = [
        "# stock-desk 族群動能資料查證報告",
        "",
        f"產出時間：{generated_at.isoformat()}",
        "",
        "## DE-1'：STOCK_DAY_ALL 是否帶交易日欄位",
        "",
        f"結論：{'PASS（找到候選欄位，仍待人工確認語意）' if de1.ok else 'FAIL（未帶交易日欄位）'}",
        "",
        de1.detail,
        "",
        "## bars 覆蓋率分母健檢：STOCK_DAY_ALL ∩ t187 普通股 ÷ t187 普通股",
        "",
    ]
    if coverage is None:
        lines.append("（未執行）")
    elif not coverage.ok:
        lines.append(f"無法量測：{coverage.detail}")
    else:
        lines.append(coverage.detail)
        if len(coverage.history) > 1:
            lines.append("")
            lines.append("歷史紀錄（依日期）：")
            for record in coverage.history:
                lines.append(
                    f"- {record['date']}：{record['matched']}/{record['common_stock_total']} "
                    f"= {record['ratio']}"
                )
    lines.extend(["", "## DE-5：`Change` 是否以除權息參考價為基準", ""])
    if de5_note:
        lines.extend([de5_note, ""])
    for result in de5_cases:
        lines.append(
            f"- {result.case.symbol} {result.case.ex_date}："
            f"{'PASS' if result.ok else 'FAIL/需複核'} -- {result.detail}"
        )
    if not de5_cases and not de5_note:
        lines.append("（沒有提供 --de5-cases，未執行）")
    lines.extend(["", "## DE-2/DE-3：FinMind 單檔全段耗時與限流", ""])
    if de2_de3 is None:
        lines.append("（未執行，缺 FINMIND_API_TOKEN 或 --skip-de2-de3）")
    else:
        lines.append(f"結論：{'PASS' if de2_de3.ok else 'FAIL/需覆核'} -- {de2_de3.detail}")
    lines.extend(["", "## DE-11：除息旺季三類排除量級（估算，已知存活者偏差）", ""])
    if de11 is None:
        lines.append("（未執行，缺 FINMIND_API_TOKEN 或 --skip-de11）")
    elif not de11.ok:
        lines.append(f"無法估算：{de11.detail}")
    else:
        lines.append(de11.detail)
        lines.append("")
        lines.append("各候選門檻、各年度「整卡降級」交易日數：")
        for threshold, by_year in de11.degraded_days_by_threshold.items():
            lines.append(f"- 門檻 {threshold}：{by_year}")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--de5-cases", type=Path, default=None, help="DE-5 案例 JSON 檔路徑")
    parser.add_argument("--finmind-symbol", default="2330", help="DE-2/DE-3 測試用標的")
    parser.add_argument("--finmind-years", type=int, default=5, help="DE-2/DE-3 抓取年數")
    parser.add_argument("--de11-years", type=int, default=3)
    parser.add_argument(
        "--de11-symbol-limit",
        type=int,
        default=None,
        help="DE-11 只抽樣前 N 檔（避免整段跑太久／太多請求）",
    )
    parser.add_argument("--skip-de2-de3", action="store_true")
    parser.add_argument("--skip-de11", action="store_true")
    parser.add_argument("--skip-coverage-ratio", action="store_true")
    parser.add_argument(
        "--coverage-log",
        type=Path,
        default=None,
        help="bars 覆蓋率歷史紀錄檔路徑（預設 work/research/ 下）",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    token = os.environ.get(TOKEN_ENV_VAR)

    twse_client = RateLimitedClient(base_url=TWSE_OPENAPI_BASE_URL, min_interval_seconds=0.5)
    twse_stock_day_client = RateLimitedClient(base_url=TWSE_BASE_URL, min_interval_seconds=0.5)
    finmind_client = RateLimitedClient(base_url=FINMIND_BASE_URL, min_interval_seconds=0.3)
    try:
        de1 = check_de1_session_date(twse_client)

        coverage: CoverageRatioResult | None = None
        if not args.skip_coverage_ratio:
            log_path = args.coverage_log or (
                _REPO_ROOT / "work" / "research" / _COVERAGE_LOG_FILENAME
            )
            coverage = check_bars_coverage_ratio(twse_client, log_path=log_path)

        de5_results: list[De5CaseResult] = []
        de5_note: str | None = None
        if args.de5_cases is not None:
            cases = _load_de5_cases(args.de5_cases)
            for case in cases:
                de5_results.append(check_de5_case(twse_stock_day_client, case))
        else:
            de5_note = (
                "**DE-5 需要什麼**：一份 JSON 檔（`--de5-cases path.json`），內容是 2~3 筆"
                '`[{"symbol": "2330", "ex_date": "2026-07-15", "prior_close": "600.00", '
                '"cash_dividend": "3.00"}]`，取自最近真實發生過除權息的個股（symbol、除權息日、'
                "前一日收盤價、公告現金股利，皆為公開資訊，CEO 或有網路環境者查證後填入）。"
            )

        de2_de3: De2De3Result | None = None
        if not args.skip_de2_de3 and token:
            end = date.today()
            start = end - timedelta(days=365 * args.finmind_years)
            de2_de3 = check_de2_de3(finmind_client, args.finmind_symbol, start, end, token)

        de11: De11Result | None = None
        if not args.skip_de11 and token:
            de11 = check_de11(
                twse_client,
                token=token,
                years=args.de11_years,
                symbol_limit=args.de11_symbol_limit,
            )
    finally:
        twse_client.close()
        twse_stock_day_client.close()
        finmind_client.close()

    report = build_report(
        de1=de1,
        coverage=coverage,
        de5_cases=de5_results,
        de5_note=de5_note,
        de2_de3=de2_de3,
        de11=de11,
        generated_at=datetime.now(UTC),
    )
    output = args.output or (
        _REPO_ROOT / "work" / "research" / f"族群動能資料查證-{date.today().isoformat()}.md"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n完整報告已寫入：{output}")
    if not token:
        print(
            f"\n提醒：未設定 {TOKEN_ENV_VAR}，DE-2/DE-3 與 DE-11 已略過。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
