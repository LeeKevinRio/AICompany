"""CEO 本機一鍵同步工具 -- 證券目錄（代號/公司名稱/市場）。

    uv run python -m app.directory.sync

## 背景

`work/stock-desk-代號目錄-PRD.md`（FR-1）與 CEO 裁示紀錄：本雲端開發環境對
財經網域的 egress 已知被封鎖（同 `apps/stock-desk/scripts/verify_market_data.py`
與 `tests/fixtures/README.md` 記錄的既有限制），所以本工具**不能**假設可以在
雲端環境即時抓到 TWSE/TPEx 的真實清單。同步動作必須是 CEO（或任何有網路的
機器）手動觸發，結果寫進本機 SQLite（`STOCK_DESK_DB_PATH`，預設
`./data/stock-desk.db` 的 `security_directory` 表），之後可離線查詢。

## 三個來源各自獨立成敗（AC-2）

TWSE 上市清單、TPEx 上櫃清單與 TWSE 上市公司產業別（`t187ap03_L`）分開抓、
分開寫入：其中一個來源逾時/格式錯誤/連線被拒，另一個成功的來源仍會正常落地，
終端輸出會明確標示每個來源的 PASS/FAIL 及原因，不會因為一個來源失敗就整批放棄，
也不會用另一個來源的資料去猜失敗來源的內容。

## 產業別落地與持倉回填（本次同步一併完成）

同步流程依序做三件事，任何一段失敗都不影響前一段已寫入的結果：

1. 抓上市/上櫃清單，寫入 `security_directory` 的代號/名稱/市場欄。
2. 抓 `t187ap03_L` 的產業別**代碼**，經 `app/directory/twse_sector_codes.py`
   轉成中文名稱後寫進同一列的 `sector` 欄。代碼不在對照表、或解析出的名稱不在
   `app/positions/sectors.py` 封閉清單內，一律**不寫入**並在終端列出原因
   （見 `app.directory.sector_resolve` 的模組說明）。上櫃與 ETF 不在這個資料集
   裡，其 `sector` 維持 NULL。
3. 回填既有持倉：`positions` 表中**產業別為空**且市場為 TW 的持倉，若目錄查得到
   產業別就補上；**已有值的一律不覆蓋**（使用者手選的優先）。終端會印出補了幾檔、
   跳過幾檔與各自原因。

只想重跑第 3 步（不連網、直接用上次同步好的目錄）：

    uv run python -m app.directory.sync --backfill-sectors

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
from app.directory.sector_backfill import SectorBackfillReport, backfill_position_sectors
from app.directory.sector_resolve import SectorResolution, resolve_sector_assignments
from app.directory.store import SecurityDirectoryStore
from app.positions.store import PositionStore

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


def sync_sectors(
    *,
    store: SecurityDirectoryStore,
    sector_adapter: TwseSectorProfileAdapter,
) -> tuple[SectorProfileFetchResult, SectorResolution | None, int]:
    """Fetch the 產業別 dataset and write the resolvable categories onto the directory.

    Independent of :func:`sync_directory` in exactly the way the two symbol
    sources are independent of each other (AC-2): this runs after them and
    only ever UPDATEs rows they wrote, so if this source is unreachable the
    symbol/name sync still stands, and if it succeeds while a symbol source
    failed, the categories still land on whatever rows do exist.

    Returns ``(fetch result, resolution or None, rows matched)``. ``rows
    matched`` is below ``len(resolution.assignments)`` whenever the sector
    dataset names a listed company the directory's own source did not return
    -- reported rather than fixed by inserting a row (see
    :meth:`SecurityDirectoryStore.apply_sectors`).
    """
    result = sector_adapter.fetch()
    if not result.ok:
        return result, None, 0
    resolution = resolve_sector_assignments(
        result.entries, as_of=result.as_of, source=result.source
    )
    matched = store.apply_sectors(resolution.assignments)
    return result, resolution, matched


def _print_banner() -> None:
    print(_BANNER_RULE)
    print("證券目錄同步 -- TWSE 上市清單 + TPEx 上櫃清單 + TWSE 上市公司產業別")
    print(_BANNER_RULE)


def _print_result(result: DirectoryFetchResult) -> None:
    verdict = "PASS" if result.ok else "FAIL/UNREACHABLE"
    print(f"[{result.source}] {verdict}")
    if result.ok:
        print(f"  寫入 {len(result.entries)} 筆，as_of={result.as_of.isoformat()}")
    else:
        print(f"  原因：{result.reason}")


def _print_sector_sync_result(
    result: SectorProfileFetchResult,
    resolution: SectorResolution | None,
    matched: int,
) -> None:
    """Report the sector pass: what landed, what was dropped, and why.

    Every dropped row is named with its reason. A silent "N 筆寫入" that hides
    a mapping-table gap would defeat the point of the UNKNOWN_CODE rule.
    """
    verdict = "PASS" if result.ok else "FAIL/UNREACHABLE"
    print(f"[{result.source}] {verdict}（產業別）")
    if not result.ok or resolution is None:
        print(f"  原因：{result.reason}")
        print("  產業別欄未更新；目錄的代號/名稱資料不受影響。")
        return
    print(
        f"  官方公司列 {len(result.entries)} 筆，可寫入 {len(resolution.assignments)} 筆，"
        f"實際更新目錄 {matched} 列，as_of={result.as_of.isoformat()}"
    )
    not_in_directory = len(resolution.assignments) - matched
    if not_in_directory > 0:
        print(
            f"  其中 {not_in_directory} 筆的代號不在目錄中（產業別來源與代號來源是不同資料集），"
            "未新增目錄列。"
        )
    if resolution.unknown_codes:
        print(
            f"  略過 {resolution.unknown_code_rows} 筆：產業別代碼不在對照表中"
            f"（{'、'.join(resolution.unknown_codes)}），需人工補進 "
            "app/directory/twse_sector_codes.py 後重跑，不以猜測值寫入。"
        )
    if resolution.outside_closed_list_names:
        outside = "、".join(resolution.outside_closed_list_names)
        print(
            f"  略過 {resolution.outside_closed_list_rows} 筆：代碼可解析但名稱不在 "
            f"app/positions/sectors.py 封閉清單內（{outside}），需先經裁決納入清單。"
        )
    if resolution.blank_code_rows:
        print(f"  略過 {resolution.blank_code_rows} 筆：該列產業別欄為空。")
    if resolution.duplicate_symbol_rows:
        print(f"  略過 {resolution.duplicate_symbol_rows} 筆：同一代號重複出現，只取第一筆。")


def _print_backfill_report(report: SectorBackfillReport) -> None:
    """Report the holdings backfill: filled, skipped, and each skip's reason."""
    print(f"持倉產業別回填：檢視 {report.considered_count} 檔，補上 {report.filled_count} 檔，"
          f"跳過 {report.skipped_count} 檔")
    for symbol, sector in report.filled:
        print(f"  補上 {symbol} -> {sector}")
    if report.skipped_already_set:
        print(f"  跳過 {report.skipped_already_set} 檔：已有產業別，不覆蓋（手動填的值優先）。")
    if report.skipped_not_tw:
        print(f"  跳過 {report.skipped_not_tw} 檔：非台股持倉，不適用台灣證交所產業別分類。")
    if report.skipped_not_in_directory:
        print(f"  跳過 {report.skipped_not_in_directory} 檔：證券目錄查無此代號。")
    if report.skipped_directory_has_no_sector:
        print(
            f"  跳過 {report.skipped_directory_has_no_sector} 檔："
            "目錄有此代號但沒有產業別（上櫃與 ETF 不在產業別來源的涵蓋範圍）。"
        )
    if report.skipped_invalid_directory_sector:
        print(
            f"  跳過 {report.skipped_invalid_directory_sector} 檔："
            "目錄中的產業別不在目前封閉清單內，未寫入持倉。"
        )


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
    parser.add_argument(
        "--backfill-sectors",
        action="store_true",
        help=(
            "只跑持倉產業別回填：不連網，直接用上次同步好的目錄，"
            "把產業別為空的台股持倉補上；已有值的一律不覆蓋"
        ),
    )
    args = parser.parse_args(argv)

    if args.backfill_sectors:
        db_path = Path(args.db_path) if args.db_path is not None else None
        store = SecurityDirectoryStore(db_path)
        print(_BANNER_RULE)
        print("持倉產業別回填 -- 只補空白值，不覆蓋既有值")
        print(_BANNER_RULE)
        print(f"資料庫：{store.db_path}")
        print(f"目錄總筆數：{store.count()}（其中有產業別：{store.sector_count()}）")
        _print_backfill_report(
            backfill_position_sectors(
                position_store=PositionStore(store.db_path),
                directory_store=store,
            )
        )
        return 0

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
    profile_client = RateLimitedClient(base_url=TWSE_OPENAPI_BASE_URL, min_interval_seconds=0.5)
    twse_adapter = TwseDirectoryAdapter(client=twse_client)
    tpex_adapter = TpexDirectoryAdapter(client=tpex_client)
    profile_adapter = TwseSectorProfileAdapter(client=profile_client)

    _print_banner()
    try:
        results = sync_directory(store=store, twse_adapter=twse_adapter, tpex_adapter=tpex_adapter)
        # Runs even when a symbol source failed: it only ever UPDATEs rows that
        # already exist, so the worst case is that it matches nothing.
        sector_result, resolution, matched = sync_sectors(
            store=store, sector_adapter=profile_adapter
        )
    finally:
        twse_adapter.close()
        tpex_adapter.close()
        profile_adapter.close()

    for result in results:
        _print_result(result)
    _print_sector_sync_result(sector_result, resolution, matched)

    print(f"資料庫：{store.db_path}")
    print(f"目前目錄總筆數：{store.count()}（其中有產業別：{store.sector_count()}）")

    # The backfill reads only what is already in SQLite, so it is worth running
    # even after a failed fetch -- an earlier sync's directory can still fill a
    # holding added since. It never overwrites, so it cannot make things worse.
    _print_backfill_report(
        backfill_position_sectors(
            position_store=PositionStore(store.db_path),
            directory_store=store,
        )
    )

    if _all_unreachable(results):
        print()
        print(_NETWORK_GUIDANCE, file=sys.stderr)
        return 1

    any_failed = any(not result.ok for result in results) or not sector_result.ok
    _print_banner()
    return 1 if (any_failed and store.count() == 0) else 0


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())
