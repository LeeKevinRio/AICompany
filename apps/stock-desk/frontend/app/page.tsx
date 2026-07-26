"use client";

import { useHealth, usePortfolioSummary } from "./lib/queries";
import { BackendOfflineState } from "./components/BackendOfflineState";
import { SummaryCards } from "./components/SummaryCards";
import { SummaryCardsSkeleton, TableSkeleton } from "./components/SkeletonBlock";
import { PositionsTable } from "./components/PositionsTable";
import { RiskGauge } from "./components/RiskGauge";
import { PendingAlertsPanel } from "./components/PendingAlertsPanel";

export default function HomePage() {
  const health = useHealth();
  const summary = usePortfolioSummary(health.isSuccess);

  if (health.isPending) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-8">
        <SummaryCardsSkeleton />
        <div className="mt-8">
          <TableSkeleton />
        </div>
      </main>
    );
  }

  if (health.isError) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-8">
        <BackendOfflineState
          onRetry={() => {
            void health.refetch();
          }}
        />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-bold text-neutral-100">投資組合總覽</h1>

      <div className="mt-6">
        {summary.isPending && <SummaryCardsSkeleton />}
        {summary.isError && (
          <p
            role="alert"
            className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300"
          >
            無法載入投資組合摘要：
            {summary.error instanceof Error ? summary.error.message : "未知錯誤"}
          </p>
        )}
        {summary.isSuccess && (
          <SummaryCards totals={summary.data.totals} asOf={summary.data.as_of} />
        )}
      </div>

      <div className="mt-8">
        <h2 className="text-lg font-semibold text-neutral-100">持倉明細</h2>
        <div className="mt-3">
          {summary.isPending && <TableSkeleton />}
          {summary.isSuccess && <PositionsTable positions={summary.data.positions} />}
        </div>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <RiskGauge />
        <PendingAlertsPanel />
      </div>
    </main>
  );
}
