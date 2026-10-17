import { describe, expect, it } from "vitest";
import { classifyRangeZone, computeCostPnlPct, computeKeyLevels } from "../keyLevels";
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
    expect(computeKeyLevels([])).toBeNull();
  });

  it("含非數字 bar 整批拒算（不混算壞資料）", () => {
    const bars = flatBars(70, 100);
    bars[10] = { ...bars[10]!, close: "not-a-number" };
    expect(computeKeyLevels(bars)).toBeNull();
  });

  it("bar 數不足時逐欄位退化為 null 而非造數", () => {
    const levels = computeKeyLevels(flatBars(10, 100));
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
    const levels = computeKeyLevels(bars);
    expect(levels!.rangePositionPct).toBeNull();
  });
});

describe("computeKeyLevels — 數值正確性", () => {
  it("均線、位階、乖離與 ATR 按定義計算", () => {
    // 前 60 根 100，最後 10 根 110：MA20 = (10*100+10*110)/20 = 105
    const bars = [...flatBars(60, 100), ...Array.from({ length: 10 }, (_, i) => bar(`2026-${i}`, 110))];
    const levels = computeKeyLevels(bars)!;
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

  it("以最新收盤為錨(持有與未持有相同),2×ATR 與 -8% 取較緊者(較高價)為建議停損", () => {
    const bars = flatBars(70, 100);
    const levels = computeKeyLevels(bars)!;
    expect(levels.anchorPrice).toBe(100);
    expect(levels.anchorPrice).toBe(levels.close);
    // ATR=2 → atr 停損 96；-8% 停損 92；建議 = 96（較緊）
    expect(levels.stopAtr).toBeCloseTo(96);
    expect(levels.stopFixedPct).toBeCloseTo(92);
    expect(levels.stopSuggested).toBeCloseTo(96);
    // 2R = 100 + 2*(100-96) = 108；+20% = 120
    expect(levels.target2R).toBeCloseTo(108);
    expect(levels.targetFixedPct).toBeCloseTo(120);
  });

  it("R-6：平均成本不是 computeKeyLevels 的輸入,停損／停利恆由最新收盤算出(不隨持倉成本改變)", () => {
    // Same bars, any cost the position might have: the levels are one function of the bars alone.
    expect(computeKeyLevels.length).toBe(1);
    const bars = flatBars(70, 100);
    const levels = computeKeyLevels(bars)!;
    // Cost 80 (profit) or 130 (loss) used to move the anchor to the cost; now it cannot.
    expect(levels.anchorPrice).toBe(100);
    expect(levels.stopSuggested).toBeCloseTo(96);
    expect(levels.target2R).toBeCloseTo(108);
    expect(levels.targetFixedPct).toBeCloseTo(120);
    expect(JSON.stringify(computeKeyLevels(bars))).toBe(JSON.stringify(levels));
  });
});

describe("computeKeyLevels — 持有分支的錨點恆為最新收盤(B0 / R-6 證明,支撐刪除「越過」整組)", () => {
  /** Deterministic pseudo-random series (LCG) so the property check is reproducible. */
  function series(seed: number, n: number, base: number, vol: number): Bar[] {
    let s = seed;
    const rnd = (): number => {
      s = (s * 1664525 + 1013904223) % 4294967296;
      return s / 4294967296;
    };
    let px = base;
    return Array.from({ length: n }, (_, i) => {
      px = Math.max(0.01, px * (1 + (rnd() - 0.5) * vol));
      const hi = px * (1 + rnd() * vol);
      const lo = px * (1 - rnd() * vol);
      return bar(`2025-${String(i + 1).padStart(3, "0")}`, px, hi, Math.max(0.005, lo));
    });
  }

  it("對 400 組隨機序列:停損參考 <= 最新收盤 <= 停利參考(嚴格比較下「越過」不可達),且錨點與最新收盤是同一根 K 棒的同一個數字", () => {
    let checked = 0;
    for (let seed = 1; seed <= 400; seed++) {
      const n = 1 + (seed % 90);
      const base = [0.5, 12, 100, 1027.25, 5000][seed % 5]!;
      const vol = [0.001, 0.02, 0.2, 0.6][seed % 4]!;
      const bars = series(seed, n, base, vol);
      const levels = computeKeyLevels(bars)!;
      expect(levels).not.toBeNull();
      const lastClose = Number.parseFloat(bars[bars.length - 1]!.close);
      expect(levels.close).toBe(lastClose);
      expect(levels.closeDate).toBe(bars[bars.length - 1]!.date);
      expect(levels.anchorPrice).toBe(levels.close);
      expect(levels.stopSuggested).toBeLessThanOrEqual(levels.close);
      expect(levels.target2R).toBeGreaterThanOrEqual(levels.close);
      expect(levels.stopFixedPct).toBeLessThan(levels.close);
      expect(levels.targetFixedPct).toBeGreaterThan(levels.close);
      checked++;
    }
    expect(checked).toBe(400);
  });

  it("ATR 為 0 的全平序列:停損等於最新收盤(相等不算越過)", () => {
    const flat = Array.from({ length: 70 }, (_, i) => bar(`2025-${String(i + 1).padStart(3, "0")}`, 100, 100, 100));
    const levels = computeKeyLevels(flat)!;
    expect(levels.atr14).toBe(0);
    expect(levels.stopSuggested).toBe(levels.close);
    expect(levels.target2R).toBe(levels.close);
  });
});

describe("computeCostPnlPct — 相對成本損益(僅顯示)", () => {
  it("(收盤 / 成本 - 1) × 100,獲利為正、虧損為負", () => {
    expect(computeCostPnlPct(110, 100)).toBeCloseTo(10);
    expect(computeCostPnlPct(90, 100)).toBeCloseTo(-10);
    expect(computeCostPnlPct(100, 100)).toBe(0);
  });

  it("成本缺席、非正數或非有限值回 null(呼叫端改用 LM-53,不造數)", () => {
    expect(computeCostPnlPct(100, null)).toBeNull();
    expect(computeCostPnlPct(100, 0)).toBeNull();
    expect(computeCostPnlPct(100, -5)).toBeNull();
    expect(computeCostPnlPct(100, Number.NaN)).toBeNull();
    expect(computeCostPnlPct(Number.NaN, 100)).toBeNull();
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
