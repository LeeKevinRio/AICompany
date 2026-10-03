/**
 * Valuation-basis sentence for the total-assets card (C3-3 and the C5-1
 * tooltip, `work/copy/盤中價揭露文案-定稿-2026-10-03.md`). Current state is S0:
 * every price is a daily close, so only the "all closing prices" sentence
 * exists. Dates come straight from each position's `valuation.price.as_of`
 * (a bare trading date, Taipei); nothing is inferred or recomputed here.
 */

import {
  C3_3_BASIS_ALL_CLOSE_RANGE,
  C3_3_BASIS_ALL_CLOSE_SINGLE,
  C5_1_TOOLTIP_SENTENCE_1,
  C5_1_TOOLTIP_SENTENCE_2,
  fillIntradayTemplate,
} from "./intradayWording";
import { formatTaipeiMonthDayTime, formatTradingDateMonthDay } from "./format";
import type { SummaryPositionItem } from "./types";

export interface ValuationBasis {
  /** `{M}`: number of positions that carry a price. */
  pricedCount: number;
  /** Earliest price date as `YYYY-MM-DD`. */
  earliest: string;
  /** Latest price date as `YYYY-MM-DD`. */
  latest: string;
}

// Anchored on both ends: a timestamp (intraday quote) must not be read as a
// closing date, so anything that is not a bare YYYY-MM-DD falls back to "no sentence".
const TRADING_DATE = /^(\d{4}-\d{2}-\d{2})$/;

/**
 * Counts positions with a price and finds the earliest and latest price
 * dates. Returns `null` (show no basis sentence) when no position has a
 * price, or when any priced position's `as_of` is not date-shaped: the date
 * is never guessed. `YYYY-MM-DD` strings sort chronologically as text, so
 * comparison never goes through `Date`.
 */
export function deriveValuationBasis(positions: readonly SummaryPositionItem[]): ValuationBasis | null {
  let pricedCount = 0;
  let earliest: string | null = null;
  let latest: string | null = null;
  for (const position of positions) {
    const price = position.valuation.price;
    if (price === null) continue;
    const match = TRADING_DATE.exec(price.as_of);
    if (match === null || match[1] === undefined) return null;
    const date = match[1];
    pricedCount += 1;
    if (earliest === null || date < earliest) earliest = date;
    if (latest === null || date > latest) latest = date;
  }
  if (pricedCount === 0 || earliest === null || latest === null) return null;
  return { pricedCount, earliest, latest };
}

/** C3-3 sentence: single-date version when all dates match, range version otherwise. */
export function buildBasisSentence(basis: ValuationBasis): string {
  const from = formatTradingDateMonthDay(basis.earliest);
  const to = formatTradingDateMonthDay(basis.latest);
  if (basis.earliest === basis.latest) {
    return fillIntradayTemplate(C3_3_BASIS_ALL_CLOSE_SINGLE, { M: basis.pricedCount, "MM/DD": from });
  }
  // The range template holds two `{MM/DD}`; `fillIntradayTemplate` would put
  // the same value in both, so fill the count first and then substitute the
  // two dates in order (earliest first).
  let index = 0;
  const dates = [from, to];
  const withCount = fillIntradayTemplate(C3_3_BASIS_ALL_CLOSE_RANGE, { M: basis.pricedCount });
  return withCount.replace(/\{MM\/DD\}/g, (whole: string) => {
    const value = dates[index];
    index += 1;
    return value ?? whole;
  });
}

/**
 * C5-1 tooltip: sentence 1 plus sentence 2. `{MM/DD}` is the Taipei calendar
 * day the page was computed (not a trading day). `null` when the response
 * timestamp is unusable: no tooltip is better than a half-filled one.
 */
export function buildBasisTooltip(generatedAtIso: string): string | null {
  const computed = formatTaipeiMonthDayTime(generatedAtIso);
  if (computed === null) return null;
  const sentence2 = fillIntradayTemplate(C5_1_TOOLTIP_SENTENCE_2, {
    "MM/DD": computed.monthDay,
    "HH:mm:ss": computed.time,
  });
  return `${C5_1_TOOLTIP_SENTENCE_1}${sentence2}`;
}
