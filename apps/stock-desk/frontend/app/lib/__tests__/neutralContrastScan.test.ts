/**
 * Contrast scan for the stock page (art-lead 2026-10-04, batch 2 of
 * `work/stock-desk-個股頁-對比提亮-第二三批-art-lead-裁示-2026-10-04.md`).
 *
 * Rule: informational text (explanations, disclosures, assumptions, timestamps, sources, data
 * values, headers, empty states) is at least `text-neutral-400`. On `#0a0a0a`, 500 is ~4.2:1 (below
 * AA 4.5) and ~3.8:1 on card backgrounds; 600 is ~2.5:1 and must not be used for any text.
 *
 * Inside `app/position/**`, `text-neutral-(500|600)` is therefore allowed only for:
 *   1. uppercase `tracking-wide` group headings set in Latin letters (uppercase has no effect on CJK
 *      and 12px 500 is below AA, so the former CJK h4 exception was withdrawn in batch 4 and those
 *      two headings are now `text-neutral-400`; the allowance is kept only for Latin-letter titles);
 *   2. genuinely disabled controls (`disabled:text-neutral-*` variants only);
 * Backgrounds and divider lines are not matched at all (`bg-` / `border-` utilities are not `text-`).
 *
 * Batch 3 (labels and controls: drag table row headers, PriceLadder thead, RangeGauge range label,
 * OperationSummaryPanel "依據：" prefix, inactive chart tab) has been lifted to `text-neutral-400`
 * and its temporary exception table is gone; nothing but the permanent whitelist remains.
 */

import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/** Same definition as componentWordingScan.test.ts `stripComments` (block + JSX comments, whole-line `//`). */
const stripComments = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const APP_DIR = fileURLToPath(new URL("../../", import.meta.url));
const TEXT_LOW_CONTRAST = /text-neutral-(500|600)/;
const TEXT_LOW_CONTRAST_GLOBAL = /text-neutral-(500|600)/g;

const positionFiles: string[] = readdirSync(APP_DIR, { recursive: true, encoding: "utf8" })
  .map((p) => p.split("\\").join("/"))
  .filter((rel) => rel.startsWith("position/") && /\.(ts|tsx)$/.test(rel))
  .filter((rel) => !rel.split("/").includes("__tests__") && !/\.test\.[^/]*$/.test(rel))
  .sort();

const codeOf = (rel: string) => stripComments(readFileSync(`${APP_DIR}${rel}`, "utf8"));

/**
 * Permanent whitelist: uppercase tracking-wide group headings (reserved for Latin-letter titles;
 * no CJK heading may rely on it), and disabled-only variants.
 */
function isPermanentlyAllowed(line: string): boolean {
  if (/\buppercase\b/.test(line) && /\btracking-wide\b/.test(line)) return true;
  const matches = line.match(/([\w:-]*)text-neutral-(?:500|600)/g) ?? [];
  return matches.length > 0 && matches.every((m) => m.startsWith("disabled:"));
}

/** Lines that hit `text-neutral-(500|600)` and are not on the permanent whitelist. */
function findViolations(_rel: string, code: string): string[] {
  return code
    .split("\n")
    .map((l, i) => ({ text: l.trim(), no: i + 1 }))
    .filter(({ text }) => TEXT_LOW_CONTRAST.test(text))
    .filter(({ text }) => !isPermanentlyAllowed(text))
    .map(({ text, no }) => `L${no}: ${text}`);
}

describe("對比掃描（art-lead 批次 2）：app/position/** 內 text-neutral-(500|600) 只允許白名單", () => {
  it("掃描清單非空，含批次 2 觸及的檔案；不含測試檔", () => {
    expect(positionFiles.length).toBeGreaterThan(0);
    for (const f of [
      "position/[symbol]/LeverageChapterView.tsx",
      "position/[symbol]/page.tsx",
      "position/[symbol]/AdviceCardView.tsx",
      "position/[symbol]/LimitsCheckList.tsx",
      "position/[symbol]/DecisionCard.tsx",
      "position/[symbol]/OperationSummaryPanel.tsx",
      "position/[symbol]/TradingViewChartPanel.tsx",
      "position/[symbol]/PriceChart.tsx",
    ]) {
      expect(positionFiles, f).toContain(f);
    }
    for (const rel of positionFiles) expect(rel).not.toMatch(/__tests__|\.test\./);
  });

  for (const rel of positionFiles) {
    it(`${rel}：無白名單以外的 text-neutral-500／600`, () => {
      expect(findViolations(rel, codeOf(rel))).toEqual([]);
    });
  }

  it("批次 3 已提亮：各項來源行改為 text-neutral-400，次數吻合", () => {
    const lifted: ReadonlyArray<{ rel: string; line: string; count: number }> = [
      { rel: "position/[symbol]/LeverageChapterView.tsx", line: '<th scope="row" className="py-1 pr-4 font-normal text-neutral-400">', count: 8 },
      { rel: "position/[symbol]/PriceLadder.tsx", line: '<tr className="border-b border-neutral-800 text-xs text-neutral-400">', count: 1 },
      { rel: "position/[symbol]/RangeGauge.tsx", line: '<span className="whitespace-nowrap text-neutral-400">{rangeLabel}</span>', count: 1 },
      { rel: "position/[symbol]/OperationSummaryPanel.tsx", line: '<span className="text-neutral-400">{RULE_BASIS_PREFIX}</span>', count: 1 },
      { rel: "position/[symbol]/page.tsx", line: ': "border-transparent text-neutral-400 hover:text-neutral-300"', count: 1 },
    ];
    for (const { rel, line, count } of lifted) {
      expect(positionFiles, rel).toContain(rel);
      const lines = codeOf(rel)
        .split("\n")
        .map((l) => l.trim());
      expect(lines.filter((l) => l === line).length, `${rel} ${line}`).toBe(count);
    }
  });

  it("app/position 不再有任何 text-neutral-500 文字", () => {
    // Exclude disabled: variants so a future legitimate disabled control does not
    // trip this pin; no other text-neutral-(500|600) hit may remain anywhere.
    const remaining = positionFiles.flatMap((rel) =>
      codeOf(rel)
        .split("\n")
        .map((l) => l.trim())
        .filter((l) => TEXT_LOW_CONTRAST.test(l))
        .filter((l) => !/disabled:text-neutral-(500|600)/.test(l) || /(^|\s)text-neutral-(500|600)/.test(l))
        .map((l) => `${rel} :: ${l}`),
    );
    expect(remaining).toEqual([]);
  });

  it("text-neutral-600 不得用於任何文字（disabled 變體除外）", () => {
    for (const rel of positionFiles) {
      const hits = (codeOf(rel).match(/([\w:-]*)text-neutral-600/g) ?? []).filter((m) => !m.startsWith("disabled:"));
      expect(hits, rel).toEqual([]);
    }
  });

  describe("掃描本身有牙：合成輸入", () => {
    it("命中一般文字的 500／600（含 hover: 等變體），放過 tracking-wide 大寫標題與 disabled 變體", () => {
      const v = (line: string) => findViolations("position/[symbol]/__synthetic__.tsx", line);
      expect(v('<p className="text-xs text-neutral-500">x</p>')).toHaveLength(1);
      expect(v('<p className="text-xs text-neutral-600">x</p>')).toHaveLength(1);
      expect(v('<a className="hover:text-neutral-500">x</a>')).toHaveLength(1);
      expect(v('<p className="text-xs text-neutral-400">x</p>')).toEqual([]);
      expect(v('<h4 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">x</h4>')).toEqual([]);
      expect(v('<button className="disabled:text-neutral-600">x</button>')).toEqual([]);
      expect(v('<button className="disabled:text-neutral-600 text-neutral-500">x</button>')).toHaveLength(1);
      expect(v('<div className="border-neutral-600 bg-neutral-500">x</div>')).toEqual([]);
    });

    it("註解內的 text-neutral-500 不計（去註解後掃描）", () => {
      expect(findViolations("position/[symbol]/__synthetic__.tsx", stripComments("// text-neutral-500\n{/* text-neutral-600 */}"))).toEqual([]);
      expect(TEXT_LOW_CONTRAST_GLOBAL.test("text-neutral-500")).toBe(true);
    });
  });
});
