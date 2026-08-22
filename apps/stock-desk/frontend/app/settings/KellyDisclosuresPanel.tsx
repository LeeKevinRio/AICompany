"use client";

/**
 * Renders every slot of `KellyDisclosuresView` (`GET
 * /api/kelly-inputs/{symbol}/disclosures`, `app/api/kelly.py`) verbatim.
 *
 * **This file renders no Chinese literal of its own.** Every sentence a user
 * reads from it is a field straight off the API response — 落地條件 3 / 約束
 * 21 (`work/reviews/2026-08-19-C5-Kelly-文案批審.md`): the front end judges
 * nothing about freshness, rewrites nothing, truncates nothing, and composes
 * no Chinese of its own. `app/lib/__tests__/kellyDisclosuresPanel.test.ts`
 * pins this with a source scan (every Han character outside a comment fails
 * the build), which is the mechanical form of the same rule `app/api/kelly.py`
 * follows on the server. Structural chrome (this component's own labels) is
 * therefore in English, not because Chinese chrome is unsafe in general (every
 * sibling settings section has some — `NetWorthSection.tsx`,
 * `KellyManualInputForm.tsx`), but because this is the one surface the whole
 * multi-round review was actually about, and the zero-literal property is
 * worth being able to check by machine rather than by re-reading the file.
 *
 * **條件 97** (第十輪): this endpoint's response never carries a (g) sentence
 * — cap 5 owns those five and ships them in its own `LimitCheck.detail`
 * (`LimitsCheckList.tsx`, position page, unchanged by this lane). A screen
 * that renders the `expired` badge without (g) beside it is exactly the
 * pairing the review forbids, and this settings screen has no (g) to show —
 * so the `expired` state of the badge is never rendered here at all (the
 * other three states — fresh/ageing/absent — render normally). This is the
 * "suppress the badge" branch of the two the K4c-2 task sheet named as an
 * open choice; see the frontend-engineer handoff report for the alternative
 * considered and why it was not taken.
 *
 * **條件 46/92 (原始值檢視)**: `tech-architect`'s 2026-08-22 ruling
 * (`work/stock-desk-C5-Kelly-條件46裁決.md`) requires the original-values view
 * and the effective-value disclosures to be **mutually exclusive in the DOM**,
 * never a `<details>/<summary>` reveal and never a `role="dialog"` overlay —
 * a plain toggle that swaps one subtree for the other, with the card header
 * (badge, source label) standing across both states and a standing "back"
 * control (never ESC/click-outside only). `KellyOriginalValuesView` is closed
 * at five fields since `38c6207` (第十三輪 required, 附註二/條件 92 二擇一): two
 * numbers, two labels, one sentence, no out-of-sample period — this component
 * renders exactly those five and nothing more.
 */

import { useState } from "react";
import type {
  KellyDetailRow,
  KellyFreshness,
  KellyInputDisclosuresView,
  KellyOriginalValuesView,
} from "../lib/types";

/**
 * 條件 97, pulled out as a pure function so the "no (g), so no `expired`
 * badge" rule has a unit test independent of rendering — this repo has no
 * `@testing-library/react`/jsdom yet (`vitest.config.ts`), so
 * `app/lib/__tests__/kellyDisclosuresPanel.test.ts` covers all four
 * `KellyFreshness | null` inputs (including the "no row at all" `null` case)
 * against this function directly.
 */
export function showsFreshnessBadge(freshness: KellyFreshness | null): boolean {
  return freshness !== "expired";
}

/**
 * 條件 46 約束 3: whether the original-values subtree renders, as a pure
 * predicate independent of the component's own `useState`. The interesting
 * property this makes checkable without a DOM: toggling `showOriginal` true
 * can never reveal the original-values view when the row does not have one
 * (`original === null`) — the JSX below renders exactly one of two mutually
 * exclusive branches keyed on this same expression, so this function and the
 * render branch cannot drift apart the way two independently-written
 * conditions could.
 */
export function shouldShowOriginalValues(
  showOriginal: boolean,
  original: KellyOriginalValuesView | null,
): boolean {
  return showOriginal && original !== null;
}

function DetailRow({ row }: { row: KellyDetailRow }) {
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-2 border-t border-neutral-800 py-1.5 first:border-t-0">
      <span className="text-neutral-400">{row.label}</span>
      {row.value !== null && <span className="text-neutral-100">{row.value}</span>}
      {row.note !== null && <span className="text-right text-neutral-400">{row.note}</span>}
    </li>
  );
}

export function KellyDisclosuresPanel({ data }: { data: KellyInputDisclosuresView }) {
  const [showOriginal, setShowOriginal] = useState(false);
  const disclosures = data.disclosures;
  const freshness = data.kelly_input?.freshness ?? null;
  const showBadge = showsFreshnessBadge(freshness);
  const original = disclosures.original_values;

  return (
    <div className="rounded-md border border-neutral-800 p-4">
      <div className="flex flex-wrap items-center gap-2">
        {showBadge && (
          <span className="rounded border border-neutral-700 bg-neutral-900 px-2 py-0.5 text-xs text-neutral-300">
            {disclosures.freshness_badge_label}
          </span>
        )}
        {disclosures.source_label !== null && (
          <span className="text-xs text-neutral-500">{disclosures.source_label}</span>
        )}
      </div>

      {shouldShowOriginalValues(showOriginal, original) && original !== null ? (
        <div className="mt-3 space-y-2 text-sm text-neutral-300">
          <p>{original.statement}</p>
          <dl className="grid grid-cols-1 gap-1 text-xs text-neutral-400 sm:grid-cols-2">
            <div className="flex gap-2">
              <dt>{original.win_rate_label}</dt>
              <dd className="text-neutral-200">{original.win_rate}</dd>
            </div>
            <div className="flex gap-2">
              <dt>{original.payoff_ratio_label}</dt>
              <dd className="text-neutral-200">{original.payoff_ratio}</dd>
            </div>
          </dl>
          {/* 條件 46 約束 5: a standing return control, never ESC/click-outside only. */}
          <button
            type="button"
            onClick={() => setShowOriginal(false)}
            className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-900"
          >
            Back
          </button>
        </div>
      ) : (
        <div className="mt-3 space-y-2 text-sm text-neutral-300">
          {disclosures.source_statement !== null && <p>{disclosures.source_statement}</p>}
          {disclosures.win_rate_disclosure !== null && <p>{disclosures.win_rate_disclosure}</p>}
          {disclosures.manual_input_disclosure !== null && (
            <p title={disclosures.manual_input_tooltip ?? undefined}>
              {disclosures.manual_input_disclosure}
            </p>
          )}
          {disclosures.selection_bias !== null && <p>{disclosures.selection_bias}</p>}
          {disclosures.walk_forward !== null && <p>{disclosures.walk_forward}</p>}

          {disclosures.f_star_interval !== null && disclosures.effective_cap !== null && (
            <div className="rounded-md border border-neutral-800 bg-neutral-950/40 p-3">
              <p>{disclosures.f_star_interval}</p>
              <p className="mt-1 flex justify-between text-xs text-neutral-400">
                <span>{disclosures.effective_cap.label}</span>
                <span className="text-neutral-200">{disclosures.effective_cap.value}</span>
              </p>
            </div>
          )}

          {disclosures.sample_detail !== null && (
            <div>
              <p>{disclosures.sample_detail.intro}</p>
              {disclosures.boundary_exclusion !== null && (
                <p className="mt-1 text-xs text-neutral-400">{disclosures.boundary_exclusion}</p>
              )}
              <ul className="mt-2 text-xs">
                {disclosures.sample_detail.rows.map((row) => (
                  <DetailRow key={row.label} row={row} />
                ))}
              </ul>
            </div>
          )}

          {original !== null && (
            <button
              type="button"
              onClick={() => setShowOriginal(true)}
              className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-900"
            >
              Original values
            </button>
          )}
        </div>
      )}
    </div>
  );
}
