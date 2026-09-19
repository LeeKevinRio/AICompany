"use client";

import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import type { AdviceResponse } from "../../lib/types";
import { buildOperationSummary } from "../../lib/operationSummary";
import {
  buildLegacyAttributedHeadline,
  CANDIDATE_NOT_SUPPORTIVE_TEXT_LEGACY,
  CONFIDENCE_PREFIX,
  HELD_ACTION_LABELS_LEGACY,
  INSUFFICIENT_DATA_NO_EVALUATION,
  NOT_HELD_BADGE,
  RULE_BASIS_PREFIX,
  RULE_SOURCE_CHIP,
  summaryConfidenceLabel,
} from "../../lib/adviceWording";
import { formatDateTime } from "../../lib/format";
import { SkeletonBlock } from "../../components/SkeletonBlock";
import { ErrorPanel } from "../../components/ErrorPanel";
import { InsufficientPanel } from "../../components/InsufficientPanel";
import { DataMetaStatusBadge } from "../../components/DataMetaStatusBadge";
import { buildFooterGuidance, buildFooterGuidanceForDataSource } from "../../lib/footerDisclosureWording";
import { OPERATION_SUMMARY_TITLE } from "../../lib/sectionTitles";
import { PAGE_LEVEL_DISCLOSURE_SECTION_TITLE } from "../../lib/sectionTaglines";
import { buildDataAsOfBadge, DETAILS_SUMMARY_OPERATION } from "../../lib/oneLinerWording";

/**
 * 一眼一句實作規格 §2.3（`work/stock-desk-一眼一句-實作規格.md`）＋ CEO 第二次
 * 裁定（2026-09-19 深夜，`work/stock-desk-一眼一句簡化-派工單.md` §4）＋
 * wave3 字面重寫（同檔 §4.3，風控逐字核可）：主視圖不放任何免責、教育用途、
 * 解碼／限定句、指引句——disclaimer、`confidenceMeaning`、反面論點、
 * `buildFooterGuidance`／`buildFooterGuidanceForDataSource`、資料時間前綴文字
 * 全部收進 `<details>`；wave3 進一步把 held 分支的舊「規則評估：{動作}」複合詞
 * 拆成純標籤＋同列 `RULE_SOURCE_CHIP` chip，候選分支加「未持有」徽章、
 * `CANDIDATE_EVIDENCE_NOTICE` 移進詳細，主要依據改短前綴「依據：」，信心改短
 * 前綴「信心 」，股數缺席改短句「未提供股數」。舊字面（`HELD_ACTION_LABELS_LEGACY`
 * 等）逐字保留、只搬進「詳細」，不刪除。主視圖只留：徽章列（資料截至徽章＋
 * compact 狀態 chip）、結論大字＋來源 chip／信心 chip、「依據：{規則名}」、
 * 股數一行、`StaleDataAlert`、`restoresComplianceWarning`（role=alert）、候選
 * 分支的「未持有」徽章。`buildOperationSummary`（`app/lib/operationSummary.ts`）
 * 本身不變，八要素仍全部由本檔某處渲染。
 *
 * DRAFT WORDING NOTICE: every visible sentence here traces back to
 * `app/lib/adviceWording.ts`, itself pending risk-compliance-officer's
 * dedicated FR-C6/C7 wording review (see that file's header).
 *
 * 決策卡 required 條件 9（`work/stock-desk-一眼一句簡化-派工單.md` §5.4／視覺
 * 規範 B.7）：the held／candidate branches' main-view share-count line
 * (`QuantitySection`) and the held branch's `role="alert"`
 * `restoresComplianceWarning` box are REMOVED from this panel's main view —
 * `DecisionCard.tsx` (rendered once, above 技術分析) is now the page's single
 * main-view place for both, driven by the SAME `buildOperationSummary(response)`
 * this panel calls. Nothing is deleted: the non-alert `quantityRangeBasis`
 * sentence still renders exactly once inside this panel's own `<details>`
 * (`basisIsAlert` below), unchanged from before this batch.
 */
export function OperationSummaryPanel({ advice }: { advice: UseQueryResult<AdviceResponse, Error> }) {
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">{OPERATION_SUMMARY_TITLE}</h2>
        {/*
          FR-C8(a) / qa-e2e A2-8: every section badges its own data
          provenance independently (same mechanism as the technical-analysis
          `<h3>` rows in `page.tsx`) — never one shared, page-level stamp
          that lets stale data ride along under a fresher section's badge.
          `advice.data` (the envelope's own `DataMeta`) is used rather than
          falling back to the sibling `useBars` query's meta: `advice.py`
          builds this envelope from its own `load_bars` call (same loader,
          same lookback window as `/api/bars`, but a genuinely separate HTTP
          round trip), so it can legitimately land on a different rung of
          the fresh/backup/cached_stale ladder than the bars section at the
          same instant — this section must report *its own* provenance, not
          borrow the bars section's, or a real divergence would be hidden.
          `advice.data.data` is always populated regardless of whether a
          card exists (see `app/api/advice.py`'s `insufficient_data` branch,
          which still returns `data=data_meta(loaded.meta())`), so this is
          gated on `advice.isSuccess` alone, not on a card being present.

          CEO 第二次裁定 2026-09-19：主視圖只留徽章本體；「資料時間：…｜
          來源：…」前綴文字改由 `SummaryBody` 印在各分支自己的 `<details>`
          第一行（`DataMetaPrefixLine`），字面不變。

          wave3（派工單 §4.3 第 5／9 點）：徽章本體本身也換成「資料截至
          {MM-DD}」＋狀態縮寫 chip（`compact`），完整版（分鐘數、括號句、
          `reason`）改由 `DataMetaPrefixLine` 在 `<details>` 內用同一元件的
          非 compact 版渲染，同一行接在「資料時間：…｜來源：…」後面。
        */}
        {advice.isSuccess && (
          <span className="flex flex-wrap items-center gap-1.5 text-xs text-neutral-500">
            {buildDataAsOfBadge(advice.data.data.last_bar_date) !== null && (
              <span className="rounded border border-neutral-700 px-1.5 py-0.5 text-neutral-400">
                {buildDataAsOfBadge(advice.data.data.last_bar_date)}
              </span>
            )}
            <DataMetaStatusBadge
              status={advice.data.data.status}
              stalenessMinutes={advice.data.data.staleness_minutes}
              isWithinTtl={advice.data.data.is_within_ttl}
              lastBarDate={advice.data.data.last_bar_date}
              reason={advice.data.data.reason}
              compact
            />
          </span>
        )}
      </div>

      {advice.isPending && <SkeletonBlock className="mt-3 h-40 w-full" />}
      {advice.isError && (
        <div className="mt-3">
          <ErrorPanel label="無法載入操作摘要" error={advice.error} />
        </div>
      )}
      {advice.isSuccess && <SummaryBody response={advice.data} />}
    </section>
  );
}

/**
 * Exported (only) so `operationSummary.test.ts` can render it directly via
 * `renderToStaticMarkup` for the R4/一眼一句 §2.3 "basis renders exactly
 * once" DOM assertion — every other caller should go through
 * `OperationSummaryPanel` above.
 */
export function SummaryBody({ response }: { response: AdviceResponse }) {
  const model = buildOperationSummary(response);

  // AC-C1.3 / AC-C7.4: no price at all anywhere in the three-tier ladder —
  // no card, no fabricated evaluation, reason shown as-is. D3③: when the
  // envelope still carries a bar date the calendar has moved past, its age is
  // disclosed here too (see `buildOperationSummary`), not only on cards.
  if (model.kind === "no_price") {
    return (
      <div className="mt-3 space-y-3">
        <InsufficientPanel reason={model.reason} />
        <StaleDataAlert notice={model.staleDataNotice} />
        <DetailsDataMetaOnly response={response} />
      </div>
    );
  }

  // AC-C6.5: the engine itself said `insufficient_data` — no action word, no
  // range, no reference figure of any kind. D3③ applies here as well.
  // CEO 第二次裁定 2026-09-19：disclaimer 行移除（全站頁尾已有一句常駐免責）。
  // wave3（派工單 §4.3 第 1 點）：headline 風格改與其餘分支一致（大字＋同列
  // 小字），不掛 `RULE_SOURCE_CHIP`——這裡沒有命中任何規則可歸因。
  if (model.kind === "no_action") {
    return (
      <div className="mt-3 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-block rounded-md border border-neutral-700 bg-neutral-900 px-4 py-2 text-2xl font-bold text-neutral-100">
            {model.reason}
          </span>
          <span className="text-sm text-neutral-400">{INSUFFICIENT_DATA_NO_EVALUATION}</span>
        </div>
        <StaleDataAlert notice={model.staleDataNotice} />
        <DetailsDataMetaOnly response={response}>
          <p>{HELD_ACTION_LABELS_LEGACY.insufficient_data}</p>
        </DetailsDataMetaOnly>
      </div>
    );
  }

  if (model.kind === "candidate") {
    /*
      wave3（派工單 §4.3 第 2 點）：`NOT_HELD_BADGE` 是 candidate 分支唯一需要
      的狀態徽章——`kind === "candidate"` 這個分支本身就定義了「未持有」
      （`buildOperationSummary` 的 `!response.held` 分岔），所以徽章恆定顯示，
      這個變數固定為 `true`。寫成 `showBadge ? 徽章 : 原句` 三元運算式而非直接
      刪掉 else 分支，是刻意的防呆：若未來這條分支被改寫成也可能涵蓋「持有」
      狀態，`showBadge` 一旦真的算出 `false`，`CANDIDATE_EVIDENCE_NOTICE`（原本
      這裡就在講的那句話）會自動回到主視圖，而不是被徽章邏輯覆蓋後silently
      消失——qa 斷言見 componentWordingScan.test.ts。
    */
    const showBadge = true;
    return (
      <div className="mt-3 space-y-4">
        {/* P1 結論位（風控替代路徑，CEO 2026-09-05）：結論標籤放大為 2xl，與信心 chip 同列。 */}
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-block rounded-md border border-sky-800 bg-sky-950/40 px-4 py-2 text-2xl font-bold text-sky-300">
            {model.headingLabel}
          </span>
          {showBadge ? (
            <span className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-0.5 text-xs text-neutral-300">
              {NOT_HELD_BADGE}
            </span>
          ) : (
            <span className="text-xs text-neutral-400">{model.required.candidateEvidenceNotice}</span>
          )}
          <span className="text-sm text-neutral-400">
            {CONFIDENCE_PREFIX}
            {summaryConfidenceLabel(model.required.confidence)}
          </span>
        </div>

        {model.supportive ? (
          <p className="text-sm text-neutral-200">
            {model.compositionText}
            <span className="font-semibold text-amber-300"> {model.supportiveDisclaimer}</span>
          </p>
        ) : (
          <p className="text-sm text-neutral-200">{model.notSupportiveText}</p>
        )}

        <StaleDataAlert notice={model.staleDataNotice} />

        <details className="group mt-1">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm text-neutral-400 hover:text-neutral-300 [&::-webkit-details-marker]:hidden">
            <span
              aria-hidden="true"
              className="inline-block text-xs transition-transform duration-150 group-open:rotate-90"
            >
              ▸
            </span>
            {DETAILS_SUMMARY_OPERATION}
          </summary>
          <div className="mt-3 space-y-3 border-t border-neutral-800 pt-3 text-xs text-neutral-400">
            <DataMetaPrefixLine response={response} />
            {/* CEO 第二次裁定 2026-09-19：disclaimer／confidenceMeaning 收進詳細。 */}
            <InlineDisclaimer text={model.required.disclaimer} />
            <p>{model.required.confidenceMeaning}</p>
            {/*
              wave3（派工單 §4.3 第 2 點）：`CANDIDATE_EVIDENCE_NOTICE` 常駐收進
              詳細（`showBadge` 為 true 時徽章頂替它站在主視圖，這裡永遠完整
              保留這句字面，供 showBadge 為 false 時的主視圖版本與這裡的詳細版
              本對照，也供 qa 逐字釘住）。
            */}
            {model.required.candidateEvidenceNotice && <p>{model.required.candidateEvidenceNotice}</p>}
            {!model.supportive && <p>{CANDIDATE_NOT_SUPPORTIVE_TEXT_LEGACY}</p>}
            {model.quantityBasisNote && <p>{model.quantityBasisNote}</p>}
            {model.required.quantityRangeBasis && <p>{model.required.quantityRangeBasis}</p>}
            {model.required.quantityAbsenceReason !== null && <p>{model.required.quantityAbsenceReason}</p>}
            {model.required.counterarguments.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-neutral-400">反面論點</h4>
                <ul className="mt-1 list-disc space-y-1 pl-5">
                  {model.required.counterarguments.map((text, i) => (
                    <li key={i}>{text}</li>
                  ))}
                </ul>
              </div>
            )}
            {model.required.invalidationConditions.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-neutral-400">失效條件</h4>
                <ul className="mt-1 list-disc space-y-1 pl-5">
                  {model.required.invalidationConditions.map((text, i) => (
                    <li key={i}>{text}</li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-sm text-neutral-300">{buildFooterGuidance(OPERATION_SUMMARY_TITLE)}</p>
            <p className="text-sm text-neutral-300">
              {buildFooterGuidanceForDataSource(PAGE_LEVEL_DISCLOSURE_SECTION_TITLE)}
            </p>
          </div>
        </details>
      </div>
    );
  }

  // model.kind === "held"
  // R4/FR-3 (決策卡 required 條件 9 落地後更新，qa Q3): basis renders exactly
  // once, page-wide. The alert box itself now lives in `DecisionCard.tsx`
  // (this panel no longer renders it at all — see this file's header);
  // `basisIsAlert` here only decides whether THIS panel's own `<details>`
  // still shows the non-alert `quantityRangeBasis` sentence (it must not,
  // whenever the alert box in `DecisionCard.tsx` is the one showing the same
  // text) or omits it.
  const basisIsAlert = model.restoresComplianceWarning !== null;

  return (
    <div className="mt-3 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="inline-block rounded-md border border-neutral-700 bg-neutral-900 px-4 py-2 text-2xl font-bold text-neutral-100">
          {model.attributedHeadline}
        </span>
        {/* wave3（派工單 §4.3 第 1 點）：來源感改由這顆常駐 chip 承擔，取代舊版烤進大字本身、以 `ATTRIBUTION_PREFIX` 開頭的前綴（見 `buildLegacyAttributedHeadline`）。 */}
        <span className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-0.5 text-xs text-neutral-400">
          {RULE_SOURCE_CHIP}
        </span>
        <span className="text-sm text-neutral-400">
          {CONFIDENCE_PREFIX}
          {summaryConfidenceLabel(model.required.confidence)}
        </span>
      </div>

      {/*
        AC-C6.1: the conclusion's main basis — the single heaviest matched
        rule. CEO 第二次裁定 2026-09-19: only the rule *name* stays standing
        here (用既有字面拆分，不新造字面); the "——{explanation}" half of the
        same original sentence moves into `<details>` below. wave3: prefix
        shortened from「主要依據：」to `RULE_BASIS_PREFIX`「依據：」。
      */}
      {model.topMatchedRule && (
        <p className="text-sm text-neutral-300">
          <span className="text-neutral-500">{RULE_BASIS_PREFIX}</span>
          {model.topMatchedRule.name}
        </p>
      )}

      <StaleDataAlert notice={model.staleDataNotice} />

      <details className="group mt-1">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm text-neutral-400 hover:text-neutral-300 [&::-webkit-details-marker]:hidden">
          <span aria-hidden="true" className="inline-block text-xs transition-transform duration-150 group-open:rotate-90">
            ▸
          </span>
          {DETAILS_SUMMARY_OPERATION}
        </summary>
        <div className="mt-3 space-y-3 border-t border-neutral-800 pt-3 text-xs text-neutral-400">
          <DataMetaPrefixLine response={response} />
          {/* CEO 第二次裁定 2026-09-19：disclaimer／confidenceMeaning 收進詳細。 */}
          <InlineDisclaimer text={model.required.disclaimer} />
          <p>{model.required.confidenceMeaning}</p>
          {/* wave3：舊「規則評估：{動作}」複合詞逐字保留在詳細，供對照與測試釘住。 */}
          <p>{buildLegacyAttributedHeadline(model.action)}</p>
          {model.topMatchedRule && <p>——{model.topMatchedRule.explanation}</p>}
          {!basisIsAlert && model.required.quantityRangeBasis && <p>{model.required.quantityRangeBasis}</p>}
          {model.required.quantityAbsenceReason !== null && <p>{model.required.quantityAbsenceReason}</p>}

          {model.required.counterarguments.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-neutral-400">反面論點</h4>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {model.required.counterarguments.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
            </div>
          )}

          {model.required.invalidationConditions.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-neutral-400">失效條件</h4>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {model.required.invalidationConditions.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
            </div>
          )}

          <p className="text-sm text-neutral-300">{buildFooterGuidance(OPERATION_SUMMARY_TITLE)}</p>
          <p className="text-sm text-neutral-300">
            {buildFooterGuidanceForDataSource(PAGE_LEVEL_DISCLOSURE_SECTION_TITLE)}
          </p>
        </div>
      </details>
    </div>
  );
}

/**
 * CEO 第二次裁定 2026-09-19：主視圖只留 `DataMetaStatusBadge` 徽章本體，
 * 「資料時間：…｜來源：…」前綴文字（原本就在 `OperationSummaryPanel` 的 h2
 * 徽章列裡）改印在各分支自己 `<details>` 的第一行，字面完全相同、不新造。
 * wave3（派工單 §4.3 追加第 9 點）：主視圖徽章換成 compact 版之後，完整版
 * （分鐘數、括號句、`reason`）改用同一元件的非 compact 版渲染在這一行，緊接
 * 在文字前綴之後——沒有任何字面被刪除，只有出現位置變了。
 */
function DataMetaPrefixLine({ response }: { response: AdviceResponse }) {
  return (
    <p>
      資料時間：{formatDateTime(response.as_of)}｜來源：{response.data.source}
      <DataMetaStatusBadge
        status={response.data.status}
        stalenessMinutes={response.data.staleness_minutes}
        isWithinTtl={response.data.is_within_ttl}
        lastBarDate={response.data.last_bar_date}
        reason={response.data.reason}
      />
    </p>
  );
}

/**
 * no_price／no_action 分支內容本就極簡（Insufficient／Stale 兩塊而已），沒有
 * 既存的 `<details>` 可承接資料時間前綴——這裡補一個只裝這一行的最小
 * `<details>`，維持「主視圖只留徽章本體」的規則，不額外新造任何字面。
 * `children`（wave3 追加）讓 no_action 分支能一併把 `HELD_ACTION_LABELS_LEGACY.insufficient_data`
 * 舊字面放進同一個詳細區，不必為它另開一個 `<details>`。
 */
function DetailsDataMetaOnly({ response, children }: { response: AdviceResponse; children?: ReactNode }) {
  return (
    <details className="group mt-1">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm text-neutral-400 hover:text-neutral-300 [&::-webkit-details-marker]:hidden">
        <span aria-hidden="true" className="inline-block text-xs transition-transform duration-150 group-open:rotate-90">
          ▸
        </span>
        {DETAILS_SUMMARY_OPERATION}
      </summary>
      <div className="mt-3 space-y-3 border-t border-neutral-800 pt-3 text-xs text-neutral-400">
        <DataMetaPrefixLine response={response} />
        {children}
      </div>
    </details>
  );
}

/**
 * §2.1 required: the fixed disclaimer, a `text-xs neutral-400` line — never
 * `truncate`/`line-clamp`. CEO 第二次裁定 2026-09-19: moved from standing
 * beside the headline into each branch's `<details>` (the全站頁尾 in
 * `app/layout.tsx` is now the page's one standing disclaimer); still rendered
 * verbatim, held／candidate alike, just one layer deeper.
 */
function InlineDisclaimer({ text }: { text: string }) {
  return <p className="text-xs text-neutral-400">{text}</p>;
}

/**
 * AC-C8.2's prominent data-age alert, in the one style every branch shares —
 * extracted (D3③) so the branches cannot drift apart on prominence. Renders
 * nothing when there is no stale gap to disclose.
 *
 * Exported (only) so `DecisionCard.tsx` renders the SAME style at the top of
 * the decision card (決策卡 required 條件 10) instead of drafting a second
 * `role="alert"` box — this panel's own usage above is unchanged.
 */
export function StaleDataAlert({ notice }: { notice: string | null }) {
  if (notice === null) return null;
  return (
    <p role="alert" className="rounded-md border border-amber-700 bg-amber-950/40 px-3 py-2 text-amber-300">
      {notice}
    </p>
  );
}
