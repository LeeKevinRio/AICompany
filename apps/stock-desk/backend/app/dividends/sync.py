"""CEO 本機一鍵同步工具 -- 除權息事件（TWSE 除權除息計算結果表）。

    uv run python -m app.dividends.sync

## 背景

同 ``app.directory.sync``：本雲端開發環境對財經網域的 egress 已知被封鎖，所以
這支工具不能假設可以在雲端即時抓到 TWSE 的真實資料。同步動作由 CEO（或任何有
網路的機器）手動觸發，結果寫進本機 SQLite（``STOCK_DESK_DB_PATH``，預設
``./data/stock-desk.db`` 的 ``dividend_events`` 表），之後可離線查詢。

## 為什麼要重複跑

上游資料集是一段滾動視窗（近期的除權息結果），不是完整歷史。寫入是以
``(symbol, market, ex_date)`` 為鍵的冪等 upsert，所以**定期重跑會逐步累積**
歷史覆蓋；重跑同一天的資料不會產生重複列。反過來說，第一次同步之後的回測只
還原得了資料庫裡有的那段區間——這件事由回測 API 誠實揭露，不在這裡假裝。

## 網路不可達時的行為

adapter 已把 ``httpx.TransportError``（DNS 失敗、連線被拒、proxy CONNECT 被擋）
轉成 ``ok=False`` 加一句可讀的中文原因，不會讓例外往外傳；``main()`` 另外印出
「請在有網路的機器重跑」的明確指引，而不是印一段裸 traceback。

## 端點尚未驗證

端點路徑與欄位名稱是**推斷**的（見 ``app.dividends.providers`` 檔頭）。第一次
真的有網路時若回 404 或解析不出任何列，那是預期中的待驗狀態，終端會直接說出
來，需由 data-engineer 對照官方 Swagger 覆核，不是這支工具的 bug。

## 測試

``tests/test_dividends_sync.py`` 用 ``httpx.MockTransport`` 合成 fixture 驗證
parsing、冪等與不可達行為，一律不打外網。
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.data.http import RateLimitedClient
from app.dividends.providers import (
    TWSE_OPENAPI_BASE_URL,
    DividendFetchResult,
    TwseDividendAdapter,
)
from app.dividends.store import DividendEventStore

_BANNER_RULE = "=" * 72

_NETWORK_GUIDANCE = (
    "無法連線到 TWSE OpenAPI。本雲端開發環境對財經網域的 egress 已知被封鎖，"
    "這是預期中的限制，不代表程式有 bug。\n"
    "請改在有網路的機器（例如 CEO 本機）執行：\n"
    "  cd apps/stock-desk/backend\n"
    "  uv run python -m app.dividends.sync\n"
    "執行結果會寫入 STOCK_DESK_DB_PATH 指到的 SQLite 檔（預設 ./data/stock-desk.db），"
    "之後這台雲端環境也能離線讀到剛才同步的除權息資料（把資料庫檔案帶過來即可）。"
)

_SCHEMA_GUIDANCE = (
    "端點路徑與欄位名稱目前是依慣例推斷、尚未經實際回應驗證（見 "
    "app/dividends/providers.py 檔頭）。若上面的原因是 HTTP 404 或「沒有任何可解析的列」，"
    "請交由 data-engineer 對照 openapi.twse.com.tw 的官方文件覆核資料集代號與欄位名稱，"
    "覆核前不要用猜的欄位硬上——寧可沒有股利資料（回測會誠實標示「未還原」），"
    "也不要有一份錯的股利資料。"
)


def sync_dividends(
    *,
    store: DividendEventStore,
    adapter: TwseDividendAdapter,
    synced_at: datetime | None = None,
) -> DividendFetchResult:
    """Fetch the ex-dividend dataset and upsert whatever parsed cleanly."""
    moment = synced_at if synced_at is not None else datetime.now(UTC)
    result = adapter.fetch()
    if result.ok and result.events:
        store.upsert(list(result.events), synced_at=moment)
    return result


def _print_banner() -> None:
    print(_BANNER_RULE)
    print("除權息事件同步 -- TWSE 除權除息計算結果表（上市；上櫃本期未涵蓋）")
    print(_BANNER_RULE)


def _print_result(result: DividendFetchResult) -> None:
    verdict = "PASS" if result.ok else "FAIL/UNREACHABLE"
    print(f"[{result.source}] {verdict}")
    if result.ok:
        print(f"  寫入 {len(result.events)} 筆，as_of={result.as_of.isoformat()}")
        if result.skipped_rows:
            print(
                f"  略過 {result.skipped_rows} 列無法解析的資料（覆蓋率不完整，"
                "這些個股的回測會標示為未還原）"
            )
    else:
        print(f"  原因：{result.reason}")


def _is_unreachable(result: DividendFetchResult) -> bool:
    return (not result.ok) and result.reason is not None and "連線失敗" in result.reason


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.dividends.sync",
        description=(
            "CEO 本機一鍵同步除權息事件：抓 TWSE OpenAPI 除權除息計算結果表，寫入本機 "
            "SQLite 供回測還原使用。雲端開發環境財經網域被封鎖，本工具設計為在有網路的"
            "機器上執行；跑不到網路時會印出明確指引，不會拋出裸 traceback。"
        ),
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="覆寫資料庫路徑；未指定時沿用 STOCK_DESK_DB_PATH（預設 ./data/stock-desk.db）",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db_path) if args.db_path is not None else None
    store = DividendEventStore(db_path)
    client = RateLimitedClient(base_url=TWSE_OPENAPI_BASE_URL, min_interval_seconds=0.5)
    adapter = TwseDividendAdapter(client=client)

    _print_banner()
    try:
        result = sync_dividends(store=store, adapter=adapter)
    finally:
        adapter.close()
        client.close()

    _print_result(result)
    print(f"資料庫：{store.db_path}")
    print(f"目前除權息事件總筆數：{store.count()}")

    if not result.ok:
        print()
        print(_NETWORK_GUIDANCE if _is_unreachable(result) else _SCHEMA_GUIDANCE, file=sys.stderr)
        return 1

    _print_banner()
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())
