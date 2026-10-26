import { HELD_ACTION_LABELS } from "./adviceWording";
import { formatPercent } from "./format";
import {
  buildLimitsDoNotChangeActionNotice,
  buildMultiViolationLine,
  buildMultiViolationTitle,
  buildNotEvaluableLimitsNotice,
  buildSingleViolationLine,
} from "./riskRemediationWording";
import type { AdviceCard, CardAction, LimitCheck } from "./types";

/**
 * View model for the decision card's limit block (risk remediation items 2-V,
 * 2-M, 2-R, 2-O and the lifted blocked-add sentence; constraints C-5, C-6).
 *
 * Pure: no React, no side effects, so every display condition is unit-tested
 * without a DOM. 風控 2026-10-26 定稿；失效條件 T1、T9.
 *
 * Cap 5 (`kelly_fraction`) is excluded from every list here (C-5). The Kelly
 * disablement itself (5-K) is a separate change and is not part of this one.
 */

/** The limit id that C-5 keeps out of the violation / not-evaluable lists. 風控 2026-10-26 定稿；失效條件 T1 */
const EXCLUDED_LIMIT_ID = "kelly_fraction";

/** Held actions on which the 2-R sentence may appear (C-6); `add` and `insufficient_data` never do. 風控 2026-10-26 定稿；失效條件 T1、T9 */
const NOTICE_ACTIONS: readonly CardAction[] = ["hold", "reduce", "take_profit", "stop_loss"];

export interface LimitNotices {
  /** 2-M title; null when there are 0 or 1 violated limits (1 uses 2-V, which has no title). */
  violationTitle: string | null;
  /** One line for 2-V, one per limit for 2-M, empty when nothing is violated. */
  violationLines: string[];
  /** The backend's own blocked-add sentences, verbatim; held only, empty otherwise. */
  blockedNotices: string[];
  /** 2-R; null unless every C-6 condition holds. */
  actionNotice: string | null;
  /** 2-O; null when no (non-excluded) limit is not_evaluable. */
  notEvaluableNotice: string | null;
  /** True when anything above is non-empty (the caller renders nothing otherwise). */
  hasAny: boolean;
}

/** The limit's name without its trailing 「上限」 (C-5: short name). */
export function limitShortName(name: string): string {
  return name.replace(/上限$/, "");
}

function describe(limit: LimitCheck): {
  index: number;
  shortName: string;
  observed: string | null;
  threshold: string | null;
} {
  const complete = limit.observed !== null && limit.threshold !== null;
  return {
    index: limit.index,
    shortName: limitShortName(limit.name),
    observed: complete ? formatPercent(limit.observed) : null,
    threshold: complete ? formatPercent(limit.threshold) : null,
  };
}

export function buildLimitNotices(
  card: AdviceCard,
  kind: "held" | "candidate",
): LimitNotices {
  const considered = card.limits_check.filter((limit) => limit.id !== EXCLUDED_LIMIT_ID);
  const violated = considered.filter((limit) => limit.status === "violated");
  const notEvaluable = considered.filter((limit) => limit.status === "not_evaluable");

  let violationTitle: string | null = null;
  let violationLines: string[] = [];
  if (violated.length === 1) {
    const only = describe(violated[0]!);
    violationLines = [buildSingleViolationLine(only.index, only.shortName, only.observed, only.threshold)];
  } else if (violated.length >= 2) {
    violationTitle = buildMultiViolationTitle(violated.length);
    violationLines = violated.map((limit) => {
      const d = describe(limit);
      return buildMultiViolationLine(d.index, d.shortName, d.observed, d.threshold);
    });
  }

  const blockedNotices = kind === "held" ? [...card.blocked_notices] : [];

  const actionNotice =
    kind === "held" && violated.length > 0 && NOTICE_ACTIONS.includes(card.action)
      ? buildLimitsDoNotChangeActionNotice(HELD_ACTION_LABELS[card.action])
      : null;

  const notEvaluableNotice =
    notEvaluable.length > 0
      ? buildNotEvaluableLimitsNotice(notEvaluable.length, violated.length > 0)
      : null;

  return {
    violationTitle,
    violationLines,
    blockedNotices,
    actionNotice,
    notEvaluableNotice,
    hasAny:
      violationLines.length > 0 ||
      blockedNotices.length > 0 ||
      actionNotice !== null ||
      notEvaluableNotice !== null,
  };
}
