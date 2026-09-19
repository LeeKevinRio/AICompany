/**
 * §1.3 required test-coverage obligation: "上表須落為單一常數來源，由後端
 * 與前端共用掃描（前端文案模板亦須被掃到）". The backend scan
 * (`apps/stock-desk/backend/tests/test_advice_wording.py`) only reaches
 * Python-side strings; this is the front-end half.
 *
 * Deliberately scans *rendered output* (every exported label and every
 * `build*` template's return value with representative arguments) rather
 * than the module's raw source text: this file's doc comments legitimately
 * *name* several banned phrases as negative examples (e.g. explaining that
 * `CANDIDATE_NOT_SUPPORTIVE_TEXT` must never be softened into "可再觀察"),
 * and a naive source-text scan would flag that explanation as a violation.
 * Scanning what actually reaches a screen is both more precise and what
 * §1.3 asks for ("文案模板").
 *
 * "即時" is deliberately excluded from the plain substring list (a naive
 * `.not.toContain("即時")` would false-positive on `NON_REALTIME_NOTICE`'s
 * required "非即時" denial) — it is instead checked automatically via
 * `findBareRealtimeClaims` (`wordingScanHelpers.ts`), which only fails when
 * "即時" appears *without* an immediately preceding "非" (qa-reviewer
 * BLOCKING/Major follow-up: this was a manual-review `it.todo` before).
 */

import { describe, expect, it } from "vitest";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";
import {
  AS_OF_AGE_UNKNOWN_STATEMENT,
  AS_OF_CALENDAR_UNCONFIRMED_STATEMENT,
  AS_OF_DATE_UNKNOWN_FULL_STATEMENT,
  AS_OF_DATE_UNKNOWN_STATEMENT,
  buildAsOfStatement,
  buildAttributedHeadline,
  buildCandidateCoverageStatement,
  buildCandidateSupportiveComposition,
  buildLegacyAttributedHeadline,
  buildRulesStatement,
  buildStaleDataProminentNotice,
  CANDIDATE_CONFIDENCE_NOT_COMPARABLE_NOTE,
  CANDIDATE_EVIDENCE_NOTICE,
  CANDIDATE_HEADING_LABEL,
  CANDIDATE_NOT_SUPPORTIVE_TEXT,
  CANDIDATE_NOT_SUPPORTIVE_TEXT_LEGACY,
  CANDIDATE_QUANTITY_BASIS_NOTE,
  CANDIDATE_SUPPORTIVE_DISCLAIMER,
  CONFIDENCE_PREFIX,
  FRONTEND_FORBIDDEN_TERMS,
  HELD_ACTION_LABELS,
  HELD_ACTION_LABELS_LEGACY,
  INSUFFICIENT_DATA_NO_EVALUATION,
  NON_REALTIME_NOTICE,
  NOT_HELD_BADGE,
  QUANTITY_RANGE_ABSENCE_TEXT,
  QUANTITY_RANGE_ABSENT_SHORT,
  RULE_BASIS_PREFIX,
  RULE_SOURCE_CHIP,
  summaryConfidenceLabel,
} from "../adviceWording";
import type { CardAction, Confidence } from "../types";

const HELD_ACTIONS: CardAction[] = ["add", "hold", "reduce", "take_profit", "stop_loss", "insufficient_data"];
const CONFIDENCES: Confidence[] = ["low", "medium", "high"];

/** Every user-facing string this module can ever render, in one flat list. */
const RENDERED_SURFACE: string[] = [
  ...Object.values(HELD_ACTION_LABELS),
  ...HELD_ACTIONS.map(buildAttributedHeadline),
  // wave3（`work/stock-desk-一眼一句簡化-派工單.md` §4.3）：舊字面搬進「詳細」，
  // 不是刪除——一併納入禁用詞掃描，與新字面（RULE_SOURCE_CHIP 等）並列。
  ...Object.values(HELD_ACTION_LABELS_LEGACY),
  ...HELD_ACTIONS.map(buildLegacyAttributedHeadline),
  RULE_SOURCE_CHIP,
  INSUFFICIENT_DATA_NO_EVALUATION,
  RULE_BASIS_PREFIX,
  QUANTITY_RANGE_ABSENT_SHORT,
  CONFIDENCE_PREFIX,
  NOT_HELD_BADGE,
  CANDIDATE_HEADING_LABEL,
  buildCandidateSupportiveComposition(3),
  CANDIDATE_SUPPORTIVE_DISCLAIMER,
  CANDIDATE_NOT_SUPPORTIVE_TEXT,
  CANDIDATE_NOT_SUPPORTIVE_TEXT_LEGACY,
  CANDIDATE_EVIDENCE_NOTICE,
  CANDIDATE_CONFIDENCE_NOT_COMPARABLE_NOTE,
  buildCandidateCoverageStatement(0.75, 4),
  CANDIDATE_QUANTITY_BASIS_NOTE,
  QUANTITY_RANGE_ABSENCE_TEXT,
  buildRulesStatement("1.0.2"),
  buildAsOfStatement("2026-08-04"),
  buildStaleDataProminentNotice("2026-08-04", 15),
  AS_OF_DATE_UNKNOWN_STATEMENT,
  // R-D5②-1: the unknown-date slot ships both sentences, so the banned-term
  // scan has to see the追加句 and the full concatenation, not just the first
  // sentence it used to cover.
  AS_OF_AGE_UNKNOWN_STATEMENT,
  AS_OF_DATE_UNKNOWN_FULL_STATEMENT,
  // 句 1 CONFIRMED (2026-08-19): the date-known/gap-unknown slot's addition —
  // scanned both standalone and concatenated, so a future edit that only
  // updates one of the two forms cannot slip past the banned-term scan.
  AS_OF_CALENDAR_UNCONFIRMED_STATEMENT,
  buildAsOfStatement("2026-08-04") + AS_OF_CALENDAR_UNCONFIRMED_STATEMENT,
  NON_REALTIME_NOTICE,
  ...CONFIDENCES.map(summaryConfidenceLabel),
];

describe("adviceWording.ts — §1.3 banned-term scan (rendered output)", () => {
  const joined = RENDERED_SURFACE.join("\n");

  it.each(FRONTEND_FORBIDDEN_TERMS)("does not contain the banned term %j", (term) => {
    expect(joined).not.toContain(term);
  });

  it("every '即時' occurrence is part of a '非即時' denial, never a bare capability claim", () => {
    expect(findBareRealtimeClaims(joined)).toEqual([]);
  });

  it("assertNoForbiddenTerms helper agrees with the it.each scan above (belt and suspenders)", () => {
    assertNoForbiddenTerms(joined, FRONTEND_FORBIDDEN_TERMS, "adviceWording.ts rendered surface");
  });
});

/**
 * wave3（`work/stock-desk-一眼一句簡化-派工單.md` §4.3，風控逐字核可）：
 * CEO 對頎邦頁面「為何評估叫做停損評估？我看不懂這一段」的提問促成的改寫。
 * 新字面與其對應的舊字面（`_LEGACY`）逐字釘住，兩者都不得漂移——舊字面搬進
 * 「詳細」而非刪除，兩邊字面都要留一份釘死的紀錄。
 */
describe("wave3 — HELD_ACTION_LABELS 改寫與 LEGACY 對照（逐字釘住）", () => {
  it("新字面：停損參考／續抱參考／分批獲利了結／資料不足", () => {
    expect(HELD_ACTION_LABELS).toEqual({
      add: "加碼參考",
      hold: "續抱參考",
      reduce: "減碼參考",
      take_profit: "分批獲利了結",
      stop_loss: "停損參考",
      insufficient_data: "資料不足",
    });
  });

  it("舊字面（LEGACY，一字不動）：續抱/維持現狀、分批獲利了結參考、停損評估、資料不足，本次不提供操作評估", () => {
    expect(HELD_ACTION_LABELS_LEGACY).toEqual({
      add: "加碼參考",
      hold: "續抱/維持現狀",
      reduce: "減碼參考",
      take_profit: "分批獲利了結參考",
      stop_loss: "停損評估",
      insufficient_data: "資料不足，本次不提供操作評估",
    });
  });

  it("buildAttributedHeadline 回傳純標籤（不再有「規則評估：」前綴）", () => {
    for (const action of HELD_ACTIONS) {
      expect(buildAttributedHeadline(action)).toBe(HELD_ACTION_LABELS[action]);
      expect(buildAttributedHeadline(action)).not.toContain("：");
    }
  });

  it("buildLegacyAttributedHeadline 逐字重現舊版「規則評估：{舊標籤}」", () => {
    expect(buildLegacyAttributedHeadline("stop_loss")).toBe("規則評估：停損評估");
    expect(buildLegacyAttributedHeadline("add")).toBe("規則評估：加碼參考");
    for (const action of HELD_ACTIONS) {
      expect(buildLegacyAttributedHeadline(action)).toBe(`規則評估：${HELD_ACTION_LABELS_LEGACY[action]}`);
    }
  });

  it("RULE_SOURCE_CHIP／INSUFFICIENT_DATA_NO_EVALUATION 逐字比對", () => {
    expect(RULE_SOURCE_CHIP).toBe("依規則");
    expect(INSUFFICIENT_DATA_NO_EVALUATION).toBe("本次不提供操作評估");
  });

  it("CANDIDATE_NOT_SUPPORTIVE_TEXT 新舊字面逐字比對", () => {
    expect(CANDIDATE_NOT_SUPPORTIVE_TEXT).toBe("本次未支持進場");
    expect(CANDIDATE_NOT_SUPPORTIVE_TEXT_LEGACY).toBe("本次規則評估未支持進場");
  });

  it("NOT_HELD_BADGE／RULE_BASIS_PREFIX／QUANTITY_RANGE_ABSENT_SHORT／CONFIDENCE_PREFIX 逐字比對", () => {
    expect(NOT_HELD_BADGE).toBe("未持有");
    expect(RULE_BASIS_PREFIX).toBe("依據：");
    expect(QUANTITY_RANGE_ABSENT_SHORT).toBe("未提供股數");
    expect(CONFIDENCE_PREFIX).toBe("信心 ");
  });
});

describe("the unknown-as-of-date slot (R-D5②-1, 風控逐字確認 2026-08-16)", () => {
  it("pins both approved sentences character for character", () => {
    expect(AS_OF_DATE_UNKNOWN_STATEMENT).toBe(
      "本評估未取得收盤資料的日期，無法標示評估所依據的資料時間。",
    );
    expect(AS_OF_AGE_UNKNOWN_STATEMENT).toBe("因此本次也無法判斷這份資料距今多久。");
  });

  it("ships the two sentences as one string, in order, with nothing between them", () => {
    // The disclosure only works as a pair: the first names the missing date,
    // the second names what that costs (no age judgement, hence no 資料過舊
    // notice). Concatenation is what makes "always together" structural rather
    // than a convention a future edit could break.
    expect(AS_OF_DATE_UNKNOWN_FULL_STATEMENT).toBe(
      "本評估未取得收盤資料的日期，無法標示評估所依據的資料時間。因此本次也無法判斷這份資料距今多久。",
    );
    expect(AS_OF_DATE_UNKNOWN_FULL_STATEMENT).toBe(
      AS_OF_DATE_UNKNOWN_STATEMENT + AS_OF_AGE_UNKNOWN_STATEMENT,
    );
    expect(AS_OF_DATE_UNKNOWN_FULL_STATEMENT.startsWith(AS_OF_DATE_UNKNOWN_STATEMENT)).toBe(true);
    expect(AS_OF_DATE_UNKNOWN_FULL_STATEMENT.endsWith(AS_OF_AGE_UNKNOWN_STATEMENT)).toBe(true);
  });

  it("carries no action guidance — it states two facts and stops", () => {
    for (const term of ["請", "建議", "自行", "應", "可以"]) {
      expect(AS_OF_AGE_UNKNOWN_STATEMENT).not.toContain(term);
    }
  });
});

describe("the calendar-unconfirmed as-of slot (句 1 CONFIRMED 2026-08-19, `work/reviews/2026-08-19-句1句3重寫-風控批審.md`)", () => {
  it("pins the CONFIRMED sentence character for character (retyped, not imported)", () => {
    // 落地條件 6: must be a fresh retype of the reviewed literal, not a
    // self-comparison against the constant this test is guarding.
    expect(AS_OF_CALENDAR_UNCONFIRMED_STATEMENT).toBe(
      "本次無法向交易日曆確認資料是否過舊，這並不代表資料已確認為最新。",
    );
  });

  it("carries no action guidance and no reversal into an affirmative claim", () => {
    for (const term of ["請", "建議", "自行", "應", "可以", "已確認為最新"]) {
      if (term === "已確認為最新") {
        // The sentence names this as the *un*confirmed state ("並不代表資料
        // 已確認為最新"), so the phrase legitimately appears once, inside a
        // negation — this asserts it never appears as a bare affirmation.
        expect(AS_OF_CALENDAR_UNCONFIRMED_STATEMENT.match(/已確認為最新/g)?.length ?? 0).toBe(1);
        continue;
      }
      expect(AS_OF_CALENDAR_UNCONFIRMED_STATEMENT).not.toContain(term);
    }
  });
});

describe("buildStaleDataProminentNotice — the C4 wording change (待風控覆核)", () => {
  it("states the gap in trading days, keeping the 2026-08-09-approved sentence shape", () => {
    // The literal sentence is pinned here so the review of the C4 change has
    // one place to read it: only the unit moved (日曆日 -> 交易日), because the
    // number it qualifies is now an observed trading-session count
    // (`data.trading_days_behind`) and leaving 「日曆日」 over it would be a
    // false statement. Every other word is unchanged from the 2026-08-09
    // 裁決 b sentence, including the 全形 punctuation of the final review.
    expect(buildStaleDataProminentNotice("2026-08-04", 3)).toBe(
      "本評估所依據的收盤資料為 2026-08-04，距今已 3 個交易日未更新，僅供參考，不代表最新市況。",
    );
  });

  it("names the basis date and the magnitude rather than hiding either", () => {
    const notice = buildStaleDataProminentNotice("2026-02-13", 12);
    expect(notice).toContain("2026-02-13");
    expect(notice).toContain("12");
  });
});
