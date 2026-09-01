import { describe, expect, it } from "vitest";
import { classifyRangeZone, computeKeyLevels } from "../keyLevels";
import type { Bar } from "../types";

function bar(date: string, close: number, high = close + 1, low = close - 1): Bar {
  return {
    date,
    open: String(close),
    high: String(high),
    low: String(low),
    close: String(close),
    volume: 1000,
    currency: "TWD",
    source: "demo_synthetic",
  };
}

/** n flat bars at `price` ending 2026-01-31 (dates only need to be distinct). */
function flatBars(n: number, price: number): Bar[] {
  return Array.from({ length: n }, (_, i) => bar(`2025-${String(i + 1).padStart(3, "0")}`, price));
}

describe("computeKeyLevels — 邊界與退化", () => {
  it("空序列回傳 null", () => {
    expect(computeKeyLevels([], null)).toBeNull();
  });

  it("含非數字 bar 整批拒算（不混算壞資料）", () => {
    const bars = flatBars(70, 100);
    bars[10] = { ...bars[10]!, close: "not-a-number" };
    expect(computeKeyLevels(bars, null)).toBeNull();
  });

  it("bar 數不足時逐欄位退化為 null 而非造數", () => {
    const levels = computeKeyLevels(flatBars(10, 100), null);
    expect(levels).not.toBeNull();
    expect(levels!.ma20).toBeNull();
    expect(levels!.ma60).toBeNull();
    expect(levels!.atr14).toBeNull();
    expect(levels!.rangeHigh).toBeNull();
    expect(levels!.rangePositionPct).toBeNull();
    // 固定百分比停損不需要歷史，仍應存在
    expect(levels!.stopFixedPct).toBeCloseTo(92);
    expect(levels!.stopSuggested).toBeCloseTo(92);
  });

  it("區間無波動（high==low 全平）時位階回 null 而非除以零", () => {
    const bars = Array.from({ length: 70 }, (_, i) =>
      bar(`2025-${String(i + 1).padStart(3, "0")}`, 100, 100, 100),
    );
    const levels = computeKeyLevels(bars, null);
    expect(levels!.rangePositionPct).toBeNull();
  });
});

describe("computeKeyLevels — 數值正確性", () => {
  it("均線、位階、乖離與 ATR 按定義計算", () => {
    // 前 60 根 100，最後 10 根 110：MA20 = (10*100+10*110)/20 = 105
    const bars = [...flatBars(60, 100), ...Array.from({ length: 10 }, (_, i) => bar(`2026-${i}`, 110))];
    const levels = computeKeyLevels(bars, null)!;
    expect(levels.close).toBe(110);
    expect(levels.ma20).toBeCloseTo(105);
    // MA60 = (50*100 + 10*110)/60
    expect(levels.ma60).toBeCloseTo((50 * 100 + 10 * 110) / 60);
    // 區間 [99, 111]（含 high/low ±1），位階 = (110-99)/(111-99)
    expect(levels.rangeHigh).toBe(111);
    expect(levels.rangeLow).toBe(99);
    expect(levels.rangePositionPct).toBeCloseTo(((110 - 99) / 12) * 100);
    expect(levels.ma60DeviationPct).toBeCloseTo((110 / levels.ma60! - 1) * 100);
    // ATR 視窗含跳空 bar：4 根 TR=2、跳空 bar TR=11、9 根 TR=2 → 37/14
    expect(levels.atr14).toBeCloseTo(37 / 14);
  });

  it("未持有：以收盤為錨,2×ATR 與 -8% 取較緊者(較高價)為建議停損", () => {
    const bars = flatBars(70, 100);
    const levels = computeKeyLevels(bars, null)!;
    expect(levels.anchoredOnCost).toBe(false);
    expect(levels.anchorPrice).toBe(100);
    // ATR=2 → atr 停損 96；-8% 停損 92；建議 = 96（較緊）
    expect(levels.stopAtr).toBeCloseTo(96);
    expect(levels.stopFixedPct).toBeCloseTo(92);
    expect(levels.stopSuggested).toBeCloseTo(96);
    // 2R = 100 + 2*(100-96) = 108；+20% = 120
    expect(levels.target2R).toBeCloseTo(108);
    expect(levels.targetFixedPct).toBeCloseTo(120);
  });

  it("持有：以成本為錨", () => {
    const bars = flatBars(70, 100);
    const levels = computeKeyLevels(bars, 80)!;
    expect(levels.anchoredOnCost).toBe(true);
    expect(levels.anchorPrice).toBe(80);
    expect(levels.stopFixedPct).toBeCloseTo(73.6);
    // atr 停損 80-4=76 高於 73.6 → 建議 76
    expect(levels.stopSuggested).toBeCloseTo(76);
    expect(levels.targetFixedPct).toBeCloseTo(96);
    expect(levels.target2R).toBeCloseTo(88);
  });

  it("成本非正數或非有限值視同未持有", () => {
    const bars = flatBars(70, 100);
    expect(computeKeyLevels(bars, 0)!.anchoredOnCost).toBe(false);
    expect(computeKeyLevels(bars, Number.NaN)!.anchoredOnCost).toBe(false);
  });
});

describe("classifyRangeZone", () => {
  it("三分類門檻含邊界", () => {
    expect(classifyRangeZone(0)).toBe("low");
    expect(classifyRangeZone(30)).toBe("low");
    expect(classifyRangeZone(30.1)).toBe("mid");
    expect(classifyRangeZone(69.9)).toBe("mid");
    expect(classifyRangeZone(70)).toBe("high");
    expect(classifyRangeZone(100)).toBe("high");
  });
});
