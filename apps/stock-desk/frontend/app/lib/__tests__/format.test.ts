/**
 * S1 fix + D2 item 3 (risk-final-review.md 列管項 / 機會清單 D2, 2026-08-10
 * 派工單): `formatDateTime` now labels its Taipei-timezone value explicitly,
 * and `ruleDirectionLabel`/`actionRawLabel` are new lookups behind
 * `AdviceCardView.tsx`'s direction-weights display. No `format.test.ts`
 * existed before this batch touched `format.ts`.
 */

import { describe, expect, it } from "vitest";
import { actionRawLabel, formatDateTime, ruleDirectionLabel } from "../format";

describe("formatDateTime — S1: every timestamp names its own timezone", () => {
  it("labels a valid ISO timestamp with the Taipei-timezone suffix", () => {
    const result = formatDateTime("2026-08-10T04:00:00Z");
    expect(result).toContain("（台北時間）");
    // Asia/Taipei is UTC+8 with no DST: 04:00 UTC -> 12:00.
    expect(result).toContain("12:00");
  });

  it("does not fabricate a timezone label for a missing/invalid timestamp", () => {
    expect(formatDateTime(null)).toBe("資料時間不明");
    expect(formatDateTime(undefined)).toBe("資料時間不明");
    expect(formatDateTime("not-a-date")).toBe("資料時間不明");
  });
});

describe("ruleDirectionLabel — D2 item 3: AdviceCard.direction_weights labels", () => {
  it("labels every direction the backend's ACTION_DIRECTION can produce", () => {
    expect(ruleDirectionLabel("constructive")).toBe("建設性");
    expect(ruleDirectionLabel("defensive")).toBe("防禦型");
    expect(ruleDirectionLabel("neutral")).toBe("中性");
  });

  it("degrades to the raw value for an unrecognised direction, never throws", () => {
    expect(ruleDirectionLabel("unknown_direction")).toBe("unknown_direction");
  });
});

describe("actionRawLabel — direction_weights[].actions labels", () => {
  it("reuses the held-mode action label whitelist", () => {
    expect(actionRawLabel("add")).toBe("加碼參考");
    expect(actionRawLabel("stop_loss")).toBe("停損評估");
  });

  it("degrades to the raw value for an unrecognised action, never throws", () => {
    expect(actionRawLabel("unknown_action")).toBe("unknown_action");
  });
});
