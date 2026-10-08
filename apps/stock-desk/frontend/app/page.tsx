"use client";

import { useHealth, usePortfolioSummary } from "./lib/queries";
import { hasBackupFx } from "./lib/fxBackupBadge";
import { BackendOfflineState } from "./components/BackendOfflineState";
import { SummaryCards } from "./components/SummaryCards";
import { SummaryCardsSkeleton, TableSkeleton } from "./components/SkeletonBlock";
import { PositionsTable } from "./components/PositionsTable";
import { RiskGauge } from "./components/RiskGauge";
import { AlertStatusStrip } from "./components/AlertStatusStrip";
import { SectorMomentumCard } from "./components/SectorMomentumCard";

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
          <SummaryCards
            totals={summary.data.totals}
            asOf={summary.data.as_of}
            positions={summary.data.positions}
            fxDisclosures={summary.data.fx_disclosures}
            // PR-RK5c (RK5-R3): the standing backup-FX badge shows when any ok
            // (valued) position's `fx` or `fx_open` is backup-sourced. The rule
            // lives in hasBackupFx; no threshold, wording unchanged.
            fxBackupActive={hasBackupFx(summary.data.positions)}
          />
        )}
      </div>

      <div className="mt-8">
        <h2 className="text-lg font-semibold text-neutral-100">持倉明細</h2>
        <div className="mt-3">
          {summary.isPending && <TableSkeleton />}
          {summary.isSuccess && (
            <PositionsTable positions={summary.data.positions} changeMode={summary.data.change_mode} />
          )}
        </div>
      </div>

      {/* 首頁「一眼一句」簡化（work/stock-desk-一眼一句-實作規格.md §3.1）：
          風險儀表與警示狀態列改全寬直排，不再並排——並排會讓長期為空的警示卡
          看起來像壞掉（派工單 §1.3）。 */}
      <div className="mt-8">
        <RiskGauge />
      </div>

      <div className="mt-6">
        <AlertStatusStrip />
      </div>

      {/* Home reflow, phase 1 (CEO 2026-10-03; `work/stock-desk-首頁重排-視覺規範-
          2026-10-03.md` §1): order is summary -> positions -> risk gauge + alerts
          -> sector momentum. Sector momentum is market intelligence, not my
          positions, so it moves last (reverses wave 4 FR-1 "sector card before
          the positions table"). Risk gauge and sector card are both close-based
          (C4), with only the alert strip between them. */}
      <div className="mt-8">
        <SectorMomentumCard />
      </div>
    </main>
  );
}
