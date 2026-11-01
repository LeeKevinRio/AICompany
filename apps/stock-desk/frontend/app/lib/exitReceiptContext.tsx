"use client";

import { createContext, useContext, useState } from "react";
import type { ReactNode } from "react";
import { createExitReceiptStore } from "./exitReceiptStore";
import type { ExitReceiptStore } from "./exitReceiptStore";

const ExitReceiptStoreContext = createContext<ExitReceiptStore | null>(null);

/**
 * Owns the one receipt store of this document. Mounted by `Providers`, above
 * every route, so the store outlives page navigation; created with
 * `useState(() => …)` like the `QueryClient` beside it, never at module level.
 */
export function ExitReceiptStoreProvider({ children }: { children: ReactNode }) {
  const [store] = useState(() => createExitReceiptStore());
  return (
    <ExitReceiptStoreContext.Provider value={store}>{children}</ExitReceiptStoreContext.Provider>
  );
}

export function useExitReceiptStore(): ExitReceiptStore {
  const store = useContext(ExitReceiptStoreContext);
  if (store === null) {
    throw new Error("useExitReceiptStore must be used inside <ExitReceiptStoreProvider>");
  }
  return store;
}
