/**
 * Focus hand-off when the 全部出清 trigger swaps position (FE-C20, tech-architect
 * Q14 §3).
 *
 * The trigger lives in the sticky status bar while `/today` is successful and in
 * the h1 row otherwise, so a `/today` transition unmounts one button and mounts
 * the other in the same commit. A keyboard user who is sitting on the old one
 * would otherwise be dropped on `<body>`.
 *
 * This only *rescues focus that was just lost*: all three conditions must hold.
 * It never moves focus away from an element the user chose, never scrolls
 * (`preventScroll` at the call site), and adds no wording — so it sits beside,
 * not against, the 「不搬動焦點」 clauses (§2.4, V-41, R-6, F-7).
 */
export interface FocusHandOffInput {
  /** The exit dialog is open: focus belongs inside it, never hand off. */
  readonly dialogOpen: boolean;
  /** The trigger that just unmounted held focus when it was removed. */
  readonly lostFocusOnUnmount: boolean;
  /** After the commit, `document.activeElement` is `<body>` (or null). */
  readonly activeIsBodyOrNull: boolean;
}

export function shouldHandOffFocus(input: FocusHandOffInput): boolean {
  return !input.dialogOpen && input.lostFocusOnUnmount && input.activeIsBodyOrNull;
}
