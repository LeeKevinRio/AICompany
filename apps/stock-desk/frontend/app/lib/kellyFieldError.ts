/**
 * 條件 57 (`work/reviews/2026-08-19-C5-Kelly-文案批審.md`, 協調人三確認 2):
 * `KellyManualInput` sets `allow_inf_nan=False` (`app/kelly/models.py`) so a
 * `nan`/`inf`/`-inf` submission is refused by pydantic's own type layer
 * *before* the field validator that would otherwise raise
 * `KELLY_WIN_RATE_OUT_OF_RANGE_MESSAGE` / `KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE`
 * ever runs. The 422 body that reaches this app for that branch is pydantic's
 * own English `"Input should be a finite number"` — unreviewed copy, and
 * `app/api/kelly.py`'s own module doc comment is explicit that "the front end
 * renders and composes nothing" of its own (約束 21).
 *
 * Condition 57 requires one of two things here: render an already-approved
 * Chinese sentence, or a generic field-level notice. This module implements
 * the check as a **shape test on the message itself**, not a retyped copy of
 * either backend sentence: a message is only ever rendered when it contains
 * at least one Han character and none of the banned engineer-word literals.
 * `KELLY_WIN_RATE_OUT_OF_RANGE_MESSAGE` / `KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE`
 * both pass this test unchanged (they are ordinary Chinese sentences with no
 * banned literal in them); pydantic's English message fails it (no Han
 * character at all). Testing the shape rather than an exact retyped string
 * avoids creating a second, driftable copy of approved wording in this
 * repository (落地條件 2's "全 repo 無第二份同語意字串" rule, generalised past
 * its literal backend scope) — a future re-wording of either backend sentence
 * needs no matching edit here.
 *
 * A message that fails this test is treated as "no field-level message
 * available", which lets the caller fall back to the generic top-level
 * rejection text `ApiError.message` already carries (`app/lib/api.ts`'s own
 * `請求失敗（HTTP {status}）` fallback for a `detail` that is not a plain
 * string) — pre-existing, already-shipped copy, not a new sentence invented
 * for this branch.
 */

//: 條件 57's own list, verbatim: a rendered field message may never contain
//: any of these regardless of what else it says.
const BANNED_LITERALS: readonly string[] = [
  "nan",
  "NaN",
  "-inf",
  "inf",
  "Infinity",
  "None",
  "null",
];

//: Any Han character, the same block `app/lib/adviceWording.ts`'s own scans
//: use to detect Chinese-language content.
const HAN_CHARACTER = /[一-鿿]/;

/**
 * Whether `message` is safe to render as a Kelly field-level error: contains
 * genuine Chinese content and none of 條件 57's banned literals. `undefined`
 * (no field error at all) is never "safe to render" — there is nothing to
 * render either way, and callers already branch on that case separately.
 */
export function isApprovedKellyFieldMessage(message: string | undefined): message is string {
  if (message === undefined) return false;
  if (!HAN_CHARACTER.test(message)) return false;
  return !BANNED_LITERALS.some((literal) => message.includes(literal));
}
