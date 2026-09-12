import type { BacktestRequest, Market } from "./types";

/**
 * Pure helpers behind the `/backtest` event-study section (PRD FR-2／FR-6／FR-7,
 * 風控 REQ-W4／REQ-W5).
 *
 * The event study is computed for **the report on screen**, never for the
 * live form: its request is derived from the backtest request that produced
 * the displayed report, and the button is disabled the moment the form drifts
 * from that request. Any change of the displayed report clears the study
 * (REQ-W4: clear, never annotate).
 */

export interface EventStudyRequest {
  symbol: string;
  market: Market;
  start: string;
  end: string;
}

/** The four fields the event study reads off the backtest request that produced the report. */
export function eventStudyRequestFrom(request: BacktestRequest): EventStudyRequest {
  return { symbol: request.symbol, market: request.market, start: request.start, end: request.end };
}

/** Fields of the form that, once changed, make the displayed report stale for the event study. */
export interface FormSnapshot {
  symbol: string;
  market: Market;
  strategy: string;
  start: string;
  end: string;
}

/**
 * 風控 REQ-W5: the button is enabled only while the form still says exactly
 * what the displayed report was run with. Symbol comparison trims whitespace
 * (the form submits a trimmed symbol); everything else is exact.
 */
export function formMatchesReport(form: FormSnapshot, request: BacktestRequest): boolean {
  return (
    form.symbol.trim() === request.symbol &&
    form.market === request.market &&
    form.strategy === request.strategy &&
    form.start === request.start &&
    form.end === request.end
  );
}

/** A stable identity for "the report on screen"; a new key clears the study (REQ-W4). */
export function reportKey(request: BacktestRequest, asOf: string): string {
  return [request.symbol, request.market, request.strategy, request.start, request.end, asOf].join("|");
}

/**
 * Guards an in-flight request against the screen moving on underneath it
 * (qa-reviewer 2026-09-12 high: a stale response must never re-populate a
 * study that REQ-W4／W5 already cleared).
 *
 * `begin()` hands out a ticket for a new request; `invalidate()` retires every
 * ticket issued so far (call it whenever the study is cleared); `isCurrent()`
 * says whether a response arriving now still belongs to the report on screen.
 */
export interface RequestSequencer {
  begin(): number;
  invalidate(): void;
  isCurrent(ticket: number): boolean;
}

export function createRequestSequencer(): RequestSequencer {
  let latest = 0;
  return {
    begin() {
      latest += 1;
      return latest;
    },
    invalidate() {
      latest += 1;
    },
    isCurrent(ticket) {
      return ticket === latest;
    },
  };
}
