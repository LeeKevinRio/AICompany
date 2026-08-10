/**
 * The one-time confirmation shown before a risk cap is widened (FR-9 (e)).
 *
 * Raising `max_gross_exposure` stays inside the 1.50 hard ceiling and needs no
 * code change, but it is still the user opening a gate — and a gate that opens
 * on the same click as "save" is one nobody had to notice. So the first submit
 * that raises it becomes a confirmation, and only the second one writes.
 *
 * The decision lives here rather than inside `SettingsForm` because of the
 * defect this module was extracted to fix: confirming a raise to 1.20, then
 * editing the field to 1.50 and pressing save, used to write 1.50 while the
 * only sentence the user ever confirmed said 1.20. A confirmation that does not
 * name the value being written is not a confirmation, so
 * {@link resolveWideningSubmit} re-derives the raise at submit time and
 * compares it with the one on screen — any difference starts the confirmation
 * over, with the new number in it.
 *
 * Pure functions, no React: this is the part that must be provably right, and
 * this project's test setup runs plain-Node unit tests (see `vitest.config.ts`).
 */

/** A raise being asked for: where the cap stands, and where it would go. */
export interface CapWidening {
  before: number;
  after: number;
}

/**
 * The raise implied by `after`, or `null` when the cap is unchanged, lowered,
 * or not a usable number.
 *
 * A non-numeric entry is deliberately *not* treated as a widening: the backend
 * is the authority on what the field accepts, and it answers with a per-field
 * 422. Demanding confirmation of a value that cannot be written would put a
 * risk warning in front of a plain typo.
 */
export function capWidening(before: number, after: number): CapWidening | null {
  if (!Number.isFinite(after) || !Number.isFinite(before)) return null;
  if (after <= before) return null;
  return { before, after };
}

/** Whether two raises are the same one; `null` (no raise) equals only `null`. */
export function isSameWidening(a: CapWidening | null, b: CapWidening | null): boolean {
  if (a === null || b === null) return a === b;
  return a.before === b.before && a.after === b.after;
}

/**
 * What a submit should do, given the raise the form would write and the raise
 * the confirmation panel is currently showing (`shown`) — clicking submit while
 * a panel is up is the act of confirming *that* pair of numbers.
 *
 * * `"submit"` — no raise, or the raise on screen is exactly this one.
 * * `"confirm"` — hold the write and show `widening`. Returned both for a
 *   first-time raise and for one that *changed* after being shown, which is
 *   the whole point: the sentence on screen and the value about to be written
 *   are always the same number.
 */
export function resolveWideningSubmit(
  widening: CapWidening | null,
  shown: CapWidening | null,
): { action: "submit" | "confirm"; widening: CapWidening | null } {
  if (widening === null) return { action: "submit", widening: null };
  if (isSameWidening(widening, shown)) return { action: "submit", widening: null };
  return { action: "confirm", widening };
}

/**
 * S4 fix (risk-final-review.md 列管項): generalises {@link resolveWideningSubmit}
 * from the single `max_gross_exposure` field to any set of independently
 * widenable fields (`SettingsForm.tsx`'s `WIDENING_FIELDS`), keyed by field
 * name — `max_position_weight` carries the same kind of hard ceiling and the
 * previous single-field version silently let it through unconfirmed.
 *
 * Same all-or-nothing rule as the single-field version, extended across
 * fields: *any* field needing confirmation holds the entire submit (never a
 * partial write of "the fields nobody objected to"). While the submit is
 * held, `pending` carries forward *every* field currently being widened —
 * including one already agreed to in an earlier round — not just the newly
 * confirm-needing one: dropping an already-agreed field from `pending`
 * would make the next call's `shown` lookup miss it and re-open a
 * confirmation the caller already clicked through, just because a sibling
 * field also needed one. Once every active field matches what was shown
 * (nothing left to agree to), `pending` collapses to `{}` and the caller
 * writes — the same terminal state the single-field version reached.
 */
export function resolveWideningSubmitForFields(
  current: Record<string, CapWidening | null>,
  shown: Partial<Record<string, CapWidening>>,
): { action: "submit" | "confirm"; pending: Partial<Record<string, CapWidening>> } {
  const active: Partial<Record<string, CapWidening>> = {};
  let needsConfirm = false;
  for (const [key, widening] of Object.entries(current)) {
    if (widening === null) continue;
    active[key] = widening;
    if (resolveWideningSubmit(widening, shown[key] ?? null).action === "confirm") {
      needsConfirm = true;
    }
  }
  return { action: needsConfirm ? "confirm" : "submit", pending: needsConfirm ? active : {} };
}
