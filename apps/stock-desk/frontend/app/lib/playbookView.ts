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
  PlaybookFastMarketState,
  PlaybookMode,
  PlaybookTodayResponse,
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

/**
 * 排程台頁面審查 required ④ (fail-closed): with no 歸屬語 the directive ledger
 * is not rendered at all.
 *
 * 風控 R2 makes the 常駐歸屬語 a condition of showing instruction-shaped copy,
 * not a decoration on it — an instruction the user reads without being told
 * whose judgement it is is exactly the misattribution the whole exemption rests
 * on avoiding. The backend fills `attribution` on every service path (including
 * 待確認規則集, where it is the blocking sentence), so a `null` here means the
 * response was degraded, and the safe reading of a degraded response is to show
 * fewer instructions rather than unattributed ones.
 *
 * Nothing is invented in its place: this module may not compose the sentence
 * that would explain the gap, and there is no approved backend one for it. The
 * 部位快照 / 結算 blocks are unaffected — they are not 指令.
 */
export function shouldRenderDirectiveLedger(attribution: string | null): boolean {
  return shouldRenderAttribution(attribution);
}

/* --- 空帳冊：未命中 vs 未評估 (四輪收斂裁決 題 12) -------------------------- */

/**
 * The sentence an empty ledger gets, or `null` to keep the bare 「無。」.
 *
 * Fail-closed on three counts, all of them required by the ruling:
 *
 * 1. The backend completeness flag has to be **exactly** `true`. An older
 *    backend sends neither field, and `undefined` is not `true`.
 * 2. The sentence itself has to have arrived. This module does not hold a copy
 *    of it: 「今日規則已全數評估」 is a claim about an evaluation this code did
 *    not run, so only the evaluator may make it.
 * 3. 凍結／緊急出清後凍結／待確認規則集 never get it, even if a future backend
 *    were to set the flag on such a day (裁決: 凍結／未確認模式不疊加). Those
 *    modes already carry their own sentence saying what is suspended, and
 *    stacking 「已全數評估」 on top of 「R 系列不執行」 would read as a denial of
 *    the very suspension above it.
 */
const MODES_WITHOUT_NO_HIT_NOTE: readonly PlaybookMode[] = [
  "frozen",
  "emergency_frozen",
  "unconfirmed",
];

export function noDirectiveNote(today: PlaybookTodayResponse): string | null {
  if (today.rules_fully_evaluated !== true) return null;
  if (MODES_WITHOUT_NO_HIT_NOTE.includes(today.mode)) return null;
  const note = today.no_directive_note;
  return note !== null && note !== undefined && note.length > 0 ? note : null;
}

/* --- 快市徽章的沿用說明 ----------------------------------------------------- */

/**
 * The sentence to render next to an `active` 快市 badge that has no `reason`
 * (排程台頁面審查 required): a carried-forward verdict was not measured today,
 * so it has no measurement sentence, and a badge that says 「快市」 with nothing
 * next to it leaves the reader to guess what it was based on.
 *
 * Returns `null` whenever the badge is off or the measurement sentence is
 * present (that one is already rendered), and whenever the backend sent no
 * carried explanation — this module has none of its own to fall back on.
 */
export function fastMarketAdjacentNote(fastMarket: PlaybookFastMarketState): string | null {
  if (!fastMarket.active) return null;
  if (fastMarket.reason !== null && fastMarket.reason.length > 0) return null;
  const note = fastMarket.carried_note;
  return note !== null && note !== undefined && note.length > 0 ? note : null;
}

/**
 * `warnings` minus the one sentence that is being rendered next to the badge.
 *
 * The backend puts the carried-forward explanation in both places on purpose
 * (`FastMarketState.carried_note` and `warnings`). It is *moved*, never
 * dropped: the filter only removes an exact string equality with the note this
 * page is already showing, and only when it is showing it — pass `null` and
 * every warning comes back untouched. No truncation, no substring matching, no
 * list of sentences this module decides are uninteresting.
 */
export function visibleWarnings(
  warnings: readonly string[],
  adjacentNote: string | null,
): string[] {
  if (adjacentNote === null) return [...warnings];
  return warnings.filter((warning) => warning !== adjacentNote);
}

/* --- 確認規則集／資本設定入口 ---------------------------------------------- */

/**
 * Whether to offer the 確認規則集 block: only in the one state it resolves.
 *
 * `unconfirmed` is the backend's own mode for 歸屬語情境 1 (風控 R2) — no
 * authorship record, so `GET /today` produces no rule-driven directive and says
 * so in `attribution`/`mode_reason`. The block is the action that lifts exactly
 * that block, so it is not shown on any other day: on a 正常／防守／凍結 day the
 * rule set is already the user's, and a confirmation control there would invite
 * a re-submission that changes nothing.
 */
export function shouldRenderRuleSetConfirm(mode: PlaybookMode): boolean {
  return mode === "unconfirmed";
}

/** Digits with at most one decimal point — no sign, no exponent, no separator. */
const CAPITAL_PATTERN = /^\d+(\.\d+)?$/;

/**
 * The capital string to submit, or `null` when the field does not hold one.
 *
 * Kept as a **string** end to end: the backend field is a `Decimal` and a
 * round-trip through a JS number is exactly the precision loss the project's
 * money convention exists to avoid. Thousands separators and spaces a user
 * typed are removed; everything else (a sign, an exponent, a second decimal
 * point, full-width digits, an empty field) is rejected rather than coerced,
 * so an unreadable field never becomes a number nobody typed.
 *
 * `null` disables the submit button. The backend refuses a non-positive capital
 * with a 422 regardless — this check is the same rule stated early, not the
 * only place it is enforced.
 */
export function normalizeCapitalInput(raw: string): string | null {
  const cleaned = raw.replace(/[\s,]/g, "");
  if (!CAPITAL_PATTERN.test(cleaned)) return null;
  return Number(cleaned) > 0 ? cleaned : null;
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
 * The four approved checks for a degraded response, copied verbatim from
 * `app/playbook/wording.py` — three from `EXIT_CONFIRM_CHECKS` (the ones that
 * carry no number) plus `EXIT_CONFIRM_FREEZE_DEGRADED` in place of check 2.
 * Used **only** when `GET /today` came back without its `exit_confirm` block.
 *
 * The normal path renders `exit_confirm.checks` — the backend fills that block
 * on every service path (including 待確認規則集), with `freeze_days` read from
 * the rule parameters in force and 預計恢復日 counted on the trading calendar.
 * Mirroring those numbers here is exactly the defect this fallback replaces: a
 * client-side `20` is wrong the day the parameter moves, and this app has no
 * trading-calendar module that could count the recovery date (see
 * `tradingCalendar.ts`'s own documented gap).
 *
 * So the degraded branch keeps the *fact* of the freeze and drops only its two
 * numbers, saying they could not be obtained and where they do appear — the
 * risk-compliance replacement (四輪收斂裁決) for the earlier behaviour of
 * dropping the sentence outright, which disclosed the freeze one step too late.
 * Neither an invented number nor a `—` where a date belongs is ever rendered,
 * and the exit stays submittable on all four checks: a missing field may not
 * become a locked door (EX-2 出口零摩擦). The numbers themselves are in the
 * post-submit response this same component renders
 * (`wording.EMERGENCY_EXIT_RESULT`/`EMERGENCY_EXIT_EMPTY` and `mode_reason`,
 * all three pinned backend-side as carrying the day count).
 */
export const EXIT_CONFIRM_FALLBACK_CHECKS: readonly string[] = [
  "此操作將對目前持有的全部標的、全部批次送出出清指令；" +
    "不可只出清部分標的或部分批次，亦不可指定單一標的" +
    "（如需針對單一標的停損，請改用該標的的 S 系列規則）。",
  "送出後，R 系列（新倉進場）暫停；本次未能取得暫停交易日數與預計恢復日，" +
    "兩者於送出後的執行結果中顯示。",
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
