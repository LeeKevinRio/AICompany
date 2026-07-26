import type { MeasureStatus } from "../lib/types";

/**
 * Generic "ok / insufficient_data" badge for the signals/leverage measurement
 * surfaces (app/signals/models.py `Status`, app/leverage/* `Status`) — the
 * DataStatusBadge sibling component covers the four-layer price ladder;
 * this one covers the two-state "could this be computed at all" ladder used
 * everywhere else in M7.
 */
export function MeasureStatusBadge({ status }: { status: MeasureStatus }) {
  if (status === "ok") return null;
  return (
    <span className="ml-1.5 inline-block rounded bg-amber-950/50 px-1.5 py-0.5 text-xs text-amber-300">
      資料不足
    </span>
  );
}
