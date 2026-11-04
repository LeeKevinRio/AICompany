/**
 * 視覺規範 V-41: when the 出清失敗面板 appears on Step 3, its label line must be
 * inside the dialog's visible area within one frame, without any user action and
 * without relying on the browser's scroll anchoring — and without moving focus
 * (focus stays on 「確認送出全部出清」, N-163).
 *
 * The page scrolls nothing here; only the dialog's own `overflow-y-auto`
 * container does (`behavior: "auto"` — instant). This is the pure part: how far
 * to scroll that container. Zero when the label is already fully visible, so a
 * tall viewport sees no scroll at all.
 */

export const FAILURE_REVEAL_MARGIN_PX = 16;

export interface RevealRects {
  /** Visible band of the scroll container (its client box in viewport coordinates). */
  readonly containerTop: number;
  readonly containerBottom: number;
  /** The label line's box in viewport coordinates. */
  readonly labelTop: number;
  readonly labelBottom: number;
}

/**
 * The amount to add to the container's `scrollTop` (positive = scroll down).
 * An out-of-view label is brought to the top of the visible band, so as much of
 * the panel's text as fits is visible below it.
 */
export function failureRevealDelta(rects: RevealRects): number {
  const visible =
    rects.labelTop >= rects.containerTop && rects.labelBottom <= rects.containerBottom;
  if (visible) return 0;
  return rects.labelTop - rects.containerTop - FAILURE_REVEAL_MARGIN_PX;
}
