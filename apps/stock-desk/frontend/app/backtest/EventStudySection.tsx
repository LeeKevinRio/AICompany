"use client";

import { useEffect, useRef, useState } from "react";
import { DataMetaStatusBadge } from "../components/DataMetaStatusBadge";
import { InsufficientPanel } from "../components/InsufficientPanel";
import { runEventStudy } from "../lib/api";
import { createRequestSequencer, eventStudyRequestFrom, reportKey } from "../lib/eventStudy";
import {
  EVENT_STUDY_BUTTON_LABEL,
  EVENT_STUDY_ERROR,
  EVENT_STUDY_LOADING,
  EVENT_STUDY_SECTION_TITLE,
  EVENT_STUDY_SEPARATOR_SENTENCES,
  EVENT_STUDY_STALE_FORM_HINT,
} from "../lib/eventStudyWording";
import type { BacktestRequest, BacktestResponse, EventStudyResponse } from "../lib/types";

/**
 * 「五項觀察條件 事件研究」 on `/backtest` (PRD `work/stock-desk-事件研究網頁版-PRD.md`,
 * ADR-0008, 風控預審 REQ-W1～W14).
 *
 * - Sibling of the report section, never inside it (REQ-W1): its own border and title.
 * - Everything the section *says* comes from `POST /api/event-study` in reading
 *   order: `page.header` items are rendered top to bottom without filtering
 *   (REQ-W8, ADR-0008 D-2), then the five sections, then the footnotes. The
 *   only frontend-owned sentences are the shell's (`eventStudyWording.ts`).
 * - The one `dangerouslySetInnerHTML` sink is `section.svg`, an SVG the backend
 *   built from numbers with every text node escaped (ADR-0008 D-5).
 * - Figures keep the CLI page's `#111111` panel on `#262626` border so the
 *   validated palette (and the hollow marks filled with that panel colour)
 *   render exactly as reviewed (REQ-W9); charts are 800px and never scaled —
 *   narrow viewports scroll the figure horizontally (REQ-W6).
 * - The study is computed for the report on screen, never the live form
 *   (REQ-W5); the button is disabled while the form has drifted, and any
 *   change of the displayed report clears the result (REQ-W4).
 */

interface Props {
  /** The report currently on screen and the request that produced it. */
  report: BacktestResponse;
  request: BacktestRequest;
  /** 風控 REQ-W5: false once the form no longer says what the report was run with. */
  formMatches: boolean;
}

export function EventStudySection({ report, request, formMatches }: Props) {
  const [result, setResult] = useState<EventStudyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const key = reportKey(request, report.as_of);
  // A response that lands after the study was cleared (new report, drifted
  // form, unmount) is dropped, never written back (qa-reviewer 2026-09-12).
  const sequencer = useRef(createRequestSequencer());

  // 風控 REQ-W4: a different report on screen, or a form that no longer says
  // what the report was run with → the study is gone, never annotated.
  useEffect(() => {
    sequencer.current.invalidate();
    setResult(null);
    setFailed(false);
    setLoading(false);
  }, [key]);
  useEffect(() => {
    if (!formMatches) {
      sequencer.current.invalidate();
      setResult(null);
      setFailed(false);
      setLoading(false);
    }
  }, [formMatches]);
  useEffect(() => {
    const current = sequencer.current;
    return () => current.invalidate();
  }, []);

  async function show() {
    const ticket = sequencer.current.begin();
    setLoading(true);
    setFailed(false);
    try {
      const response = await runEventStudy(eventStudyRequestFrom(request));
      if (!sequencer.current.isCurrent(ticket)) return;
      setResult(response);
    } catch {
      if (!sequencer.current.isCurrent(ticket)) return;
      setFailed(true);
    } finally {
      if (sequencer.current.isCurrent(ticket)) setLoading(false);
    }
  }

  return (
    <section className="mt-6 rounded-lg border border-neutral-800 p-5" aria-label={EVENT_STUDY_SECTION_TITLE}>
      <h2 className="text-lg font-semibold text-neutral-100">{EVENT_STUDY_SECTION_TITLE}</h2>

      {/* 風控 REQ-W2: standing, body-size, before the button and before any chart. */}
      <div className="mt-2 rounded-md border border-neutral-700 bg-neutral-900/60 px-4 py-2 text-sm text-neutral-300">
        {EVENT_STUDY_SEPARATOR_SENTENCES.map((sentence) => (
          <p key={sentence}>{sentence}</p>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={show}
          disabled={!formMatches || loading}
          className="rounded-md border border-neutral-600 bg-neutral-800 px-4 py-2 text-sm text-neutral-100 hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {EVENT_STUDY_BUTTON_LABEL}
        </button>
        {!formMatches && <p className="text-sm text-neutral-300">{EVENT_STUDY_STALE_FORM_HINT}</p>}
      </div>

      {loading && <p className="mt-3 text-sm text-neutral-300">{EVENT_STUDY_LOADING}</p>}
      {failed && (
        <p role="alert" className="mt-3 rounded-md border border-amber-800 bg-amber-950/40 px-4 py-2 text-sm text-amber-300">
          {EVENT_STUDY_ERROR}
        </p>
      )}

      {result && result.page === null && (
        <div className="mt-3">
          <InsufficientPanel reason={result.reason} />
        </div>
      )}

      {result && result.page && (
        <div className="mt-4">
          {/* 風控 REQ-W11: this section's own data freshness, from its own response. */}
          <p className="flex flex-wrap items-center gap-2 text-sm text-neutral-400">
            來源：{result.data.source}
            {result.data.last_bar_date !== null && <span>｜資料截至 {result.data.last_bar_date}</span>}
            <DataMetaStatusBadge
              status={result.data.status}
              stalenessMinutes={result.data.staleness_minutes}
              isWithinTtl={result.data.is_within_ttl}
              lastBarDate={result.data.last_bar_date}
              reason={result.data.reason}
            />
          </p>
          <h3 className="mt-2 text-base font-semibold text-neutral-100">{result.page.title}</h3>

          {/* ADR-0008 D-2 / REQ-W8: rendered in the order the backend sent, nothing skipped. */}
          {result.page.header.map((item, index) =>
            item.role === "notice" ? (
              <p key={index} className="mt-2 rounded-md border border-neutral-700 px-3 py-2 text-sm text-neutral-200">
                {item.text}
              </p>
            ) : item.role === "legend" ? (
              <p key={index} className="mt-1 text-sm text-neutral-300">
                {item.text}
              </p>
            ) : (
              <p key={index} className="mt-1 text-sm text-neutral-400">
                {item.text}
              </p>
            ),
          )}

          {result.page.sections.map((section) => (
            <section key={section.key} className="mt-6" aria-label={section.title}>
              <h4 className="text-sm font-semibold text-neutral-200">{section.title}</h4>
              {section.no_events_note && <p className="mt-1 text-sm text-neutral-300">{section.no_events_note}</p>}
              {section.svg !== null ? (
                <figure
                  className="mt-2 overflow-x-auto rounded-md border p-3"
                  style={{ background: "#111111", borderColor: "#262626" }}
                >
                  {/* The single innerHTML sink: backend-built SVG from numbers (ADR-0008 D-5). */}
                  <div dangerouslySetInnerHTML={{ __html: section.svg }} />
                </figure>
              ) : (
                <p className="mt-2 rounded-md border border-dashed border-neutral-700 px-3 py-2 text-sm text-neutral-300">
                  {section.empty_statement}
                </p>
              )}
              <p className="mt-1 text-sm text-neutral-300">{section.note}</p>
              {section.extra_note && <p className="mt-1 text-sm text-neutral-300">{section.extra_note}</p>}
            </section>
          ))}

          <h4 className="mt-6 text-sm font-semibold text-neutral-200">{result.page.footnotes_heading}</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-neutral-300">
            {result.page.footnotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
