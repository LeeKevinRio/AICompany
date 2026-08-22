/**
 * Unit tests for `KellyDeleteDialog.tsx`'s pure/pure-ish decision logic
 * (`resolveDeleteTriggerDecision`) — this repo has no
 * `@testing-library/react`/jsdom yet (`vitest.config.ts`'s own doc comment),
 * so these test the extracted function directly rather than rendering the
 * dialog. DOM-level assertions (the "刪除" trigger not appearing when
 * `hasRow` is false, cancelling never calling `DELETE`, the dialog closing on
 * `onError` per B6's pattern) are qa-e2e's to verify on a real page.
 */

import { describe, expect, it } from "vitest";
import { resolveDeleteTriggerDecision } from "../../settings/KellyDeleteDialog";
import type { KellyDeleteNoticeView } from "../types";

// Fixture text is deliberately synthetic (ASCII placeholders): the function
// under test branches only on whether `delete_notice` is `null`, never on
// its wording.
const NOTICE: KellyDeleteNoticeView = {
  title: "TEST_DELETE_TITLE",
  body: ["TEST_BODY_1", "TEST_BODY_2", "TEST_BODY_3", "TEST_BODY_4"],
  confirm_label: "TEST_CONFIRM_DELETE",
  cancel_label: "TEST_CANCEL",
};

describe("resolveDeleteTriggerDecision — 條件 111/114 (never a stale variant, never opens on a vanished row)", () => {
  it("opens the dialog with the freshly fetched delete_notice on success", async () => {
    const decision = await resolveDeleteTriggerDecision(async () => ({
      disclosures: { delete_notice: NOTICE },
    }));
    expect(decision).toEqual({ kind: "open-dialog", notice: NOTICE });
  });

  it("aborts when the fresh read says the row is gone (delete_notice: null) — never opens an empty dialog", async () => {
    const decision = await resolveDeleteTriggerDecision(async () => ({
      disclosures: { delete_notice: null },
    }));
    expect(decision).toEqual({ kind: "abort" });
  });

  it("aborts — never falls back to a stale notice — when the fetch rejects", async () => {
    const decision = await resolveDeleteTriggerDecision(() => Promise.reject(new Error("network")));
    expect(decision).toEqual({ kind: "abort" });
  });

  it("never invents a notice: the opened decision's `notice` is reference-equal to the fetched one", async () => {
    const decision = await resolveDeleteTriggerDecision(async () => ({
      disclosures: { delete_notice: NOTICE },
    }));
    if (decision.kind !== "open-dialog") throw new Error("expected open-dialog");
    expect(decision.notice).toBe(NOTICE);
  });
});
