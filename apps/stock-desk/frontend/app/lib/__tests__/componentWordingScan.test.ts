/**
 * qa-reviewer Major follow-up on the FR-C1 review: the wording guard
 * (`adviceWording.test.ts`) only scanned `adviceWording.ts`'s exported
 * strings, which does not fully satisfy §1.3's required obligation that
 * "前端文案模板亦須被掃到" — any Traditional-Chinese literal written
 * directly into a component's JSX (a hard-coded label, an inline error
 * message, a `placeholder`, …) would ship unscanned. This suite reads the
 * *raw source text* of every component in the operation-summary surface
 * that can render user-facing copy and scans it against the same
 * `FRONTEND_FORBIDDEN_TERMS` list.
 *
 * Source-text (not rendered-output) scanning is deliberate here, unlike
 * `adviceWording.test.ts`: these three files are consumers, not the wording
 * module itself, so they have no legitimate reason to *name* a banned term
 * in a comment the way `adviceWording.ts`'s own doc comments do (explaining
 * what NOT to write). If that ever changes, narrow the scan the same way
 * `adviceWording.test.ts` does (scan rendered output / an explicit slice)
 * rather than silently widening this list's exceptions.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";
import {
  CONFIGURED_SOURCES,
  US_DATA_SOURCE_DISCLOSURE_STATEMENT,
} from "../../settings/DataSourcesSection";
import {
  TRADINGVIEW_CHART_DATA_MISMATCH_STATEMENT,
  TRADINGVIEW_CHART_DISCLOSURE_FULL_STATEMENT,
  TRADINGVIEW_CHART_DISCLOSURE_STATEMENT,
  TRADINGVIEW_CHART_FALLBACK_MESSAGE,
  TRADINGVIEW_CHART_INVALID_SYMBOL_MESSAGE,
} from "../../position/[symbol]/TradingViewChartPanel";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";
import { PageFooterDisclosures } from "../../components/PageFooterDisclosures";
import {
  ADVICE_CARD_XREF_TO_SUMMARY,
  KEY_LEVELS_TAGLINE,
  LEVERAGE_CHAPTER_TAGLINE,
  OPERATION_SUMMARY_TAGLINE,
  PAGE_LEVEL_DISCLOSURE_SECTION_INTRO,
  PAGE_LEVEL_DISCLOSURE_SECTION_TITLE,
  TECHNICAL_CHART_TAGLINE,
  TECHNICAL_INDICATORS_TAGLINE,
} from "../sectionTaglines";
import { NON_REALTIME_NOTICE } from "../adviceWording";
import {
  KEY_LEVELS_BASIS_ANCHOR,
  KEY_LEVELS_BASIS_ATR,
  KEY_LEVELS_BASIS_CLOSE_DISTANCE,
  KEY_LEVELS_BASIS_MA,
  KEY_LEVELS_BASIS_PULLBACK,
  KEY_LEVELS_BASIS_RECENT_LOW60,
  KEY_LEVELS_BASIS_SECTION_TITLE,
  KEY_LEVELS_BASIS_STOP,
  KEY_LEVELS_BASIS_TARGET,
  KEY_LEVELS_BASIS_UNADJUSTED_XREF,
  KEY_LEVELS_BASIS_ZONE,
  KEY_LEVELS_HEADER_DASH_NOTICE,
  KEY_LEVELS_HEADER_STALENESS_SELF_NOTICE,
  KEY_LEVELS_HEADER_UNADJUSTED_NOTICE,
  KEY_LEVELS_MA60_DEVIATION_LABEL,
  KEY_LEVELS_NO_DATA_STATEMENT,
  KEY_LEVELS_PANEL_DISCLAIMER,
  KEY_LEVELS_PANEL_TITLE,
  KEY_LEVELS_PULLBACK_CARD_TITLE,
  KEY_LEVELS_PULLBACK_EXPLAIN_NOTE,
  KEY_LEVELS_PULLBACK_ROW_MA20,
  KEY_LEVELS_PULLBACK_ROW_MA60,
  KEY_LEVELS_PULLBACK_ROW_RECENT_LOW60,
  KEY_LEVELS_STOP_CARD_TITLE,
  KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE,
  KEY_LEVELS_STOP_CONDITION_ATR_UNAVAILABLE,
  KEY_LEVELS_STOP_ROW_ATR,
  KEY_LEVELS_STOP_ROW_FIXED_PCT,
  KEY_LEVELS_STOP_S5_NEUTRAL_NOTE,
  KEY_LEVELS_TARGET_ANCHOR_CROSS_REF,
  KEY_LEVELS_TARGET_CARD_TITLE,
  KEY_LEVELS_TARGET_ROW_2R,
  KEY_LEVELS_TARGET_ROW_FIXED_PCT,
  KEY_LEVELS_TARGET_ROW_TRAILING_LABEL,
  KEY_LEVELS_TARGET_ROW_TRAILING_NOTE,
  KEY_LEVELS_TARGET_STANDING_NOTICE,
  KEY_LEVELS_ZONE_LABEL_HIGH,
  KEY_LEVELS_ZONE_LABEL_LOW,
  KEY_LEVELS_ZONE_LABEL_MID,
  buildBasisClose,
  buildBasisRange,
  buildFooterSample,
  buildKeyLevelsCloseLine,
  buildRangeCardTitle,
  buildRangeFlatReason,
  buildRangeInsufficientReason,
  buildRangeLabel,
  buildRangeNotValuationNote,
  buildStopBasisConfirmedNotHeld,
  buildStopBasisHeldWithCost,
  buildStopBasisUnknown,
} from "../../position/[symbol]/KeyLevelsPanel";
import type { BasisItem } from "../../position/[symbol]/KeyLevelsPanel";
import {
  KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE,
  KEY_LEVELS_LADDER_RUNG_ANCHOR_COST,
  KEY_LEVELS_LADDER_RUNG_CLOSE,
} from "../../position/[symbol]/KeyLevelsPanel";
import {
  KEY_LEVELS_GAUGE_HIGH_END_LABEL,
  KEY_LEVELS_GAUGE_LOW_END_LABEL,
  KEY_LEVELS_GAUGE_MARKER_LABEL,
  buildGaugeAriaLabel,
} from "../../position/[symbol]/RangeGauge";
import {
  KEY_LEVELS_LADDER_DISTANCE_HEADER,
  KEY_LEVELS_LADDER_HEADLINE_TAG,
  KEY_LEVELS_LADDER_INTRO,
  KEY_LEVELS_LADDER_NOTE,
  KEY_LEVELS_LADDER_TITLE,
} from "../../position/[symbol]/PriceLadder";
import {
  INDICATOR_OVERVIEW_EMPTY,
  INDICATOR_OVERVIEW_LEGEND,
  INDICATOR_OVERVIEW_TITLE,
  KD_BAND_LABELS,
  PERCENT_B_BAND_LABELS,
  RSI_BAND_LABELS,
  VOLUME_Z_BAND_LABELS,
} from "../../position/[symbol]/TechnicalIndicatorsPanel";
import { DIRECTION_BAR_ARIA_LABEL, DIRECTION_SHARE_QUALIFIER } from "../../position/[symbol]/AdviceCardView";
import {
  PAGE_FOOTER_DISCLOSURES_INTRO,
  PAGE_FOOTER_DISCLOSURES_TITLE,
  buildFooterGuidance,
  buildFooterGuidanceForDataSource,
} from "../footerDisclosureWording";
import {
  ADVICE_CARD_TITLE,
  LEVERAGE_CHAPTER_TITLE,
  OPERATION_SUMMARY_TITLE,
  TECHNICAL_ANALYSIS_TITLE,
} from "../sectionTitles";
import { buildKeyLevelsFooterItems } from "../../position/[symbol]/KeyLevelsPanel";
import { buildAdviceFooterItems } from "../../position/[symbol]/AdviceCardView";
import { buildTechnicalFooterItems } from "../../position/[symbol]/TechnicalIndicatorsPanel";
import { buildSummaryFooterItems } from "../operationSummary";
import type { AdviceCard, AdviceResponse, Bar, SignalsPayload } from "../types";
import {
  ENTRY_BASIS_MOMENTUM,
  ENTRY_BASIS_PULLBACK,
  ENTRY_BASIS_RULES,
  ENTRY_BASIS_TREND,
  ENTRY_BASIS_VOLUME,
  ENTRY_CONDITION_LABELS,
  ENTRY_CONDITION_THRESHOLDS,
  ENTRY_E1_QUALIFIER,
  ENTRY_E2_XREF,
  ENTRY_E3_DASH_NOTE,
  ENTRY_NO_DATA_STATEMENT,
  ENTRY_PANEL_TAGLINE,
  ENTRY_PANEL_TITLE,
  ENTRY_STATUS_LABELS,
  LADDER_BAND_NOTE,
  LADDER_BAND_TAG,
  buildConditionCount,
  buildDataTimesLine,
  buildDefensiveHitsText,
  buildEntryBasisRange,
  buildEntryFooterItems,
  buildEntryRangeNotValuationNote,
  buildRangeConditionLabel,
} from "../entryObservationWording";
import { ENTRY_PULLBACK_MAX_ABS_PCT, ENTRY_RANGE_MAX_PCT } from "../entryObservation";
import {
  ALERTS_LOAD_ERROR_PREFIX,
  ALERTS_MANAGE_LINK,
  ALERTS_NO_RULES,
  ALERTS_NO_RULES_LINK,
  ALERTS_SCHEDULER_DISABLED,
  DETAILS_SUMMARY_ENTRY,
  DETAILS_SUMMARY_GENERIC,
  DETAILS_SUMMARY_KEY_LEVELS,
  DETAILS_SUMMARY_OPERATION,
  DETAILS_SUMMARY_RISK_GAUGE,
  DETAILS_SUMMARY_TECHNICAL,
  FX_BACKUP_BADGE,
  buildAdviceHitCount,
  buildAlertsPendingCount,
  buildAlertsQueriedAt,
  buildAlertsRulesNoEvents,
  buildDataAsOfBadge,
  buildKeyLevelsOneLiner,
  buildTechOneLiner,
} from "../oneLinerWording";
import { RiskGaugeView } from "../../components/RiskGauge";
import type { BookLimitCheck, PortfolioLimitsResponse, SymbolDataMeta } from "../types";
import {
  DECISION_CARD_ARIA_LABEL,
  DECISION_CARD_DISTANCE_PREFIX,
  DECISION_CARD_QUANTITY_LABEL,
  buildDecisionCardDistance,
} from "../decisionCardWording";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import {
  buildListingOrderSentence,
  buildLookbackChip,
  DEMO_DATA_CARD_WARNING,
  SECTOR_CARD_TITLE,
  TWSE_ONLY_TAG,
} from "../sectorMomentumWording";

/** P2 算式行改寫後，計算依據常數為 { formula, qualifier }；掃描與釘住以攤平字串進行。 */
function flatBasis(item: BasisItem): string {
  // 以換行分隔，避免相鄰行的尾字與首字在攤平後誤組成禁用詞（qa-reviewer 建議）。
  return [...item.formula, item.qualifier ?? ""].join("\n");
}

const SCANNED_FILES = [
  "../../position/[symbol]/OperationSummaryPanel.tsx",
  "../../position/[symbol]/page.tsx",
  "../../components/NavBar.tsx",
  // FR-9's settings surface: the net-worth field's label, its hints and the
  // risk-widening confirmation are all hard-coded Traditional Chinese in JSX,
  // which is exactly the class of copy this scan exists to reach.
  "../../settings/NetWorthSection.tsx",
  "../../settings/SettingsForm.tsx",
  // R5 fix (risk-final-review.md): the advice-card surface and its wording
  // helpers had no coverage at all — exactly the gap that let R1/R2's
  // unattributed, non-whitelisted labels ship unscanned.
  "../../position/[symbol]/AdviceCardView.tsx",
  "../format.ts",
  "../../components/RiskGauge.tsx",
  "../../position/[symbol]/LimitsCheckList.tsx",
  "../operationSummary.ts",
  // 風控快審 2026-08-09：掃描覆蓋是文案核可前提，補上兩個原本未被掃到的
  // 持倉/警示規則表面。
  "../../components/EditPositionModal.tsx",
  "../../settings/AlertRulesSection.tsx",
  // 風控 2026-09-01 VETO 落地條件 3：關鍵價位面板全部字面納入掃描與逐字釘住。
  "../../position/[symbol]/KeyLevelsPanel.tsx",
  "../keyLevels.ts",
  // 個股頁減負（work/stock-desk-個股頁減負-PRD.md，風控 2026-09-02）：導讀／頁級
  // 揭露區／建議卡銜接句的新字面與其渲染元件。
  "../sectionTaglines.ts",
  // 揭露下沉頁尾（CEO 裁定 2026-09-06）：頁級揭露區元件退場，改為頁尾揭露區＋字面模組＋標題常數。
  "../../components/PageFooterDisclosures.tsx",
  "../footerDisclosureWording.ts",
  "../sectionTitles.ts",
  // 六項觀察條件（CEO 2026-09-06；PRD §4b 風控 R-01～R-22）：面板、字面模組、純函式。
  "../../position/[symbol]/EntryObservationPanel.tsx",
  "../entryObservationWording.ts",
  "../entryObservation.ts",
  // 減負批次 3（FR-6）：指標卡 description 為 inline props，納入掃描並逐字守門限定語。
  "../../position/[symbol]/TechnicalIndicatorsPanel.tsx",
  // FE-WIRING BLOCKING 退修 2026-08-09（qa-reviewer 建議）：ref 型條件的
  // 唯讀提示句是這批新加的硬編碼 JSX 文案，兩個相關檔案原本都未被掃到。
  "../../settings/EditAlertRuleModal.tsx",
  "../../settings/AlertParamFields.tsx",
  // 代號目錄 (FR-4/5/6/7, work/stock-desk-代號目錄-PRD.md): the combobox's
  // FR-7 degrade notices and the Q1(b) market-picker prompt are new
  // hard-coded strings, and `PositionsTable.tsx` now renders directory
  // company names inline — neither surface was scanned before this batch.
  "../directorySearch.ts",
  "../../components/PositionsTable.tsx",
  // CEO 指示 2026-08-09: 代號目錄自動完成接到「新增部位」表單的代號欄。
  // `SymbolCombobox.tsx` is the shared combobox both `ManualAddForm.tsx` and
  // `EditPositionModal.tsx` now render; its own hard-coded strings (aria
  // labels) are copied verbatim from the already-scanned `NavBar.tsx`, but
  // this file was never itself in the scan list.
  "../../components/SymbolCombobox.tsx",
  // 風控列管清償批(work/機會清單.md D1, 2026-08-10):新增的「證券目錄」設定頁
  // 區塊帶新的事實陳述文案，先前不在掃描範圍內。
  "../../settings/DirectorySection.tsx",
  // D3② (risk-fix-review.md N2 列管清償, 2026-08-16): this file used to be
  // *excluded* from the scan entirely because its pre-existing `METRIC_ROWS`
  // win-rate row label (a realized backtest statistic — the acknowledged-
  // historical-result 語境 risk-final-review.md already accepted for
  // RiskGauge, not probability laundering) would have been killed by the
  // verbatim match; a context whitelist entry masking that one source line
  // brought the rest of the file — including its D2-item-4 常駐警語 — into the
  // scan. C8-3(a) (2026-08-23) removed the need for the exception entirely:
  // the label is served by the backend now, so this file is scanned with no
  // allowlist entry of its own at all.
  "../../backtest/BacktestReportView.tsx",
  // CEO 2026-09-09 equity-curve chart: the wording module and the component
  // that renders it (legend, split labels, tooltip field names, empty state).
  "../../backtest/EquityCurveChart.tsx",
  "../backtestCurveWording.ts",
  // CEO 2026-09-12 event study on /backtest: the shell's own sentences and the page intro.
  "../../backtest/EventStudySection.tsx",
  "../../backtest/page.tsx",
  "../eventStudyWording.ts",
  // 排程台 (`/playbook`, work/stock-desk-快市排程-視覺規範.md 派工單
  // 2026-08-12): new surface, new hard-coded JSX text (headings, the
  // EMERGENCY_EXIT flow's risk-compliance-approved button labels, the mirrored
  // `EXIT_CONFIRM_CHECKS` constants). None of these files existed before this
  // batch, so none were previously in this scan.
  "../playbookView.ts",
  "../../playbook/page.tsx",
  "../../playbook/ModeStatusBar.tsx",
  "../../playbook/DirectiveLedger.tsx",
  "../../playbook/PositionSnapshotTable.tsx",
  "../../playbook/SettlementPanel.tsx",
  "../../playbook/EmergencyExitControl.tsx",
  // 規則集確認 + 資本設定入口 (派工單 2026-08-12): the block's own functional
  // labels (區塊標題／小標／資本欄標籤／按鈕／失敗標籤), the two sentences stating
  // what confirming means and the 資金用途句 next to the capital field (五輪定稿
  // ⑥/④) are hard-coded JSX text, which is exactly the class of copy this scan
  // exists to reach. Their approved *wording* is pinned separately, against the
  // rendered output, by `app/playbook/__tests__/RuleSetConfirmPanel.test.ts`.
  "../../playbook/RuleSetConfirmPanel.tsx",
  // D4 定稿(work/stock-desk-D4-資料來源措辭.md,含 R-D4-1,risk-compliance
  // -officer APPROVE):美股揭露句是這批新加的硬編碼 JSX 文案，該檔先前完全
  // 不在掃描清單內。
  "../../settings/DataSourcesSection.tsx",
  // 產業別自動帶入 (CEO 指示 2026-08-16): `ManualAddForm.tsx` gains the 產業別
  // dropdown and both position forms now render `SECTOR_SOURCE_DISCLOSURE`.
  // The add form was never in this scan at all despite carrying hard-coded
  // field labels and hints since it shipped.
  "../../positions/import/ManualAddForm.tsx",
  // TradingView 嵌入 (CEO 派工單 2026-08-16): the chart panel's disclosure
  // sentence and the widget-load fallback message are new hard-coded JSX
  // literals; this file was never in the scan before this batch existed.
  "../../position/[symbol]/TradingViewChartPanel.tsx",
  // C5 Kelly Lane K4c-2 (2026-08-22, `work/reviews/2026-08-19-C5-Kelly-文案批審.md`):
  // the settings-page Kelly surface. `KellyDisclosuresPanel.tsx` also has its
  // own stricter zero-Chinese-literal scan
  // (`app/lib/__tests__/kellyDisclosuresPanel.test.ts`, which asserts no Han
  // character survives at all outside a comment) — added here too so it never
  // becomes a blind spot if that dedicated test is ever removed.
  "../../settings/KellyInputsSection.tsx",
  "../../settings/KellyManualInputForm.tsx",
  "../../settings/KellyImportDialog.tsx",
  "../../settings/KellyDisclosuresPanel.tsx",
  // 圖形化 1–3（CEO 2026-09-06）：位階量表、價位階梯、指標速覽區帶標籤與規則方向
  // 標籤是新面向使用者字面；三個純函式模組只帶 doc comment，但一併納入以免日後
  // 有人把字面搬進去而逃出掃描。
  "../../position/[symbol]/RangeGauge.tsx",
  "../../position/[symbol]/PriceLadder.tsx",
  "../keyLevelsVisuals.ts",
  "../indicatorBands.ts",
  "../ruleDirection.ts",
  // 一眼一句實作規格（`work/stock-desk-一眼一句-實作規格.md`）風控逐字審 R-A2 落地
  // 條件 1：`oneLinerWording.ts`（個股頁＋首頁新字面集中檔）與首頁新元件
  // `AlertStatusStrip.tsx` 先前都不在掃描清單內。
  "../oneLinerWording.ts",
  "../../components/AlertStatusStrip.tsx",
  // 決策卡（`work/stock-desk-一眼一句簡化-派工單.md` §5.4；視覺規範 B.7）：
  // 新元件與其專屬字面模組，先前都不在掃描清單內。
  "../../position/[symbol]/DecisionCard.tsx",
  "../decisionCardWording.ts",
  // 族群動能排行（第四波，`work/stock-desk-族群動能-派工單.md` §12/§13）：新首頁
  // 卡與其專屬字面模組，先前都不在掃描清單內。
  "../../components/SectorMomentumCard.tsx",
  "../sectorMomentumWording.ts",
] as const;

/**
 * D3② 語境白名單 (risk-fix-review.md N2): per-file *exact source lines* in
 * which a banned term is an acknowledged historical statistic or an admitted
 * limitation rather than a claim. `assertNoForbiddenTerms` masks only these
 * exact strings and rejects entries that are dead (no banned term) or stale
 * (no longer in the file), so the whitelist cannot rot into a loophole; the
 * term stays banned everywhere else in the same file. Adding an entry here is
 * a wording-governance decision — cite the review that accepted the 語境.
 */
const ALLOWED_SOURCE_CONTEXTS: Partial<Record<(typeof SCANNED_FILES)[number], readonly string[]>> =
  {
    // C8-2 (風控 2026-08-23 批審, `work/reviews/2026-08-23-C8-顯示語意-風控批審.md`):
    // `BacktestReportView.tsx`'s entry is **deleted**, not updated. Its win-rate
    // row label is backend copy now (C8-3 路徑 a: served on
    // `BacktestResponse.metric_labels`, single definition site
    // `app/api/kelly_wording.py`), so the file carries no banned term at all and
    // needs no exception — and `assertNoForbiddenTerms` rejects stale entries,
    // so keeping one would have turned this scan red. The whitelist's headcount
    // therefore goes down by one; it is not widened and gains no second entry.
    // D8 句 3 第二輪 (`work/reviews/2026-08-19-句1句3重寫-風控批審.md` 落地條件
    // 6/10): the mandated 列管註記 doc comment on
    // `TRADINGVIEW_CHART_DATA_MISMATCH_STATEMENT` quotes the review's own
    // required wording verbatim ("須立即重送風控"), an internal escalation
    // instruction to future maintainers, not user-facing copy — the
    // acknowledged-limitation/instruction 語境 this whitelist exists for (D3② /
    // risk-fix-review.md N2), scoped to this one comment line.
    //
    // 註解更正 (風控追加裁示 2026-08-23「附帶查獲」,
    // `work/reviews/2026-08-23-C8-顯示語意-風控批審.md`): this note used to cite
    // "the 「勝率」 line above" as its precedent. That entry — the
    // `BacktestReportView.tsx` win-rate row label — was deleted by C8-2 in the
    // same batch (the label became backend copy), so the referent no longer
    // exists and the citation had become the same kind of false governance
    // statement C8-5 was raised for. The 語境 rule stands on its own; this is
    // now the whitelist's only entry.
    "../../position/[symbol]/TradingViewChartPanel.tsx": [
      " * 列管：一旦系統新增任何跨資料源比對/校正邏輯，「本系統不會將兩者互相校正」即失真，須立即重送風控。",
    ],
  };

describe("component source scan — §1.3 banned-term coverage on hard-coded JSX text", () => {
  for (const relativePath of SCANNED_FILES) {
    const absolutePath = fileURLToPath(new URL(relativePath, import.meta.url));
    const source = readFileSync(absolutePath, "utf-8");

    it(`${relativePath}: contains none of the §1.3 banned terms`, () => {
      assertNoForbiddenTerms(
        source,
        FRONTEND_FORBIDDEN_TERMS,
        relativePath,
        ALLOWED_SOURCE_CONTEXTS[relativePath] ?? [],
      );
    });

    it(`${relativePath}: every "即時" occurrence is a "非即時" denial, never a bare claim`, () => {
      expect(findBareRealtimeClaims(source)).toEqual([]);
    });
  }
});

/**
 * D4 揭露句 (`work/stock-desk-D4-資料來源措辭.md`「一之 2」，含 R-D4-1)：
 * 比照 `adviceWording.test.ts` 對 `AS_OF_DATE_UNKNOWN_STATEMENT` 的作法，把
 * exported 常數本身（而不只是原始檔案文字）納入掃描面，防止日後改寫時只改了
 * JSX 卻漏改常數（或反之）而逃過上面的原始檔掃描。
 */
describe("DataSourcesSection.tsx — US_DATA_SOURCE_DISCLOSURE_STATEMENT (D4 定稿逐字)", () => {
  it("contains none of the §1.3 banned terms", () => {
    assertNoForbiddenTerms(
      US_DATA_SOURCE_DISCLOSURE_STATEMENT,
      FRONTEND_FORBIDDEN_TERMS,
      "US_DATA_SOURCE_DISCLOSURE_STATEMENT",
    );
  });

  it("every '即時' occurrence is a '非即時' denial, never a bare claim", () => {
    expect(findBareRealtimeClaims(US_DATA_SOURCE_DISCLOSURE_STATEMENT)).toEqual([]);
  });

  it("matches the D4 定稿 verbatim wording, including the R-D4-1 ALPHA_VANTAGE_DAILY_LIMIT sentence", () => {
    expect(US_DATA_SOURCE_DISCLOSURE_STATEMENT).toBe(
      "美股（US）已完成接線，並以測試替身通過自動化測試；尚未以真實 API key 對外部服務實際發送過請求。" +
        "需設定環境變數 ALPHA_VANTAGE_API_KEY；未設定時此層直接跳過，不嘗試發送請求。" +
        "另需設定環境變數 ALPHA_VANTAGE_DAILY_LIMIT（每日額度上限）；此設定未完成時，主要來源同樣直接跳過，不會發出任何請求。" +
        "實際覆蓋率、速率限制與資料品質目前未知，應視為待查證狀態。",
    );
  });
});

/**
 * D5④/D5⑤ (2026-08-13 衝刺覆核列管;字面 2026-08-16 改稿,**待風控覆核**):
 * pins both table rows verbatim so the exact strings sent to review are the
 * ones that ship, and any later edit is a visible test change rather than a
 * silent drift. TW 備援鏈補終局「→ 資料不足」並比照 US 列已核可格式;US 主要
 * 來源欄括號改為與 S7 註記同字面(由 `US_MARKET_OPTION_CAVEAT` 組成,不可能
 * 漂移),肯定語半句仍逐字保留於下方 D4 揭露句。
 */
/**
 * TradingView 嵌入：兩句均為 **risk-compliance-officer 逐字定稿（2026-08-16，
 * 揭露句二輪 CONFIRMED、失敗句三輪刪尾版 CONFIRMED，歷程見
 * work/stock-desk-D4-資料來源措辭.md 第七節/七之二）**。逐字釘住定稿字面，
 * 任何變更視為漂移須重送風控後才能同步更新此處與常數本身。
 */
describe("TradingViewChartPanel.tsx — 揭露句與 fallback 文案 (風控逐字定稿)", () => {
  it("disclosure statement: contains none of the §1.3 banned terms", () => {
    assertNoForbiddenTerms(
      TRADINGVIEW_CHART_DISCLOSURE_STATEMENT,
      FRONTEND_FORBIDDEN_TERMS,
      "TRADINGVIEW_CHART_DISCLOSURE_STATEMENT",
    );
  });

  it("disclosure statement: every '即時' occurrence is a '非即時' denial, never a bare claim", () => {
    expect(findBareRealtimeClaims(TRADINGVIEW_CHART_DISCLOSURE_STATEMENT)).toEqual([]);
  });

  it("disclosure statement matches the risk-approved wording verbatim", () => {
    expect(TRADINGVIEW_CHART_DISCLOSURE_STATEMENT).toBe(
      "此互動圖表由 TradingView 提供；其資料來源與本系統自有的行情資料鏈是各自獨立的兩條路徑，" +
        "本系統未查證此圖表資料的正確性、完整性或時效性，亦不為其負責；" +
        "本系統無法標示其資料時間與延遲狀態；" +
        "圖表內容僅供檢視、不參與本系統任何計算或建議產出，載入需要網路連線。",
    );
  });

  it("fallback message: contains none of the §1.3 banned terms", () => {
    assertNoForbiddenTerms(
      TRADINGVIEW_CHART_FALLBACK_MESSAGE,
      FRONTEND_FORBIDDEN_TERMS,
      "TRADINGVIEW_CHART_FALLBACK_MESSAGE",
    );
  });

  it("fallback message: every '即時' occurrence is a '非即時' denial, never a bare claim", () => {
    expect(findBareRealtimeClaims(TRADINGVIEW_CHART_FALLBACK_MESSAGE)).toEqual([]);
  });

  it("fallback message matches the risk-approved wording verbatim", () => {
    expect(TRADINGVIEW_CHART_FALLBACK_MESSAGE).toBe(
      "互動圖表目前未能載入，可能原因是網路連線不穩、瀏覽器擴充套件（例如廣告攔截）攔截了外部資源，" +
        "或 TradingView 服務本身暫時無法連線；可重新整理頁面再試一次，或可改用「本地圖表」頁籤。",
    );
  });

  // TradingView 列管小項 (2026-08-16 審查全紀錄): the invalid-symbol message is
  // a technical error notice, not risk-gated advice copy (qa 複審 low 觀察 —
  // 「不落風險閘門」), so unlike the two sentences above it gets the banned-term
  // and bare-"即時" scans only, **not** a verbatim pin: rewording it does not
  // require a risk resubmission, but it must never grow a banned term.
  it("invalid-symbol message: contains none of the §1.3 banned terms", () => {
    assertNoForbiddenTerms(
      TRADINGVIEW_CHART_INVALID_SYMBOL_MESSAGE,
      FRONTEND_FORBIDDEN_TERMS,
      "TRADINGVIEW_CHART_INVALID_SYMBOL_MESSAGE",
    );
  });

  it("invalid-symbol message: every '即時' occurrence is a '非即時' denial, never a bare claim", () => {
    expect(findBareRealtimeClaims(TRADINGVIEW_CHART_INVALID_SYMBOL_MESSAGE)).toEqual([]);
  });
});

/**
 * D8 句 3 (`work/reviews/2026-08-19-句1句3重寫-風控批審.md`「句 3 第二輪 —
 * CONFIRMED(修訂版)」，落地條件 1-10)：獨立新常數
 * `TRADINGVIEW_CHART_DATA_MISMATCH_STATEMENT` 與現有揭露句串接成
 * `TRADINGVIEW_CHART_DISCLOSURE_FULL_STATEMENT`，兩個渲染點一律改渲染 FULL
 * 常數。落地條件 5：補句常數與 FULL 常數各加逐字釘住 + 禁用詞掃描 + 裸「即時」
 * 掃描，與常數同一 commit。落地條件 9：另加兩條反向斷言，防止「各自獨立的兩
 * 條路徑」與「兩者」被善意補回而重新變成不唯一/冗贅。
 */
describe("TradingViewChartPanel.tsx — 價量不一致補句 (D8 句 3 第二輪 CONFIRMED 修訂版)", () => {
  it("mismatch statement: contains none of the §1.3 banned terms", () => {
    assertNoForbiddenTerms(
      TRADINGVIEW_CHART_DATA_MISMATCH_STATEMENT,
      FRONTEND_FORBIDDEN_TERMS,
      "TRADINGVIEW_CHART_DATA_MISMATCH_STATEMENT",
    );
  });

  it("mismatch statement: every '即時' occurrence is a '非即時' denial, never a bare claim", () => {
    expect(findBareRealtimeClaims(TRADINGVIEW_CHART_DATA_MISMATCH_STATEMENT)).toEqual([]);
  });

  it("mismatch statement matches the risk-approved wording verbatim (retyped, not imported)", () => {
    // 落地條件 5: must be a fresh retype of the reviewed literal, not a
    // self-comparison against the constant this test is guarding.
    expect(TRADINGVIEW_CHART_DATA_MISMATCH_STATEMENT).toBe(
      "此圖表顯示的價格與成交量，可能與本系統自有的行情資料鏈不一致；本系統不會將兩者互相校正。",
    );
  });

  it("full statement: contains none of the §1.3 banned terms", () => {
    assertNoForbiddenTerms(
      TRADINGVIEW_CHART_DISCLOSURE_FULL_STATEMENT,
      FRONTEND_FORBIDDEN_TERMS,
      "TRADINGVIEW_CHART_DISCLOSURE_FULL_STATEMENT",
    );
  });

  it("full statement: every '即時' occurrence is a '非即時' denial, never a bare claim", () => {
    expect(findBareRealtimeClaims(TRADINGVIEW_CHART_DISCLOSURE_FULL_STATEMENT)).toEqual([]);
  });

  it("full statement matches the risk-approved wording verbatim (retyped, not imported)", () => {
    expect(TRADINGVIEW_CHART_DISCLOSURE_FULL_STATEMENT).toBe(
      "此互動圖表由 TradingView 提供；其資料來源與本系統自有的行情資料鏈是各自獨立的兩條路徑，" +
        "本系統未查證此圖表資料的正確性、完整性或時效性，亦不為其負責；" +
        "本系統無法標示其資料時間與延遲狀態；" +
        "圖表內容僅供檢視、不參與本系統任何計算或建議產出，載入需要網路連線。" +
        "此圖表顯示的價格與成交量，可能與本系統自有的行情資料鏈不一致；本系統不會將兩者互相校正。",
    );
  });

  it("full statement is the existing sentence and the mismatch sentence, in order, concatenated directly", () => {
    expect(TRADINGVIEW_CHART_DISCLOSURE_FULL_STATEMENT).toBe(
      TRADINGVIEW_CHART_DISCLOSURE_STATEMENT + TRADINGVIEW_CHART_DATA_MISMATCH_STATEMENT,
    );
    expect(TRADINGVIEW_CHART_DISCLOSURE_FULL_STATEMENT.startsWith(TRADINGVIEW_CHART_DISCLOSURE_STATEMENT)).toBe(
      true,
    );
    expect(TRADINGVIEW_CHART_DISCLOSURE_FULL_STATEMENT.endsWith(TRADINGVIEW_CHART_DATA_MISMATCH_STATEMENT)).toBe(
      true,
    );
  });

  // 落地條件 9(反向斷言，防「補回」漂移):第二輪裁決刪去了第三稿「兩者是各自
  // 獨立的兩條路徑，」這個冗贅分句，並把「兩者」收斂為單一指涉。這兩條斷言釘
  // 死該裁定，防止日後有人善意把被刪的分句加回來，或讓「兩者」重新變得不唯一。
  it("'各自獨立的兩條路徑' appears exactly once in the FULL statement (no reintroduced redundant clause)", () => {
    expect(TRADINGVIEW_CHART_DISCLOSURE_FULL_STATEMENT.match(/各自獨立的兩條路徑/g)?.length ?? 0).toBe(1);
  });

  it("'兩者' appears exactly once in the FULL statement (single, unambiguous referent)", () => {
    expect(TRADINGVIEW_CHART_DISCLOSURE_FULL_STATEMENT.match(/兩者/g)?.length ?? 0).toBe(1);
  });
});

describe("DataSourcesSection.tsx — CONFIGURED_SOURCES rows (D5④/D5⑤ 字面,待風控覆核)", () => {
  it("TW row names the ladder's real terminal layers in the US row's approved format", () => {
    expect(CONFIGURED_SOURCES[0]).toEqual({
      market: "TW",
      primary: "TWSE（證交所）",
      backups: "TPEx（櫃買中心）→ FinMind → 任何可用快取 → 資料不足",
    });
  });

  it("US primary cell carries the S7 caveat verbatim, not the affirmative-only parenthetical", () => {
    expect(CONFIGURED_SOURCES[1]).toEqual({
      market: "US",
      primary: "Alpha Vantage（資料來源未經真實環境驗證）",
      backups:
        "TTL 內本地快取（優先於主要來源）→ Alpha Vantage → yfinance → 任何可用快取 → 資料不足",
    });
  });
});

/**
 * 風控 2026-09-01 VETO 落地條件 3：關鍵價位面板全部面向使用者字面
 * (`work/stock-desk-關鍵價位-文案成稿.md`，creative-lead 第二版定稿) 逐字
 * 釘住＋禁用詞掃描＋裸「即時」掃描。字面（含標點）不得再改動，任何變更視為
 * 漂移須重送風控。
 */
describe("KeyLevelsPanel 定稿字面", () => {
  const STATIC_CONSTANTS: Record<string, string> = {
    KEY_LEVELS_PANEL_TITLE,
    KEY_LEVELS_PANEL_DISCLAIMER,
    KEY_LEVELS_HEADER_STALENESS_SELF_NOTICE,
    KEY_LEVELS_HEADER_UNADJUSTED_NOTICE,
    KEY_LEVELS_HEADER_DASH_NOTICE,
    KEY_LEVELS_ZONE_LABEL_LOW,
    KEY_LEVELS_ZONE_LABEL_MID,
    KEY_LEVELS_ZONE_LABEL_HIGH,
    KEY_LEVELS_MA60_DEVIATION_LABEL,
    KEY_LEVELS_PULLBACK_CARD_TITLE,
    KEY_LEVELS_PULLBACK_EXPLAIN_NOTE,
    KEY_LEVELS_PULLBACK_ROW_MA20,
    KEY_LEVELS_PULLBACK_ROW_MA60,
    KEY_LEVELS_PULLBACK_ROW_RECENT_LOW60,
    KEY_LEVELS_STOP_CARD_TITLE,
    KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE,
    KEY_LEVELS_STOP_CONDITION_ATR_UNAVAILABLE,
    KEY_LEVELS_STOP_ROW_ATR,
    KEY_LEVELS_STOP_ROW_FIXED_PCT,
    KEY_LEVELS_STOP_S5_NEUTRAL_NOTE,
    KEY_LEVELS_TARGET_CARD_TITLE,
    KEY_LEVELS_TARGET_ANCHOR_CROSS_REF,
    KEY_LEVELS_TARGET_STANDING_NOTICE,
    KEY_LEVELS_TARGET_ROW_2R,
    KEY_LEVELS_TARGET_ROW_FIXED_PCT,
    KEY_LEVELS_TARGET_ROW_TRAILING_LABEL,
    KEY_LEVELS_TARGET_ROW_TRAILING_NOTE,
    KEY_LEVELS_BASIS_ZONE: flatBasis(KEY_LEVELS_BASIS_ZONE),
    KEY_LEVELS_BASIS_MA: flatBasis(KEY_LEVELS_BASIS_MA),
    KEY_LEVELS_BASIS_RECENT_LOW60: flatBasis(KEY_LEVELS_BASIS_RECENT_LOW60),
    KEY_LEVELS_BASIS_ATR: flatBasis(KEY_LEVELS_BASIS_ATR),
    KEY_LEVELS_BASIS_STOP: flatBasis(KEY_LEVELS_BASIS_STOP),
    KEY_LEVELS_BASIS_TARGET: flatBasis(KEY_LEVELS_BASIS_TARGET),
    KEY_LEVELS_BASIS_CLOSE_DISTANCE: flatBasis(KEY_LEVELS_BASIS_CLOSE_DISTANCE),
    KEY_LEVELS_BASIS_ANCHOR: flatBasis(KEY_LEVELS_BASIS_ANCHOR),
    KEY_LEVELS_BASIS_PULLBACK: flatBasis(KEY_LEVELS_BASIS_PULLBACK),
    KEY_LEVELS_BASIS_UNADJUSTED_XREF,
    KEY_LEVELS_BASIS_SECTION_TITLE,
    KEY_LEVELS_NO_DATA_STATEMENT,
  };

  const BUILT_SAMPLES: Record<string, string> = {
    buildKeyLevelsCloseLine: buildKeyLevelsCloseLine("918.66", "2026-09-01"),
    buildRangeCardTitle: buildRangeCardTitle(252),
    buildRangeLabel: buildRangeLabel(252),
    buildRangeNotValuationNote: buildRangeNotValuationNote(252),
    buildRangeInsufficientReason: buildRangeInsufficientReason(42),
    buildRangeFlatReason: buildRangeFlatReason(300),
    buildStopBasisHeldWithCost: buildStopBasisHeldWithCost("895.44"),
    buildStopBasisConfirmedNotHeld: buildStopBasisConfirmedNotHeld("918.66"),
    buildStopBasisUnknown: buildStopBasisUnknown("918.66"),
    buildBasisClose: flatBasis(buildBasisClose("918.66", "2026-09-01")),
    buildBasisRange: flatBasis(buildBasisRange(252)),
    buildFooterSample: buildFooterSample(387, "2026-09-01"),
  };

  it("每一句定稿：不含 §1.3 禁用詞", () => {
    for (const [name, text] of [...Object.entries(STATIC_CONSTANTS), ...Object.entries(BUILT_SAMPLES)]) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, name);
    }
  });

  it("每一句定稿：每個「即時」都是否定語境，無裸即時宣稱", () => {
    for (const text of [...Object.values(STATIC_CONSTANTS), ...Object.values(BUILT_SAMPLES)]) {
      expect(findBareRealtimeClaims(text)).toEqual([]);
    }
  });

  it("頭部揭露段逐字比對成稿", () => {
    expect(KEY_LEVELS_PANEL_DISCLAIMER).toBe(
      "以下數字皆為本面板依固定算式計算之參考水位，僅供研究與教育用途，非投資建議，亦非任何買賣指示；" +
        "每個數字的計算方式，包括收盤資料的來源，皆在「計算依據」中逐項揭露。",
    );
    expect(KEY_LEVELS_HEADER_STALENESS_SELF_NOTICE).toBe(
      "本面板不判斷、也不另行標示所使用的日線資料是否已經過舊。",
    );
    expect(KEY_LEVELS_HEADER_UNADJUSTED_NOTICE).toBe(
      "以下所有計算皆以未還原權值之原始收盤價進行；跨除權息日之區間、均線與 ATR(14) 可能因此失真。",
    );
    expect(KEY_LEVELS_HEADER_DASH_NOTICE).toBe(
      "面板中以「—」呈現的欄位，代表可用日線根數尚未達最低計算門檻，並非數值為零或計算結果為零。",
    );
  });

  it("三態基準句逐字比對成稿（{X} 代入）", () => {
    expect(buildStopBasisHeldWithCost("895.44")).toBe("本卡以你的持倉平均成本 895.44 為基準計算。");
    expect(buildStopBasisConfirmedNotHeld("918.66")).toBe(
      "未持有此標的，以最新收盤 918.66 試算；此數字不是任何進場暗示。",
    );
    expect(buildStopBasisUnknown("918.66")).toBe("持倉成本尚未取得，暫以最新收盤 918.66 試算。");
  });

  it("R5 停利常駐句與 R9 條件句逐字比對成稿", () => {
    expect(KEY_LEVELS_TARGET_STANDING_NOTICE).toBe(
      "以下數字皆由固定算式自基準價推得，僅為算式計算結果，不代表價格未來會到達此水位；" +
        "「2R」所稱賺賠比 2:1，僅描述算式中兩個差值之間的比例關係，不代表任何達成機率。",
    );
    expect(KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE).toBe("大字為 2×ATR(14) 與 −8% 兩者中較緊（虧損較小）者。");
    expect(KEY_LEVELS_STOP_CONDITION_ATR_UNAVAILABLE).toBe("ATR(14) 資料不足，大字僅為 −8% 固定停損。");
  });

  it("無資料狀態句與頁尾樣本句逐字比對成稿（R4 無未來式承諾）", () => {
    expect(KEY_LEVELS_NO_DATA_STATEMENT).toBe("目前沒有可用的日線資料，本面板無法計算任何關鍵價位。");
    expect(buildFooterSample(387, "2026-09-01")).toBe(
      "計算樣本：387 根日線，最後一根 2026-09-01。本面板僅供研究與教育用途，不構成投資建議。",
    );
  });

  // 風控第二輪 R16：其餘全部常數逐字釘住（retyped, not imported）。
  it("標題、收盤列與位階卡字面逐字比對成稿", () => {
    expect(KEY_LEVELS_PANEL_TITLE).toBe("關鍵價位參考");
    expect(buildKeyLevelsCloseLine("918.66", "2026-09-01")).toBe("收盤 918.66（2026-09-01）");
    expect(buildRangeCardTitle(252)).toBe("近 252 根日線位階");
    expect(KEY_LEVELS_ZONE_LABEL_LOW).toBe("區間下緣");
    expect(KEY_LEVELS_ZONE_LABEL_MID).toBe("區間中段");
    expect(KEY_LEVELS_ZONE_LABEL_HIGH).toBe("區間上緣");
    expect(buildRangeLabel(252)).toBe("近 252 根區間");
    expect(KEY_LEVELS_MA60_DEVIATION_LABEL).toBe("對 MA60 乖離");
    expect(buildRangeNotValuationNote(252)).toBe(
      "位階描述價格相對自身近 252 根區間的位置，不等於便宜或昂貴的估值判斷。",
    );
    expect(buildRangeInsufficientReason(42)).toBe(
      "日線根數不足，本次無法計算區間位階（僅有 42 根，至少需要 60 根）。",
    );
    expect(buildRangeFlatReason(300)).toBe(
      "本次採樣的 300 根日線中，最高價與最低價相同，位階公式的分母為零，無法定義位階。",
    );
  });

  it("拉回卡與停損/停利卡其餘字面逐字比對成稿", () => {
    expect(KEY_LEVELS_PULLBACK_CARD_TITLE).toBe("拉回觀察參考");
    expect(KEY_LEVELS_PULLBACK_EXPLAIN_NOTE).toBe(
      "本面板固定以 MA20、MA60、近 60 日低點作為拉回觀察區；是否跌破為觀察條件，不是進出指令；" +
        "並非本系統對任何族群實際行為的統計，本系統未持有此類統計資料。",
    );
    expect(KEY_LEVELS_PULLBACK_ROW_MA20).toBe("MA20");
    expect(KEY_LEVELS_PULLBACK_ROW_MA60).toBe("MA60");
    expect(KEY_LEVELS_PULLBACK_ROW_RECENT_LOW60).toBe("近 60 日低點");
    expect(KEY_LEVELS_STOP_CARD_TITLE).toBe("停損參考");
    expect(KEY_LEVELS_STOP_ROW_ATR).toBe("2×ATR(14)");
    expect(KEY_LEVELS_STOP_ROW_FIXED_PCT).toBe("−8% 固定停損");
    expect(KEY_LEVELS_STOP_S5_NEUTRAL_NOTE).toBe(
      "停損參考水位與最新收盤的相對高低，因基準價與波動不同而不同，可能高於也可能低於最新收盤。",
    );
    expect(KEY_LEVELS_TARGET_CARD_TITLE).toBe("停利參考");
    expect(KEY_LEVELS_TARGET_ANCHOR_CROSS_REF).toBe("本卡數字所用之基準價，與「停損參考」卡片相同。");
    expect(KEY_LEVELS_TARGET_ROW_2R).toBe("2R（賺賠比 2:1）");
    expect(KEY_LEVELS_TARGET_ROW_FIXED_PCT).toBe("+20% 固定停利");
    expect(KEY_LEVELS_TARGET_ROW_TRAILING_LABEL).toBe("移動停利觀察");
    expect(KEY_LEVELS_TARGET_ROW_TRAILING_NOTE).toBe(
      "（與「拉回觀察」卡片的 MA20 為同一數字；系統並未另行計算移動停利水位，僅以跌破 MA20 作為觀察條件）",
    );
  });

  it("計算依據全部條目逐字比對成稿（P2 算式行＋限定語，限定語一字不動）", () => {
    expect(KEY_LEVELS_BASIS_SECTION_TITLE).toBe("計算依據（逐項揭露）");
    expect(buildBasisClose("918.66", "2026-09-01")).toEqual({
      formula: ["收盤（本面板所有計算所稱之）=系統行情資料鏈中該標的最近一根日線收盤價，與頂部「收盤 918.66（2026-09-01）」同一數字。"],
      qualifier: null,
    });
    expect(buildBasisRange(252)).toEqual({
      formula: ["位階(近252根)=(收盤-近252根K線最低價)/(近252根K線最高價-近252根K線最低價)×100%"],
      qualifier: "252 最多取 252 根，不足 252 根時以實際根數計算，未滿 60 根時不計算位階。",
    });
    expect(KEY_LEVELS_BASIS_ZONE).toEqual({
      formula: ["分類：位階≤30%→標示「區間下緣」；≥70%→標示「區間上緣」；其餘→標示「區間中段」；"],
      qualifier: "30%／70% 這兩個門檻為本面板自訂之分類標準，並無實證依據，亦非任何機構或研究之結論。",
    });
    expect(KEY_LEVELS_BASIS_MA).toEqual({
      formula: ["MA20＝近20根收盤價簡單平均；MA60＝近60根收盤價簡單平均；MA60乖離%=(收盤/MA60-1)×100%"],
      qualifier: null,
    });
    expect(KEY_LEVELS_BASIS_RECENT_LOW60).toEqual({ formula: ["近60日低點=近60根日線最低價最小值"], qualifier: null });
    expect(KEY_LEVELS_BASIS_ATR).toEqual({
      formula: ["ATR(14)=近14根日線真實波幅(TR)簡單平均"],
      qualifier: "未滿 15 根日線時無法計算，本面板不以其他方式估算或填補。",
    });
    expect(KEY_LEVELS_BASIS_STOP).toEqual({
      formula: [
        "停損參考：",
        "ATR(14)可得→大字=「基準價-2×ATR(14)」與「基準價×0.92」中較緊(虧損較小)者",
        "ATR(14)不可得→大字=基準價×0.92",
      ],
      qualifier:
        "本面板固定採 −8% 作為固定停損比例，僅為本面板自訂之算式參數，並非本系統對任何族群實際行為的統計，本系統未持有此類統計資料。",
    });
    expect(KEY_LEVELS_BASIS_TARGET).toEqual({
      formula: ["停利參考：", "2R=基準價+2×(基準價-上方停損參考大字)", "固定停利=基準價×1.2（本面板固定採 +20%）"],
      qualifier:
        "此為算式定義下賺賠比 2:1 的計算結果，不代表任何達成機率；" +
        "同樣僅為本面板自訂之算式參數，並非本系統對任何族群實際行為的統計，本系統未持有此類統計資料；" +
        "「移動停利觀察」顯示的是 MA20 的同一數字，系統並未另行計算移動停利水位，僅以跌破 MA20 作為觀察條件。",
    });
    // 決策卡 required 條件 3（`work/stock-desk-一眼一句簡化-派工單.md` §5.4）：
    // 距最新收盤算式行＋qualifier，緊接 `KEY_LEVELS_BASIS_TARGET` 之後。
    expect(KEY_LEVELS_BASIS_CLOSE_DISTANCE).toEqual({
      formula: [
        "距最新收盤：",
        "停損距離=(停損參考-最新收盤)/最新收盤×100%",
        "停利距離=(停利參考-最新收盤)/最新收盤×100%",
      ],
      qualifier:
        "停損參考與停利參考皆由基準價推得，此處距離之分母為最新收盤，兩者基準不同；" +
        "距離為算式結果，不代表價格會依此幅度到達任一價位。",
    });
    expect(flatBasis(KEY_LEVELS_BASIS_CLOSE_DISTANCE)).toContain("不代表價格會依此幅度到達任一價位");
    expect(KEY_LEVELS_BASIS_ANCHOR).toEqual({
      formula: [
        "基準價：",
        "持有且成本可得→基準價=持倉平均成本",
        "持有但成本未取得→基準價=最新收盤(試算)",
        "未持有→基準價=最新收盤(試算)；此數字不是任何進場暗示。",
      ],
      qualifier: null,
    });
    expect(KEY_LEVELS_BASIS_UNADJUSTED_XREF).toBe(
      "以上計算皆以未還原權值之原始收盤價進行，跨除權息日可能失真；完整說明見面板頂部揭露。",
    );
    expect(KEY_LEVELS_BASIS_PULLBACK).toEqual({
      formula: ["拉回觀察區=固定觀察價位{MA20,MA60,近60日低點}；是否跌破為觀察條件，不是進出指令；"],
      qualifier: "其餘限制說明見上方『拉回觀察參考』卡片，本處不重複列出。",
    });
    expect(flatBasis(KEY_LEVELS_BASIS_PULLBACK)).toContain("不是進出指令");
    // C9：否定式統計聲明仍須存在於頁面（卡片層承載）。
    expect(KEY_LEVELS_PULLBACK_EXPLAIN_NOTE).toContain("並非本系統對任何族群實際行為的統計");
    // P2 紅線：限定語／否定式子句一字不動——逐條 toContain 守門。
    expect(flatBasis(KEY_LEVELS_BASIS_ZONE)).toContain("並無實證依據，亦非任何機構或研究之結論");
    expect(flatBasis(KEY_LEVELS_BASIS_ATR)).toContain("本面板不以其他方式估算或填補");
    expect(flatBasis(KEY_LEVELS_BASIS_STOP)).toContain("並非本系統對任何族群實際行為的統計，本系統未持有此類統計資料");
    expect(flatBasis(KEY_LEVELS_BASIS_TARGET)).toContain("不代表任何達成機率");
    expect(flatBasis(KEY_LEVELS_BASIS_ANCHOR)).toContain("此數字不是任何進場暗示");
  });
});


/**
 * 個股頁減負（PRD FR-2／FR-3／FR-4 方向 A；風控 2026-09-02 預審 C1–C7 與逐字審）：
 * 新字面逐字釘住＋禁用詞掃描＋裸「即時」掃描，以及頁級揭露區的守門測試（C3：
 * page.tsx 缺席該區塊 ⇒ 紅燈；該區塊必須渲染 NON_REALTIME_NOTICE）。
 */
describe("個股頁減負 新字面與頁級揭露區守門", () => {
  const CONSTANTS: Record<string, string> = {
    OPERATION_SUMMARY_TAGLINE,
    KEY_LEVELS_TAGLINE,
    TECHNICAL_CHART_TAGLINE,
    TECHNICAL_INDICATORS_TAGLINE,
    LEVERAGE_CHAPTER_TAGLINE,
    PAGE_LEVEL_DISCLOSURE_SECTION_TITLE,
    PAGE_LEVEL_DISCLOSURE_SECTION_INTRO,
    ADVICE_CARD_XREF_TO_SUMMARY,
  };

  it("每一句：不含 §1.3 禁用詞、無裸即時宣稱", () => {
    for (const [name, text] of Object.entries(CONSTANTS)) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, name);
      expect(findBareRealtimeClaims(text)).toEqual([]);
    }
  });

  it("五則導讀逐字比對定稿，且每則 ≤ 30 字", () => {
    expect(OPERATION_SUMMARY_TAGLINE).toBe("這裡先給一句規則評估結論，細節在下方逐項展開。");
    expect(KEY_LEVELS_TAGLINE).toBe("這裡是系統依公式算出的參考價位，算法列在下方。");
    expect(TECHNICAL_CHART_TAGLINE).toBe("這裡呈現價格與均線圖表，方便比對數字與圖形。");
    expect(TECHNICAL_INDICATORS_TAGLINE).toBe("這裡列出技術指標數值，用途與計算方式見下方說明。");
    expect(LEVERAGE_CHAPTER_TAGLINE).toBe("這裡說明槓桿 ETF 的損耗特性，含拆解與假設情境試算。");
    for (const text of [
      OPERATION_SUMMARY_TAGLINE,
      KEY_LEVELS_TAGLINE,
      TECHNICAL_CHART_TAGLINE,
      TECHNICAL_INDICATORS_TAGLINE,
      LEVERAGE_CHAPTER_TAGLINE,
    ]) {
      expect([...text].length).toBeLessThanOrEqual(30);
    }
  });

  it("頁級揭露區標題與導語逐字比對定稿", () => {
    expect(PAGE_LEVEL_DISCLOSURE_SECTION_TITLE).toBe("本頁資料與計算揭露");
    expect(PAGE_LEVEL_DISCLOSURE_SECTION_INTRO).toBe(
      "以下為本頁共用的資料來源與更新頻率說明；各項計算方式與限制，另列於對應區塊。",
    );
  });

  it("建議卡銜接句逐字比對定稿（含 C7 的「非結論」否定式限定）", () => {
    expect(ADVICE_CARD_XREF_TO_SUMMARY).toBe(
      "結論、信心等級、免責事項、反面論點、失效條件與建議數量區間，已完整列於上方操作摘要；" +
        "本卡以下僅列命中規則、風險上限檢查與資料完整度等規則明細；規則明細本身不是結論。",
    );
    expect(ADVICE_CARD_XREF_TO_SUMMARY).toContain("規則明細本身不是結論");
  });

  it("C2/C3 守門（揭露下沉後）：page.tsx 必須渲染 PageFooterDisclosures，資料來源組以靜態常數渲染 NON_REALTIME_NOTICE", () => {
    const pageSource = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/page.tsx", import.meta.url)),
      "utf8",
    );
    expect(pageSource).toContain("<PageFooterDisclosures groups={footerGroups} />");
    // 無條件層（風控 L6-4）：資料來源組是字面常數，不掛在任何 query 狀態之下。
    expect(pageSource).toContain("{ title: PAGE_LEVEL_DISCLOSURE_SECTION_TITLE, items: [NON_REALTIME_NOTICE] }");
    const footerSource = readFileSync(
      fileURLToPath(new URL("../../components/PageFooterDisclosures.tsx", import.meta.url)),
      "utf8",
    );
    // C2：頁尾元件為純呈現，不得依賴任何 query 狀態。
    expect(footerSource).not.toMatch(/useQuery|useAdvice|useBars|isPending|isError/);
    expect(NON_REALTIME_NOTICE.length).toBeGreaterThan(0);
  });

  it("FR-6 守門：技術指標卡 description 的限定語與用途語逐字存在（風控 P2 落地條件）", () => {
    const src = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/TechnicalIndicatorsPanel.tsx", import.meta.url)),
      "utf8",
    );
    // 五則實際編輯者：定稿字面逐字釘住
    for (const text of [
      "收盤價於近期高低區間之相對位置，K、D 介於 0–100；僅為數值觀察。",
      "衡量近期價格波動幅度之統計量；不代表方向。",
      "衡量當日成交量偏離近 20 日平均之程度（正值偏高、負值偏低）；屬統計描述，不代表方向判斷。",
      "以近期日報酬標準差換算之年化數值，衡量價格波動程度之統計量；不代表方向或預測。",
      "觀察區間內高點到低點之最大跌幅，屬歷史統計描述，不代表未來會重演。",
    ]) {
      expect(src).toContain(text);
    }
    // 限定語不得流失
    for (const q of ["僅為數值觀察", "不代表方向", "屬統計描述，不代表方向判斷", "不代表方向或預測", "屬歷史統計描述", "不代表未來會重演", "不代表買賣訊號"]) {
      expect(src).toContain(q);
    }
    // 方案 (a)：三張未動卡片保留唯一用途語，兌現 TECHNICAL_INDICATORS_TAGLINE 的「用途…見下方說明」
    for (const u of ["用於觀察價格趨勢", "用於觀察趨勢動能變化", "用於觀察價格相對近期波動區間的位置"]) {
      expect(src).toContain(u);
    }
  });

  it("FR-2 wiring 守門：LEVERAGE_CHAPTER_TAGLINE（唯一仍渲染的導讀）確實由其宿主元件渲染（qa-reviewer 建議）", () => {
    const wiring: [string, string][] = [["../../position/[symbol]/LeverageChapterView.tsx", "{LEVERAGE_CHAPTER_TAGLINE}"]];
    for (const [rel, needle] of wiring) {
      const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
      expect(src, `${rel} 應渲染 ${needle}`).toContain(needle);
    }
  });

  /**
   * 一眼一句實作規格（`work/stock-desk-一眼一句-實作規格.md`）§2.2/§2.3/§2.4/§2.5：
   * 五則導讀常數仍存在（供既有 import／守門引用），但改為主視圖一句結論或
   * 直接省略——`OPERATION_SUMMARY_TAGLINE`／`KEY_LEVELS_TAGLINE`／
   * `TECHNICAL_CHART_TAGLINE`／`TECHNICAL_INDICATORS_TAGLINE`（技術分析）／
   * `ENTRY_PANEL_TAGLINE`（entryObservationWording.ts，非本檔「五則」之一）
   * 不再被任何個股頁元件渲染；`LEVERAGE_CHAPTER_TAGLINE`（槓桿專章，既有不動）
   * 是唯一例外，見上一則測試。
   */
  it("五則導讀＋ENTRY_PANEL_TAGLINE：常數仍存在但不再被個股頁元件渲染（一眼一句 §2.2–§2.5）", () => {
    expect(OPERATION_SUMMARY_TAGLINE).toBeTruthy();
    expect(KEY_LEVELS_TAGLINE).toBeTruthy();
    expect(TECHNICAL_CHART_TAGLINE).toBeTruthy();
    expect(TECHNICAL_INDICATORS_TAGLINE).toBeTruthy();
    expect(ENTRY_PANEL_TAGLINE).toBeTruthy();
    const retired: [string, string][] = [
      ["../../position/[symbol]/OperationSummaryPanel.tsx", "{OPERATION_SUMMARY_TAGLINE}"],
      ["../../position/[symbol]/page.tsx", "{OPERATION_SUMMARY_TAGLINE}"],
      ["../../position/[symbol]/KeyLevelsPanel.tsx", "{KEY_LEVELS_TAGLINE}"],
      ["../../position/[symbol]/page.tsx", "{KEY_LEVELS_TAGLINE}"],
      ["../../position/[symbol]/page.tsx", "{TECHNICAL_CHART_TAGLINE}"],
      ["../../position/[symbol]/page.tsx", "{TECHNICAL_INDICATORS_TAGLINE}"],
      ["../../position/[symbol]/EntryObservationPanel.tsx", "{ENTRY_PANEL_TAGLINE}"],
    ];
    for (const [rel, needle] of retired) {
      const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
      expect(src, `${rel} 不應再渲染 ${needle}`).not.toContain(needle);
    }
  });

  it("FR-4 C5 守門：建議卡必須渲染銜接句，且 AdviceCardView 不得單獨放回 headline／disclaimer／信心等級", () => {
    const src = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/AdviceCardView.tsx", import.meta.url)),
      "utf8",
    );
    // 一眼一句 §2.6：XREF 改由 page.tsx 的 <details> 承載（CEO 第二次裁定
    // 2026-09-19 後：展開內容第一行，非 summary），AdviceCardView 本身不再重複渲染。
    expect(src).not.toContain("{ADVICE_CARD_XREF_TO_SUMMARY}");
    const pageSrc = readFileSync(fileURLToPath(new URL("../../position/[symbol]/page.tsx", import.meta.url)), "utf8");
    expect(pageSrc).toContain("{ADVICE_CARD_XREF_TO_SUMMARY}");
    // C5：headline／信心等級／confidenceMeaning／disclaimer 同進同退——任何一項回流即紅燈。
    expect(src).not.toMatch(/buildAttributedHeadline|CANDIDATE_HEADING_LABEL|advice\.disclaimer|confidenceLabel\(|confidence_meaning/);
    // R-1：衝突揭露句指涉改為操作摘要的結論（逐字）。
    expect(src).toContain("本次同時命中方向相反的規則，上方操作摘要的結論只代表權重較高的一方。");
  });

  it("P1／L6-5 順序守門（一眼一句 §2.1）：技術分析 → 操作摘要 → 關鍵價位參考，頁尾揭露區為 </main> 前最後一個節點", () => {
    const pageSource = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/page.tsx", import.meta.url)),
      "utf8",
    );
    const technical = pageSource.indexOf(`{TECHNICAL_ANALYSIS_TITLE}</h2>`);
    const summary = pageSource.indexOf("<OperationSummaryPanel advice={advice} />");
    const keyLevels = pageSource.indexOf("<KeyLevelsPanel");
    const footer = pageSource.indexOf("<PageFooterDisclosures groups={footerGroups} />");
    const mainClose = pageSource.lastIndexOf("</main>");
    expect(technical).toBeGreaterThan(-1);
    expect(summary).toBeGreaterThan(technical);
    expect(keyLevels).toBeGreaterThan(summary);
    expect(footer).toBeGreaterThan(keyLevels);
    expect(mainClose).toBeGreaterThan(footer);
    // 一眼一句 §2.1：移除操作摘要下方那句 buildFooterGuidanceForDataSource(...)（改放進操作摘要的「詳細」最後一行）。
    expect(pageSource).not.toContain("buildFooterGuidanceForDataSource");
    expect(
      readFileSync(fileURLToPath(new URL("../../position/[symbol]/OperationSummaryPanel.tsx", import.meta.url)), "utf8"),
    ).toContain("{buildFooterGuidanceForDataSource(PAGE_LEVEL_DISCLOSURE_SECTION_TITLE)}");
    // 頁尾之後不得再有任何區塊：只剩空白與 </main>。
    expect(pageSource.slice(footer + "<PageFooterDisclosures groups={footerGroups} />".length, mainClose).trim()).toBe("");
  });

  it("FR-3 C4：NON_REALTIME_NOTICE 在頁面元件中只由頁級揭露區渲染（操作摘要與關鍵價位面板不再重複）", () => {
    for (const rel of ["../../position/[symbol]/OperationSummaryPanel.tsx", "../../position/[symbol]/KeyLevelsPanel.tsx"]) {
      const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
      expect(src).not.toMatch(/\{(model|required)\.nonRealtimeNotice\}|\{NON_REALTIME_NOTICE\}/);
    }
  });
});

/**
 * 圖形化 1–3（CEO 2026-09-06）：位階量表／價位階梯／指標速覽／規則方向的新字面
 * 逐字釘住＋禁用詞掃描＋裸「即時」掃描；並守門「圖不取代字」——每個圖形都伴隨
 * 一句說明其不代表方向或買賣判斷的限定語，且色彩不得用紅綠語意（風控 S1 沿用）。
 */
describe("圖形化 1–3 新字面與守門", () => {
  const CONSTANTS: Record<string, string> = {
    KEY_LEVELS_GAUGE_LOW_END_LABEL,
    KEY_LEVELS_GAUGE_HIGH_END_LABEL,
    KEY_LEVELS_GAUGE_MARKER_LABEL,
    buildGaugeAriaLabel: buildGaugeAriaLabel(252, 41.4, "區間中段"),
    KEY_LEVELS_LADDER_TITLE,
    KEY_LEVELS_LADDER_INTRO,
    KEY_LEVELS_LADDER_HEADLINE_TAG,
    KEY_LEVELS_LADDER_DISTANCE_HEADER,
    KEY_LEVELS_LADDER_NOTE,
    KEY_LEVELS_LADDER_RUNG_ANCHOR_COST,
    KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE,
    KEY_LEVELS_LADDER_RUNG_CLOSE,
    INDICATOR_OVERVIEW_TITLE,
    INDICATOR_OVERVIEW_LEGEND,
    INDICATOR_OVERVIEW_EMPTY,
    ...Object.fromEntries(Object.entries(RSI_BAND_LABELS).map(([k, v]) => [`RSI_${k}`, v])),
    ...Object.fromEntries(Object.entries(KD_BAND_LABELS).map(([k, v]) => [`KD_${k}`, v])),
    ...Object.fromEntries(Object.entries(PERCENT_B_BAND_LABELS).map(([k, v]) => [`PB_${k}`, v])),
    ...Object.fromEntries(Object.entries(VOLUME_Z_BAND_LABELS).map(([k, v]) => [`VZ_${k}`, v])),
    DIRECTION_BAR_ARIA_LABEL,
    DIRECTION_SHARE_QUALIFIER,
  };

  it("每一句：不含 §1.3 禁用詞、無裸即時宣稱", () => {
    for (const [name, text] of Object.entries(CONSTANTS)) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, name);
      expect(findBareRealtimeClaims(text)).toEqual([]);
    }
  });

  it("位階量表字面逐字比對", () => {
    expect(KEY_LEVELS_GAUGE_LOW_END_LABEL).toBe("區間最低");
    expect(KEY_LEVELS_GAUGE_HIGH_END_LABEL).toBe("區間最高");
    // 風控 S-b：「收盤位於 41%」，不得是「收盤 41%」（會被讀成漲跌幅）。
    expect(KEY_LEVELS_GAUGE_MARKER_LABEL).toBe("收盤位於");
    expect(buildGaugeAriaLabel(252, 41.4, "區間中段")).toBe("近 252 根日線位階量表：收盤位於區間的 41%，區間中段");
  });

  it("價位階梯字面逐字比對（含「不代表價格會…到達」限定語）", () => {
    expect(KEY_LEVELS_LADDER_TITLE).toBe("價位階梯");
    expect(KEY_LEVELS_LADDER_INTRO).toBe(
      "本面板各參考價位由高至低排列；橫條為各價位相對基準價的百分比距離，右為高於基準價，左為低於基準價。",
    );
    expect(KEY_LEVELS_LADDER_HEADLINE_TAG).toBe("大字所示");
    expect(KEY_LEVELS_LADDER_DISTANCE_HEADER).toBe("相對基準價");
    expect(KEY_LEVELS_LADDER_NOTE).toBe("排序與距離皆為算式結果，不代表價格會依此順序或幅度到達任一價位。");
    expect(KEY_LEVELS_LADDER_RUNG_ANCHOR_COST).toBe("基準價（持倉平均成本）");
    expect(KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE).toBe("基準價（最新收盤，試算）");
    expect(KEY_LEVELS_LADDER_RUNG_CLOSE).toBe("最新收盤");
  });

  it("指標速覽字面逐字比對（區帶標籤帶門檻；圖例句含「不代表多空方向」與「不是任何買賣判斷」）", () => {
    expect(INDICATOR_OVERVIEW_TITLE).toBe("指標速覽");
    expect(INDICATOR_OVERVIEW_LEGEND).toBe(
      "色帶只標示各指標最新值落在自身量尺的哪個區帶（低／中／高），不代表多空方向，也不是任何買賣判斷。",
    );
    expect(INDICATOR_OVERVIEW_EMPTY).toBe("目前沒有可分區帶的指標數值。");
    expect(RSI_BAND_LABELS).toEqual({ low: "RSI 低區帶（≤30）", mid: "RSI 中區帶（30–70）", high: "RSI 高區帶（≥70）" });
    expect(KD_BAND_LABELS).toEqual({ low: "K 值低區帶（≤20）", mid: "K 值中區帶（20–80）", high: "K 值高區帶（≥80）" });
    expect(PERCENT_B_BAND_LABELS).toEqual({ low: "%B 低於下軌（<0）", mid: "%B 通道內（0–1）", high: "%B 高於上軌（>1）" });
    expect(VOLUME_Z_BAND_LABELS).toEqual({
      low: "成交量明顯偏低（z≤−2）",
      mid: "成交量接近近期平均（|z|<2）",
      high: "成交量明顯偏高（z≥2）",
    });
    expect(DIRECTION_BAR_ARIA_LABEL).toBe("命中規則方向權重占比");
    // R5：堆疊條限定語（creative-lead 候選 A，風控逐字審）——含「比例」與三個否定對象。
    expect(DIRECTION_SHARE_QUALIFIER).toBe(
      "占比為各方向命中規則權重佔全部命中規則權重總和的比例，不代表機率、達成率或建議強度。",
    );
    expect(DIRECTION_SHARE_QUALIFIER).toContain("不代表機率、達成率或建議強度");
    expect([...DIRECTION_SHARE_QUALIFIER].length).toBeLessThanOrEqual(45);
  });

  it("R3/R4：不得存在「收盤 vs MA」chip（二元關係非區帶；且會跨兩支 API 的時間戳）", () => {
    for (const rel of [
      "../../position/[symbol]/TechnicalIndicatorsPanel.tsx",
      "../../position/[symbol]/page.tsx",
      "../indicatorBands.ts",
    ]) {
      const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
      expect(src, `${rel} 不得復活收盤 vs MA 比較`).not.toMatch(/closeVsMa|MaRelation|latestClose|buildMaRelationLabel/);
    }
  });

  it("R8(a)：區帶 chip 只在「指標速覽」渲染，不散落到各指標卡", () => {
    const tech = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/TechnicalIndicatorsPanel.tsx", import.meta.url)),
      "utf8",
    );
    // 唯一的 <BandChip 呼叫點在 IndicatorOverview 內；IndicatorCard 不再接受 chip prop。
    expect(tech.match(/<BandChip /g)?.length).toBe(1);
    expect(tech.indexOf("<BandChip ")).toBeGreaterThan(tech.indexOf("function IndicatorOverview"));
    expect(tech).not.toMatch(/chip\?:|chip=\{/);
  });

  it("R5：方向堆疊條的限定語與條同區、≥ text-sm / ≥ neutral-400、不在 <details> 內", () => {
    const advice = readFileSync(fileURLToPath(new URL("../../position/[symbol]/AdviceCardView.tsx", import.meta.url)), "utf8");
    const bar = advice.slice(advice.indexOf("function DirectionWeightBar"), advice.indexOf("export function hasOpposingDirections"));
    // CEO 第二次裁定 2026-09-06：限定語下沉頁尾（buildAdviceFooterItems，與條同閘門）；條的同區改為指引句。
    expect(bar).toMatch(/className="mt-2 text-sm text-neutral-300">\{buildFooterGuidance\(ADVICE_CARD_TITLE\)\}/);
    expect(bar).toContain("hasDirectionShareBar(advice)");
    expect(bar).not.toContain("<details");
  });

  it("R1：圖形化元件與方向標籤不得使用方向性符號（▲▼△▽↑↓）", () => {
    for (const rel of [
      "../../position/[symbol]/RangeGauge.tsx",
      "../../position/[symbol]/PriceLadder.tsx",
      "../../position/[symbol]/TechnicalIndicatorsPanel.tsx",
      "../../position/[symbol]/AdviceCardView.tsx",
    ]) {
      const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
      expect(src, `${rel} 不得含方向性符號`).not.toMatch(/[▲▼△▽↑↓↗↘⇧⇩🔺🔻]/);
    }
  });

  it("圖不取代字：三個圖形元件各自渲染其限定語；圖例句與階梯註記 ≥ text-sm / ≥ neutral-400", () => {
    const gauge = readFileSync(fileURLToPath(new URL("../../position/[symbol]/RangeGauge.tsx", import.meta.url)), "utf8");
    const ladder = readFileSync(fileURLToPath(new URL("../../position/[symbol]/PriceLadder.tsx", import.meta.url)), "utf8");
    const panel = readFileSync(fileURLToPath(new URL("../../position/[symbol]/KeyLevelsPanel.tsx", import.meta.url)), "utf8");
    const tech = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/TechnicalIndicatorsPanel.tsx", import.meta.url)),
      "utf8",
    );
    // 位階≠估值句、階梯註記、速覽圖例：CEO 第二次裁定 2026-09-06 下沉頁尾，由 builder 產出
    // （見「揭露下沉頁尾 守門」L6-1'），原位不再渲染，改留指引句。
    expect(panel).toContain("<RangeGauge");
    expect(panel).toContain("<PriceLadder");
    expect(ladder).not.toContain("{KEY_LEVELS_LADDER_NOTE}");
    expect(tech).not.toContain("{INDICATOR_OVERVIEW_LEGEND}");
    expect(tech).toContain("{buildFooterGuidance(TECHNICAL_ANALYSIS_TITLE)}");
    // 每一個數字都有文字形式（量表兩端與標記皆印出數值）。
    expect(gauge).toContain("{lowText}");
    expect(gauge).toContain("{highText}");
    expect(gauge).toContain("{rangePositionPct.toFixed(0)}%");
  });

  it("風控 S1 沿用：圖形化元件與速覽／方向標籤不得使用紅綠語意色", () => {
    for (const rel of [
      "../../position/[symbol]/RangeGauge.tsx",
      "../../position/[symbol]/PriceLadder.tsx",
      "../../position/[symbol]/TechnicalIndicatorsPanel.tsx",
    ]) {
      const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
      expect(src, `${rel} 不得帶 red/green/rose/emerald 色票`).not.toMatch(/\b(bg|text|border)-(red|green|rose|emerald)-\d/);
    }
    // AdviceCardView 既有的 rose 警示區（風險上限擋下）不在此限；守門新加的方向 chip 與堆疊條色票
    //（風控落地條件 3：DIRECTION_BAR_CLASS 一併納入），且 S-d：方向色票全中性。
    const advice = readFileSync(fileURLToPath(new URL("../../position/[symbol]/AdviceCardView.tsx", import.meta.url)), "utf8");
    const colourBlock = advice.slice(advice.indexOf("const DIRECTION_CHIP_CLASS"), advice.indexOf("function DirectionChip"));
    expect(colourBlock).toContain("DIRECTION_BAR_CLASS");
    expect(colourBlock).not.toMatch(/(red|green|rose|emerald|sky|amber)-\d/);
    // R2：指標區帶 chip 不得借用 amber 警示色；量表／階梯不得用 sky 以外或紅綠色相（S-c：階梯距離條為中性灰）。
    const tech = readFileSync(fileURLToPath(new URL("../../position/[symbol]/TechnicalIndicatorsPanel.tsx", import.meta.url)), "utf8");
    const chipBlock = tech.slice(tech.indexOf("const BAND_CHIP_CLASS"), tech.indexOf("function BandChip"));
    expect(chipBlock).not.toMatch(/amber-\d/);
    const ladder = readFileSync(fileURLToPath(new URL("../../position/[symbol]/PriceLadder.tsx", import.meta.url)), "utf8");
    expect(ladder).not.toMatch(/\b(bg|text|border)-(sky|amber)-\d/);
    // 量表：單一色相（sky），不得借用 amber 警示色。
    const gauge = readFileSync(fileURLToPath(new URL("../../position/[symbol]/RangeGauge.tsx", import.meta.url)), "utf8");
    expect(gauge).not.toMatch(/amber-\d/);
  });
});

/**
 * 揭露下沉頁尾（CEO 裁定 2026-09-06；風控 ACCEPT_WITH_CONDITIONS，L1–L6）。
 * `work/stock-desk-揭露下沉頁尾-CEO裁定與方案.md`。
 */
describe("揭露下沉頁尾 守門", () => {
  const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
  const footerSrc = read("../../components/PageFooterDisclosures.tsx");
  const pageSrc = read("../../position/[symbol]/page.tsx");

  it("新字面：不含禁用詞、無裸即時；逐字釘住（creative-lead 起草、風控逐字審）", () => {
    const constants: Record<string, string> = {
      PAGE_FOOTER_DISCLOSURES_TITLE,
      PAGE_FOOTER_DISCLOSURES_INTRO,
      guidance: buildFooterGuidance("關鍵價位參考"),
      guidanceDataSource: buildFooterGuidanceForDataSource(PAGE_LEVEL_DISCLOSURE_SECTION_TITLE),
      OPERATION_SUMMARY_TITLE,
      TECHNICAL_ANALYSIS_TITLE,
      ADVICE_CARD_TITLE,
      LEVERAGE_CHAPTER_TITLE,
    };
    for (const [name, text] of Object.entries(constants)) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, name);
      expect(findBareRealtimeClaims(text)).toEqual([]);
    }
    expect(PAGE_FOOTER_DISCLOSURES_TITLE).toBe("本頁揭露與計算依據");
    expect(PAGE_FOOTER_DISCLOSURES_INTRO).toBe("以下為本頁各區塊的資料來源、揭露事項與計算方式說明，依區塊分組列示。");
    // 風控第二輪 R1：模板須涵蓋「揭露事項」一類（與導語三類用詞對齊）。
    expect(buildFooterGuidance("關鍵價位參考")).toBe("頁尾「關鍵價位參考」涵蓋本區資料來源、揭露事項與計算方式說明。");
    // 風控第二輪 R2：頁級變體不自稱「本區」、不承諾計算方式。
    expect(buildFooterGuidanceForDataSource(PAGE_LEVEL_DISCLOSURE_SECTION_TITLE)).toBe(
      "頁尾「本頁資料與計算揭露」說明資料來源與更新頻率。",
    );
    expect(buildFooterGuidanceForDataSource("X")).not.toMatch(/本區|計算方式/);
    // L5：指引句不得用弱化為選讀的措辭。
    for (const text of [buildFooterGuidance("X"), buildFooterGuidanceForDataSource("X")]) {
      expect(text).not.toMatch(/詳見|更多說明|僅供參考/);
    }
    expect(OPERATION_SUMMARY_TITLE).toBe("操作摘要");
    expect(TECHNICAL_ANALYSIS_TITLE).toBe("技術分析");
    expect(ADVICE_CARD_TITLE).toBe("建議卡");
    expect(LEVERAGE_CHAPTER_TITLE).toBe("槓桿型 ETF 專章");
  });

  it("INTRO 退場（風控第二輪 APPROVE）：PAGE_LEVEL_DISCLOSURE_SECTION_INTRO 不得再被任何元件渲染", () => {
    const glob = [
      "../../position/[symbol]/page.tsx",
      "../../position/[symbol]/OperationSummaryPanel.tsx",
      "../../position/[symbol]/KeyLevelsPanel.tsx",
      "../../position/[symbol]/LeverageChapterView.tsx",
      "../../position/[symbol]/AdviceCardView.tsx",
      "../../position/[symbol]/TechnicalIndicatorsPanel.tsx",
      "../../components/PageFooterDisclosures.tsx",
    ];
    for (const rel of glob) {
      expect(read(rel), `${rel} 不得渲染 INTRO（尾句在新架構為假陳述）`).not.toContain("PAGE_LEVEL_DISCLOSURE_SECTION_INTRO");
    }
  });

  it("L1：頁尾字級 text-xs、字色不得低於 neutral-400（neutral-500 未達 WCAG AA）", () => {
    expect(footerSrc).not.toMatch(/text-neutral-(5|6|7)00/);
    expect(footerSrc).toMatch(/text-xs text-neutral-400/);
  });

  it("L0（風控 F-7，2026-09-19）：app/layout.tsx 全站免責句自頁尾收成 details 起為全頁唯一常駐免責——不得移除、摺疊、下調字級或對比、不得移出頁面最後節點", () => {
    const layoutSrc = read("../../layout.tsx");
    const sentence = "本工具為研究與教育用途，非投資建議";
    const idx = layoutSrc.indexOf(sentence);
    expect(idx).toBeGreaterThan(-1);
    expect(layoutSrc).not.toMatch(/<details|<summary|line-clamp|truncate|sr-only|\bhidden\b/);
    // 所在 <footer> 的 class 不得低於 text-sm／neutral-400。
    const footerTag = layoutSrc.slice(layoutSrc.lastIndexOf("<footer", idx), idx);
    expect(footerTag).toMatch(/text-sm/);
    expect(footerTag).toMatch(/text-neutral-400/);
    expect(footerTag).not.toMatch(/text-xs|text-neutral-(5|6|7)00/);
    // 頁面最後節點：<footer> 之後直到 </Providers> 只剩 </footer>。
    const afterSentence = layoutSrc.slice(idx + sentence.length, layoutSrc.indexOf("</Providers>"));
    expect(afterSentence.replace(/\s/g, "")).toBe("</footer>");
  });

  it("F-3（風控 2026-09-19 放行條件）：頁尾 <details> 掛 print-expand，globals.css 於 @media print 強制展開", () => {
    expect(footerSrc).toMatch(/<details className="[^"]*\bprint-expand\b[^"]*"/);
    const css = read("../../globals.css");
    const printBlock = css.slice(css.indexOf("@media print"));
    expect(printBlock).toMatch(/details\.print-expand:not\(\[open\]\) > :not\(summary\)\s*\{\s*display: block;/);
    expect(printBlock).toMatch(/details\.print-expand::details-content\s*\{[^}]*content-visibility: visible;/);
  });

  it("L2'（CEO 第三次裁定 2026-09-19「頁尾那段也收成詳細」，派工單 §5）：頁尾區收成單一 <details>，summary 為既有標題常數；仍不得截斷、延後掛載", () => {
    // 摺疊本身獲 CEO 書面裁定放行（推翻 2026-09-06「常駐不摺疊」與風控 L2 摺疊條款；風控否決紀錄見派工單 §5.2），
    // 但只允許「一層 <details>、summary 即標題」；展開後內容仍須完整——截斷／延後掛載／黏附等構造照舊禁止。
    // `[&::-webkit-details-marker]:hidden` 與 chevron 的 `aria-hidden="true"` 只藏原生三角／裝飾（各區塊 <details> 共用的同一 idiom），
    // 不藏內容，先剔除再掃 `hidden`。qa 2026-09-19（low）：剔除要有界限——`aria-hidden` 只准出現在 <summary> 的 chevron 上、恰一次，
    // 否則有人把揭露文字對 AT 隱藏也會被一併吃掉而逃過守門。
    const summaryOnly = footerSrc.match(/<summary className=[\s\S]*?<\/summary>/)?.[0] ?? "";
    expect((footerSrc.match(/aria-hidden/g) ?? []).length).toBe(1);
    expect((summaryOnly.match(/aria-hidden="true"/g) ?? []).length).toBe(1);
    const scanned = footerSrc.replaceAll("[&::-webkit-details-marker]:hidden", "").replace('aria-hidden="true"', "");
    expect(scanned).not.toMatch(/line-clamp|truncate|max-h-|overflow-y-(auto|scroll)|\bhidden\b|sr-only|aria-expanded|IntersectionObserver|React\.lazy|Suspense|sticky/);
    // 只數 JSX 標籤（註解裡的 `<details>` 反引號提及不算）。
    expect((footerSrc.match(/<details className=/g) ?? []).length).toBe(1);
    expect(footerSrc).toMatch(/<summary className=[^>]*>[\s\S]*?\{PAGE_FOOTER_DISCLOSURES_TITLE\}<\/h2>[\s\S]*?<\/summary>/);
    // summary 不得另造入口字：<summary> 內唯一文字節點是標題常數（chevron 為 aria-hidden 裝飾）。
    const summaryBlock = footerSrc.match(/<summary className=[\s\S]*?<\/summary>/)?.[0] ?? "";
    expect(summaryBlock.replace(/<[^>]+>|\s|▸/g, "")).toBe("{PAGE_FOOTER_DISCLOSURES_TITLE}");
    // 導語、分組、清單全部在 <details> 內（摺疊即整區摺疊，不留半截常駐）。
    const detailsOpen = footerSrc.indexOf("<details className=");
    const detailsClose = footerSrc.indexOf("</details>");
    for (const needle of ["{PAGE_FOOTER_DISCLOSURES_INTRO}", "visible.map((group) =>", "<ul"]) {
      const idx = footerSrc.indexOf(needle);
      expect(idx, `${needle} 應在 <details> 內`).toBeGreaterThan(detailsOpen);
      expect(idx).toBeLessThan(detailsClose);
    }
    // DOM：預設收合（無 open 屬性），展開內容仍逐字渲染。
    const html = renderToStaticMarkup(
      createElement(PageFooterDisclosures, {
        groups: [{ title: "技術分析", items: ["句一。", { formula: ["a = b"], qualifier: "限定語。" }] }],
      }),
    );
    expect(html).toContain("<details");
    expect(html).not.toMatch(/<details[^>]*\sopen/);
    expect(html).toContain(`<summary`);
    expect(html).toContain(PAGE_FOOTER_DISCLOSURES_TITLE);
    expect(html).toContain(PAGE_FOOTER_DISCLOSURES_INTRO);
    for (const text of ["句一。", "a = b", "限定語。"]) expect(html).toContain(text);
  });

  it("L3／L4：分組順序寫死為頁面順序，組名以既有標題常數 import 取得", () => {
    // 一眼一句 §2.1: 技術分析 → 操作摘要 → 關鍵價位參考（→ 六項觀察條件 → 建議卡，見 T9）→ 槓桿專章。
    const order = [
      "PAGE_LEVEL_DISCLOSURE_SECTION_TITLE",
      "TECHNICAL_ANALYSIS_TITLE",
      "OPERATION_SUMMARY_TITLE",
      "KEY_LEVELS_PANEL_TITLE",
      "ADVICE_CARD_TITLE",
      "LEVERAGE_CHAPTER_TITLE",
    ];
    const positions = order.map((name) => pageSrc.indexOf(`title: ${name}`));
    expect(positions.every((p) => p > -1)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
    // 組名不得在 page.tsx 內以字串複製。
    for (const title of ["操作摘要", "關鍵價位參考", "技術分析", "建議卡", "槓桿型 ETF 專章", "本頁資料與計算揭露"]) {
      expect(pageSrc.match(new RegExp(`title: "${title}"`))).toBeNull();
    }
    // 六組 `items:` 各自接到對應 builder（風控第二次裁定後 required：下沉不得等同刪除）。
    for (const [title, needle] of [
      ["PAGE_LEVEL_DISCLOSURE_SECTION_TITLE", "items: [NON_REALTIME_NOTICE]"],
      ["OPERATION_SUMMARY_TITLE", "buildSummaryFooterItems(advice.data)"],
      ["KEY_LEVELS_PANEL_TITLE", "buildKeyLevelsFooterItems(bars.data.bars, keyLevelsAnchor.avgCost, keyLevelsAnchor.anchorSource)"],
      ["TECHNICAL_ANALYSIS_TITLE", "buildTechnicalFooterItems(signals.data.signals)"],
      ["ADVICE_CARD_TITLE", "buildAdviceFooterItems(advice.data.advice)"],
      ["LEVERAGE_CHAPTER_TITLE", "[leverage.data.chapter.disclosure]"],
    ] as const) {
      const from = pageSrc.indexOf(`title: ${title}`);
      const block = pageSrc.slice(from, pageSrc.indexOf("},", from));
      expect(block, `${title} 組應接到 ${needle}`).toContain(needle);
    }
    // 各區塊標題同樣改用常數，避免 h2 與頁尾組名漂移。
    expect(read("../../position/[symbol]/OperationSummaryPanel.tsx")).toContain("{OPERATION_SUMMARY_TITLE}</h2>");
    expect(read("../../position/[symbol]/LeverageChapterView.tsx")).toContain("{LEVERAGE_CHAPTER_TITLE}</h2>");
    expect(pageSrc).toContain("{TECHNICAL_ANALYSIS_TITLE}</h2>");
    expect(pageSrc).toContain("{ADVICE_CARD_TITLE}</h2>");
  });

  it("L5：每個有句子下沉的區塊都渲染帶組名的指引句，字級不低於導讀（text-sm / neutral-300）", () => {
    const wiring: [string, string][] = [
      // 一眼一句 §2.1: buildFooterGuidanceForDataSource(...) moved from page.tsx into
      // OperationSummaryPanel's own `<details>` (its last line, held／candidate branches).
      ["../../position/[symbol]/OperationSummaryPanel.tsx", "{buildFooterGuidanceForDataSource(PAGE_LEVEL_DISCLOSURE_SECTION_TITLE)}"],
      ["../../position/[symbol]/OperationSummaryPanel.tsx", "{buildFooterGuidance(OPERATION_SUMMARY_TITLE)}"],
      ["../../position/[symbol]/KeyLevelsPanel.tsx", "{buildFooterGuidance(KEY_LEVELS_PANEL_TITLE)}"],
      ["../../position/[symbol]/LeverageChapterView.tsx", "{buildFooterGuidance(LEVERAGE_CHAPTER_TITLE)}"],
      ["../../position/[symbol]/TechnicalIndicatorsPanel.tsx", "{buildFooterGuidance(TECHNICAL_ANALYSIS_TITLE)}"],
      ["../../position/[symbol]/AdviceCardView.tsx", "{buildFooterGuidance(ADVICE_CARD_TITLE)}"],
      // R3（決策卡第二輪修正，風控複審 APPROVE_WITH_CONDITIONS）：本卡不設
      // `<details>`，指引句常駐卡片底部，指向頁尾揭露區本身（非某一組）。
      ["../../position/[symbol]/DecisionCard.tsx", "{buildFooterGuidance(PAGE_FOOTER_DISCLOSURES_TITLE)}"],
    ];
    for (const [rel, needle] of wiring) {
      const src = read(rel);
      const idx = src.indexOf(needle);
      expect(idx, `${rel} 應渲染 ${needle}`).toBeGreaterThan(-1);
      expect(src.slice(Math.max(0, idx - 80), idx)).toMatch(/text-sm text-neutral-300/);
    }
  });

  it("L6-1'（CEO 第二次裁定 2026-09-06 推翻風控 A+1～A+10）：十句一律下沉，原區塊不再渲染，由 builder 逐句產出", () => {
    const summary = read("../../position/[symbol]/OperationSummaryPanel.tsx");
    for (const needle of ["{required.asOfStatement}", "{model.notComparableNote}"]) {
      expect(summary, `${needle} 應已下沉`).not.toContain(needle);
    }
    // 一眼一句 §2.3 R2（推翻本節先前的下沉裁定）：candidateEvidenceNotice 回到結論旁，
    // 常駐於面板主視圖，`buildSummaryFooterItems` 不再重複輸出（見下方 builder 斷言）。
    expect(summary, "{model.required.candidateEvidenceNotice} 應已回到主視圖").toContain(
      "{model.required.candidateEvidenceNotice}",
    );
    expect(read("../../position/[symbol]/AdviceCardView.tsx")).not.toContain("{DIRECTION_SHARE_QUALIFIER}");
    const panel = read("../../position/[symbol]/KeyLevelsPanel.tsx");
    for (const needle of [
      "{KEY_LEVELS_PANEL_DISCLAIMER}",
      "{KEY_LEVELS_TARGET_STANDING_NOTICE}",
      "{buildRangeNotValuationNote(levels.rangeBarCount)}",
      "{KEY_LEVELS_HEADER_DASH_NOTICE}",
    ]) {
      expect(panel, `${needle} 應已下沉`).not.toContain(needle);
    }
    // 附條件保留（XREF／qualifier 指涉，不在第二次裁定範圍）：
    for (const needle of [
      "{KEY_LEVELS_HEADER_UNADJUSTED_NOTICE}",
      "{KEY_LEVELS_PULLBACK_EXPLAIN_NOTE}",
      "{KEY_LEVELS_TARGET_ROW_TRAILING_NOTE}",
    ]) {
      expect(panel).toContain(needle);
    }
    expect(read("../../position/[symbol]/TechnicalIndicatorsPanel.tsx")).not.toContain("{INDICATOR_OVERVIEW_LEGEND}");
    expect(read("../../position/[symbol]/PriceLadder.tsx")).not.toContain("{KEY_LEVELS_LADDER_NOTE}");
    // 槓桿專章：nature 與 notes 不在下沉範圍。
    const leverage = read("../../position/[symbol]/LeverageChapterView.tsx");
    expect(leverage).toContain("chapter.erosion?.nature");
    expect(leverage).toContain("chapter.notes.map");

    // builder 逐句：建議卡與技術分析組。
    const adviceWithBar = { direction_weights: [{ direction: "defensive", weight: 0.6, actions: ["reduce"] }] } as unknown as AdviceCard;
    const adviceNoBar = { direction_weights: [] } as unknown as AdviceCard;
    expect(buildAdviceFooterItems(adviceWithBar)).toEqual([DIRECTION_SHARE_QUALIFIER]);
    expect(buildAdviceFooterItems(adviceNoBar)).toEqual([]);
    expect(buildTechnicalFooterItems({ technical: {} } as unknown as SignalsPayload)).toEqual([INDICATOR_OVERVIEW_LEGEND]);
    expect(buildTechnicalFooterItems({} as unknown as SignalsPayload)).toEqual([]);
  });

  it("L6-2／L6-7：下沉句由 builder 產出且原區塊不再渲染（全頁恰好一次）", () => {
    const panel = read("../../position/[symbol]/KeyLevelsPanel.tsx");
    const summary = read("../../position/[symbol]/OperationSummaryPanel.tsx");
    const leverage = read("../../position/[symbol]/LeverageChapterView.tsx");
    // 原區塊 JSX 不再渲染這些句子（builder 內以常數名出現屬允許，故只查 JSX 插值形式）。
    for (const needle of [
      "{KEY_LEVELS_HEADER_STALENESS_SELF_NOTICE}",
      "{KEY_LEVELS_STOP_S5_NEUTRAL_NOTE}",
      "{KEY_LEVELS_BASIS_SECTION_TITLE}",
      "{KEY_LEVELS_BASIS_UNADJUSTED_XREF}",
      "{buildFooterSample(",
    ]) {
      expect(panel, `${needle} 應已下沉`).not.toContain(needle);
    }
    expect(summary).not.toContain("{model.coverageStatement}");
    expect(summary).not.toContain("{required.rulesStatement}");
    expect(leverage).not.toContain("{chapter.disclosure}");
    expect(pageSrc).toContain("[leverage.data.chapter.disclosure]");

    // builder 產出：計算依據一條不減、順序不變、標題為組內小標、樣本句殿後。
    // 決策卡 required 條件 3（`work/stock-desk-一眼一句簡化-派工單.md` §5.4）：
    // `KEY_LEVELS_BASIS_TARGET` 之後新增 `KEY_LEVELS_BASIS_CLOSE_DISTANCE`，原
    // 十條變十一條，其餘順序不變。
    const bar = (i: number): Bar => ({
      date: `2026-0${1 + Math.floor(i / 28)}-${String(1 + (i % 28)).padStart(2, "0")}`,
      open: "100", high: "105", low: "95", close: String(100 + (i % 7)), volume: 1000, currency: "TWD", source: "demo",
    });
    const bars = Array.from({ length: 80 }, (_, i) => bar(i));
    const items = buildKeyLevelsFooterItems(bars, null, "close-not-held");
    expect(items.slice(0, 8)).toEqual([
      KEY_LEVELS_PANEL_DISCLAIMER,
      KEY_LEVELS_HEADER_STALENESS_SELF_NOTICE,
      KEY_LEVELS_HEADER_DASH_NOTICE,
      buildRangeNotValuationNote(80),
      KEY_LEVELS_STOP_S5_NEUTRAL_NOTE,
      KEY_LEVELS_TARGET_STANDING_NOTICE,
      KEY_LEVELS_LADDER_NOTE,
      { heading: KEY_LEVELS_BASIS_SECTION_TITLE },
    ]);
    expect(items[8]).toBe(KEY_LEVELS_BASIS_UNADJUSTED_XREF);
    const basis = items.slice(9, 20);
    expect(basis).toHaveLength(11);
    expect(basis.map((b) => (typeof b === "string" || !("formula" in b) ? "?" : b.formula[0]?.slice(0, 4)))).toEqual([
      "收盤（本", "位階(近", "分類：位", "MA20", "近60日", "ATR(", "停損參考", "停利參考", "距最新收", "基準價：", "拉回觀察",
    ]);
    expect(items[20]).toBe(buildFooterSample(80, bars[79]!.date));
    // 位階不可計算時（< 60 根）不含位階≠估值句，其餘順序不變。
    const short = buildKeyLevelsFooterItems(bars.slice(0, 40), null, "close-not-held");
    expect(short.slice(0, 4)).toEqual([
      KEY_LEVELS_PANEL_DISCLAIMER,
      KEY_LEVELS_HEADER_STALENESS_SELF_NOTICE,
      KEY_LEVELS_HEADER_DASH_NOTICE,
      KEY_LEVELS_STOP_S5_NEUTRAL_NOTE,
    ]);
    expect(buildKeyLevelsFooterItems([], null, "close-not-held")).toEqual([]);

    // 操作摘要 builder：候選＝覆蓋度句（完整數字）＋規則版本句；no_price／no_action＝[]。
    const noPrice = { status: "insufficient_data", reason: "x", advice: null, held: false, position_ids: [], context_notes: [], data: { status: "fresh" }, as_of: null } as unknown as AdviceResponse;
    expect(buildSummaryFooterItems(noPrice)).toEqual([]);
  });

  it("P2 落地條件隨句移動：頁尾算式行與限定語同 <li>、同字級同顏色，font-mono 只在算式行", () => {
    expect(footerSrc).toMatch(/className="block whitespace-pre-wrap font-mono text-xs text-neutral-400"/);
    expect(footerSrc).toMatch(/item\.qualifier !== null && <span className="block text-xs text-neutral-400">/);
    expect((footerSrc.match(/className="[^"]*font-mono/g) ?? []).length).toBe(1);
  });
});

/**
 * CEO 第二次裁定（2026-09-19 深夜，`work/stock-desk-一眼一句簡化-派工單.md` §4，
 * dev-lead 派工「純搬移」）：主視圖不放任何免責、教育用途、解碼／限定句、指引
 * 句——這批只搬移出現層級，字面一字不改。以下用原始碼位置比對取代「常駐不得
 * 摺疊」的舊斷言：每個被搬移的字面，其在檔案中第一次出現的位置都必須晚於
 * （深於）該區塊 `<details>` 的開啟位置，證明它只存在於 details 裡；沒有任何
 * 字面被刪除，只有出現層級改變。
 */
describe("CEO 第二次裁定 wave2（2026-09-19 深夜）：主視圖收斂進 <details>", () => {
  const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
  const summarySrc = read("../../position/[symbol]/OperationSummaryPanel.tsx");
  const keyLevelsSrc = read("../../position/[symbol]/KeyLevelsPanel.tsx");
  const entrySrc = read("../../position/[symbol]/EntryObservationPanel.tsx");
  const pageSrc = read("../../position/[symbol]/page.tsx");

  it("操作摘要 candidate 分支（wave3，派工單 §4.3 第 2 點）：disclaimer／confidenceMeaning／反面論點／資料時間前綴／CANDIDATE_EVIDENCE_NOTICE 只出現在 <details> 之後；主視圖改留 NOT_HELD_BADGE，且徽章與原句用 showBadge 三元運算式互斥", () => {
    const start = summarySrc.indexOf('if (model.kind === "candidate")');
    const end = summarySrc.indexOf('// model.kind === "held"');
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const region = summarySrc.slice(start, end);
    // 用實際 JSX 標籤（含 className）比對，避免比對到上方 doc comment 裡提到的
    // 「`<details>`」純文字 reference（同一子字串，但不是真正的標籤）。
    const detailsIdx = region.indexOf('<details className="group mt-1">');
    expect(detailsIdx).toBeGreaterThan(-1);
    for (const needle of [
      "<InlineDisclaimer text={model.required.disclaimer} />",
      "{model.required.confidenceMeaning}",
      "反面論點",
      "<DataMetaPrefixLine response={response} />",
    ]) {
      const idx = region.indexOf(needle);
      expect(idx, `${needle} 應出現、且只出現在 <details> 內`).toBeGreaterThan(detailsIdx);
    }
    // wave3：CANDIDATE_EVIDENCE_NOTICE 這句字面在檔案中出現兩處——一處是
    // `showBadge ? 徽章 : 原句` 三元運算式的 else 分支（防呆用，主視圖區塊內，
    // 但 `showBadge` 恆為 true 所以永遠不會實際渲染到），另一處才是真正常駐
    // 渲染的 `<details>` 版本。用「出現次數」而非「第一次出現位置」驗證，
    // 避免誤把防呆用的 else 分支誤判為「這句仍在主視圖顯示」。
    const evidenceOccurrences = region.split("{model.required.candidateEvidenceNotice}").length - 1;
    expect(evidenceOccurrences).toBe(2);
    const lastEvidenceIdx = region.lastIndexOf("{model.required.candidateEvidenceNotice}");
    expect(lastEvidenceIdx).toBeGreaterThan(detailsIdx);

    // wave3：NOT_HELD_BADGE 徽章常駐主視圖（<details> 之前），且與 else 分支的
    // candidateEvidenceNotice 是同一個三元運算式的兩側（`showBadge ? (badge) : (notice)`）。
    const mainRegion = region.slice(0, detailsIdx);
    expect(mainRegion).toContain("const showBadge = true");
    expect(mainRegion).toMatch(/showBadge\s*\?\s*\(/);
    const ternaryIdx = mainRegion.search(/showBadge\s*\?\s*\(/);
    const badgeIdx = mainRegion.indexOf("{NOT_HELD_BADGE}", ternaryIdx);
    const elseIdx = mainRegion.indexOf(") : (", ternaryIdx);
    const noticeIdx = mainRegion.indexOf("{model.required.candidateEvidenceNotice}", ternaryIdx);
    expect(badgeIdx, "NOT_HELD_BADGE 應在三元運算式的 true 分支").toBeGreaterThan(ternaryIdx);
    expect(badgeIdx).toBeLessThan(elseIdx);
    expect(noticeIdx, "candidateEvidenceNotice 應在三元運算式的 else 分支（徽章不渲染時的回退）").toBeGreaterThan(elseIdx);
    // 決策卡 required 條件 9：候選分支的股數一行也從本檔主視圖移除，改由
    // DecisionCard.tsx 渲染。
    expect(mainRegion).not.toContain("QuantitySection");
  });

  it("操作摘要 held 分支（wave3，派工單 §4.3 第 1／3／6 點；決策卡 required 條件 9 落地後更新）：disclaimer／confidenceMeaning／反面論點／explanation 半句／資料時間前綴／舊「規則評估：」複合詞只出現在 <details> 之後；主視圖保留結論大字、RULE_SOURCE_CHIP、CONFIDENCE_PREFIX 信心 chip、依據規則名、StaleDataAlert；role=alert 的 restoresComplianceWarning 已移至 DecisionCard.tsx，本檔主視圖不再渲染", () => {
    const start = summarySrc.indexOf('// model.kind === "held"');
    const end = summarySrc.indexOf("function DataMetaPrefixLine");
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const region = summarySrc.slice(start, end);
    const detailsIdx = region.indexOf('<details className="group mt-1">');
    expect(detailsIdx).toBeGreaterThan(-1);
    for (const needle of [
      "<InlineDisclaimer text={model.required.disclaimer} />",
      "{model.required.confidenceMeaning}",
      "反面論點",
      "——{model.topMatchedRule.explanation}",
      "<DataMetaPrefixLine response={response} />",
      "{buildLegacyAttributedHeadline(model.action)}",
    ]) {
      const idx = region.indexOf(needle);
      expect(idx, `${needle} 應出現、且只出現在 <details> 內`).toBeGreaterThan(detailsIdx);
    }
    const mainRegion = region.slice(0, detailsIdx);
    expect(mainRegion).toContain("{model.attributedHeadline}");
    expect(mainRegion).toContain("{RULE_SOURCE_CHIP}");
    expect(mainRegion).toContain("{CONFIDENCE_PREFIX}");
    expect(mainRegion).toContain("{summaryConfidenceLabel(model.required.confidence)}");
    expect(mainRegion).toContain("{RULE_BASIS_PREFIX}");
    expect(mainRegion).toContain("{model.topMatchedRule.name}");
    expect(mainRegion).not.toContain("{model.topMatchedRule.explanation}");
    expect(mainRegion).not.toContain("規則評估：");
    expect(mainRegion).toContain("<StaleDataAlert");
    // 決策卡 required 條件 9：股數一行與 role="alert" 的 restoresComplianceWarning
    // 從本檔主視圖移除（全頁恰一次改由 DecisionCard.tsx 渲染），不得回流。
    expect(mainRegion).not.toContain('role="alert"');
    expect(mainRegion).not.toContain("QuantitySection");
    // Q4(a)（qa low，決策卡第二輪修正）：本檔主視圖區段不含 quantityRangeShares
    // 這個欄位——股數一行已完全移交 DecisionCard.tsx，不留半殘引用。
    expect(mainRegion).not.toContain("quantityRangeShares");
  });

  it("no_price／no_action 分支（wave3 改版）：disclaimer 整行移除（全站頁尾 app/layout.tsx 已有一句常駐免責），資料時間前綴與舊字面收進最小 <details>；no_action 主視圖改為大字「資料不足」＋常駐小字 INSUFFICIENT_DATA_NO_EVALUATION，不掛 RULE_SOURCE_CHIP", () => {
    const noPriceStart = summarySrc.indexOf('if (model.kind === "no_price")');
    const noActionStart = summarySrc.indexOf('if (model.kind === "no_action")');
    const candidateStart = summarySrc.indexOf('if (model.kind === "candidate")');
    expect(noPriceStart).toBeGreaterThan(-1);
    expect(noActionStart).toBeGreaterThan(noPriceStart);
    expect(candidateStart).toBeGreaterThan(noActionStart);
    const noPriceRegion = summarySrc.slice(noPriceStart, noActionStart);
    const noActionRegion = summarySrc.slice(noActionStart, candidateStart);
    for (const region of [noPriceRegion, noActionRegion]) {
      expect(region).not.toContain("InlineDisclaimer");
      expect(region).toContain("<DetailsDataMetaOnly response={response}");
    }
    expect(noActionRegion).toContain("{model.reason}");
    expect(noActionRegion).toContain("{INSUFFICIENT_DATA_NO_EVALUATION}");
    expect(noActionRegion).not.toContain("RULE_SOURCE_CHIP");
    // 舊字面（HELD_ACTION_LABELS_LEGACY.insufficient_data）搬進這個分支自己的
    // <details>（children），不是刪除。
    const detailsIdx = noActionRegion.indexOf("<DetailsDataMetaOnly response={response}");
    const legacyIdx = noActionRegion.indexOf("{HELD_ACTION_LABELS_LEGACY.insufficient_data}");
    expect(legacyIdx).toBeGreaterThan(detailsIdx);
  });

  it("關鍵價位參考：R7 未還原權值句與 R6 停損兩句只出現在 <details> 之後，主視圖仍留兩個大字", () => {
    const compStart = keyLevelsSrc.indexOf("export function KeyLevelsPanel(");
    expect(compStart).toBeGreaterThan(-1);
    // 用實際 JSX 標籤（含 className）比對，避免比對到上方 doc comment 裡提到的
    // 「`<details>`」純文字references（同一子字串，但不是真正的標籤）。
    const detailsIdx = keyLevelsSrc.indexOf('<details className="group mt-3">', compStart);
    expect(detailsIdx).toBeGreaterThan(-1);
    for (const needle of [
      "{KEY_LEVELS_HEADER_UNADJUSTED_NOTICE}",
      "{anchorBasisSentence(anchorSource, levels)}",
      "KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE : KEY_LEVELS_STOP_CONDITION_ATR_UNAVAILABLE",
    ]) {
      const idx = keyLevelsSrc.indexOf(needle, compStart);
      expect(idx, `${needle} 應出現、且只出現在 <details> 內`).toBeGreaterThan(detailsIdx);
    }
    const mainRegion = keyLevelsSrc.slice(compStart, detailsIdx);
    expect(mainRegion).toContain("{KEY_LEVELS_STOP_CARD_TITLE}");
    expect(mainRegion).toContain("{fmt(levels.stopSuggested)}");
    expect(mainRegion).toContain("{KEY_LEVELS_TARGET_CARD_TITLE}");
    expect(mainRegion).toContain("{fmt(levels.target2R)}");
  });

  it("六項觀察條件：E-1 與資料時間句只出現在 <details> 之後，主視圖只留 h2＋計數句＋六圓點", () => {
    const compStart = entrySrc.indexOf("export function EntryObservationPanel(");
    expect(compStart).toBeGreaterThan(-1);
    const detailsIdx = entrySrc.indexOf('<details className="group mt-3">', compStart);
    expect(detailsIdx).toBeGreaterThan(-1);
    for (const needle of ["{ENTRY_E1_QUALIFIER}", "{buildDataTimesLine("]) {
      const idx = entrySrc.indexOf(needle, compStart);
      expect(idx, `${needle} 應出現、且只出現在 <details> 內`).toBeGreaterThan(detailsIdx);
    }
    const mainRegion = entrySrc.slice(compStart, detailsIdx);
    expect(mainRegion).toContain("{ENTRY_PANEL_TITLE}");
    expect(mainRegion).toContain("{buildConditionCount(");
    expect(mainRegion).toContain("STATUS_GLYPH[c.status]");
  });

  it("技術分析（wave3，派工單 §4.3 第 5／9 點）：bars／signals 的「資料時間：…｜來源：…」前綴與完整版徽章只出現在 <details> 內；主視圖合併同一列，只留「資料截至」徽章＋compact 狀態 chip（「日線」「指標」前綴沿用既有字面）", () => {
    const technicalDetailsIdx = pageSrc.indexOf("{DETAILS_SUMMARY_TECHNICAL}");
    expect(technicalDetailsIdx).toBeGreaterThan(-1);
    const barsPrefix = "資料時間：{formatDateTime(bars.data.as_of)}｜來源：{bars.data.data.source}";
    const signalsPrefix = "資料時間：{formatDateTime(signals.data.as_of)}｜來源：{signals.data.data.source}";
    expect(pageSrc.indexOf(barsPrefix)).toBeGreaterThan(technicalDetailsIdx);
    expect(pageSrc.indexOf(signalsPrefix)).toBeGreaterThan(technicalDetailsIdx);
    const mainRegion = pageSrc.slice(pageSrc.indexOf("{TECHNICAL_ANALYSIS_TITLE}</h2>"), technicalDetailsIdx);
    expect(mainRegion).not.toContain(barsPrefix);
    expect(mainRegion).not.toContain(signalsPrefix);
    // 主視圖：資料截至徽章＋兩顆 compact chip，「日線」「指標」同一列。
    expect(mainRegion).toContain("{buildDataAsOfBadge(bars.data.data.last_bar_date)}");
    expect(mainRegion).toContain("日線");
    expect(mainRegion).toContain("指標");
    // 主視圖兩顆徽章都帶 `compact`（逐一檢查每個標籤本身的屬性，而非整段文字
    // ——doc comment 裡也會提到這個詞，整段字串比對會誤判）。
    const mainBadgeTagStarts = [...mainRegion.matchAll(/<DataMetaStatusBadge/g)].map((m) => m.index ?? -1);
    expect(mainBadgeTagStarts.length).toBe(2);
    for (const start of mainBadgeTagStarts) {
      const tagEnd = mainRegion.indexOf("/>", start);
      expect(mainRegion.slice(start, tagEnd)).toMatch(/\bcompact\b/);
    }
    // 完整版（非 compact）徽章緊接在詳細內的前綴文字後面，同一行、同一個 <p>。
    const detailsRegion = pageSrc.slice(technicalDetailsIdx);
    const detailsEndIdx = detailsRegion.indexOf("</details>");
    const detailsBody = detailsRegion.slice(0, detailsEndIdx);
    expect(detailsBody.indexOf(barsPrefix)).toBeGreaterThan(-1);
    expect(detailsBody.indexOf(signalsPrefix)).toBeGreaterThan(-1);
    // 兩顆完整版徽章都不帶 compact（逐一檢查每個 <DataMetaStatusBadge ... />
    // 標籤本身的屬性，而非整段文字——doc comment 裡也會提到「compact」這個
    // 詞，用整段字串比對會誤判）。
    const badgeTagStarts = [...detailsBody.matchAll(/<DataMetaStatusBadge/g)].map((m) => m.index ?? -1);
    expect(badgeTagStarts.length).toBe(2);
    for (const start of badgeTagStarts) {
      const tagEnd = detailsBody.indexOf("/>", start);
      expect(detailsBody.slice(start, tagEnd)).not.toMatch(/\bcompact\b/);
    }
  });

  it("建議卡：R9 XREF 句從 summary 第二行移進展開內容第一行", () => {
    const adviceDetailsStart = pageSrc.indexOf('<details className="group rounded-lg border border-neutral-800">');
    expect(adviceDetailsStart).toBeGreaterThan(-1);
    const adviceRegion = pageSrc.slice(adviceDetailsStart, pageSrc.indexOf("</section>", adviceDetailsStart));
    const summaryEndIdx = adviceRegion.indexOf("</summary>");
    const xrefIdx = adviceRegion.indexOf("{ADVICE_CARD_XREF_TO_SUMMARY}");
    expect(summaryEndIdx).toBeGreaterThan(-1);
    expect(xrefIdx).toBeGreaterThan(summaryEndIdx);
  });
});
/**
 * 六項觀察條件（CEO 2026-09-06；PRD `work/stock-desk-進場觀察條件-PRD.md` §4b；
 * 風控預審 R-01～R-22 → 守門 T1～T14）。
 */
describe("六項觀察條件 守門（T1～T14）", () => {
  const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
  const panelSrc = read("../../position/[symbol]/EntryObservationPanel.tsx");
  const pageSrc = read("../../position/[symbol]/page.tsx");
  const wordingSrc = read("../entryObservationWording.ts");

  const CONSTANTS: Record<string, string> = {
    ENTRY_PANEL_TITLE,
    ENTRY_PANEL_TAGLINE,
    ENTRY_E1_QUALIFIER,
    ENTRY_E2_XREF,
    ENTRY_E3_DASH_NOTE,
    ENTRY_NO_DATA_STATEMENT,
    LADDER_BAND_TAG,
    LADDER_BAND_NOTE,
    count0: buildConditionCount(0, 0),
    count4: buildConditionCount(4, 0),
    count31: buildConditionCount(3, 1),
    count6: buildConditionCount(6, 0),
    rangeLabel: buildRangeConditionLabel(252),
    rangeLabelNull: buildRangeConditionLabel(null),
    hits: buildDefensiveHitsText(1),
    times: buildDataTimesLine("A", "B", "C", false),
    timesSame: buildDataTimesLine("A", "A", "A", true),
    timesMissing: buildDataTimesLine(null, null, null, false),
    basisRangeNull: flatBasis(buildEntryBasisRange(null)),
    rangeNoteNull: buildEntryRangeNotValuationNote(null),
    rangeNote: buildEntryRangeNotValuationNote(252),
    ...Object.fromEntries(Object.entries(ENTRY_CONDITION_LABELS).map(([k, v]) => [`label_${k}`, v])),
    ...Object.fromEntries(Object.entries(ENTRY_CONDITION_THRESHOLDS).map(([k, v]) => [`threshold_${k}`, v])),
    ...Object.fromEntries(Object.entries(ENTRY_STATUS_LABELS).map(([k, v]) => [`status_${k}`, v])),
    basisRange: flatBasis(buildEntryBasisRange(252)),
    basisTrend: flatBasis(ENTRY_BASIS_TREND),
    basisPullback: flatBasis(ENTRY_BASIS_PULLBACK),
    basisMomentum: flatBasis(ENTRY_BASIS_MOMENTUM),
    basisVolume: flatBasis(ENTRY_BASIS_VOLUME),
    basisRules: flatBasis(ENTRY_BASIS_RULES),
  };

  it("T1／T2：全部字面逐字釘住、無禁用詞、無裸即時、無本案組合禁語", () => {
    const combos = [
      /條件成立/,
      /進場[^。；]{0,8}成立/,
      /(成立|符合|達成|通過)率|分數|評分|得分|滿分|等級|星級/,
      /還差|僅差|只差|接近成立/,
      /全部成立|六條全數|全數成立|滿足全部/,
      /進場點|買點|時機|時點|訊號|達標|過關/,
    ];
    for (const [name, text] of Object.entries(CONSTANTS)) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, name);
      expect(findBareRealtimeClaims(text), name).toEqual([]);
      // 組合禁語只針對肯定句；E-1 依風控要求以否定式列舉「不代表…達成率」，該否定子句先剝除再掃。
      // 「信心等級」為既有固定名詞（E-2 依風控要求指向操作摘要的信心等級），非對計數的分級。
      // REQ-4: the negation clause ends at the next comma too, so an affirmative clause after 「，」 is still scanned.
      // REQ-5: the fixed-term exemption is limited to E-2's exact phrase, not to every 「信心等級」.
      const affirmative = text.replace(/不代表[^。；，,]*/g, "").replace(/信心等級與免責事項見上方操作摘要/g, "");
      for (const re of combos) expect(affirmative, `${name} 命中組合禁語 ${re}`).not.toMatch(re);
    }
    expect(ENTRY_PANEL_TITLE).toBe("六項觀察條件");
    expect(ENTRY_PANEL_TITLE).not.toContain("進場");
    expect(ENTRY_PANEL_TAGLINE).toBe("這裡逐條列出六項條件的現況，明細列於下方。");
    expect(ENTRY_STATUS_LABELS).toEqual({ met: "成立", unmet: "未成立", unavailable: "無法判定" });
    expect(ENTRY_CONDITION_LABELS).toEqual({
      trend: "收盤與 MA60",
      pullback: "距 MA20",
      momentum: "RSI(14)",
      volume: "成交量 z",
      rules: "防禦型規則",
    });
    expect(buildRangeConditionLabel(252)).toBe("近 252 根位階");
    expect(ENTRY_CONDITION_THRESHOLDS).toEqual({
      range: "≤ 70%",
      trend: "收盤 > MA60",
      pullback: "±3% 內",
      momentum: "30–70（不含端點）",
      volume: "−2～2（不含端點）",
      rules: "= 0（未持有時無法判定）",
    });
    // 門檻字面與純函式常數同源。
    expect(ENTRY_CONDITION_THRESHOLDS.range).toContain(String(ENTRY_RANGE_MAX_PCT));
    expect(ENTRY_CONDITION_THRESHOLDS.pullback).toContain(String(ENTRY_PULLBACK_MAX_ABS_PCT));
    expect(ENTRY_E1_QUALIFIER).toBe(
      "以上六條門檻皆為本面板自訂之固定值；成立數僅為符合門檻的條數，不代表機率、達成率或任何買賣判斷。",
    );
    for (const q of ["自訂之固定值", "僅為符合門檻的條數", "不代表機率、達成率或任何買賣判斷"]) expect(ENTRY_E1_QUALIFIER).toContain(q);
    expect(ENTRY_E2_XREF).toBe("本面板不是操作摘要結論的一部分；結論、信心等級與免責事項見上方操作摘要。");
    expect(ENTRY_E3_DASH_NOTE).toBe("「—」代表無法判定，不代表數值為零，也不代表未成立。");
    expect(ENTRY_NO_DATA_STATEMENT).toBe("目前資料不足，六條條件均無法判定。");
    expect(LADDER_BAND_TAG).toBe("MA20 ±3%");
    expect(LADDER_BAND_NOTE).toBe("有「MA20 ±3%」標籤的列，價位皆在該範圍內。");
    expect(buildDefensiveHitsText(1)).toBe("命中 1 條");
    expect(buildDataTimesLine("A", "B", "C", false)).toBe("資料時間：日線 A｜指標 B｜規則評估 C");
    expect(buildDataTimesLine("A", "A", "A", true)).toBe("資料時間：A（日線／指標／規則評估同步）");
    // REQ-3: identical display strings are NOT enough — the caller decides from raw stamps.
    expect(buildDataTimesLine("A", "A", "A", false)).toBe("資料時間：日線 A｜指標 A｜規則評估 A");
    expect(buildDataTimesLine(null, null, null, false)).toBe("資料時間：日線 —｜指標 —｜規則評估 —");
    expect(buildEntryBasisRange(null).formula[0]).toContain("位階(近N根)");
    expect(buildEntryRangeNotValuationNote(null)).toBe("位階數字僅反映價格在近 N 根區間中的相對位置，與便宜或昂貴的估值判斷無關。");
    expect(buildEntryRangeNotValuationNote(252)).toBe("位階數字僅反映價格在近 252 根區間中的相對位置，與便宜或昂貴的估值判斷無關。");
    expect(buildEntryRangeNotValuationNote(252)).not.toBe(buildRangeNotValuationNote(252));
    expect(ENTRY_BASIS_RULES.qualifier).toContain("不因未命中而視為成立");
    expect(buildEntryFooterItems(252)).toHaveLength(7);
  });

  it("T3／T11：計數句為陳述句，無 %、無 N/6、無「分」；unavailable > 0 一律印出無法判定條數", () => {
    for (const [met, un] of [[0, 0], [4, 0], [3, 1], [0, 6], [6, 0]] as const) {
      const text = buildConditionCount(met, un);
      expect(text).not.toMatch(/%|\/6|分/);
      expect(text).toMatch(/^6 條中成立 \d 條/);
      if (un > 0) expect(text).toContain(`其中 ${un} 條無法判定`);
      else expect(text).not.toContain("無法判定");
    }
    expect(buildConditionCount(4, 0)).toBe("6 條中成立 4 條。");
    expect(buildConditionCount(3, 1)).toBe("6 條中成立 3 條，其中 1 條無法判定。");
  });

  it("T4／T7／T8／T13：三重編碼、E-1～E-4（CEO 第二次裁定 2026-09-19 後全數收進詳細）、不 import 結論元素、計數字級 ≤ text-lg", () => {
    expect(panelSrc).toContain("aria-label={`${conditionLabel(c.id, rangeBarCount)}：${observedText(c)}，${ENTRY_STATUS_LABELS[c.status]}`}");
    expect(panelSrc).toContain("{STATUS_GLYPH[c.status]}");
    expect(panelSrc).toContain("{ENTRY_STATUS_LABELS[c.status]}");
    // REQ-1: rows always listed; the footer group is unconditional; 「同步」 決定 on raw stamps (REQ-3).
    expect(panelSrc).not.toContain("observation.allUnavailable ? (");
    expect(pageSrc).toContain("{ title: ENTRY_PANEL_TITLE, items: buildEntryFooterItems(entryLevels?.rangeBarCount ?? null) }");
    expect(panelSrc).toContain("dataTimes.bars === dataTimes.signals && dataTimes.signals === dataTimes.advice");
    for (const needle of ["{ENTRY_E1_QUALIFIER}", "{ENTRY_E2_XREF}", "{ENTRY_E3_DASH_NOTE}", "{buildDataTimesLine("]) {
      expect(panelSrc).toContain(needle);
    }
    // CEO 第二次裁定 2026-09-19（推翻一眼一句 §2.5 的「E-1／資料時間句常駐主視圖」
    // 舊裁定）：E-1、E-2、E-3、資料時間句（不論是否 synchronized）全數收進
    // `<details>`（六項觀察條件唯一允許的摺疊區塊，summary＝`DETAILS_SUMMARY_ENTRY`）；
    // 主視圖只留 h2、計數句、六圓點。精確的「只出現在 details 內」位置比對見
    // 「CEO 第二次裁定 wave2」describe block。
    expect(panelSrc).toContain("<details");
    expect(panelSrc).toContain("<summary");
    // `[&::-webkit-details-marker]:hidden` is the same `<details>`-chevron idiom every
    // other 一眼一句 panel already uses (KeyLevelsPanel／OperationSummaryPanel／page.tsx),
    // not a content-hiding utility — excluded from this scan on that basis alone.
    expect(panelSrc).not.toMatch(/line-clamp|truncate|max-h-|overflow-y-(auto|scroll)|sr-only|aria-expanded|IntersectionObserver|React\.lazy|Suspense|sticky/);
    expect(panelSrc).not.toMatch(/text-neutral-(5|6|7)00/);
    // R-15：只看 import 行與 JSX 取值，doc comment 提到這些詞不算。
    const importLines = panelSrc.split("\n").filter((l) => l.startsWith("import"));
    for (const l of importLines) {
      expect(l).not.toMatch(/buildAttributedHeadline|CANDIDATE_HEADING_LABEL|confidenceLabel|summaryConfidenceLabel|HELD_ACTION_LABELS|actionRawLabel|adviceWording|operationSummary/);
    }
    expect(panelSrc).not.toMatch(/\.disclaimer|\.confidence\b|\.headline|\.action\b/);
    expect(panelSrc).not.toMatch(/text-(xl|2xl|3xl)/);
  });

  it("T5：狀態常數區塊與階梯標籤不得帶任何色相（R-21）", () => {
    const block = panelSrc.slice(panelSrc.indexOf("const STATUS_GLYPH"), panelSrc.indexOf("function fmtNum"));
    expect(block).not.toMatch(/(red|green|rose|emerald|amber|lime|yellow|sky|blue|indigo|violet|orange)-\d/);
    expect(panelSrc).not.toMatch(/(red|green|rose|emerald|amber|lime|yellow|sky)-\d/);
    const ladder = read("../../position/[symbol]/PriceLadder.tsx");
    const bandBits = ladder.split("\n").filter((l) => l.includes("inBand") || l.includes("LADDER_BAND"));
    for (const l of bandBits) expect(l).not.toMatch(/(red|green|rose|emerald|amber|lime|yellow|sky)-\d/);
  });

  it("T6：全部成立無特殊態——原始碼無 metCount 分支、無 === 6", () => {
    expect(panelSrc).not.toMatch(/metCount\s*===|=== 6\b|=== conditions\.length|allMet|metCount >=/);
    expect(wordingSrc).not.toMatch(/=== 6\b|met === /);
  });

  it("T9（一眼一句 §2.1 改序）：位置——操作摘要 → 關鍵價位參考 → 六項觀察條件；頁尾組同序", () => {
    const summary = pageSrc.indexOf("<OperationSummaryPanel advice={advice} />");
    const keyLevels = pageSrc.indexOf("<KeyLevelsPanel");
    const entry = pageSrc.indexOf("<EntryObservationPanel");
    expect(summary).toBeGreaterThan(-1);
    expect(keyLevels).toBeGreaterThan(summary);
    expect(entry).toBeGreaterThan(keyLevels);
    const gEntry = pageSrc.indexOf("title: ENTRY_PANEL_TITLE");
    const gSummary = pageSrc.indexOf("title: OPERATION_SUMMARY_TITLE");
    const gKey = pageSrc.indexOf("title: KEY_LEVELS_PANEL_TITLE");
    expect(gKey).toBeGreaterThan(gSummary);
    expect(gEntry).toBeGreaterThan(gKey);
    expect(panelSrc).toContain("{buildFooterGuidance(ENTRY_PANEL_TITLE)}");
  });

  it("T10／T12：R3／R4 防復活——indicatorBands 無 closeVsMa；收盤與 MA60 同取自 KeyLevels；規則條需 held 確認", () => {
    expect(read("../indicatorBands.ts")).not.toContain("closeVsMa");
    const evalSrc = read("../entryObservation.ts");
    expect(evalSrc).toMatch(/const close = fin\(levels\?\.close\);\s*const ma60 = fin\(levels\?\.ma60\);/);
    expect(evalSrc).toContain("held !== true");
    expect(pageSrc).toContain('advice.data?.status === "ok" ? advice.data.held : null');
  });

  it("T14：EntryObservation／metCount 不離開個股頁", () => {
    for (const rel of [
      "../../components/PositionsTable.tsx",
      "../../components/SummaryCards.tsx",
      "../../components/PendingAlertsPanel.tsx",
      "../../settings/AlertRulesSection.tsx",
      "../../playbook/page.tsx",
      "../../backtest/BacktestReportView.tsx",
    ]) {
      expect(read(rel), `${rel} 不得引用六項觀察條件`).not.toMatch(/EntryObservation|metCount|entryObservation/);
    }
  });
});

/**
 * 風控逐字審 R-A2（`work/stock-desk-一眼一句-實作規格.md` §5 全數 APPROVE 後
 * required）：`oneLinerWording.ts` header 自稱「逐字釘住」，但落地當下沒有任何
 * 斷言比對其字面——本節補齊：該檔全部 exported 常數與 builder 輸出樣板逐字
 * `toBe`；`RiskGauge.tsx` 的 H4 頂部說明句全文與 H5 summary 半句原本只加測試、
 * 不改元件，但 CEO 2026-09-19 第二次裁定（派工單 §4.1）推翻 H4 常駐後，
 * wave2-B 把這句搬進 details——本節斷言同步改為「字面仍在、但落在 details
 * 內」；`AlertStatusStrip.tsx` 的查詢失敗前綴同時釘常數與 wiring。
 * qa 追加 low：`DETAILS_SUMMARY_ADVICE` 全專案未被引用，已直接自
 * `oneLinerWording.ts` 移除（規格 §5 清單同步由 dev-lead 更新），不留死碼。
 */
describe("oneLinerWording.ts 逐字釘住（風控逐字審 R-A2）", () => {
  it("DETAILS_SUMMARY_* 常數逐字比對，且死碼 DETAILS_SUMMARY_ADVICE 已移除", () => {
    expect(DETAILS_SUMMARY_GENERIC).toBe("詳細說明與依據");
    expect(DETAILS_SUMMARY_OPERATION).toBe("詳細：反面論點、失效條件與假設");
    expect(DETAILS_SUMMARY_KEY_LEVELS).toBe("查看計算依據");
    expect(DETAILS_SUMMARY_ENTRY).toBe("詳細：六條逐項明細");
    expect(DETAILS_SUMMARY_TECHNICAL).toBe("詳細：七張指標卡與風險量測");
    expect(DETAILS_SUMMARY_RISK_GAUGE).toBe("詳細：各項判定依據、假設與資料來源");
    const src = readFileSync(fileURLToPath(new URL("../oneLinerWording.ts", import.meta.url)), "utf8");
    expect(src).not.toContain("DETAILS_SUMMARY_ADVICE");
  });

  it("個股頁 3 個 builder 輸出樣板逐字比對", () => {
    expect(buildTechOneLiner(386, "918.66")).toBe("近 386 根日線，收盤 918.66。");
    expect(buildKeyLevelsOneLiner("918.66", 252, "上緣")).toBe("收盤 918.66，位於近 252 根區間上緣。");
    expect(buildAdviceHitCount(3)).toBe("命中 3 條");
  });

  /**
   * wave3（派工單 §4.3 第 5 點）：同年只印月-日，跨年印完整西元年；`null`
   * （尚無日線）不渲染任何徽章。
   */
  it("buildDataAsOfBadge：同年 MM-DD／跨年 YYYY-MM-DD／null 不渲染", () => {
    const thisYear = new Date().getFullYear();
    expect(buildDataAsOfBadge(`${thisYear}-09-18`)).toBe("資料截至 09-18");
    expect(buildDataAsOfBadge(`${thisYear - 1}-09-18`)).toBe(`資料截至 ${thisYear - 1}-09-18`);
    expect(buildDataAsOfBadge(null)).toBeNull();
  });

  it("首頁警示狀態列常數與 3 個 builder 輸出樣板逐字比對", () => {
    expect(ALERTS_NO_RULES).toBe("尚未設定警示規則");
    expect(ALERTS_NO_RULES_LINK).toBe("去設定");
    expect(ALERTS_MANAGE_LINK).toBe("管理警示規則");
    expect(ALERTS_SCHEDULER_DISABLED).toBe("排程目前未啟用，警示評估暫不會更新");
    expect(ALERTS_LOAD_ERROR_PREFIX).toBe("無法載入警示狀態：");
    expect(buildAlertsRulesNoEvents(4)).toBe("4 條規則已設定，目前沒有待處理警示");
    expect(buildAlertsQueriedAt("2026-09-19 16:40（台北時間）")).toBe("查詢時間：2026-09-19 16:40（台北時間）");
    expect(buildAlertsPendingCount(2)).toBe("2 條待處理警示");
  });

  it("AlertStatusStrip.tsx wiring：查詢失敗前綴確實由元件渲染", () => {
    const src = readFileSync(fileURLToPath(new URL("../../components/AlertStatusStrip.tsx", import.meta.url)), "utf8");
    expect(src).toContain("{ALERTS_LOAD_ERROR_PREFIX}");
  });

  /**
   * 第二波（派工單 §4.3，風控逐字審核可）：匯率貢獻卡「備援匯率」徽章新常數
   * 逐字比對，並確認 `SummaryCards.tsx` 確實渲染它、且不是 hover-only。
   */
  it("FX_BACKUP_BADGE 逐字比對，且 SummaryCards.tsx 確實渲染、非 hover-only", () => {
    expect(FX_BACKUP_BADGE).toBe("備援匯率");
    const src = readFileSync(fileURLToPath(new URL("../../components/SummaryCards.tsx", import.meta.url)), "utf8");
    expect(src).toContain("{FX_BACKUP_BADGE}");
    expect(src).not.toMatch(/hover:[^\n"]*\{FX_BACKUP_BADGE\}/);
  });
});

describe("RiskGauge.tsx H4／H5 逐字釘住（風控逐字審 R-A2；只加測試，不改 B 的元件）", () => {
  function makeSource(symbol: string, status: string): SymbolDataMeta {
    return {
      symbol,
      market: "TW",
      data: {
        status,
        source: "twse",
        staleness_minutes: null,
        is_within_ttl: null,
        bar_count: 100,
        first_bar_date: "2026-01-01",
        last_bar_date: "2026-08-08",
        trading_days_behind: null,
        reason: null,
      },
    };
  }

  function makeCheck(overrides: Partial<BookLimitCheck>): BookLimitCheck {
    return {
      index: 1,
      limit_id: "single_position_weight",
      name: "單一標的佔比上限",
      status: "passed",
      observed: 0.05,
      threshold: 0.2,
      detail: "detail",
      worst_symbol: null,
      evaluated_count: 3,
      excluded: [],
      ...overrides,
    };
  }

  it("H4：頂部說明句全文逐字存在於原始碼，且落在 details 內（CEO 2026-09-19 第二次裁定 §4.1 推翻 H4 常駐，wave2-B 純搬移；字面仍為風控裁決 2026-08-09 核可全文，不得改字）", () => {
    const src = readFileSync(fileURLToPath(new URL("../../components/RiskGauge.tsx", import.meta.url)), "utf8");
    // JSX 原始碼跨行縮排；比對前雙方都去除全部空白字元，避免換行/縮排造成假陰性。
    const flat = src.replace(/\s+/g, "");
    const h4 =
      "單一標的佔比、單一產業佔比、單筆最大可承受虧損三條為逐檔比較，回報最差結果；總曝險與 Kelly" +
      "部位上限為帳本層單一判定。未納入比較的標的列於各條之下。";
    expect(flat).toContain(h4.replace(/\s+/g, ""));

    // 不只存在於原始碼，且必須在渲染輸出裡落在 <details> 開標籤之後（在
    // details 內）——主視圖不得再看到這句。
    const data: PortfolioLimitsResponse = {
      as_of: "2026-09-19T16:40:00+08:00",
      limits: [makeCheck({})],
      notes: [],
      sources: [makeSource("2330", "fresh")],
    } as unknown as PortfolioLimitsResponse;
    const html = renderToStaticMarkup(createElement(RiskGaugeView, { data }));
    const detailsIndex = html.indexOf("<details");
    const h4Index = html.indexOf("單一標的佔比、單一產業佔比、單筆最大可承受虧損三條為逐檔比較");
    expect(detailsIndex).toBeGreaterThanOrEqual(0);
    expect(h4Index).toBeGreaterThan(detailsIndex);
  });

  it("H5：非 fresh 時 summary 附「——其中 {N} 檔非即時」半句，緊接 DETAILS_SUMMARY_RISK_GAUGE 之後", () => {
    const data: PortfolioLimitsResponse = {
      as_of: "2026-09-19T16:40:00+08:00",
      limits: [makeCheck({})],
      notes: [],
      sources: [makeSource("2330", "fresh"), makeSource("2317", "cached_stale")],
    } as unknown as PortfolioLimitsResponse;
    const html = renderToStaticMarkup(createElement(RiskGaugeView, { data }));
    expect(html).toContain(`${DETAILS_SUMMARY_RISK_GAUGE}——其中 1 檔非即時`);
  });

  it("H5：全部 fresh 時 summary 不附半句", () => {
    const data: PortfolioLimitsResponse = {
      as_of: "2026-09-19T16:40:00+08:00",
      limits: [makeCheck({})],
      notes: [],
      sources: [makeSource("2330", "fresh")],
    } as unknown as PortfolioLimitsResponse;
    const html = renderToStaticMarkup(createElement(RiskGaugeView, { data }));
    expect(html).toContain(DETAILS_SUMMARY_RISK_GAUGE);
    expect(html).not.toContain("非即時");
  });
});

/**
 * 決策卡（`work/stock-desk-一眼一句簡化-派工單.md` §5.4／視覺規範 B.7）風控
 * 2026-09-19 預審 APPROVE_WITH_CONDITIONS：新字面逐字釘住、位置守門。
 */
describe("決策卡（DecisionCard.tsx）新字面逐字釘住與位置守門", () => {
  const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

  const HELD_RESPONSE = {
    status: "ok",
    reason: null,
    held: true,
    position_ids: [1],
    context_notes: [],
    symbol: "2330",
    market: "TW",
    as_of: "2026-09-18T09:00:00+08:00",
    portfolio_context: {} as unknown,
    data: {
      status: "fresh",
      source: "twse",
      staleness_minutes: 5,
      is_within_ttl: null,
      bar_count: 300,
      first_bar_date: "2025-05-01",
      last_bar_date: "2026-09-18",
      trading_days_behind: null,
      reason: null,
    },
    advice: {
      symbol: "2330",
      action: "add",
      quantity_range: {
        min_shares: 500,
        max_shares: 1000,
        restores_compliance: true,
        basis: "以「單一標的佔比上限」為最小可用額度換算，最多可再買進 1000 股。",
      },
      matched_rules: [
        {
          id: "uptrend_ma_stack",
          name: "均線多頭排列",
          action: "add",
          weight: 0.5,
          weight_meaning: "權重為規則優先序，非機率、勝率或預期報酬",
          explanation: "5 日、20 日、60 日均線由上而下排列。",
        },
      ],
      counterarguments: [],
      invalidation_conditions: [],
      confidence: "medium",
      confidence_meaning: "信心等級反映規則一致性與資料完整度，非勝率或機率",
      rules_version: "1.0.2",
      as_of: "2026-09-18T09:00:00+08:00",
      observation_window: { start: "2025-05-01", end: "2026-09-18", bars: 300 },
      disclaimer: "本工具為研究與教育用途，非投資建議",
      limits_check: [],
      action_weights: [],
      direction_weights: [],
      has_conflict: false,
      aggregated_action: "add",
      blocked_action: null,
      blocked_notices: [],
      downgrade_notices: [],
      evaluation: { total_rules: 1, evaluated_rules: 1, matched_rules: 1, data_completeness: 1, skipped_rules: [] },
    },
  } as unknown as AdviceResponse;

  it("required 條件 4／1：DECISION_CARD_ARIA_LABEL／DECISION_CARD_DISTANCE_PREFIX 逐字比對，且無 §1.3 禁用詞、無裸即時宣稱", () => {
    expect(DECISION_CARD_ARIA_LABEL).toBe("決策摘要");
    expect(DECISION_CARD_DISTANCE_PREFIX).toBe("距最新收盤 ");
    // R1（決策卡第二輪修正，風控複審 APPROVE_WITH_CONDITIONS）：「股數」不予核可，改為「股數參考」。
    expect(DECISION_CARD_QUANTITY_LABEL).toBe("股數參考");
    for (const text of [DECISION_CARD_ARIA_LABEL, DECISION_CARD_DISTANCE_PREFIX, DECISION_CARD_QUANTITY_LABEL]) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, text);
      expect(findBareRealtimeClaims(text)).toEqual([]);
    }
  });

  it("required 條件 1（風控 VETO）：「距現價」三字不得出現於任何面向使用者的字面（常數本身與其渲染輸出，不含解釋性 doc comment）", () => {
    expect(buildDecisionCardDistance(-8)).not.toContain("距現價");
    expect(buildDecisionCardDistance(-8)).toContain("距最新收盤");
    for (const text of [DECISION_CARD_ARIA_LABEL, DECISION_CARD_DISTANCE_PREFIX, DECISION_CARD_QUANTITY_LABEL]) {
      expect(text).not.toContain("距現價");
    }
    const bars: Bar[] = Array.from({ length: 80 }, (_, i) => ({
      date: `2026-0${1 + Math.floor(i / 28)}-${String(1 + (i % 28)).padStart(2, "0")}`,
      open: "100", high: "105", low: "95", close: String(100 + (i % 7)), volume: 1000, currency: "TWD", source: "demo",
    }));
    const html = renderToStaticMarkup(
      createElement(DecisionCardBody, {
        response: HELD_RESPONSE,
        bars,
        anchorSource: "cost",
        avgCost: 1000,
      }),
    );
    expect(html).not.toContain("距現價");
    expect(html).toContain("距最新收盤");
  });

  it("required 條件 2：符號由 (水位－最新收盤)/最新收盤×100 決定，複用 fmtSigned；四捨五入為 0 印 0.0% 不得 -0.0%", () => {
    expect(buildDecisionCardDistance(-8)).toBe("距最新收盤 -8.0%");
    expect(buildDecisionCardDistance(19.98)).toBe("距最新收盤 +20.0%");
    expect(buildDecisionCardDistance(0)).toBe("距最新收盤 0.0%");
    expect(buildDecisionCardDistance(-0.02)).toBe("距最新收盤 0.0%");
    expect(buildDecisionCardDistance(-0.02)).not.toContain("-0.0%");
    // decisionCardWording.ts 不得另寫一份四捨五入／正負號邏輯——只允許 import fmtSigned。
    const src = read("../decisionCardWording.ts");
    expect(src).toContain('import { fmtSigned } from "../position/[symbol]/PriceLadder"');
    expect(src).not.toMatch(/function fmtSigned/);
  });

  it("required 條件 4：<section aria-label={DECISION_CARD_ARIA_LABEL}> 且本卡不另外渲染任何 <h2> 可見標題", () => {
    const src = read("../../position/[symbol]/DecisionCard.tsx");
    expect(src).toContain("<section aria-label={DECISION_CARD_ARIA_LABEL}");
    expect(src).not.toMatch(/<h2/);
  });

  it("P1（一眼一句 §2.1 之上）：<DecisionCard 出現在 page.tsx 技術分析 section 之前，且恰出現一次（Q4c）", () => {
    const pageSrc = read("../../position/[symbol]/page.tsx");
    const decisionCardIdx = pageSrc.indexOf("<DecisionCard");
    const technicalIdx = pageSrc.indexOf(`{TECHNICAL_ANALYSIS_TITLE}</h2>`);
    expect(decisionCardIdx).toBeGreaterThan(-1);
    expect(technicalIdx).toBeGreaterThan(decisionCardIdx);
    expect((pageSrc.match(/<DecisionCard/g) ?? []).length).toBe(1);
  });

  it("Q4(b)（qa low）：全部掃描檔案中，只有 DecisionCard.tsx 引用 quantityRangeShares（operationSummary.ts 是型別／建構來源，本身必然帶有欄位名，不計入）", () => {
    for (const rel of SCANNED_FILES) {
      if (rel === "../operationSummary.ts") continue; // 欄位定義／組裝來源，非「渲染引用」。
      const src = read(rel);
      if (rel === "../../position/[symbol]/DecisionCard.tsx") {
        expect(src).toContain("quantityRangeShares");
      } else {
        expect(src, `${rel} 不應引用 quantityRangeShares`).not.toContain("quantityRangeShares");
      }
    }
  });

  it("Q4(d)（qa low／風控 S2）：DecisionCard.tsx 的 NumberCell 原始碼不含 rose-/red-/green-/emerald- 類別（required 條件 11：停損/停利大字與距離不上紅綠）", () => {
    const src = read("../../position/[symbol]/DecisionCard.tsx");
    const start = src.indexOf("function NumberCell");
    const end = src.indexOf("function MainSlot");
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const region = src.slice(start, end);
    expect(region).not.toMatch(/rose-|red-|green-|emerald-/);
  });
});

/**
 * 族群動能排行（第四波，`work/stock-desk-族群動能-派工單.md` §12/§13 風控逐字
 * 定稿）：卡片標題、常駐 tag 與 NE-8 卡片層級警告逐字釘住。其餘句子（NE 原因
 * 句、failed／passed 主視圖與詳細句、族群排除句等）由
 * `sectorMomentumWording.test.ts` 逐句釘住，這裡只覆蓋跨檔案共用、最容易被
 * 誤改的幾個常數，避免與該檔重複整份列表。
 */
describe("SectorMomentumCard — 標題與常駐 tag 定稿字面（§4.6 CL-2／§12／§6.1 NE-8）", () => {
  it("標題、時間窗 chip、僅上市 tag、NE-8 卡片層級警告", () => {
    expect(SECTOR_CARD_TITLE).toBe("族群動能排行");
    expect(buildLookbackChip(5)).toBe("近 5 日");
    expect(TWSE_ONLY_TAG).toBe("僅上市");
    expect(DEMO_DATA_CARD_WARNING).toBe("警告：本卡使用的是離線示範資料（demo_synthetic），不是市場資料。");
  });

  it("列示順序句（§4.1e／§6.3 H-2）", () => {
    expect(buildListingOrderSentence(5)).toBe("列示順序僅依近 5 日漲跌幅，不代表任何優先順序。");
  });
});
