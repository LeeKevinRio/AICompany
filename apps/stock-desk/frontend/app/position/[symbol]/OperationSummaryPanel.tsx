"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { AdviceResponse } from "../../lib/types";
import { buildOperationSummary } from "../../lib/operationSummary";
import { summaryConfidenceLabel } from "../../lib/adviceWording";
import { formatDateTime } from "../../lib/format";
import { SkeletonBlock } from "../../components/SkeletonBlock";
import { ErrorPanel } from "../../components/ErrorPanel";
import { InsufficientPanel } from "../../components/InsufficientPanel";
import { DataMetaStatusBadge } from "../../components/DataMetaStatusBadge";
import { buildFooterGuidance, buildFooterGuidanceForDataSource } from "../../lib/footerDisclosureWording";
import { OPERATION_SUMMARY_TITLE } from "../../lib/sectionTitles";
import { PAGE_LEVEL_DISCLOSURE_SECTION_TITLE } from "../../lib/sectionTaglines";
import { DETAILS_SUMMARY_OPERATION } from "../../lib/oneLinerWording";

/**
 * 一眼一句實作規格 §2.3（`work/stock-desk-一眼一句-實作規格.md`）：the
 * place-topping operation summary (FR-C1 AC-C1.1, FR-C6, FR-C7, FR-C8),
 * reshaped into the standard 主視圖／`<details>` 兩層 — the eight §2-required
 * elements still all travel with every rendered card (`buildOperationSummary`,
 * `app/lib/operationSummary.ts`), just split across the two layers per the
 *風控 R1–R10 最低常駐線 (see that spec's 附錄): only R1/R2/R3/R5/R10 stay in
 * the always-visible main view, the rest move into `<details>`.
 *
 * DRAFT WORDING NOTICE: every visible sentence here traces back to
 * `app/lib/adviceWording.ts`, itself pending risk-compliance-officer's
 * dedicated FR-C6/C7 wording review (see that file's header).
 */
export function OperationSummaryPanel({ advice }: { advice: UseQueryResult<AdviceResponse, Error> }) {
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">{OPERATION_SUMMARY_TITLE}</h2>
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
          <span className="flex flex-wrap items-center text-xs text-neutral-500">
            資料時間：{formatDateTime(advice.data.as_of)}｜來源：{advice.data.data.source}
            <DataMetaStatusBadge
              status={advice.data.data.status}
              stalenessMinutes={advice.data.data.staleness_minutes}
              isWithinTtl={advice.data.data.is_within_ttl}
              lastBarDate={advice.data.data.last_bar_date}
              reason={advice.data.data.reason}
            />
          </span>
        )}
      </div>

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

/**
 * Exported (only) so `operationSummary.test.ts` can render it directly via
 * `renderToStaticMarkup` for the R4/一眼一句 §2.3 "basis renders exactly
 * once" DOM assertion — every other caller should go through
 * `OperationSummaryPanel` above.
 */
export function SummaryBody({ response }: { response: AdviceResponse }) {
  const model = buildOperationSummary(response);

  // AC-C1.3 / AC-C7.4: no price at all anywhere in the three-tier ladder —
  // no card, no fabricated evaluation, reason shown as-is. D3③: when the
  // envelope still carries a bar date the calendar has moved past, its age is
  // disclosed here too (see `buildOperationSummary`), not only on cards.
  // 一眼一句 §2.3: unchanged besides the disclaimer's banner→inline text style.
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
        <InlineDisclaimer text={model.disclaimer} />
      </div>
    );
  }

  if (model.kind === "candidate") {
    const [firstCounterargument, ...restCounterarguments] = model.required.counterarguments;
    return (
      <div className="mt-3 space-y-4">
        {/* P1 結論位（風控替代路徑，CEO 2026-09-05）：結論標籤放大為 2xl，與信心 chip／說明句同列。 */}
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-block rounded-md border border-sky-800 bg-sky-950/40 px-4 py-2 text-2xl font-bold text-sky-300">
            {model.headingLabel}
          </span>
          <span className="text-sm text-neutral-400">
            信心等級：{summaryConfidenceLabel(model.required.confidence)}
          </span>
          {/* R10: the confidence chip and its meaning sentence stand or fall together, same row. */}
          <span className="text-xs text-neutral-400">{model.required.confidenceMeaning}</span>
        </div>

        {/*
          §2.1 required: the disclaimer must sit in the same visual region as
          the headline, never collapsed — rendered here as a standing text-xs
          line (風控核可，一眼一句 §2.3 第 3 點), not a bordered banner.
        */}
        <InlineDisclaimer text={model.required.disclaimer} />

        {model.supportive ? (
          <p className="text-sm text-neutral-200">
            {model.compositionText}
            <span className="font-semibold text-amber-300"> {model.supportiveDisclaimer}</span>
          </p>
        ) : (
          <p className="text-sm text-neutral-200">{model.notSupportiveText}</p>
        )}

        <QuantitySection shares={model.required.quantityRangeShares} absenceReason={model.required.quantityAbsenceReason} />

        {/*
          R2: `CANDIDATE_EVIDENCE_NOTICE` is rendered here, standing, once —
          `buildSummaryFooterItems` no longer duplicates it in the footer
          (operationSummary.ts).
        */}
        {model.required.candidateEvidenceNotice && (
          <p className="text-xs text-neutral-400">{model.required.candidateEvidenceNotice}</p>
        )}

        {/* R3: only the first counterargument stays standing; the rest move to <details>. */}
        {firstCounterargument && (
          <div>
            <h4 className="text-xs font-semibold text-neutral-400">反面論點</h4>
            <p className="mt-1 text-sm text-neutral-300">{firstCounterargument}</p>
          </div>
        )}

        <StaleDataAlert notice={model.staleDataNotice} />

        <details className="group mt-1">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm text-neutral-400 hover:text-neutral-300 [&::-webkit-details-marker]:hidden">
            <span
              aria-hidden="true"
              className="inline-block text-xs transition-transform duration-150 group-open:rotate-90"
            >
              ▸
            </span>
            {DETAILS_SUMMARY_OPERATION}
          </summary>
          <div className="mt-3 space-y-3 border-t border-neutral-800 pt-3 text-xs text-neutral-400">
            {model.quantityBasisNote && <p>{model.quantityBasisNote}</p>}
            {model.required.quantityRangeBasis && <p>{model.required.quantityRangeBasis}</p>}
            {restCounterarguments.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-neutral-400">反面論點</h4>
                <ul className="mt-1 list-disc space-y-1 pl-5">
                  {restCounterarguments.map((text, i) => (
                    <li key={i}>{text}</li>
                  ))}
                </ul>
              </div>
            )}
            {model.required.invalidationConditions.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-neutral-400">失效條件</h4>
                <ul className="mt-1 list-disc space-y-1 pl-5">
                  {model.required.invalidationConditions.map((text, i) => (
                    <li key={i}>{text}</li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-sm text-neutral-300">{buildFooterGuidance(OPERATION_SUMMARY_TITLE)}</p>
            <p className="text-sm text-neutral-300">
              {buildFooterGuidanceForDataSource(PAGE_LEVEL_DISCLOSURE_SECTION_TITLE)}
            </p>
          </div>
        </details>
      </div>
    );
  }

  // model.kind === "held"
  const [firstCounterargument, ...restCounterarguments] = model.required.counterarguments;
  // R4/FR-3: basis renders exactly once — as the alert when it is a
  // non-restoring defensive quantity range, otherwise tucked into `<details>`.
  const basisIsAlert = model.restoresComplianceWarning !== null;

  return (
    <div className="mt-3 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="inline-block rounded-md border border-neutral-700 bg-neutral-900 px-4 py-2 text-2xl font-bold text-neutral-100">
          {model.attributedHeadline}
        </span>
        <span className="text-sm text-neutral-400">
          信心等級：{summaryConfidenceLabel(model.required.confidence)}
        </span>
        {/* R10: the confidence chip and its meaning sentence stand or fall together, same row. */}
        <span className="text-xs text-neutral-400">{model.required.confidenceMeaning}</span>
      </div>

      <InlineDisclaimer text={model.required.disclaimer} />

      {/* AC-C6.1: the conclusion's main basis — the single heaviest matched rule. */}
      {model.topMatchedRule && (
        <p className="text-sm text-neutral-300">
          <span className="text-neutral-500">主要依據：</span>
          {model.topMatchedRule.name}——{model.topMatchedRule.explanation}
        </p>
      )}

      <QuantitySection shares={model.required.quantityRangeShares} absenceReason={model.required.quantityAbsenceReason} />

      {basisIsAlert && (
        <p
          role="alert"
          className="rounded-md border border-rose-800 bg-rose-950/50 px-4 py-3 text-sm font-semibold text-rose-300"
        >
          {model.restoresComplianceWarning}
        </p>
      )}

      {/* R3: only the first counterargument stays standing; the rest move to <details>. */}
      {firstCounterargument && (
        <div>
          <h4 className="text-xs font-semibold text-neutral-400">反面論點</h4>
          <p className="mt-1 text-sm text-neutral-300">{firstCounterargument}</p>
        </div>
      )}

      <StaleDataAlert notice={model.staleDataNotice} />

      <details className="group mt-1">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm text-neutral-400 hover:text-neutral-300 [&::-webkit-details-marker]:hidden">
          <span aria-hidden="true" className="inline-block text-xs transition-transform duration-150 group-open:rotate-90">
            ▸
          </span>
          {DETAILS_SUMMARY_OPERATION}
        </summary>
        <div className="mt-3 space-y-3 border-t border-neutral-800 pt-3 text-xs text-neutral-400">
          {!basisIsAlert && model.required.quantityRangeBasis && <p>{model.required.quantityRangeBasis}</p>}

          {restCounterarguments.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-neutral-400">反面論點</h4>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {restCounterarguments.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
            </div>
          )}

          {model.required.invalidationConditions.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-neutral-400">失效條件</h4>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {model.required.invalidationConditions.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
            </div>
          )}

          <p className="text-sm text-neutral-300">{buildFooterGuidance(OPERATION_SUMMARY_TITLE)}</p>
          <p className="text-sm text-neutral-300">
            {buildFooterGuidanceForDataSource(PAGE_LEVEL_DISCLOSURE_SECTION_TITLE)}
          </p>
        </div>
      </details>
    </div>
  );
}

/**
 * §2.1 required: the fixed disclaimer, now a standing `text-xs neutral-400`
 * line right beneath the headline (風控核可，一眼一句 §2.3 第 3 點) — never
 * `truncate`/`line-clamp`, replacing the old `DisclaimerBanner` bordered
 * style everywhere it was rendered (held／candidate／no_action alike).
 */
function InlineDisclaimer({ text }: { text: string }) {
  return <p className="text-xs text-neutral-400">{text}</p>;
}

/**
 * AC-C8.2's prominent data-age alert, in the one style every branch shares —
 * extracted (D3③) so the branches cannot drift apart on prominence. Renders
 * nothing when there is no stale gap to disclose.
 */
function StaleDataAlert({ notice }: { notice: string | null }) {
  if (notice === null) return null;
  return (
    <p role="alert" className="rounded-md border border-amber-700 bg-amber-950/40 px-3 py-2 text-amber-300">
      {notice}
    </p>
  );
}

/**
 * 一眼一句 §2.3 第 4 點: prints ONLY the share count ("{min} ~ {max} 股") —
 * the `basis` sentence that used to be bundled into the same string is now a
 * separate field the two branches above place exactly once (main-view alert
 * or `<details>`), never here.
 */
function QuantitySection({ shares, absenceReason }: { shares: string | null; absenceReason: string | null }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-neutral-200">建議股數區間</h3>
      {shares !== null ? (
        <p className="mt-1 text-sm text-neutral-300">{shares}</p>
      ) : (
        <p className="mt-1 text-sm text-neutral-500">{absenceReason}</p>
      )}
    </div>
  );
}
