/**
 * qa-reviewer Medium follow-up on the FR-9 review: the one-time confirmation
 * before widening `max_gross_exposure` could be walked around. Once the panel
 * was up, *any* second submit went through — including one that carried a
 * value the user had edited after reading the sentence, so the number written
 * could differ from the number confirmed.
 *
 * These tests pin the rule that fixes it: a submit only proceeds when the
 * raise it would write is the same pair of numbers the panel is showing.
 * Everything else re-opens the confirmation with the new number.
 */

import { describe, expect, it } from "vitest";
import { capWidening, isSameWidening, resolveWideningSubmit } from "../riskWidening";

describe("capWidening — only a genuine raise counts", () => {
  it("reports the pair when the cap goes up", () => {
    expect(capWidening(1.0, 1.2)).toEqual({ before: 1.0, after: 1.2 });
  });

  it("is null when the cap is unchanged or lowered", () => {
    expect(capWidening(1.0, 1.0)).toBeNull();
    expect(capWidening(1.2, 0.8)).toBeNull();
  });

  it("is null for an unparseable entry, leaving the 422 to the backend", () => {
    // Demanding confirmation of a value that cannot be written would put a
    // risk warning in front of a plain typo.
    expect(capWidening(1.0, Number("abc"))).toBeNull();
    expect(capWidening(1.0, Number(""))).toBeNull();
  });
});

describe("resolveWideningSubmit — the confirmed number is the written number", () => {
  it("submits straight away when nothing is being widened", () => {
    expect(resolveWideningSubmit(null, null)).toEqual({ action: "submit", widening: null });
  });

  it("holds the first submit that raises the cap", () => {
    const widening = { before: 1.0, after: 1.2 };
    expect(resolveWideningSubmit(widening, null)).toEqual({ action: "confirm", widening });
  });

  it("lets the second submit through once the same raise is on screen", () => {
    const widening = { before: 1.0, after: 1.2 };
    expect(resolveWideningSubmit(widening, { ...widening })).toEqual({
      action: "submit",
      widening: null,
    });
  });

  it("re-confirms when the value changed after the panel appeared", () => {
    // The defect this suite exists for: confirm 1.20, edit to 1.50, save.
    const shown = { before: 1.0, after: 1.2 };
    const edited = { before: 1.0, after: 1.5 };
    expect(resolveWideningSubmit(edited, shown)).toEqual({
      action: "confirm",
      widening: edited,
    });
  });

  it("re-confirms even when the edit is downward but still a raise", () => {
    const shown = { before: 1.0, after: 1.5 };
    const edited = { before: 1.0, after: 1.1 };
    expect(resolveWideningSubmit(edited, shown)).toEqual({
      action: "confirm",
      widening: edited,
    });
  });

  it("submits when the user backs the value down out of raise territory", () => {
    // Nothing is being widened any more, so there is nothing to confirm.
    expect(resolveWideningSubmit(null, { before: 1.0, after: 1.2 })).toEqual({
      action: "submit",
      widening: null,
    });
  });
});

describe("isSameWidening", () => {
  it("treats equal pairs as the same raise", () => {
    expect(isSameWidening({ before: 1, after: 1.2 }, { before: 1, after: 1.2 })).toBe(true);
  });

  it("distinguishes a different target or a different starting point", () => {
    expect(isSameWidening({ before: 1, after: 1.2 }, { before: 1, after: 1.3 })).toBe(false);
    expect(isSameWidening({ before: 1, after: 1.2 }, { before: 1.1, after: 1.2 })).toBe(false);
  });

  it("only matches null with null", () => {
    expect(isSameWidening(null, null)).toBe(true);
    expect(isSameWidening({ before: 1, after: 1.2 }, null)).toBe(false);
  });
});
