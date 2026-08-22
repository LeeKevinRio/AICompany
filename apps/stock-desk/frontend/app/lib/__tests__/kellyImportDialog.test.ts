/**
 * Unit tests for `KellyImportDialog.tsx`'s pure/pure-ish decision logic
 * (`decideImportTrigger`, `resolveImportTriggerDecision`,
 * `buildKellyImportRequest`) — this repo has no `@testing-library/react`/
 * jsdom yet (`vitest.config.ts`'s own doc comment), so these test the
 * extracted functions directly rather than rendering the dialog, the same
 * trade-off `EditAlertRuleModal.test.ts`'s coverage of
 * `decideAlertRuleSubmit` makes. DOM-level assertions (mutual exclusion of
 * the two views, the cancel button not calling the endpoint, the dialog
 * closing on B6's `onError`) are qa-e2e's to verify on a real page — see the
 * K4c-2 handoff report.
 */

import { describe, expect, it } from "vitest";
import {
  buildKellyImportRequest,
  decideImportTrigger,
  resolveImportTriggerDecision,
  type SpecFormState,
} from "../../settings/KellyImportDialog";
import type { KellyInputDisclosuresView, KellyOverwriteNoticeView } from "../types";

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

/**
 * B3 (qa 補審 2026-08-22, `work/reviews/2026-08-22-C5-K4c2-qa補審.md`): the
 * failure path this suite exists to pin — a rejected `fetchDisclosures()`
 * must abort, never fall back to a stale variant that could run an import
 * with no dialog (defeating 條件 74 in the one case it exists to prevent).
 */
function freshView(overwriteNotice: KellyOverwriteNoticeView | null): KellyInputDisclosuresView {
  return {
    kelly_input: null,
    as_of: "2026-08-22T00:00:00+00:00",
    disclosures: {
      import_trigger_label: "TEST_TRIGGER",
      freshness_badge_label: "TEST_BADGE",
      source_statement: null,
      source_label: null,
      win_rate_disclosure: null,
      manual_input_disclosure: null,
      manual_input_tooltip: null,
      selection_bias: null,
      walk_forward: null,
      f_star_interval: null,
      effective_cap: null,
      boundary_exclusion: null,
      sample_detail: null,
      original_values: null,
      original_values_entry_label: null,
      original_values_return_label: null,
      overwrite_notice: overwriteNotice,
      delete_notice: null,
      k_observed: 0,
      k_distinct_specs: 0,
    },
  };
}

describe("resolveImportTriggerDecision — B3 (never falls back to a stale variant on failure)", () => {
  it("decides from the freshly fetched overwrite_notice on success", async () => {
    const decision = await resolveImportTriggerDecision(async () => freshView(NOTICE));
    expect(decision).toEqual({ kind: "open-dialog", notice: NOTICE });
  });

  it("decides 'run' when the fresh read says there is nothing to overwrite", async () => {
    const decision = await resolveImportTriggerDecision(async () => freshView(null));
    expect(decision).toEqual({ kind: "run" });
  });

  it("aborts — never runs, never opens a stale dialog — when the fetch rejects", async () => {
    const decision = await resolveImportTriggerDecision(() => Promise.reject(new Error("network")));
    expect(decision).toEqual({ kind: "abort" });
  });

  it("aborts on a rejected fetch even when a caller might otherwise have a cached non-null notice lying around — this function takes no such fallback parameter at all", async () => {
    // The regression this guards: the first draft of this component computed
    // `fresh.data?.disclosures.overwrite_notice ?? disclosures.overwrite_notice`
    // — a `??` fallback to a stale prop. `resolveImportTriggerDecision`'s
    // signature has no second, "fallback" argument for a caller to supply,
    // which is what makes that regression structurally impossible here
    // rather than merely untested.
    const decision = await resolveImportTriggerDecision(() => Promise.reject(new Error("timeout")));
    expect(decision).toEqual({ kind: "abort" });
    expect(decision).not.toEqual({ kind: "run" });
    expect(decision).not.toMatchObject({ kind: "open-dialog" });
  });
});

describe("buildKellyImportRequest — 列管 L11 (every field is on-screen, none invented)", () => {
  const spec: SpecFormState = {
    strategy: "breakout",
    instrument_type: "etf",
    start: "2024-01-01",
    end: "2026-01-01",
    initial_cash: "500000",
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
      initial_cash: 500_000,
      train_size: 252,
      test_size: 63,
    });
  });

  it("B4: initial_cash comes from the (now editable) spec form field, not a hard-coded constant", () => {
    const request = buildKellyImportRequest("2330", "TW", { ...spec, initial_cash: "2000000" });
    expect(request.initial_cash).toBe(2_000_000);
  });

  it("條件 75: the request never carries a measured win_rate/payoff_ratio/f_star field — only backtest parameters", () => {
    const request = buildKellyImportRequest("2330", "TW", spec) as unknown as Record<string, unknown>;
    for (const forbidden of ["win_rate", "payoff_ratio", "f_star", "p", "b"]) {
      expect(request).not.toHaveProperty(forbidden);
    }
  });
});
