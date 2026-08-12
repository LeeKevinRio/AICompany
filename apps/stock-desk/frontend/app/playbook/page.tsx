"use client";

import { ErrorPanel } from "../components/ErrorPanel";
import { SkeletonBlock } from "../components/SkeletonBlock";
import {
  fastMarketAdjacentNote,
  noDirectiveNote,
  shouldRenderAttribution,
  shouldRenderDirectiveLedger,
  shouldRenderRuleSetConfirm,
  visibleWarnings,
} from "../lib/playbookView";
import { usePlaybookToday } from "../lib/queries";
import { DirectiveLedger } from "./DirectiveLedger";
import { ModeStatusBar } from "./ModeStatusBar";
import { PositionSnapshotTable } from "./PositionSnapshotTable";
import { RuleSetConfirmPanel } from "./RuleSetConfirmPanel";
import { SettlementPanel } from "./SettlementPanel";

/**
 * 排程台 (`/playbook`, 視覺規範 全文). 第 0 層狀態列（`ModeStatusBar`,
 * sticky）is rendered as soon as `GET /api/playbook/today` succeeds, ahead of
 * everything else, per §1's information-hierarchy table — it must never wait
 * behind the ledger/snapshot below it.
 *
 * §6's 總覽區塊 is now rendered (四輪收斂裁決 題 11 settled its three sentences
 * and the backend sends them as `page_summary`): above the ledger, never
 * collapsed, `text-sm` on `neutral-300` — the ruling's floor is ≥text-sm and
 * ≥neutral-400, and it sits above the ledger rather than beside it because the
 * first sentence scopes the whole page. §0's page-level framing line remains a
 * `{PAGE_FRAMING_LINE}` placeholder in the visual spec and has no backend field
 * (risk-compliance ruled it 「MVP 可缺」 because the 歸屬語 already carries it),
 * so it is still not rendered.
 */
export default function PlaybookPage() {
  const today = usePlaybookToday(true);
  const data = today.data;
  // 快市沿用說明 is rendered next to the badge in `ModeStatusBar`; the same
  // sentence is filtered out of the warnings list below so the page states it
  // once, in the more prominent of the two places (never dropped from both).
  const carriedNote = data === undefined ? null : fastMarketAdjacentNote(data.fast_market);
  const warnings = data === undefined ? [] : visibleWarnings(data.warnings, carriedNote);

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

        {today.isSuccess && data !== undefined && (
          <>
            {/* 風控 R2 常駐歸屬語；EMPTY 契約：null 時不渲染整行。 */}
            {shouldRenderAttribution(data.attribution) && (
              <p className="mt-4 rounded-md border border-neutral-700 bg-neutral-900/80 px-3 py-2 text-sm text-neutral-200">
                {data.attribution}
              </p>
            )}

            {/*
              §6 總覽區塊（四輪收斂裁決 題 11）：後端逐字下發的三句，位置在帳冊
              上方、不摺疊、不縮寫、不進 tooltip。空陣列（舊版後端）就整塊不渲染
              ——這裡沒有可替代的自撰句。
            */}
            {data.page_summary.length > 0 && (
              <div className="mt-4 space-y-1 rounded-md border border-neutral-800 bg-neutral-900/60 px-3 py-2">
                {data.page_summary.map((sentence, i) => (
                  <p key={i} className="text-sm text-neutral-300">
                    {sentence}
                  </p>
                ))}
              </div>
            )}

            {warnings.length > 0 && (
              <div className="mt-4 space-y-2">
                {warnings.map((warning, i) => (
                  <p
                    key={i}
                    className="rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-300"
                  >
                    {warning}
                  </p>
                ))}
              </div>
            )}

            {/*
              待確認規則集（歸屬語情境 1）唯一的出口：確認規則集 + 資本設定入口，
              就接在阻斷態的說明（歸屬語／§6 三句／警示）下方，讓「為什麼沒有指令」
              與「怎麼解除」讀在一起。其他模式不渲染——見 `shouldRenderRuleSetConfirm`。
            */}
            {shouldRenderRuleSetConfirm(data.mode) && <RuleSetConfirmPanel />}

            {/*
              required ④ fail-closed：沒有歸屬語就不渲染指令帳冊（風控 R2 把常駐
              歸屬語當成顯示指令的條件，不是裝飾）。`shouldRenderDirectiveLedger`
              的註解寫明為什麼此處不補一句自撰的說明句。
            */}
            {shouldRenderDirectiveLedger(data.attribution) && (
              <DirectiveLedger
                directives={data.directives}
                dataDate={data.data_date}
                noDirectiveNote={noDirectiveNote(data)}
              />
            )}
            <PositionSnapshotTable
              snapshot={data.snapshot}
              dataDate={data.data_date}
              asOf={data.as_of}
            />
            <SettlementPanel settlement={data.settlement} />
          </>
        )}
      </main>
    </div>
  );
}
