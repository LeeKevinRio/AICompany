/**
 * Pure decision/helper functions behind the NavBar combobox (FR-4/FR-5/FR-7,
 * `work/stock-desk-代號目錄-PRD.md`). Deliberately framework-free (no React,
 * no fetch) so the debounce/keyboard/fallback logic the dispatch order asks
 * to be unit-tested can be tested directly, the same way `tradingCalendar.ts`
 * keeps its date arithmetic separate from any component.
 */

import type { DirectoryItem, DirectorySearchResponse, Market } from "./types";

// FR-C7(a): a symbol is whatever the backend's `Market` literal accepts as a
// path segment — no known closed vocabulary to validate against on the
// front end (TW tickers are numeric, US tickers are alphabetic, both can
// carry a "." for share-class suffixes). This only rejects what can never be
// a valid symbol: empty input, whitespace, characters that would need
// URL-encoding games to survive the round trip, and input made up entirely
// of "." with no actual ticker characters (qa-reviewer Minor follow-up).
export const SYMBOL_PATTERN = /^(?=.*[A-Za-z0-9])[A-Za-z0-9.]+$/;

/**
 * FR-3/FR-4 leave the debounce interval to frontend-engineer ("防抖由前端
 * 控制，不寫死秒數在本 PRD"). 300ms is the dispatch order's stated target —
 * long enough to collapse a fast typing burst into one request, short enough
 * that the candidate list still feels live.
 */
export const DIRECTORY_SEARCH_DEBOUNCE_MS = 300;

/**
 * Minimal trailing-edge debouncer: each `schedule()` call cancels any
 * pending previous call and re-arms the timer, so only the *last* call
 * within a `delayMs` window actually fires. `cancel()` lets a caller (e.g.
 * component unmount, or the input being cleared) drop a pending call
 * without firing it.
 */
export function createDebouncer(delayMs: number) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  return {
    schedule(fn: () => void): void {
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(fn, delayMs);
    },
    cancel(): void {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    },
  };
}

/**
 * Arrow-key navigation over the candidate list (AC-8), wrapping at both
 * ends so repeated ArrowDown/ArrowUp cycles instead of getting stuck.
 * `-1` means "nothing highlighted"; an empty list always stays at `-1`.
 */
export function nextHighlightedIndex(
  key: "ArrowDown" | "ArrowUp",
  current: number,
  length: number,
): number {
  if (length === 0) return -1;
  if (key === "ArrowDown") return current >= length - 1 ? 0 : current + 1;
  return current <= 0 ? length - 1 : current - 1;
}

/**
 * FR-7 honest degrade notices for the dropdown area. Exported as constants
 * (not just returned by `directorySearchNotice`) so the wording scan and the
 * unit tests both check the exact same string, with one place to update it.
 *
 * `DIRECTORY_NOT_SYNCED_NOTICE` 風控核可句（2026-08-09，證券目錄批快審）：原句
 * 「…；同步指令請見設定頁。」指向不存在的內容，遭否決；核可截短句逐字如下，
 * 日後修改不得續接任何承諾未來動作的字句（設定頁若補上同步說明區塊，需另案送
 * 風控核可才可擴回）。
 */
export const DIRECTORY_NOT_SYNCED_NOTICE = "證券目錄尚未同步，僅支援代號直達。";
export const DIRECTORY_TRUNCATED_NOTICE = "候選過多，請輸入更精確關鍵字。";

/**
 * Which (if any) FR-7 status line the dropdown should show below the
 * candidate rows. `directory_synced: false` always wins over `truncated`
 * (an unsynced directory's `items` is always empty per the backend contract,
 * so `truncated` cannot be true at the same time in practice — the order
 * here just documents the intended precedence rather than relying on that).
 */
export function directorySearchNotice(
  response: Pick<DirectorySearchResponse, "directory_synced" | "truncated"> | undefined,
): string | null {
  if (!response) return null;
  if (!response.directory_synced) return DIRECTORY_NOT_SYNCED_NOTICE;
  if (response.truncated) return DIRECTORY_TRUNCATED_NOTICE;
  return null;
}

/**
 * Whether the dropdown should render candidate rows at all (FR-7: never
 * fake a candidate list against an unsynced/empty directory).
 */
export function shouldShowCandidates(
  response: Pick<DirectorySearchResponse, "directory_synced" | "items"> | undefined,
): boolean {
  return response !== undefined && response.directory_synced && response.items.length > 0;
}

/**
 * FR-2 / Q1(b) CEO 裁示: after a plain-symbol Enter resolves against the
 * directory, either navigate straight to the (now market-known) position
 * page, or — on a miss — surface the small TW/US market picker instead of
 * guessing (AC-4, AC-16).
 */
export type ResolveOutcome =
  | { type: "navigate"; symbol: string; market: Market }
  | { type: "needMarketPicker"; symbol: string };

export function decideAfterResolve(symbol: string, resolved: DirectoryItem | null): ResolveOutcome {
  if (resolved !== null) {
    return { type: "navigate", symbol, market: resolved.market };
  }
  return { type: "needMarketPicker", symbol };
}

/** Prompt shown above the two-button TW/US picker (Q1(b)'s "縮小版市場選擇"). */
export const MARKET_PICKER_PROMPT = "查無此代號對應的市場，請手動選擇。";

/** What NavBar's `handleSubmit` should do with a given submit attempt, as data rather than side effects. */
export type SubmitDecision =
  | { kind: "selectCandidate"; item: DirectoryItem }
  | { kind: "invalidInput"; message: string }
  | { kind: "resolved"; outcome: ResolveOutcome }
  | { kind: "resolveFailed" };

export interface DecideSubmitParams {
  /** Only `cancel()` is needed here — kept minimal so a test double doesn't need the rest of `createDebouncer`'s shape. */
  debouncer: Pick<ReturnType<typeof createDebouncer>, "cancel">;
  open: boolean;
  highlighted: DirectoryItem | undefined;
  inputValue: string;
  resolveSymbol: (symbol: string) => Promise<DirectoryItem | null>;
}

/**
 * Pure(-ish — the only side effects are the two injected callbacks, both of
 * which are unavoidably impure at the real call site: `debouncer.cancel()`
 * and `resolveSymbol`) orchestration behind NavBar's `handleSubmit`,
 * extracted for the BLOCKING fix (qa 2026-08-09, 證券目錄批): NavBar is part
 * of the shared layout and never unmounts on a client-side route change, so
 * a debounce timer left over from earlier typing can outlive a submit and
 * later reopen the dropdown with a stale query. `debouncer.cancel()` is
 * called unconditionally as the very first statement — before any branch —
 * so every exit path below (including the `resolveFailed` catch) is
 * guaranteed to have cancelled the pending schedule, and a test can assert
 * that without rendering the component (this repo has no RTL/jsdom; see
 * `alertRuleForm.ts`'s `decideAlertRuleSubmit` for the same extraction
 * pattern applied to a different BLOCKING fix).
 */
export async function decideSubmit(params: DecideSubmitParams): Promise<SubmitDecision> {
  params.debouncer.cancel();
  if (params.open && params.highlighted) {
    return { kind: "selectCandidate", item: params.highlighted };
  }
  const trimmed = params.inputValue.trim();
  if (trimmed.length === 0) {
    return { kind: "invalidInput", message: "請輸入股票代號" };
  }
  if (!SYMBOL_PATTERN.test(trimmed)) {
    return { kind: "invalidInput", message: "代號格式不正確，僅接受英數字與小數點" };
  }
  try {
    const resolved = await params.resolveSymbol(trimmed);
    return { kind: "resolved", outcome: decideAfterResolve(trimmed, resolved) };
  } catch {
    return { kind: "resolveFailed" };
  }
}
