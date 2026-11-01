import type { ReactNode, Ref } from "react";
import type { PlaybookTodayResponse } from "../lib/types";
import {
  FAST_MARKET_BADGE_CLASS,
  FAST_MARKET_DOT_CLASS,
  fastMarketAdjacentNote,
  modeBadgeVisual,
} from "../lib/playbookView";

/**
 * 第 0 層狀態列 (視覺規範 §2.4): 模式徽章 + 快市徽章（獨立疊加）+
 * EMERGENCY_EXIT，`sticky top-0`，捲動今日指令帳冊時仍常駐可見。
 *
 * `mode_label`/`mode_reason`/`fast_market.reason` are all server-rendered
 * strings (`wording.MODE_LABELS`/`wording.MODE_REASON_*`/
 * `wording.fast_market_reason`) — this component only decides colour/shape
 * per `today.mode`, never composes the label text itself.
 *
 * The 全部出清 trigger is passed in as `trigger` and nothing about the exit flow
 * lives here: no dialog, no mutation, no receipt (tech-architect Q14, FE-C10,
 * VETO-2). This bar is mounted only while `/today` is successful, so anything
 * hosted below it would vanish when a refetch fails.
 *
 * 視覺規範 §5: the background is the opaque `bg-black` (風控 必改項 8) — no
 * `backdrop-blur`, so no content shows through the disclosure text, and no
 * `max-h` / `overflow-*` / `line-clamp` may ever be added (that would be
 * collapsing a disclosure).
 */
export function ModeStatusBar({
  today,
  trigger,
  rootRef,
}: {
  today: PlaybookTodayResponse;
  trigger: ReactNode;
  /** The sticky root, for the receipt scroll to measure the bar's bottom edge. */
  rootRef?: Ref<HTMLDivElement>;
}) {
  const modeVisual = modeBadgeVisual(today.mode);
  // 排程台頁面審查 required: an `active` badge whose verdict was carried forward
  // has no measurement sentence (`reason` is null), so the backend's carried
  // explanation is rendered next to the badge instead of only in the warnings
  // list further down the page.
  const carriedNote = fastMarketAdjacentNote(today.fast_market);

  return (
    <div ref={rootRef} className="sticky top-0 z-10 border-b border-neutral-800 bg-black">
      <div className="mx-auto max-w-5xl px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium ${modeVisual.containerClass}`}
            >
              <span aria-hidden="true" className={`h-2.5 w-2.5 ${modeVisual.dotClass}`} />
              {today.mode_label}
            </span>
            {today.fast_market.active && (
              <span
                className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium ${FAST_MARKET_BADGE_CLASS}`}
              >
                <span aria-hidden="true" className={`h-2.5 w-2.5 ${FAST_MARKET_DOT_CLASS}`} />
                快市
              </span>
            )}
            <span className="text-xs text-neutral-500">規則版本 v{today.rules_version}</span>
          </div>
          {trigger}
        </div>
        <p className="mt-2 text-sm text-neutral-300">{today.mode_reason}</p>
        {today.fast_market.active && today.fast_market.reason !== null && (
          <p className="mt-1 text-sm text-indigo-200">{today.fast_market.reason}</p>
        )}
        {carriedNote !== null && <p className="mt-1 text-sm text-indigo-200">{carriedNote}</p>}
      </div>
    </div>
  );
}
