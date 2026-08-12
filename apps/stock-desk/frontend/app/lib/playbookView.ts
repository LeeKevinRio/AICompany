/**
 * Pure rendering-decision logic for the `/playbook` (排程台) surface, split
 * out of the components so the visual-规范-mandated invariants below can be
 * asserted with a plain unit test, without a DOM — same pattern
 * `riskGauge.ts` already established for `RiskGauge.tsx`.
 *
 * WORDING RULE this whole module follows (派工單 2026-08-12): every
 * user-facing *sentence* on `/playbook` must come from a backend field
 * (`directive.line` / `rule_summary` / `mode_label` / `mode_reason` /
 * `warnings` / `attribution` / settlement's rendered strings / the
 * risk-compliance-approved EMERGENCY_EXIT button labels). Nothing in this
 * file composes new prose — it only maps enum/id values to Tailwind class
 * strings, sorts/splits/formats values the backend already sent, and runs
 * the exit-confirmation checkbox state machine. The one deliberate exception
 * (`EXIT_CONFIRM_FALLBACK_CHECKS`, three backend constants copied verbatim for
 * a degraded response) is documented at its own definition.
 */

import type {
  PlaybookDirectiveLine,
  PlaybookDirectiveStatus,
  PlaybookExitConfirm,
  PlaybookMode,
} from "./types";

/* --- 模式徽章 (視覺規範 §2) ------------------------------------------------ */

export interface ModeBadgeVisual {
  containerClass: string;
  dotClass: string;
}

/**
 * 視覺規範 §2.2 色值表, applied verbatim for the three modes it defines
 * (normal/defense/frozen). `emergency_frozen` and `unconfirmed` postdate that
 * table (added by wording.py's 三輪定稿 the same day) and have no assigned
 * colour there, so both are given a neutral, non-alarming treatment
 * consistent with §4.4's own ruling that a user-initiated freeze must not
 * read as "you did something wrong" (rose is reserved for a *rule-violation*
 * freeze, S3). `dotClass` varies the shape (circle/square-ish/none-radius/
 * ring/dashed-ring) as the non-colour half of the required "色彙 + icon +
 * 文字" triple encoding, since this app has no icon library — see 視覺規範
 * §2.1 "四態一律色彙 + icon + 文字三重編碼".
 */
const MODE_BADGE_VISUALS: Record<PlaybookMode, ModeBadgeVisual> = {
  normal: {
    containerClass: "border-neutral-800 bg-neutral-900 text-neutral-100",
    dotClass: "rounded-full bg-emerald-500",
  },
  defense: {
    containerClass: "border-amber-700 bg-amber-950/60 text-amber-200",
    dotClass: "rounded-sm bg-amber-400",
  },
  frozen: {
    containerClass: "border-rose-700 bg-rose-950/70 text-rose-200",
    dotClass: "rounded-none bg-rose-400",
  },
  emergency_frozen: {
    containerClass: "border-neutral-600 bg-neutral-900 text-neutral-200",
    dotClass: "rounded-full border border-neutral-400 bg-transparent",
  },
  unconfirmed: {
    containerClass: "border-neutral-600 bg-neutral-900 text-neutral-300",
    dotClass: "rounded-full border border-dashed border-neutral-400 bg-transparent",
  },
};

export function modeBadgeVisual(mode: PlaybookMode): ModeBadgeVisual {
  return MODE_BADGE_VISUALS[mode];
}

/** 視覺規範 §2.2 快市列, `indigo` — the one new hue the spec allows. */
export const FAST_MARKET_BADGE_CLASS = "border-indigo-700 bg-indigo-950/70 text-indigo-200";
export const FAST_MARKET_DOT_CLASS = "rotate-45 bg-indigo-400";

/* --- 規則家族色彙 (視覺規範 §3.4) ------------------------------------------ */

export type RuleFamily = "R" | "S" | "P" | "M1" | "OTHER";

/**
 * `OTHER` covers `IRON1` / `EMERGENCY` / `REBALANCE` — 視覺規範 §3.4's table
 * only defines the four R/S/P/M1 families; these three rule ids are real
 * (`app/playbook/models.py RuleId`) but outside that table, so they fall back
 * to a neutral border rather than guessing a colour the spec never assigned.
 *
 * Matched against the closed `R1`-`R4` / `S1`-`S3` / `P1`-`P3` sets, not a
 * `startsWith("R")` prefix check — `REBALANCE` also starts with `R` and would
 * otherwise be misclassified into the entry-rule family it has nothing to do
 * with (caught by this module's own test suite).
 */
const R_FAMILY_IDS = new Set(["R1", "R2", "R3", "R4"]);
const S_FAMILY_IDS = new Set(["S1", "S2", "S3"]);
const P_FAMILY_IDS = new Set(["P1", "P2", "P3"]);

export function ruleFamily(ruleId: string): RuleFamily {
  if (ruleId === "M1") return "M1";
  if (R_FAMILY_IDS.has(ruleId)) return "R";
  if (S_FAMILY_IDS.has(ruleId)) return "S";
  if (P_FAMILY_IDS.has(ruleId)) return "P";
  return "OTHER";
}

export interface RuleFamilyVisual {
  borderClass: string;
  chipClass: string;
}

const RULE_FAMILY_VISUALS: Record<RuleFamily, RuleFamilyVisual> = {
  R: {
    borderClass: "border-l-violet-600",
    chipClass: "border border-violet-700 text-violet-300 bg-violet-950/30",
  },
  S: {
    borderClass: "border-l-orange-600",
    chipClass: "border border-orange-700 text-orange-300 bg-orange-950/30",
  },
  P: {
    borderClass: "border-l-teal-600",
    chipClass: "border border-teal-700 text-teal-300 bg-teal-950/30",
  },
  M1: {
    borderClass: "border-l-amber-600",
    chipClass: "border border-amber-700 text-amber-300 bg-amber-950/30",
  },
  OTHER: {
    borderClass: "border-l-neutral-600",
    chipClass: "border border-neutral-700 text-neutral-300 bg-neutral-950/30",
  },
};

export function ruleFamilyVisual(ruleId: string): RuleFamilyVisual {
  return RULE_FAMILY_VISUALS[ruleFamily(ruleId)];
}

/* --- 帳冊列排序 (視覺規範 §3.5) -------------------------------------------- */

/**
 * 鐵律③ arbitration order restated by 視覺規範 §3.5: "M1 > S3 > S2 > S1 > P3 >
 * P1 > P2 > R". The spec leaves the R sub-order unstated (R1-R4 are one
 * bucket "R" at the bottom); `R1`-`R4` are listed individually here only so
 * the sort is a total order (stable, deterministic) without inventing a
 * priority the spec never gave. `IRON1`/`EMERGENCY`/`REBALANCE` are not part
 * of this arbitration list at all (they are not R/S/P/M1 rule-set entries)
 * and sort after every entry that is.
 */
const PRIORITY_ORDER: readonly string[] = [
  "M1",
  "S3",
  "S2",
  "S1",
  "P3",
  "P1",
  "P2",
  "R1",
  "R2",
  "R3",
  "R4",
];

export function directivePriorityIndex(ruleId: string): number {
  const index = PRIORITY_ORDER.indexOf(ruleId);
  return index === -1 ? PRIORITY_ORDER.length : index;
}

/** Priority first, then symbol (same tie-break 視覺規範 §3.5 names). */
export function sortDirectiveLines(
  lines: readonly PlaybookDirectiveLine[],
): PlaybookDirectiveLine[] {
  return [...lines].sort((a, b) => {
    const priorityDelta =
      directivePriorityIndex(a.directive.rule_id) - directivePriorityIndex(b.directive.rule_id);
    if (priorityDelta !== 0) return priorityDelta;
    return a.directive.symbol.localeCompare(b.directive.symbol);
  });
}

/* --- 一行式指令句拆解 ------------------------------------------------------ */

/**
 * Splits the backend-rendered `directive.line` on its `｜` field separator
 * (`wording.directive_line`, verified: `symbol batch｜action｜shares｜規則
 * {id}｜依據資料日 …｜預定執行日 …｜參考價 …`) into its seven segments, so the
 * ledger row can lay them out as separate always-visible lines per 視覺規範
 * §3.3's wireframe — without re-composing a single word of the sentence
 * itself. Returns the whole string as a single-element array if the
 * separator is not found (defensive; every real backend line has it).
 */
export function splitDirectiveLine(line: string): string[] {
  return line.split("｜");
}

/* --- 執行狀態徽章 ----------------------------------------------------------- */

/**
 * `pending`/`executed`/`missed` -> the exact vocabulary the backend already
 * uses in its own rendered sentences for this status
 * (`wording.SETTLEMENT_SUMMARY`: "成交 N 筆、未成交（MISSED）N 筆、未結算 N
 * 筆"; `wording.SETTLEMENT_NO_OPEN_PRICE`: "…維持待結算狀態") — mirrored here
 * as a per-directive badge label since no directive-level field carries a
 * pre-rendered status word of its own (`Directive.status` is the raw enum).
 */
const DIRECTIVE_STATUS_LABELS: Record<PlaybookDirectiveStatus, string> = {
  pending: "待結算",
  executed: "成交",
  missed: "未成交（MISSED）",
};

export function directiveStatusLabel(status: PlaybookDirectiveStatus): string {
  return DIRECTIVE_STATUS_LABELS[status];
}

/* --- 歸屬語 EMPTY 契約 ------------------------------------------------------ */

/** `attribution === null` (or empty) -> render nothing (EMPTY 契約, 派工單). */
export function shouldRenderAttribution(attribution: string | null): attribution is string {
  return attribution !== null && attribution.length > 0;
}

/* --- 數值格式化 ------------------------------------------------------------- */

/**
 * `BatchSnapshot.unrealized_pct` is a stringified `Decimal` **already scaled
 * to percent** (`"12.34"` means +12.34%), unlike `format.ts`'s
 * `formatPercent` (which expects a 0-1 fraction and multiplies by 100) — see
 * the field's doc comment in `types.ts`. A dedicated formatter avoids a
 * silent ×100 bug at the one call site that needs this shape.
 */
export function formatScaledPercent(value: string | null, decimals = 2): string {
  if (value === null) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n.toFixed(decimals)}%`;
}

/* --- EMERGENCY_EXIT 核取狀態機 (視覺規範 §4.3) ------------------------------ */

export function initialExitChecks(count: number): boolean[] {
  return new Array(count).fill(false);
}

export function toggleExitCheck(state: readonly boolean[], index: number): boolean[] {
  return state.map((value, i) => (i === index ? !value : value));
}

/** All checks ticked, and there is at least one to tick — 視覺規範 §4.3: "核取方塊全勾選才能點". */
export function allExitChecksConfirmed(state: readonly boolean[]): boolean {
  return state.length > 0 && state.every(Boolean);
}

/* --- EMERGENCY_EXIT Step 2 事實核取句 --------------------------------------- */

/**
 * The three approved checks that carry no number, copied verbatim from
 * `wording.EXIT_CONFIRM_CHECKS` (app/playbook/wording.py), used **only** when
 * `GET /today` came back without its `exit_confirm` block.
 *
 * The normal path renders `exit_confirm.checks` — the backend fills that block
 * on every service path (including 待確認規則集), with `freeze_days` read from
 * the rule parameters in force and 預計恢復日 counted on the trading calendar.
 * Mirroring those numbers here is exactly the defect this fallback replaces: a
 * client-side `20` is wrong the day the parameter moves, and this app has no
 * trading-calendar module that could count the recovery date (see
 * `tradingCalendar.ts`'s own documented gap).
 *
 * So the degraded branch drops the freeze sentence (index 1) instead of
 * rendering it with an invented number or a `—` where a date belongs, and
 * keeps the exit submittable on the remaining three checks — EX-2 出口零摩擦:
 * a missing field may not become a locked door. The freeze is still stated in
 * full, with its real numbers, in the post-submit response this same component
 * renders (`wording.EMERGENCY_EXIT_RESULT`/`EMERGENCY_EXIT_EMPTY` and
 * `mode_reason`), so the fact is disclosed even on this path — one step later
 * than intended, which is the deliberate trade-off recorded here.
 */
export const EXIT_CONFIRM_FALLBACK_CHECKS: readonly string[] = [
  "此操作將對目前持有的全部標的、全部批次送出出清指令；" +
    "不可只出清部分標的或部分批次，亦不可指定單一標的" +
    "（如需針對單一標的停損，請改用該標的的 S 系列規則）。",
  "凍結期間內，S／P 系列（停損／停利）仍照常評估；凍結期間仍可再次送出全部出清。",
  "本操作產生的是賣出指令，不是成交：T+1 開盤以市價單送出，跌停或無量時可能無法成交。",
];

/** Backend-rendered checks when the block is present, the fallback when not. */
export function exitConfirmChecks(exitConfirm: PlaybookExitConfirm | null): string[] {
  if (exitConfirm === null || exitConfirm.checks.length === 0) {
    return [...EXIT_CONFIRM_FALLBACK_CHECKS];
  }
  return [...exitConfirm.checks];
}
