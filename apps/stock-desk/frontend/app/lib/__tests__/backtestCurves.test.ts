import { describe, expect, it } from "vitest";
import { INDEX_BASE, buildEquityCurveSeries, indexSegment, isEquityCurveEmpty } from "../backtestCurves";
import type { WalkForwardCurves } from "../types";

const CURVES: WalkForwardCurves = {
  in_sample: {
    dates: ["2025-01-02", "2025-01-03", "2025-01-06"],
    strategy: [1_000_000, 1_050_000, 1_020_000],
    buy_and_hold: [1_000_000, 990_000, 1_100_000],
    drawdown: [0, 0, -0.0285714],
  },
  out_of_sample: {
    dates: ["2025-01-07", "2025-01-08"],
    strategy: [1_020_000, 1_122_000],
    buy_and_hold: [1_000_000, 1_010_000],
    drawdown: [0, 0],
  },
  split_date: "2025-01-07",
  trades: [
    { date: "2025-01-03", side: "buy", price: 100 },
    { date: "2025-01-08", side: "sell", price: 110 },
  ],
};

describe("backtestCurves — 每段各自指數化 100", () => {
  it("re-bases both series to 100 at each segment's own first bar (matches the per-segment table)", () => {
    const s = buildEquityCurveSeries(CURVES);
    expect(s.inSample.strategy.map((p) => p.value)).toEqual([100, 105, 102]);
    expect(s.inSample.buyAndHold.map((p) => p.value)).toEqual([100, 99, 110.00000000000001]);
    // The out-of-sample strategy restarts at 100 even though its equity continues from in-sample.
    expect(s.outOfSample.strategy.map((p) => p.value)).toEqual([100, 110.00000000000001]);
    expect(s.outOfSample.buyAndHold.map((p) => p.value)).toEqual([100, 101]);
    expect(INDEX_BASE).toBe(100);
  });

  it("carries dates through unchanged and converts drawdown to percentage points", () => {
    const seg = indexSegment(CURVES.in_sample);
    expect(seg.strategy.map((p) => p.time)).toEqual(CURVES.in_sample.dates);
    expect(seg.drawdown.map((p) => p.value).slice(0, 2)).toEqual([0, 0]);
    expect(seg.drawdown[2]!.value).toBeCloseTo(-2.85714, 5);
  });

  it("split date and trade count pass through; markers are never derived from trades", () => {
    const s = buildEquityCurveSeries(CURVES);
    expect(s.splitDate).toBe("2025-01-07");
    expect(s.tradeCount).toBe(2);
    expect(Object.keys(s)).toEqual(["inSample", "outOfSample", "splitDate", "tradeCount"]);
  });

  it("a degenerate first value (0 / NaN) yields an empty series rather than Infinity", () => {
    expect(indexSegment({ dates: ["a", "b"], strategy: [0, 5], buy_and_hold: [Number.NaN, 1], drawdown: [] })).toEqual({
      strategy: [],
      buyAndHold: [],
      drawdown: [],
      drawable: false,
      absent: false,
    });
  });

  it("REQ-2/REQ-5: a segment is drawable only when BOTH series have >= 2 points; empty when neither segment is", () => {
    const both = buildEquityCurveSeries(CURVES);
    expect(both.inSample.drawable).toBe(true);
    expect(both.outOfSample.drawable).toBe(true);
    expect(isEquityCurveEmpty(both)).toBe(false);

    // One bar in the out-of-sample window: re-based it would sit at 100/100 and read as "identical" — not drawn.
    const oneBarOut: WalkForwardCurves = {
      ...CURVES,
      out_of_sample: { dates: ["2025-01-07"], strategy: [1], buy_and_hold: [1], drawdown: [0] },
    };
    const s1 = buildEquityCurveSeries(oneBarOut);
    expect(s1.outOfSample.drawable).toBe(false);
    expect(s1.outOfSample.absent).toBe(false);
    expect(isEquityCurveEmpty(s1)).toBe(false);

    // Buy & Hold missing (degenerate first close) with a full strategy series: still not drawable.
    const noBh: WalkForwardCurves = {
      ...CURVES,
      in_sample: { ...CURVES.in_sample, buy_and_hold: [] },
      out_of_sample: { dates: [], strategy: [], buy_and_hold: [], drawdown: [] },
      split_date: null,
    };
    const s2 = buildEquityCurveSeries(noBh);
    expect(s2.inSample.drawable).toBe(false);
    expect(s2.outOfSample.absent).toBe(true);
    expect(isEquityCurveEmpty(s2)).toBe(true);
  });
});
