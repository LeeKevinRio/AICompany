/**
 * Pure helpers for the dialog focus management of `EditPositionModal`
 * (kept out of the component so the Tab-cycling decision is unit-testable
 * under the node test environment, which has no DOM).
 */

/** Elements a Tab key can land on; disabled controls are skipped. */
export const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

/** The first control that takes typed input (what the dialog focuses on open). */
export const FIRST_FIELD_SELECTOR = "input:not([disabled]), select:not([disabled]), textarea:not([disabled])";

/**
 * Where Tab / Shift+Tab should move inside a trapped dialog.
 *
 * `activeIndex` is the position of the currently focused element within the
 * dialog's focusable list, or `-1` when focus is not on any of them (e.g. on
 * the dialog container itself). Returns the index to focus explicitly, or
 * `null` when the browser's default movement already stays inside the dialog.
 */
export function trapTabTarget(count: number, activeIndex: number, shiftKey: boolean): number | null {
  if (count === 0) return null;
  const last = count - 1;
  if (shiftKey) {
    return activeIndex <= 0 ? last : null;
  }
  return activeIndex === -1 || activeIndex >= last ? 0 : null;
}
