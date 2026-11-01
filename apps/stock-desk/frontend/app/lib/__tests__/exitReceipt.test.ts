/**
 * FE-T1 / FE-T2 / FE-T3 (tech-architect Q14): the receipt reducer, the banner's
 * `mode_reason` hiding rule, and the once-per-receipt scroll decision.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  type ExitReceiptAction,
  RECEIPT_BAR_GAP_PX,
  exitReceiptReducer,
  isReceiptModeReasonHidden,
  receiptNeedsScroll,
  receiptScrollCorrection,
  shouldScrollForReceipt,
} from "../exitReceipt";
import { receiptResponse } from "./exitFixtures";

describe("exitReceiptReducer (FE-T1, FE-C2)", () => {
  it("starts empty", () => {
    expect(exitReceiptReducer(null, { type: "accepted", response: receiptResponse() })).not.toBeNull();
  });

  it("numbers receipts 1, 2, ... and a later receipt replaces the earlier one", () => {
    const first = receiptResponse({ message: "first" });
    const second = receiptResponse({ message: "second" });
    const after1 = exitReceiptReducer(null, { type: "accepted", response: first });
    expect(after1).toEqual({ seq: 1, response: first });
    const after2 = exitReceiptReducer(after1, { type: "accepted", response: second });
    expect(after2).toEqual({ seq: 2, response: second });
    // Exactly one receipt is held, never a list: 「橫幅數恰為 1」.
    expect(Object.keys(after2 ?? {}).sort()).toEqual(["response", "seq"]);
  });

  it("returns the same reference for an unknown action", () => {
    const state = exitReceiptReducer(null, { type: "accepted", response: receiptResponse() });
    const unknown = { type: "something-else" } as unknown as ExitReceiptAction;
    expect(exitReceiptReducer(state, unknown)).toBe(state);
    expect(exitReceiptReducer(null, unknown)).toBeNull();
  });

  it("has no way to clear: the action union is `accepted` only", () => {
    // @ts-expect-error -- there is no `clear` action; a receipt ends only on reload or replacement.
    const clear: ExitReceiptAction = { type: "clear" };
    // @ts-expect-error -- nor `reset`.
    const reset: ExitReceiptAction = { type: "reset" };
    const state = exitReceiptReducer(null, { type: "accepted", response: receiptResponse() });
    expect(exitReceiptReducer(state, clear)).toBe(state);
    expect(exitReceiptReducer(state, reset)).toBe(state);

    const source = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "../exitReceipt.ts"),
      "utf-8",
    ).replace(/\/\*[\s\S]*?\*\//g, "");
    expect(source.match(/type: "/g)).toHaveLength(1);
    expect(source).toMatch(/readonly type: "accepted"/);
  });
});

describe("isReceiptModeReasonHidden (FE-T2, FR-5, FE-C7)", () => {
  const R = "R 系列（新倉進場）自 2026-08-11 起暫停 20 交易日，預計 2026-09-09 恢復。";

  it("never hides when /today is not successful, however equal the strings are", () => {
    expect(isReceiptModeReasonHidden(false, R, R)).toBe(false);
    expect(isReceiptModeReasonHidden(false, null, R)).toBe(false);
  });

  it("hides on strict equality while /today is successful", () => {
    expect(isReceiptModeReasonHidden(true, R, R)).toBe(true);
  });

  it("does not hide when the strings differ by whitespace or any character", () => {
    expect(isReceiptModeReasonHidden(true, `${R} `, R)).toBe(false);
    expect(isReceiptModeReasonHidden(true, ` ${R}`, R)).toBe(false);
    expect(isReceiptModeReasonHidden(true, R.replace("20", "19"), R)).toBe(false);
    expect(isReceiptModeReasonHidden(true, R.replace("起暫停", "起 暫停"), R)).toBe(false);
  });

  it("does not hide without a /today mode_reason to compare with", () => {
    expect(isReceiptModeReasonHidden(true, null, R)).toBe(false);
  });
});

describe("shouldScrollForReceipt (FE-T3, FE-C8)", () => {
  it("scrolls once per new receipt", () => {
    expect(shouldScrollForReceipt(undefined, 0)).toBe(false);
    expect(shouldScrollForReceipt(1, 0)).toBe(true);
    expect(shouldScrollForReceipt(1, 1)).toBe(false);
    expect(shouldScrollForReceipt(2, 1)).toBe(true);
  });

  it("a page that mounts with a receipt already present does not scroll (lastHandled starts at the current seq)", () => {
    expect(shouldScrollForReceipt(3, 3)).toBe(false);
  });
});

describe("receiptNeedsScroll / receiptScrollCorrection (視覺規範 §4.1, 風控 必改項 12)", () => {
  it("does not scroll when the banner is already comfortably in view (AC-7)", () => {
    expect(receiptNeedsScroll(120, 0, 900)).toBe(false);
    expect(receiptNeedsScroll(250, 127, 812)).toBe(false);
  });

  it("scrolls when the banner is behind or too close to the sticky bar", () => {
    expect(receiptNeedsScroll(100, 127, 812)).toBe(true);
    expect(receiptNeedsScroll(127 + RECEIPT_BAR_GAP_PX - 1, 127, 812)).toBe(true);
    expect(receiptNeedsScroll(127 + RECEIPT_BAR_GAP_PX, 127, 812)).toBe(false);
  });

  it("scrolls when the banner sits below the top two thirds of the viewport", () => {
    expect(receiptNeedsScroll(0.66 * 812 + 1, 87, 812)).toBe(true);
    expect(receiptNeedsScroll(0.66 * 812, 87, 812)).toBe(false);
  });

  it("with no sticky bar the bar bottom is 0 and a banner above the top edge still scrolls", () => {
    expect(receiptNeedsScroll(-5, 0, 900)).toBe(true);
    expect(receiptNeedsScroll(16, 0, 900)).toBe(false);
  });

  it("the correction is zero when the first line clears the bar, and moves the page up when it does not", () => {
    expect(receiptScrollCorrection(160, 127)).toBe(0);
    expect(receiptScrollCorrection(143, 127)).toBe(0);
    // 快市啟動: a 200px bar over a banner placed at 160px by scroll-mt-40.
    expect(receiptScrollCorrection(160, 200)).toBe(160 - 216);
  });
});
