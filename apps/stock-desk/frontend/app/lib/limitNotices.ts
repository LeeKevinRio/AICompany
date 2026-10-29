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
 * Cap 5 (`kelly_fraction`) and these lists — 風控 2026-10-26
 * `第1條上限下修審查` D-4, which revises C-5 for the Kelly sunset (plan D):
 * - 2-V / 2-M / 2-R exclude cap 5 **by its status**, never by its id. During
 *   the sunset cap 5 can still be `violated` and still blocks an add
 *   (`engine.py`'s blocked notice names it), so it is listed like any other
 *   cap; once 5-K reports it as `disabled`, it drops out on its own because
 *   only `violated` checks enter these lists. Batch two must keep it that way
 *   and not reintroduce an id filter here.
 * - 2-O keeps excluding cap 5 by id in both periods: its inputs are frozen, so
 *   「無法評估」 there leaves the user nothing to act on.
 */

/** The limit id 2-O keeps out of its count (C-5, D-4). 風控 2026-10-26 定稿；失效條件 T1 */
const NOT_EVALUABLE_EXCLUDED_LIMIT_ID = "kelly_fraction";

/**
 * Held actions on which the 2-R sentence may appear: `hold` only. add, reduce, take_profit, stop_loss and
 * insufficient_data never show it (on the sell side the sentence is empty or clashes with the quantity range).
 * 風控 2026-10-26 裁定修訂 C-6；失效條件 T1、T9
 */
const NOTICE_ACTIONS: readonly CardAction[] = ["hold"];

export interface LimitNotices {
  /** 2-M title; null when there are 0 or 1 violated limits (1 uses 2-V, which has no title). */
  violationTitle: string | null;
  /** One line for 2-V, one per limit for 2-M, empty when nothing is violated. */
  violationLines: string[];
  /** The backend's own blocked-add sentences, verbatim; held only, empty otherwise. */
  blockedNotices: string[];
  /** 2-R; null unless every C-6 condition holds. */
  actionNotice: string | null;
  /** 2-O; null when no limit other than cap 5 is not_evaluable. */
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
  // D-4: by status only; a disabled cap (5-K) is never `violated`.
  const violated = card.limits_check.filter((limit) => limit.status === "violated");
  const notEvaluable = card.limits_check.filter(
    (limit) => limit.id !== NOT_EVALUABLE_EXCLUDED_LIMIT_ID && limit.status === "not_evaluable",
  );

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
