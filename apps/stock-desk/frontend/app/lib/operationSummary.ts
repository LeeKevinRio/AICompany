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
  buildAsOfStatement,
  buildAttributedHeadline,
  buildCandidateCoverageStatement,
  buildCandidateSupportiveComposition,
  buildRulesStatement,
  CANDIDATE_CONFIDENCE_NOT_COMPARABLE_NOTE,
  CANDIDATE_EVIDENCE_NOTICE,
  CANDIDATE_HEADING_LABEL,
  CANDIDATE_NOT_SUPPORTIVE_TEXT,
  CANDIDATE_QUANTITY_BASIS_NOTE,
  CANDIDATE_SUPPORTIVE_DISCLAIMER,
  HELD_ACTION_LABELS,
  NON_REALTIME_NOTICE,
  QUANTITY_RANGE_ABSENCE_TEXT,
  STALE_DATA_PROMINENT_NOTICE,
} from "./adviceWording";

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
}

export interface NoActionSummary {
  kind: "no_action";
  reason: string;
  disclaimer: string;
  nonRealtimeNotice: string;
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

function buildRequiredElements(card: AdviceCard, candidate: boolean): RequiredElements {
  const quantityRangeText =
    card.quantity_range === null
      ? null
      : `${card.quantity_range.min_shares.toLocaleString("zh-Hant-TW")} ~ ` +
        `${card.quantity_range.max_shares.toLocaleString("zh-Hant-TW")} 股。${card.quantity_range.basis}`;

  return {
    disclaimer: card.disclaimer,
    confidence: card.confidence,
    confidenceMeaning: card.confidence_meaning,
    asOfStatement: buildAsOfStatement(card.as_of ?? card.observation_window.end ?? "—"),
    nonRealtimeNotice: NON_REALTIME_NOTICE,
    counterarguments: card.counterarguments,
    invalidationConditions: card.invalidation_conditions,
    rulesStatement: buildRulesStatement(card.rules_version),
    quantityRangeText,
    quantityAbsenceReason: quantityRangeText === null ? QUANTITY_RANGE_ABSENCE_TEXT : null,
    candidateEvidenceNotice: candidate ? CANDIDATE_EVIDENCE_NOTICE : null,
  };
}

/**
 * `dateFromDataMeta` should be the underlying bars' `last_bar_date`
 * (`AdviceResponse.data.last_bar_date`) — the actual trading date behind the
 * evaluation — not `advice.as_of`, which is a retrieval timestamp (see
 * `app/signals/frame.py::provenance`). Falls back to the card's own
 * `observation_window.end` when the envelope did not carry one.
 */
export function buildOperationSummary(
  response: Pick<AdviceResponse, "status" | "reason" | "advice" | "held" | "data">,
): OperationSummaryModel {
  if (response.status === "insufficient_data" || response.advice === null) {
    return {
      kind: "no_price",
      reason: response.reason ?? "資料不足，無法計算。",
      nonRealtimeNotice: NON_REALTIME_NOTICE,
    };
  }

  const card = response.advice;
  const staleDataNotice = response.data.status === "cached_stale" ? STALE_DATA_PROMINENT_NOTICE : null;

  if (card.action === "insufficient_data") {
    return {
      kind: "no_action",
      reason: HELD_ACTION_LABELS.insufficient_data,
      disclaimer: card.disclaimer,
      nonRealtimeNotice: NON_REALTIME_NOTICE,
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
      required: buildRequiredElements(card, true),
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
    required: buildRequiredElements(card, false),
  };
}
