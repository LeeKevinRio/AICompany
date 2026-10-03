import { describe, expect, it } from "vitest";
import { ApiError } from "../api";
import {
  buildPositionPatch,
  changedFields,
  draftFromPosition,
  focusTargetAfterRemoval,
  inlineKeyAction,
  isEmptyPatch,
  normalizeDecimalString,
  originalValueHints,
  parsePositionAnchor,
  positionAnchorId,
  positionEditButtonId,
  routeSaveError,
  saveErrorFocusTarget,
  unmappedFieldMessages,
  positionFieldInputId,
  positionRemoveButtonId,
  positionSaveButtonId,
} from "../inventoryEdit";
import type { InlineEditable } from "../inventoryEdit";

const POSITION: InlineEditable = {
  quantity: "1000",
  avg_cost: "605.50",
  currency: "TWD",
  note: "long term",
};

/** C1: the only keys an inline PATCH body may ever carry. */
const ALLOWED_PATCH_KEYS = ["quantity", "avg_cost", "note"];

describe("normalizeDecimalString", () => {
  it("treats trailing zeros, leading zeros and a plus sign as the same number", () => {
    expect(normalizeDecimalString("1000")).toBe("1000");
    expect(normalizeDecimalString("1000.00")).toBe("1000");
    expect(normalizeDecimalString("0001000")).toBe("1000");
    expect(normalizeDecimalString("+5")).toBe("5");
    expect(normalizeDecimalString("605.50")).toBe("605.5");
    expect(normalizeDecimalString(" 12.0 ")).toBe("12");
  });

  it("leaves text that is not a plain decimal as trimmed text, so the backend can reject it", () => {
    expect(normalizeDecimalString(" abc ")).toBe("abc");
    expect(normalizeDecimalString("")).toBe("");
    expect(normalizeDecimalString("1e3")).toBe("1e3");
  });

  it("keeps the sign of a negative value and never prints -0", () => {
    expect(normalizeDecimalString("-3.50")).toBe("-3.5");
    expect(normalizeDecimalString("-0.00")).toBe("0");
  });
});

describe("buildPositionPatch (C1: PATCH body is a subset of {quantity, avg_cost, note})", () => {
  it("sends only the changed key, decimals as strings", () => {
    const draft = { ...draftFromPosition(POSITION), quantity: "1500" };
    expect(buildPositionPatch(POSITION, draft)).toEqual({ quantity: "1500" });
  });

  it("sends several changed keys together and still nothing else", () => {
    const draft = { quantity: "1500", avg_cost: "610.25", note: "added" };
    const patch = buildPositionPatch(POSITION, draft);
    expect(patch).toEqual({ quantity: "1500", avg_cost: "610.25", note: "added" });
    for (const key of Object.keys(patch)) expect(ALLOWED_PATCH_KEYS).toContain(key);
    expect(typeof patch.quantity).toBe("string");
    expect(typeof patch.avg_cost).toBe("string");
  });

  it("never carries identity / currency / market keys whatever the input", () => {
    const patch = buildPositionPatch(POSITION, { quantity: "1", avg_cost: "2", note: "x" });
    for (const forbidden of ["symbol", "market", "currency", "instrument_type", "opened_at", "sector", "id"]) {
      expect(patch).not.toHaveProperty(forbidden);
    }
  });

  it("an emptied note is sent as null", () => {
    const draft = { ...draftFromPosition(POSITION), note: "   " };
    expect(buildPositionPatch(POSITION, draft)).toEqual({ note: null });
  });

  it("a note typed into a previously empty field is sent trimmed", () => {
    const empty: InlineEditable = { ...POSITION, note: null };
    expect(buildPositionPatch(empty, { ...draftFromPosition(empty), note: "  hello " })).toEqual({
      note: "hello",
    });
  });

  it("no change (including 1000 vs 1000.00 and a null note vs empty text) yields an empty patch: no request", () => {
    expect(isEmptyPatch(buildPositionPatch(POSITION, draftFromPosition(POSITION)))).toBe(true);
    expect(
      isEmptyPatch(buildPositionPatch(POSITION, { quantity: "1000.00", avg_cost: "605.5", note: "long term" })),
    ).toBe(true);
    const nullNote: InlineEditable = { ...POSITION, note: null };
    expect(isEmptyPatch(buildPositionPatch(nullNote, draftFromPosition(nullNote)))).toBe(true);
  });

  it("does not validate: zero and empty go to the backend, which supplies the message", () => {
    expect(buildPositionPatch(POSITION, { ...draftFromPosition(POSITION), quantity: "0" })).toEqual({
      quantity: "0",
    });
    expect(buildPositionPatch(POSITION, { ...draftFromPosition(POSITION), avg_cost: "" })).toEqual({
      avg_cost: "",
    });
  });

  it("changedFields reports exactly the differing fields", () => {
    expect(changedFields(POSITION, { quantity: "1", avg_cost: "605.5", note: "long term" })).toEqual([
      "quantity",
    ]);
  });
});

describe("originalValueHints (V3: original value only, in the display format)", () => {
  it("shows nothing when nothing changed", () => {
    expect(originalValueHints(POSITION, draftFromPosition(POSITION))).toEqual({});
  });

  it("uses the same formatters as the display mode", () => {
    const hints = originalValueHints(
      { quantity: "1000", avg_cost: "605.5", currency: "TWD", note: null },
      { quantity: "100", avg_cost: "600", note: "x" },
    );
    expect(hints.quantity).toBe("1,000");
    expect(hints.avg_cost).toBe("NT$605.50");
    expect(hints.note).toBe("—");
  });

  it("carries no delta, ratio, percentage or arrow", () => {
    const hints = originalValueHints(POSITION, { quantity: "1", avg_cost: "1", note: "y" });
    for (const text of Object.values(hints)) {
      expect(text).not.toMatch(/[%×▲▼↑↓→+]/);
    }
  });
});

describe("routeSaveError (C7 / C8: nothing swallowed, no invented copy)", () => {
  it("puts quantity / avg_cost / note messages under their inputs, verbatim", () => {
    const error = new ApiError("請求失敗（HTTP 422）", 422, {
      quantity: "數量必須大於 0",
      avg_cost: "平均成本必須大於 0",
      note: "備註過長",
    });
    expect(routeSaveError(error)).toEqual({
      inline: { quantity: "數量必須大於 0", avg_cost: "平均成本必須大於 0", note: "備註過長" },
      residual: [],
      showGeneric: false,
    });
  });

  it("sends field errors that have no input in the row (body, currency, symbol) to the error panel", () => {
    const error = new ApiError("x", 422, {
      quantity: "數量必須大於 0",
      body: "至少需提供一個欄位",
      currency: "幣別不符",
      symbol: "代號不可變更",
    });
    const routed = routeSaveError(error);
    expect(routed.inline).toEqual({ quantity: "數量必須大於 0" });
    expect(routed.residual).toEqual(["至少需提供一個欄位", "幣別不符", "代號不可變更"]);
    expect(routed.showGeneric).toBe(false);
  });

  it("an error without field detail (404 / 5xx / network) is shown as a whole", () => {
    expect(routeSaveError(new ApiError("找不到指定的部位", 404)).showGeneric).toBe(true);
    expect(routeSaveError(new ApiError("無法連線到後端服務", 0)).showGeneric).toBe(true);
    expect(routeSaveError(new Error("boom")).showGeneric).toBe(true);
  });

  it("no error means nothing to show", () => {
    expect(routeSaveError(null)).toEqual({ inline: {}, residual: [], showGeneric: false });
    expect(routeSaveError(undefined)).toEqual({ inline: {}, residual: [], showGeneric: false });
  });
});

describe("inlineKeyAction (Enter saves, Escape cancels, never while an IME is composing)", () => {
  it("maps Enter and Escape", () => {
    expect(inlineKeyAction({ key: "Enter", isComposing: false })).toBe("save");
    expect(inlineKeyAction({ key: "Escape", isComposing: false })).toBe("cancel");
  });

  it("ignores Enter and Escape during composition (isComposing)", () => {
    expect(inlineKeyAction({ key: "Enter", isComposing: true })).toBeNull();
    expect(inlineKeyAction({ key: "Escape", isComposing: true })).toBeNull();
  });

  it("ignores the legacy keyCode 229 composition marker", () => {
    expect(inlineKeyAction({ key: "Enter", isComposing: false, keyCode: 229 })).toBeNull();
  });

  it("ignores every other key", () => {
    expect(inlineKeyAction({ key: "a", isComposing: false })).toBeNull();
    expect(inlineKeyAction({ key: "Tab", isComposing: false })).toBeNull();
  });
});

describe("anchors and removal focus", () => {
  it("anchor and edit-button ids", () => {
    expect(positionAnchorId(12)).toBe("pos-12");
    expect(positionEditButtonId(12)).toBe("pos-edit-12");
  });

  it("parsePositionAnchor accepts only #pos-{positive integer}", () => {
    expect(parsePositionAnchor("#pos-12")).toBe(12);
    expect(parsePositionAnchor("")).toBeNull();
    expect(parsePositionAnchor("#pos-")).toBeNull();
    expect(parsePositionAnchor("#pos-1x")).toBeNull();
    expect(parsePositionAnchor("#pos-0")).toBeNull();
    expect(parsePositionAnchor("#pos--3")).toBeNull();
    expect(parsePositionAnchor("pos-3")).toBeNull();
    expect(parsePositionAnchor("#other")).toBeNull();
  });

  it("focus goes to the next row, else the previous row, else the heading (never body)", () => {
    expect(focusTargetAfterRemoval([1, 2, 3], 2)).toEqual({ kind: "row", id: 3 });
    expect(focusTargetAfterRemoval([1, 2, 3], 1)).toEqual({ kind: "row", id: 2 });
    expect(focusTargetAfterRemoval([1, 2, 3], 3)).toEqual({ kind: "row", id: 2 });
    expect(focusTargetAfterRemoval([7], 7)).toEqual({ kind: "heading" });
    expect(focusTargetAfterRemoval([], 7)).toEqual({ kind: "heading" });
  });
});

describe("unmappedFieldMessages (forms never drop a refusal that has no input)", () => {
  it("returns backend messages for keys outside the form's own fields, verbatim", () => {
    const error = new ApiError("x", 422, { quantity: "數量必須大於 0", body: "model level text" });
    expect(unmappedFieldMessages(error, ["quantity", "avg_cost"])).toEqual(["model level text"]);
  });

  it("returns nothing for known fields, non-field errors and non-ApiError values", () => {
    expect(unmappedFieldMessages(new ApiError("x", 422, { quantity: "q" }), ["quantity"])).toEqual([]);
    expect(unmappedFieldMessages(new ApiError("down", 500), ["quantity"])).toEqual([]);
    expect(unmappedFieldMessages(null, ["quantity"])).toEqual([]);
  });
});

describe("saveErrorFocusTarget (focus after a failed save)", () => {
  it("first errored field in visual order", () => {
    expect(saveErrorFocusTarget(new ApiError("x", 422, { note: "n", avg_cost: "c" }))).toBe("avg_cost");
    expect(saveErrorFocusTarget(new ApiError("x", 422, { quantity: "q", note: "n" }))).toBe("quantity");
    expect(saveErrorFocusTarget(new ApiError("x", 422, { note: "n" }))).toBe("note");
  });

  it("no field to blame (non-field, residual-only, network) goes to the save button", () => {
    expect(saveErrorFocusTarget(new ApiError("找不到指定的部位", 404))).toBe("save");
    expect(saveErrorFocusTarget(new ApiError("x", 422, { body: "b" }))).toBe("save");
    expect(saveErrorFocusTarget(new Error("boom"))).toBe("save");
  });

  it("element ids", () => {
    expect(positionFieldInputId(7, "avg_cost")).toBe("pos-7-avg_cost");
    expect(positionSaveButtonId(7)).toBe("pos-save-7");
    expect(positionRemoveButtonId(7)).toBe("pos-remove-7");
  });
});
