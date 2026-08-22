/**
 * `parseKellyImportRefusal` reads `KellyImportRefusal` (`app/api/kelly.py`)
 * back out of `ApiError.body` — the 422 for `POST .../import-backtest` puts
 * a plain object in `detail`, unlike every other endpoint's FastAPI
 * validation-error array, so `ApiError.fieldErrors`/`message` cannot reach
 * it (see `ApiError`'s own doc comment in `app/lib/api.ts`).
 */

import { describe, expect, it } from "vitest";
import { parseKellyImportRefusal } from "../api";

// Fixture text is deliberately synthetic ASCII, not a retyped approved Kelly
// sentence: `parseKellyImportRefusal` performs no Chinese-content validation
// (unlike `isApprovedKellyFieldMessage`), so a real sentence buys this test
// nothing — and `tests/test_kelly_wording.py`'s own
// `test_no_approved_kelly_sentence_has_been_copied_into_the_front_end` scans
// every frontend source file, tests included, for the opening of each of the
// 72 risk-compliance-approved sentences; a fixture that happened to retype
// one verbatim would trip that guard for no reason connected to what this
// suite actually tests (field mapping, not wording).
const VALID_REFUSAL_BODY = {
  detail: {
    reason_code: "low_round_trips",
    message: "TEST_MESSAGE",
    frame: "TEST_FRAME",
    attempt_logged: "TEST_ATTEMPT_LOGGED",
    selection_bias: "TEST_SELECTION_BIAS",
    k_observed: 3,
    k_distinct_specs: 2,
  },
};

describe("parseKellyImportRefusal", () => {
  it("reads every field off a well-formed refusal body", () => {
    expect(parseKellyImportRefusal(VALID_REFUSAL_BODY)).toEqual({
      reason_code: "low_round_trips",
      message: VALID_REFUSAL_BODY.detail.message,
      frame: VALID_REFUSAL_BODY.detail.frame,
      attempt_logged: VALID_REFUSAL_BODY.detail.attempt_logged,
      selection_bias: VALID_REFUSAL_BODY.detail.selection_bias,
      k_observed: 3,
      k_distinct_specs: 2,
    });
  });

  it("落地條件 13: frame is null for a non-sample-size reason code (e.g. symbol_mismatch) — still a valid refusal", () => {
    const body = {
      detail: {
        ...VALID_REFUSAL_BODY.detail,
        reason_code: "symbol_mismatch",
        frame: null,
      },
    };
    expect(parseKellyImportRefusal(body)?.frame).toBeNull();
    expect(parseKellyImportRefusal(body)?.reason_code).toBe("symbol_mismatch");
  });

  it("落地條件 5: selection_bias is null for K == 0 (unreachable through the gate today, still a valid shape)", () => {
    const body = { detail: { ...VALID_REFUSAL_BODY.detail, selection_bias: null } };
    expect(parseKellyImportRefusal(body)?.selection_bias).toBeNull();
  });

  it("returns null for a FastAPI validation-error array body (a different endpoint's 422 shape)", () => {
    expect(
      parseKellyImportRefusal({ detail: [{ loc: ["body", "win_rate"], msg: "x" }] }),
    ).toBeNull();
  });

  it("returns null for a plain-string detail (e.g. KELLY_NON_FINITE_INTERVAL_MESSAGE's 500 body)", () => {
    expect(parseKellyImportRefusal({ detail: "TEST_PLAIN_STRING_DETAIL" })).toBeNull();
  });

  it("returns null for an unrecognised reason_code (defends against a future backend enum drift)", () => {
    expect(
      parseKellyImportRefusal({ detail: { ...VALID_REFUSAL_BODY.detail, reason_code: "new_code" } }),
    ).toBeNull();
  });

  it("returns null for null, undefined, and a non-object body", () => {
    expect(parseKellyImportRefusal(null)).toBeNull();
    expect(parseKellyImportRefusal(undefined)).toBeNull();
    expect(parseKellyImportRefusal("oops")).toBeNull();
  });

  it("defaults k_observed/k_distinct_specs to 0 rather than throwing when they are missing", () => {
    const { k_observed: _ko, k_distinct_specs: _kds, ...rest } = VALID_REFUSAL_BODY.detail;
    const body = { detail: rest };
    const parsed = parseKellyImportRefusal(body);
    expect(parsed?.k_observed).toBe(0);
    expect(parsed?.k_distinct_specs).toBe(0);
  });
});
