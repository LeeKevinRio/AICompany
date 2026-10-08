/**
 * RK4c-R3 guard: the front end must never READ `fx_to_twd`.
 *
 * Why: the W-RK4-1 source note ("the FX rate referred to here ... does not
 * include price or ATR") only holds while no number multiplied by a quote is
 * shown on screen. `fx_to_twd` is the one field that would let a component
 * rebuild `close * fx_to_twd` or `atr * fx_to_twd`. The type declaration in
 * `types.ts` and mentions inside comments are allowed; property reads are not.
 *
 * Detection (TypeScript 7 ships no JS compiler API, so this is text based):
 *   1. strip comments with a small scanner that understands string, template
 *      and `${}` nesting (so `// ...` inside a string is not a comment, and an
 *      expression inside a template literal is still scanned);
 *   2. match `.fx_to_twd` (also covers `?.fx_to_twd`) and
 *      `["fx_to_twd"]` / `['fx_to_twd']` / `[`fx_to_twd`]` index reads.
 * An interface field declaration (`fx_to_twd: number;`) matches neither
 * pattern, so `types.ts` needs no special casing; it is only asserted to have
 * been scanned, so the guard cannot silently run on an empty file list.
 *
 *   3. destructuring reads (`const { fx_to_twd } = x`, `{ fx_to_twd: rate }`,
 *      parameter patterns, nested patterns) are found by locating each
 *      `fx_to_twd` key inside a `{...}` and classifying that brace: it is a
 *      binding pattern only if it follows `const|let|var`, is a parameter of
 *      an arrow / function (the `)` is followed by `=>` or a body, or it is a
 *      `function` with a return annotation), or is nested in such a pattern.
 *      A brace after `:` (type annotation), after an identifier
 *      (`interface P {`), after `=` (`type T = {`, object literal) or an
 *      object literal passed to a call is NOT a pattern.
 *
 *   Assignment destructuring is covered too: a `{` / `[` whose matching closer
 *   is followed by a plain `=` (not `==`, `=>`) and is not a `: Type`
 *   annotation is a pattern (`({ fx_to_twd } = x)`, `[{ fx_to_twd }] = xs`).
 *   A computed key `const { ["fx_to_twd"]: r } = x` is caught by the index
 *   pattern in step 2 (which, conservatively, also flags `{ ["fx_to_twd"]: 1 }`).
 *
 * KNOWN LIMITS -- read before trusting this guard as "complete":
 *   - Heuristic, text based, not a parser. Do not read a green run as proof of
 *     "no read exists"; it proves "none of the shapes below the ceiling exist".
 *   - Not detected: a destructured parameter of a class method or arrow that
 *     also has a return-type annotation (`foo({ fx_to_twd }): T {`,
 *     `({ fx_to_twd }): T =>`); it is indistinguishable from the ternary
 *     `c ? f({ fx_to_twd }) : x` at text level.
 *   - Comment stripping can over-strip: a `//` inside JSX text
 *     (`<p>http://x</p>`) or inside a regex literal (`/https?:\/\//`) is taken
 *     as a line comment, so the rest of that line is not scanned (a read later
 *     on the same line would be missed).
 *   - Unbalanced brackets in JSX text can confuse the bracket matching.
 *   - Ceiling of any text match: reads whose key is not a literal
 *     `fx_to_twd` token are invisible -- `row[KEY]` with a variable key,
 *     string concatenation (`row["fx_" + "to_twd"]`), `Object.values(row)` /
 *     `Object.entries(row)`, and `"fx_to_twd" in row` (that last one checks
 *     presence only, but is listed so nobody assumes it is scanned).
 * A false positive fails loudly (red); a false negative is the real risk, so
 * extend the self-check cases below whenever a new shape appears.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const APP_DIR = fileURLToPath(new URL("../../", import.meta.url));

const FAILURE_HINT = "回風控重審 W-RK4-1（RK4c-R3：前端不得呈現乘過報價的數字）";

const PROPERTY_READ = /\.fx_to_twd\b/g;
// `\s` also matches newlines, so `[\n  "fx_to_twd"\n]` is covered.
const INDEX_READ = /\[\s*["'`]fx_to_twd["'`]\s*\]/g;

/** Remove `//` and block comments; keep everything else (strings included). */
function stripComments(src: string, maskBrackets = false): string {
  let out = "";
  // In mask mode, bracket characters inside string / template text become "_"
  // so that bracket matching only sees real code brackets.
  const lit = (t: string) => (maskBrackets ? t.replace(/[{}()[\]]/g, "_") : t);
  let i = 0;
  // Stack of contexts: "code" | "tpl" (inside template text) | "brace" (a `{` in code).
  const stack: string[] = ["code"];
  const top = () => stack[stack.length - 1];
  while (i < src.length) {
    const c = src.charAt(i);
    const n = src.charAt(i + 1);
    if (top() === "tpl") {
      if (c === "\\") {
        out += lit(c + n);
        i += 2;
      } else if (c === "`") {
        stack.pop();
        out += c;
        i += 1;
      } else if (c === "$" && n === "{") {
        stack.push("brace");
        out += "${";
        i += 2;
      } else {
        out += lit(c);
        i += 1;
      }
      continue;
    }
    // code / brace context
    if (c === "/" && n === "/") {
      while (i < src.length && src[i] !== "\n") i += 1;
    } else if (c === "/" && n === "*") {
      const end = src.indexOf("*/", i + 2);
      const stop = end === -1 ? src.length : end + 2;
      // Preserve newlines so line numbers stay meaningful.
      out += src.slice(i, stop).replace(/[^\n]/g, "");
      i = stop;
    } else if (c === '"' || c === "'") {
      let j = i + 1;
      while (j < src.length && src[j] !== c && src[j] !== "\n") {
        j += src[j] === "\\" ? 2 : 1;
      }
      out += lit(src.slice(i, j + 1));
      i = j + 1;
    } else if (c === "`") {
      stack.push("tpl");
      out += c;
      i += 1;
    } else if (c === "{") {
      stack.push("brace");
      out += c;
      i += 1;
    } else if (c === "}") {
      if (top() === "brace") stack.pop();
      out += c;
      i += 1;
    } else {
      out += c;
      i += 1;
    }
  }
  return out;
}

const OPEN = "{[(";
const CLOSE = "}])";

/** Index of the nearest unmatched opening bracket before `idx`, or -1. */
function enclosingOpener(m: string, idx: number): number {
  let depth = 0;
  for (let i = idx - 1; i >= 0; i -= 1) {
    if (CLOSE.includes(m.charAt(i))) depth += 1;
    else if (OPEN.includes(m.charAt(i))) {
      if (depth === 0) return i;
      depth -= 1;
    }
  }
  return -1;
}

/** Is the `(` at `open` the parameter list of an arrow function / function? */
function isParamList(m: string, open: number): boolean {
  let depth = 0;
  let close = -1;
  for (let i = open; i < m.length; i += 1) {
    if (m[i] === "(") depth += 1;
    else if (m[i] === ")") {
      depth -= 1;
      if (depth === 0) {
        close = i;
        break;
      }
    }
  }
  if (close === -1) return false;
  const after = m.slice(close + 1);
  const before = m.slice(0, open);
  if (/^\s*=>/.test(after)) return true;
  if (/^\s*\{/.test(after)) {
    // `f(...) {` is a body for functions / methods / catch, a block for control flow.
    return !/\b(?:if|while|for|switch|with)\s*$/.test(before);
  }
  // `function f({ fx_to_twd }: T): R {` -- return annotation before the body.
  return /^\s*:/.test(after) && /\bfunction\b[^()]*$/.test(before);
}

/** Index of the bracket closing the one at `open`, or -1. */
function matchingCloser(m: string, open: number): number {
  let depth = 0;
  for (let i = open; i < m.length; i += 1) {
    if (OPEN.includes(m.charAt(i))) depth += 1;
    else if (CLOSE.includes(m.charAt(i))) {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/** Is the `{` / `[` / `(` at `open` a binding (destructuring) pattern? */
function isPatternOpen(m: string, open: number): boolean {
  if (m[open] === "(") return isParamList(m, open);
  const before = m.slice(0, open).trimEnd();
  // Assignment destructuring: `({ a } = x)`, `[{ a }] = xs`. A bracket closed by a
  // plain `=` is a target, unless it is a `: Type` annotation (`const a: {…} = b`).
  const closer = matchingCloser(m, open);
  if (closer >= 0 && before.slice(-1) !== ":" && /^\s*=(?![=>])/.test(m.slice(closer + 1))) {
    return true;
  }
  if (/\b(?:const|let|var)$/.test(before)) return true;
  const last = before.slice(-1);
  const lastIdx = before.length - 1;
  if (last === "(") return isParamList(m, lastIdx);
  if (last === "[") return isPatternOpen(m, lastIdx);
  if (last === ",") {
    const o = enclosingOpener(m, lastIdx);
    return o >= 0 && isPatternOpen(m, o);
  }
  if (last === ":") {
    // `{ a: { fx_to_twd } } = x` nests; `const a: {` / `(x: {` is a type.
    const o = enclosingOpener(m, lastIdx);
    return o >= 0 && m[o] === "{" && isPatternOpen(m, o);
  }
  return false;
}

/** Lines where `fx_to_twd` is a key of a destructuring pattern (not a type or literal). */
function findDestructuringReads(masked: string): number[] {
  const lines: number[] = [];
  const key = /(?<=[{,]\s*)(["'`]?)fx_to_twd\1(?=\s*[,}=:])/g;
  for (const hit of masked.matchAll(key)) {
    const open = enclosingOpener(masked, hit.index);
    if (open >= 0 && masked[open] === "{" && isPatternOpen(masked, open)) {
      lines.push(masked.slice(0, hit.index).split("\n").length);
    }
  }
  return lines;
}

/** 1-based line numbers of every `fx_to_twd` read in `src` (comments ignored). */
function findFxToTwdReads(src: string): number[] {
  const hits = new Set<number>();
  const stripped = stripComments(src);
  for (const re of [PROPERTY_READ, INDEX_READ]) {
    for (const hit of stripped.matchAll(re)) {
      // Report the line of the `fx_to_twd` token itself (matters for multi-line indexes).
      const at = hit.index + hit[0].indexOf("fx_to_twd");
      hits.add(stripped.slice(0, at).split("\n").length);
    }
  }
  for (const line of findDestructuringReads(stripComments(src, true))) hits.add(line);
  return [...hits].sort((a, b) => a - b);
}

function collectSourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name === "__tests__" || entry.name === "node_modules") return [];
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return collectSourceFiles(full);
    return /\.tsx?$/.test(entry.name) ? [full] : [];
  });
}

describe("detector self-check (guard must not be vacuous)", () => {
  it("flags property, optional-chain and index reads", () => {
    expect(findFxToTwdReads("const v = x.fx_to_twd;")).toEqual([1]);
    expect(findFxToTwdReads("const v = x?.fx_to_twd;")).toEqual([1]);
    expect(findFxToTwdReads('const v = x["fx_to_twd"];')).toEqual([1]);
    expect(findFxToTwdReads("const v = x['fx_to_twd'];")).toEqual([1]);
    expect(findFxToTwdReads("const v = x[ `fx_to_twd` ];")).toEqual([1]);
    expect(findFxToTwdReads("const v = a.close * b.fx_to_twd;")).toEqual([1]);
  });

  it("flags a read inside a template-literal expression", () => {
    expect(findFxToTwdReads("const s = `v=${x.fx_to_twd}`;")).toEqual([1]);
  });

  it("flags a read that follows a string containing comment markers", () => {
    expect(findFxToTwdReads('const u = "http://a"; const v = x.fx_to_twd;')).toEqual([1]);
  });

  it("allows declarations and comment mentions", () => {
    expect(findFxToTwdReads("interface P {\n  fx_to_twd: number;\n}")).toEqual([]);
    expect(findFxToTwdReads("// uses x.fx_to_twd here\nconst a = 1;")).toEqual([]);
    expect(findFxToTwdReads("/**\n * via `fx_to_twd` and x.fx_to_twd\n */\nconst a = 1;")).toEqual([]);
    expect(findFxToTwdReads("const a = 1; /* x['fx_to_twd'] */")).toEqual([]);
  });

  it("flags destructuring reads: plain, renamed, default, nested, loop", () => {
    expect(findFxToTwdReads("const { fx_to_twd } = x;")).toEqual([1]);
    expect(findFxToTwdReads("const { close, fx_to_twd: rate } = x;")).toEqual([1]);
    expect(findFxToTwdReads("let { fx_to_twd = 1 } = x;")).toEqual([1]);
    expect(findFxToTwdReads('const { "fx_to_twd": rate } = x;')).toEqual([1]);
    expect(findFxToTwdReads("const { p: { fx_to_twd } } = x;")).toEqual([1]);
    expect(findFxToTwdReads("const [{ fx_to_twd }] = xs;")).toEqual([1]);
    expect(findFxToTwdReads("for (const { fx_to_twd } of xs) {}")).toEqual([1]);
    expect(findFxToTwdReads("const {\n  close,\n  fx_to_twd,\n} = x;")).toEqual([3]);
  });

  it("flags assignment destructuring (no const/let/var)", () => {
    expect(findFxToTwdReads("({ fx_to_twd } = x);")).toEqual([1]);
    expect(findFxToTwdReads("({ fx_to_twd: rate } = x);")).toEqual([1]);
    expect(findFxToTwdReads("[{ fx_to_twd }] = xs;")).toEqual([1]);
    expect(findFxToTwdReads("[a, { fx_to_twd }] = xs;")).toEqual([1]);
  });

  it("flags a computed-key destructuring via the index pattern", () => {
    expect(findFxToTwdReads('const { ["fx_to_twd"]: r } = x;')).toEqual([1]);
  });

  it("flags multi-line index reads and reports the token's line", () => {
    expect(findFxToTwdReads('const v = x[\n  "fx_to_twd"\n];')).toEqual([2]);
    expect(findFxToTwdReads("/* c\n c */\nconst v = x[\n  `fx_to_twd`\n];")).toEqual([4]);
  });

  it("is not confused by brackets inside strings (mask mode)", () => {
    // Trailing / leading string brackets (cheap sanity cases).
    expect(findFxToTwdReads('const { fx_to_twd } = x; const s = "}";')).toEqual([1]);
    expect(findFxToTwdReads('const s = "{"; const { fx_to_twd } = x;')).toEqual([1]);
    // A string bracket BETWEEN the opener and the key breaks the backward scan if unmasked.
    expect(findFxToTwdReads('const { a = "}", fx_to_twd } = x;')).toEqual([1]);
    expect(findFxToTwdReads('const f = ({ a = "(", fx_to_twd }) => 1;')).toEqual([1]);
    expect(findFxToTwdReads("const { a = `)]`, fx_to_twd } = x;")).toEqual([1]);
    // A string bracket inside the span after the key breaks the forward scans if unmasked.
    expect(findFxToTwdReads('const f = ({ fx_to_twd }, s = ")") => 1;')).toEqual([1]);
    expect(findFxToTwdReads('({ fx_to_twd, a = "}" } = x);')).toEqual([1]);
    // A string brace must not turn a type annotation into a pattern either.
    expect(findFxToTwdReads('const a: { fx_to_twd: number } = b; const s = "{";')).toEqual([]);
  });

  it("flags destructured parameters of arrows and functions", () => {
    expect(findFxToTwdReads("const f = ({ fx_to_twd }) => 1;")).toEqual([1]);
    expect(findFxToTwdReads("const f = ({ fx_to_twd }: Row) => 1;")).toEqual([1]);
    expect(findFxToTwdReads("const f = (a: number, { fx_to_twd }: Row) => 1;")).toEqual([1]);
    expect(findFxToTwdReads("function f({ fx_to_twd }: T) { return 1; }")).toEqual([1]);
    expect(findFxToTwdReads("function f({ fx_to_twd }: T): number { return 1; }")).toEqual([1]);
    expect(findFxToTwdReads("xs.map(([k, { fx_to_twd }]) => k);")).toEqual([1]);
    expect(findFxToTwdReads("const f = ({ p: { fx_to_twd } }: T) => 1;")).toEqual([1]);
  });

  it("allows type annotations and declarations that mention the field", () => {
    expect(findFxToTwdReads("const a: { fx_to_twd: number } = b;")).toEqual([]);
    expect(findFxToTwdReads("const f = (x: { fx_to_twd: number }) => 1;")).toEqual([]);
    expect(findFxToTwdReads("function f(a: number, x: { fx_to_twd: number }): void {}")).toEqual([]);
    expect(findFxToTwdReads("const f = ({ a }: { fx_to_twd: number }) => a;")).toEqual([]);
    expect(findFxToTwdReads("interface P {\n  close: number;\n  fx_to_twd: number;\n}")).toEqual([]);
    expect(findFxToTwdReads("type P = { fx_to_twd: number; atr: number };")).toEqual([]);
    expect(findFxToTwdReads("type P = {\n  fx_to_twd: number,\n};")).toEqual([]);
    expect(findFxToTwdReads("type Q = Pick<{ fx_to_twd: number }, 'fx_to_twd'>;")).toEqual([]);
  });

  it("allows annotated assignment targets and comparisons", () => {
    expect(findFxToTwdReads("const t: [{ fx_to_twd: number }] = b;")).toEqual([]);
    expect(findFxToTwdReads("const f = (x: { fx_to_twd: number } = d) => 1;")).toEqual([]);
    expect(findFxToTwdReads("if ({ fx_to_twd: 1 } == y) {}")).toEqual([]);
    expect(findFxToTwdReads("const g = useState<{ fx_to_twd: number }>(d);")).toEqual([]);
  });

  it("allows writing / constructing the field (object literals are not reads)", () => {
    expect(findFxToTwdReads("const row = { close: 1, fx_to_twd: 1 };")).toEqual([]);
    expect(findFxToTwdReads("render({ fx_to_twd: 1 });")).toEqual([]);
    expect(findFxToTwdReads("const g = () => ({ fx_to_twd: 1 });")).toEqual([]);
    expect(findFxToTwdReads('const m = "{ fx_to_twd }"; const { a } = x;')).toEqual([]);
  });

  it("reports the correct line after a multi-line block comment", () => {
    expect(findFxToTwdReads("/* a\n b */\nconst v = x.fx_to_twd;")).toEqual([3]);
  });
});

describe("RK4c-R3: front end never reads fx_to_twd", () => {
  const files = collectSourceFiles(APP_DIR);
  const rel = (f: string) => relative(APP_DIR, f).split(sep).join("/");

  it("scans a non-empty file set that includes types.ts", () => {
    expect(files.length).toBeGreaterThan(0);
    const names = files.map(rel);
    expect(names).toContain("lib/types.ts");
    expect(names.some((n) => n.startsWith("__tests__/") || n.includes("/__tests__/"))).toBe(false);
    expect(names.some((n) => n.includes("node_modules"))).toBe(false);
    // The declaration site must really exist, otherwise the guard watches nothing.
    expect(readFileSync(join(APP_DIR, "lib/types.ts"), "utf8")).toContain("fx_to_twd");
  });

  it("has no fx_to_twd property or index read in app/**/*.ts(x)", () => {
    const violations = files.flatMap((f) =>
      findFxToTwdReads(readFileSync(f, "utf8")).map((line) => `${rel(f)}:${line}`),
    );
    expect(violations, `${FAILURE_HINT}\n違規位置：${violations.join(", ")}`).toEqual([]);
  });
});
