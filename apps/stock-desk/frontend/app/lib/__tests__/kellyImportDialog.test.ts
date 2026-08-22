/**
 * Unit tests for `KellyImportDialog.tsx`'s pure decision logic
 * (`decideImportTrigger`, `buildKellyImportRequest`) — this repo has no
 * `@testing-library/react`/jsdom yet (`vitest.config.ts`'s own doc comment),
 * so these test the extracted functions directly rather than rendering the
 * dialog, the same trade-off `EditAlertRuleModal.test.ts`'s coverage of
 * `decideAlertRuleSubmit` makes. DOM-level assertions (mutual exclusion of
 * the two views, the cancel button not calling the endpoint) are qa-e2e's to
 * verify on a real page — see the K4c-2 handoff report.
 */

import { describe, expect, it } from "vitest";
import {
  buildKellyImportRequest,
  decideImportTrigger,
  type SpecFormState,
} from "../../settings/KellyImportDialog";
import type { KellyOverwriteNoticeView } from "../types";

// Fixture text is deliberately synthetic (ASCII placeholders), not a retyped
// approved Kelly sentence: `decideImportTrigger` only branches on whether
// `overwrite_notice` is `null`, never on its wording, so a real sentence buys
// this test nothing and only couples it to exact copy this lane does not own.
const NOTICE: KellyOverwriteNoticeView = {
  title: "TEST_TITLE",
  body: ["TEST_BODY_1", "TEST_BODY_2", "TEST_BODY_3"],
  confirm_label: "TEST_CONFIRM",
  cancel_label: "TEST_CANCEL",
};

describe("decideImportTrigger — 條件 73 四格", () => {
  it("cell absent/backtest (overwrite_notice: null): runs directly, no dialog", () => {
    expect(decideImportTrigger(null)).toEqual({ kind: "run" });
  });

  it("cell manual/backtest_overridden (overwrite_notice non-null): opens the dialog with that exact notice", () => {
    expect(decideImportTrigger(NOTICE)).toEqual({ kind: "open-dialog", notice: NOTICE });
  });

  it("never invents a notice: the dialog decision's `notice` is reference-equal to the input", () => {
    const decision = decideImportTrigger(NOTICE);
    if (decision.kind !== "open-dialog") throw new Error("expected open-dialog");
    expect(decision.notice).toBe(NOTICE);
  });
});

describe("buildKellyImportRequest — 列管 L11 (every field is on-screen, none invented)", () => {
  const spec: SpecFormState = {
    strategy: "breakout",
    instrument_type: "etf",
    start: "2024-01-01",
    end: "2026-01-01",
    train_size: "252",
    test_size: "63",
  };

  it("maps the symbol/market the caller passed and every spec-form field, numeric fields coerced", () => {
    expect(buildKellyImportRequest("2330", "TW", spec)).toEqual({
      symbol: "2330",
      market: "TW",
      strategy: "breakout",
      instrument_type: "etf",
      start: "2024-01-01",
      end: "2026-01-01",
      initial_cash: 1_000_000,
      train_size: 252,
      test_size: 63,
    });
  });

  it("條件 75: the request never carries a measured win_rate/payoff_ratio/f_star field — only backtest parameters", () => {
    const request = buildKellyImportRequest("2330", "TW", spec) as unknown as Record<string, unknown>;
    for (const forbidden of ["win_rate", "payoff_ratio", "f_star", "p", "b"]) {
      expect(request).not.toHaveProperty(forbidden);
    }
  });
});
