/**
 * 條件 95 (`work/reviews/2026-08-19-C5-Kelly-文案批審.md` 第十輪批審): "前端出現
 * Kelly 限定語而 BacktestReportView 仍未限定即紅燈" — the two win-rate
 * qualifiers (Kelly-side 「勝率（依完整回合計）」, backend-owned and shipped
 * from `app/api/kelly_wording.py`; the fill-level side's own
 * 「勝率（依結算筆數計）」, `app/backtest/BacktestReportView.tsx`) must land or
 * revert **together**, because they exist to keep two different-denominator
 * numbers with the same underlying Chinese name from reading as one metric on
 * a screen where both are reachable (the backtest page is where the "import
 * into Kelly" action lives).
 *
 * **Design (this lane's choice, K4c-2)**: the Kelly-side qualifier is backend
 * copy — it never appears as a frontend source literal at all (分歧① required
 * 2 bans the bare term from every frontend file, so this app cannot mint a
 * static string equal to it, and cannot render it except by echoing an API
 * field). A test asserting "if the Kelly string appears anywhere in the
 * frontend, the BacktestReportView string must too" is therefore vacuously
 * true by construction on the *source* side (the Kelly string never appears
 * in source) and would only be meaningful against a live API mock or a
 * running render — which this repo cannot do (`vitest.config.ts`: no
 * `@testing-library/react`/jsdom yet). Mocking the API response to fabricate
 * "the frontend renders a Kelly-qualified win rate" would itself violate
 * 落地條件 3/約束 21 (the front end must never *decide* to show this string;
 * only the backend's own `KellyDisclosuresView.original_values.win_rate_label`
 * controls that, and it is always backend-sourced whenever it appears at
 * all).
 *
 * So the guard that is actually checkable *today*, without a DOM, is the
 * other half of the pairing requirement, made mechanical: **the
 * BacktestReportView side can never silently regress to its unqualified
 * form**, which is the one the qualifier exists to move away from and the one
 * a reviewer re-reading only the Kelly side's diff would not notice reverting.
 * `componentWordingScan.test.ts`'s `ALLOWED_SOURCE_CONTEXTS` entry for this
 * file already pins the qualified line verbatim (a drift there fails that
 * suite); this file adds the *reverse* assertion — the bare, unqualified
 * object literal must never reappear — and the backend pairing itself
 * (`app/api/kelly.py` `KellyDisclosuresView.original_values.win_rate_label ==
 * wording.KELLY_WIN_RATE_ROUND_TRIP_QUALIFIER`, `tests/test_api_kelly_disclosures
 * .py`) is asserted server-side, where the string is actually produced. Both
 * conditions failing independently is what "either side reverts, a test goes
 * red" means in practice for a codebase where one side of the pair can never
 * be a frontend literal.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

describe("BacktestReportView.tsx — 條件 95 半邊(反向斷言,不得回退為無限定語版本)", () => {
  const absolutePath = fileURLToPath(new URL("../../backtest/BacktestReportView.tsx", import.meta.url));
  const source = readFileSync(absolutePath, "utf-8");

  it("carries the qualified label exactly once", () => {
    const matches = source.match(/勝率（依結算筆數計）/g) ?? [];
    expect(matches).toHaveLength(1);
  });

  it("never carries the bare, unqualified win-rate row literal (the pre-任務6 form)", () => {
    expect(source).not.toContain('label: "勝率",');
  });

  it("the bare two-character term never appears outside the one qualified label", () => {
    // Every occurrence of the term must be immediately followed by the
    // qualifier's opening full-width parenthesis — i.e. it never stands
    // alone.
    const bareOccurrences = source.match(/勝率(?!（依結算筆數計）)/g) ?? [];
    expect(bareOccurrences).toEqual([]);
  });
});
