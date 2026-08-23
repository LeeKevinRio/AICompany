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
    // instruction to future maintainers, not user-facing copy — the same
    // acknowledged-limitation/instruction 語境 already accepted for the
    // 「勝率」 line above, scoped to this one comment line.
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
