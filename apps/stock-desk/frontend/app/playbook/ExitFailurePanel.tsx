"use client";

import { useLayoutEffect, useRef } from "react";
import type { RefObject } from "react";
import { failureRevealDelta } from "../lib/exitFailureReveal";
import type { ExitFailureWording } from "../lib/playbookView";

/**
 * 出清失敗面板 (視覺規範 §11, PRD FR-8b): exit-only, so the shared red
 * `ErrorPanel` is neither used nor changed (AC-29). The label and the three
 * paragraphs are the 風控-signed text, passed in from the backend-mirrored
 * constants and rendered verbatim — one `<p>` each, in order, never merged, never
 * joined with `<br>`, nothing appended (no backend message, no HTTP status, no
 * exception text), for every failure kind (5xx, 4xx, network, unparsable body).
 *
 * Neutral grey on purpose: red would strengthen 「失敗 = 沒處理」, the opposite of
 * what the text says (it lists "not processed" and "accepted" side by side).
 * Structure, not hue, makes it stand out: its own border (`neutral-500`, two
 * steps brighter than the dialog's), a semibold label, `role="alert"`. No icon,
 * no animation, no close button, no `tabIndex` — focus stays on
 * 「確認送出全部出清」 (N-163), and the panel never receives it.
 *
 * Visibility (V-41): when the panel appears, its label is brought into the
 * dialog's scroll container's visible band by scrolling that container directly
 * (instant), never by focus and never by scroll anchoring. The panel is mounted
 * only while the failure stands and the dialog is on Step 3, so it re-appears —
 * and re-reveals — after an R-5 step back (V-40).
 */
export function ExitFailurePanel({
  wording,
  scrollContainerRef,
}: {
  wording: ExitFailureWording;
  /** The dialog's `overflow-y-auto` box. */
  scrollContainerRef: RefObject<HTMLDivElement | null>;
}) {
  const labelRef = useRef<HTMLParagraphElement>(null);

  useLayoutEffect(() => {
    const container = scrollContainerRef.current;
    const label = labelRef.current;
    if (container === null || label === null) return;
    const box = container.getBoundingClientRect();
    const line = label.getBoundingClientRect();
    const delta = failureRevealDelta({
      containerTop: box.top,
      containerBottom: box.bottom,
      labelTop: line.top,
      labelBottom: line.bottom,
    });
    if (delta !== 0) container.scrollTo({ top: container.scrollTop + delta, behavior: "auto" });
  }, [scrollContainerRef]);

  return (
    <div
      role="alert"
      className="mt-4 rounded-md border border-neutral-500 bg-neutral-900 px-4 py-3"
    >
      <p ref={labelRef} className="text-sm font-semibold text-neutral-100">
        {wording.label}
      </p>
      <p className="mt-2 text-sm text-neutral-300">{wording.body[0]}</p>
      <p className="mt-2 text-sm text-neutral-300">{wording.body[1]}</p>
      <p className="mt-2 text-sm text-neutral-300">{wording.body[2]}</p>
    </div>
  );
}
