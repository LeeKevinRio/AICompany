import { describe, expect, it } from "vitest";
import {
  deleteButtonState,
  shouldBlockPositionSubmit,
  submitButtonState,
} from "../positionFormSubmit";

describe("shouldBlockPositionSubmit — Enter-key / re-entry guard", () => {
  it("blocks a submit while the mutation is pending", () => {
    expect(shouldBlockPositionSubmit(true)).toBe(true);
  });

  it("allows a submit while the mutation is idle", () => {
    expect(shouldBlockPositionSubmit(false)).toBe(false);
  });
});

describe("submitButtonState — 儲存/新增/匯入 single-instance button", () => {
  it("shows the idle label and is enabled when not pending", () => {
    expect(submitButtonState(false, "儲存變更", "儲存中…")).toEqual({
      disabled: false,
      label: "儲存變更",
    });
  });

  it("shows the pending label and is disabled while pending", () => {
    expect(submitButtonState(true, "儲存變更", "儲存中…")).toEqual({
      disabled: true,
      label: "儲存中…",
    });
  });

  it("carries each caller's own verbatim labels through unchanged", () => {
    expect(submitButtonState(true, "新增部位", "新增中…")).toEqual({
      disabled: true,
      label: "新增中…",
    });
    expect(submitButtonState(true, "上傳並匯入", "匯入中…")).toEqual({
      disabled: true,
      label: "匯入中…",
    });
  });
});

describe("deleteButtonState — per-row 刪除 button on a shared mutation instance", () => {
  it("is idle and enabled for every row when nothing is pending", () => {
    expect(deleteButtonState(null, 1)).toEqual({ disabled: false, label: "刪除" });
    expect(deleteButtonState(null, 2)).toEqual({ disabled: false, label: "刪除" });
  });

  it("shows 刪除中… only on the row actually being deleted", () => {
    expect(deleteButtonState(1, 1)).toEqual({ disabled: true, label: "刪除中…" });
  });

  it("disables every other row too, so a second row's delete cannot race the first on the shared instance", () => {
    // Row 2 is not the one being deleted, but must still be disabled while
    // row 1's delete is in flight — otherwise clicking it would fire a
    // second `mutate()` on the same `useDeletePosition()` instance and steal
    // row 1's pending indicator (the bug this module exists to close).
    expect(deleteButtonState(1, 2)).toEqual({ disabled: true, label: "刪除" });
  });

  it("clears back to idle for all rows once pendingDeleteId resets to null", () => {
    expect(deleteButtonState(null, 1)).toEqual({ disabled: false, label: "刪除" });
  });
});
