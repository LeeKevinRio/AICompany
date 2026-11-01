"use client";

import { useLayoutEffect } from "react";
import type { RefObject } from "react";
import { consumeTriggerMount, recordTriggerUnmount } from "../lib/exitFocus";

/**
 * The 「全部出清」 trigger: appearance only (視覺規範 §4.2). Button styling is
 * deliberately ordinary — 中性色階, no rose/red, no icon, no animation ("成本來自
 * 流程摩擦，不是來自視覺恐嚇") — and the cost lives in the 3-step dialog.
 *
 * It owns no flow state. `PlaybookPage` renders it in exactly one of two places
 * chosen by the same `today.isSuccess` expression that gates `ModeStatusBar`
 * (sticky bar when the bar is mounted, the h1 row otherwise — 視覺規範 §10,
 * 方案 B), so one trigger exists in every frame (FE-C12, V-29). Both placements
 * share one `buttonRef` object, so the page can always focus whichever is
 * mounted. The label is the pre-approved literal and nothing is attached to it:
 * no `aria-label`, `title`, `aria-describedby`, `disabled` or `aria-disabled`
 * (風控 F-4, EX-2).
 *
 * Focus hand-off (FE-C20): a `/today` transition unmounts one trigger and mounts
 * the other in a single commit. If the old one held focus when it was removed
 * and focus has fallen to `<body>`, the new one takes it (`preventScroll`, so a
 * receipt scrolled into view stays put). See `shouldHandOffFocus` for the three
 * conditions; it never pulls focus away from anything the user picked.
 */
export function ExitTriggerButton({
  buttonRef,
  focusLostRef,
  dialogOpen,
  onOpen,
}: {
  buttonRef: RefObject<HTMLButtonElement | null>;
  /** Shared across both placements: set by an unmounting trigger that held focus. */
  focusLostRef: RefObject<boolean>;
  dialogOpen: boolean;
  onOpen: () => void;
}) {
  useLayoutEffect(() => {
    const node = buttonRef.current;
    const active = document.activeElement;
    // Consumes the flag whether or not it hands off (FE-8(a)); one call, no retry (FE-8(b)).
    if (
      consumeTriggerMount(focusLostRef, {
        dialogOpen,
        activeIsBodyOrNull: active === null || active === document.body,
      })
    ) {
      node?.focus({ preventScroll: true });
    }
    return () => {
      // Runs when this trigger is removed, while the node is still in the DOM;
      // always overwrites the flag with the truth at this moment.
      recordTriggerUnmount(focusLostRef, node !== null && document.activeElement === node);
    };
    // Mount / unmount only: the effect describes the lifetime of one placement.
  }, []);

  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={onOpen}
      className="rounded-md border border-neutral-600 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800"
    >
      全部出清
    </button>
  );
}
