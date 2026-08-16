/**
 * Pure transform from an `AdviceResponse` envelope to the shape the
 * operation-summary panel (FR-C1/FR-C6/FR-C7) renders. Kept separate from
 * the React component so the risk-mandated "eight required elements always
 * travel together" contract (`work/stock-desk-phase8-風控定調.md` §2) can be
 * asserted with a plain unit test, without a DOM.
 *
 * DRAFT WORDING NOTICE: strings composed here draw from `adviceWording.ts`,
 * itself marked draft-stage pending risk-compliance-officer's dedicated
 * FR-C6/C7 wording review — see that file's header.
 */

import type { AdviceCard, AdviceResponse, CardAction } from "./types";
import {
  AS_OF_DATE_UNKNOWN_FULL_STATEMENT,
  buildAsOfStatement,
  buildAttributedHeadline,
  buildCandidateCoverageStatement,
  buildCandidateSupportiveComposition,
  buildRulesStatement,
  buildStaleDataProminentNotice,
  CANDIDATE_CONFIDENCE_NOT_COMPARABLE_NOTE,
  CANDIDATE_EVIDENCE_NOTICE,
  CANDIDATE_HEADING_LABEL,
  CANDIDATE_NOT_SUPPORTIVE_TEXT,
  CANDIDATE_QUANTITY_BASIS_NOTE,
  CANDIDATE_SUPPORTIVE_DISCLAIMER,
  HELD_ACTION_LABELS,
  NON_REALTIME_NOTICE,
  QUANTITY_RANGE_ABSENCE_TEXT,
} from "./adviceWording";
import { isDataStaleByTradingDays } from "./tradingCalendar";

/**
 * The eight elements §2 of the wording brief requires on every rendered
 * card: `null` on a field means "not applicable to this card" (e.g. no
 * matched rule yet to quote a counterargument from), never "omitted by
 * mistake" — the panel renders every field it receives, so a missing one is
 * a builder bug, not a display choice.
 */
export interface RequiredElements {
  /** §2.1 */
  disclaimer: string;
  /** §2.2 */
  confidence: AdviceCard["confidence"];
  confidenceMeaning: string;
  /** §2.3 */
  asOfStatement: string;
  /** §2.4 */
  nonRealtimeNotice: string;
  /** §2.5 (full text, not a link) */
  counterarguments: string[];
  invalidationConditions: string[];
  /** §2.6 */
  rulesStatement: string;
  /** §2.7 — exactly one of the two is non-null */
  quantityRangeText: string | null;
  quantityAbsenceReason: string | null;
  /** §2.8 — candidate mode only */
  candidateEvidenceNotice: string | null;
}

export interface HeldSummary {
  kind: "held";
  attributedHeadline: string;
  action: CardAction;
  /** AC-C6.1: "該結論的主要依據（權重最高的命中規則一句話）" — `null` only when nothing matched. */
  topMatchedRule: { name: string; explanation: string } | null;
  restoresComplianceWarning: string | null;
  staleDataNotice: string | null;
  required: RequiredElements;
}

export interface CandidateSummary {
  kind: "candidate";
  headingLabel: typeof CANDIDATE_HEADING_LABEL;
  supportive: boolean;
  compositionText: string | null;
  supportiveDisclaimer: string | null;
  notSupportiveText: string | null;
  quantityBasisNote: string | null;
  coverageStatement: string;
  notComparableNote: string;
  staleDataNotice: string | null;
  required: RequiredElements;
}

export interface NoPriceSummary {
  kind: "no_price";
  reason: string;
  nonRealtimeNotice: string;
  /** D3③ (risk-fix-review.md N3 列管): see `buildOperationSummary`. */
  staleDataNotice: string | null;
}

export interface NoActionSummary {
  kind: "no_action";
  reason: string;
  disclaimer: string;
  nonRealtimeNotice: string;
  /** D3③ (risk-fix-review.md N3 列管): see `buildOperationSummary`. */
  staleDataNotice: string | null;
}

export type OperationSummaryModel = HeldSummary | CandidateSummary | NoPriceSummary | NoActionSummary;

const DEFENSIVE_ACTIONS: readonly CardAction[] = ["reduce", "stop_loss", "take_profit"];

/**
 * AC-C6.1's "權重最高的命中規則" — `matched_rules` is returned in rule-file
 * order, not weight order (see `build_advice` in `app/advice/engine.py`), so
 * the heaviest one has to be picked client-side. Ties keep the first one
 * encountered (stable, deterministic, matches the backend's own tie-break
 * convention of "first in file order" used elsewhere on the card).
 */
function pickTopMatchedRule(card: AdviceCard): { name: string; explanation: string } | null {
  if (card.matched_rules.length === 0) return null;
  const top = card.matched_rules.reduce((heaviest, rule) =>
    rule.weight > heaviest.weight ? rule : heaviest,
  );
  return { name: top.name, explanation: top.explanation };
}

/**
 * S5 fix (risk-final-review.md 列管項): picks the same date `buildAsOfStatement`
 * used to receive via `lastBarDate ?? card.observation_window.end ?? "—"`,
 * except that when both sources are `null` this returns the honest
 * `AS_OF_DATE_UNKNOWN_FULL_STATEMENT` instead of formatting the `"—"`
 * placeholder as if it were a date. Pure and unit-tested in isolation from the
 * rest of `buildRequiredElements` so the three branches (last-bar date,
 * observation-window fallback, both absent) each have a direct assertion.
 *
 * R-D5②-1 (2026-08-16): the unknown-date branch returns *both* approved
 * sentences as one string — the missing date also takes the 資料過舊 notice
 * down with it, and silence there reads as "the data is recent". Composed in
 * `adviceWording.ts` so this slot renders them together, in the same
 * `<p>` (`OperationSummaryPanel.tsx`'s `RequiredElementsFooter`), at the same
 * size and contrast, with nothing able to fold one of them away.
 */
export function resolveAsOfStatement(lastBarDate: string | null, observationEnd: string | null): string {
  const dateIso = lastBarDate ?? observationEnd;
  return dateIso === null ? AS_OF_DATE_UNKNOWN_FULL_STATEMENT : buildAsOfStatement(dateIso);
}

function buildRequiredElements(
  card: AdviceCard,
  candidate: boolean,
  lastBarDate: string | null,
): RequiredElements {
  const quantityRangeText =
    card.quantity_range === null
      ? null
      : `${card.quantity_range.min_shares.toLocaleString("zh-Hant-TW")} ~ ` +
        `${card.quantity_range.max_shares.toLocaleString("zh-Hant-TW")} 股。${card.quantity_range.basis}`;

  return {
    disclaimer: card.disclaimer,
    confidence: card.confidence,
    confidenceMeaning: card.confidence_meaning,
    // §2 item 3 / AC-C8.2: the literal YYYY-MM-DD trading date behind the
    // evaluation, NOT `card.as_of` (that is the latest bar's *retrieval*
    // timestamp, a full ISO 8601 datetime — see `app/signals/frame.py
    // ::provenance`). Under `cached_stale`/backup-source conditions the
    // retrieval time and the bar's own trading date can genuinely differ, so
    // this must come from `response.data.last_bar_date` (verified against
    // the same `DataMeta` the bars endpoint publishes), falling back to the
    // card's own `observation_window.end` only when the envelope carried no
    // `last_bar_date` at all.
    //
    // S5 fix (risk-final-review.md 列管項): when *neither* field is present,
    // this used to fall back to the placeholder `"—"` and hand it straight
    // to `buildAsOfStatement`, degrading the §2-mandatory as-of sentence
    // into an unreadable "本評估基於 —收盤資料。" instead of disclosing the
    // gap. `resolveAsOfStatement` below states that gap honestly instead.
    asOfStatement: resolveAsOfStatement(lastBarDate, card.observation_window.end),
    nonRealtimeNotice: NON_REALTIME_NOTICE,
    counterarguments: card.counterarguments,
    invalidationConditions: card.invalidation_conditions,
    rulesStatement: buildRulesStatement(card.rules_version),
    quantityRangeText,
    quantityAbsenceReason: quantityRangeText === null ? QUANTITY_RANGE_ABSENCE_TEXT : null,
    candidateEvidenceNotice: candidate ? CANDIDATE_EVIDENCE_NOTICE : null,
  };
}

export function buildOperationSummary(
  response: Pick<AdviceResponse, "status" | "reason" | "advice" | "held" | "data">,
): OperationSummaryModel {
  const lastBarDate = response.data.last_bar_date;
  // R4 fix (risk-final-review.md): this notice is about data *age*, not
  // source degradation — it must fire off how old `last_bar_date` is, not
  // off `data.status === "cached_stale"` (a same-day `cached_stale` read is
  // not stale). `cached_stale` itself continues to be surfaced separately
  // by `DataMetaStatusBadge`.
  //
  // C4 (2026-08-13): "how old" is now the backend's `trading_days_behind` —
  // sessions the market was observed to have had since `last_bar_date` —
  // replacing the B1 stop-gap that counted plain calendar days against a >10
  // buffer because no trading calendar reached the browser. The threshold is
  // back to one missed session, and the fail-safe is unchanged: an unmodelled
  // closure produces no sessions to count (no false alarm), and a `null` gap
  // means the calendar could not be consulted and nothing is claimed. See
  // `tradingCalendar.ts`'s header.
  //
  // D3③ (risk-fix-review.md N3 列管): computed ahead of *every* branch, so
  // the two insufficient_data outcomes carry it too. The old shape computed
  // it only after the no_price return and attached it only to held/candidate
  // cards, so an "insufficient data" screen built over week-old bars said
  // nothing about their age — the reader most in need of the age disclosure
  // was the one not shown it. The sentence itself is the risk-approved
  // `buildStaleDataProminentNotice`, reused verbatim; when the envelope has
  // no `last_bar_date`/`trading_days_behind` (the common no-data case) this
  // stays `null` and those screens render exactly as before.
  const tradingDaysBehind = response.data.trading_days_behind;
  const staleDataNotice =
    lastBarDate !== null && tradingDaysBehind !== null && isDataStaleByTradingDays(tradingDaysBehind)
      ? buildStaleDataProminentNotice(lastBarDate, tradingDaysBehind)
      : null;

  if (response.status === "insufficient_data" || response.advice === null) {
    return {
      kind: "no_price",
      reason: response.reason ?? "資料不足，無法計算。",
      nonRealtimeNotice: NON_REALTIME_NOTICE,
      staleDataNotice,
    };
  }

  const card = response.advice;

  if (card.action === "insufficient_data") {
    return {
      kind: "no_action",
      reason: HELD_ACTION_LABELS.insufficient_data,
      disclaimer: card.disclaimer,
      nonRealtimeNotice: NON_REALTIME_NOTICE,
      staleDataNotice,
    };
  }

  if (!response.held) {
    const supportive = card.action === "add";
    const constructiveCount = card.matched_rules.filter((rule) => rule.action === "add").length;
    return {
      kind: "candidate",
      headingLabel: CANDIDATE_HEADING_LABEL,
      supportive,
      compositionText: supportive ? buildCandidateSupportiveComposition(constructiveCount) : null,
      supportiveDisclaimer: supportive ? CANDIDATE_SUPPORTIVE_DISCLAIMER : null,
      notSupportiveText: supportive ? null : CANDIDATE_NOT_SUPPORTIVE_TEXT,
      quantityBasisNote: card.quantity_range === null ? null : CANDIDATE_QUANTITY_BASIS_NOTE,
      coverageStatement: buildCandidateCoverageStatement(
        card.evaluation.data_completeness,
        card.evaluation.skipped_rules.length,
      ),
      notComparableNote: CANDIDATE_CONFIDENCE_NOT_COMPARABLE_NOTE,
      staleDataNotice,
      required: buildRequiredElements(card, true, lastBarDate),
    };
  }

  const restoresComplianceWarning =
    card.quantity_range !== null &&
    !card.quantity_range.restores_compliance &&
    DEFENSIVE_ACTIONS.includes(card.action)
      ? card.quantity_range.basis
      : null;

  return {
    kind: "held",
    attributedHeadline: buildAttributedHeadline(card.action),
    action: card.action,
    topMatchedRule: pickTopMatchedRule(card),
    restoresComplianceWarning,
    staleDataNotice,
    required: buildRequiredElements(card, false, lastBarDate),
  };
}
