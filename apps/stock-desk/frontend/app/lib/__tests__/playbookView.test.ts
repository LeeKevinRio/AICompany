import { describe, expect, it } from "vitest";
import type {
  PlaybookDirectiveLine,
  PlaybookExitConfirm,
  PlaybookMode,
  PlaybookTodayResponse,
} from "../types";
import {
  EXIT_CONFIRM_FALLBACK_CHECKS,
  allExitChecksConfirmed,
  directivePriorityIndex,
  exitConfirmChecks,
  directiveStatusLabel,
  fastMarketAdjacentNote,
  formatScaledPercent,
  initialExitChecks,
  modeBadgeVisual,
  noDirectiveNote,
  ruleFamily,
  ruleFamilyVisual,
  shouldRenderAttribution,
  shouldRenderDirectiveLedger,
  sortDirectiveLines,
  splitDirectiveLine,
  toggleExitCheck,
  visibleWarnings,
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

function exitConfirm(freezeDays: number, freezeUntil: string): PlaybookExitConfirm {
  // Shaped exactly as `wording.exit_confirm_checks` renders it server-side, so
  // the assertions below read the numbers off the sentence, never off a
  // client-side template.
  return {
    freeze_days: freezeDays,
    freeze_until: freezeUntil,
    checks: [
      "此操作將對目前持有的全部標的、全部批次送出出清指令；" +
        "不可只出清部分標的或部分批次，亦不可指定單一標的" +
        "（如需針對單一標的停損，請改用該標的的 S 系列規則）。",
      `送出後，R 系列（新倉進場）暫停 ${freezeDays} 個交易日` +
        `（預計恢復日：${freezeUntil}，依交易日曆計算）。`,
      "凍結期間內，S／P 系列（停損／停利）仍照常評估；凍結期間仍可再次送出全部出清。",
      "本操作產生的是賣出指令，不是成交：T+1 開盤以市價單送出，跌停或無量時可能無法成交。",
    ],
  };
}

describe("exitConfirmChecks", () => {
  it("renders the backend sentences verbatim, numbers included", () => {
    const checks = exitConfirmChecks(exitConfirm(20, "2026-09-09"));
    expect(checks).toEqual(exitConfirm(20, "2026-09-09").checks);
    expect(checks[1]).toContain("暫停 20 個交易日");
    expect(checks[1]).toContain("預計恢復日：2026-09-09");
  });

  it("follows a changed freeze parameter instead of a mirrored default", () => {
    const checks = exitConfirmChecks(exitConfirm(10, "2026-08-26"));
    expect(checks[1]).toContain("暫停 10 個交易日");
    expect(checks[1]).not.toContain("20 個交易日");
    expect(checks[1]).toContain("預計恢復日：2026-08-26");
  });

  it("never leaves an unresolved {placeholder} or a dash where a date belongs", () => {
    for (const check of exitConfirmChecks(exitConfirm(20, "2026-09-09"))) {
      expect(check).not.toMatch(/\{[a-zA-Z_]+\}/);
      expect(check).not.toContain("預計恢復日：—");
    }
  });

  it("falls back to the four approved sentences when the block is missing", () => {
    const checks = exitConfirmChecks(null);
    expect(checks).toEqual([...EXIT_CONFIRM_FALLBACK_CHECKS]);
    // 降級句保留「暫停」這個事實，但兩個數字一個都不編：沒有假數字，也沒有
    // 把日期渲染成破折號。
    expect(checks[1]).toContain("R 系列（新倉進場）暫停；");
    expect(checks.some((check) => /\d/.test(check.replace("T+1", "")))).toBe(false);
    expect(checks.some((check) => check.includes("預計恢復日：—"))).toBe(false);
  });

  it("renders the degraded freeze sentence only on the degraded branch", () => {
    // qa 釘（四輪收斂裁決）：僅 null／空時渲染。
    const degraded = EXIT_CONFIRM_FALLBACK_CHECKS[1];
    expect(exitConfirmChecks(null)).toContain(degraded);
    expect(exitConfirmChecks({ ...exitConfirm(20, "2026-09-09"), checks: [] })).toContain(
      degraded,
    );
    expect(exitConfirmChecks(exitConfirm(20, "2026-09-09"))).not.toContain(degraded);
    expect(exitConfirmChecks(exitConfirm(10, "2026-08-26"))).not.toContain(degraded);
  });

  it("keeps the exit submittable on the fallback (EX-2: 缺欄位不得變成鎖門)", () => {
    const checks = exitConfirmChecks(null);
    expect(checks.length).toBeGreaterThan(0);
    expect(allExitChecksConfirmed(checks.map(() => true))).toBe(true);
  });

  it("treats an empty checks array as a degraded response, not an empty checklist", () => {
    // 空陣列會讓 `allExitChecksConfirmed` 永遠是 false——那等於把出口鎖死。
    expect(exitConfirmChecks({ ...exitConfirm(20, "2026-09-09"), checks: [] })).toEqual([
      ...EXIT_CONFIRM_FALLBACK_CHECKS,
    ]);
  });

  it("copies the fallback sentences from the backend constants verbatim", () => {
    expect(EXIT_CONFIRM_FALLBACK_CHECKS).toEqual([
      "此操作將對目前持有的全部標的、全部批次送出出清指令；" +
        "不可只出清部分標的或部分批次，亦不可指定單一標的" +
        "（如需針對單一標的停損，請改用該標的的 S 系列規則）。",
      // wording.EXIT_CONFIRM_FREEZE_DEGRADED（四輪收斂裁決核可句）。
      "送出後，R 系列（新倉進場）暫停；本次未能取得暫停交易日數與預計恢復日，" +
        "兩者於送出後的執行結果中顯示。",
      "凍結期間內，S／P 系列（停損／停利）仍照常評估；凍結期間仍可再次送出全部出清。",
      "本操作產生的是賣出指令，不是成交：T+1 開盤以市價單送出，跌停或無量時可能無法成交。",
    ]);
  });
});

/* --- 空帳冊：未命中 vs 未評估 / 快市沿用說明 -------------------------------- */

const NO_HIT_NOTE = "今日規則已全數評估，無任何規則命中，未產生指令。";

function todayResponse(overrides: Partial<PlaybookTodayResponse> = {}): PlaybookTodayResponse {
  return {
    data_date: "2026-08-11",
    execution_date: "2026-08-12",
    mode: "normal",
    mode_label: "正常",
    mode_reason: "正常模式：M1 未觸發，組合未凍結。",
    is_schedule_day: true,
    fast_market: {
      active: false,
      annualized_vol_20d: null,
      large_move_days: 0,
      reason: null,
      carried_forward: false,
      measured_on: "2026-08-11",
      carried_note: null,
    },
    rules_version: 1,
    rules_effective_date: "2026-01-01",
    page_summary: [
      "本頁面指令依 2026-08-11 收盤資料計算。",
      "採用規則版本 1（生效日 2026-01-01）。",
      "今日指令帳冊中的每筆指令是你自行設定的規則之機械執行結果，" +
        "非本系統的判斷或建議；實際成交結果以你的券商回報為準。",
    ],
    directives: [],
    snapshot: [],
    warnings: [],
    rules_fully_evaluated: false,
    no_directive_note: null,
    attribution: "此指令是你於 2026-01-01 自行設定的規則之機械執行結果，非本系統的判斷或建議。",
    settlement: null,
    exit_confirm: null,
    as_of: "2026-08-12T01:00:00Z",
    ...overrides,
  };
}

describe("noDirectiveNote (題 12: 未命中 vs 未評估)", () => {
  it("renders the backend sentence when the completeness flag is set", () => {
    const note = noDirectiveNote(
      todayResponse({ rules_fully_evaluated: true, no_directive_note: NO_HIT_NOTE }),
    );
    expect(note).toBe(NO_HIT_NOTE);
  });

  it("keeps 「無。」 when the flag is false, even if a sentence arrived", () => {
    // 旗標才是渲染條件；句子單獨出現不足以宣稱「已全數評估」。
    expect(
      noDirectiveNote(
        todayResponse({ rules_fully_evaluated: false, no_directive_note: NO_HIT_NOTE }),
      ),
    ).toBeNull();
  });

  it("keeps 「無。」 when the flag is absent altogether (舊版後端 fail-closed)", () => {
    const legacy = todayResponse({ no_directive_note: NO_HIT_NOTE });
    // 模擬未帶新欄位的回應：`undefined` 不是 `true`。
    delete (legacy as Partial<PlaybookTodayResponse>).rules_fully_evaluated;
    expect(noDirectiveNote(legacy)).toBeNull();
  });

  it("keeps 「無。」 when the flag is set but no sentence came with it", () => {
    // 前端不持有這句話：宣稱「已全數評估」的只能是做了評估的那一端。
    expect(
      noDirectiveNote(todayResponse({ rules_fully_evaluated: true, no_directive_note: null })),
    ).toBeNull();
  });

  it("never stacks on 凍結／緊急出清後凍結／待確認規則集", () => {
    for (const mode of ["frozen", "emergency_frozen", "unconfirmed"] as PlaybookMode[]) {
      expect(
        noDirectiveNote(
          todayResponse({ mode, rules_fully_evaluated: true, no_directive_note: NO_HIT_NOTE }),
        ),
        `${mode} must not stack the no-hit sentence`,
      ).toBeNull();
    }
  });
});

describe("shouldRenderDirectiveLedger (required ④ fail-closed)", () => {
  it("renders the ledger only when the attribution sentence is present", () => {
    expect(shouldRenderDirectiveLedger(todayResponse().attribution)).toBe(true);
    expect(shouldRenderDirectiveLedger(null)).toBe(false);
    expect(shouldRenderDirectiveLedger("")).toBe(false);
  });
});

describe("fastMarketAdjacentNote / visibleWarnings", () => {
  const carried = "加權指數資料狀態為 unavailable，快市判定沿用前一次評估結果（快市，依據資料日 2026-08-10）；資料缺漏不會使系統首次進入快市。";

  function fastMarket(overrides: Partial<PlaybookTodayResponse["fast_market"]> = {}) {
    return { ...todayResponse().fast_market, ...overrides };
  }

  it("returns the carried explanation for an active badge with no measurement", () => {
    expect(
      fastMarketAdjacentNote(
        fastMarket({ active: true, reason: null, carried_forward: true, carried_note: carried }),
      ),
    ).toBe(carried);
  });

  it("returns null when the badge is off", () => {
    expect(
      fastMarketAdjacentNote(fastMarket({ active: false, carried_note: carried })),
    ).toBeNull();
  });

  it("returns null when the verdict was measured today (reason already shown)", () => {
    expect(
      fastMarketAdjacentNote(
        fastMarket({ active: true, reason: "20 日年化波動率 41.2%；…", carried_note: null }),
      ),
    ).toBeNull();
  });

  it("returns null when the backend sent no explanation to render", () => {
    expect(
      fastMarketAdjacentNote(fastMarket({ active: true, reason: null, carried_note: null })),
    ).toBeNull();
  });

  it("moves the sentence out of the warnings list only when it is shown elsewhere", () => {
    const warnings = [carried, "其他警示句"];
    expect(visibleWarnings(warnings, carried)).toEqual(["其他警示句"]);
    // 沒有在別處渲染時，一句都不過濾。
    expect(visibleWarnings(warnings, null)).toEqual(warnings);
  });

  it("filters on exact equality only — never on a substring", () => {
    const warnings = [`${carried}（附註）`];
    expect(visibleWarnings(warnings, carried)).toEqual(warnings);
  });
});
