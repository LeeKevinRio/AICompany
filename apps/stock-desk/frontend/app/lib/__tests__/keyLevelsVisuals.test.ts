import { describe, expect, it } from "vitest";
import type { KeyLevels } from "../keyLevels";
import {
  GAUGE_ZONE_BANDS,
  buildLadderViewModel,
  gaugeMarkerLeftPct,
  ladderBarGeometry,
} from "../keyLevelsVisuals";

function levels(overrides: Partial<KeyLevels> = {}): KeyLevels {
  return {
    close: 100,
    closeDate: "2026-09-05",
    rangeHigh: 130,
    rangeLow: 70,
    rangePositionPct: 50,
    ma20: 98,
    ma60: 95,
    ma60DeviationPct: 5.26,
    recentLow60: 85,
    atr14: 3,
    anchorPrice: 100,
    anchoredOnCost: false,
    stopAtr: 94,
    stopFixedPct: 92,
    stopSuggested: 94,
    targetFixedPct: 120,
    target2R: 112,
    barCount: 300,
    rangeBarCount: 252,
    rangeUnavailableCause: null,
    ...overrides,
  };
}

describe("gauge", () => {
  it("bands cover 0–100 contiguously with the 30/70 thresholds", () => {
    expect(GAUGE_ZONE_BANDS.map((b) => [b.fromPct, b.toPct])).toEqual([
      [0, 30],
      [30, 70],
      [70, 100],
    ]);
  });

  it("marker offset is clamped and NaN-safe", () => {
    expect(gaugeMarkerLeftPct(41.4)).toBe(41.4);
    expect(gaugeMarkerLeftPct(-3)).toBe(0);
    expect(gaugeMarkerLeftPct(140)).toBe(100);
    expect(gaugeMarkerLeftPct(Number.NaN)).toBe(0);
  });
});

describe("ladder", () => {
  it("sorts rungs highest first and tags the headline stop/target", () => {
    const vm = buildLadderViewModel(levels(), "close-not-held");
    expect(vm.rungs.map((r) => r.id)).toEqual([
      "target-fixed",
      "target-2r",
      "anchor",
      "ma20",
      "ma60",
      "stop-atr",
      "stop-fixed",
      "recent-low60",
    ]);
    const byId = Object.fromEntries(vm.rungs.map((r) => [r.id, r]));
    expect(byId["target-2r"]!.isHeadline).toBe(true);
    expect(byId["target-fixed"]!.isHeadline).toBe(false);
    expect(byId["stop-atr"]!.isHeadline).toBe(true);
    expect(byId["stop-fixed"]!.isHeadline).toBe(false);
    expect(byId["anchor"]!.distancePct).toBe(0);
    expect(byId["target-fixed"]!.distancePct).toBeCloseTo(20);
    expect(byId["stop-fixed"]!.distancePct).toBeCloseTo(-8);
    expect(vm.maxAbsDistancePct).toBeCloseTo(20);
  });

  it("drops the close rung when the anchor IS the close, keeps it when anchored on cost", () => {
    expect(buildLadderViewModel(levels(), "close-unknown").rungs.some((r) => r.id === "close")).toBe(false);
    const held = buildLadderViewModel(levels({ anchorPrice: 90, anchoredOnCost: true }), "cost");
    const close = held.rungs.find((r) => r.id === "close");
    expect(close).toBeDefined();
    expect(close!.distancePct).toBeCloseTo((100 / 90 - 1) * 100);
  });

  it("never invents a rung for a null level, and moves the headline tag to the fixed stop without ATR", () => {
    const vm = buildLadderViewModel(
      levels({ ma20: null, ma60: null, recentLow60: null, atr14: null, stopAtr: null, stopSuggested: 92, target2R: 116 }),
      "close-not-held",
    );
    expect(vm.rungs.map((r) => r.id)).toEqual(["target-fixed", "target-2r", "anchor", "stop-fixed"]);
    expect(vm.rungs.find((r) => r.id === "stop-fixed")!.isHeadline).toBe(true);
  });

  it("stable order on equal prices (declaration order wins)", () => {
    const vm = buildLadderViewModel(levels({ ma20: 94, stopAtr: 94 }), "close-not-held");
    const ids = vm.rungs.map((r) => r.id);
    expect(ids.indexOf("ma20")).toBeLessThan(ids.indexOf("stop-atr"));
  });

  it("bar geometry: above → grows right from 50%, below → grows left, anchor → nothing", () => {
    expect(ladderBarGeometry(20, 20)).toEqual({ leftPct: 50, widthPct: 50 });
    expect(ladderBarGeometry(-10, 20)).toEqual({ leftPct: 25, widthPct: 25 });
    expect(ladderBarGeometry(0, 20)).toEqual({ leftPct: 50, widthPct: 0 });
    expect(ladderBarGeometry(5, 0)).toEqual({ leftPct: 50, widthPct: 0 });
    // Never overflows the half track even if a caller passes a stale max.
    expect(ladderBarGeometry(40, 20).widthPct).toBe(50);
  });
});
