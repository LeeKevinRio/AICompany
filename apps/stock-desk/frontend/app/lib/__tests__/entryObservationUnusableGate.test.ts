import { describe, expect, it } from "vitest";
import { evaluateDailyBarsUsability } from "../dailyBarsUsability";
import type { DailyBarsUsability } from "../dailyBarsUsability";
import { evaluateEntryObservation } from "../entryObservation";
import type { ConditionId, ConditionResult } from "../entryObservation";
import { computeKeyLevels } from "../keyLevels";
import type { AdviceCard, Bar, IndicatorResult, SignalsPayload, SignalsTechnicalBlock } from "../types";

/**
 * RC-862 / RC-863: the single fail-closed gate on the daily-bar verdict.
 * Worst-case fixtures on purpose: backend payloads are perfectly healthy
 * (signals ok with RSI 50 / z 0.5, advice ok, held, no rule matched), so any
 * "met" or any printed number can only come from a missing gate.
 */

function bar(i: number, over: Partial<Bar> = {}): Bar {
  const base = 100 + i * 0.1;
  return {
    date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    open: String(base),
    high: String(base + 1),
    low: String(base - 1),
    close: String(base),
    volume: 1000,
    currency: "TWD",
    source: "test",
    ...over,
  };
}

/** 80 healthy bars, then one field of one bar replaced. `at` is an index into the series. */
function barsWith(at: number | null, over: Partial<Bar> = {}): Bar[] {
  const out = Array.from({ length: 80 }, (_, i) => bar(i));
  if (at !== null) out[at] = bar(at, over);
  return out;
}

const CLEAN_BARS = barsWith(null);
const BAD_LATEST_CLOSE = barsWith(79, { close: "0" });
const BAD_LATEST_LOW = barsWith(79, { low: "0" });
const BAD_EARLIER_CLOSE = barsWith(10, { close: "0" });
const BAD_EARLIER_HIGH = barsWith(10, { high: "-1" });

function signals(rsi: number, z: number): SignalsPayload {
  const ok = (last: Record<string, number | null>): IndicatorResult =>
    ({ status: "ok", last, name: "", params: {}, dates: [], series: {}, inputs_used: {}, as_of: null, source: null }) as unknown as IndicatorResult;
  return {
    symbol: "2330",
    bar_count: 80,
    as_of: null,
    source: null,
    technical: { rsi: ok({ rsi }), volume_zscore: ok({ zscore: z }) } as Partial<SignalsTechnicalBlock> as SignalsTechnicalBlock,
  };
}

/** Held, nothing matched: the reassuring case the gate exists to stop. */
const NO_HIT_ADVICE = { matched_rules: [], direction_weights: [] } as unknown as AdviceCard;
const CLEAN_RULE_ADVICE = {
  matched_rules: [{ id: "r0", name: "", action: "hold", weight: 1, weight_meaning: "", explanation: "", invalidation: null }],
  direction_weights: [{ direction: "neutral", actions: ["hold"], weight: 1 }],
} as unknown as AdviceCard;

/** The page's wiring: the verdict and the levels are both derived from the same loaded bars. */
function evaluateFor(bars: Bar[] | null, held: boolean | null = true, advice: AdviceCard | null = NO_HIT_ADVICE) {
  return evaluateEntryObservation(
    bars === null ? null : computeKeyLevels(bars),
    signals(50, 0.5),
    advice,
    held,
    bars === null ? null : evaluateDailyBarsUsability(bars),
  );
}

function byId(conditions: readonly ConditionResult[], id: ConditionId): ConditionResult {
  const found = conditions.find((c) => c.id === id);
  if (found === undefined) throw new Error(`missing condition ${id}`);
  return found;
}

const UNAVAILABLE = { status: "unavailable", observed: null, reference: null } as const;

describe("RC-862 point 9: the gate's range equals computeKeyLevels' whole-batch refusal", () => {
  const cases: [string, Bar[]][] = [
    ["(a) latest close 0", BAD_LATEST_CLOSE],
    ["(b) latest low 0, close fine", BAD_LATEST_LOW],
    ["(c) earlier close 0", BAD_EARLIER_CLOSE],
    ["(d) earlier high -1", BAD_EARLIER_HIGH],
    ["non-finite close", barsWith(40, { close: "NaN" })],
  ];
  for (const [name, bars] of cases) {
    it(`${name}: shared verdict is unusable and computeKeyLevels refuses the batch`, () => {
      expect(evaluateDailyBarsUsability(bars).status).toBe("unusable");
      expect(computeKeyLevels(bars)).toBeNull();
    });
  }
  it("clean bars: shared verdict is usable and computeKeyLevels computes", () => {
    expect(evaluateDailyBarsUsability(CLEAN_BARS).status).toBe("usable");
    expect(computeKeyLevels(CLEAN_BARS)).not.toBeNull();
  });
});

describe("RC-862 rules condition: unusable daily bars => always unavailable", () => {
  const cases: [string, Bar[]][] = [
    ["(a) latest close 0", BAD_LATEST_CLOSE],
    ["(b) latest low 0", BAD_LATEST_LOW],
    ["(c) earlier close 0", BAD_EARLIER_CLOSE],
    ["(d) earlier high -1", BAD_EARLIER_HIGH],
  ];
  for (const [name, bars] of cases) {
    it(`${name}: held + empty matched_rules => unavailable with observed and reference null`, () => {
      const rules = byId(evaluateFor(bars).conditions, "rules");
      expect(rules).toEqual({ id: "rules", ...UNAVAILABLE });
    });
    it(`${name}: held + a clean non-defensive rule, and not held / undetermined => unavailable`, () => {
      expect(byId(evaluateFor(bars, true, CLEAN_RULE_ADVICE).conditions, "rules")).toEqual({ id: "rules", ...UNAVAILABLE });
      expect(byId(evaluateFor(bars, false).conditions, "rules")).toEqual({ id: "rules", ...UNAVAILABLE });
      expect(byId(evaluateFor(bars, null).conditions, "rules")).toEqual({ id: "rules", ...UNAVAILABLE });
    });
  }

  it("(e) bars not loaded (verdict null, e.g. error / insufficient_data / not ok): unavailable", () => {
    expect(byId(evaluateFor(null).conditions, "rules")).toEqual({ id: "rules", ...UNAVAILABLE });
    // Even when levels happen to be present, a missing verdict keeps the gate shut.
    const withLevelsNoVerdict = evaluateEntryObservation(computeKeyLevels(CLEAN_BARS), signals(50, 0.5), NO_HIT_ADVICE, true, null);
    expect(byId(withLevelsNoVerdict.conditions, "rules")).toEqual({ id: "rules", ...UNAVAILABLE });
  });

  it("(e) RC-872 point 1: ok envelope with an empty array (verdict usable, zero bars) => unavailable", () => {
    expect(evaluateDailyBarsUsability([]).status).toBe("usable");
    expect(byId(evaluateFor([]).conditions, "rules")).toEqual({ id: "rules", ...UNAVAILABLE });
  });

  it("fail-closed: an unknown or missing verdict value never opens the gate", () => {
    const levels = computeKeyLevels(CLEAN_BARS);
    for (const verdict of [undefined, { status: "gap" }, { status: "" }, {}] as unknown[]) {
      const result = evaluateEntryObservation(levels, signals(50, 0.5), NO_HIT_ADVICE, true, verdict as DailyBarsUsability | null);
      expect(byId(result.conditions, "rules"), JSON.stringify(verdict)).toEqual({ id: "rules", ...UNAVAILABLE });
    }
  });

  it("(f) usable bars: unchanged — held with no defensive hit is met, not held / undetermined is unavailable", () => {
    const met = byId(evaluateFor(CLEAN_BARS).conditions, "rules");
    expect(met).toEqual({ id: "rules", status: "met", observed: 0, reference: null });
    expect(byId(evaluateFor(CLEAN_BARS, true, CLEAN_RULE_ADVICE).conditions, "rules").status).toBe("met");
    expect(byId(evaluateFor(CLEAN_BARS, false).conditions, "rules")).toEqual({ id: "rules", ...UNAVAILABLE });
    expect(byId(evaluateFor(CLEAN_BARS, null).conditions, "rules")).toEqual({ id: "rules", ...UNAVAILABLE });
  });

  it("backend statuses are not a bad-value signal: an ok advice on bad bars is still gated, a null advice stays unavailable", () => {
    expect(byId(evaluateFor(BAD_EARLIER_CLOSE, true, NO_HIT_ADVICE).conditions, "rules").status).toBe("unavailable");
    expect(byId(evaluateFor(CLEAN_BARS, true, null).conditions, "rules").status).toBe("unavailable");
  });
});
