/** Fixtures for the `/playbook` page-level tests (not a test file). */

import type { PlaybookEmergencyExitResponse, PlaybookTodayResponse } from "../../lib/types";

export const MODE_REASON = "SENTINEL-MODE-REASON";
export const MODE_LABEL = "SENTINEL-MODE-LABEL";

export function todayResponse(overrides: Partial<PlaybookTodayResponse> = {}): PlaybookTodayResponse {
  return {
    data_date: "2026-10-27",
    execution_date: "2026-10-28",
    mode: "emergency_frozen",
    mode_label: MODE_LABEL,
    mode_reason: MODE_REASON,
    is_schedule_day: true,
    fast_market: {
      active: false,
      annualized_vol_20d: null,
      large_move_days: 0,
      reason: null,
      carried_forward: false,
      measured_on: null,
      carried_note: null,
    },
    rules_version: 1,
    rules_effective_date: null,
    page_summary: ["SENTINEL-SUMMARY-ONE", "SENTINEL-SUMMARY-TWO", "SENTINEL-SUMMARY-THREE"],
    directives: [],
    snapshot: [],
    warnings: ["SENTINEL-WARNING"],
    rules_fully_evaluated: true,
    no_directive_note: null,
    attribution: "SENTINEL-ATTRIBUTION",
    settlement: null,
    exit_confirm: null,
    as_of: "2026-10-28T00:00:00+00:00",
    ...overrides,
  };
}

export function receiptResponse(
  overrides: Partial<PlaybookEmergencyExitResponse> = {},
): PlaybookEmergencyExitResponse {
  return {
    executed_at: "2026-10-27",
    execution_date: "2026-10-28",
    total_shares: 500,
    freeze_until: "2026-11-24",
    message: "SENTINEL-RECEIPT-MESSAGE",
    mode_reason: MODE_REASON,
    attribution: "SENTINEL-RECEIPT-ATTRIBUTION",
    directives: [],
    pending_directives: [],
    warnings: ["SENTINEL-RECEIPT-WARNING"],
    as_of: "2026-10-27",
    ...overrides,
  };
}
