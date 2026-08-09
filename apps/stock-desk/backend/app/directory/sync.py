"""CEO 本機一鍵同步工具 -- 證券目錄（代號/公司名稱/市場）。

    uv run python -m app.directory.sync

## 背景

`work/stock-desk-代號目錄-PRD.md`（FR-1）與 CEO 裁示紀錄：本雲端開發環境對
財經網域的 egress 已知被封鎖（同 `apps/stock-desk/scripts/verify_market_data.py`
與 `tests/fixtures/README.md` 記錄的既有限制），所以本工具**不能**假設可以在
雲端環境即時抓到 TWSE/TPEx 的真實清單。同步動作必須是 CEO（或任何有網路的
機器）手動觸發，結果寫進本機 SQLite（`STOCK_DESK_DB_PATH`，預設
`./data/stock-desk.db` 的 `security_directory` 表），之後可離線查詢。

## 兩個來源各自獨立成敗（AC-2）

TWSE 上市清單與 TPEx 上櫃清單分開抓、分開寫入：其中一個來源逾時/格式錯誤/
連線被拒，另一個成功的來源仍會正常落地，終端輸出會明確標示每個來源的
PASS/FAIL 及原因，不會因為一個來源失敗就整批放棄，也不會用另一個來源的資料
去猜失敗來源的內容。

## 網路不可達時的行為

這支工具在打不到網路（`httpx.TransportError`：DNS 失敗、連線被拒、proxy
CONNECT 被擋等）時，兩個來源各自的 adapter（`app.directory.providers`）已經
把這類錯誤轉成 `ok=False` 加上一句可讀的中文原因，不會讓例外往外傳到這支
CLI；`main()` 額外在兩個來源都不可達時印出一段「請在有網路的機器重跑」的
明確指引，而不是印出一段裸 traceback 讓人看不懂發生了什麼事。

## 測試

`apps/stock-desk/backend/tests/test_directory_providers.py` 與
`tests/test_directory_sync.py` 用 `httpx.MockTransport` 合成 fixture 驗證
parsing 與部分失敗行為，一律不打外網：

    cd apps/stock-desk/backend
    uv run pytest tests/test_directory_providers.py tests/test_directory_sync.py -v
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.data.http import RateLimitedClient
from app.directory.providers import (
    TPEX_OPENAPI_BASE_URL,
    TWSE_OPENAPI_BASE_URL,
    DirectoryFetchResult,
    TpexDirectoryAdapter,
    TwseDirectoryAdapter,
)
from app.directory.store import SecurityDirectoryStore

_BANNER_RULE = "=" * 72

_NETWORK_GUIDANCE = (
    "兩個來源皆無法連線。本雲端開發環境對財經網域的 egress 已知被封鎖，"
    "這是預期中的限制，不代表程式有 bug。\n"
    "請改在有網路的機器（例如 CEO 本機）執行：\n"
    "  cd apps/stock-desk/backend\n"
    "  uv run python -m app.directory.sync\n"
    "執行結果會寫入 STOCK_DESK_DB_PATH 指到的 SQLite 檔（預設 ./data/stock-desk.db），"
    "之後這台雲端環境也能離線讀到剛才同步的目錄資料（把資料庫檔案帶過來即可）。"
)


def sync_directory(
    *,
    store: SecurityDirectoryStore,
    twse_adapter: TwseDirectoryAdapter,
    tpex_adapter: TpexDirectoryAdapter,
    synced_at: datetime | None = None,
) -> list[DirectoryFetchResult]:
    """Fetch both sources independently and upsert whichever ones succeed.

    Each source's rows are written immediately after that source's own fetch
    succeeds, so one source failing never withholds the other's already-fetched
    rows (AC-2). Returns both sources' raw results for the CLI to report on.
    """
    moment = synced_at if synced_at is not None else datetime.now(UTC)
    results: list[DirectoryFetchResult] = []
    for adapter in (twse_adapter, tpex_adapter):
        result = adapter.fetch()
        results.append(result)
        if result.ok and result.entries:
            store.upsert(list(result.entries), synced_at=moment)
    return results


def _print_banner() -> None:
    print(_BANNER_RULE)
    print("證券目錄同步 -- TWSE 上市清單 + TPEx 上櫃清單")
    print(_BANNER_RULE)


def _print_result(result: DirectoryFetchResult) -> None:
    verdict = "PASS" if result.ok else "FAIL/UNREACHABLE"
    print(f"[{result.source}] {verdict}")
    if result.ok:
        print(f"  寫入 {len(result.entries)} 筆，as_of={result.as_of.isoformat()}")
    else:
        print(f"  原因：{result.reason}")


def _all_unreachable(results: Sequence[DirectoryFetchResult]) -> bool:
    return all(
        (not result.ok) and result.reason is not None and "連線失敗" in result.reason
        for result in results
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.directory.sync",
        description=(
            "CEO 本機一鍵同步證券目錄：抓 TWSE OpenAPI 上市清單與 TPEx OpenAPI 上櫃清單，"
            "寫入本機 SQLite 供離線查詢。雲端開發環境財經網域被封鎖，本工具設計為在有網路"
            "的機器上執行；跑不到網路時會印出明確指引，不會拋出裸 traceback。"
        ),
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="覆寫資料庫路徑；未指定時沿用 STOCK_DESK_DB_PATH（預設 ./data/stock-desk.db）",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db_path) if args.db_path is not None else None
    store = SecurityDirectoryStore(db_path)

    twse_client = RateLimitedClient(base_url=TWSE_OPENAPI_BASE_URL, min_interval_seconds=0.5)
    tpex_client = RateLimitedClient(base_url=TPEX_OPENAPI_BASE_URL, min_interval_seconds=0.5)
    twse_adapter = TwseDirectoryAdapter(client=twse_client)
    tpex_adapter = TpexDirectoryAdapter(client=tpex_client)

    _print_banner()
    try:
        results = sync_directory(
            store=store, twse_adapter=twse_adapter, tpex_adapter=tpex_adapter
        )
    finally:
        twse_adapter.close()
        tpex_adapter.close()

    for result in results:
        _print_result(result)

    print(f"資料庫：{store.db_path}")
    print(f"目前目錄總筆數：{store.count()}")

    if _all_unreachable(results):
        print()
        print(_NETWORK_GUIDANCE, file=sys.stderr)
        return 1

    any_failed = any(not result.ok for result in results)
    _print_banner()
    return 1 if (any_failed and store.count() == 0) else 0


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())
