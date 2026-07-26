"use client";

import Link from "next/link";
import { useState } from "react";
import type { BacktestResponse } from "../lib/types";
import { BacktestForm } from "./BacktestForm";
import { BacktestReportView } from "./BacktestReportView";

export default function BacktestPage() {
  const [report, setReport] = useState<BacktestResponse | null>(null);

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-neutral-100">回測</h1>
        <Link href="/" className="text-sm text-sky-400 underline hover:text-sky-300">
          回總覽
        </Link>
      </div>
      <p className="mt-2 text-sm text-neutral-400">
        以均線交叉（MA Cross）策略回測單一標的，並附上同期間 Buy &amp; Hold 對照與樣本內／外分列結果。
      </p>

      <div className="mt-6">
        <BacktestForm onResult={setReport} />
      </div>

      {report && <BacktestReportView report={report} />}
    </main>
  );
}
