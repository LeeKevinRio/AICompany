import { describe, expect, it } from "vitest";
import type { KeyLevels } from "../keyLevels";
import type { AdviceCard, IndicatorResult, SignalsPayload, SignalsTechnicalBlock } from "../types";
import { ENTRY_CONDITION_IDS, evaluateEntryObservation, isInObservationBand } from "../entryObservation";

function levels(overrides: Partial<KeyLevels> = {}): KeyLevels {
  return {
    close: 918.66,
    closeDate: "2026-09-01",
    rangeHigh: 1004.44,
    rangeLow: 705.36,
    rangePositionPct: 71.3,
    ma20: 923.44,
    ma60: 906.93,
    ma60DeviationPct: 1.3,
    recentLow60: 844.38,
    atr14: 17.54,
    anchorPrice: 895.44,
    anchoredOnCost: true,
    stopAtr: 860.36,
    stopFixedPct: 823.8,
    stopSuggested: 860.36,
    targetFixedPct: 1074.53,
    target2R: 965.6,
    barCount: 382,
    rangeBarCount: 252,
    rangeUnavailableCause: null,
    ...overrides,
  };
}

function signals(rsi: number | null, z: number | null): SignalsPayload {
  const ok = (last: Record<string, number | null>): IndicatorResult =>
    ({ status: "ok", last, name: "", params: {}, dates: [], series: {}, inputs_used: {}, as_of: null, source: null }) as unknown as IndicatorResult;
  const insufficient = (): IndicatorResult => ({ status: "insufficient_data", last: {} }) as unknown as IndicatorResult;
  return {
    symbol: "2330",
    bar_count: 382,
    as_of: null,
    source: null,
    technical: {
      rsi: rsi === null ? insufficient() : ok({ rsi }),
      volume_zscore: z === null ? insufficient() : ok({ zscore: z }),
    } as Partial<SignalsTechnicalBlock> as SignalsTechnicalBlock,
  };
}

function advice(rules: { action: string }[], directions: { direction: string; actions: string[] }[]): AdviceCard {
  return {
    matched_rules: rules.map((r, i) => ({ id: `r${i}`, name: "", action: r.action, weight: 1, weight_meaning: "", explanation: "" })),
    direction_weights: directions.map((d) => ({ ...d, weight: 1 })),
  } as unknown as AdviceCard;
}

describe("evaluateEntryObservation — 六條固定條件三態", () => {
  it("AC-1 2330 demo: 4 of 6 met; 位階與規則未成立", () => {
    const result = evaluateEntryObservation(
      levels(),
      signals(51.37, 0.7),
      advice([{ action: "add" }, { action: "reduce" }], [
        { direction: "constructive", actions: ["add"] },
        { direction: "defensive", actions: ["reduce"] },
      ]),
      true,
    );
    expect(result.conditions.map((c) => c.id)).toEqual(ENTRY_CONDITION_IDS);
    expect(result.conditions.map((c) => c.status)).toEqual(["unmet", "met", "met", "met", "met", "unmet"]);
    expect(result.metCount).toBe(4);
    expect(result.unmetCount).toBe(2);
    expect(result.unavailableCount).toBe(0);
    expect(result.allUnavailable).toBe(false);
    const byId = Object.fromEntries(result.conditions.map((c) => [c.id, c]));
    expect(byId.range!.observed).toBeCloseTo(71.3);
    expect(byId.trend!.observed).toBeCloseTo(918.66);
    expect(byId.trend!.reference).toBeCloseTo(906.93);
    expect(byId.pullback!.observed).toBeCloseTo((918.66 / 923.44 - 1) * 100);
    expect(byId.rules!.observed).toBe(1);
  });

  it("thresholds are inclusive/exclusive exactly as printed: ≤70%, ±3% inclusive, RSI/z open intervals", () => {
    const at70 = evaluateEntryObservation(levels({ rangePositionPct: 70 }), null, null, true).conditions[0]!;
    expect(at70.status).toBe("met");
    const at3 = evaluateEntryObservation(levels({ close: 103, ma20: 100 }), null, null, true).conditions[2]!;
    expect(at3.status).toBe("met");
    const over3 = evaluateEntryObservation(levels({ close: 103.01, ma20: 100 }), null, null, true).conditions[2]!;
    expect(over3.status).toBe("unmet");
    expect(evaluateEntryObservation(null, signals(70, 0), null, true).conditions[3]!.status).toBe("unmet");
    expect(evaluateEntryObservation(null, signals(69.9, 0), null, true).conditions[3]!.status).toBe("met");
    expect(evaluateEntryObservation(null, signals(50, 2), null, true).conditions[4]!.status).toBe("unmet");
    expect(evaluateEntryObservation(null, signals(50, 1.99), null, true).conditions[4]!.status).toBe("met");
    // close == MA60 is not "above".
    expect(evaluateEntryObservation(levels({ close: 100, ma60: 100 }), null, null, true).conditions[1]!.status).toBe("unmet");
  });

  it("AC-2 short history: 位階 unavailable, denominator stays 6", () => {
    const result = evaluateEntryObservation(
      levels({ rangePositionPct: null, rangeUnavailableCause: "too-few-bars" }),
      signals(50, 0),
      advice([], []),
      true,
    );
    expect(result.conditions[0]!.status).toBe("unavailable");
    expect(result.conditions[0]!.observed).toBeNull();
    expect(result.metCount + result.unmetCount + result.unavailableCount).toBe(6);
    expect(result.unavailableCount).toBe(1);
  });

  it("AC-3 advice unavailable: 規則 unavailable, others evaluated; unknown action also unavailable", () => {
    expect(evaluateEntryObservation(levels(), signals(50, 0), null, true).conditions[5]!.status).toBe("unavailable");
    const unknown = advice([{ action: "mystery" }], [{ direction: "neutral", actions: ["hold"] }]);
    expect(evaluateEntryObservation(levels(), signals(50, 0), unknown, true).conditions[5]!.status).toBe("unavailable");
    const clean = advice([{ action: "hold" }], [{ direction: "neutral", actions: ["hold"] }]);
    expect(evaluateEntryObservation(levels(), signals(50, 0), clean, true).conditions[5]!.status).toBe("met");
  });

  it("RED-1 路徑 (a): not held or undetermined → 規則 unavailable even with a clean card", () => {
    const clean = advice([{ action: "hold" }], [{ direction: "neutral", actions: ["hold"] }]);
    expect(evaluateEntryObservation(levels(), signals(50, 0), clean, false).conditions[5]!.status).toBe("unavailable");
    expect(evaluateEntryObservation(levels(), signals(50, 0), clean, null).conditions[5]!.status).toBe("unavailable");
    expect(evaluateEntryObservation(levels(), signals(50, 0), clean, true).conditions[5]!.status).toBe("met");
  });

  it("all unavailable when nothing is loaded; observation band follows MA20", () => {
    const empty = evaluateEntryObservation(null, null, null, true);
    expect(empty.allUnavailable).toBe(true);
    expect(empty.observationBand).toBeNull();
    const withMa = evaluateEntryObservation(levels({ ma20: 100 }), null, null, true);
    expect(withMa.observationBand).toEqual({ low: 97, high: 103 });
    expect(isInObservationBand(97, withMa.observationBand)).toBe(true);
    expect(isInObservationBand(103.5, withMa.observationBand)).toBe(false);
    expect(isInObservationBand(100, null)).toBe(false);
  });
});
