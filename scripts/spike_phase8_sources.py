"""Phase 8 資料源可行性 spike -- 逐源最小查證請求腳本。

用途
----
Stock Desk Phase 8 的核心主軸需要接入台股/美股的基本面(S-1)、籌碼面(S-2，
CEO 裁示最優先)、消息面(S-3) 資料源。開發沙盒本身無外網（對外 HTTPS 一律
403/000），所有候選端點只能憑公開文件的既有知識盤點，無法在沙盒內查證。
本腳本設計為在**有網路的環境**（CEO 本機）執行，對每個候選源發出一次最小
查證請求，如實印出「源名稱 / HTTP 狀態 / 欄位樣本 / 結論」，供 CEO 回填到
``work/stock-desk-phase8-spike-盤點.md`` 的空欄。

執行方式
--------
    uv run --with httpx python scripts/spike_phase8_sources.py
    # 或（已安裝 httpx 的環境）
    python scripts/spike_phase8_sources.py

本腳本刻意設計為單檔、只依賴 stdlib + httpx，不 import 任何專案內程式碼
（``app.*``），因此可以獨立丟到任何有網路的機器上執行，不需要安裝整個
backend 專案。

紅線與誠實聲明
--------------
- 本腳本內所有端點路徑、參數名稱、資料集名稱均**憑撰寫當下（2026-08）的
  既有知識手工列出，尚未在有網環境中實測過**；標了「高/中/低信心」僅代表
  data-engineer 對記憶正確性的主觀評估，不是查證結果。
- 任何請求失敗（404、格式不符、逾時、被擋）都是**有用的 spike 產出**，
  不代表腳本有 bug——請把失敗訊息原樣記錄回盤點表，不要為了「讓它綠燈」
  而修改判斷邏輯去掩蓋失敗。
- 不需要 API key 的來源排在前面優先測試；需要 key 的來源（Alpha Vantage、
  FinMind 進階 dataset）以環境變數讀取，未設定就整段跳過並在報告中明列
  跳過條件，**絕不把任何金鑰寫死在本檔案**。
- 本腳本只做「打得通、欄位長什麼樣子」層級的最小查證，不做完整的欄位
  對應、分頁、歷史回補；後續正式 adapter 實作另行設計。
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover - guidance path, not exercised in CI
    print(
        "此腳本需要 httpx。請用下列任一方式執行：\n"
        "  uv run --with httpx python scripts/spike_phase8_sources.py\n"
        "  pip install httpx && python scripts/spike_phase8_sources.py",
        file=sys.stderr,
    )
    sys.exit(1)


TIMEOUT_SECONDS = 15.0
# Yahoo Finance 的未公開端點已知會拒絕沒有 User-Agent 的請求
# (沿用 app/data/providers/yfinance.py 既有作法，同一條既有教訓)。
BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0"}

# 查證用標的：台積電（TWSE 上市，S-1/S-2 主要查證對象）、
# 上櫃股票（TPEx 對應端點查證用）、蘋果（美股 S-1/S-3 查證對象）。
TW_SYMBOL_LISTED = "2330"
TW_SYMBOL_OTC = "6488"
US_SYMBOL = "AAPL"

TODAY = date.today()
RECENT_START = TODAY - timedelta(days=14)


@dataclass
class SourceResult:
    """一筆查證結果，對應報告要求的四欄。"""

    category: str  # S-1 / S-2 / S-3
    name: str  # 源名稱
    http_status: str  # HTTP 狀態（或 SKIPPED / EXCEPTION）
    field_sample: str  # 欄位樣本
    conclusion: str  # 結論
    confidence_note: str = ""  # 撰寫時對端點記憶正確性的信心備註


RESULTS: list[SourceResult] = []


def _print_result(r: SourceResult) -> None:
    print(f"\n[{r.category}] {r.name}")
    print(f"  HTTP 狀態  : {r.http_status}")
    print(f"  欄位樣本   : {r.field_sample}")
    print(f"  結論       : {r.conclusion}")
    if r.confidence_note:
        print(f"  信心備註   : {r.confidence_note}")
    RESULTS.append(r)


def _sample_from_json(payload: Any, max_items: int = 1, max_len: int = 400) -> str:
    """從解析後的 JSON 擷取一小段可讀的欄位樣本字串。"""
    try:
        if isinstance(payload, list):
            if not payload:
                return "(空陣列，無欄位可看)"
            sample = payload[:max_items]
            text = json.dumps(sample, ensure_ascii=False)
        elif isinstance(payload, dict):
            # 常見的「外層包一層 data list」形狀
            for key in ("data", "Time Series (Daily)", "result"):
                inner = payload.get(key) if isinstance(payload, dict) else None
                if isinstance(inner, list) and inner:
                    text = json.dumps(inner[:max_items], ensure_ascii=False)
                    break
                if isinstance(inner, dict) and inner:
                    first_key = next(iter(inner))
                    text = json.dumps({first_key: inner[first_key]}, ensure_ascii=False)
                    break
            else:
                keys = list(payload.keys())[:20]
                text = f"top-level keys: {keys}"
        else:
            text = repr(payload)
    except Exception as exc:  # noqa: BLE001 - spike 腳本，任何序列化失敗都要如實記錄
        return f"(欄位樣本擷取失敗: {exc!r})"
    if len(text) > max_len:
        text = text[:max_len] + "...(截斷)"
    return text


def run_get(
    client: httpx.Client,
    *,
    category: str,
    name: str,
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    confidence_note: str = "",
    parse_json: bool = True,
) -> None:
    """對單一來源發出一次 GET 查證請求，任何失敗都捕捉並繼續。"""
    try:
        response = client.get(url, params=params, headers=headers, timeout=TIMEOUT_SECONDS)
    except httpx.TimeoutException as exc:
        _print_result(
            SourceResult(
                category=category,
                name=name,
                http_status="EXCEPTION (timeout)",
                field_sample="(無回應)",
                conclusion=f"連線逾時，需重測或確認端點是否仍存在：{exc!r}",
                confidence_note=confidence_note,
            )
        )
        return
    except httpx.HTTPError as exc:
        _print_result(
            SourceResult(
                category=category,
                name=name,
                http_status="EXCEPTION (transport)",
                field_sample="(無回應)",
                conclusion=f"連線層失敗（DNS/TLS/連線被拒等）：{exc!r}",
                confidence_note=confidence_note,
            )
        )
        return
    except Exception as exc:  # noqa: BLE001 - spike 腳本要求任何失敗都不中斷後續來源
        _print_result(
            SourceResult(
                category=category,
                name=name,
                http_status="EXCEPTION (unexpected)",
                field_sample="(無回應)",
                conclusion=f"未預期的例外，請回報給 data-engineer：{traceback.format_exc()[:300]}",
                confidence_note=confidence_note,
            )
        )
        return

    status_line = f"{response.status_code} {response.reason_phrase}"
    field_sample = "(未嘗試解析為 JSON)"
    conclusion = ""

    if parse_json:
        try:
            payload = response.json()
            field_sample = _sample_from_json(payload)
            if response.status_code == httpx.codes.OK:
                conclusion = "HTTP 200 且可解析為 JSON；請人工核對欄位樣本是否符合預期 schema。"
            else:
                conclusion = f"HTTP {response.status_code}，非預期狀態碼，端點可能已變動或需要額外參數。"
        except ValueError:
            body_preview = response.text[:300].replace("\n", " ")
            field_sample = f"(非 JSON 回應，前 300 字元): {body_preview!r}"
            if response.status_code == httpx.codes.OK:
                conclusion = "HTTP 200 但非 JSON（可能是 HTML/CSV/純文字），需改用對應格式解析或改端點。"
            else:
                conclusion = f"HTTP {response.status_code} 且非 JSON，端點可能不存在或被導向錯誤頁。"
    else:
        body_preview = response.text[:300].replace("\n", " ")
        field_sample = f"(前 300 字元): {body_preview!r}"
        conclusion = (
            "HTTP 200，內容非 JSON（預期為 HTML/CSV），本腳本僅檢查可達性，"
            "正式 adapter 需另寫對應格式的 parser。"
            if response.status_code == httpx.codes.OK
            else f"HTTP {response.status_code}，端點可能不存在或路徑已變動。"
        )

    _print_result(
        SourceResult(
            category=category,
            name=name,
            http_status=status_line,
            field_sample=field_sample,
            conclusion=conclusion,
            confidence_note=confidence_note,
        )
    )


def run_post_form(
    client: httpx.Client,
    *,
    category: str,
    name: str,
    url: str,
    data: dict[str, Any],
    headers: dict[str, str] | None = None,
    confidence_note: str = "",
) -> None:
    """對需要 POST 表單的來源（如 MOPS）發出一次查證請求。"""
    try:
        response = client.post(url, data=data, headers=headers, timeout=TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        _print_result(
            SourceResult(
                category=category,
                name=name,
                http_status="EXCEPTION",
                field_sample="(無回應)",
                conclusion=f"POST 請求失敗：{exc!r}",
                confidence_note=confidence_note,
            )
        )
        return
    body_preview = response.text[:300].replace("\n", " ")
    _print_result(
        SourceResult(
            category=category,
            name=name,
            http_status=f"{response.status_code} {response.reason_phrase}",
            field_sample=f"(前 300 字元): {body_preview!r}",
            conclusion=(
                "HTTP 200，需人工檢視是否為預期的公告列表 HTML/JSON（此端點過往需要正確的編碼與"
                "隱藏欄位，本腳本只做最小可達性測試）。"
                if response.status_code == httpx.codes.OK
                else f"HTTP {response.status_code}，端點、表單欄位或編碼可能已變動。"
            ),
            confidence_note=confidence_note,
        )
    )


def skip(category: str, name: str, reason: str) -> None:
    _print_result(
        SourceResult(
            category=category,
            name=name,
            http_status="SKIPPED",
            field_sample="(未發出請求)",
            conclusion=reason,
        )
    )


# ---------------------------------------------------------------------------
# S-2 台股籌碼面（CEO 裁示最優先）—— 不需要 API key 的來源
# ---------------------------------------------------------------------------


def check_s2_sources(client: httpx.Client) -> None:
    print("\n" + "=" * 72)
    print("S-2 台股籌碼面（三大法人買賣超 / 融資融券 / 借券）—— 最優先")
    print("=" * 72)

    run_get(
        client,
        category="S-2",
        name="TWSE OpenAPI｜三大法人買賣超日報 (fund/T86)",
        url="https://openapi.twse.com.tw/v1/fund/T86",
        confidence_note=(
            "中信心：T86 是 TWSE 傳統盤後資料集代號（三大法人買賣超日報），"
            "OpenAPI 化後路徑推測為 /v1/fund/T86；回傳預期為當日『全市場』清單"
            "（非單一股票查詢參數），需自行用 stockNo 篩選 2330。"
        ),
    )
    run_get(
        client,
        category="S-2",
        name="TWSE OpenAPI｜信用交易（融資融券）餘額 (margin/MI_MARGN)",
        url="https://openapi.twse.com.tw/v1/margin/MI_MARGN",
        confidence_note="中信心：MI_MARGN 為 TWSE 融資融券餘額傳統資料集代號，OpenAPI 路徑為推測。",
    )
    run_get(
        client,
        category="S-2",
        name="TWSE OpenAPI｜有價證券借貸交易日報表（借券，猜測端點）",
        url="https://openapi.twse.com.tw/v1/exchangeReport/TWT96U",
        confidence_note=(
            "低信心：借券資料的確切 OpenAPI 資料集代號不確定，TWT96U 為憑印象猜測，"
            "很可能是錯的；404 屬預期結果之一，需 CEO 於 openapi.twse.com.tw 的 "
            "Swagger 目錄人工核對正確路徑。"
        ),
    )
    run_get(
        client,
        category="S-2",
        name="TPEx OpenAPI｜三大法人買賣金額統計表（猜測端點）",
        url="https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading",
        confidence_note=(
            "低信心：TPEx OpenAPI 的資料集命名規則與 TWSE 不同，此路徑為憑印象猜測，"
            "需 CEO 於 www.tpex.org.tw/openapi 的目錄頁核對正確路徑（含上櫃 6488 適用性）。"
        ),
    )
    run_get(
        client,
        category="S-2",
        name="TPEx OpenAPI｜融資融券餘額（猜測端點）",
        url="https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_trading",
        confidence_note="低信心：路徑為猜測，同上，待人工於官方目錄核對。",
    )

    api_key = os.environ.get("FINMIND_API_TOKEN")
    finmind_note = (
        "FINMIND_API_TOKEN 已設定，將帶 token 呼叫。"
        if api_key
        else "FINMIND_API_TOKEN 未設定，改以不帶 token 方式嘗試"
        "（FinMind 部分 dataset 未登入仍可用但額度更低，部分則會被拒絕——"
        "兩種結果都請記錄，這正是 spike 要回答的問題）。"
    )
    for dataset, zh_name in [
        ("TaiwanStockInstitutionalInvestorsBuySell", "三大法人買賣超"),
        ("TaiwanStockMarginPurchaseShortSale", "融資融券"),
        ("TaiwanStockSecuritiesLending", "借券（dataset 名稱不確定，見信心備註）"),
    ]:
        params: dict[str, Any] = {
            "dataset": dataset,
            "data_id": TW_SYMBOL_LISTED,
            "start_date": RECENT_START.isoformat(),
            "end_date": TODAY.isoformat(),
        }
        if api_key:
            params["token"] = api_key
        run_get(
            client,
            category="S-2",
            name=f"FinMind｜{zh_name} (dataset={dataset})",
            url="https://api.finmindtrade.com/api/v4/data",
            params=params,
            confidence_note=(
                f"{finmind_note} dataset 名稱信心：{'中' if dataset != 'TaiwanStockSecuritiesLending' else '低（借券 dataset 名稱為猜測，可能是 TaiwanStockShortSaleBalances 或其他名稱，需查 FinMind 官方文件 https://finmindtrade.com/analysis/#/data/api 核對）'}"
            ),
        )


# ---------------------------------------------------------------------------
# S-1 基本面 —— 台股優先、美股次之
# ---------------------------------------------------------------------------


def check_s1_sources(client: httpx.Client) -> None:
    print("\n" + "=" * 72)
    print("S-1 基本面（EPS / 本益比 / 殖利率 / 淨值比 / 月營收）—— 次優先")
    print("=" * 72)

    run_get(
        client,
        category="S-1",
        name="TWSE OpenAPI｜個股日本益比、殖利率及股價淨值比 (BWIBBU_ALL)",
        url="https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
        confidence_note=(
            "中高信心：BWIBBU 是 TWSE 這份資料集的傳統代號，OpenAPI 版本常見以 "
            "_ALL 後綴表示『全市場當日』清單，需自行篩選 2330。"
        ),
    )

    roc_year = TODAY.year - 1911
    month = TODAY.month - 1 or 12
    year_for_month = roc_year if TODAY.month != 1 else roc_year - 1
    run_get(
        client,
        category="S-1",
        name="MOPS（公開資訊觀測站）｜上市公司月營收彙總表（HTML，猜測端點）",
        url=f"https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{year_for_month}_{month}.html",
        confidence_note=(
            "中信心：mopsov.twse.com.tw/nas/t21/sii/t21sc03_<民國年>_<月>.html 為業界常引用的"
            "月營收彙總表legacy 路徑，回傳為 HTML 表格（含 big5 編碼疑慮）而非 JSON，"
            "本次查證用月份為上月（{}）。".format(f"{year_for_month}/{month:02d}")
        ),
        parse_json=False,
    )

    finmind_token = os.environ.get("FINMIND_API_TOKEN")
    for dataset, zh_name in [
        ("TaiwanStockFinancialStatements", "財報（含 EPS 相關科目）"),
        ("TaiwanStockMonthRevenue", "月營收"),
    ]:
        params: dict[str, Any] = {
            "dataset": dataset,
            "data_id": TW_SYMBOL_LISTED,
            "start_date": (TODAY - timedelta(days=400)).isoformat(),
            "end_date": TODAY.isoformat(),
        }
        if finmind_token:
            params["token"] = finmind_token
        run_get(
            client,
            category="S-1",
            name=f"FinMind｜{zh_name} (dataset={dataset})",
            url="https://api.finmindtrade.com/api/v4/data",
            params=params,
            confidence_note="中信心：dataset 名稱依 FinMind 慣例命名推測，未逐字核對官方文件。",
        )

    av_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not av_key:
        skip(
            "S-1",
            "Alpha Vantage｜OVERVIEW（含 GICS Sector，一次查證兩用）",
            "跳過條件：環境變數 ALPHA_VANTAGE_API_KEY 未設定。"
            "若要測試，請先在本機環境變數設定免費申請到的 key 再重跑本腳本，"
            "本腳本絕不內建任何金鑰。",
        )
        skip(
            "S-1",
            "Alpha Vantage｜EARNINGS",
            "跳過條件同上：ALPHA_VANTAGE_API_KEY 未設定。",
        )
    else:
        run_get(
            client,
            category="S-1",
            name="Alpha Vantage｜OVERVIEW（含 GICS Sector，一次查證兩用）",
            url="https://www.alphavantage.co/query",
            params={"function": "OVERVIEW", "symbol": US_SYMBOL, "apikey": av_key},
            confidence_note=(
                "高信心：OVERVIEW 是 Alpha Vantage 文件明載的公開端點；"
                "**重要**：與 Phase 7 日線查詢共用同一個 25 req/day 免費額度，"
                "本次查證會消耗一次額度。"
            ),
        )
        run_get(
            client,
            category="S-1",
            name="Alpha Vantage｜EARNINGS",
            url="https://www.alphavantage.co/query",
            params={"function": "EARNINGS", "symbol": US_SYMBOL, "apikey": av_key},
            confidence_note="高信心：官方文件端點；同樣消耗共用額度，請確認當日額度是否足夠。",
        )

    run_get(
        client,
        category="S-1",
        name="Yahoo Finance（yfinance 同款未公開端點）｜quoteSummary fundamentals",
        url=f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{US_SYMBOL}",
        params={
            "modules": "defaultKeyStatistics,financialData,summaryDetail,earnings",
        },
        headers=BROWSER_HEADERS,
        confidence_note=(
            "低~中信心：quoteSummary 是 yfinance 套件內部實際呼叫的未公開端點之一，"
            "與既有 app/data/providers/yfinance.py 使用的 v8/finance/chart 是同一家但不同端點，"
            "未在本產品驗證過；Yahoo 對此類端點的封鎖／改版風險與既有備援來源同級。"
        ),
    )


# ---------------------------------------------------------------------------
# S-3 消息面 —— 最後盤點，預設傾向「本期不做」
# ---------------------------------------------------------------------------


def check_s3_sources(client: httpx.Client) -> None:
    print("\n" + "=" * 72)
    print("S-3 消息面（個股新聞／公告）—— 最後盤點，PRD 預設傾向本期不做")
    print("=" * 72)

    run_post_form(
        client,
        category="S-3",
        name="MOPS（公開資訊觀測站）｜重大訊息公告查詢（猜測表單端點）",
        url="https://mops.twse.com.tw/mops/web/ajax_t05st02",
        data={
            "encodeURIComponent": "1",
            "step": "1",
            "firstin": "1",
            "off": "1",
            "co_id": TW_SYMBOL_LISTED,
        },
        confidence_note=(
            "低信心：MOPS 重大訊息查詢傳統上是 POST 表單、部分頁面用 big5 編碼、"
            "無官方 JSON API 文件；本腳本只做最小可達性測試，"
            "無法確認回傳內容是否真的是 2330 的公告列表，需人工開瀏覽器比對。"
        ),
    )

    finmind_token = os.environ.get("FINMIND_API_TOKEN")
    params: dict[str, Any] = {
        "dataset": "TaiwanStockNews",
        "data_id": TW_SYMBOL_LISTED,
        "start_date": RECENT_START.isoformat(),
        "end_date": TODAY.isoformat(),
    }
    if finmind_token:
        params["token"] = finmind_token
    run_get(
        client,
        category="S-3",
        name="FinMind｜新聞 (dataset=TaiwanStockNews，是否存在待驗證)",
        url="https://api.finmindtrade.com/api/v4/data",
        params=params,
        confidence_note="低信心：不確定 FinMind 免費層是否真的有這個 dataset，這正是本次要驗證的問題。",
    )

    av_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not av_key:
        skip(
            "S-3",
            "Alpha Vantage｜NEWS_SENTIMENT",
            "跳過條件：環境變數 ALPHA_VANTAGE_API_KEY 未設定。"
            "另提醒：即使可行，其 sentiment 分數依 PRD 需風控官單獨核准才能呈現，"
            "本腳本只驗證『抓不抓得到』，不代表可以直接上線。",
        )
    else:
        run_get(
            client,
            category="S-3",
            name="Alpha Vantage｜NEWS_SENTIMENT",
            url="https://www.alphavantage.co/query",
            params={"function": "NEWS_SENTIMENT", "tickers": US_SYMBOL, "apikey": av_key},
            confidence_note=(
                "高信心端點存在，但同樣消耗共用 25 req/day 額度；"
                "sentiment 分數呈現需風控官另外核准（不在本腳本查證範圍）。"
            ),
        )

    run_get(
        client,
        category="S-3",
        name="Yahoo Finance（yfinance 同款未公開端點）｜新聞搜尋",
        url="https://query2.finance.yahoo.com/v1/finance/search",
        params={"q": US_SYMBOL, "newsCount": 5},
        headers=BROWSER_HEADERS,
        confidence_note="低信心：未公開端點，僅供了解美股新聞可行性的參考，非本產品優先項。",
    )


def print_summary_table() -> None:
    print("\n" + "=" * 72)
    print("總結表（請將此區塊完整複製回填至 work/stock-desk-phase8-spike-盤點.md）")
    print("=" * 72)
    header = f"{'分類':<5} | {'源名稱':<55} | {'HTTP 狀態':<20} | 結論"
    print(header)
    print("-" * len(header))
    for r in RESULTS:
        name = r.name if len(r.name) <= 55 else r.name[:52] + "..."
        print(f"{r.category:<5} | {name:<55} | {r.http_status:<20} | {r.conclusion}")

    ok_count = sum(1 for r in RESULTS if r.http_status.startswith("200"))
    skip_count = sum(1 for r in RESULTS if r.http_status == "SKIPPED")
    fail_count = len(RESULTS) - ok_count - skip_count
    print(
        f"\n共查證 {len(RESULTS)} 個來源：HTTP 200 有 {ok_count} 個、"
        f"跳過 {skip_count} 個、其餘（非 200 / 例外）{fail_count} 個。"
    )
    print(
        "\n提醒：HTTP 200 只代表『打得通』，不代表欄位內容就是預期的 schema——"
        "務必人工核對每一筆的『欄位樣本』是否真的是三大法人買賣超 / 本益比 / "
        "新聞列表等預期內容，再回填盤點表的結論欄。"
    )


def main() -> None:
    print("Stock Desk Phase 8 — 資料源 spike 查證")
    print(f"執行時間（本機時區）：{TODAY.isoformat()}")
    print(f"查證標的：台股上市={TW_SYMBOL_LISTED}、台股上櫃={TW_SYMBOL_OTC}、美股={US_SYMBOL}")
    print(
        "本腳本只發出最小查證請求並如實記錄結果；任一來源失敗都會被捕捉並繼續下一個，"
        "不會中斷整個腳本。"
    )

    with httpx.Client(follow_redirects=True) as client:
        # 依 CEO 裁示優先序執行：S-2 > S-1 > S-3。
        check_s2_sources(client)
        check_s1_sources(client)
        check_s3_sources(client)

    print_summary_table()


if __name__ == "__main__":
    main()
