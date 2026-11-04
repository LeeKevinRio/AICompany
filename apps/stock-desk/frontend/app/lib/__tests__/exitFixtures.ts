/**
 * Shared fixtures for the exit-feedback tests. Not a test file (vitest only
 * collects `*.test.ts`).
 */

import type { ExitTodayView } from "../exitDialogState";
import type { PlaybookEmergencyExitResponse, PlaybookExitConfirm } from "../types";

/** The backend `EXIT_CONFIRM_CHECKS` with day count / date filled, as `/today` sends it. */
export function formalChecks(freezeDays: number, freezeUntil: string): string[] {
  return [
    "此操作將對目前持有的全部標的、全部批次送出出清指令；" +
      "不可只出清部分標的或部分批次，亦不可指定單一標的" +
      "（如需針對單一標的停損，請改用該標的的 S 系列規則）。",
    `送出後，R 系列（新倉進場）暫停 ${freezeDays} 個交易日` +
      `（預計恢復日：${freezeUntil}，依交易日曆計算）。`,
    "凍結期間內，S／P 系列（停損／停利）仍照常評估；凍結期間仍可再次送出全部出清。",
    "本操作產生的是賣出指令，不是成交：T+1 開盤以市價單送出，跌停或無量時可能無法成交。",
  ];
}

export function exitConfirmBlock(freezeDays = 20, freezeUntil = "2026-09-09"): PlaybookExitConfirm {
  return { freeze_days: freezeDays, freeze_until: freezeUntil, checks: formalChecks(freezeDays, freezeUntil) };
}

/** 2026-08-11 12:00 Asia/Taipei. */
export const NOON_AUG_11 = Date.UTC(2026, 7, 11, 4, 0, 0);
/** 2026-08-11 23:59:59.999 Asia/Taipei — the last millisecond of the day. */
export const LAST_MS_AUG_11 = Date.UTC(2026, 7, 11, 15, 59, 59, 999);
/** 2026-08-12 00:00:00.000 Asia/Taipei — the first millisecond of the next day. */
export const FIRST_MS_AUG_12 = Date.UTC(2026, 7, 11, 16, 0, 0, 0);
/** 2026-08-12 09:00 Asia/Taipei. */
export const MORNING_AUG_12 = Date.UTC(2026, 7, 12, 1, 0, 0);

export function successToday(
  overrides: Partial<ExitTodayView> & { exitConfirm?: PlaybookExitConfirm | null } = {},
): ExitTodayView {
  return {
    status: "success",
    dataUpdatedAt: NOON_AUG_11,
    exitConfirm: exitConfirmBlock(),
    ...overrides,
  };
}

/** `/today` not successful: the view carries no `exit_confirm` by construction (F-1). */
export function failedToday(status: "pending" | "error" = "error", dataUpdatedAt = NOON_AUG_11): ExitTodayView {
  return { status, dataUpdatedAt, exitConfirm: null };
}

export function receiptResponse(
  overrides: Partial<PlaybookEmergencyExitResponse> = {},
): PlaybookEmergencyExitResponse {
  return {
    executed_at: "2026-08-11",
    execution_date: "2026-08-12",
    total_shares: 500,
    freeze_until: "2026-09-08",
    message: "EMERGENCY_EXIT 已受理：message",
    mode_reason: "mode reason sentence",
    attribution: "attribution sentence",
    directives: [],
    pending_directives: [],
    warnings: [],
    as_of: "2026-08-11",
    ...overrides,
  };
}
