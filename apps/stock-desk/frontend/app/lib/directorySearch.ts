/**
 * Pure decision/helper functions behind the NavBar combobox (FR-4/FR-5/FR-7,
 * `work/stock-desk-代號目錄-PRD.md`). Deliberately framework-free (no React,
 * no fetch) so the debounce/keyboard/fallback logic the dispatch order asks
 * to be unit-tested can be tested directly, the same way `tradingCalendar.ts`
 * keeps its date arithmetic separate from any component.
 */

import type { DirectoryItem, DirectorySearchResponse, Market } from "./types";

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
 */
export const DIRECTORY_NOT_SYNCED_NOTICE =
  "證券目錄尚未同步，僅支援代號直達；同步指令請見設定頁。";
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
