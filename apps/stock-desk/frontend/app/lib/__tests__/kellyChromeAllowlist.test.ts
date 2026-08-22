/**
 * 條件 106 (第十四輪, `work/reviews/2026-08-19-C5-Kelly-文案批審.md`): the round
 * approved a closed set of structural chrome literals across
 * `KellyInputsSection.tsx` / `KellyManualInputForm.tsx` / `KellyImportDialog
 * .tsx` (and, since 第十五輪 revived the delete control in a new sibling file,
 * `KellyDeleteDialog.tsx`) under a three-part test (chrome 判準): (i) verbatim-or-subject-only
 * reuse of an already-shipped convention, (ii) no methodology/probability/
 * data-quality/consequence/advice claim, (iii) context unchanged from that
 * convention's own approval. `KellyDisclosuresPanel.tsx` is not in this file:
 * it still carries **zero** Han characters at all — see
 * `kellyDisclosuresPanel.test.ts` — because every sentence there is Kelly-
 * disclosure content, never chrome.
 *
 * This suite makes the round's own finding mechanical, exactly as it asked:
 * "本輪核可 chrome 字面納入前端逐行 allowlist（檔+行+慣例出處）", and any Han
 * character in these three files that is **not** in the allowlist below fails
 * the build — a chrome exemption can never again slip in silently the way
 * `KellyImportDialog.tsx`'s own `"未知錯誤"` fallback did before this round
 * named it (條件 106's explicit instruction: "chrome 豁免不得默默例外").
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { chineseLiteralsOutsideAllowlist } from "./wordingScanHelpers";

/**
 * (檔, 行, 字面, 慣例出處) — 條件 106 要求的粒度。`context` is the exact
 * rendered-text substring the allowlist masks; `origin` is retyped into each
 * `it()`'s own title (not stored separately) so a failing assertion's name is
 * self-explanatory without cross-referencing this comment block.
 */
const ALLOWLIST: Record<string, readonly string[]> = {
  "../../settings/KellyInputsSection.tsx": [
    // Longer/more specific contexts listed *before* shorter ones they
    // overlap with ("Kelly 輸入" is a substring of both the heading and the
    // L118 error label below) — `chineseLiteralsOutsideAllowlist` masks in
    // array order, so the specific match must be consumed first or the
    // shorter entry would eat it and break the longer entry's own lookup.
    //
    // L118 — ErrorPanel label prop, 逐字同構 the "無法載入 X" pattern already
    // shipped across this app's other `ErrorPanel`/`isError` call sites
    // (e.g. settings/page.tsx's own "無法載入設定").
    'label="無法載入 Kelly 輸入"',
    // L73 — 條件 107's own guidance sentence (see the dedicated pairing test
    // below); listed here too so this file's overall scan has no gap.
    "第 5 條「分數 Kelly 部位上限」使用的 win_rate／payoff_ratio 輸入：手動輸入，或從一次回測帶入。",
    // L71 — section heading, same register as every other settings section's
    // own <h2> (NetWorthSection.tsx "帳戶總淨值" etc.), 條件 106 准.
    "Kelly 輸入",
    // L79/L92 — field labels, 逐字同構 ManualAddForm.tsx's own FIELD_LABELS
    // ("股票代號"/"市場" for the same symbol/market picker fields).
    "股票代號",
    "市場",
    // L87 — SymbolCombobox placeholder, 逐字同構 every other symbol picker in
    // this app (ManualAddForm.tsx, BacktestForm.tsx: `placeholder="例如 2330"`).
    'placeholder="例如 2330"',
    // L111 — submit-a-lookup button, no prior "查詢" button exists verbatim
    // elsewhere in this app but the word carries no methodology/advice
    // content (chrome 判準 (ii)) and 條件 106 准 this字面 explicitly.
    "查詢",
  ],
  "../../settings/KellyManualInputForm.tsx": [
    // L149 — submit button, 逐字同構 every other settings-page submit button's
    // pending/idle pair (NetWorthSection.tsx "更新中…"/"更新帳戶總淨值" shape;
    // subject-only difference per chrome 判準 (i)).
    'updateMutation.isPending ? "儲存中…" : "儲存"',
  ],
  "../../settings/KellyImportDialog.tsx": [
    // The mini backtest-spec form's own field labels (line numbers shift as
    // the file grows, e.g. B4's `initial_cash` field — matched by literal
    // content, not position), 逐字同構 BacktestForm.tsx's own #bt-strategy/
    // #bt-instrument/#bt-start/#bt-end labels (same four words, same fields,
    // same convention).
    "策略",
    "類型",
    "開始日期",
    "結束日期",
    // `ImportRefusalPanel`'s generic error fallback, 逐字同構 `ErrorPanel.tsx`/
    // every other `error instanceof ApiError ? error.message : "未知錯誤"`
    // call site in this app (12+ 慣例出處 per 條件 106's own count). 條件 106
    // explicitly named this line as the one chrome exemption that must be
    // recorded rather than pass silently.
    '"未知錯誤"',
  ],
  "../../settings/KellyDeleteDialog.tsx": [
    // The delete trigger's own button label, 條件 106 第十四輪 chrome 判準 "准"
    // (listed there among "「查詢」「儲存」「刪除」字面本身") — the
    // *confirmation dialog's* content was gated behind 條件 109/110/112 (now
    // resolved, 第十五輪), but this bare trigger-button word was never
    // withheld.
    "刪除",
    // Generic error fallback, 逐字同構 the same convention `kellyImportDialog
    // .tsx`'s `ImportRefusalPanel` and 12+ other call sites across this app
    // already use.
    '"未知錯誤"',
  ],
};

describe("Kelly chrome 逐行 allowlist（條件 106）— 未列入即紅燈", () => {
  for (const [relativePath, allowedContexts] of Object.entries(ALLOWLIST)) {
    it(`${relativePath}: every Han character is inside an allowlisted chrome context`, () => {
      const absolutePath = fileURLToPath(new URL(relativePath, import.meta.url));
      const source = readFileSync(absolutePath, "utf-8");
      expect(chineseLiteralsOutsideAllowlist(source, allowedContexts)).toEqual([]);
    });
  }
});
