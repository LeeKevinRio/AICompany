import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DIRECTORY_NOT_SYNCED_NOTICE,
  DIRECTORY_TRUNCATED_NOTICE,
  createDebouncer,
  decideAfterResolve,
  decideSubmit,
  directorySearchNotice,
  nextHighlightedIndex,
  shouldShowCandidates,
} from "../directorySearch";
import type { DirectoryItem, DirectorySearchResponse } from "../types";

const ITEM: DirectoryItem = {
  symbol: "2330",
  name: "台灣積體電路製造股份有限公司",
  market: "TW",
  source: "twse",
  as_of: "2026-08-09T00:00:00Z",
};

function response(overrides: Partial<DirectorySearchResponse> = {}): DirectorySearchResponse {
  return {
    query: "2330",
    items: [ITEM],
    truncated: false,
    directory_synced: true,
    limit: 12,
    as_of: "2026-08-09T00:00:00Z",
    ...overrides,
  };
}

describe("createDebouncer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("fires once, after delayMs, for a single schedule() call", () => {
    const fn = vi.fn();
    const debouncer = createDebouncer(300);
    debouncer.schedule(fn);
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(299);
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("collapses a fast typing burst into a single trailing call", () => {
    const fn = vi.fn();
    const debouncer = createDebouncer(300);
    debouncer.schedule(() => fn("2"));
    vi.advanceTimersByTime(100);
    debouncer.schedule(() => fn("23"));
    vi.advanceTimersByTime(100);
    debouncer.schedule(() => fn("233"));
    vi.advanceTimersByTime(100);
    debouncer.schedule(() => fn("2330"));
    vi.advanceTimersByTime(300);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("2330");
  });

  it("cancel() drops a pending call without firing it", () => {
    const fn = vi.fn();
    const debouncer = createDebouncer(300);
    debouncer.schedule(fn);
    debouncer.cancel();
    vi.advanceTimersByTime(1000);
    expect(fn).not.toHaveBeenCalled();
  });

  it("a later schedule() after cancel() still fires normally", () => {
    const fn = vi.fn();
    const debouncer = createDebouncer(300);
    debouncer.schedule(fn);
    debouncer.cancel();
    debouncer.schedule(fn);
    vi.advanceTimersByTime(300);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});

describe("nextHighlightedIndex", () => {
  it("returns -1 for an empty candidate list regardless of key or current", () => {
    expect(nextHighlightedIndex("ArrowDown", -1, 0)).toBe(-1);
    expect(nextHighlightedIndex("ArrowUp", 2, 0)).toBe(-1);
  });

  it("ArrowDown moves from -1 (nothing highlighted) to the first item", () => {
    expect(nextHighlightedIndex("ArrowDown", -1, 3)).toBe(0);
  });

  it("ArrowDown advances and wraps from the last item back to the first", () => {
    expect(nextHighlightedIndex("ArrowDown", 0, 3)).toBe(1);
    expect(nextHighlightedIndex("ArrowDown", 2, 3)).toBe(0);
  });

  it("ArrowUp moves from -1 to the last item", () => {
    expect(nextHighlightedIndex("ArrowUp", -1, 3)).toBe(2);
  });

  it("ArrowUp retreats and wraps from the first item back to the last", () => {
    expect(nextHighlightedIndex("ArrowUp", 1, 3)).toBe(0);
    expect(nextHighlightedIndex("ArrowUp", 0, 3)).toBe(2);
  });
});

describe("DIRECTORY_NOT_SYNCED_NOTICE wording (風控核可句 2026-08-09)", () => {
  it("matches the risk-compliance-approved sentence verbatim, no trailing promise clause", () => {
    // Pinned literal (not just comparing the constant to itself) so a silent
    // drift back toward the vetoed "…；同步指令請見設定頁。" tail — or any new
    // "請稍候"/"即將支援" style promise — fails this test even if the constant
    // definition itself is edited.
    expect(DIRECTORY_NOT_SYNCED_NOTICE).toBe("證券目錄尚未同步，僅支援代號直達。");
  });
});

describe("shouldShowCandidates / directorySearchNotice (FR-7 honest degrade)", () => {
  it("shows candidates when the directory is synced and items is non-empty", () => {
    expect(shouldShowCandidates(response())).toBe(true);
    expect(directorySearchNotice(response())).toBeNull();
  });

  it("never shows candidates when directory_synced is false, even if items were non-empty", () => {
    const r = response({ directory_synced: false, items: [ITEM] });
    expect(shouldShowCandidates(r)).toBe(false);
    expect(directorySearchNotice(r)).toBe(DIRECTORY_NOT_SYNCED_NOTICE);
  });

  it("shows the not-synced notice over the truncated notice when both flags are set", () => {
    const r = response({ directory_synced: false, truncated: true, items: [] });
    expect(directorySearchNotice(r)).toBe(DIRECTORY_NOT_SYNCED_NOTICE);
  });

  it("shows the truncated notice when synced but truncated (AC-7)", () => {
    const r = response({ truncated: true });
    expect(directorySearchNotice(r)).toBe(DIRECTORY_TRUNCATED_NOTICE);
  });

  it("shows no candidates and no notice for a synced-but-empty result (no match, not an outage)", () => {
    const r = response({ items: [] });
    expect(shouldShowCandidates(r)).toBe(false);
    expect(directorySearchNotice(r)).toBeNull();
  });

  it("shows nothing before any response has arrived (undefined)", () => {
    expect(shouldShowCandidates(undefined)).toBe(false);
    expect(directorySearchNotice(undefined)).toBeNull();
  });
});

describe("decideAfterResolve (FR-2 / Q1(b) 404 fallback)", () => {
  it("navigates straight to the position page on a directory hit, using its market", () => {
    expect(decideAfterResolve("2330", ITEM)).toEqual({
      type: "navigate",
      symbol: "2330",
      market: "TW",
    });
  });

  it("asks for the small TW/US market picker on a miss instead of guessing", () => {
    expect(decideAfterResolve("9999X", null)).toEqual({
      type: "needMarketPicker",
      symbol: "9999X",
    });
  });
});

describe("decideSubmit (BLOCKING fix, qa 2026-08-09: debounce cancelled on every submit path)", () => {
  function stubDebouncer() {
    return { cancel: vi.fn() };
  }

  it("cancels the debouncer when a highlighted candidate is submitted", async () => {
    const debouncer = stubDebouncer();
    const resolveSymbol = vi.fn();
    const decision = await decideSubmit({
      debouncer,
      open: true,
      highlighted: ITEM,
      inputValue: "irrelevant while a candidate is highlighted",
      resolveSymbol,
    });
    expect(debouncer.cancel).toHaveBeenCalledTimes(1);
    expect(decision).toEqual({ kind: "selectCandidate", item: ITEM });
    expect(resolveSymbol).not.toHaveBeenCalled();
  });

  it("cancels the debouncer on an empty-input submit (error branch)", async () => {
    const debouncer = stubDebouncer();
    const decision = await decideSubmit({
      debouncer,
      open: false,
      highlighted: undefined,
      inputValue: "   ",
      resolveSymbol: vi.fn(),
    });
    expect(debouncer.cancel).toHaveBeenCalledTimes(1);
    expect(decision).toEqual({ kind: "invalidInput", message: "請輸入股票代號" });
  });

  it("cancels the debouncer on a bad-symbol-pattern submit (error branch)", async () => {
    const debouncer = stubDebouncer();
    const decision = await decideSubmit({
      debouncer,
      open: false,
      highlighted: undefined,
      inputValue: "!!!",
      resolveSymbol: vi.fn(),
    });
    expect(debouncer.cancel).toHaveBeenCalledTimes(1);
    expect(decision).toEqual({
      kind: "invalidInput",
      message: "代號格式不正確，僅接受英數字與小數點",
    });
  });

  it("cancels the debouncer before a successful resolve-to-navigate submit", async () => {
    const debouncer = stubDebouncer();
    const resolveSymbol = vi.fn().mockResolvedValue(ITEM);
    const decision = await decideSubmit({
      debouncer,
      open: false,
      highlighted: undefined,
      inputValue: "2330",
      resolveSymbol,
    });
    expect(debouncer.cancel).toHaveBeenCalledTimes(1);
    expect(resolveSymbol).toHaveBeenCalledWith("2330");
    expect(decision).toEqual({
      kind: "resolved",
      outcome: { type: "navigate", symbol: "2330", market: "TW" },
    });
  });

  it("cancels the debouncer on a resolve-miss submit (needs the market picker)", async () => {
    const debouncer = stubDebouncer();
    const resolveSymbol = vi.fn().mockResolvedValue(null);
    const decision = await decideSubmit({
      debouncer,
      open: false,
      highlighted: undefined,
      inputValue: "9999X",
      resolveSymbol,
    });
    expect(debouncer.cancel).toHaveBeenCalledTimes(1);
    expect(decision).toEqual({
      kind: "resolved",
      outcome: { type: "needMarketPicker", symbol: "9999X" },
    });
  });

  it("cancels the debouncer even when resolveSymbol rejects (network-failure error branch)", async () => {
    const debouncer = stubDebouncer();
    const resolveSymbol = vi.fn().mockRejectedValue(new Error("network down"));
    const decision = await decideSubmit({
      debouncer,
      open: false,
      highlighted: undefined,
      inputValue: "2330",
      resolveSymbol,
    });
    expect(debouncer.cancel).toHaveBeenCalledTimes(1);
    expect(decision).toEqual({ kind: "resolveFailed" });
  });

  it("cancels the debouncer even when a candidate is highlighted but the dropdown is closed (falls through to validation)", async () => {
    // `open: false` means the highlighted candidate must not be used (mirrors
    // NavBar only reading `candidates[highlightedIndex]` while `open`), so
    // this exercises the *first* real branch (empty input) with a
    // non-undefined `highlighted` still present, guarding against a future
    // refactor accidentally checking `highlighted` alone.
    const debouncer = stubDebouncer();
    const decision = await decideSubmit({
      debouncer,
      open: false,
      highlighted: ITEM,
      inputValue: "",
      resolveSymbol: vi.fn(),
    });
    expect(debouncer.cancel).toHaveBeenCalledTimes(1);
    expect(decision).toEqual({ kind: "invalidInput", message: "請輸入股票代號" });
  });
});
