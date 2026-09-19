import type { ConditionId, ConditionResult, EntryObservation } from "../../lib/entryObservation";
import {
  ENTRY_CONDITION_LABELS,
  ENTRY_CONDITION_THRESHOLDS,
  ENTRY_E1_QUALIFIER,
  ENTRY_E2_XREF,
  ENTRY_E3_DASH_NOTE,
  ENTRY_NO_DATA_STATEMENT,
  ENTRY_PANEL_TITLE,
  ENTRY_STATUS_LABELS,
  buildConditionCount,
  buildDataTimesLine,
  buildDefensiveHitsText,
  buildRangeConditionLabel,
} from "../../lib/entryObservationWording";
import { buildFooterGuidance } from "../../lib/footerDisclosureWording";
import { formatDateTime } from "../../lib/format";
import { DETAILS_SUMMARY_ENTRY } from "../../lib/oneLinerWording";

/**
 * 六條固定觀察條件面板 (CEO 需求 2026-09-06; PRD `work/stock-desk-進場觀察條件-PRD.md`
 * §4b, 風控預審 R-01～R-22 落地):
 * - R-04/R-07: all six rows always visible, fixed order, observed value beside
 *   each verdict; the six dots are 1:1 with the rows, same size, each aria-read.
 * - R-05/R-06/R-08: the count is a sentence only (no N/6, no %, no score), the
 *   all-met case has NO special state (no branch on metCount anywhere in the
 *   markup), and the count never exceeds text-lg.
 * - R-21: status carries no hue — glyph (●○—) + word + aria, neutral greys only.
 * - E-1～E-4 render inside the panel (NOT covered by the 2026-09-06 footer
 *   rulings); CEO 第二次裁定 2026-09-19（`work/stock-desk-一眼一句簡化-派工單.md`
 *   §4）moved all four, plus the data-times line, into `<details>` — the
 *   main view keeps only the h2, the count sentence and the six dots.
 * - R-15: nothing from the advice headline / confidence / disclaimer is imported.
 * Every user-facing string is a pinned constant in `entryObservationWording.ts`.
 */

const STATUS_GLYPH: Record<ConditionResult["status"], string> = { met: "●", unmet: "○", unavailable: "—" };

/** Neutral only (R-21): met = brighter grey, unmet = mid grey, unavailable = mid grey; no hue anywhere. */
const STATUS_TEXT_CLASS: Record<ConditionResult["status"], string> = {
  met: "text-neutral-100",
  unmet: "text-neutral-400",
  unavailable: "text-neutral-400",
};

function fmtNum(n: number | null, digits = 2): string {
  if (n === null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("zh-TW", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtSignedPct(n: number | null): string {
  if (n === null || !Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

/** The observed value(s) printed beside each verdict (R-04). */
function observedText(c: ConditionResult): string {
  if (c.status === "unavailable") return "—";
  switch (c.id) {
    case "range":
      return `${(c.observed ?? 0).toFixed(0)}%`;
    case "trend":
      return `${fmtNum(c.observed)} vs ${fmtNum(c.reference)}`;
    case "pullback":
      return fmtSignedPct(c.observed);
    case "momentum":
      return fmtNum(c.observed, 1);
    case "volume":
      return fmtNum(c.observed, 2);
    case "rules":
      return buildDefensiveHitsText(c.observed ?? 0);
  }
}

function conditionLabel(id: ConditionId, rangeBarCount: number | null): string {
  if (id === "range") return buildRangeConditionLabel(rangeBarCount);
  return ENTRY_CONDITION_LABELS[id];
}

export function EntryObservationPanel({
  observation,
  rangeBarCount,
  dataTimes,
}: {
  observation: EntryObservation;
  /** `KeyLevels.rangeBarCount` when bars are loaded (R-14: the row prints the real bar count). */
  rangeBarCount: number | null;
  /** E-4: the three queries' own as_of stamps (bars / signals / advice), null when not loaded. */
  dataTimes: { bars: string | null; signals: string | null; advice: string | null };
}) {
  const times = {
    bars: dataTimes.bars ? formatDateTime(dataTimes.bars) : null,
    signals: dataTimes.signals ? formatDateTime(dataTimes.signals) : null,
    advice: dataTimes.advice ? formatDateTime(dataTimes.advice) : null,
  };
  // 風控 REQ-3: 「同步」 is decided on the RAW ISO stamps, never on the minute-rounded display strings.
  const synchronized =
    dataTimes.bars !== null && dataTimes.bars === dataTimes.signals && dataTimes.signals === dataTimes.advice;

  return (
    <section className="mt-6 rounded-lg border border-neutral-800 p-4" aria-label={ENTRY_PANEL_TITLE}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">{ENTRY_PANEL_TITLE}</h2>
        {!observation.allUnavailable && (
          // R-08: never larger than text-lg; R-05: a sentence, not a fraction.
          <p className="text-base font-semibold text-neutral-100">
            {buildConditionCount(observation.metCount, observation.unavailableCount)}
          </p>
        )}
      </div>
      {/* 風控 REQ-1: the six rows are always listed (all 「—」 when nothing is loaded) so E-1's 「以上六條門檻」 always has its referent; only the count is withheld. */}
      {observation.allUnavailable && <p className="mt-3 text-sm text-neutral-300">{ENTRY_NO_DATA_STATEMENT}</p>}
      {/* R-07: six dots, 1:1 with the rows below, same order, same size. Decorative here (S-4): a screen reader gets the full readable text from the detailed list in `<details>`. */}
      <ul className="mt-3 flex gap-2" aria-hidden="true">
        {observation.conditions.map((c) => (
          <li
            key={c.id}
            className={`flex h-6 w-6 items-center justify-center rounded-md border border-neutral-700 bg-neutral-900 text-sm ${STATUS_TEXT_CLASS[c.status]}`}
          >
            {STATUS_GLYPH[c.status]}
          </li>
        ))}
      </ul>

      {/*
        CEO 第二次裁定 2026-09-19（`work/stock-desk-一眼一句簡化-派工單.md`
        §4）：E-1 與資料時間句一律收進 `<details>`，字面不動——主視圖只留
        h2＋計數句＋六圓點。
      */}

      <details className="group mt-3">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm text-neutral-400 hover:text-neutral-300 [&::-webkit-details-marker]:hidden">
          <span aria-hidden="true" className="inline-block text-xs transition-transform duration-150 group-open:rotate-90">
            ▸
          </span>
          {DETAILS_SUMMARY_ENTRY}
        </summary>
        <div className="mt-3 space-y-3 border-t border-neutral-800 pt-3 text-xs text-neutral-400">
          <p>{ENTRY_E1_QUALIFIER}</p>
          <ul className="divide-y divide-neutral-800/60 rounded-md border border-neutral-800 bg-neutral-900/40">
            {observation.conditions.map((c) => (
              <li
                key={c.id}
                aria-label={`${conditionLabel(c.id, rangeBarCount)}：${observedText(c)}，${ENTRY_STATUS_LABELS[c.status]}`}
                className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-3 py-2 text-sm"
              >
                {/* Left: glyph + data-item name + threshold; right: observed value + status word. Groups wrap as units on narrow screens. */}
                <span className="flex items-center gap-2">
                  <span aria-hidden="true" className={`w-4 text-center ${STATUS_TEXT_CLASS[c.status]}`}>
                    {STATUS_GLYPH[c.status]}
                  </span>
                  <span className="text-neutral-200">{conditionLabel(c.id, rangeBarCount)}</span>
                  <span className="text-neutral-400">{ENTRY_CONDITION_THRESHOLDS[c.id]}</span>
                </span>
                <span className="ml-auto flex items-center gap-3">
                  <span className="font-mono tabular-nums text-neutral-200">{observedText(c)}</span>
                  <span className={`w-16 text-right ${STATUS_TEXT_CLASS[c.status]}`}>{ENTRY_STATUS_LABELS[c.status]}</span>
                </span>
              </li>
            ))}
          </ul>
          <p>{ENTRY_E2_XREF}</p>
          <p>{ENTRY_E3_DASH_NOTE}</p>
          <p>{buildDataTimesLine(times.bars, times.signals, times.advice, synchronized)}</p>
          <p className="text-sm text-neutral-300">{buildFooterGuidance(ENTRY_PANEL_TITLE)}</p>
        </div>
      </details>
    </section>
  );
}

