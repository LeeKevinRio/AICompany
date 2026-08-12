"use client";

import { ErrorPanel } from "../components/ErrorPanel";
import { SkeletonBlock } from "../components/SkeletonBlock";
import { shouldRenderAttribution } from "../lib/playbookView";
import { usePlaybookToday } from "../lib/queries";
import { DirectiveLedger } from "./DirectiveLedger";
import { ModeStatusBar } from "./ModeStatusBar";
import { PositionSnapshotTable } from "./PositionSnapshotTable";
import { SettlementPanel } from "./SettlementPanel";

/**
 * 排程台 (`/playbook`, 視覺規範 全文). 第 0 層狀態列（`ModeStatusBar`,
 * sticky）is rendered as soon as `GET /api/playbook/today` succeeds, ahead of
 * everything else, per §1's information-hierarchy table — it must never wait
 * behind the ledger/snapshot below it.
 *
 * Known limitation (see hand-off report): §0's page-level framing line and
 * §6's fixed disclaimer/資料基準日總覽 sentence are both still
 * `{PAGE_FRAMING_LINE}`-style placeholders in the visual spec itself (not yet
 * risk-compliance finalized, and no backend field carries them either), so
 * neither is rendered here — rendering a self-authored placeholder sentence
 * would violate this task's zero-invented-copy rule more than omitting it.
 */
export default function PlaybookPage() {
  const today = usePlaybookToday(true);

  return (
    <div>
      {today.isSuccess && <ModeStatusBar today={today.data} />}

      <main className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="text-2xl font-bold text-neutral-100">排程台</h1>

        {today.isPending && (
          <div className="mt-6 space-y-3">
            <SkeletonBlock className="h-16 w-full" />
            <SkeletonBlock className="h-40 w-full" />
            <SkeletonBlock className="h-40 w-full" />
          </div>
        )}

        {today.isError && (
          <div className="mt-6">
            <ErrorPanel label="無法載入排程台資料" error={today.error} />
          </div>
        )}

        {today.isSuccess && (
          <>
            {/* 風控 R2 常駐歸屬語；EMPTY 契約：null 時不渲染整行。 */}
            {shouldRenderAttribution(today.data.attribution) && (
              <p className="mt-4 rounded-md border border-neutral-700 bg-neutral-900/80 px-3 py-2 text-sm text-neutral-200">
                {today.data.attribution}
              </p>
            )}

            {today.data.warnings.length > 0 && (
              <div className="mt-4 space-y-2">
                {today.data.warnings.map((warning, i) => (
                  <p
                    key={i}
                    className="rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-300"
                  >
                    {warning}
                  </p>
                ))}
              </div>
            )}

            <DirectiveLedger directives={today.data.directives} dataDate={today.data.data_date} />
            <PositionSnapshotTable snapshot={today.data.snapshot} />
            <SettlementPanel settlement={today.data.settlement} />
          </>
        )}
      </main>
    </div>
  );
}
