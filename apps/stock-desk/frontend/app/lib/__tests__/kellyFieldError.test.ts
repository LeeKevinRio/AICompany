/**
 * 條件 57 (`work/reviews/2026-08-19-C5-Kelly-文案批審.md`, 協調人三確認 2):
 * `isApprovedKellyFieldMessage` is the gate `KellyManualInputForm.tsx` uses to
 * decide whether a `win_rate`/`payoff_ratio` field error is safe to render.
 *
 * Fixture text below is deliberately synthetic Chinese ("測試訊息…"), not a
 * retyped copy of `KELLY_WIN_RATE_OUT_OF_RANGE_MESSAGE` /
 * `KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE` (`app/kelly/models.py`):
 * `isApprovedKellyFieldMessage` is a **shape test** (Han character present,
 * no banned literal) by design — see its own doc comment for why it does not
 * compare against either sentence's exact text — so a real backend sentence
 * would only couple this test to wording it does not need to know, and
 * `tests/test_kelly_wording.py`'s own
 * `test_no_approved_kelly_sentence_has_been_copied_into_the_front_end` scans
 * every frontend source file (tests included) for the opening of every
 * risk-compliance-approved sentence — a fixture that happened to retype one
 * verbatim (`KELLY_PAYOFF_RATIO_LABEL` is itself one of the 72 tracked
 * strings, confirmed by running that suite while drafting this file) would
 * trip that guard for no reason connected to what this suite tests.
 */

import { describe, expect, it } from "vitest";
import { isApprovedKellyFieldMessage } from "../kellyFieldError";

describe("isApprovedKellyFieldMessage", () => {
  it("accepts an ordinary Chinese sentence with an echoed numeric value", () => {
    expect(isApprovedKellyFieldMessage("測試訊息：欄位數值不合法（收到 1.5）。")).toBe(true);
  });

  it("accepts an ordinary Chinese sentence with a negative echoed value", () => {
    expect(isApprovedKellyFieldMessage("測試訊息：欄位數值必須為正（收到 -2）。")).toBe(true);
  });

  it("rejects pydantic's own English finite-number message (the 條件 57 branch)", () => {
    expect(isApprovedKellyFieldMessage("Input should be a finite number")).toBe(false);
  });

  it("rejects a message with no field error at all", () => {
    expect(isApprovedKellyFieldMessage(undefined)).toBe(false);
  });

  it("rejects any message carrying a banned engineer-word literal, even alongside Chinese", () => {
    for (const literal of ["nan", "NaN", "-inf", "inf", "Infinity", "None", "null"]) {
      expect(isApprovedKellyFieldMessage(`測試訊息：數值不合法（收到 ${literal}）。`)).toBe(false);
    }
  });

  it("rejects a bare English word that happens to contain a banned literal's letters without being one (control: still fails on the no-Han-character branch)", () => {
    // "information" contains no banned literal, but it also has no Han
    // character, so it fails for that reason instead — pinning that the two
    // gates are independent (not "banned-literal free" alone).
    expect(isApprovedKellyFieldMessage("information")).toBe(false);
  });

  // B2 (qa 補審 2026-08-22): pydantic v2 prefixes a `field_validator`'s own
  // `ValueError` with its own English `"Value error, "` before the body
  // reaches this app — a mixed sentence with Han characters, no banned
  // literal, and unreviewed English attached to the front of it. Fixture is
  // synthetic Chinese (see this file's own doc comment on why), with the
  // real pydantic prefix prepended verbatim — that prefix is not
  // Kelly-approved copy and has no CONFIRMED_VERBATIM entry to collide with.
  it("B2: rejects a message carrying pydantic's 'Value error, ' prefix even though Han characters and no banned literal are both present", () => {
    expect(
      isApprovedKellyFieldMessage("Value error, 測試訊息：欄位數值不合法（收到 1.5）。"),
    ).toBe(false);
  });

  it("B2: rejects any run of two or more Latin letters embedded in an otherwise-clean Chinese sentence", () => {
    expect(isApprovedKellyFieldMessage("測試訊息 ab：欄位數值不合法。")).toBe(false);
  });

  it("B2 control: a single Latin letter (e.g. scientific-notation 'e') does not trip the run-of-2+ gate", () => {
    expect(isApprovedKellyFieldMessage("測試訊息：欄位數值不合法（收到 1e+20）。")).toBe(true);
  });
});
