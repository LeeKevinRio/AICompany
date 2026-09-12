"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { formMatchesReport, type FormSnapshot } from "../lib/eventStudy";
import { BACKTEST_PAGE_INTRO } from "../lib/eventStudyWording";
import type { BacktestRequest, BacktestResponse } from "../lib/types";
import { BacktestForm } from "./BacktestForm";
import { BacktestReportView } from "./BacktestReportView";
import { EventStudySection } from "./EventStudySection";

interface Displayed {
  report: BacktestResponse;
  request: BacktestRequest;
}

export default function BacktestPage() {
  const [displayed, setDisplayed] = useState<Displayed | null>(null);
  const [form, setForm] = useState<FormSnapshot | null>(null);

  const onResult = useCallback((report: BacktestResponse, request: BacktestRequest) => {
    setDisplayed({ report, request });
  }, []);
  const onFormChange = useCallback((snapshot: FormSnapshot) => setForm(snapshot), []);

  // PRD FR-1／SUG-W2: the event study exists only for a successful
  // five_conditions report; 風控 REQ-W4／W5: it follows the report on screen.
  // FR-6／AC-4: switching the strategy select away hides the section at once.
  const showEventStudy =
    displayed !== null &&
    displayed.request.strategy === "five_conditions" &&
    form?.strategy === "five_conditions" &&
    displayed.report.status !== "insufficient_data" &&
    displayed.report.report !== null;
  const formMatches = displayed !== null && form !== null && formMatchesReport(form, displayed.request);

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-neutral-100">回測</h1>
        <Link href="/" className="text-sm text-sky-400 underline hover:text-sky-300">
          回總覽
        </Link>
      </div>
      <p className="mt-2 text-sm text-neutral-400">{BACKTEST_PAGE_INTRO}</p>

      <div className="mt-6">
        <BacktestForm onResult={onResult} onFormChange={onFormChange} />
      </div>

      {displayed && <BacktestReportView report={displayed.report} />}

      {/* 風控 REQ-W1: a sibling of the report section, never inside it. */}
      {showEventStudy && displayed && (
        <EventStudySection report={displayed.report} request={displayed.request} formMatches={formMatches} />
      )}
    </main>
  );
}
