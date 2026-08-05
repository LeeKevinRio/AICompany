"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Market } from "../lib/types";
import { MARKET_OPTIONS } from "../lib/format";

// FR-C7(a): a symbol is whatever the backend's `Market` literal accepts as a
// path segment — no known closed vocabulary to validate against on the
// front end (TW tickers are numeric, US tickers are alphabetic, both can
// carry a "." for share-class suffixes). This only rejects what can never be
// a valid symbol: empty input, whitespace, and characters that would need
// URL-encoding games to survive the round trip.
const SYMBOL_PATTERN = /^[A-Za-z0-9.]+$/;

/**
 * Small symbol lookup used to reach `/position/[symbol]` from anywhere
 * (FR-C7(a) query entry point). Validates in place instead of navigating on
 * bad input (AC-C7.1).
 */
function SymbolSearch() {
  const router = useRouter();
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<Market>("TW");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = symbol.trim();
    if (trimmed.length === 0) {
      setError("請輸入股票代號");
      return;
    }
    if (!SYMBOL_PATTERN.test(trimmed)) {
      setError("代號格式不正確，僅接受英數字與小數點");
      return;
    }
    setError(null);
    router.push(`/position/${encodeURIComponent(trimmed)}?market=${market}`);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1.5">
        <label htmlFor="nav-symbol-search" className="sr-only">
          查詢個股代號
        </label>
        <input
          id="nav-symbol-search"
          value={symbol}
          onChange={(e) => {
            setSymbol(e.target.value);
            if (error) setError(null);
          }}
          placeholder="代號，如 2330"
          aria-invalid={error !== null}
          aria-describedby={error !== null ? "nav-symbol-search-error" : undefined}
          className="w-24 rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-100 sm:w-32"
        />
        <label htmlFor="nav-market-search" className="sr-only">
          市場
        </label>
        <select
          id="nav-market-search"
          value={market}
          onChange={(e) => setMarket(e.target.value as Market)}
          className="rounded-md border border-neutral-700 bg-neutral-900 px-1.5 py-1 text-sm text-neutral-100"
        >
          {MARKET_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.value}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="rounded-md bg-neutral-100 px-2.5 py-1 text-sm font-medium text-neutral-900 hover:bg-white"
        >
          查詢
        </button>
      </div>
      {error !== null && (
        <p id="nav-symbol-search-error" role="alert" className="text-xs text-rose-400">
          {error}
        </p>
      )}
    </form>
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
