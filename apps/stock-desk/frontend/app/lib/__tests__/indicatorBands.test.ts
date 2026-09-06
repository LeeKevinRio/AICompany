import { describe, expect, it } from "vitest";
import { kdBand, percentBBand, rsiBand, volumeZBand } from "../indicatorBands";

describe("indicator bands — thresholds exactly as printed on the chips", () => {
  it("RSI: ≤30 low, ≥70 high, boundaries inclusive", () => {
    expect(rsiBand(30)).toBe("low");
    expect(rsiBand(30.01)).toBe("mid");
    expect(rsiBand(69.99)).toBe("mid");
    expect(rsiBand(70)).toBe("high");
    expect(rsiBand(null)).toBeNull();
    expect(rsiBand(Number.NaN)).toBeNull();
  });

  it("KD (K line): ≤20 low, ≥80 high", () => {
    expect(kdBand(20)).toBe("low");
    expect(kdBand(50)).toBe("mid");
    expect(kdBand(80)).toBe("high");
    expect(kdBand(null)).toBeNull();
  });

  it("%B: <0 low, 0–1 mid (inclusive), >1 high", () => {
    expect(percentBBand(-0.01)).toBe("low");
    expect(percentBBand(0)).toBe("mid");
    expect(percentBBand(1)).toBe("mid");
    expect(percentBBand(1.01)).toBe("high");
    expect(percentBBand(null)).toBeNull();
  });

  it("volume z: |z| ≥ 2 is the deviation band, sign decides the side", () => {
    expect(volumeZBand(-2)).toBe("low");
    expect(volumeZBand(-1.99)).toBe("mid");
    expect(volumeZBand(1.99)).toBe("mid");
    expect(volumeZBand(2)).toBe("high");
    expect(volumeZBand(null)).toBeNull();
  });
});
