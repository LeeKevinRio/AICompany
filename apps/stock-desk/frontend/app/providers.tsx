"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";
import { ExitReceiptStoreProvider } from "./lib/exitReceiptContext";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      {/* 出清受理回執 store（Q15 方案 D）：Providers 範圍，記憶體內，隨文件載入重建。 */}
      <ExitReceiptStoreProvider>{children}</ExitReceiptStoreProvider>
    </QueryClientProvider>
  );
}
