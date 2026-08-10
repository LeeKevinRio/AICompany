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

## 產業清單覆核（``--verify-sectors``）

    uv run python -m app.directory.sync --verify-sectors

`app/positions/sectors.py` 的 TWSE 產業別清單標註「依公開常識整理、未經 TWSE
線上來源查證」。這個旗標抓 TWSE OpenAPI 的 ``t187ap03_L``（上市公司基本資料，
含 ``產業別`` 欄）與該清單比對，輸出「官方有我們沒有／我們有官方沒有／名稱
用字差異」到終端，並把完整報告寫成 ``work/research/產業清單覆核-<日期>.md``
草稿。**不會寫 SQLite、不會自動改 ``sectors.py``**——那是核可清單，任何差異
都回報 CEO 轉裁決，見 ``app.directory.sector_audit`` 的模組說明。與一般同步
一樣，本雲端環境打不到 TWSE 網域時會印出指引而不是裸 traceback。

## 測試

`apps/stock-desk/backend/tests/test_directory_providers.py` 與
`tests/test_directory_sync.py` 用 `httpx.MockTransport` 合成 fixture 驗證
parsing 與部分失敗行為，一律不打外網：

    cd apps/stock-desk/backend
    uv run pytest tests/test_directory_providers.py tests/test_directory_sync.py \\
        tests/test_sector_audit.py -v
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from app.data.http import RateLimitedClient
from app.directory.providers import (
    TPEX_OPENAPI_BASE_URL,
    TWSE_OPENAPI_BASE_URL,
    DirectoryFetchResult,
    SectorProfileFetchResult,
    TpexDirectoryAdapter,
    TwseDirectoryAdapter,
    TwseSectorProfileAdapter,
)
from app.directory.sector_audit import compare_sectors, render_markdown, render_terminal_lines
from app.directory.store import SecurityDirectoryStore

_BANNER_RULE = "=" * 72

#: apps/stock-desk/backend/app/directory/sync.py -> repo root (5 parents up).
_REPO_ROOT = Path(__file__).resolve().parents[5]

_NETWORK_GUIDANCE = (
    "兩個來源皆無法連線。本雲端開發環境對財經網域的 egress 已知被封鎖，"
    "這是預期中的限制，不代表程式有 bug。\n"
    "請改在有網路的機器（例如 CEO 本機）執行：\n"
    "  cd apps/stock-desk/backend\n"
    "  uv run python -m app.directory.sync\n"
    "執行結果會寫入 STOCK_DESK_DB_PATH 指到的 SQLite 檔（預設 ./data/stock-desk.db），"
    "之後這台雲端環境也能離線讀到剛才同步的目錄資料（把資料庫檔案帶過來即可）。"
)

_SECTOR_NETWORK_GUIDANCE = (
    "TWSE 產業別來源（t187ap03_L）無法連線。本雲端開發環境對財經網域的 egress "
    "已知被封鎖，這是預期中的限制，不代表程式有 bug。\n"
    "請改在有網路的機器（例如 CEO 本機）執行：\n"
    "  cd apps/stock-desk/backend\n"
    "  uv run python -m app.directory.sync --verify-sectors\n"
    "執行結果會印在終端並寫成 work/research/產業清單覆核-<日期>.md 草稿，"
    "不會自動修改 app/positions/sectors.py。"
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


def _print_sector_banner() -> None:
    print(_BANNER_RULE)
    print("產業清單覆核 -- TWSE 上市公司產業別 vs. app/positions/sectors.py")
    print(_BANNER_RULE)


def _default_sector_report_path(*, today: date | None = None) -> Path:
    moment = today if today is not None else date.today()
    return _REPO_ROOT / "work" / "research" / f"產業清單覆核-{moment.isoformat()}.md"


def run_sector_verification(
    *,
    adapter: TwseSectorProfileAdapter,
    output_path: Path | None = None,
) -> tuple[int, SectorProfileFetchResult]:
    """Fetch TWSE's per-company sector column and diff it against ``TWSE_SECTORS``.

    Never writes to the SQLite store and never touches ``sectors.py`` -- see
    ``app.directory.sector_audit``'s module docstring for why. Returns the
    process exit code and the raw fetch result so the CLI and tests can both
    inspect what happened without re-fetching.
    """
    result = adapter.fetch()
    if not result.ok:
        print(f"[{result.source}] FAIL/UNREACHABLE")
        print(f"  原因：{result.reason}")
        if result.reason is not None and "連線失敗" in result.reason:
            print()
            print(_SECTOR_NETWORK_GUIDANCE, file=sys.stderr)
        return 1, result

    print(
        f"[{result.source}] PASS -- 抓到 {len(result.entries)} 筆公司列，"
        f"as_of={result.as_of.isoformat()}"
    )
    report = compare_sectors(result.entries, as_of=result.as_of, source=result.source)
    for line in render_terminal_lines(report):
        print(line)

    resolved_output = output_path or _default_sector_report_path()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(render_markdown(report), encoding="utf-8")
    print(f"完整報告已寫入：{resolved_output}")

    return 0, result


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
    parser.add_argument(
        "--verify-sectors",
        action="store_true",
        help=(
            "改跑產業清單覆核：抓 TWSE 上市公司產業別（t187ap03_L），"
            "與 app/positions/sectors.py 比對差異並輸出報告；"
            "不寫 SQLite、不自動修改 sectors.py（見本檔案模組說明）"
        ),
    )
    parser.add_argument(
        "--sectors-output",
        type=Path,
        default=None,
        help=(
            "覆寫 --verify-sectors 報告輸出路徑；未指定時預設 "
            "work/research/產業清單覆核-<今天日期>.md"
        ),
    )
    args = parser.parse_args(argv)

    if args.verify_sectors:
        sector_client = RateLimitedClient(base_url=TWSE_OPENAPI_BASE_URL, min_interval_seconds=0.5)
        sector_adapter = TwseSectorProfileAdapter(client=sector_client)
        _print_sector_banner()
        try:
            exit_code, _ = run_sector_verification(
                adapter=sector_adapter, output_path=args.sectors_output
            )
        finally:
            sector_adapter.close()
        return exit_code

    db_path = Path(args.db_path) if args.db_path is not None else None
    store = SecurityDirectoryStore(db_path)

    twse_client = RateLimitedClient(base_url=TWSE_OPENAPI_BASE_URL, min_interval_seconds=0.5)
    tpex_client = RateLimitedClient(base_url=TPEX_OPENAPI_BASE_URL, min_interval_seconds=0.5)
    twse_adapter = TwseDirectoryAdapter(client=twse_client)
    tpex_adapter = TpexDirectoryAdapter(client=tpex_client)

    _print_banner()
    try:
        results = sync_directory(store=store, twse_adapter=twse_adapter, tpex_adapter=tpex_adapter)
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
