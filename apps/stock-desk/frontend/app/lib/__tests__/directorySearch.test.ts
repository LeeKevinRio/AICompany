import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DIRECTORY_NOT_SYNCED_NOTICE,
  DIRECTORY_TRUNCATED_NOTICE,
  applyDirectorySelection,
  createDebouncer,
  decideAfterResolve,
  decideComboboxKeyDown,
  decideSubmit,
  directorySearchNotice,
  nextHighlightedIndex,
  sectorAfterDirectorySelection,
  shouldShowCandidates,
} from "../directorySearch";
import { SECTOR_SOURCE_DISCLOSURE } from "../format";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";
import type { DirectoryItem, DirectorySearchResponse } from "../types";

const ITEM: DirectoryItem = {
  symbol: "2330",
  name: "台灣積體電路製造股份有限公司",
  market: "TW",
  source: "twse",
  as_of: "2026-08-09T00:00:00Z",
  sector: "半導體業",
  sector_source: "twse_openapi_t187ap03_L",
  sector_as_of: "2026-08-16T03:00:00Z",
};

const ITEM_US: DirectoryItem = {
  symbol: "AAPL",
  name: "Apple Inc.",
  market: "US",
  source: "nasdaq",
  as_of: "2026-08-09T00:00:00Z",
  sector: null,
  sector_source: null,
  sector_as_of: null,
};

/** An ETF / 上櫃 row: in the directory, but with no category to offer. */
const ITEM_NO_SECTOR: DirectoryItem = {
  symbol: "0050",
  name: "元大台灣50",
  market: "TW",
  source: "twse",
  as_of: "2026-08-09T00:00:00Z",
  sector: null,
  sector_source: null,
  sector_as_of: null,
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

describe("applyDirectorySelection (ManualAddForm/EditPositionModal SymbolCombobox wiring, CEO 指示 2026-08-09)", () => {
  interface FormState {
    symbol: string;
    market: "TW" | "US" | "";
    quantity: string;
  }
  const BASE_FORM: FormState = { symbol: "", market: "", quantity: "1000" };

  it("selecting a candidate syncs symbol and market from it (market 同步)", () => {
    const next = applyDirectorySelection(BASE_FORM, ITEM);
    expect(next).toEqual({ symbol: "2330", market: "TW", quantity: "1000" });
  });

  it("leaves every other field untouched and does not mutate the previous state", () => {
    const next = applyDirectorySelection(BASE_FORM, ITEM);
    expect(next.quantity).toBe(BASE_FORM.quantity);
    expect(next).not.toBe(BASE_FORM);
    expect(BASE_FORM).toEqual({ symbol: "", market: "", quantity: "1000" });
  });

  it("a manual market change made after a selection is not reverted (Q4 CEO 裁示: 市場欄手動 select 保留)", () => {
    const afterSelect = applyDirectorySelection(BASE_FORM, ITEM);
    // Simulates the market <select>'s own onChange, which never calls this
    // function — it is a plain field write, exactly like every other
    // `updateField` call in the form.
    const afterManualMarketEdit = { ...afterSelect, market: "US" as const };
    expect(afterManualMarketEdit).toEqual({ symbol: "2330", market: "US", quantity: "1000" });
  });

  it("selecting a second candidate overrides both symbol and market again", () => {
    const afterFirst = applyDirectorySelection(BASE_FORM, ITEM);
    const afterSecond = applyDirectorySelection(afterFirst, ITEM_US);
    expect(afterSecond).toEqual({ symbol: "AAPL", market: "US", quantity: "1000" });
  });
});

describe("decideComboboxKeyDown (SymbolCombobox keyboard dispatch)", () => {
  it("ArrowDown/ArrowUp delegate to nextHighlightedIndex when candidates exist", () => {
    expect(decideComboboxKeyDown("ArrowDown", { open: true, highlightedIndex: -1, candidatesLength: 3 })).toEqual({
      kind: "highlightMove",
      index: 0,
    });
    expect(decideComboboxKeyDown("ArrowUp", { open: true, highlightedIndex: 0, candidatesLength: 3 })).toEqual({
      kind: "highlightMove",
      index: 2,
    });
  });

  it("ArrowDown/ArrowUp do nothing when there are no candidates", () => {
    expect(decideComboboxKeyDown("ArrowDown", { open: false, highlightedIndex: -1, candidatesLength: 0 })).toEqual({
      kind: "none",
    });
  });

  it("Escape always closes, regardless of highlight state", () => {
    expect(decideComboboxKeyDown("Escape", { open: true, highlightedIndex: 1, candidatesLength: 3 })).toEqual({
      kind: "close",
    });
  });

  it("Enter selects the highlighted candidate only while the dropdown is open", () => {
    expect(decideComboboxKeyDown("Enter", { open: true, highlightedIndex: 1, candidatesLength: 3 })).toEqual({
      kind: "selectHighlighted",
    });
  });

  it("Enter with no highlight falls through (lets the surrounding form's own Enter behaviour run)", () => {
    expect(decideComboboxKeyDown("Enter", { open: true, highlightedIndex: -1, candidatesLength: 3 })).toEqual({
      kind: "none",
    });
  });

  it("Enter with a stale highlighted index from a closed dropdown does not select (mirrors NavBar's `open` gate)", () => {
    expect(decideComboboxKeyDown("Enter", { open: false, highlightedIndex: 1, candidatesLength: 3 })).toEqual({
      kind: "none",
    });
  });

  it("any other key is a no-op", () => {
    expect(decideComboboxKeyDown("a", { open: true, highlightedIndex: 1, candidatesLength: 3 })).toEqual({
      kind: "none",
    });
  });
});

describe("sectorAfterDirectorySelection (產業別自動帶入, CEO 指示 2026-08-16)", () => {
  it("fills the directory's category when a TW candidate is picked", () => {
    expect(
      sectorAfterDirectorySelection({ item: ITEM, previousSymbol: "", previousSector: "" }),
    ).toBe("半導體業");
  });

  it("leaves the field empty when the directory has no category (ETF / 上櫃 / 未同步)", () => {
    expect(
      sectorAfterDirectorySelection({
        item: ITEM_NO_SECTOR,
        previousSymbol: "",
        previousSector: "",
      }),
    ).toBe("");
  });

  it("never keeps the outgoing company's category when the symbol changes", () => {
    // 2330 was filed under 半導體業; switching to an ETF with no category must
    // not leave 半導體業 sitting on a different holding.
    expect(
      sectorAfterDirectorySelection({
        item: ITEM_NO_SECTOR,
        previousSymbol: "2330",
        previousSector: "半導體業",
      }),
    ).toBe("");
  });

  it("does not overwrite an existing value when the same symbol is re-picked (已有值不覆蓋)", () => {
    expect(
      sectorAfterDirectorySelection({
        item: ITEM,
        previousSymbol: "2330",
        previousSector: "其他業",
      }),
    ).toBe("其他業");
  });

  it("still fills the same symbol when the field is currently empty", () => {
    expect(
      sectorAfterDirectorySelection({ item: ITEM, previousSymbol: "2330", previousSector: "" }),
    ).toBe("半導體業");
  });

  it("clears the field for a non-TW candidate regardless of anything else (AC-12.6)", () => {
    expect(
      sectorAfterDirectorySelection({
        item: ITEM_US,
        previousSymbol: "AAPL",
        previousSector: "半導體業",
      }),
    ).toBe("");
  });

  it("returns a plain closed-list string, indistinguishable from a hand-picked value", () => {
    // The auto-filled value carries no marker, wrapper or flag: it is exactly
    // the kind of string the <select> would hold after a manual pick.
    const filled = sectorAfterDirectorySelection({
      item: ITEM,
      previousSymbol: "",
      previousSector: "",
    });
    expect(typeof filled).toBe("string");
    expect(filled).toBe(ITEM.sector);
  });
});

/**
 * 產業別來源說明句（`SECTOR_SOURCE_DISCLOSURE`，`format.ts`）。
 *
 * **待 risk-compliance-officer 覆核**：下面的逐字比對是防止句子被無聲改寫的守門，
 * 不代表這句已經核可。風控覆核後若指定改寫，這裡與 `format.ts` 的註解要一起更新。
 */
describe("SECTOR_SOURCE_DISCLOSURE (產業別來源說明，待風控覆核)", () => {
  it("contains none of the §1.3 banned terms", () => {
    assertNoForbiddenTerms(
      SECTOR_SOURCE_DISCLOSURE,
      FRONTEND_FORBIDDEN_TERMS,
      "SECTOR_SOURCE_DISCLOSURE",
    );
  });

  it("every '即時' occurrence is a '非即時' denial, never a bare claim", () => {
    expect(findBareRealtimeClaims(SECTOR_SOURCE_DISCLOSURE)).toEqual([]);
  });

  it("states the source, the staleness basis, the uncovered instruments and that the field is editable", () => {
    expect(SECTOR_SOURCE_DISCLOSURE).toContain("證交所公開資料");
    expect(SECTOR_SOURCE_DISCLOSURE).toContain("最後一次同步的時間");
    expect(SECTOR_SOURCE_DISCLOSURE).toContain("上櫃股票與 ETF");
    expect(SECTOR_SOURCE_DISCLOSURE).toContain("可自行修改");
  });

  it("does not tell the user the classification is handled for them", () => {
    // CEO 指示 2026-08-16 第 4 點: 不得含「自動幫你分類好了不用管」類語氣。
    for (const phrase of ["不用管", "不必管", "免填", "無需確認", "不需確認", "已幫您", "已幫你"]) {
      expect(SECTOR_SOURCE_DISCLOSURE).not.toContain(phrase);
    }
  });
});
