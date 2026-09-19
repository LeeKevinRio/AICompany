"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { AdviceResponse, Bar } from "../../lib/types";
import type { AnchorSource } from "../../lib/keyLevels";
import { computeKeyLevels } from "../../lib/keyLevels";
import { buildOperationSummary } from "../../lib/operationSummary";
import type { OperationSummaryModel } from "../../lib/operationSummary";
import {
  INSUFFICIENT_DATA_NO_EVALUATION,
  NOT_HELD_BADGE,
  QUANTITY_RANGE_ABSENT_SHORT,
  RULE_SOURCE_CHIP,
} from "../../lib/adviceWording";
import { buildDataAsOfBadge } from "../../lib/oneLinerWording";
import {
  DECISION_CARD_ARIA_LABEL,
  DECISION_CARD_QUANTITY_LABEL,
  buildDecisionCardDistance,
} from "../../lib/decisionCardWording";
import {
  PAGE_FOOTER_DISCLOSURES_TITLE,
  buildFooterGuidance,
} from "../../lib/footerDisclosureWording";
import { SkeletonBlock } from "../../components/SkeletonBlock";
import { ErrorPanel } from "../../components/ErrorPanel";
import { InsufficientPanel } from "../../components/InsufficientPanel";
import { DataMetaStatusBadge } from "../../components/DataMetaStatusBadge";
import { StaleDataAlert } from "./OperationSummaryPanel";
import {
  KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE,
  KEY_LEVELS_LADDER_RUNG_ANCHOR_COST,
  KEY_LEVELS_LADDER_RUNG_CLOSE,
  KEY_LEVELS_STOP_CARD_TITLE,
  KEY_LEVELS_TARGET_CARD_TITLE,
  buildStopBasisConfirmedNotHeld,
} from "./KeyLevelsPanel";

/**
 * 決策卡（`work/stock-desk-一眼一句簡化-派工單.md` §5.4 dev-lead 草案／CEO 第三次
 * 裁定 §5.1／§5.3；視覺規範 B.7；文案稿 `work/stock-desk-決策卡-文案稿.md`：不設
 * 標題，只留動作大字）。整頁第一張卡，放在標題列與技術分析之間；全部數字沿用
 * 既有計算結果的重排（`buildOperationSummary`／`computeKeyLevels`），不新增任何
 * 模型或算式，本卡本身不設「詳細」——下方各區塊本身就是它的展開版。
 *
 * 決策卡第二輪修正（風控複審 APPROVE_WITH_CONDITIONS 新增 R1–R3；qa NEEDS_CHANGES
 * Q1–Q4；dev-lead 視覺修正 V1–V2）：
 *   R1. `DECISION_CARD_QUANTITY_LABEL` 改為「股數參考」（見 `decisionCardWording.ts`）。
 *   R2. 兩來源不一致時降級為 close-unknown（`effectiveAnchorSource`）：
 *       `model.kind === "held"` 但 `anchorSource === "close-not-held"`，或
 *       `model.kind === "candidate"` 但 `anchorSource === "cost"`——這兩種組合代表
 *       advice 與 positions 兩個查詢對「是否持有」給出矛盾答案，一律不顯示任何
 *       持有/未持有的暗示，等同 close-unknown。`no_price`／`no_action` 不受影響
 *       （這兩種 kind 從不觸發上述條件）。
 *   R3. 卡片底部常駐 `buildFooterGuidance(PAGE_FOOTER_DISCLOSURES_TITLE)`，不在
 *       任何摺疊內（本卡本來就不設 `<details>`）。
 *   Q1. 未持有徽章與 `buildStopBasisConfirmedNotHeld` 全句同一個閘門
 *       （`effectiveAnchorSource === "close-not-held"`），不得只看 `levels !== null`
 *       ——`levels === null` 時全句仍常駐，價格代入 `fmt(null)`（即「—」）。
 *   Q2. `no_price`／`no_action` 的股數格印「—」，不印 `QUANTITY_RANGE_ABSENT_SHORT`
 *       （該三字專屬 held／candidate 且 `quantity_range === null` 的情境）。
 *   V1. `NumberCell` 的 `distance` 為 `undefined`（收盤／股數格，無距離概念）或
 *       `null`（水位缺席）時渲染不可見佔位（`aria-hidden`＋`&nbsp;`），不得印
 *       「—」——頁尾 `KEY_LEVELS_HEADER_DASH_NOTICE` 已把「—」定義為「日線根數
 *       不足」，用在「這格沒有距離」上會誤導。
 *   V2. 四格 `value` 的 `<p>` 加 `whitespace-nowrap`（375px 實測「股」字被擠到
 *       下一行）。
 *
 * 風控 2026-09-19 預審 APPROVE_WITH_CONDITIONS（逐條對應本檔）：
 *   1/2. 距離小字固定前綴「距最新收盤 」（`buildDecisionCardDistance`），符號由
 *        (水位－最新收盤)/最新收盤×100 算出，一律複用 `PriceLadder.tsx` 的
 *        `fmtSigned`（同一份實作，未另寫）。
 *   3. 頁尾「關鍵價位參考」組新增的 `KEY_LEVELS_BASIS_CLOSE_DISTANCE` 算式行見
 *      `KeyLevelsPanel.tsx`／`buildKeyLevelsFooterItems`。
 *   4. 本卡不設可見標題；`<section aria-label={DECISION_CARD_ARIA_LABEL}>`。
 *   5. 基準來源標籤（`KEY_LEVELS_LADDER_RUNG_ANCHOR_COST`／`_CLOSE`）與停損／
 *      停利同層常駐一次（`anchorLabel` 段落）。
 *   6. 未持有（`close-not-held`）：`NOT_HELD_BADGE` 徽章＋
 *      `buildStopBasisConfirmedNotHeld` 全句同時常駐。
 *   7. 持倉狀態未知（`close-unknown`）：不顯示「未持有」、停損／停利兩格「—」、
 *      不畫距離、不印基準標籤（`suppressAnchor`）。
 *   8. 候選模式支持分支：`compositionText`＋`CANDIDATE_SUPPORTIVE_DISCLAIMER`
 *      同層不可分離（兩者皆已烤進 `model.compositionText`／`model.supportiveDisclaimer`，
 *      本檔原樣渲染，不重新拼字）；不支持時 `model.notSupportiveText`
 *      （＝`CANDIDATE_NOT_SUPPORTIVE_TEXT`）。主字 `model.headingLabel`
 *      （＝`CANDIDATE_HEADING_LABEL`「進場評估」）。
 *   9. 第四格股數：`model.required.quantityRangeShares` 或
 *      `QUANTITY_RANGE_ABSENT_SHORT`；`restoresComplianceWarning` 非 null 時卡內
 *      同層 `role="alert"`（沿用 `OperationSummaryPanel.tsx` 既有 alert 樣式，
 *      import 自該檔的 `StaleDataAlert` 同款作法，非另寫一份）。全頁「股數＋
 *      warning」恰一次：`OperationSummaryPanel.tsx` 的對應主視圖渲染已移除
 *      （見該檔 header 說明），本卡是全頁唯一渲染處。
 *   10. 徽章列：`buildDataAsOfBadge(advice.data.data.last_bar_date)` ＋
 *       `DataMetaStatusBadge compact`（advice envelope 的 `DataMeta`）；
 *       `StaleDataAlert`（`model.staleDataNotice`）渲染在卡片內頂部。
 *   11. 停損／停利大字與距離 % 不上紅綠（`text-neutral-100`／`text-neutral-400`）。
 *   12. 兩處動作大字（本卡與 `OperationSummaryPanel`）同一資料來源：都呼叫
 *       `buildOperationSummary(advice.data)`；bars 不 ok 或 `computeKeyLevels`
 *       為 null → 收盤／停損／停利三格「—」、不畫距離。
 *
 * 版面依視覺規範 B.7：桌機主字左、四格右（`grid grid-cols-2 sm:grid-cols-4`）；
 * 主字 `text-2xl font-bold`（不超過 `h1`）；數字 `font-mono text-xl font-bold
 * text-neutral-100`；標籤 `text-sm text-neutral-400`；距離小字
 * `text-xs text-neutral-400`。
 */

function fmt(n: number | null): string {
  if (n === null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("zh-TW", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * V1（dev-lead 視覺修正）：`distance` 只在停損／停利兩格有意義。`undefined`
 * （收盤／股數格，這兩格根本沒有距離概念）或 `null`（水位本身缺席，如
 * close-unknown／bars 不可用）一律渲染不可見佔位，保留行高，不得印「—」——
 * 頁尾 `KEY_LEVELS_HEADER_DASH_NOTICE` 已把「—」定義為「可用日線根數不足」，
 * 借來表示「這格沒有距離概念」會與該定義衝突、造成誤讀。
 */
function NumberCell({
  label,
  value,
  distance,
}: {
  label: string;
  value: string;
  distance?: string | null;
}) {
  return (
    <div className="flex min-h-[4.5rem] flex-col items-start sm:items-end">
      <p className="text-sm text-neutral-400">{label}</p>
      <p className="mt-1 whitespace-nowrap font-mono text-xl font-bold text-neutral-100">
        {value}
      </p>
      {distance != null ? (
        <p className="mt-0.5 text-xs text-neutral-400">{distance}</p>
      ) : (
        <p className="mt-0.5 text-xs" aria-hidden="true">
          &nbsp;
        </p>
      )}
    </div>
  );
}

/**
 * 主字位（動作大字＋緊鄰狀態）：四種 `model.kind` 各自的既有字面，原樣重排，
 * 不新造任何字面——沿用 `OperationSummaryPanel.tsx`「詳細」之外主視圖曾經的
 * 同一組常數與 class（held：`RULE_SOURCE_CHIP`；candidate：`NOT_HELD_BADGE`／
 * `compositionText`／`supportiveDisclaimer`／`notSupportiveText`；no_action：
 * `INSUFFICIENT_DATA_NO_EVALUATION`；no_price：`InsufficientPanel`）。
 */
function MainSlot({ model }: { model: OperationSummaryModel }) {
  if (model.kind === "no_price") {
    return <InsufficientPanel reason={model.reason} />;
  }

  if (model.kind === "no_action") {
    return (
      <>
        <span className="inline-block rounded-md border border-neutral-700 bg-neutral-900 px-4 py-2 text-2xl font-bold text-neutral-100">
          {model.reason}
        </span>
        <span className="text-sm text-neutral-400">
          {INSUFFICIENT_DATA_NO_EVALUATION}
        </span>
      </>
    );
  }

  if (model.kind === "candidate") {
    return (
      <>
        <span className="inline-block rounded-md border border-sky-800 bg-sky-950/40 px-4 py-2 text-2xl font-bold text-sky-300">
          {model.headingLabel}
        </span>
        {model.supportive ? (
          <span className="text-sm text-neutral-200">
            {model.compositionText}
            <span className="font-semibold text-amber-300">
              {" "}
              {model.supportiveDisclaimer}
            </span>
          </span>
        ) : (
          <span className="text-sm text-neutral-200">
            {model.notSupportiveText}
          </span>
        )}
      </>
    );
  }

  // model.kind === "held"
  return (
    <>
      <span className="inline-block rounded-md border border-neutral-700 bg-neutral-900 px-4 py-2 text-2xl font-bold text-neutral-100">
        {model.attributedHeadline}
      </span>
      <span className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-0.5 text-xs text-neutral-400">
        {RULE_SOURCE_CHIP}
      </span>
    </>
  );
}

/**
 * Exported (only) so `decisionCard.test.ts` can render it directly via
 * `renderToStaticMarkup`, mirroring `OperationSummaryPanel.tsx`'s own
 * `SummaryBody` export for the same reason — every other caller goes through
 * `DecisionCard` below.
 */
export function DecisionCardBody({
  response,
  bars,
  anchorSource,
  avgCost,
}: {
  response: AdviceResponse;
  bars: Bar[] | null;
  anchorSource: AnchorSource;
  avgCost: number | null;
}) {
  const model = buildOperationSummary(response);

  // R2（決策卡第二輪修正）：advice 與 positions 兩個查詢對「是否持有」給出矛盾
  // 答案時（held 卻讀到 close-not-held；candidate 卻讀到 cost）一律降級為
  // close-unknown，不顯示任何持有/未持有的暗示。`no_price`／`no_action` 這兩種
  // kind 從不參與這個判斷，不受影響。
  const inconsistentHeld =
    model.kind === "held" && anchorSource === "close-not-held";
  const inconsistentCandidate =
    model.kind === "candidate" && anchorSource === "cost";
  const effectiveAnchorSource: AnchorSource =
    inconsistentHeld || inconsistentCandidate ? "close-unknown" : anchorSource;

  const levels =
    bars !== null
      ? computeKeyLevels(
          bars,
          effectiveAnchorSource === "cost" ? avgCost : null,
        )
      : null;
  // 風控 required 條件 7：持倉狀態未知時，停損／停利兩格「—」、不畫距離、不印
  // 基準標籤——即使 bars 足夠算出試算值，也不得暗示任何一種持有狀態。
  const suppressAnchor = effectiveAnchorSource === "close-unknown";
  const notHeld = effectiveAnchorSource === "close-not-held";

  const closeText = levels !== null ? fmt(levels.close) : "—";
  const stopText =
    levels !== null && !suppressAnchor ? fmt(levels.stopSuggested) : "—";
  const targetText =
    levels !== null && !suppressAnchor ? fmt(levels.target2R) : "—";
  const stopDistance =
    levels !== null && !suppressAnchor
      ? buildDecisionCardDistance(
          ((levels.stopSuggested - levels.close) / levels.close) * 100,
        )
      : null;
  const targetDistance =
    levels !== null && !suppressAnchor
      ? buildDecisionCardDistance(
          ((levels.target2R - levels.close) / levels.close) * 100,
        )
      : null;
  const anchorLabel =
    levels !== null && !suppressAnchor
      ? effectiveAnchorSource === "cost"
        ? KEY_LEVELS_LADDER_RUNG_ANCHOR_COST
        : KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE
      : null;

  // Q2（qa medium）："未提供股數" 專屬 held／candidate 且 quantity_range 為
  // null 的情境；no_price／no_action 這兩種 kind 根本沒有 quantity_range 這個
  // 欄位可言，股數格改印「—」（與其他缺席數字同一慣例），不得借用該三字。
  const quantityText =
    model.kind === "held" || model.kind === "candidate"
      ? (model.required.quantityRangeShares ?? QUANTITY_RANGE_ABSENT_SHORT)
      : "—";
  const restoresWarning =
    model.kind === "held" ? model.restoresComplianceWarning : null;

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex flex-wrap items-center gap-1.5 text-xs text-neutral-500">
          {buildDataAsOfBadge(response.data.last_bar_date) !== null && (
            <span className="rounded border border-neutral-700 px-1.5 py-0.5 text-neutral-400">
              {buildDataAsOfBadge(response.data.last_bar_date)}
            </span>
          )}
          <DataMetaStatusBadge
            status={response.data.status}
            stalenessMinutes={response.data.staleness_minutes}
            isWithinTtl={response.data.is_within_ttl}
            lastBarDate={response.data.last_bar_date}
            reason={response.data.reason}
            compact
          />
          {notHeld && (
            <span className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-0.5 text-neutral-400">
              {NOT_HELD_BADGE}
            </span>
          )}
        </span>
      </div>

      {/*
        風控 required 條件 6／qa Q1（high）：未持有時，徽章與這句全句用同一個
        閘門（`notHeld`），不得只看 `levels !== null`——`levels` 為 `null`（bars
        不可用）時全句仍常駐，價格代入 `fmt(null)`（即「—」），確保「徽章有、
        全句無」或反過來的情況不會發生。
      */}
      {notHeld && (
        <p className="mt-1 text-xs text-neutral-400">
          {buildStopBasisConfirmedNotHeld(
            fmt(levels !== null ? levels.anchorPrice : null),
          )}
        </p>
      )}

      <div className="mt-1">
        <StaleDataAlert notice={model.staleDataNotice} />
      </div>

      <div className="mt-3 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-h-[3.5rem] flex-wrap items-center gap-3">
          <MainSlot model={model} />
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4 sm:gap-x-6">
          <NumberCell label={KEY_LEVELS_LADDER_RUNG_CLOSE} value={closeText} />
          <NumberCell
            label={KEY_LEVELS_STOP_CARD_TITLE}
            value={stopText}
            distance={stopDistance}
          />
          <NumberCell
            label={KEY_LEVELS_TARGET_CARD_TITLE}
            value={targetText}
            distance={targetDistance}
          />
          <NumberCell
            label={DECISION_CARD_QUANTITY_LABEL}
            value={quantityText}
          />
        </div>
      </div>

      {/* 風控 required 條件 5：基準來源標籤與停損／停利同層常駐一次。 */}
      {anchorLabel !== null && (
        <p className="mt-2 text-xs text-neutral-400">{anchorLabel}</p>
      )}

      {/* 風控 required 條件 9：restoresComplianceWarning 與股數同層，全頁唯一渲染處。 */}
      {restoresWarning !== null && (
        <p
          role="alert"
          className="mt-3 rounded-md border border-rose-800 bg-rose-950/50 px-4 py-3 text-sm font-semibold text-rose-300"
        >
          {restoresWarning}
        </p>
      )}

      {/*
        R3（決策卡第二輪修正）：卡片底部常駐指引句，指向頁尾揭露區——本卡不設
        `<details>`，這句本來就不在任何摺疊內。
      */}
      <p className="mt-3 text-sm text-neutral-300">
        {buildFooterGuidance(PAGE_FOOTER_DISCLOSURES_TITLE)}
      </p>
    </>
  );
}

export function DecisionCard({
  advice,
  bars,
  anchorSource,
  avgCost,
}: {
  advice: UseQueryResult<AdviceResponse, Error>;
  /** Only bars from an `ok` envelope — `null` means "not usable this render". */
  bars: Bar[] | null;
  anchorSource: AnchorSource;
  avgCost: number | null;
}) {
  return (
    <section
      aria-label={DECISION_CARD_ARIA_LABEL}
      className="mt-6 rounded-lg border border-neutral-800 p-4"
    >
      {advice.isPending && <SkeletonBlock className="h-40 w-full" />}
      {advice.isError && (
        <ErrorPanel label="無法載入決策摘要" error={advice.error} />
      )}
      {advice.isSuccess && (
        <DecisionCardBody
          response={advice.data}
          bars={bars}
          anchorSource={anchorSource}
          avgCost={avgCost}
        />
      )}
    </section>
  );
}
