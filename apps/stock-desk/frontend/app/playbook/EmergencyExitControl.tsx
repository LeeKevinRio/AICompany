"use client";

import { useState } from "react";
import { ErrorPanel } from "../components/ErrorPanel";
import { useEmergencyExit } from "../lib/queries";
import {
  allExitChecksConfirmed,
  exitConfirmChecks,
  initialExitChecks,
  shouldRenderAttribution,
  toggleExitCheck,
} from "../lib/playbookView";
import type { PlaybookExitConfirm } from "../lib/types";

type ExitStep = "idle" | "confirm" | "final";

/**
 * EMERGENCY_EXIT control (視覺規範 §4). Button styling is deliberately
 * ordinary — 中性色階, no rose/red, no icon, no animation (§4.2: "成本來自流程
 * 摩擦，不是來自視覺恐嚇") — and the cost lives entirely in the 3-step flow
 * below (§4.3): Step 1 is this button; Step 2 is the fact-checklist modal
 * (`confirm`), which requires every checkbox ticked before advancing; Step 3
 * (`final`) is the second confirmation that actually calls
 * `POST /emergency-exit`. No checkbox is pre-ticked and there is no countdown
 * anywhere in this flow (EX-2 / 出口零摩擦, wording.py's own doc comment on
 * `EXIT_CONFIRM_CHECKS`).
 *
 * Every sentence in the modal is backend-sourced or a risk-compliance
 * pre-approved literal: the Step 2 checks are `today.exit_confirm.checks`,
 * rendered exactly as `wording.exit_confirm_checks` produced them — including
 * the freeze length and 預計恢復日, which are the day's rule parameter and a
 * trading-calendar count, never mirrored here (see `exitConfirmChecks` for the
 * degraded branch when the block is absent). The four button labels are the
 * pre-approved literals the hand-off task named verbatim: 全部出清／我已閱讀，
 * 繼續／確認送出全部出清／取消.
 */
export function EmergencyExitControl({
  exitConfirm,
}: {
  exitConfirm: PlaybookExitConfirm | null;
}) {
  const checkTexts = exitConfirmChecks(exitConfirm);
  const [step, setStep] = useState<ExitStep>("idle");
  const [checks, setChecks] = useState<boolean[]>(() => initialExitChecks(checkTexts.length));
  const mutation = useEmergencyExit();

  // The checklist length only changes when a refetch swaps the degraded
  // fallback for the real block (3 checks <-> 4). Re-seeding keeps a tick
  // bound to the sentence it was given for: a box ticked against a sentence
  // that is no longer on screen may not carry over into the submission.
  if (checks.length !== checkTexts.length) {
    setChecks(initialExitChecks(checkTexts.length));
  }

  function openConfirm() {
    mutation.reset();
    setChecks(initialExitChecks(checkTexts.length));
    setStep("confirm");
  }

  function cancel() {
    setStep("idle");
    setChecks(initialExitChecks(checkTexts.length));
  }

  function submit() {
    mutation.mutate(undefined, {
      onSuccess: () => setStep("idle"),
    });
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <button
        type="button"
        onClick={openConfirm}
        className="rounded-md border border-neutral-600 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800"
      >
        全部出清
      </button>

      {step !== "idle" && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="全部出清確認"
          className="fixed inset-0 z-20 flex items-center justify-center bg-black/70 p-4"
        >
          <div className="w-full max-w-lg rounded-md border border-neutral-700 bg-neutral-950 p-5">
            {step === "confirm" && (
              <>
                {/* 視覺規範 §4.3 逐字引用（Step 2 標頭）。 */}
                <h2 className="text-lg font-semibold text-neutral-100">
                  全部出清 — 確認前請閱讀以下事實
                </h2>
                <ul className="mt-4 space-y-3">
                  {checkTexts.map((text, index) => (
                    <li key={index} className="flex items-start gap-2">
                      <input
                        id={`exit-check-${index}`}
                        type="checkbox"
                        checked={checks[index] === true}
                        onChange={() => setChecks((prev) => toggleExitCheck(prev, index))}
                        className="mt-1"
                      />
                      <label htmlFor={`exit-check-${index}`} className="text-sm text-neutral-300">
                        {text}
                      </label>
                    </li>
                  ))}
                </ul>
                <div className="mt-5 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={cancel}
                    className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    disabled={!allExitChecksConfirmed(checks)}
                    onClick={() => setStep("final")}
                    className="rounded-md border border-neutral-500 bg-neutral-800 px-3 py-1.5 text-sm text-neutral-100 hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    我已閱讀，繼續
                  </button>
                </div>
              </>
            )}

            {step === "final" && (
              <>
                <h2 className="text-lg font-semibold text-neutral-100">全部出清 — 二次確認</h2>
                {/* 排程台頁面審查 (suggested): Step 3 的覆述是二次確認前最後
                    一次讀到這些事實，對比度不低於 neutral-300。 */}
                <ul className="mt-4 space-y-2 text-sm text-neutral-300">
                  {checkTexts.map((text, index) => (
                    <li key={index}>{text}</li>
                  ))}
                </ul>
                {mutation.isError && (
                  <div className="mt-3">
                    <ErrorPanel label="全部出清送出失敗" error={mutation.error} />
                  </div>
                )}
                <div className="mt-5 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={cancel}
                    disabled={mutation.isPending}
                    className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800 disabled:opacity-50"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    onClick={submit}
                    disabled={mutation.isPending}
                    className="rounded-md border border-neutral-500 bg-neutral-800 px-3 py-1.5 text-sm text-neutral-100 hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {mutation.isPending ? "送出中…" : "確認送出全部出清"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/*
        視覺規範 §4.4 執行後狀態: 中性色階橫幅，非 rose. The message/mode_reason
        below are `wording.EMERGENCY_EXIT_RESULT`/`EMERGENCY_EXIT_EMPTY` and
        `wording.mode_reason_emergency`, both server-rendered verbatim.
      */}
      {mutation.isSuccess && (
        <div className="max-w-sm rounded-md border border-neutral-700 bg-neutral-900 p-4 text-sm text-neutral-200">
          <p>{mutation.data.message}</p>
          <p className="mt-1 text-neutral-300">{mutation.data.mode_reason}</p>
          {shouldRenderAttribution(mutation.data.attribution) && (
            <p className="mt-1 text-neutral-400">{mutation.data.attribution}</p>
          )}
          {mutation.data.warnings.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-neutral-400">
              {mutation.data.warnings.map((warning, i) => (
                <li key={i}>{warning}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
