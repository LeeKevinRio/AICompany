"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Market } from "../lib/types";
import { MARKET_OPTIONS } from "../lib/format";

/** Small symbol lookup used to reach `/position/[symbol]` from anywhere. */
function SymbolSearch() {
  const router = useRouter();
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<Market>("TW");

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = symbol.trim();
    if (trimmed.length === 0) return;
    router.push(`/position/${encodeURIComponent(trimmed)}?market=${market}`);
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-1.5">
      <label htmlFor="nav-symbol-search" className="sr-only">
        查詢個股代號
      </label>
      <input
        id="nav-symbol-search"
        value={symbol}
        onChange={(e) => setSymbol(e.target.value)}
        placeholder="代號，如 2330"
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
