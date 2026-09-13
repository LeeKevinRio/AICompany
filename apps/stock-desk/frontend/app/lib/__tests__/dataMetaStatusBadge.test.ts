import { describe, expect, it } from "vitest";
import { cachedStaleLabel } from "../../components/DataMetaStatusBadge";

/**
 * 風控 2026-09-13 第二輪核可（ADR-0009 D-5）方案 A 八句，逐字釘住：徽章陳述可驗證的
 * 「資料截至日期」與「取得時間」，不下「今日已更新」或「已含最近交易日」這類
 * 使用者無從驗證的推論。任何一字改動須重送 risk-compliance-officer。
 */
describe("DataMetaStatusBadge cached_stale wording — 風控 2026-09-13 方案 A", () => {
  it("cache holds the latest published session (isWithinTtl === true)", () => {
    expect(cachedStaleLabel({ stalenessMinutes: 42, isWithinTtl: true, lastBarDate: "2026-09-11" })).toBe(
      "本機快取，資料截至 2026-09-11（42 分鐘前取得）",
    );
    expect(cachedStaleLabel({ stalenessMinutes: null, isWithinTtl: true, lastBarDate: "2026-09-11" })).toBe(
      "本機快取，資料截至 2026-09-11",
    );
    expect(cachedStaleLabel({ stalenessMinutes: 42, isWithinTtl: true, lastBarDate: null })).toBe(
      "本機快取（42 分鐘前取得）",
    );
    expect(cachedStaleLabel({ stalenessMinutes: null, isWithinTtl: true, lastBarDate: null })).toBe("本機快取");
  });

  it("cache known or suspected to be short of a session (false and null read the same)", () => {
    for (const isWithinTtl of [false, null]) {
      expect(cachedStaleLabel({ stalenessMinutes: 1440, isWithinTtl, lastBarDate: "2026-09-11" })).toBe(
        "快取資料，資料截至 2026-09-11（1440 分鐘前取得，可能未含最近交易日）",
      );
      expect(cachedStaleLabel({ stalenessMinutes: null, isWithinTtl, lastBarDate: "2026-09-11" })).toBe(
        "快取資料，資料截至 2026-09-11（可能未含最近交易日）",
      );
      expect(cachedStaleLabel({ stalenessMinutes: 1440, isWithinTtl, lastBarDate: null })).toBe(
        "快取資料，1440 分鐘前取得，可能未含最近交易日",
      );
      expect(cachedStaleLabel({ stalenessMinutes: null, isWithinTtl, lastBarDate: null })).toBe(
        "快取資料（取得時間不明，可能未含最近交易日）",
      );
    }
  });

  it("never claims liveness or a same-day update, in any of the eight sentences", () => {
    for (const isWithinTtl of [true, false, null]) {
      for (const stalenessMinutes of [1, null]) {
        for (const lastBarDate of ["2026-09-11", null]) {
          expect(cachedStaleLabel({ stalenessMinutes, isWithinTtl, lastBarDate })).not.toMatch(
            /即時|今日已更新|已含最近交易日/,
          );
        }
      }
    }
  });
});
