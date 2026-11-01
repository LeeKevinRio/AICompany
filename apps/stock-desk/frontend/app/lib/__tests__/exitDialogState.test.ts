/**
 * FE-T8 / FE-T10: the scenario matrix for the dialog's check-sentence rules —
 * 風控 Q8 F-1～F-3 and Q11 R-1～R-6, with the PRD acceptance ids they back
 * (AC-46～AC-54, AC-56).
 */

import { describe, expect, it } from "vitest";
import {
  type ExitDialogAction,
  type ExitDialogState,
  createExitDialogState,
  exitDialogReducer,
  isExitChecksStale,
  planAdvance,
  planSubmit,
  reconcileExitChecks,
  selectExitChecks,
} from "../exitDialogState";
import { EXIT_CONFIRM_FALLBACK_CHECKS } from "../playbookView";
import {
  FIRST_MS_AUG_12,
  LAST_MS_AUG_11,
  MORNING_AUG_12,
  NOON_AUG_11,
  exitConfirmBlock,
  failedToday,
  formalChecks,
  successToday,
} from "./exitFixtures";

const FALLBACK = [...EXIT_CONFIRM_FALLBACK_CHECKS];

/** Tick exactly these sentences (toggle through the reducer, as the UI does). */
function withTicks(state: ExitDialogState, indices: readonly number[]): ExitDialogState {
  return indices.reduce((s, index) => exitDialogReducer(s, { type: "toggle", index }), state);
}

function reduce(state: ExitDialogState, ...actions: ExitDialogAction[]): ExitDialogState {
  return actions.reduce(exitDialogReducer, state);
}

function tickedIndices(state: ExitDialogState): number[] {
  return state.checks.flatMap((ticked, i) => (ticked ? [i] : []));
}

const openFormal = () => createExitDialogState(successToday());
const openDegraded = () => createExitDialogState(failedToday("pending"));

describe("R-1: the set is decided once, when the dialog opens (AC-56, F-1)", () => {
  it("success: the backend's sentences, nothing ticked, held since dataUpdatedAt", () => {
    const state = openFormal();
    expect(state.source).toBe("formal");
    expect(state.texts).toEqual(formalChecks(20, "2026-09-09"));
    expect(state.checks).toEqual([false, false, false, false]);
    expect(state.heldAt).toBe(NOON_AUG_11);
    expect(state.step).toBe("confirm");
    expect(state.confirmedSource).toBeNull();
    expect(state.notice).toBe(false);
  });

  it.each(["pending", "error"] as const)("%s: the degraded set, no held time", (status) => {
    const state = createExitDialogState(failedToday(status));
    expect(state.source).toBe("degraded");
    expect(state.texts).toEqual(FALLBACK);
    expect(state.heldAt).toBeNull();
  });

  it("a failed refetch whose view still (wrongly) carries the old block is not used", () => {
    // F-1: the page builds the view from `isSuccess ? data.exit_confirm : null`; and
    // even if a caller slipped, a non-success status never selects the formal set.
    const state = createExitDialogState({
      status: "error",
      dataUpdatedAt: NOON_AUG_11,
      exitConfirm: exitConfirmBlock(7, "2026-08-20"),
    });
    expect(state.source).toBe("degraded");
    expect(state.texts.join("")).not.toContain("2026-08-20");
  });

  it("a successful /today without a usable block is also the degraded set, never an empty list", () => {
    expect(selectExitChecks(null)).toEqual({ texts: FALLBACK, source: "degraded" });
    expect(selectExitChecks({ ...exitConfirmBlock(), checks: [] })).toEqual({
      texts: FALLBACK,
      source: "degraded",
    });
    expect(createExitDialogState(successToday({ exitConfirm: null })).heldAt).toBeNull();
  });

  it("every state the machine produces has at least one sentence per tick", () => {
    const state = openDegraded();
    expect(state.texts.length).toBeGreaterThan(0);
    expect(state.checks).toHaveLength(state.texts.length);
  });
});

describe("R-2: /today turning non-successful changes nothing (AC-47)", () => {
  it.each(["error", "pending"] as const)("success -> %s keeps sentences and ticks, no N1", (status) => {
    const before = withTicks(openFormal(), [0, 1, 2]);
    const after = reconcileExitChecks(before, failedToday(status), NOON_AUG_11 + 60_000, false);
    expect(after).toBe(before);
    expect(after.notice).toBe(false);
  });

  it("a later recovery with identical content still changes no sentence, no tick, no N1", () => {
    const before = withTicks(openFormal(), [0, 1, 2, 3]);
    const failed = reconcileExitChecks(before, failedToday("error"), NOON_AUG_11 + 1000, false);
    const recovered = reconcileExitChecks(
      failed,
      successToday({ dataUpdatedAt: NOON_AUG_11 + 5000 }),
      NOON_AUG_11 + 5000,
      false,
    );
    expect(recovered.texts).toEqual(before.texts);
    expect(recovered.checks).toEqual(before.checks);
    expect(recovered.notice).toBe(false);
    expect(recovered.step).toBe("confirm");
  });
});

describe("R-3 + R-6 at step 2 (AC-46, AC-48, AC-53)", () => {
  it("degraded -> formal: only sentence 2 is swapped and un-ticked, the others keep their ticks, N1 appears", () => {
    const before = withTicks(openDegraded(), [0, 1, 2, 3]);
    const after = reconcileExitChecks(before, successToday(), NOON_AUG_11, false);
    expect(after.source).toBe("formal");
    expect(after.texts).toEqual(formalChecks(20, "2026-09-09"));
    expect(tickedIndices(after)).toEqual([0, 2, 3]);
    expect(after.notice).toBe(true);
    expect(after.step).toBe("confirm");
    expect(after.heldAt).toBe(NOON_AUG_11);
  });

  it("the swap is not decided by sentence count (both sets have four) — the tick on the old sentence does not carry over", () => {
    const before = withTicks(openDegraded(), [1]);
    expect(before.texts).toHaveLength(formalChecks(20, "x").length);
    const after = reconcileExitChecks(before, successToday(), NOON_AUG_11, false);
    expect(after.checks[1]).toBe(false);
  });

  it("「繼續」becomes unavailable until sentence 2 is ticked again", () => {
    const before = withTicks(openDegraded(), [0, 1, 2, 3]);
    const swapped = reconcileExitChecks(before, successToday(), NOON_AUG_11, false);
    expect(reduce(swapped, { type: "advance" }).step).toBe("confirm");
    const reticked = reduce(swapped, { type: "toggle", index: 1 }, { type: "advance" });
    expect(reticked.step).toBe("final");
  });

  it("degraded -> formal with sentence 2 un-ticked: swapped, others keep ticks, NO N1 (nothing was cleared)", () => {
    const before = withTicks(openDegraded(), [0, 2, 3]);
    const after = reconcileExitChecks(before, successToday(), NOON_AUG_11, false);
    expect(after.texts).toEqual(formalChecks(20, "2026-09-09"));
    expect(tickedIndices(after)).toEqual([0, 2, 3]);
    expect(after.notice).toBe(false);
  });

  it("same-day number change on the formal set, sentence ticked: only it is cleared, N1 appears (⑧a)", () => {
    const before = withTicks(openFormal(), [0, 1, 2, 3]);
    const after = reconcileExitChecks(
      before,
      successToday({ exitConfirm: exitConfirmBlock(19, "2026-09-08"), dataUpdatedAt: NOON_AUG_11 + 1000 }),
      NOON_AUG_11 + 1000,
      false,
    );
    expect(after.texts).toEqual(formalChecks(19, "2026-09-08"));
    expect(tickedIndices(after)).toEqual([0, 2, 3]);
    expect(after.notice).toBe(true);
    expect(after.heldAt).toBe(NOON_AUG_11 + 1000);
  });

  it("same-day number change, sentence not ticked: the new sentence is shown, no N1 (⑧b)", () => {
    const before = withTicks(openFormal(), [0, 2]);
    const after = reconcileExitChecks(
      before,
      successToday({ exitConfirm: exitConfirmBlock(19, "2026-09-08") }),
      NOON_AUG_11,
      false,
    );
    expect(after.texts).toEqual(formalChecks(19, "2026-09-08"));
    expect(tickedIndices(after)).toEqual([0, 2]);
    expect(after.notice).toBe(false);
  });

  it("identical content: no swap, no clearing, no N1, and the held time moves forward (FE-C18)", () => {
    const before = withTicks(openFormal(), [0, 1, 2, 3]);
    const later = NOON_AUG_11 + 3_600_000;
    const after = reconcileExitChecks(before, successToday({ dataUpdatedAt: later }), later, false);
    expect(after.texts).toBe(before.texts);
    expect(after.checks).toBe(before.checks);
    expect(after.notice).toBe(false);
    expect(after.heldAt).toBe(later);
  });

  it("identical content with the same acquisition time returns the very same state (no render loop)", () => {
    const before = openFormal();
    expect(reconcileExitChecks(before, successToday(), NOON_AUG_11, false)).toBe(before);
    const degraded = openDegraded();
    expect(reconcileExitChecks(degraded, failedToday("pending"), NOON_AUG_11, false)).toBe(degraded);
  });

  it("a different number of sentences clears every tick and counts as a change of all", () => {
    const before = withTicks(openFormal(), [0, 1, 2, 3]);
    const three = { ...exitConfirmBlock(), checks: formalChecks(20, "2026-09-09").slice(0, 3) };
    const after = reconcileExitChecks(before, successToday({ exitConfirm: three }), NOON_AUG_11, false);
    expect(after.texts).toHaveLength(3);
    expect(after.checks).toEqual([false, false, false]);
    expect(after.notice).toBe(true);
  });

  it("a different number of sentences with nothing ticked shows no N1", () => {
    const three = { ...exitConfirmBlock(), checks: formalChecks(20, "2026-09-09").slice(0, 3) };
    const after = reconcileExitChecks(openFormal(), successToday({ exitConfirm: three }), NOON_AUG_11, false);
    expect(after.checks).toEqual([false, false, false]);
    expect(after.notice).toBe(false);
  });

  it("success whose block disappeared swaps the formal set for the degraded one (it is a content change)", () => {
    const before = withTicks(openFormal(), [0, 1]);
    const after = reconcileExitChecks(before, successToday({ exitConfirm: null }), NOON_AUG_11, false);
    expect(after.source).toBe("degraded");
    expect(after.texts).toEqual(FALLBACK);
    expect(after.heldAt).toBeNull();
    expect(tickedIndices(after)).toEqual([0]);
    expect(after.notice).toBe(true);
  });
});

describe("R-4: a formal set held across a Taipei midnight is replaced by the degraded set (AC-52)", () => {
  it("crosses at the exact boundary: 23:59:59.999 stays, 00:00:00.000 degrades", () => {
    const state = withTicks(openFormal(), [0, 1, 2, 3]);
    expect(isExitChecksStale(state, LAST_MS_AUG_11)).toBe(false);
    expect(isExitChecksStale(state, FIRST_MS_AUG_12)).toBe(true);
    expect(exitDialogReducer(state, { type: "expire", now: LAST_MS_AUG_11 })).toBe(state);
  });

  it("swaps to the degraded set, clears only sentence 2 (the only one that differs), shows N1", () => {
    const before = withTicks(openFormal(), [0, 1, 2, 3]);
    const after = exitDialogReducer(before, { type: "expire", now: MORNING_AUG_12 });
    expect(after.source).toBe("degraded");
    expect(after.texts).toEqual(FALLBACK);
    expect(tickedIndices(after)).toEqual([0, 2, 3]);
    expect(after.notice).toBe(true);
    expect(after.heldAt).toBeNull();
  });

  it("⑦b: sentence 2 not ticked -> degraded set shown, nothing cleared, no N1", () => {
    const before = withTicks(openFormal(), [0, 2, 3]);
    const after = exitDialogReducer(before, { type: "expire", now: MORNING_AUG_12 });
    expect(after.texts).toEqual(FALLBACK);
    expect(tickedIndices(after)).toEqual([0, 2, 3]);
    expect(after.notice).toBe(false);
  });

  it("does not apply to a degraded set (nothing to distrust)", () => {
    const state = withTicks(openDegraded(), [0, 1, 2, 3]);
    expect(exitDialogReducer(state, { type: "expire", now: MORNING_AUG_12 })).toBe(state);
  });

  it("a fresh successful fetch of identical content restarts the clock instead of degrading", () => {
    const before = withTicks(openFormal(), [0, 1, 2, 3]);
    const after = reconcileExitChecks(
      before,
      successToday({ dataUpdatedAt: MORNING_AUG_12 }),
      MORNING_AUG_12,
      false,
    );
    expect(after.source).toBe("formal");
    expect(after.heldAt).toBe(MORNING_AUG_12);
    expect(after.notice).toBe(false);
  });

  it("a non-successful /today does not postpone R-4", () => {
    const before = withTicks(openFormal(), [0, 1, 2, 3]);
    const after = reconcileExitChecks(before, failedToday("error"), MORNING_AUG_12, false);
    expect(after.source).toBe("degraded");
    expect(after.notice).toBe(true);
  });

  it("dialog opened on yesterday's cached success data degrades on the very first reconcile", () => {
    const opened = createExitDialogState(successToday({ dataUpdatedAt: NOON_AUG_11 }));
    const after = reconcileExitChecks(opened, null, MORNING_AUG_12, false);
    expect(after.source).toBe("degraded");
    expect(after.notice).toBe(false); // nothing had been ticked yet
  });
});

describe("heldAt update rules (風控 2026-11-01 FE-5)", () => {
  it("(e1) crossed midnight, then a newer fetch with identical content: heldAt moves, no N1, no step back", () => {
    const final = exitDialogReducer(withTicks(openFormal(), [0, 1, 2, 3]), { type: "advance" });
    const after = reconcileExitChecks(
      final,
      successToday({ dataUpdatedAt: MORNING_AUG_12 }),
      MORNING_AUG_12,
      false,
    );
    expect(after.step).toBe("final");
    expect(after.source).toBe("formal");
    expect(after.heldAt).toBe(MORNING_AUG_12);
    expect(after.notice).toBe(false);
    expect(tickedIndices(after)).toEqual([0, 1, 2, 3]);
  });

  it("(e2) the order matters: new success data first, then R-4 with the updated heldAt", () => {
    const ticked = withTicks(openFormal(), [0, 1, 2, 3]);
    const fresh = successToday({ dataUpdatedAt: MORNING_AUG_12 });
    // The right order, in one evaluation: no N1, the set is unchanged.
    const single = reconcileExitChecks(ticked, fresh, MORNING_AUG_12, false);
    expect(single.notice).toBe(false);
    expect(single.texts).toEqual(ticked.texts);
    // The reverse order (expire first, then take the data) is exactly the trap: it
    // ends on the very same sentences, but has cleared a tick and shown an N1
    // whose 「有變動的項目」 is untrue.
    const reversed = reconcileExitChecks(
      exitDialogReducer(ticked, { type: "expire", now: MORNING_AUG_12 }),
      fresh,
      MORNING_AUG_12,
      false,
    );
    expect(reversed.texts).toEqual(ticked.texts);
    expect(reversed.notice).toBe(true);
    expect(tickedIndices(reversed)).toEqual([0, 2, 3]);
  });

  it("an older or equal dataUpdatedAt never moves heldAt (error and retry-wait leave it alone)", () => {
    const state = openFormal();
    const same = reconcileExitChecks(state, successToday({ dataUpdatedAt: NOON_AUG_11 }), NOON_AUG_11, false);
    expect(same).toBe(state);
    const older = reconcileExitChecks(state, successToday({ dataUpdatedAt: NOON_AUG_11 - 1 }), NOON_AUG_11, false);
    expect(older).toBe(state);
    const error = reconcileExitChecks(state, failedToday("error", NOON_AUG_11 + 5000), NOON_AUG_11 + 5000, false);
    expect(error.heldAt).toBe(NOON_AUG_11);
  });

  it("never touches a degraded set's clock, and does nothing while the lock is held", () => {
    const degraded = openDegraded();
    const sameDegraded = reconcileExitChecks(
      degraded,
      successToday({ exitConfirm: null, dataUpdatedAt: NOON_AUG_11 + 5000 }),
      NOON_AUG_11 + 5000,
      false,
    );
    expect(sameDegraded.heldAt).toBeNull();
    const formal = openFormal();
    expect(
      reconcileExitChecks(formal, successToday({ dataUpdatedAt: NOON_AUG_11 + 5000 }), NOON_AUG_11 + 5000, true),
    ).toBe(formal);
  });

  it("the comparison is the whole list: a different sentence count is a change, not 「identical」", () => {
    const state = withTicks(openFormal(), [0, 1, 2, 3]);
    const longer = { ...exitConfirmBlock(), checks: [...formalChecks(20, "2026-09-09"), "extra"] };
    const after = reconcileExitChecks(state, successToday({ exitConfirm: longer, dataUpdatedAt: NOON_AUG_11 + 1 }), NOON_AUG_11 + 1, false);
    expect(after.texts).toHaveLength(5);
    expect(after.notice).toBe(true);
  });
});

describe("R-5: step 3 (AC-49, AC-50, AC-51, AC-54)", () => {
  function atFinal(open: ExitDialogState): ExitDialogState {
    const ticked = withTicks(open, open.texts.map((_, i) => i));
    const final = exitDialogReducer(ticked, { type: "advance" });
    expect(final.step).toBe("final");
    return final;
  }

  it("records which set the user confirmed", () => {
    expect(atFinal(openFormal()).confirmedSource).toBe("formal");
    expect(atFinal(openDegraded()).confirmedSource).toBe("degraded");
  });

  it("confirmed formal + same-day content change: back to step 2, only the changed tick cleared, N1 (AC-49)", () => {
    const final = atFinal(openFormal());
    const after = reconcileExitChecks(
      final,
      successToday({ exitConfirm: exitConfirmBlock(19, "2026-09-08") }),
      NOON_AUG_11,
      false,
    );
    expect(after.step).toBe("confirm");
    expect(after.texts).toEqual(formalChecks(19, "2026-09-08"));
    expect(tickedIndices(after)).toEqual([0, 2, 3]);
    expect(after.notice).toBe(true);
    expect(after.confirmedSource).toBeNull();
  });

  it("confirmed formal + R-4: back to step 2 on the degraded set, N1 (AC-49, AC-52)", () => {
    const final = atFinal(openFormal());
    const after = exitDialogReducer(final, { type: "expire", now: MORNING_AUG_12 });
    expect(after.step).toBe("confirm");
    expect(after.texts).toEqual(FALLBACK);
    expect(tickedIndices(after)).toEqual([0, 2, 3]);
    expect(after.notice).toBe(true);
  });

  it("confirmed degraded + /today recovers with a different formal set: stays at step 3, set kept, no N1 (AC-50, AC-54)", () => {
    const final = atFinal(openDegraded());
    const after = reconcileExitChecks(final, successToday(), NOON_AUG_11, false);
    expect(after).toBe(final);
    expect(after.step).toBe("final");
    expect(after.texts).toEqual(FALLBACK);
    expect(after.notice).toBe(false);
  });

  it("confirmed degraded: the set stays until close even across a midnight", () => {
    const final = atFinal(openDegraded());
    expect(exitDialogReducer(final, { type: "expire", now: MORNING_AUG_12 })).toBe(final);
  });

  it("confirmed formal + /today fails: nothing changes (R-2), the failure panel can stay", () => {
    const final = atFinal(openFormal());
    expect(reconcileExitChecks(final, failedToday("error"), NOON_AUG_11 + 1000, false)).toBe(final);
  });

  it("after a step back the user re-ticks and continues; the recap shows the current sentences, N1 stays on", () => {
    const final = atFinal(openFormal());
    const back = reconcileExitChecks(
      final,
      successToday({ exitConfirm: exitConfirmBlock(19, "2026-09-08") }),
      NOON_AUG_11,
      false,
    );
    const again = reduce(back, { type: "toggle", index: 1 }, { type: "advance" });
    expect(again.step).toBe("final");
    expect(again.texts).toEqual(formalChecks(19, "2026-09-08"));
    expect(again.notice).toBe(true); // N1 persists into step 3 (r3 §13)
    expect(again.confirmedSource).toBe("formal");
  });
});

describe("the submit lock: nothing is evaluated while locked (AC-51, FE-C16)", () => {
  it("returns the very same state for any change while locked, whatever /today says", () => {
    const final = exitDialogReducer(
      withTicks(openFormal(), [0, 1, 2, 3]),
      { type: "advance" },
    );
    const changed = successToday({ exitConfirm: exitConfirmBlock(19, "2026-09-08") });
    expect(reconcileExitChecks(final, changed, NOON_AUG_11, true)).toBe(final);
    expect(reconcileExitChecks(final, failedToday("error"), MORNING_AUG_12, true)).toBe(final);
    expect(reconcileExitChecks(final, null, MORNING_AUG_12, true)).toBe(final);
  });

  it("runs again once released, against the latest /today", () => {
    const final = exitDialogReducer(withTicks(openFormal(), [0, 1, 2, 3]), { type: "advance" });
    const changed = successToday({ exitConfirm: exitConfirmBlock(19, "2026-09-08") });
    expect(reconcileExitChecks(final, changed, NOON_AUG_11, true)).toBe(final);
    const released = reconcileExitChecks(final, changed, NOON_AUG_11, false);
    expect(released.step).toBe("confirm");
    expect(released.notice).toBe(true);
  });
});

describe("N1 (R-6) lifetime", () => {
  it("stays on across steps and is gone when the dialog is opened again", () => {
    const swapped = reconcileExitChecks(
      withTicks(openDegraded(), [0, 1, 2, 3]),
      successToday(),
      NOON_AUG_11,
      false,
    );
    expect(swapped.notice).toBe(true);
    const final = reduce(swapped, { type: "toggle", index: 1 }, { type: "advance" });
    expect(final.notice).toBe(true);
    // Reopening builds a fresh state from /today; nothing carries over (F-1).
    expect(createExitDialogState(successToday()).notice).toBe(false);
  });

  it("never appears on open, on R-2, or on a normal flow to step 3", () => {
    let state = openFormal();
    expect(state.notice).toBe(false);
    state = reconcileExitChecks(state, failedToday("error"), NOON_AUG_11, false);
    expect(state.notice).toBe(false);
    state = reduce(withTicks(state, [0, 1, 2, 3]), { type: "advance" });
    expect(state.notice).toBe(false);
  });
});

describe("toggle / advance guards", () => {
  it("advance needs every sentence ticked", () => {
    expect(exitDialogReducer(withTicks(openFormal(), [0, 1, 2]), { type: "advance" }).step).toBe("confirm");
    expect(exitDialogReducer(withTicks(openFormal(), [0, 1, 2, 3]), { type: "advance" }).step).toBe("final");
  });

  it("toggle is a step-2 control only and ignores out-of-range indices", () => {
    const state = openFormal();
    expect(exitDialogReducer(state, { type: "toggle", index: 9 })).toBe(state);
    expect(exitDialogReducer(state, { type: "toggle", index: -1 })).toBe(state);
    const final = exitDialogReducer(withTicks(state, [0, 1, 2, 3]), { type: "advance" });
    expect(exitDialogReducer(final, { type: "toggle", index: 0 })).toBe(final);
  });

  it("advance cannot be repeated from step 3", () => {
    const final = exitDialogReducer(withTicks(openFormal(), [0, 1, 2, 3]), { type: "advance" });
    expect(exitDialogReducer(final, { type: "advance" })).toBe(final);
  });
});

describe("planSubmit (FE-T10, FE-C17)", () => {
  const confirmedFormal = () =>
    exitDialogReducer(withTicks(openFormal(), [0, 1, 2, 3]), { type: "advance" });
  const confirmedDegraded = () =>
    exitDialogReducer(withTicks(openDegraded(), [0, 1, 2, 3]), { type: "advance" });

  it("ignores a click while the lock is held, however stale", () => {
    expect(planSubmit(confirmedFormal(), NOON_AUG_11, true)).toBe("ignore");
    expect(planSubmit(confirmedFormal(), MORNING_AUG_12, true)).toBe("ignore");
  });

  it("submits a fresh confirmed set", () => {
    expect(planSubmit(confirmedFormal(), NOON_AUG_11 + 60_000, false)).toBe("submit");
    expect(planSubmit(confirmedFormal(), LAST_MS_AUG_11, false)).toBe("submit");
  });

  it("turns the click into the R-5 step back when a confirmed formal set has crossed midnight", () => {
    expect(planSubmit(confirmedFormal(), FIRST_MS_AUG_12, false)).toBe("stepBack");
    expect(planSubmit(confirmedFormal(), MORNING_AUG_12, false)).toBe("stepBack");
  });

  it("submits a confirmed degraded set at any time of day (nothing to step back for)", () => {
    expect(planSubmit(confirmedDegraded(), MORNING_AUG_12, false)).toBe("submit");
  });

  it("the stepBack plan is realised by the `expire` action and sends no request", () => {
    const state = confirmedFormal();
    expect(planSubmit(state, MORNING_AUG_12, false)).toBe("stepBack");
    const after = exitDialogReducer(state, { type: "expire", now: MORNING_AUG_12 });
    expect(after.step).toBe("confirm");
    expect(after.notice).toBe(true);
  });
});

describe("a click turned into a step back never loops (風控 2026-11-01 FE-6)", () => {
  it("step 3: the click is consumed (no request), and after re-ticking the next click submits exactly once", () => {
    const final = exitDialogReducer(withTicks(openFormal(), [0, 1, 2, 3]), { type: "advance" });
    expect(planSubmit(final, MORNING_AUG_12, false)).toBe("stepBack");
    const back = exitDialogReducer(final, { type: "expire", now: MORNING_AUG_12 });
    expect(back.step).toBe("confirm");
    expect(back.source).toBe("degraded");
    // Re-tick the cleared sentence, continue, and submit: R-4 only concerns a formal set.
    const again = reduce(back, { type: "toggle", index: 1 }, { type: "advance" });
    expect(again.step).toBe("final");
    expect(planSubmit(again, MORNING_AUG_12 + 1000, false)).toBe("submit");
    expect(planSubmit(again, MORNING_AUG_12 + 2000, true)).toBe("ignore"); // and a second click is locked out
  });

  it("step 2: 「繼續」 on a stale formal set swaps in place and does not advance", () => {
    const ticked = withTicks(openFormal(), [0, 1, 2, 3]);
    expect(planAdvance(ticked, MORNING_AUG_12)).toBe("expire");
    const after = exitDialogReducer(ticked, { type: "expire", now: MORNING_AUG_12 });
    expect(after.step).toBe("confirm");
    expect(after.texts).toEqual(FALLBACK);
    expect(exitDialogReducer(after, { type: "advance" }).step).toBe("confirm"); // sentence 2 is un-ticked
  });

  it("the step back never asks for the mutation to be reset: failure state is not part of this machine", () => {
    // R-5's step back keeps everything about the failed submit (FR-14g): the state
    // has no field for it, so there is nothing for the transition to clear.
    expect(Object.keys(openFormal()).sort()).toEqual(
      ["checks", "confirmedSource", "heldAt", "notice", "source", "step", "texts"].sort(),
    );
  });
});

describe("planAdvance (the 「我已閱讀，繼續」 handler re-checks R-4 synchronously)", () => {
  it("advances a fresh set and expires a stale one instead", () => {
    const ticked = withTicks(openFormal(), [0, 1, 2, 3]);
    expect(planAdvance(ticked, NOON_AUG_11)).toBe("advance");
    expect(planAdvance(ticked, MORNING_AUG_12)).toBe("expire");
    const expired = exitDialogReducer(ticked, { type: "expire", now: MORNING_AUG_12 });
    expect(exitDialogReducer(expired, { type: "advance" }).step).toBe("confirm");
  });

  it("never expires a degraded set", () => {
    expect(planAdvance(withTicks(openDegraded(), [0, 1, 2, 3]), MORNING_AUG_12)).toBe("advance");
  });
});
