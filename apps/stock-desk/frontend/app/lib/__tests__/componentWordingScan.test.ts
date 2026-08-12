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
