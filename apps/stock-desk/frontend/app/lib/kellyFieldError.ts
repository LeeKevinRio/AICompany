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
 *
 * **B2 (qa 補審 2026-08-22, `work/reviews/2026-08-22-C5-K4c2-qa補審.md`)**:
 * qa reproduced a *mixed* 422 body this shape test did not catch —
 * pydantic v2 prefixes a `field_validator`'s own `ValueError` message with
 * its own English `"Value error, "` before it reaches this app, so the range
 * check's own approved Chinese sentence can arrive with that English prefix
 * still attached: Han characters present, no banned literal present, and yet
 * unreviewed English copy is now sitting in front of an otherwise-approved
 * sentence. `LATIN_LETTER_RUN` closes that gap: neither approved sentence
 * contains any run of two or more Latin letters at all (both are pure
 * Chinese text plus digits/punctuation), so rejecting any message that does
 * costs nothing on the approved path and catches this prefix (and any other
 * Latin-letter contamination) without needing to know pydantic's exact
 * wording. **This is the frontend half
 * only** — the backend fix (strip the prefix at the source, e.g. a
 * `PydanticCustomError`/422-handler change) is dev-lead's; this hardening
 * stands regardless of whether or when that lands.
 */

//: 條件 57's own list, verbatim: a rendered field message may never contain
//: any of these regardless of what else it says. Every entry here is also a
//: run of 2+ Latin letters, so `LATIN_LETTER_RUN` below already rejects all
//: of them — this list is kept anyway (not dead-code-removed) because 條件
//: 57 names these specific literals explicitly, and a future narrowing of
//: `LATIN_LETTER_RUN` (e.g. to allow some Latin content) must not silently
//: let one of these back in without a second, independent check noticing.
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

//: B2: two or more consecutive Latin letters — present in pydantic's own
//: `"Value error, "` prefix and absent from both approved range sentences.
const LATIN_LETTER_RUN = /[A-Za-z]{2,}/;

/**
 * Whether `message` is safe to render as a Kelly field-level error: contains
 * genuine Chinese content, none of 條件 57's banned literals, and no run of
 * Latin letters (B2 — catches an unreviewed English prefix pydantic can
 * prepend to an otherwise-approved Chinese sentence). `undefined` (no field
 * error at all) is never "safe to render" — there is nothing to render
 * either way, and callers already branch on that case separately.
 */
export function isApprovedKellyFieldMessage(message: string | undefined): message is string {
  if (message === undefined) return false;
  if (!HAN_CHARACTER.test(message)) return false;
  if (LATIN_LETTER_RUN.test(message)) return false;
  return !BANNED_LITERALS.some((literal) => message.includes(literal));
}
