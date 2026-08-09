"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { DirectoryItem, Market } from "../lib/types";
import { MARKET_OPTIONS, marketLabel } from "../lib/format";
import { resolveDirectorySymbol } from "../lib/api";
import { useDirectorySearch } from "../lib/queries";
import {
  DIRECTORY_SEARCH_DEBOUNCE_MS,
  MARKET_PICKER_PROMPT,
  createDebouncer,
  decideAfterResolve,
  directorySearchNotice,
  nextHighlightedIndex,
  shouldShowCandidates,
} from "../lib/directorySearch";

// FR-C7(a): a symbol is whatever the backend's `Market` literal accepts as a
// path segment — no known closed vocabulary to validate against on the
// front end (TW tickers are numeric, US tickers are alphabetic, both can
// carry a "." for share-class suffixes). This only rejects what can never be
// a valid symbol: empty input, whitespace, characters that would need
// URL-encoding games to survive the round trip, and input made up entirely
// of "." with no actual ticker characters (qa-reviewer Minor follow-up).
const SYMBOL_PATTERN = /^(?=.*[A-Za-z0-9])[A-Za-z0-9.]+$/;

/**
 * NavBar symbol/company-name combobox (FR-4/FR-5/FR-7,
 * `work/stock-desk-代號目錄-PRD.md`). Replaces the old plain text input +
 * hand-picked market `<select>`:
 * - Typing debounces (300ms, `directorySearch.ts`) into
 *   `GET /api/directory/search` and shows candidates; ArrowUp/ArrowDown/Enter
 *   select without a mouse (AC-8), Escape closes.
 * - Selecting a candidate navigates with *its* market — the user is never
 *   asked to pick one (AC-9, FR-5).
 * - The old "type a full symbol, press Enter" direct path still works
 *   (AC-10): it now resolves the symbol first so the destination market is
 *   still automatic; only on a directory miss does it fall back to Q1(b)'s
 *   small TW/US picker instead of guessing (AC-4).
 * - `directory_synced: false` (FR-7) degrades the dropdown to a status line
 *   with no fake candidates; the direct-Enter path keeps working underneath.
 */
function SymbolSearch() {
  const router = useRouter();
  const [inputValue, setInputValue] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const [pendingMarketSymbol, setPendingMarketSymbol] = useState<string | null>(null);
  const debouncerRef = useRef(createDebouncer(DIRECTORY_SEARCH_DEBOUNCE_MS));

  const search = useDirectorySearch(debouncedQuery, debouncedQuery.length > 0);
  const candidates = shouldShowCandidates(search.data) && search.data ? search.data.items : [];
  const notice = directorySearchNotice(search.data);

  useEffect(() => {
    const debouncer = debouncerRef.current;
    return () => debouncer.cancel();
  }, []);

  function closeDropdown() {
    setOpen(false);
    setHighlightedIndex(-1);
  }

  function handleChange(value: string) {
    setInputValue(value);
    setHighlightedIndex(-1);
    if (error) setError(null);
    if (pendingMarketSymbol) setPendingMarketSymbol(null);
    const trimmed = value.trim();
    if (trimmed.length === 0) {
      debouncerRef.current.cancel();
      setDebouncedQuery("");
      closeDropdown();
      return;
    }
    debouncerRef.current.schedule(() => {
      setDebouncedQuery(trimmed);
      setOpen(true);
    });
  }

  function navigateTo(symbol: string, market: Market) {
    closeDropdown();
    setInputValue("");
    setDebouncedQuery("");
    setPendingMarketSymbol(null);
    router.push(`/position/${encodeURIComponent(symbol)}?market=${market}`);
  }

  function selectCandidate(item: DirectoryItem) {
    navigateTo(item.symbol, item.market);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (open) {
      const highlighted = highlightedIndex >= 0 ? candidates[highlightedIndex] : undefined;
      if (highlighted) {
        selectCandidate(highlighted);
        return;
      }
    }
    const trimmed = inputValue.trim();
    if (trimmed.length === 0) {
      setError("請輸入股票代號");
      return;
    }
    if (!SYMBOL_PATTERN.test(trimmed)) {
      setError("代號格式不正確，僅接受英數字與小數點");
      return;
    }
    setError(null);
    closeDropdown();
    setResolving(true);
    try {
      const resolved = await resolveDirectorySymbol(trimmed);
      const outcome = decideAfterResolve(trimmed, resolved);
      if (outcome.type === "navigate") {
        navigateTo(outcome.symbol, outcome.market);
      } else {
        setPendingMarketSymbol(outcome.symbol);
      }
    } catch {
      setError("查詢失敗，請稍後再試");
    } finally {
      setResolving(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (candidates.length === 0) return;
      event.preventDefault();
      setOpen(true);
      setHighlightedIndex((current) => nextHighlightedIndex(event.key as "ArrowDown" | "ArrowUp", current, candidates.length));
    } else if (event.key === "Escape") {
      closeDropdown();
    }
  }

  const showDropdown = open && (candidates.length > 0 || notice !== null);

  return (
    <div className="flex flex-col items-end gap-1">
      <form onSubmit={handleSubmit} className="relative flex items-center gap-1.5">
        <label htmlFor="nav-symbol-search" className="sr-only">
          查詢股票代號或公司名稱
        </label>
        <input
          id="nav-symbol-search"
          role="combobox"
          aria-expanded={showDropdown}
          aria-controls="nav-symbol-search-listbox"
          aria-autocomplete="list"
          aria-activedescendant={
            highlightedIndex >= 0 && candidates[highlightedIndex]
              ? `nav-symbol-search-option-${highlightedIndex}`
              : undefined
          }
          value={inputValue}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (candidates.length > 0 || notice !== null) setOpen(true);
          }}
          onBlur={() => {
            // mousedown on a candidate (below) fires before this blur commits,
            // so a short delay lets the click's own handler run first.
            window.setTimeout(() => closeDropdown(), 100);
          }}
          placeholder="代號或公司名稱，如 2330 / 台積電"
          autoComplete="off"
          aria-invalid={error !== null}
          aria-describedby={error !== null ? "nav-symbol-search-error" : undefined}
          className="w-32 rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-100 sm:w-48"
        />
        <button
          type="submit"
          disabled={resolving}
          className="rounded-md bg-neutral-100 px-2.5 py-1 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          {resolving ? "查詢中…" : "查詢"}
        </button>

        {showDropdown && (
          <ul
            id="nav-symbol-search-listbox"
            role="listbox"
            aria-label="股票代號或公司名稱搜尋候選"
            className="absolute right-0 top-full z-10 mt-1 w-64 rounded-md border border-neutral-700 bg-neutral-900 py-1 text-sm shadow-lg"
          >
            {candidates.map((item, index) => (
              <li
                key={item.symbol}
                id={`nav-symbol-search-option-${index}`}
                role="option"
                aria-selected={index === highlightedIndex}
                onMouseDown={(e) => {
                  // mousedown fires before the input's blur, so the click still lands.
                  e.preventDefault();
                  selectCandidate(item);
                }}
                onMouseEnter={() => setHighlightedIndex(index)}
                className={`cursor-pointer px-3 py-1.5 ${
                  index === highlightedIndex ? "bg-neutral-800 text-neutral-100" : "text-neutral-300"
                }`}
              >
                <span className="font-medium text-neutral-100">{item.symbol}</span> {item.name}
                <span className="ml-1 text-xs text-neutral-500">（{marketLabel(item.market)}）</span>
              </li>
            ))}
            {notice !== null && (
              <li className="border-t border-neutral-800 px-3 py-1.5 text-xs text-neutral-500">{notice}</li>
            )}
          </ul>
        )}
      </form>

      {error !== null && (
        <p id="nav-symbol-search-error" role="alert" className="text-xs text-rose-400">
          {error}
        </p>
      )}

      {pendingMarketSymbol !== null && (
        <div className="flex items-center gap-2 rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-xs text-neutral-300">
          <span>{MARKET_PICKER_PROMPT}</span>
          {MARKET_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => navigateTo(pendingMarketSymbol, opt.value)}
              className="rounded-md border border-neutral-600 px-2 py-0.5 hover:bg-neutral-800"
            >
              {opt.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setPendingMarketSymbol(null)}
            className="text-neutral-500 hover:text-neutral-300"
          >
            取消
          </button>
        </div>
      )}
    </div>
  );
}

export function NavBar() {
  return (
    <header className="border-b border-neutral-800 px-4 py-3">
      <div className="mx-auto flex max-w-5xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center justify-between gap-4">
          <Link href="/" className="text-lg font-bold text-neutral-100">
            stock-desk
          </Link>
          <nav className="flex flex-wrap gap-4 text-sm text-neutral-400">
            <Link href="/" className="hover:text-neutral-100">
              總覽
            </Link>
            <Link href="/positions/import" className="hover:text-neutral-100">
              匯入 / 新增部位
            </Link>
            <Link href="/backtest" className="hover:text-neutral-100">
              回測
            </Link>
            <Link href="/settings" className="hover:text-neutral-100">
              設定
            </Link>
          </nav>
        </div>
        <SymbolSearch />
      </div>
    </header>
  );
}
