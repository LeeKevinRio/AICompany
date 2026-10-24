/**
 * `formErrors.ts`: a cleared numeric field must never be sent as `Number("")`'s
 * 0, and a 422 on a key no field renders must still reach the generic error.
 */

import { describe, expect, it } from "vitest";
import { REQUIRED_NUMBER_MESSAGE, parseRequiredNumbers, unplacedFieldErrors } from "../formErrors";

describe("parseRequiredNumbers", () => {
  it("parses every filled field, zero included", () => {
    const parsed = parseRequiredNumbers({ fee: "0.001425", cooldown: "0", cash: " 1000000 " });
    expect(parsed.errors).toEqual({});
    expect(parsed.values).toEqual({ fee: 0.001425, cooldown: 0, cash: 1_000_000 });
  });

  it("refuses a blank field instead of reading it as 0", () => {
    const parsed = parseRequiredNumbers({ fee: "", cooldown: "   ", cash: "1000" });
    expect(parsed.errors).toEqual({ fee: REQUIRED_NUMBER_MESSAGE, cooldown: REQUIRED_NUMBER_MESSAGE });
  });

  it("refuses thousands separators and non-finite values", () => {
    const parsed = parseRequiredNumbers({ cash: "1,000,000", slippage: "Infinity", other: "abc" });
    expect(Object.keys(parsed.errors).sort()).toEqual(["cash", "other", "slippage"]);
  });
});

describe("unplacedFieldErrors", () => {
  it("returns the messages no field renders, such as a model-level `body` error", () => {
    const errors = { body: "Value error, end must be after start", symbol: "too short" };
    // Pydantic's "Value error, " prefix is dropped; the validator's own text stays.
    expect(unplacedFieldErrors(errors, ["symbol", "start", "end"])).toEqual(["end must be after start"]);
  });

  it("is empty when every error has a slot", () => {
    expect(unplacedFieldErrors({ symbol: "x" }, ["symbol"])).toEqual([]);
  });
});
