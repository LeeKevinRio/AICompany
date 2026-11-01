/**
 * State machine of the EMERGENCY_EXIT confirmation dialog's check sentences
 * (風控 Q8 F-1～F-3 and Q11 R-1～R-6 / F-1、F-2、F-9、F-10; tech-architect Q14
 * FE-C14～FE-C18). Pure functions only, so the whole rule table runs in the node
 * test environment; the component just feeds events in.
 *
 * The principle (Q11): a tick means 「I have read *this* sentence」, so it may
 * only stand for the sentence that was on screen when it was made. A sentence is
 * swapped only when the system *knows* its content changed, and a swap clears
 * the ticks of the sentences that changed — and only those.
 *
 * - R-1  The set is decided once, when the dialog opens: the backend's
 *        `exit_confirm` when `/today` is successful, the degraded set otherwise.
 *        It is held here, in the dialog's own state, and thrown away on close.
 *        The stale `exit_confirm` of a failed refetch is never an input.
 * - R-2  `/today` turning non-successful changes nothing.
 * - R-3  `/today` successful with different content swaps the changed
 *        sentences and clears exactly their ticks.
 * - R-4  A formal set held from an earlier Taipei day is replaced by the
 *        degraded set, then handled like R-3.
 * - R-5  At step 3, a swap sends the user back to step 2 only if the set they
 *        confirmed was the formal one; a confirmed degraded set stays put until
 *        the dialog closes. While a submit is in flight nothing changes at all.
 * - R-6  N1 is shown only when at least one tick was cleared by the system.
 */

import { EXIT_CONFIRM_FALLBACK_CHECKS, exitConfirmChecks, allExitChecksConfirmed } from "./playbookView";
import { taipeiDayKey } from "./taipeiDay";
import type { PlaybookExitConfirm } from "./types";

export type ExitStep = "confirm" | "final";
export type ExitCheckSource = "formal" | "degraded";

/**
 * The part of `GET /today` the dialog may see. Built by the page with
 * `exitConfirm` taken from `today.isSuccess ? today.data.exit_confirm : null`
 * (F-1), so a failed refetch's leftover data can never reach the dialog.
 */
export interface ExitTodayView {
  readonly status: "pending" | "error" | "success";
  /** TanStack's `dataUpdatedAt` — the client-clock moment the data was last fetched OK. */
  readonly dataUpdatedAt: number;
  readonly exitConfirm: PlaybookExitConfirm | null;
}

export interface ExitDialogState {
  readonly step: ExitStep;
  readonly source: ExitCheckSource;
  /** The set on screen, in display order. */
  readonly texts: readonly string[];
  /** One tick per sentence, index-aligned with `texts`. */
  readonly checks: readonly boolean[];
  /**
   * When the formal set was last known current (`dataUpdatedAt`). A snapshot
   * taken when the set was adopted or re-confirmed identical — deliberately not
   * the live query value, which also moves while the lock suppresses
   * reconciliation. `null` for the degraded set.
   */
  readonly heldAt: number | null;
  /** The set the user confirmed at step 2; `null` until they continue. */
  readonly confirmedSource: ExitCheckSource | null;
  /** N1 is on screen (R-6). Stays until the dialog closes. */
  readonly notice: boolean;
}

export type ExitDialogAction =
  | { readonly type: "reconcile"; readonly today: ExitTodayView; readonly now: number }
  | { readonly type: "expire"; readonly now: number }
  | { readonly type: "toggle"; readonly index: number }
  | { readonly type: "advance" };

interface SelectedChecks {
  readonly texts: readonly string[];
  readonly source: ExitCheckSource;
}

/** The set `/today` offers right now (F-1): backend's when present, else degraded. */
export function selectExitChecks(exitConfirm: PlaybookExitConfirm | null): SelectedChecks {
  const texts = exitConfirmChecks(exitConfirm);
  const formal = exitConfirm !== null && exitConfirm.checks.length > 0;
  return { texts, source: formal ? "formal" : "degraded" };
}

/** R-1: decide the set when the dialog opens. */
export function createExitDialogState(today: ExitTodayView): ExitDialogState {
  const selected = selectExitChecks(today.status === "success" ? today.exitConfirm : null);
  return {
    step: "confirm",
    source: selected.source,
    texts: selected.texts,
    checks: selected.texts.map(() => false),
    heldAt: selected.source === "formal" ? today.dataUpdatedAt : null,
    confirmedSource: null,
    notice: false,
  };
}

function sameTexts(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((text, i) => text === b[i]);
}

/** R-4's trigger: a formal set whose acquisition moment is on an earlier Taipei day. */
export function isExitChecksStale(state: ExitDialogState, now: number): boolean {
  return (
    state.source === "formal" &&
    state.heldAt !== null &&
    taipeiDayKey(state.heldAt) !== taipeiDayKey(now)
  );
}

interface Replacement {
  readonly texts: readonly string[];
  readonly source: ExitCheckSource;
  readonly heldAt: number | null;
}

/** Swap in a new set: clear the ticks of changed sentences, apply R-5 and R-6. */
function replaceChecks(state: ExitDialogState, next: Replacement): ExitDialogState {
  // A confirmed degraded set stays on screen until close (R-5); nothing about
  // step 3 changes, N1 stays hidden (AC-50).
  if (state.step === "final" && state.confirmedSource === "degraded") return state;

  const sameLength = next.texts.length === state.texts.length;
  // A different sentence count cannot be mapped index by index: every sentence
  // counts as changed (the backend always sends four, so this is the safe side).
  const changed = next.texts.map((text, i) => !sameLength || text !== state.texts[i]);
  const checks = next.texts.map((_, i) => !changed[i] && state.checks[i] === true);
  const cleared = state.checks.some((ticked, i) => ticked && (!sameLength || changed[i] === true));

  const stepsBack = state.step === "final"; // here the confirmed set was the formal one
  return {
    step: stepsBack ? "confirm" : state.step,
    source: next.source,
    texts: next.texts,
    checks,
    heldAt: next.heldAt,
    confirmedSource: stepsBack ? null : state.confirmedSource,
    notice: state.notice || cleared,
  };
}

/**
 * Apply what `/today` now says (or, with `today = null`, only the passage of
 * time) to the dialog. Returns the *same object* when nothing changes, so a
 * dispatch from an effect cannot loop.
 *
 * `locked` is the submit lock / `isPending`: while it is held nothing is
 * evaluated at all (R-5), and the caller re-runs this after release so the
 * latest `/today` is considered then (FE-C16).
 */
export function reconcileExitChecks(
  state: ExitDialogState,
  today: ExitTodayView | null,
  now: number,
  locked: boolean,
): ExitDialogState {
  if (locked) return state;

  let current = state;
  if (today !== null && today.status === "success") {
    const offered = selectExitChecks(today.exitConfirm);
    if (!sameTexts(offered.texts, current.texts)) {
      return replaceChecks(current, {
        texts: offered.texts,
        source: offered.source,
        heldAt: offered.source === "formal" ? today.dataUpdatedAt : null,
      });
    }
    // Identical content, successfully re-fetched just now: the held sentences
    // were true at this newer moment too, so restart R-4's clock instead of
    // degrading a set that was just re-confirmed (FE-C18; 待風控確認 Q16).
    if (current.source === "formal" && current.heldAt !== today.dataUpdatedAt) {
      current = { ...current, heldAt: today.dataUpdatedAt };
    }
  }
  // R-2: a non-successful `/today` falls through untouched. R-4 is the only
  // thing left that can change a held set.
  if (isExitChecksStale(current, now)) {
    return replaceChecks(current, {
      texts: [...EXIT_CONFIRM_FALLBACK_CHECKS],
      source: "degraded",
      heldAt: null,
    });
  }
  return current;
}

export function exitDialogReducer(
  state: ExitDialogState,
  action: ExitDialogAction,
): ExitDialogState {
  switch (action.type) {
    case "reconcile":
      // The lock is checked by the caller (it must read the live ref at effect
      // time); the reducer is only given states it may act on.
      return reconcileExitChecks(state, action.today, action.now, false);
    case "expire":
      return reconcileExitChecks(state, null, action.now, false);
    case "toggle": {
      if (state.step !== "confirm" || action.index < 0 || action.index >= state.checks.length) {
        return state;
      }
      return {
        ...state,
        checks: state.checks.map((ticked, i) => (i === action.index ? !ticked : ticked)),
      };
    }
    case "advance": {
      if (state.step !== "confirm" || !allExitChecksConfirmed(state.checks)) return state;
      return { ...state, step: "final", confirmedSource: state.source };
    }
    default:
      return state;
  }
}

export type SubmitPlan = "ignore" | "stepBack" | "submit";

/**
 * What a click on 「確認送出全部出清」 does (FE-C17). Runs *before* the lock is
 * taken: a locked click is ignored; a click on a formal set that has crossed a
 * Taipei midnight becomes the R-5 step back instead of an irreversible POST
 * (the lock is not held yet, so this is not 「換句 while submitting」 — 待風控
 * 確認 Q16); anything else goes through.
 */
export function planSubmit(state: ExitDialogState, now: number, locked: boolean): SubmitPlan {
  if (locked) return "ignore";
  if (state.confirmedSource === "formal" && isExitChecksStale(state, now)) return "stepBack";
  return "submit";
}

export type AdvancePlan = "advance" | "expire";

/** What a click on 「我已閱讀，繼續」 does: re-check R-4 synchronously first. */
export function planAdvance(state: ExitDialogState, now: number): AdvancePlan {
  return isExitChecksStale(state, now) ? "expire" : "advance";
}
