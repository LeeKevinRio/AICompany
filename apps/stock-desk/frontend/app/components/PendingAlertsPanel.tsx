"use client";

import Link from "next/link";
import { ApiError } from "../lib/api";
import { alertTypeLabel, formatDateTime } from "../lib/format";
import { useAckAlertEvent, useAlertEvents } from "../lib/queries";
import { SkeletonBlock } from "./SkeletonBlock";

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

export function PendingAlertsPanel() {
  const events = useAlertEvents(true, true);
  const ackMutation = useAckAlertEvent();

  return (
    <div className="rounded-lg border border-neutral-800 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">待處理警示</h2>
        <Link href="/settings" className="text-xs text-sky-400 underline hover:text-sky-300">
          管理警示規則
        </Link>
      </div>

      {events.isPending && (
        <div className="mt-3 space-y-2">
          <SkeletonBlock className="h-14 w-full" />
          <SkeletonBlock className="h-14 w-full" />
        </div>
      )}
      {events.isError && (
        <p role="alert" className="mt-3 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          無法載入警示事件：{events.error instanceof ApiError ? events.error.message : "未知錯誤"}
        </p>
      )}
      {events.isSuccess && events.data.items.length === 0 && (
        <p className="mt-3 text-sm text-neutral-500">目前沒有待處理的警示。</p>
      )}
      {events.isSuccess && events.data.items.length > 0 && (
        <ul className="mt-3 space-y-2">
          {events.data.items.map((event) => (
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
                onClick={() => ackMutation.mutate(event.id)}
                disabled={ackMutation.isPending}
                className="mt-2 rounded-md bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                標記已處理
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
