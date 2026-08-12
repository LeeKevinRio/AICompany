import { describe, expect, it } from "vitest";
import type { PlaybookDirectiveLine, PlaybookMode } from "../types";
import {
  EXIT_FREEZE_DAYS_DEFAULT,
  allExitChecksConfirmed,
  buildExitConfirmChecks,
  directivePriorityIndex,
  directiveStatusLabel,
  formatScaledPercent,
  initialExitChecks,
  modeBadgeVisual,
  ruleFamily,
  ruleFamilyVisual,
  shouldRenderAttribution,
  sortDirectiveLines,
  splitDirectiveLine,
  toggleExitCheck,
} from "../playbookView";

function directiveLine(ruleId: string, symbol: string, line = ""): PlaybookDirectiveLine {
  return {
    line: line || `${symbol}｜買進｜100 股｜規則 ${ruleId}｜依據資料日 2026-08-11｜預定執行日 2026-08-12｜參考價 100.00（依據交易日收盤價，不反映今日盤中變動）`,
    directive: {
      symbol,
      batch_no: 1,
      action: "buy",
      shares: 100,
      // Cast: the test fixture spans rule ids beyond the exact literal
      // RuleId union on purpose (priority/family mapping must degrade
      // gracefully for ids outside R/S/P/M1 too), so a strict literal type
      // would fight the fixture rather than help it.
      rule_id: ruleId as PlaybookDirectiveLine["directive"]["rule_id"],
      rule_summary: "規則全文",
      data_date: "2026-08-11",
      execution_date: "2026-08-12",
      reference_price: "100.00",
      limit_low: "98.00",
      limit_high: "102.00",
      limit_note: "限價帶",
      data_status: "fresh",
      source: "twse",
      status: "pending",
    },
  };
}

describe("modeBadgeVisual", () => {
  const modes: PlaybookMode[] = ["normal", "defense", "frozen", "emergency_frozen", "unconfirmed"];

  it("returns a distinct container/dot class pair for every mode", () => {
    const seen = new Set<string>();
    for (const mode of modes) {
      const visual = modeBadgeVisual(mode);
      expect(visual.containerClass.length).toBeGreaterThan(0);
      expect(visual.dotClass.length).toBeGreaterThan(0);
      const key = `${visual.containerClass}|${visual.dotClass}`;
      expect(seen.has(key), `${mode} shares a visual with another mode`).toBe(false);
      seen.add(key);
    }
  });

  it("uses rose only for the rule-violation freeze (frozen), never emergency_frozen", () => {
    expect(modeBadgeVisual("frozen").containerClass).toContain("rose");
    expect(modeBadgeVisual("emergency_frozen").containerClass).not.toContain("rose");
  });

  it("uses amber for defense, matching 視覺規範 §2.2's 防守 ≠ 恐慌 ruling", () => {
    expect(modeBadgeVisual("defense").containerClass).toContain("amber");
  });
});

describe("ruleFamily / ruleFamilyVisual", () => {
  it("maps every documented rule id to its family", () => {
    expect(ruleFamily("R1")).toBe("R");
    expect(ruleFamily("R4")).toBe("R");
    expect(ruleFamily("S1")).toBe("S");
    expect(ruleFamily("S3")).toBe("S");
    expect(ruleFamily("P2")).toBe("P");
    expect(ruleFamily("M1")).toBe("M1");
  });

  it("falls back to OTHER for ids outside the §3.4 table", () => {
    expect(ruleFamily("IRON1")).toBe("OTHER");
    expect(ruleFamily("EMERGENCY")).toBe("OTHER");
    expect(ruleFamily("REBALANCE")).toBe("OTHER");
  });

  it("never reuses rose or sky (already action-semantic colours on AdviceCardView)", () => {
    for (const ruleId of ["R1", "S1", "P1", "M1", "IRON1"]) {
      const visual = ruleFamilyVisual(ruleId);
      expect(visual.borderClass).not.toContain("rose");
      expect(visual.borderClass).not.toContain("sky");
    }
  });
});

describe("directivePriorityIndex / sortDirectiveLines", () => {
  it("orders M1 > S3 > S2 > S1 > P3 > P1 > P2 > R per 鐵律③", () => {
    expect(directivePriorityIndex("M1")).toBeLessThan(directivePriorityIndex("S3"));
    expect(directivePriorityIndex("S3")).toBeLessThan(directivePriorityIndex("S2"));
    expect(directivePriorityIndex("S2")).toBeLessThan(directivePriorityIndex("S1"));
    expect(directivePriorityIndex("S1")).toBeLessThan(directivePriorityIndex("P3"));
    expect(directivePriorityIndex("P3")).toBeLessThan(directivePriorityIndex("P1"));
    expect(directivePriorityIndex("P1")).toBeLessThan(directivePriorityIndex("P2"));
    expect(directivePriorityIndex("P2")).toBeLessThan(directivePriorityIndex("R1"));
  });

  it("sorts ids outside the arbitration list last", () => {
    expect(directivePriorityIndex("IRON1")).toBeGreaterThan(directivePriorityIndex("R4"));
  });

  it("sorts a mixed batch by priority, then by symbol", () => {
    const input = [
      directiveLine("R1", "2330"),
      directiveLine("S1", "2454"),
      directiveLine("M1", "0050"),
      directiveLine("S1", "1101"),
    ];
    const sorted = sortDirectiveLines(input);
    expect(sorted.map((item) => `${item.directive.rule_id}-${item.directive.symbol}`)).toEqual([
      "M1-0050",
      "S1-1101",
      "S1-2454",
      "R1-2330",
    ]);
  });

  it("does not mutate the input array", () => {
    const input = [directiveLine("R1", "2330"), directiveLine("M1", "0050")];
    const copy = [...input];
    sortDirectiveLines(input);
    expect(input).toEqual(copy);
  });
});

describe("splitDirectiveLine", () => {
  it("splits the backend's ｜-joined line into its seven fields", () => {
    const line = directiveLine("S1", "2330").line;
    const parts = splitDirectiveLine(line);
    expect(parts).toHaveLength(7);
    expect(parts[0]).toBe("2330");
    expect(parts[3]).toBe("規則 S1");
    expect(parts[4]).toBe("依據資料日 2026-08-11");
    expect(parts[5]).toBe("預定執行日 2026-08-12");
  });

  it("degrades to a single-element array when the separator is absent", () => {
    expect(splitDirectiveLine("no separator here")).toEqual(["no separator here"]);
  });
});

describe("directiveStatusLabel", () => {
  it("maps every DirectiveStatus to the backend's own vocabulary", () => {
    expect(directiveStatusLabel("pending")).toBe("待結算");
    expect(directiveStatusLabel("executed")).toBe("成交");
    expect(directiveStatusLabel("missed")).toBe("未成交（MISSED）");
  });
});

describe("shouldRenderAttribution (EMPTY 契約)", () => {
  it("returns false for null", () => {
    expect(shouldRenderAttribution(null)).toBe(false);
  });

  it("returns false for an empty string", () => {
    expect(shouldRenderAttribution("")).toBe(false);
  });

  it("returns true for a non-empty attribution sentence", () => {
    expect(shouldRenderAttribution("此指令是你於 2026-08-01 自行設定的規則之機械執行結果")).toBe(true);
  });
});

describe("formatScaledPercent", () => {
  it("renders a dash for null", () => {
    expect(formatScaledPercent(null)).toBe("—");
  });

  it("appends % without re-scaling (value is already percent-scaled)", () => {
    expect(formatScaledPercent("12.3456")).toBe("12.35%");
  });

  it("handles negative values", () => {
    expect(formatScaledPercent("-8")).toBe("-8.00%");
  });

  it("renders a dash for a non-numeric string", () => {
    expect(formatScaledPercent("not-a-number")).toBe("—");
  });
});

describe("EMERGENCY_EXIT checkbox state machine", () => {
  it("initialExitChecks starts every box unticked (視覺規範 §4.3: 不預設勾選)", () => {
    expect(initialExitChecks(4)).toEqual([false, false, false, false]);
  });

  it("toggleExitCheck flips only the targeted index", () => {
    const state = initialExitChecks(4);
    const toggled = toggleExitCheck(state, 2);
    expect(toggled).toEqual([false, false, true, false]);
    // original state is untouched (pure function)
    expect(state).toEqual([false, false, false, false]);
  });

  it("allExitChecksConfirmed is false until every box is ticked", () => {
    let state = initialExitChecks(3);
    expect(allExitChecksConfirmed(state)).toBe(false);
    state = toggleExitCheck(state, 0);
    state = toggleExitCheck(state, 1);
    expect(allExitChecksConfirmed(state)).toBe(false);
    state = toggleExitCheck(state, 2);
    expect(allExitChecksConfirmed(state)).toBe(true);
  });

  it("allExitChecksConfirmed is false for an empty checklist (no false-positive on zero checks)", () => {
    expect(allExitChecksConfirmed([])).toBe(false);
  });
});

describe("buildExitConfirmChecks", () => {
  it("returns four checks, none with an unresolved {placeholder}", () => {
    const checks = buildExitConfirmChecks();
    expect(checks).toHaveLength(4);
    for (const check of checks) {
      expect(check).not.toMatch(/\{[a-zA-Z_]+\}/);
    }
  });

  it("fills freeze_days with the given value", () => {
    const checks = buildExitConfirmChecks(30);
    expect(checks[1]).toContain("30 個交易日");
  });

  it("defaults freeze_days to EXIT_FREEZE_DAYS_DEFAULT", () => {
    const checks = buildExitConfirmChecks();
    expect(checks[1]).toContain(`${EXIT_FREEZE_DAYS_DEFAULT} 個交易日`);
  });

  it("renders the unavailable FREEZE_UNTIL as the site's existing dash sentinel", () => {
    const checks = buildExitConfirmChecks();
    expect(checks[1]).toContain("預計恢復日：—");
  });

  it("checks 0, 2, 3 need no substitution and match the backend constants verbatim", () => {
    const checks = buildExitConfirmChecks();
    expect(checks[0]).toBe(
      "此操作將對目前持有的全部標的、全部批次送出出清指令；" +
        "不可只出清部分標的或部分批次，亦不可指定單一標的" +
        "（如需針對單一標的停損，請改用該標的的 S 系列規則）。",
    );
    expect(checks[2]).toBe(
      "凍結期間內，S／P 系列（停損／停利）仍照常評估；凍結期間仍可再次送出全部出清。",
    );
    expect(checks[3]).toBe(
      "本操作產生的是賣出指令，不是成交：T+1 開盤以市價單送出，跌停或無量時可能無法成交。",
    );
  });
});
