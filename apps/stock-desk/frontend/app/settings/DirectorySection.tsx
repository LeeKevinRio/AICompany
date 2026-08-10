"use client";

/**
 * 「證券目錄」說明區塊(work/機會清單.md D1「設定頁」項,2026-08-10 派工單)。
 *
 * 不是同步觸發器:目錄同步是 CLI 指令(`app/directory/sync.py`,由後端主機的人
 * 手動執行,見 `app/api/deps.py` 的 `_default_directory_store` 註解),這裡沒有
 * 同步按鈕,因為前端沒有可呼叫的同步端點——顯示一個假按鈕會讓使用者以為按了
 * 就會觸發動作。這個區塊純粹是「怎麼同步」與「目前狀不狀態」兩件事實的陳述,
 * 呼應 `DataSourcesSection.tsx` 同樣的「設定說明,非即時健康面板」定位。
 *
 * 狀態旗標沒有專用端點,借用 `GET /api/directory/search` 的 `directory_synced`
 * (`useDirectoryStatus`,`queries.ts`)——後端唯一會誠實回報這面旗標的呼叫。
 * 未同步時沿用 `directorySearch.ts` 既有風控核可句 `DIRECTORY_NOT_SYNCED_NOTICE`
 * 逐字,不重寫。
 *
 * 已同步文案 VETO 退修(風控快審波次 1,2026-08-10,`work/reviews/波次1文案裁決.md`
 * D4):原「證券目錄已同步，代號自動完成可用。」暗示「已同步」等於「完整且最新」,
 * 與本檔第一段揭露的事實(只知道目錄非空,無法判斷內容完整度)矛盾。改用風控逐字
 * 核可句(下方 `DIRECTORY_SYNCED_APPROVED_TEXT`)。
 */

import { formatDateTime } from "../lib/format";
import { DIRECTORY_NOT_SYNCED_NOTICE } from "../lib/directorySearch";
import { useDirectoryStatus } from "../lib/queries";
import { SkeletonBlock } from "../components/SkeletonBlock";
import { ErrorPanel } from "../components/ErrorPanel";

const SYNC_COMMAND = "uv run python -m app.directory.sync";

/**
 * 風控核可句(`work/reviews/波次1文案裁決.md` D4,逐字),取代原先暗示「已同步=
 * 完整且最新」的「證券目錄已同步，代號自動完成可用。」。
 */
const DIRECTORY_SYNCED_APPROVED_TEXT =
  "證券目錄有資料,代號自動完成可用。目錄僅涵蓋台股上市與上櫃,不含美股;且本系統只知道目錄非空,無法判斷內容是否完整或最新。";

export function DirectorySection() {
  const status = useDirectoryStatus();

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-semibold text-neutral-100">證券目錄</h2>
      <p className="mt-1 text-xs text-neutral-500">
        NavBar 與「新增部位」表單的代號自動完成，仰賴這份本機證券目錄快取；目錄未同步時，這兩處僅支援輸入完整代號直接查詢。
      </p>

      <div className="mt-3 rounded-md border border-neutral-800 bg-neutral-950/40 p-3">
        <p className="text-xs text-neutral-400">手動同步指令（於後端主機執行）：</p>
        <code className="mt-1 block break-all rounded bg-neutral-900 px-2 py-1 text-xs text-neutral-200">
          {SYNC_COMMAND}
        </code>
      </div>

      <div className="mt-3">
        {status.isPending && <SkeletonBlock className="h-6 w-48" />}
        {status.isError && <ErrorPanel label="無法查詢證券目錄同步狀態" error={status.error} />}
        {status.isSuccess && (
          <>
            <span
              className={`inline-block rounded border px-2 py-0.5 text-xs ${
                status.data.directory_synced
                  ? "border-emerald-800 bg-emerald-950/40 text-emerald-300"
                  : "border-amber-800 bg-amber-950/40 text-amber-300"
              }`}
            >
              {status.data.directory_synced ? "已同步" : "尚未同步"}
            </span>
            <p className="mt-2 text-xs text-neutral-500">
              {status.data.directory_synced ? DIRECTORY_SYNCED_APPROVED_TEXT : DIRECTORY_NOT_SYNCED_NOTICE}
            </p>
            {/*
              `SearchResponse.as_of`（backend/app/api/directory.py，驗證）是這次
              查詢的產生時間，不是目錄實際同步的時間——後端沒有暴露同步時間的
              欄位，此處據實只稱「查詢時間」，不得誤植為「同步時間」。

              D4 required(波次1文案裁決.md,2026-08-10):補「(非目錄同步時間)」,
              避免讀者把這個時間戳誤認成目錄的同步時間。
            */}
            <p className="mt-1 text-xs text-neutral-600">
              本次查詢時間：{formatDateTime(status.data.as_of)}(非目錄同步時間)
            </p>
          </>
        )}
      </div>
    </section>
  );
}
