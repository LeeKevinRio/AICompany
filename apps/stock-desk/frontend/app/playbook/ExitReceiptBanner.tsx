import type { RefObject } from "react";
import { shouldRenderAttribution } from "../lib/playbookView";
import type { PlaybookEmergencyExitResponse } from "../lib/types";

/**
 * 受理回執 (視覺規範 §2、§4.4 執行後狀態): a neutral-grey banner, never rose
 * (R13 — the exit is the user's own choice, not an error). `message`,
 * `mode_reason`, `attribution` and `warnings` are server-rendered verbatim
 * (`wording.EMERGENCY_EXIT_RESULT` / `EMERGENCY_EXIT_ALREADY_PENDING` /
 * `EMERGENCY_EXIT_EMPTY`, `wording.mode_reason_emergency`, `EXIT_ATTRIBUTION*`)
 * and stay in this one container in this order (風控 必改項 6); the
 * attribution is never split out.
 *
 * Rendered from the Providers-scope receipt store, not from the mutation (VETO-1),
 * and *outside* the `today.isSuccess` gate, inside the always-present
 * `role="status"` container (FR-7a). `showModeReason` is false only when the
 * status bar is mounted and already shows the identical sentence; the paragraph
 * is then not rendered at all — no CSS hiding, no `sr-only` copy, no reserved
 * height (風控 必改項 5).
 *
 * No close button, no collapse, no `max-h` / `overflow` / `line-clamp`: the
 * whole text is readable without interaction (AC-5, AC-9). `scroll-mt-*` is the
 * offset `scrollIntoView` honours so the first line clears the sticky bar.
 */
export function ExitReceiptBanner({
  response,
  showModeReason,
  bannerRef,
}: {
  response: PlaybookEmergencyExitResponse;
  showModeReason: boolean;
  bannerRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      ref={bannerRef}
      className="mt-4 w-full scroll-mt-40 rounded-md border border-neutral-600 bg-neutral-900 p-4 text-sm text-neutral-200 lg:scroll-mt-32"
    >
      <p>{response.message}</p>
      {showModeReason && <p className="mt-1 text-neutral-300">{response.mode_reason}</p>}
      {shouldRenderAttribution(response.attribution) && (
        <p className="mt-1 text-neutral-400">{response.attribution}</p>
      )}
      {response.warnings.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-neutral-400">
          {response.warnings.map((warning, i) => (
            <li key={i}>{warning}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
