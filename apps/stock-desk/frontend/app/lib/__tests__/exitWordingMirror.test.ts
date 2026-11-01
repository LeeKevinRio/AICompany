/**
 * Guard tests: the exit-dialog sentences the frontend mirrors must equal their
 * single approved source, `backend/app/playbook/wording.py`, byte for byte
 * (風控 必改項 10、Q8 F-3、Q11 F-10; PRD FR-11 / AC-30 / AC-57 / AC-58).
 *
 * The expected value is read out of the backend file at test time, not retyped
 * here: editing either side alone fails. The literal assertions further down
 * pin the signed-off text itself, so changing both sides together to something
 * unapproved fails as well.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { EXIT_CONFIRM_CHECKS_UPDATED, EXIT_CONFIRM_FALLBACK_CHECKS } from "../playbookView";
import {
  pythonStringConstant,
  pythonTupleConstant,
  readWordingPy,
} from "./pythonWording";

const wording = readWordingPy();

describe("pythonWording helper (the guard's own reader)", () => {
  it("joins adjacent literals, ignores comments and honours escapes", () => {
    const source = [
      "#: doc comment with NAME = (",
      "NAME = (",
      '    "a\\"b"  # trailing comment',
      '    "c"',
      ")",
      "TUPLE: tuple[str, ...] = (",
      '    "x"',
      '    "y",',
      '    "z",',
      ")",
      'SINGLE = "one"',
    ].join("\n");
    expect(pythonStringConstant(source, "NAME")).toBe('a"bc');
    expect(pythonTupleConstant(source, "TUPLE")).toEqual(["xy", "z"]);
    expect(pythonStringConstant(source, "SINGLE")).toBe("one");
  });

  it("throws on a missing constant or a shape mismatch instead of returning something", () => {
    expect(() => pythonStringConstant("A = (\n)", "B")).toThrow();
    expect(() => pythonStringConstant('T = (\n "a",\n "b",\n)', "T")).toThrow();
    expect(() => pythonTupleConstant('S = "a"', "S")).toThrow();
  });
});

describe("N1 (風控 Q11 F-10) mirrors wording.EXIT_CONFIRM_CHECKS_UPDATED", () => {
  it("is byte-for-byte the backend constant", () => {
    expect(EXIT_CONFIRM_CHECKS_UPDATED).toBe(
      pythonStringConstant(wording, "EXIT_CONFIRM_CHECKS_UPDATED"),
    );
  });

  it("is the signed-off sentence", () => {
    expect(EXIT_CONFIRM_CHECKS_UPDATED).toBe(
      "核取句已依最新取得的資料更新，有變動的項目已改為未勾選，請重新閱讀後再勾選。",
    );
  });
});

describe("degraded checklist (風控 Q8 F-3) mirrors wording.py", () => {
  const backendChecks = pythonTupleConstant(wording, "EXIT_CONFIRM_CHECKS");
  const backendDegraded = pythonStringConstant(wording, "EXIT_CONFIRM_FREEZE_DEGRADED");

  it("is the three number-free backend checks with the degraded sentence in place of check 2", () => {
    expect(backendChecks).toHaveLength(4);
    expect([...EXIT_CONFIRM_FALLBACK_CHECKS]).toEqual([
      backendChecks[0],
      backendDegraded,
      backendChecks[2],
      backendChecks[3],
    ]);
  });

  it("carries the 1b revision as its second sentence", () => {
    expect(EXIT_CONFIRM_FALLBACK_CHECKS[1]).toBe(
      "送出後，R 系列（新倉進場）暫停；本次未能取得暫停交易日數與預計恢復日，" +
        "預計恢復日會在受理後的執行結果中顯示。",
    );
  });

  it("differs from the formal checklist only at index 1, so a swap clears exactly that tick", () => {
    const placeholder = /\{[a-zA-Z_]+\}/;
    expect(placeholder.test(backendChecks[1] ?? "")).toBe(true);
    for (const index of [0, 2, 3]) {
      expect(placeholder.test(backendChecks[index] ?? "")).toBe(false);
      expect(EXIT_CONFIRM_FALLBACK_CHECKS[index]).toBe(backendChecks[index]);
    }
  });

  it("no longer contains the retired 「兩者」 promise anywhere in the frontend sources (grep guard)", () => {
    const retired = "兩者" + "於送出後的執行結果中顯示";
    const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
    const offenders: string[] = [];
    function walk(dir: string): void {
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) {
          if (entry !== "__tests__" && entry !== "node_modules" && entry !== ".next") walk(full);
        } else if (/\.(ts|tsx)$/.test(entry) && readFileSync(full, "utf-8").includes(retired)) {
          offenders.push(full);
        }
      }
    }
    walk(root);
    expect(offenders).toEqual([]);
    expect(wording.includes(retired)).toBe(false);
  });
});
