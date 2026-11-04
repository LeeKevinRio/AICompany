/**
 * Test helper: read the string constants of the backend's `wording.py` so a
 * frontend mirror can be compared with its single approved source byte for
 * byte (風控 必改項 10 / F-10: "後端常數是唯一核可來源，前端鏡射，加守門測試").
 *
 * Deliberately tiny: it understands only what `wording.py` uses for these
 * constants — adjacent double-quoted literals (implicit concatenation),
 * optionally parenthesised, optionally a comma-separated tuple of those, with
 * `#` comments and the escapes `\\`, `\"`, `\n`. Anything else throws, so a
 * future change to how a constant is written fails loudly instead of letting a
 * mirror drift unnoticed.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

/** Absolute path of the backend wording module, resolved from this file. */
export const WORDING_PY_PATH = resolve(here, "../../../../backend/app/playbook/wording.py");

export function readWordingPy(): string {
  return readFileSync(WORDING_PY_PATH, "utf-8");
}

type Parsed = string | string[];

function skipBlank(source: string, from: number): number {
  let i = from;
  while (i < source.length) {
    const ch = source[i];
    if (ch === " " || ch === "\t" || ch === "\n" || ch === "\r") {
      i += 1;
    } else if (ch === "#") {
      while (i < source.length && source[i] !== "\n") i += 1;
    } else {
      break;
    }
  }
  return i;
}

/** One `"..."` literal starting at `from`; returns the decoded text and the index after it. */
function readLiteral(source: string, from: number): [string, number] {
  if (source[from] !== '"') throw new Error(`expected a double-quoted literal at ${from}`);
  let out = "";
  let i = from + 1;
  while (i < source.length) {
    const ch = source[i];
    if (ch === '"') return [out, i + 1];
    if (ch === "\\") {
      const next = source[i + 1];
      if (next === "\\" || next === '"') out += next;
      else if (next === "n") out += "\n";
      else throw new Error(`unsupported escape \\${String(next)} at ${i}`);
      i += 2;
    } else if (ch === "\n") {
      throw new Error(`unterminated literal at ${from}`);
    } else {
      out += ch;
      i += 1;
    }
  }
  throw new Error(`unterminated literal at ${from}`);
}

/** Adjacent literals, concatenated the way Python does. */
function readConcatenation(source: string, from: number): [string, number] {
  let i = skipBlank(source, from);
  let [text, next] = readLiteral(source, i);
  i = skipBlank(source, next);
  while (source[i] === '"') {
    const [more, after] = readLiteral(source, i);
    text += more;
    i = skipBlank(source, after);
  }
  return [text, i];
}

function readExpression(source: string, from: number): [Parsed, number] {
  let i = skipBlank(source, from);
  if (source[i] === '"') return readConcatenation(source, i);
  if (source[i] !== "(") throw new Error(`unsupported expression at ${i}`);
  i = skipBlank(source, i + 1);
  const items: string[] = [];
  let sawComma = false;
  for (;;) {
    if (source[i] === ")") return [sawComma ? items : (items[0] ?? ""), i + 1];
    const [item, next] = readConcatenation(source, i);
    items.push(item);
    i = skipBlank(source, next);
    if (source[i] === ",") {
      sawComma = true;
      i = skipBlank(source, i + 1);
    } else if (source[i] !== ")") {
      throw new Error(`expected , or ) at ${i}`);
    }
  }
}

function constantStart(source: string, name: string): number {
  const match = new RegExp(`^${name}(?::[^=\\n]+)? = `, "m").exec(source);
  if (match === null) throw new Error(`constant ${name} not found in wording.py`);
  return match.index + match[0].length;
}

/** `NAME = ("..." "...")` as one string. */
export function pythonStringConstant(source: string, name: string): string {
  const [value] = readExpression(source, constantStart(source, name));
  if (typeof value !== "string") throw new Error(`${name} is a tuple, not a string`);
  return value;
}

/** `NAME: tuple[str, ...] = ("...", "...", ...)` as an array. */
export function pythonTupleConstant(source: string, name: string): string[] {
  const [value] = readExpression(source, constantStart(source, name));
  if (typeof value === "string") throw new Error(`${name} is a string, not a tuple`);
  return value;
}
