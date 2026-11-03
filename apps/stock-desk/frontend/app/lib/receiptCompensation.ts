/**
 * Occlusion compensation for the receipt banner (visual spec r3.5a §4.2, PRD
 * FR-3 (i)-(v), AC-33, AC-68).
 *
 * The first scroll measures the sticky status bar as it is at that moment. When
 * the bar grows afterwards (the `/today` refetch turns normal into frozen, or
 * fast-market adds lines) it can cover the banner's first line. One compensating
 * scroll is allowed per receipt, at the "sync point": the first `/today` refetch
 * that ends after the receipt was shown, with the bar height unchanged for two
 * consecutive frames.
 *
 * Trigger choice: the refetch's end (an in-flight -> idle transition of the
 * `playbook-today` query, fed by the hook), not a ResizeObserver. A
 * ResizeObserver would also fire on later growth (background polling), which the
 * spec explicitly leaves uncovered; the refetch end is exactly the sync point.
 *
 * Framework-free on purpose: measurement, scrolling and frame scheduling are
 * injected so the whole truth table runs under plain Node.
 */

/** Compensation fires only below `barBottom + 12` (the V-9 lower bound). */
export const COMPENSATION_TRIGGER_GAP_PX = 12;
/** ...and moves the banner to `barBottom + 16`. 12 vs 16 is deliberate hysteresis (r3.5a), never unify. */
export const COMPENSATION_TARGET_GAP_PX = 16;
/** Give up waiting for two equal frames after this many frames and judge anyway. */
export const COMPENSATION_MAX_STABLE_WAIT_FRAMES = 60;

export interface CompensationInput {
  bannerTop: number;
  /** Bottom edge of the sticky bar; `null` when the bar is not mounted. */
  barBottom: number | null;
  userScrolled: boolean;
  quotaUsed: boolean;
}

/**
 * The truth table of the three conditions (+ "a bar exists"). Returns the
 * `scrollBy` delta (negative = up), or 0 for "do nothing". No safety valve here:
 * when the target is unreachable the browser clamps at `scrollY = 0` and the
 * verifier decides (r3.5a).
 */
export function receiptCompensationDelta(input: CompensationInput): number {
  if (input.quotaUsed || input.userScrolled) return 0;
  if (input.barBottom === null) return 0; // nothing sticky can cover the banner
  if (!(input.bannerTop < input.barBottom + COMPENSATION_TRIGGER_GAP_PX)) return 0;
  return input.bannerTop - (input.barBottom + COMPENSATION_TARGET_GAP_PX);
}

/** Keys that scroll the page; Space is included, as the spec lists it. */
const SCROLL_KEYS = new Set([
  "PageUp",
  "PageDown",
  "Home",
  "End",
  " ",
  "Spacebar",
  "ArrowUp",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
]);

export function isScrollKey(key: string): boolean {
  return SCROLL_KEYS.has(key);
}

export interface CompensationMeasure {
  bannerTop: number;
  barBottom: number | null;
  barHeight: number | null;
}

export interface CompensationDeps {
  measure: () => CompensationMeasure | null;
  scrollBy: (deltaY: number) => void;
  requestFrame: (cb: () => void) => number;
  cancelFrame: (handle: number) => void;
}

export interface CompensationController {
  /** A receipt was just scrolled to (or judged not to need it) by this page instance. */
  arm: (seq: number, refetchInFlight: boolean) => void;
  /** wheel / touchmove / scroll key. Counts only after `arm`. */
  userInput: () => void;
  /** The `/today` query's fetch status changed. */
  fetchingChanged: (inFlight: boolean) => void;
  dispose: () => void;
  /** Test/inspection only. */
  readonly state: {
    armedSeq: number | null;
    quotaUsed: boolean;
    userScrolled: boolean;
    phase: "idle" | "waiting" | "stabilizing" | "done";
  };
}

export function createReceiptCompensation(deps: CompensationDeps): CompensationController {
  const state: CompensationController["state"] = {
    armedSeq: null,
    quotaUsed: false,
    userScrolled: false,
    phase: "idle",
  };
  let sawFetching = false;
  let frame: number | null = null;

  function cancel() {
    if (frame !== null) deps.cancelFrame(frame);
    frame = null;
  }

  function judge() {
    state.phase = "done";
    const m = deps.measure();
    if (m === null) return;
    const delta = receiptCompensationDelta({
      bannerTop: m.bannerTop,
      barBottom: m.barBottom,
      userScrolled: state.userScrolled,
      quotaUsed: state.quotaUsed,
    });
    if (delta !== 0) {
      state.quotaUsed = true;
      deps.scrollBy(delta);
    }
  }

  function stabilize() {
    state.phase = "stabilizing";
    let previous: number | null | undefined;
    let waited = 0;
    const tick = () => {
      frame = null;
      const m = deps.measure();
      const height = m === null ? null : m.barHeight;
      waited += 1;
      if ((previous !== undefined && height === previous) || waited >= COMPENSATION_MAX_STABLE_WAIT_FRAMES) {
        judge();
        return;
      }
      previous = height;
      frame = deps.requestFrame(tick);
    };
    frame = deps.requestFrame(tick);
  }

  return {
    state,
    arm(seq, refetchInFlight) {
      if (state.armedSeq === seq) return; // idempotent (StrictMode re-run)
      cancel();
      state.armedSeq = seq;
      state.quotaUsed = false; // a new receipt has its own quota
      state.userScrolled = false;
      state.phase = "waiting";
      sawFetching = refetchInFlight;
    },
    userInput() {
      if (state.armedSeq !== null) state.userScrolled = true;
    },
    fetchingChanged(inFlight) {
      if (state.phase !== "waiting") return;
      if (inFlight) {
        sawFetching = true;
        return;
      }
      if (sawFetching) stabilize();
    },
    dispose() {
      cancel();
      state.phase = "done";
    },
  };
}
