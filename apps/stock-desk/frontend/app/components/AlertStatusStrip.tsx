"use client";

import Link from "next/link";
import { ApiError } from "../lib/api";
import { formatDateTime } from "../lib/format";
import {
  ALERTS_LOAD_ERROR_PREFIX,
  ALERTS_MANAGE_LINK,
  ALERTS_NO_RULES,
  ALERTS_NO_RULES_LINK,
  ALERTS_SCHEDULER_DISABLED,
  buildAlertsPendingCount,
  buildAlertsQueriedAt,
  buildAlertsRulesNoEvents,
} from "../lib/oneLinerWording";
import { useAckAlertEvent, useAlertEvents, useAlerts, useSettings } from "../lib/queries";
import type { AlertEvent, AlertRule } from "../lib/types";
import { AlertEventList } from "./PendingAlertsPanel";
import { SkeletonBlock } from "./SkeletonBlock";

/**
 * 首頁警示狀態列（`work/stock-desk-一眼一句-實作規格.md` §3.3、視覺規範
 * B.4）——取代 `RiskGauge` 旁邊常年空白的 `PendingAlertsPanel` 半版卡。四態：
 * 沒規則／有規則沒觸發／排程總開關關閉／有事件（風控 2026-09-19 required
 * R-A3 新增第四態），只有「有事件」用 amber 警示色，其餘用中性容器，這正是
 * 解決 CEO「旁邊待處理警示長期為空、看起來很怪」的根因。
 *
 * 優先序（R-A3）：事件 >0 → C；否則排程總開關關閉 → D；否則規則 0 → A；
 * 否則 → B。事件優先於總開關是刻意的——即使排程目前關閉，過去已觸發但尚未
 * 標記已處理的事件仍是使用者現在就要看到的資訊，不能被「排程關閉」蓋過去。
 *
 * Pure presentational half (`AlertStatusStripView`), split out so it can be
 * unit-tested with `renderToStaticMarkup` without a query client — see
 * `alertStatusStrip.test.ts`. `AlertStatusStrip` below wires it to
 * `useAlerts`/`useAlertEvents`/`useSettings`.
 */
export interface AlertStatusStripViewProps {
  rules: AlertRule[];
  events: AlertEvent[];
  eventsAsOf: string;
  /**
   * `AppSettings.alerts.enabled` — the scheduler's own kill switch (when
   * `false` the whole evaluation tick is skipped, so state B's "已設定，目前
   * 沒有待處理警示" would read as "just checked, all clear", which is false).
   * `null` means "unknown" (the settings query itself failed) — R-A3: a
   * settings failure must not block the alerts strip, so `null` falls back to
   * the A/B/C-only judgement as if the switch were on.
   */
  schedulerEnabled: boolean | null;
  onAck: (id: number) => void;
  ackPending: boolean;
}

export function AlertStatusStripView({
  rules,
  events,
  eventsAsOf,
  schedulerEnabled,
  onAck,
  ackPending,
}: AlertStatusStripViewProps) {
  // 狀態 C：有待處理事件——優先於其他所有狀態（見上方優先序註解）。
  if (events.length > 0) {
    return (
      <div className="rounded-lg border border-amber-800/60 bg-amber-950/10 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium text-amber-300">{buildAlertsPendingCount(events.length)}</p>
          <Link href="/settings" className="text-xs text-sky-400 underline hover:text-sky-300">
            {ALERTS_MANAGE_LINK}
          </Link>
        </div>
        <AlertEventList events={events} onAck={onAck} ackPending={ackPending} />
      </div>
    );
  }

  // 狀態 D：排程總開關關閉（R-A3）。
  if (schedulerEnabled === false) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/40 px-4 py-3">
        <p className="text-sm text-neutral-300">{ALERTS_SCHEDULER_DISABLED}</p>
        <Link href="/settings" className="text-xs text-sky-400 underline hover:text-sky-300">
          {ALERTS_MANAGE_LINK}
        </Link>
      </div>
    );
  }

  // 狀態 A：沒有任何規則。
  if (rules.length === 0) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/40 px-4 py-3">
        <p className="text-sm text-neutral-300">{ALERTS_NO_RULES}</p>
        <Link href="/settings" className="text-xs text-sky-400 underline hover:text-sky-300">
          {ALERTS_NO_RULES_LINK}
        </Link>
      </div>
    );
  }

  // 狀態 B：有規則、沒有待處理事件。N 用規則**總數**（不分 enabled/disabled，
  // 見 `oneLinerWording.ts` 的 `buildAlertsRulesNoEvents` 註解）。
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/40 px-4 py-3">
      <p className="text-sm text-neutral-300">{buildAlertsRulesNoEvents(rules.length)}</p>
      <span className="text-xs text-neutral-500">{buildAlertsQueriedAt(formatDateTime(eventsAsOf))}</span>
    </div>
  );
}

export function AlertStatusStrip() {
  const alerts = useAlerts(true);
  const events = useAlertEvents(true, true);
  const settings = useSettings(true);
  const ackMutation = useAckAlertEvent();

  if (alerts.isPending || events.isPending || settings.isPending) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-950/40 px-4 py-3">
        <SkeletonBlock className="h-5 w-full" />
      </div>
    );
  }

  if (alerts.isError || events.isError) {
    const error = alerts.isError ? alerts.error : events.error;
    return (
      <p role="alert" className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
        {ALERTS_LOAD_ERROR_PREFIX}
        {error instanceof ApiError ? error.message : "未知錯誤"}
      </p>
    );
  }

  // R-A3: a `settings` failure degrades to "unknown switch state" (A/B/C-only
  // judgement) rather than blocking the whole strip — the alerts/events data
  // this component exists for is still available and more important.
  const schedulerEnabled = settings.isSuccess ? settings.data.settings.alerts.enabled : null;

  return (
    <AlertStatusStripView
      rules={alerts.data.items}
      events={events.data.items}
      eventsAsOf={events.data.as_of}
      schedulerEnabled={schedulerEnabled}
      onAck={(id) => ackMutation.mutate(id)}
      ackPending={ackMutation.isPending}
    />
  );
}
