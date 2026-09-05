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
  "../../components/PageDisclosureSection.tsx",
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

  it("C2/C3 守門：page.tsx 必須渲染 PageDisclosureSection，且該元件必須渲染 NON_REALTIME_NOTICE", () => {
    const pageSource = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/page.tsx", import.meta.url)),
      "utf8",
    );
    expect(pageSource).toContain("<PageDisclosureSection />");
    const sectionSource = readFileSync(
      fileURLToPath(new URL("../../components/PageDisclosureSection.tsx", import.meta.url)),
      "utf8",
    );
    expect(sectionSource).toContain("{NON_REALTIME_NOTICE}");
    // C2：區塊為靜態常數，不得依賴任何 query 狀態
    expect(sectionSource).not.toMatch(/useQuery|useAdvice|useBars|isPending|isError/);
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

  it("FR-2 wiring 守門：五則導讀各自的宿主元件確實渲染該常數（qa-reviewer 建議）", () => {
    const wiring: [string, string][] = [
      ["../../position/[symbol]/OperationSummaryPanel.tsx", "{OPERATION_SUMMARY_TAGLINE}"],
      ["../../position/[symbol]/KeyLevelsPanel.tsx", "{KEY_LEVELS_TAGLINE}"],
      ["../../position/[symbol]/page.tsx", "{TECHNICAL_CHART_TAGLINE}"],
      ["../../position/[symbol]/page.tsx", "{TECHNICAL_INDICATORS_TAGLINE}"],
      ["../../position/[symbol]/LeverageChapterView.tsx", "{LEVERAGE_CHAPTER_TAGLINE}"],
    ];
    for (const [rel, needle] of wiring) {
      const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
      expect(src, `${rel} 應渲染 ${needle}`).toContain(needle);
    }
  });

  it("FR-4 C5 守門：AdviceCardView 必須渲染銜接句，且不得單獨放回 headline／disclaimer／信心等級", () => {
    const src = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/AdviceCardView.tsx", import.meta.url)),
      "utf8",
    );
    expect(src).toContain("{ADVICE_CARD_XREF_TO_SUMMARY}");
    // C5：headline／信心等級／confidenceMeaning／disclaimer 同進同退——任何一項回流即紅燈。
    expect(src).not.toMatch(/buildAttributedHeadline|CANDIDATE_HEADING_LABEL|advice\.disclaimer|confidenceLabel\(|confidence_meaning/);
    // R-1：衝突揭露句指涉改為操作摘要的結論（逐字）。
    expect(src).toContain("本次同時命中方向相反的規則，上方操作摘要的結論只代表權重較高的一方。");
  });

  it("P1 結論位順序守門：操作摘要先於頁級揭露區，頁級揭露區先於其餘區塊（qa-reviewer 建議）", () => {
    const pageSource = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/page.tsx", import.meta.url)),
      "utf8",
    );
    const summary = pageSource.indexOf("<OperationSummaryPanel advice={advice} />");
    const disclosure = pageSource.indexOf("<PageDisclosureSection />");
    const keyLevels = pageSource.indexOf("<KeyLevelsPanel");
    expect(summary).toBeGreaterThan(-1);
    expect(disclosure).toBeGreaterThan(summary);
    expect(keyLevels).toBeGreaterThan(disclosure);
  });

  it("FR-3 C4：NON_REALTIME_NOTICE 在頁面元件中只由頁級揭露區渲染（操作摘要與關鍵價位面板不再重複）", () => {
    for (const rel of ["../../position/[symbol]/OperationSummaryPanel.tsx", "../../position/[symbol]/KeyLevelsPanel.tsx"]) {
      const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
      expect(src).not.toMatch(/\{(model|required)\.nonRealtimeNotice\}|\{NON_REALTIME_NOTICE\}/);
    }
  });
});
