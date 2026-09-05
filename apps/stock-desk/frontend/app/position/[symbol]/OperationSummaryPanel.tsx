"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { AdviceResponse } from "../../lib/types";
import { buildOperationSummary } from "../../lib/operationSummary";
import { summaryConfidenceLabel } from "../../lib/adviceWording";
import { formatDateTime } from "../../lib/format";
import { SkeletonBlock } from "../../components/SkeletonBlock";
import { OPERATION_SUMMARY_TAGLINE } from "../../lib/sectionTaglines";
import { ErrorPanel } from "../../components/ErrorPanel";
import { InsufficientPanel } from "../../components/InsufficientPanel";
import { DataMetaStatusBadge } from "../../components/DataMetaStatusBadge";

/**
 * The place-topping operation summary (FR-C1 AC-C1.1, FR-C6, FR-C7, FR-C8).
 * Renders whatever `buildOperationSummary` (`app/lib/operationSummary.ts`)
 * derives from the same `useAdvice` payload the advice-card section further
 * down the page already fetches — no new endpoint, no new query. See that
 * module's doc comment for why the eight §2-required elements are modelled
 * as one always-populated object rather than left to ad-hoc JSX branches.
 *
 * DRAFT WORDING NOTICE: every visible sentence here traces back to
 * `app/lib/adviceWording.ts`, itself pending risk-compliance-officer's
 * dedicated FR-C6/C7 wording review (see that file's header).
 */
export function OperationSummaryPanel({ advice }: { advice: UseQueryResult<AdviceResponse, Error> }) {
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">操作摘要</h2>
        {/*
          FR-C8(a) / qa-e2e A2-8: every section badges its own data
          provenance independently (same mechanism as the technical-analysis
          `<h3>` rows in `page.tsx`) — never one shared, page-level stamp
          that lets stale data ride along under a fresher section's badge.
          `advice.data` (the envelope's own `DataMeta`) is used rather than
          falling back to the sibling `useBars` query's meta: `advice.py`
          builds this envelope from its own `load_bars` call (same loader,
          same lookback window as `/api/bars`, but a genuinely separate HTTP
          round trip), so it can legitimately land on a different rung of
          the fresh/backup/cached_stale ladder than the bars section at the
          same instant — this section must report *its own* provenance, not
          borrow the bars section's, or a real divergence would be hidden.
          `advice.data.data` is always populated regardless of whether a
          card exists (see `app/api/advice.py`'s `insufficient_data` branch,
          which still returns `data=data_meta(loaded.meta())`), so this is
          gated on `advice.isSuccess` alone, not on a card being present.
        */}
        {advice.isSuccess && (
          <span className="flex items-center text-xs text-neutral-500">
            資料時間：{formatDateTime(advice.data.as_of)}｜來源：{advice.data.data.source}
            <DataMetaStatusBadge
              status={advice.data.data.status}
              stalenessMinutes={advice.data.data.staleness_minutes}
              isWithinTtl={advice.data.data.is_within_ttl}
            />
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-neutral-300">{OPERATION_SUMMARY_TAGLINE}</p>

      {advice.isPending && <SkeletonBlock className="mt-3 h-40 w-full" />}
      {advice.isError && (
        <div className="mt-3">
          <ErrorPanel label="無法載入操作摘要" error={advice.error} />
        </div>
      )}
      {advice.isSuccess && <SummaryBody response={advice.data} />}
    </section>
  );
}

function SummaryBody({ response }: { response: AdviceResponse }) {
  const model = buildOperationSummary(response);

  // AC-C1.3 / AC-C7.4: no price at all anywhere in the three-tier ladder —
  // no card, no fabricated evaluation, reason shown as-is. D3③: when the
  // envelope still carries a bar date the calendar has moved past, its age is
  // disclosed here too (see `buildOperationSummary`), not only on cards.
  if (model.kind === "no_price") {
    return (
      <div className="mt-3 space-y-3">
        <InsufficientPanel reason={model.reason} />
        <StaleDataAlert notice={model.staleDataNotice} />
      </div>
    );
  }

  // AC-C6.5: the engine itself said `insufficient_data` — no action word, no
  // range, no reference figure of any kind. D3③ applies here as well.
  if (model.kind === "no_action") {
    return (
      <div className="mt-3 space-y-3">
        <InsufficientPanel reason={model.reason} />
        <StaleDataAlert notice={model.staleDataNotice} />
        <DisclaimerBanner text={model.disclaimer} />
      </div>
    );
  }

  if (model.kind === "candidate") {
    return (
      <div className="mt-3 space-y-4">
        {/* P1 結論位（風控替代路徑，CEO 2026-09-05）：結論標籤放大為 2xl，與免責同區、同進同退（R3）。 */}
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-block rounded-md border border-sky-800 bg-sky-950/40 px-4 py-2 text-2xl font-bold text-sky-300">
            {model.headingLabel}
          </span>
          <span className="text-sm text-neutral-400">
            信心等級：{summaryConfidenceLabel(model.required.confidence)}
          </span>
        </div>
        {/* §2.2 required: kept in the same eye-span as the confidence badge above, not moved to the meta footer. */}
        <p className="-mt-2 text-xs text-neutral-500">{model.required.confidenceMeaning}</p>

        {/*
          §2.1 required: the disclaimer must sit in the same visual region as
          the headline, never collapsed, never smaller than this block's own
          body text — rendered here (not tucked into the meta footer below)
          precisely so top-pinning the summary cannot visually demote it.
        */}
        <DisclaimerBanner text={model.required.disclaimer} />

        {/* §2.8 candidate-mode evidence-limit notice: always on, never behind a toggle. */}
        <p
          role="note"
          className="rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-300"
        >
          {model.required.candidateEvidenceNotice}
        </p>

        {model.supportive ? (
          <p className="text-sm text-neutral-200">
            {model.compositionText}
            <span className="font-semibold text-amber-300"> {model.supportiveDisclaimer}</span>
          </p>
        ) : (
          <p className="text-sm text-neutral-200">{model.notSupportiveText}</p>
        )}

        {/* §3.3 required: coverage ratio + skipped-rule count, not just prose. */}
        <p className="text-xs text-neutral-500">{model.coverageStatement}</p>
        {/* §3.4: confidence not comparable across held/candidate modes. */}
        <p className="text-xs text-neutral-500">{model.notComparableNote}</p>

        <QuantitySection
          text={model.required.quantityRangeText}
          absenceReason={model.required.quantityAbsenceReason}
          basisNote={model.quantityBasisNote}
        />

        <RequiredElementsFooter required={model.required} staleDataNotice={model.staleDataNotice} />
      </div>
    );
  }

  // model.kind === "held"
  return (
    <div className="mt-3 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="inline-block rounded-md border border-neutral-700 bg-neutral-900 px-4 py-2 text-2xl font-bold text-neutral-100">
          {model.attributedHeadline}
        </span>
        <span className="text-sm text-neutral-400">
          信心等級：{summaryConfidenceLabel(model.required.confidence)}
        </span>
      </div>
      {/* §2.2 required: kept in the same eye-span as the confidence badge above, not moved to the meta footer. */}
      <p className="-mt-2 text-xs text-neutral-500">{model.required.confidenceMeaning}</p>

      <DisclaimerBanner text={model.required.disclaimer} />

      {/* AC-C6.1: the conclusion's main basis — the single heaviest matched rule. */}
      {model.topMatchedRule && (
        <p className="text-sm text-neutral-300">
          <span className="text-neutral-500">主要依據：</span>
          {model.topMatchedRule.name}——{model.topMatchedRule.explanation}
        </p>
      )}

      <QuantitySection
        text={model.required.quantityRangeText}
        absenceReason={model.required.quantityAbsenceReason}
        basisNote={null}
      />

      {model.restoresComplianceWarning && (
        <p
          role="alert"
          className="rounded-md border border-rose-800 bg-rose-950/50 px-4 py-3 text-sm font-semibold text-rose-300"
        >
          {model.restoresComplianceWarning}
        </p>
      )}

      <RequiredElementsFooter required={model.required} staleDataNotice={model.staleDataNotice} />
    </div>
  );
}

/**
 * §2.1 required: the fixed disclaimer, always rendered at (at least) the
 * block's own body text size — never the smaller "meta" size used for
 * source/timestamp captions elsewhere on this page — and never collapsible.
 */
function DisclaimerBanner({ text }: { text: string }) {
  return (
    <p className="rounded-md border border-neutral-700 bg-neutral-900/80 px-3 py-2 text-sm text-neutral-200">
      {text}
    </p>
  );
}

/**
 * AC-C8.2's prominent data-age alert, in the one style every branch shares —
 * extracted (D3③) so the two insufficient_data branches and
 * `RequiredElementsFooter` cannot drift apart on prominence. Renders nothing
 * when there is no stale gap to disclose.
 */
function StaleDataAlert({ notice }: { notice: string | null }) {
  if (notice === null) return null;
  return (
    <p role="alert" className="rounded-md border border-amber-700 bg-amber-950/40 px-3 py-2 text-amber-300">
      {notice}
    </p>
  );
}

function QuantitySection({
  text,
  absenceReason,
  basisNote,
}: {
  text: string | null;
  absenceReason: string | null;
  basisNote: string | null;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-neutral-200">建議股數區間</h3>
      {text !== null ? (
        <div className="mt-1 text-sm text-neutral-300">
          <p>{text}</p>
          {basisNote && <p className="mt-1 text-xs text-neutral-500">{basisNote}</p>}
        </div>
      ) : (
        <p className="mt-1 text-sm text-neutral-500">{absenceReason}</p>
      )}
    </div>
  );
}

/**
 * Renders §2 items 3/4/5/6 together, in one always-visible block. Item 1
 * (disclaimer) and item 2 (confidence meaning) are rendered separately, right
 * beside the headline/confidence badge above (see the call sites above), so
 * top-pinning the summary cannot visually demote or separate them from what
 * they qualify. Never behind a `<details>`: §2.5 explicitly bars hiding
 * counterarguments/invalidation conditions behind an "expand" link.
 */
function RequiredElementsFooter({
  required,
  staleDataNotice,
}: {
  required: import("../../lib/operationSummary").RequiredElements;
  staleDataNotice: string | null;
}) {
  return (
    <div className="space-y-3 border-t border-neutral-800 pt-4 text-sm">
      <StaleDataAlert notice={staleDataNotice} />

      <p className="text-neutral-300">{required.asOfStatement}</p>

      {required.counterarguments.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-neutral-400">反面論點</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-neutral-400">
            {required.counterarguments.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        </div>
      )}

      {required.invalidationConditions.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-neutral-400">失效條件</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-neutral-400">
            {required.invalidationConditions.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-xs text-neutral-500">{required.rulesStatement}</p>
    </div>
  );
}
