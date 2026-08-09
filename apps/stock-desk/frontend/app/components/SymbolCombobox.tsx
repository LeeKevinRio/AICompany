"use client";

import { useEffect, useRef, useState } from "react";
import type { DirectoryItem } from "../lib/types";
import { marketLabel } from "../lib/format";
import { useDirectorySearch } from "../lib/queries";
import {
  DIRECTORY_SEARCH_DEBOUNCE_MS,
  createDebouncer,
  decideComboboxKeyDown,
  directorySearchNotice,
  shouldShowCandidates,
} from "../lib/directorySearch";

/**
 * Symbol/company-name combobox for the position forms (`ManualAddForm.tsx`,
 * `EditPositionModal.tsx` — CEO 指示 2026-08-09: 把證券目錄自動完成接到「新增
 * 部位」表單的代號欄). Reuses the same pure decision functions and
 * `useDirectorySearch` hook as `NavBar.tsx`'s `SymbolSearch` (300ms debounce
 * via `createDebouncer`, `shouldShowCandidates`/`directorySearchNotice` for
 * FR-7's honest degrade, full aria combobox/listbox wiring) but is a
 * *parallel* implementation, not an extraction of NavBar into a shared
 * component, for two reasons:
 *   1. NavBar's Enter key resolves the typed symbol and navigates
 *      (`decideSubmit` + `resolveDirectorySymbol`) — there is no equivalent
 *      here. This component only ever fills the caller's form fields via
 *      `onSelect`; a plain-symbol Enter with nothing highlighted simply
 *      falls through to the position form's own `<form onSubmit>`,
 *      unchanged from before this feature (manual free-text entry is never
 *      blocked, per the dispatch order's degrade requirement).
 *   2. NavBar owns `value`/`open`/`highlightedIndex` entirely as internal
 *      state; here `value` must be the caller's own form field (`form.symbol`
 *      via `updateField`, same as every other field in `FormState`) so a
 *      selected candidate's symbol lands in the exact same state slot a
 *      manually typed one would — `onChange` is a plain string setter, and
 *      `onSelect` is only ever called on an actual candidate pick (see
 *      `applyDirectorySelection`, `lib/directorySearch.ts`, for what a
 *      caller does with it).
 * `market` is never touched by this component itself — filling it in from a
 * selection, and leaving a later manual `market` `<select>` change alone
 * afterwards, is entirely the caller's `onSelect` handler (Q4 CEO 裁示: 市場
 * 欄手動 select 保留，選定候選後仍可再手動改).
 */
export function SymbolCombobox({
  id,
  value,
  onChange,
  onSelect,
  required = false,
  placeholder,
  className,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  onSelect: (item: DirectoryItem) => void;
  required?: boolean;
  placeholder?: string;
  className?: string;
}) {
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const debouncerRef = useRef(createDebouncer(DIRECTORY_SEARCH_DEBOUNCE_MS));

  const search = useDirectorySearch(debouncedQuery, debouncedQuery.length > 0);
  const candidates = shouldShowCandidates(search.data) && search.data ? search.data.items : [];
  const notice = directorySearchNotice(search.data);

  // Same unmount-safety concern as NavBar's `SymbolSearch`: an unmount (this
  // component lives inside a modal / a form that can be reset after submit)
  // must not let a pending debounce fire afterwards.
  useEffect(() => {
    const debouncer = debouncerRef.current;
    return () => debouncer.cancel();
  }, []);

  function closeDropdown() {
    setOpen(false);
    setHighlightedIndex(-1);
  }

  function handleChange(next: string) {
    onChange(next);
    setHighlightedIndex(-1);
    const trimmed = next.trim();
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

  function selectCandidate(item: DirectoryItem) {
    debouncerRef.current.cancel();
    closeDropdown();
    setDebouncedQuery("");
    onSelect(item);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    const decision = decideComboboxKeyDown(event.key, {
      open,
      highlightedIndex,
      candidatesLength: candidates.length,
    });
    switch (decision.kind) {
      case "highlightMove":
        event.preventDefault();
        setOpen(true);
        setHighlightedIndex(decision.index);
        break;
      case "selectHighlighted": {
        // Must preventDefault: without it, Enter would also bubble up to the
        // surrounding multi-field `<form>` and attempt to submit it.
        event.preventDefault();
        const item = candidates[highlightedIndex];
        // `decideComboboxKeyDown` only returns this decision when
        // `highlightedIndex < candidatesLength`, so this is always defined —
        // the guard is here purely to satisfy strict mode without an
        // assertion.
        if (item) selectCandidate(item);
        break;
      }
      case "close":
        closeDropdown();
        break;
      case "none":
        break;
    }
  }

  const showDropdown = open && (candidates.length > 0 || notice !== null);
  const listboxId = `${id}-listbox`;

  return (
    <div className="relative">
      <input
        id={id}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={showDropdown}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={
          highlightedIndex >= 0 && candidates[highlightedIndex]
            ? `${id}-option-${highlightedIndex}`
            : undefined
        }
        required={required}
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={() => {
          if (candidates.length > 0 || notice !== null) setOpen(true);
        }}
        onBlur={() => {
          // mousedown on a candidate (below) fires before this blur commits,
          // so a short delay lets the click's own handler run first — same
          // pattern as NavBar's `SymbolSearch`.
          window.setTimeout(() => closeDropdown(), 100);
        }}
        placeholder={placeholder}
        autoComplete="off"
        className={
          className ??
          "mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
        }
      />

      {showDropdown && (
        <ul
          id={listboxId}
          role="listbox"
          aria-label="股票代號或公司名稱搜尋候選"
          className="absolute left-0 right-0 top-full z-10 mt-1 rounded-md border border-neutral-700 bg-neutral-900 py-1 text-sm shadow-lg"
        >
          {candidates.map((item, index) => (
            <li
              key={item.symbol}
              id={`${id}-option-${index}`}
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
            // Same neutral-400 contrast fix as NavBar's `SymbolSearch`
            // (§2.1 對比度列管, 2026-08-09 風控裁量) — neutral-500 on this
            // dark background is <AA (3.9:1); neutral-400 clears it (~7.5:1).
            <li className="border-t border-neutral-800 px-3 py-1.5 text-xs text-neutral-400">{notice}</li>
          )}
        </ul>
      )}
    </div>
  );
}
