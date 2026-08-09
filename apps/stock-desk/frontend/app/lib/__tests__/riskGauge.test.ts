import { describe, expect, it } from "vitest";
import {
  buildLimitGaugeViewModel,
  limitBarWidthPercent,
  shouldShowLimitBar,
} from "../riskGauge";
import type { BookLimitCheck } from "../types";

function makeCheck(overrides: Partial<BookLimitCheck>): BookLimitCheck {
  return {
    index: 1,
    limit_id: "single_position_weight",
    name: "單一標的佔比上限",
    status: "passed",
    observed: 0.05,
    threshold: 0.2,
    detail: "detail",
    worst_symbol: "2330",
    evaluated_count: 3,
    excluded: [],
    ...overrides,
  };
}

describe("shouldShowLimitBar", () => {
  it("never draws a bar when the cap is not_evaluable, even with a real threshold", () => {
    expect(shouldShowLimitBar("not_evaluable", 0.2)).toBe(false);
  });

  it("does not draw a bar when threshold is null (defensive, cap 5)", () => {
    expect(shouldShowLimitBar("passed", null)).toBe(false);
    expect(shouldShowLimitBar("violated", null)).toBe(false);
  });

  it("does not draw a bar when threshold is zero or negative", () => {
    expect(shouldShowLimitBar("passed", 0)).toBe(false);
    expect(shouldShowLimitBar("passed", -0.1)).toBe(false);
  });

  it("draws a bar for a passed or violated cap with a real positive threshold", () => {
    expect(shouldShowLimitBar("passed", 0.2)).toBe(true);
    expect(shouldShowLimitBar("violated", 0.2)).toBe(true);
  });
});

describe("limitBarWidthPercent", () => {
  it("is 0 when observed is null", () => {
    expect(limitBarWidthPercent(null, 0.2)).toBe(0);
  });

  it("is 0 when threshold is null or non-positive", () => {
    expect(limitBarWidthPercent(0.1, null)).toBe(0);
    expect(limitBarWidthPercent(0.1, 0)).toBe(0);
    expect(limitBarWidthPercent(0.1, -0.5)).toBe(0);
  });

  it("computes the observed/threshold ratio as a percentage", () => {
    expect(limitBarWidthPercent(0.05, 0.2)).toBe(25);
    expect(limitBarWidthPercent(0.1, 0.2)).toBe(50);
  });

  it("clamps at 100 when observed has reached or passed threshold (violated)", () => {
    expect(limitBarWidthPercent(0.2, 0.2)).toBe(100);
    expect(limitBarWidthPercent(0.5, 0.2)).toBe(100);
  });

  it("floors at 0 for a negative observed value", () => {
    expect(limitBarWidthPercent(-0.1, 0.2)).toBe(0);
  });
});

describe("buildLimitGaugeViewModel", () => {
  it("a not_evaluable check never shows a bar, regardless of excluded symbols", () => {
    const check = makeCheck({
      status: "not_evaluable",
      observed: null,
      threshold: null,
      worst_symbol: null,
      evaluated_count: 0,
      excluded: [
        { symbol: "2330", market: "TW", reason: "no unvalued reason" },
        { symbol: "AAPL", market: "US", reason: "another reason" },
      ],
    });
    const view = buildLimitGaugeViewModel(check);
    expect(view.showBar).toBe(false);
    expect(view.barWidthPercent).toBe(0);
    expect(view.hasExcluded).toBe(true);
    expect(view.excludedCount).toBe(2);
  });

  it("a not_evaluable check with a borrowed (non-null) threshold still shows no bar", () => {
    // Mirrors app/advice/book_limits.py::_aggregate: the empty-comparable
    // branch borrows `baseline.threshold` even though status is
    // not_evaluable — this must not accidentally satisfy shouldShowLimitBar.
    const check = makeCheck({ status: "not_evaluable", observed: null, threshold: 0.2 });
    const view = buildLimitGaugeViewModel(check);
    expect(view.showBar).toBe(false);
    expect(view.barWidthPercent).toBe(0);
  });

  it("a passed check with no excluded symbols shows a bar and reports zero exclusions", () => {
    const check = makeCheck({ status: "passed", observed: 0.1, threshold: 0.2, excluded: [] });
    const view = buildLimitGaugeViewModel(check);
    expect(view.showBar).toBe(true);
    expect(view.barWidthPercent).toBe(50);
    expect(view.hasExcluded).toBe(false);
    expect(view.excludedCount).toBe(0);
  });

  it("a violated check with a null threshold (defensive) still shows no bar", () => {
    const check = makeCheck({ status: "violated", observed: 0.3, threshold: null });
    const view = buildLimitGaugeViewModel(check);
    expect(view.showBar).toBe(false);
    expect(view.barWidthPercent).toBe(0);
  });
});
