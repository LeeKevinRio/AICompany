"use client";

import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { createReceiptCompensation, fetchStatusSignal, isScrollKey } from "../lib/receiptCompensation";
import type { CompensationController } from "../lib/receiptCompensation";

/**
 * Wires the occlusion compensation (lib/receiptCompensation.ts, spec §4.2) to the
 * page: it measures the banner and the sticky bar, listens for the user's own
 * scroll input, and reports when the `/today` fetch starts and ends. Returns the
 * controller (and a probe for an in-flight fetch); the scroll effect arms it after the first scroll of a receipt.
 */
export function useReceiptCompensation(
  bannerRef: RefObject<HTMLDivElement | null>,
  statusBarRef: RefObject<HTMLDivElement | null>,
  fetchStatus: "fetching" | "paused" | "idle",
): { controller: CompensationController; isFetchingNow: () => boolean } {
  const fetchingRef = useRef(false);
  const controllerRef = useRef<CompensationController | null>(null);
  if (controllerRef.current === null) {
    controllerRef.current = createReceiptCompensation({
      measure: () => {
        const banner = bannerRef.current;
        if (banner === null) return null;
        const bar = statusBarRef.current?.getBoundingClientRect() ?? null;
        return {
          bannerTop: banner.getBoundingClientRect().top,
          barBottom: bar === null ? null : bar.bottom,
          barHeight: bar === null ? null : bar.height,
        };
      },
      // `behavior: "auto"`: instant, never smooth. No focus is touched.
      scrollBy: (deltaY) => window.scrollBy({ top: deltaY, behavior: "auto" }),
      requestFrame: (cb) => window.requestAnimationFrame(cb),
      cancelFrame: (handle) => window.cancelAnimationFrame(handle),
    });
  }
  const controller = controllerRef.current;

  // Manual scrolling is detected from input events, never from a `scrollY`
  // difference (scroll anchoring moves `scrollY` by itself).
  useEffect(() => {
    const onInput = () => controller.userInput();
    const onKey = (event: KeyboardEvent) => {
      if (isScrollKey(event.key)) controller.userInput();
    };
    window.addEventListener("wheel", onInput, { passive: true });
    window.addEventListener("touchmove", onInput, { passive: true });
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("wheel", onInput);
      window.removeEventListener("touchmove", onInput);
      window.removeEventListener("keydown", onKey);
      controller.dispose();
    };
  }, [controller]);

  // Fed by the page from its own `/today` query (a hook-free module boundary: this
  // file opens no query observer).
  // Only "idle" ends a refetch; "paused" (offline) leaves the state untouched.
  const fetching = fetchStatusSignal(fetchStatus);
  useEffect(() => {
    if (fetching === null) return;
    fetchingRef.current = fetching;
    controller.fetchingChanged(fetching);
  }, [controller, fetching]);

  return {
    controller,
    /** Whether a `/today` fetch is already in flight (read when arming). */
    isFetchingNow: () => fetchingRef.current,
  };
}
