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
import {
  EXIT_CONFIRM_CHECKS_UPDATED,
  EXIT_CONFIRM_FALLBACK_CHECKS,
  EXIT_FAILURE_WORDING,
} from "../playbookView";
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

describe("NB-6 failure panel (風控 必改項 9、10; merged-with-N-166 version) mirrors wording.py", () => {
  it("label and the three paragraphs are byte-for-byte the backend constants", () => {
    expect(EXIT_FAILURE_WORDING.label).toBe(pythonStringConstant(wording, "EXIT_RESULT_UNCONFIRMED_LABEL"));
    expect([...EXIT_FAILURE_WORDING.body]).toEqual([
      pythonStringConstant(wording, "EXIT_RESULT_UNCONFIRMED_STATES"),
      pythonStringConstant(wording, "EXIT_RESULT_UNCONFIRMED_BADGE"),
      pythonStringConstant(wording, "EXIT_RESULT_UNCONFIRMED_RETRY"),
    ]);
  });

  it("is the signed-off text, paragraph 3 being the CEO #87 revision", () => {
    expect(EXIT_FAILURE_WORDING.label).toBe("無法確認全部出清的處理結果");
    expect(EXIT_FAILURE_WORDING.body[0]).toBe(
      "這次送出未取得可確認結果的回應。目前可能尚未處理，也可能已受理：" +
        "R 系列（新倉進場）已暫停，持有批次也都已有賣出指令。",
    );
    expect(EXIT_FAILURE_WORDING.body[1]).toBe(
      "頁面上方的狀態列在重新取得資料後，其模式徽章會顯示 R 系列（新倉進場）目前是否已暫停，" +
        "但不會顯示賣出指令；若這次送出前 R 系列就已暫停，徽章也無法顯示這次是否已受理。",
    );
    expect(EXIT_FAILURE_WORDING.body[2]).toBe(
      "你可以再次送出：已有尚未結算之出清賣出指令的持有批次，不會再重複產生賣出指令，" +
        "除非該指令的預定執行日沒有日線開盤價、且之後的交易日已有日線資料，" +
        "這時會為該批次另行產生賣出指令；但再次送出可能延後 R 系列（新倉進場）的預計恢復日。" +
        "再次送出若取得回應，回應會說明該次的處理結果，包括先前已有、尚未結算的賣出指令。",
    );
  });

  it("keeps paragraph 3 as one paragraph with two sentences, and never says 安全/放心", () => {
    expect(EXIT_FAILURE_WORDING.body).toHaveLength(3);
    expect(EXIT_FAILURE_WORDING.body[2].match(/。/g)).toHaveLength(2);
    for (const text of [EXIT_FAILURE_WORDING.label, ...EXIT_FAILURE_WORDING.body]) {
      expect(text).not.toMatch(/安全|放心|已執行|已出清|未確認|請關閉|視窗/);
    }
  });

  it("does not contain the retired pre-merge text, neither paragraph 1's 「只暫停了」 nor the unqualified paragraph 3", () => {
    const joined = EXIT_FAILURE_WORDING.body.join("");
    expect(joined).not.toContain("只暫停了");
    expect(joined).not.toContain("尚未產生賣出指令");
    expect(joined).not.toContain("若這次其實已產生賣出指令");
    expect(joined).not.toContain("不會再重複產生賣出指令；但");
  });
});
