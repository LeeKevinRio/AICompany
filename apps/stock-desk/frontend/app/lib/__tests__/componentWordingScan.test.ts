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
  //
  // 註: `BacktestReportView.tsx` 本批也加了一句常駐警語(D2 item 4)，但該檔既有
  // 的 `METRIC_ROWS` 「勝率」欄位標籤(回測歷史績效統計量,非新增)會被本掃描的
  // 逐字比對誤殺——與 risk-final-review.md 已接受的「勝率→歷史交易的獲勝比例」
  // 屬同一類語境(承認/描述已發生的歷史結果,非機率洗白),但改寫該標籤或调整
  // 掃描例外清單都超出本批派工範圍,故不將該檔納入掃描,留待下次動到回測頁措辭
  // 時一併處理。
  "../../settings/DirectorySection.tsx",
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
] as const;

describe("component source scan — §1.3 banned-term coverage on hard-coded JSX text", () => {
  for (const relativePath of SCANNED_FILES) {
    const absolutePath = fileURLToPath(new URL(relativePath, import.meta.url));
    const source = readFileSync(absolutePath, "utf-8");

    it(`${relativePath}: contains none of the §1.3 banned terms`, () => {
      assertNoForbiddenTerms(source, FRONTEND_FORBIDDEN_TERMS, relativePath);
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
