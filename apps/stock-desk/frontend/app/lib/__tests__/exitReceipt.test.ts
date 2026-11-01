/**
 * FE-T1 / FE-T2 / FE-T3 (tech-architect Q14): the receipt reducer, the banner's
 * `mode_reason` hiding rule, and the once-per-receipt scroll decision.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  INITIAL_EXIT_RECEIPT_STATE,
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
  const accepted = (response = receiptResponse()): ExitReceiptAction => ({ type: "accepted", response });

  it("starts as { receipt: null, scrolledSeq: 0 } and is frozen", () => {
    expect(INITIAL_EXIT_RECEIPT_STATE).toEqual({ receipt: null, scrolledSeq: 0 });
    expect(Object.isFrozen(INITIAL_EXIT_RECEIPT_STATE)).toBe(true);
  });

  it("numbers receipts 1, 2, ... and a later receipt replaces the earlier one", () => {
    const first = receiptResponse({ message: "first" });
    const second = receiptResponse({ message: "second" });
    const after1 = exitReceiptReducer(INITIAL_EXIT_RECEIPT_STATE, accepted(first));
    expect(after1.receipt).toEqual({ seq: 1, response: first });
    const after2 = exitReceiptReducer(after1, accepted(second));
    expect(after2.receipt).toEqual({ seq: 2, response: second });
    // Exactly one receipt is held, never a list: 「橫幅數恰為 1」.
    expect(Object.keys(after2).sort()).toEqual(["receipt", "scrolledSeq"]);
  });

  it("a new receipt keeps the scrolled marker (it is older than the receipt, so the new one will scroll)", () => {
    const shown = exitReceiptReducer(
      exitReceiptReducer(INITIAL_EXIT_RECEIPT_STATE, accepted()),
      { type: "scrollHandled", seq: 1 },
    );
    const next = exitReceiptReducer(shown, accepted());
    expect(next.scrolledSeq).toBe(1);
    expect(next.receipt?.seq).toBe(2);
  });

  it("scrollHandled takes the max, never moves the receipt, and is a no-op reference when nothing moves", () => {
    const state = exitReceiptReducer(INITIAL_EXIT_RECEIPT_STATE, accepted());
    const handled = exitReceiptReducer(state, { type: "scrollHandled", seq: 1 });
    expect(handled.scrolledSeq).toBe(1);
    expect(handled.receipt).toBe(state.receipt);
    expect(exitReceiptReducer(handled, { type: "scrollHandled", seq: 1 })).toBe(handled);
    expect(exitReceiptReducer(handled, { type: "scrollHandled", seq: 0 })).toBe(handled);
  });

  it("returns the same reference for an unknown action", () => {
    const state = exitReceiptReducer(INITIAL_EXIT_RECEIPT_STATE, accepted());
    const unknown = { type: "something-else" } as unknown as ExitReceiptAction;
    expect(exitReceiptReducer(state, unknown)).toBe(state);
    expect(exitReceiptReducer(INITIAL_EXIT_RECEIPT_STATE, unknown)).toBe(INITIAL_EXIT_RECEIPT_STATE);
  });

  it("has no way to clear: the action union is `accepted` and `scrollHandled` only", () => {
    // @ts-expect-error -- there is no `clear` action; a receipt ends only on reload or replacement.
    const clear: ExitReceiptAction = { type: "clear" };
    // @ts-expect-error -- nor `reset`.
    const reset: ExitReceiptAction = { type: "reset" };
    // @ts-expect-error -- nor a setter.
    const set: ExitReceiptAction = { type: "set", receipt: null };
    const state = exitReceiptReducer(INITIAL_EXIT_RECEIPT_STATE, accepted());
    for (const action of [clear, reset, set]) expect(exitReceiptReducer(state, action)).toBe(state);

    const source = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "../exitReceipt.ts"),
      "utf-8",
    ).replace(/\/\*[\s\S]*?\*\//g, "");
    expect(source.match(/readonly type: "/g)).toHaveLength(2);
    expect(source).toMatch(/readonly type: "accepted"/);
    expect(source).toMatch(/readonly type: "scrollHandled"/);
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
  it("scrolls once per new receipt, only while the dialog is closed", () => {
    expect(shouldScrollForReceipt(undefined, 0, false)).toBe(false);
    expect(shouldScrollForReceipt(1, 0, false)).toBe(true);
    expect(shouldScrollForReceipt(1, 1, false)).toBe(false);
    expect(shouldScrollForReceipt(2, 1, false)).toBe(true);
  });

  it("waits while the dialog is open, whatever the receipt and the marker say", () => {
    for (const [seq, scrolled] of [[1, 0], [2, 1], [5, 0]] as const) {
      expect(shouldScrollForReceipt(seq, scrolled, true)).toBe(false);
    }
    expect(shouldScrollForReceipt(undefined, 0, true)).toBe(false);
  });

  it("a page mounted with a receipt it has already shown does not scroll", () => {
    expect(shouldScrollForReceipt(3, 3, false)).toBe(false);
  });

  it("a receipt written while the dialog is open is scrolled to once the dialog has closed", () => {
    expect(shouldScrollForReceipt(1, 0, true)).toBe(false); // written, dialog still open
    expect(shouldScrollForReceipt(1, 0, false)).toBe(true); // closed
    expect(shouldScrollForReceipt(1, 1, false)).toBe(false); // handled
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
