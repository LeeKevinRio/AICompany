"use client";

import { alertTypeLabel, formatDateTime } from "../lib/format";
import type { AlertEvent } from "../lib/types";

/** Renders `AlertEvent.observed` (a `Record<string, number|string|null>`, verified shape). */
function ObservedValues({ observed }: { observed: Record<string, number | string | null> }) {
  const entries = Object.entries(observed);
  if (entries.length === 0) return null;
  return (
    <p className="mt-1 text-xs text-neutral-500">
      {entries.map(([key, value]) => `${key}: ${value ?? "—"}`).join("　")}
    </p>
  );
}

export interface AlertEventListProps {
  events: AlertEvent[];
  onAck: (id: number) => void;
  ackPending: boolean;
}

/**
 * The event-list markup previously rendered inline by the full
 * `PendingAlertsPanel` component. That full panel has retired from the home
 * page (首頁「一眼一句」簡化，`work/stock-desk-一眼一句-實作規格.md` §3.3 —
 * it always rendered a half-width card even with zero rules/events, which is
 * exactly the "旁邊待處理警示長期為空、看起來很怪" CEO raised); this file now
 * only exports the list styling itself, reused by `AlertStatusStrip`'s
 * "有事件" state so the amber card list rows are not duplicated between the
 * two files.
 */
export function AlertEventList({ events, onAck, ackPending }: AlertEventListProps) {
  return (
    <ul className="mt-3 space-y-2">
      {events.map((event) => (
        <li key={event.id} className="rounded-md border border-amber-800 bg-amber-950/30 p-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium text-neutral-100">
              {event.symbol}（{event.market}）・{alertTypeLabel(event.rule_type)}
            </span>
            <span className="text-xs text-neutral-500">{formatDateTime(event.triggered_at)}</span>
          </div>
          <p className="mt-1 text-neutral-300">{event.message}</p>
          <ObservedValues observed={event.observed} />
          <button
            type="button"
            onClick={() => onAck(event.id)}
            disabled={ackPending}
            className="mt-2 rounded-md bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            標記已處理
          </button>
        </li>
      ))}
    </ul>
  );
}
