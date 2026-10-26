import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * 風控 2026-10-26 裁定第 1 點 R1（required）— file-level guard for E-4.
 *
 * The L-10b guard in `componentWordingScan.test.ts` only checks that E-4's own
 * `<p>` line carries no `&&` / ternary. The `if (pending) return` added for the
 * first-load skeleton sits above that line and bypasses it, so a second early
 * return (or a wrapper around E-4) could silently hide E-4 again. This guard
 * reads the whole component body up to E-4 and pins that:
 *
 * - the only early return / conditional branch before E-4 is `if (pending)`;
 * - that pending branch renders neither the count nor E-4 nor E-1 (same in,
 *   same out: E-4 is withheld only together with the count);
 * - E-4 sits in the component's single main `return (`, inside no `{…}`
 *   expression container other than its own, and under intrinsic HTML tags
 *   only (no component wrapper that could decide to drop its children).
 *
 * The guard is self-tested against mutated copies of the real source so it
 * cannot silently pass on everything.
 */

const PANEL_PATH = "../../position/[symbol]/EntryObservationPanel.tsx";
const panelSrc = readFileSync(fileURLToPath(new URL(PANEL_PATH, import.meta.url)), "utf8");

const E4_CALL = "buildDataAsOfLine(";
const OPENERS: Record<string, string> = { "(": ")", "{": "}", "[": "]" };
const CLOSERS = new Set([")", "}", "]"]);

/**
 * Blanks out comments and string / template literal bodies with spaces
 * (newlines kept), so brackets, keywords and identifiers inside them are not
 * counted while every index still points at the same place in the source.
 */
function blankCommentsAndStrings(src: string): string {
  const out = src.split("");
  let i = 0;
  const blank = (from: number, to: number) => {
    for (let k = from; k < to; k += 1) if (out[k] !== "\n") out[k] = " ";
  };
  while (i < src.length) {
    const two = src.slice(i, i + 2);
    if (two === "//") {
      const end = src.indexOf("\n", i);
      const stop = end === -1 ? src.length : end;
      blank(i, stop);
      i = stop;
    } else if (two === "/*") {
      const end = src.indexOf("*/", i + 2);
      const stop = end === -1 ? src.length : end + 2;
      blank(i, stop);
      i = stop;
    } else if (src[i] === '"' || src[i] === "'" || src[i] === "`") {
      const quote = src[i];
      let j = i + 1;
      while (j < src.length && src[j] !== quote) j += src[j] === "\\" ? 2 : 1;
      blank(i + 1, j);
      i = j + 1;
    } else {
      i += 1;
    }
  }
  return out.join("");
}

/** Index of the bracket that closes the one opened at `open`, or -1. */
function matchingClose(clean: string, open: number): number {
  const stack: string[] = [];
  for (let i = open; i < clean.length; i += 1) {
    const ch = clean[i];
    if (ch in OPENERS) stack.push(OPENERS[ch]);
    else if (CLOSERS.has(ch)) {
      if (stack.pop() !== ch) return -1;
      if (stack.length === 0) return i;
    }
  }
  return -1;
}

const count = (text: string, pattern: RegExp) => (text.match(pattern) ?? []).length;

/** Every violation of the R1 file-level contract; empty means the source complies. */
function e4GuardViolations(src: string): string[] {
  const violations: string[] = [];
  const clean = blankCommentsAndStrings(src);

  const compStart = clean.indexOf("export function EntryObservationPanel(");
  if (compStart === -1) return ["EntryObservationPanel not found"];
  const paramsOpen = clean.indexOf("(", compStart);
  const paramsClose = matchingClose(clean, paramsOpen);
  const bodyOpen = clean.indexOf("{", paramsClose);
  const bodyClose = matchingClose(clean, bodyOpen);
  if (paramsClose === -1 || bodyOpen === -1 || bodyClose === -1) return ["component body not parseable"];
  const body = clean.slice(bodyOpen + 1, bodyClose);
  const bodyOffset = bodyOpen + 1;

  // Exactly one E-4 call in the component.
  const e4Count = body.split(E4_CALL).length - 1;
  if (e4Count !== 1) return [`E-4 must be rendered exactly once in the component, found ${e4Count}`];
  const e4 = bodyOffset + body.indexOf(E4_CALL);
  const before = clean.slice(bodyOffset, e4);

  // The only conditional branch before E-4 is `if (pending)`.
  const ifs = count(before, /\bif\s*\(/g);
  const pendingIf = /\bif\s*\(\s*pending\s*\)\s*\{/.exec(before);
  if (ifs !== 1 || pendingIf === null) {
    violations.push(`exactly one \`if\` before E-4, and it must be \`if (pending) {\`; found ${ifs} \`if\`(s), pending form ${pendingIf === null ? "absent" : "present"}`);
  }
  for (const [name, pattern] of [
    ["else", /\belse\b/g],
    ["switch", /\bswitch\b/g],
    ["throw", /\bthrow\b/g],
    ["try", /\btry\b/g],
  ] as const) {
    if (count(before, pattern) > 0) violations.push(`no \`${name}\` allowed before E-4`);
  }

  // Early returns: one inside the pending block, then the single main `return (`.
  const returns = [...before.matchAll(/\breturn\b/g)].map((m) => bodyOffset + (m.index ?? 0));
  if (returns.length !== 2) violations.push(`expected exactly 2 \`return\` before E-4 (pending + main), found ${returns.length}`);
  if (pendingIf !== null) {
    const blockOpen = bodyOffset + pendingIf.index + pendingIf[0].length - 1;
    const blockClose = matchingClose(clean, blockOpen);
    const block = clean.slice(blockOpen, blockClose + 1);
    if (count(block, /\breturn\b/g) !== 1) violations.push("the pending block must hold exactly one `return`");
    for (const forbidden of ["buildConditionCount(", E4_CALL, "ENTRY_E1_QUALIFIER", "STATUS_GLYPH"]) {
      if (block.includes(forbidden)) violations.push(`the pending block must not render \`${forbidden}\``);
    }
    if (returns.length === 2 && !(returns[0] > blockOpen && returns[0] < blockClose && returns[1] > blockClose)) {
      violations.push("the first `return` must be inside the pending block and the second after it");
    }
  }

  // E-4 hangs off the main `return (` with no conditional / iterating container.
  const mainReturn = returns.at(-1);
  if (mainReturn === undefined) return violations;
  const afterReturn = clean.slice(mainReturn + "return".length);
  const parenOffset = afterReturn.search(/\S/);
  if (afterReturn[parenOffset] !== "(") {
    violations.push("the main return must be `return (` (no ternary / logical expression around the JSX)");
    return violations;
  }
  const returnParen = mainReturn + "return".length + parenOffset;
  const e4Container = clean.lastIndexOf("{", e4);
  if (clean.slice(e4Container + 1, e4).trim() !== "") violations.push("E-4 must be the whole of its own `{…}` container");

  const brackets: number[] = [];
  const tags: string[] = [];
  let i = returnParen + 1;
  while (i < e4Container) {
    const ch = clean[i];
    if (ch in OPENERS) {
      brackets.push(i);
      i += 1;
    } else if (CLOSERS.has(ch)) {
      brackets.pop();
      i += 1;
    } else if (ch === "<" && brackets.length === 0) {
      if (clean[i + 1] === "/") {
        tags.pop();
        i = clean.indexOf(">", i) + 1;
        continue;
      }
      const name = /^<([A-Za-z][\w.]*)?/.exec(clean.slice(i))?.[1] ?? "<>";
      // Walk to the end of the opening tag, skipping `{…}` attribute expressions (they may hold `=>`).
      let j = i + 1;
      while (j < e4Container && clean[j] !== ">") j = clean[j] === "{" ? matchingClose(clean, j) + 1 : j + 1;
      if (clean[j - 1] !== "/") tags.push(name);
      i = j + 1;
    } else {
      i += 1;
    }
  }
  if (brackets.length > 0) {
    const wrappers = brackets.map((at) => clean.slice(Math.max(returnParen, at - 40), at + 1).trim().replace(/\s+/g, " "));
    violations.push(`E-4 is wrapped by an expression container: ${wrappers.join(" / ")}`);
  }
  const components = tags.filter((t) => !/^[a-z]/.test(t));
  if (components.length > 0) violations.push(`E-4 must sit under intrinsic HTML tags only, found ${components.join(", ")}`);
  if (!tags.includes("details")) violations.push("E-4 must sit inside <details>");
  return violations;
}

describe("風控 R1：EntryObservationPanel 在 E-4 之前唯一的提早 return／條件分支是 if (pending)", () => {
  it("the real source complies", () => {
    expect(e4GuardViolations(panelSrc)).toEqual([]);
  });

  describe("the guard rejects every way of hiding E-4 (self-test on mutated source)", () => {
    const E4_LINE = "<p>{buildDataAsOfLine(dataAsOfDates.bars, dataAsOfDates.signals, dataAsOfDates.advice)}</p>";
    const MAIN_PREAMBLE = "const showPriceUnit = observation.conditions.some(printsPriceValues);";

    const mutations: [string, (src: string) => string][] = [
      ["a second early return on a data value", (s) => s.replace(MAIN_PREAMBLE, `if (observation.allUnavailable) return null;\n  ${MAIN_PREAMBLE}`)],
      ["the pending condition widened", (s) => s.replace("if (pending) {", "if (pending || observation.allUnavailable) {")],
      ["the pending condition replaced", (s) => s.replace("if (pending) {", "if (dataAsOfDates.bars === dataAsOfDates.advice) {")],
      ["a second if-return after the pending check", (s) => s.replace(MAIN_PREAMBLE, `${MAIN_PREAMBLE}\n  if (bars === null) {\n    return null;\n  }`)],
      ["E-4 wrapped in &&", (s) => s.replace(E4_LINE, `{showPriceUnit && (${E4_LINE})}`)],
      ["E-4 wrapped in a ternary", (s) => s.replace(E4_LINE, `{bars ? ${E4_LINE} : null}`)],
      ["E-4 wrapped in a component", (s) => s.replace(E4_LINE, `<Show when={bars !== null}>${E4_LINE}</Show>`)],
      ["main return turned into a ternary", (s) => s.replace("  return (\n    <section", "  return observation.allUnavailable ? null : (\n    <section")],
      ["E-4 rendered in the pending skeleton", (s) => s.replace('<SkeletonBlock className="h-16 w-full" />', `<SkeletonBlock className="h-16 w-full" />${E4_LINE}`)],
      ["count rendered in the pending skeleton", (s) => s.replace('<SkeletonBlock className="h-16 w-full" />', '<SkeletonBlock className="h-16 w-full" />{buildConditionCount(0, 0)}')],
      ["E-4 removed", (s) => s.replace(E4_LINE, "")],
    ];

    for (const [label, mutate] of mutations) {
      it(label, () => {
        const mutated = mutate(panelSrc);
        expect(mutated, "mutation must actually change the source").not.toBe(panelSrc);
        expect(e4GuardViolations(mutated)).not.toEqual([]);
      });
    }

    it("comments and strings mentioning `if (`, `return` or brackets do not trip the guard", () => {
      const noisy = panelSrc.replace(
        MAIN_PREAMBLE,
        `// if (x) return null; { ( [\n  /* return ( if ( */\n  const noise = "if (a) { return } )";\n  ${MAIN_PREAMBLE}`,
      );
      expect(e4GuardViolations(noisy)).toEqual([]);
    });
  });
});
