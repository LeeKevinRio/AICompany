/**
 * #61 (CEO 2026-10-26, plan A): cap 1's default `max_position_weight` is 0.10,
 * the value `DEFAULT_MAX_POSITION_WEIGHT` in `app/advice/limits.py` carries
 * (quant constraint 2). The settings page prints the default under the field
 * ("預設值：…"), so a stale front-end copy would tell the user the old 0.15.
 *
 * The backend half (`tests/test_cap1_default.py`) reads this form's source and
 * asserts the two are equal; this half pins the front-end value on its own.
 */

import { describe, expect, it } from "vitest";
import { RISK_BUDGET_FIELDS } from "../../settings/SettingsForm";

describe("SettingsForm — cap 1 default (#61)", () => {
  it("shows 0.1 as the default of max_position_weight", () => {
    const field = RISK_BUDGET_FIELDS.find((spec) => spec.key === "max_position_weight");
    expect(field?.defaultValue).toBe(0.1);
  });

  it("leaves the 0.50 hard ceiling untouched", () => {
    const field = RISK_BUDGET_FIELDS.find((spec) => spec.key === "max_position_weight");
    expect(field?.hardCeiling?.max).toBe(0.5);
  });

  it("keeps kelly_position_cap's own 0.1 default (the bound 10% was derived from)", () => {
    const field = RISK_BUDGET_FIELDS.find((spec) => spec.key === "kelly_position_cap");
    expect(field?.defaultValue).toBe(0.1);
  });
});
