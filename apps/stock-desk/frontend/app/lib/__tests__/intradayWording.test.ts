/**
 * ADR-0014 W9 guard for the intraday ("盤中") disclosure wording. The copy is
 * frozen in `work/copy/盤中價揭露文案-定稿-2026-10-03.md` (section 5 allowlist,
 * section 12 implementation conditions); risk conditions (a)-(e), R1-1..R1-4
 * and the reply to BLOCKING 13 are what this file enforces:
 *
 * - the 30 allowlist sentences are pinned as plain literals (no snapshot);
 * - "盤中" may appear in a non-test source file only in `intradayWording.ts`
 *   (and then only as whole allowlist sentences) and as the single element of
 *   `FRONTEND_FORBIDDEN_TERMS` in `adviceWording.ts`;
 * - matching is whole-sentence equality after splitting on the full-width
 *   period and on newlines. There is no substring masking (`allowedContexts`)
 *   anywhere in this file, on purpose;
 * - allowlist sentences still pass every other banned term and the bare
 *   "即時" scan ("非即時" is the only pass);
 * - the three PENDING_PRECONDITION constants are not imported by any non-test
 *   file, and the C6 sentence 2 constant is recorded as not yet wired.
 *
 * `__tests__` is outside condition (c): pinning literals needs retyping them.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { FRONTEND_FORBIDDEN_TERMS, NON_REALTIME_NOTICE } from "../adviceWording";
import * as intraday from "../intradayWording";
import {
  fillIntradayTemplate,
  INTRADAY_ALLOWED_SENTENCES,
  PENDING_PRECONDITION_SENTENCES,
} from "../intradayWording";
import {
  findBareRealtimeClaims,
  findForbiddenTermsExceptAllowedSentences,
  splitWordingSentences,
  stripComments,
} from "./wordingScanHelpers";

const TERM = "盤中";
const APP_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const INTRADAY_FILE = "lib/intradayWording.ts";
const ADVICE_FILE = "lib/adviceWording.ts";

/** [allowlist #, exported constant name, pinned sentence template], table order. */
const PINNED: ReadonlyArray<readonly [number, string, string]> = [
  [1, "C1_1_PRICE_LABEL", "盤中 {HH:mm} 成交"],
  [2, "C2_1_NO_TRADE_TOOLTIP", "來源目前沒有提供這檔今日的成交價（可能是今日尚未成交），因此不採用盤中價，改用 {MM/DD} 收盤價計算。"],
  [3, "C2_2_COOLDOWN_BADGE", "盤中價暫停查詢"],
  [4, "C2_2_COOLDOWN_TOOLTIP", "盤中價的來源近期無法正常取用，本產品暫停查詢一段時間，這檔改用 {MM/DD} 收盤價計算。"],
  [5, "C2_3_NOT_OBTAINED_BADGE", "未取得盤中價"],
  [6, "C2_3_NOT_OBTAINED_TOOLTIP", "這次沒有取得這檔的盤中價，改用 {MM/DD} 收盤價計算。"],
  [7, "C2_4_FAILED_CHECK_BADGE", "盤中價未通過檢查"],
  [8, "C2_4_FAILED_CHECK_TOOLTIP", "取得的盤中價未通過本產品的資料檢查（例如價格超出檢查範圍、時間異常或來源更新停滯），因此不採用，改用 {MM/DD} 收盤價計算。"],
  [9, "C2_5_BOARD_UNKNOWN_TOOLTIP", "本產品無法判定這檔屬於上市或上櫃，因此不查詢盤中價，改用 {MM/DD} 收盤價計算。"],
  [10, "C2_6_DEMO_SERIES_TOOLTIP", "示範持倉的價格為模擬資料，不查詢盤中價。"],
  [11, "C2_7_US_CLOSE_ONLY", "美股目前只提供收盤價，不查詢盤中價。"],
  [12, "C2_8_ALL_UNAVAILABLE_LINE", "盤中價目前無法取得，總計全部以各檔收盤價計算。"],
  [13, "C3_1_BASIS_MIXED", "估值基準：含 {N} 檔盤中價、{M} 檔收盤價，各檔價格時點不同"],
  [14, "C3_2_BASIS_ALL_INTRADAY_RANGE", "估值基準：{N} 檔皆為盤中價，成交時間 {HH:mm}～{HH:mm}"],
  [15, "C3_2_BASIS_ALL_INTRADAY_SINGLE", "估值基準：{N} 檔皆為盤中價，成交時間 {HH:mm}"],
  [16, "C4_1_RISK_GAUGE_SINGLE_DAY_WITH_INTRADAY", "本卡以 {MM/DD} 收盤計算，不含盤中價，數字可能與總資產卡不同。"],
  [17, "C4_1_RISK_GAUGE_DATE_RANGE_WITH_INTRADAY", "本卡以 {MM/DD}～{MM/DD} 收盤計算，不含盤中價，數字可能與總資產卡不同。"],
  [18, "C4_2_SECTOR_MOMENTUM_WITH_INTRADAY", "本卡以 {MM/DD} 收盤計算，不含盤中價。"],
  [19, "C5_2_CARD_BASIS_MIXED", "含 {N} 檔盤中價、{M} 檔收盤價"],
  [20, "C5_2_CARD_BASIS_ALL_INTRADAY", "{N} 檔皆為盤中價"],
  [21, "C6_SENTENCE_2_OVERVIEW_NOT_IN_PAGE_EVALUATION", "總覽頁持倉估值所用的盤中價（可能有延遲）不納入本頁評估。"],
  [22, "C8_1_MARKET_CELL", "TW（盤中價）"],
  [23, "PENDING_PRECONDITION_C8_2_SENTENCE_1", "台股盤中價讀取自臺灣證券交易所基本市況報導網站（TWSE MIS）網頁所用的資料介面。"],
  [24, "PENDING_PRECONDITION_C8_2_SENTENCE_3", "盤中價只用於總覽頁的持倉估值顯示，不用於風險上限、警示、建議、訊號與回測。"],
  [25, "PENDING_PRECONDITION_C10_1", "本產品採用盤中價的時段已結束，尚未取得當日收盤資料，目前顯示 {MM/DD} 收盤價，不使用今日成交價。"],
  [26, "C12_1_AUTO_REFRESH", "盤中價約每 {N} 秒自動重新載入一次，分頁在背景時暫停；重新載入不改變來源資料本身的延遲。"],
  [27, "C12_2_NO_AUTO_REFRESH", "盤中價不會定時自動重新載入，只在開啟頁面、切回此分頁等情況下重新載入；重新載入不改變來源資料本身的延遲。"],
  [28, "C15_1_ALERT_WITH_DATE", "警示以 {MM/DD} 收盤評估，不隨盤中價變動。"],
  [29, "C15_1_ALERT_NO_DATE", "警示以收盤資料評估，不隨盤中價變動。"],
  [30, "C15_2_ADVICE_CARD", "本卡以 {MM/DD} 收盤資料評估，不使用盤中價。"],
];

/**
 * The allowlist the scans compare against is this pinned table, never the
 * module's own array: otherwise editing a sentence in the source would move
 * the allowlist with it and the scan could not notice.
 */
const PINNED_SENTENCES: readonly string[] = PINNED.map(([, , literal]) => literal);

const C6_SENTENCE_2_NAME = "C6_SENTENCE_2_OVERVIEW_NOT_IN_PAGE_EVALUATION";
const PENDING_NAMES = [
  "PENDING_PRECONDITION_C8_2_SENTENCE_1",
  "PENDING_PRECONDITION_C8_2_SENTENCE_3",
  "PENDING_PRECONDITION_C10_1",
];
const PENDING_LITERALS = [
  "台股盤中價讀取自臺灣證券交易所基本市況報導網站（TWSE MIS）網頁所用的資料介面。",
  "盤中價只用於總覽頁的持倉估值顯示，不用於風險上限、警示、建議、訊號與回測。",
  "本產品採用盤中價的時段已結束，尚未取得當日收盤資料，目前顯示 {MM/DD} 收盤價，不使用今日成交價。",
];
const NEW_FORBIDDEN_TERMS = [
  "即時價",
  "即時行情",
  "即時股價",
  "即時更新",
  "即時顯示",
  "即時同步",
  "實時",
  "最新成交",
  "及時",
  "零延遲",
  "無延遲",
];

function exportedValue(name: string): unknown {
  for (const [key, value] of Object.entries(intraday)) {
    if (key === name) return value;
  }
  return undefined;
}

// ---------------------------------------------------------------------------
// 1. The 30 sentences, pinned verbatim.
// ---------------------------------------------------------------------------

describe("intradayWording — 30 句允許清單逐字釘住", () => {
  it("釘住表本身有 30 列、編號 1..30、字面不重複", () => {
    expect(PINNED).toHaveLength(30);
    expect(PINNED.map(([n]) => n)).toEqual(Array.from({ length: 30 }, (_, i) => i + 1));
    expect(new Set(PINNED.map(([, , literal]) => literal)).size).toBe(30);
  });

  it.each(PINNED)("#%i %s 常數字面逐字相等", (_n, name, literal) => {
    expect(exportedValue(name)).toBe(literal);
  });

  it("INTRADAY_ALLOWED_SENTENCES 與釘住表逐句、依序相等（共 30 句）", () => {
    expect(INTRADAY_ALLOWED_SENTENCES).toHaveLength(30);
    expect([...INTRADAY_ALLOWED_SENTENCES]).toEqual(PINNED.map(([, , literal]) => literal));
  });

  it("模組只匯出這 30 個字串常數：沒有清單以外的字串（含「盤中」或不含）混進來", () => {
    const stringExports = Object.entries(intraday)
      .filter(([, value]) => typeof value === "string")
      .map(([key]) => key)
      .sort();
    expect(stringExports).toEqual(PINNED.map(([, name]) => name).sort());
  });

  it("30 句每一句都含「盤中」，且切句後恰為自己一句（整句比對的前提）", () => {
    for (const sentence of INTRADAY_ALLOWED_SENTENCES) {
      expect(sentence, sentence).toContain(TERM);
      expect(splitWordingSentences(sentence), sentence).toEqual([sentence]);
    }
  });

  it("占位符保留字面；還原成模板逐字相等（無參數、或以占位符字面回填）", () => {
    const identity = { N: "{N}", M: "{M}", "MM/DD": "{MM/DD}", "HH:mm": "{HH:mm}", "HH:mm:ss": "{HH:mm:ss}" };
    for (const sentence of INTRADAY_ALLOWED_SENTENCES) {
      expect(fillIntradayTemplate(sentence), sentence).toBe(sentence);
      expect(fillIntradayTemplate(sentence, identity), sentence).toBe(sentence);
    }
  });

  it("fillIntradayTemplate 回填：數字與字串、單趟取代、值不被再次展開", () => {
    expect(fillIntradayTemplate(intraday.C1_1_PRICE_LABEL, { "HH:mm": "09:05" })).toBe("盤中 09:05 成交");
    expect(
      fillIntradayTemplate(intraday.C3_1_BASIS_MIXED, { N: 2, M: 3 }),
    ).toBe("估值基準：含 2 檔盤中價、3 檔收盤價，各檔價格時點不同");
    expect(
      fillIntradayTemplate(intraday.C3_2_BASIS_ALL_INTRADAY_RANGE, { N: 4, "HH:mm": "09:05" }),
    ).toBe("估值基準：4 檔皆為盤中價，成交時間 09:05～09:05");
    expect(fillIntradayTemplate(intraday.C15_2_ADVICE_CARD, { "MM/DD": "10/03" })).toBe(
      "本卡以 10/03 收盤資料評估，不使用盤中價。",
    );
    // a value that looks like a placeholder is inert (single pass)
    expect(fillIntradayTemplate(intraday.C5_2_CARD_BASIS_ALL_INTRADAY, { N: "{M}", M: 9 })).toBe(
      "{M} 檔皆為盤中價",
    );
    // {HH:mm:ss} is not eaten by {HH:mm}
    expect(fillIntradayTemplate("{HH:mm:ss}|{HH:mm}", { "HH:mm": "A", "HH:mm:ss": "B" })).toBe("B|A");
  });
});

// ---------------------------------------------------------------------------
// 2. 「盤中」 scope scan over non-test sources (condition (c), section 12 point 2).
// ---------------------------------------------------------------------------

function listNonTestSources(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "__tests__" || entry === "node_modules" || entry === ".next") continue;
      files.push(...listNonTestSources(full));
    } else if (/\.(ts|tsx)$/.test(entry) && !/\.test\.(ts|tsx)$/.test(entry)) {
      files.push(full);
    }
  }
  return files;
}

function appRelative(file: string): string {
  return relative(APP_ROOT, file).split(sep).join("/");
}

const DOUBLE_QUOTED_LITERAL = /"(?:[^"\\\n]|\\.)*"/g;

/**
 * Violations in the single-source file: every string literal containing the
 * term must consist, after splitting into sentences, of sentences that either
 * lack the term or are whole allowlist sentences; the term may not appear
 * outside a double-quoted literal at all; other quote styles are refused so
 * nothing hides from the literal scanner.
 */
function intradayFileViolations(source: string, allowed: readonly string[]): string[] {
  const stripped = stripComments(source);
  const violations: string[] = [];
  if (stripped.includes("`") || stripped.includes("'")) {
    violations.push("file uses a backtick or single quote; only double-quoted literals are scannable");
  }
  const allowedSet = new Set(allowed);
  for (const literal of stripped.match(DOUBLE_QUOTED_LITERAL) ?? []) {
    const decoded: unknown = JSON.parse(literal);
    if (typeof decoded !== "string" || !decoded.includes(TERM)) continue;
    for (const sentence of splitWordingSentences(decoded)) {
      if (sentence.includes(TERM) && !allowedSet.has(sentence)) {
        violations.push(`not an allowlist sentence: ${JSON.stringify(sentence)}`);
      }
    }
  }
  if (stripped.replace(DOUBLE_QUOTED_LITERAL, "").includes(TERM)) {
    violations.push("term appears outside a double-quoted string literal");
  }
  return violations;
}

/** The only legal spot in `adviceWording.ts`: one `"盤中"` element of the banned-term array. */
function adviceFileViolations(source: string): string[] {
  const stripped = stripComments(source);
  const occurrences = stripped.split(TERM).length - 1;
  const violations: string[] = [];
  if (occurrences !== 1) {
    violations.push(`expected exactly 1 occurrence, found ${occurrences}`);
  }
  const start = stripped.indexOf("export const FRONTEND_FORBIDDEN_TERMS");
  const end = start === -1 ? -1 : stripped.indexOf("\n];", start);
  const block = start === -1 || end === -1 ? "" : stripped.slice(start, end);
  if (!/^\s*"盤中",\s*$/m.test(block)) {
    violations.push('no `"盤中",` array element inside FRONTEND_FORBIDDEN_TERMS');
  }
  if (occurrences === 1 && !block.includes(TERM)) {
    violations.push("the single occurrence is outside FRONTEND_FORBIDDEN_TERMS");
  }
  return violations;
}

function scopeViolations(files: ReadonlyArray<{ path: string; source: string }>): string[] {
  const violations: string[] = [];
  for (const { path, source } of files) {
    if (path === INTRADAY_FILE) {
      violations.push(...intradayFileViolations(source, PINNED_SENTENCES).map((v) => `${path}: ${v}`));
    } else if (path === ADVICE_FILE) {
      violations.push(...adviceFileViolations(source).map((v) => `${path}: ${v}`));
    } else if (stripComments(source).includes(TERM)) {
      violations.push(`${path}: contains the term`);
    }
  }
  return violations;
}

const SOURCES = listNonTestSources(APP_ROOT).map((file) => ({
  path: appRelative(file),
  source: readFileSync(file, "utf-8"),
}));

describe("「盤中」範圍掃描（條件 (c)：app 下非測試 .ts/.tsx，去註解）", () => {
  it("掃描確實涵蓋到兩個豁免檔，且不含 __tests__（掃描不是空轉）", () => {
    const paths = SOURCES.map((s) => s.path);
    expect(paths).toContain(INTRADAY_FILE);
    expect(paths).toContain(ADVICE_FILE);
    expect(paths.length).toBeGreaterThan(20);
    expect(paths.filter((p) => p.includes("__tests__") || /\.test\./.test(p))).toEqual([]);
  });

  it("目前 repo：除兩個豁免處外，沒有任何非測試檔含「盤中」", () => {
    expect(scopeViolations(SOURCES)).toEqual([]);
  });

  it("FRONTEND_FORBIDDEN_TERMS 仍保留「盤中」（條件 (a)），且只出現一次", () => {
    expect(FRONTEND_FORBIDDEN_TERMS.filter((t) => t === TERM)).toHaveLength(1);
  });

  describe("掃描器本身會紅燈（合成檔案）", () => {
    const allowed = PINNED_SENTENCES;
    const lit = (s: string) => `export const X = ${JSON.stringify(s)};`;

    it("其他檔案出現「盤中」（字面、JSX 文字、識別字旁）一律紅燈", () => {
      expect(scopeViolations([{ path: "components/Foo.tsx", source: lit("盤中價") }])).toHaveLength(1);
      expect(scopeViolations([{ path: "components/Foo.tsx", source: "<p>盤中 09:05 成交</p>" }])).toHaveLength(1);
    });

    it("註解內的「盤中」不算（去註解後掃描）", () => {
      const source = "// 盤中 is discussed here\n/* 盤中 */\nexport const X = 1;";
      expect(scopeViolations([{ path: "components/Foo.tsx", source }])).toEqual([]);
    });

    it("intradayWording.ts：加前綴、加後綴、截斷、串接拆句都紅燈；整句相等放行", () => {
      const ok = allowed[2] ?? "";
      expect(intradayFileViolations(lit(ok), allowed)).toEqual([]);
      expect(intradayFileViolations(lit("請注意：" + ok), allowed)).toHaveLength(1);
      expect(intradayFileViolations(lit(ok + "，數字準確"), allowed)).toHaveLength(1);
      expect(intradayFileViolations(lit(ok.slice(0, -1)), allowed)).toHaveLength(1);
      const s = allowed[1] ?? "";
      const half = Math.floor(s.length / 2);
      const concatenated = `export const X = ${JSON.stringify(s.slice(0, half))} + ${JSON.stringify(s.slice(half))};`;
      expect(intradayFileViolations(concatenated, allowed).length).toBeGreaterThan(0);
    });

    it("intradayWording.ts：跨句字面中，每個含「盤中」的句子都要在清單內", () => {
      const a = allowed[20] ?? "";
      expect(intradayFileViolations(lit(a + "另一句盤中價。"), allowed)).toHaveLength(1);
      expect(intradayFileViolations(lit(a + "另一句不相干。"), allowed)).toEqual([]);
    });

    it("intradayWording.ts：模板字串、單引號、字面外的「盤中」都紅燈", () => {
      expect(intradayFileViolations("export const X = `盤中價`;", allowed).length).toBeGreaterThan(0);
      expect(intradayFileViolations("export const X = '盤中價';", allowed).length).toBeGreaterThan(0);
      expect(intradayFileViolations("const 盤中 = 1;", allowed).length).toBeGreaterThan(0);
    });

    it("adviceWording.ts：禁用詞陣列的那一個元素放行；第二處、重打 C6 句 2 一律紅燈", () => {
      const arrayOnly = 'export const FRONTEND_FORBIDDEN_TERMS: readonly string[] = [\n  "立即",\n  "盤中",\n];';
      expect(adviceFileViolations(arrayOnly)).toEqual([]);
      const retyped = arrayOnly + "\n" + lit(allowed[20] ?? "");
      expect(adviceFileViolations(retyped).length).toBeGreaterThan(0);
      const noElement = 'export const FRONTEND_FORBIDDEN_TERMS: readonly string[] = [\n  "立即",\n];\n' + lit("盤中價");
      expect(adviceFileViolations(noElement).length).toBeGreaterThan(0);
      const outsideArray = 'export const FRONTEND_FORBIDDEN_TERMS: readonly string[] = [\n  "立即",\n];\n' + lit("x") + '\nconst a = "盤中";';
      expect(adviceFileViolations(outsideArray).length).toBeGreaterThan(0);
    });
  });
});

// ---------------------------------------------------------------------------
// 3. Allowlist sentences vs the remaining banned terms (condition (d)).
// ---------------------------------------------------------------------------

describe("允許清單句仍須過其餘禁用詞與裸「即時」掃描（條件 (d)）", () => {
  const otherTerms = FRONTEND_FORBIDDEN_TERMS.filter((t) => t !== TERM);

  it.each(PINNED)("#%i %s：不含「盤中」以外的任何禁用詞", (_n, _name, literal) => {
    for (const term of otherTerms) {
      expect(literal, `contains banned term ${JSON.stringify(term)}`).not.toContain(term);
    }
  });

  it.each(PINNED)("#%i %s：沒有裸「即時」（「非即時」才放行）", (_n, _name, literal) => {
    expect(findBareRealtimeClaims(literal)).toEqual([]);
  });

  it("整批以「整句相等豁免」掃描：無違規", () => {
    const joined = PINNED_SENTENCES.join("\n");
    expect(
      findForbiddenTermsExceptAllowedSentences(joined, FRONTEND_FORBIDDEN_TERMS, TERM, PINNED_SENTENCES),
    ).toEqual([]);
  });

  it("整句相等豁免不是子字串遮罩：核可句前後加字、拆句後非整句，一律仍被擋", () => {
    const short = intraday.C2_2_COOLDOWN_BADGE;
    const tw = intraday.C8_1_MARKET_CELL;
    const run = (text: string) =>
      findForbiddenTermsExceptAllowedSentences(text, FRONTEND_FORBIDDEN_TERMS, TERM, PINNED_SENTENCES);
    expect(run(short)).toEqual([]);
    expect(run(`請看${short}`)).toHaveLength(1);
    expect(run(`${short}，保證獲利`).length).toBeGreaterThan(0);
    expect(run(`${tw}。`)).toHaveLength(1);
    expect(run(`美股 ${tw}`)).toHaveLength(1);
    // joined by a newline or a period the approved sentences are separate sentences again
    expect(run(`${short}\n${tw}`)).toEqual([]);
    // an approved sentence is still scanned for every other term (condition (d))
    expect(run("盤中價暫停查詢")).toEqual([]);
    expect(
      findForbiddenTermsExceptAllowedSentences("盤中價暫停查詢", [...FRONTEND_FORBIDDEN_TERMS, "暫停"], TERM, [
        "盤中價暫停查詢",
      ]),
    ).toHaveLength(1);
  });

  it("splitWordingSentences：以「。」（保留在句尾）與換行切分，無句號者為整則", () => {
    expect(splitWordingSentences("甲。乙。丙")).toEqual(["甲。", "乙。", "丙"]);
    expect(splitWordingSentences("資料日期 10/03（日線收盤，非即時）\n美股目前只提供收盤價，不查詢盤中價。")).toEqual([
      "資料日期 10/03（日線收盤，非即時）",
      "美股目前只提供收盤價，不查詢盤中價。",
    ]);
    expect(splitWordingSentences("")).toEqual([]);
  });
});

describe("P13 新增禁用詞（11 個）", () => {
  it.each(NEW_FORBIDDEN_TERMS)("FRONTEND_FORBIDDEN_TERMS 含 %j", (term) => {
    expect(FRONTEND_FORBIDDEN_TERMS).toContain(term);
  });

  it("「盤中」以及 P13 之前的即時性禁用詞全部保留", () => {
    for (const term of ["real-time", "盤中", "最新報價", "最新股價", "最新行情"]) {
      expect(FRONTEND_FORBIDDEN_TERMS).toContain(term);
    }
  });

  it("清單無重複；「即時報價」不加入禁用詞（由裸「即時」規則處理）", () => {
    expect(new Set(FRONTEND_FORBIDDEN_TERMS).size).toBe(FRONTEND_FORBIDDEN_TERMS.length);
    expect(FRONTEND_FORBIDDEN_TERMS).not.toContain("即時報價");
    expect(FRONTEND_FORBIDDEN_TERMS).not.toContain("即時");
  });
});

// ---------------------------------------------------------------------------
// 4. Call-site guards (section 12 point 3, R1-4) and the C6 "not wired" record.
// ---------------------------------------------------------------------------

function referencingFiles(pattern: RegExp): string[] {
  return SOURCES.filter(({ path, source }) => path !== INTRADAY_FILE && pattern.test(stripComments(source))).map(
    ({ path }) => path,
  );
}

describe("呼叫點守門：PENDING_PRECONDITION（#23、#24、#25）", () => {
  it("三個常數存在、字面逐字相等，且都在允許清單內", () => {
    expect(PENDING_NAMES.map(exportedValue)).toEqual(PENDING_LITERALS);
    expect([...PENDING_PRECONDITION_SENTENCES]).toEqual(PENDING_LITERALS);
    for (const literal of PENDING_LITERALS) {
      expect(INTRADAY_ALLOWED_SENTENCES).toContain(literal);
    }
  });

  it("所有以 PENDING_PRECONDITION 為名的匯出就是這三個加彙總陣列（沒有漏網的待前置常數）", () => {
    const pendingExports = Object.keys(intraday)
      .filter((k) => k.startsWith("PENDING_PRECONDITION"))
      .sort();
    expect(pendingExports).toEqual([...PENDING_NAMES, "PENDING_PRECONDITION_SENTENCES"].sort());
  });

  it("目前任何非測試檔都不得引用 PENDING_PRECONDITION 常數", () => {
    // Lifting this guard belongs in the same PR that lifts the precondition and re-sends to risk.
    expect(referencingFiles(/PENDING_PRECONDITION/)).toEqual([]);
  });

  it("也不得以 namespace import、動態 import、require 繞過（任何非測試檔都不得 import * 自 intradayWording）", () => {
    expect(referencingFiles(/import\s*\*\s*as\s+\w+\s+from\s+["'][^"']*intradayWording["']/)).toEqual([]);
    expect(referencingFiles(/import\s*\(\s*["'][^"']*intradayWording["']\s*\)/)).toEqual([]);
    expect(referencingFiles(/require\s*\(\s*["'][^"']*intradayWording["']\s*\)/)).toEqual([]);
  });

  it("也不得以 INTRADAY_ALLOWED_SENTENCES 取得待前置句（該陣列只供測試與掃描）", () => {
    expect(referencingFiles(/INTRADAY_ALLOWED_SENTENCES/)).toEqual([]);
  });
});

describe("C6 句 2（#21）尚未接線的現況記錄（I-27：與 W15 同一個 PR 才改）", () => {
  it("目前沒有任何非測試檔引用 C6 句 2 常數", () => {
    // W15 changes this expectation to ["lib/adviceWording.ts"] in the same PR (R1-4: only adviceWording.ts may import it).
    expect(referencingFiles(new RegExp(C6_SENTENCE_2_NAME))).toEqual([]);
  });

  it("adviceWording.ts 目前沒有 import intradayWording", () => {
    const advice = SOURCES.find((s) => s.path === ADVICE_FILE);
    expect(advice).toBeDefined();
    expect(stripComments(advice?.source ?? "")).not.toMatch(/intradayWording/);
  });

  it("NON_REALTIME_NOTICE 目前仍是舊版字面：不含 C6 句 2、不含「盤中」（W15 才改成四句）", () => {
    expect(NON_REALTIME_NOTICE).not.toContain(intraday.C6_SENTENCE_2_OVERVIEW_NOT_IN_PAGE_EVALUATION);
    expect(NON_REALTIME_NOTICE).not.toContain(TERM);
    expect(NON_REALTIME_NOTICE.startsWith("本產品採免費日線資料源，非即時報價系統；台股日線為盤後資料。")).toBe(true);
  });
});
