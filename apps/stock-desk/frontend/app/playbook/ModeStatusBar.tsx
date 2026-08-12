import type { PlaybookTodayResponse } from "../lib/types";
import {
  FAST_MARKET_BADGE_CLASS,
  FAST_MARKET_DOT_CLASS,
  fastMarketAdjacentNote,
  modeBadgeVisual,
} from "../lib/playbookView";
import { EmergencyExitControl } from "./EmergencyExitControl";

/**
 * 第 0 層狀態列 (視覺規範 §2.4): 模式徽章 + 快市徽章（獨立疊加）+
 * EMERGENCY_EXIT，`sticky top-0`，捲動今日指令帳冊時仍常駐可見。
 *
 * `mode_label`/`mode_reason`/`fast_market.reason` are all server-rendered
 * strings (`wording.MODE_LABELS`/`wording.MODE_REASON_*`/
 * `wording.fast_market_reason`) — this component only decides colour/shape
 * per `today.mode`, never composes the label text itself.
 */
export function ModeStatusBar({ today }: { today: PlaybookTodayResponse }) {
  const modeVisual = modeBadgeVisual(today.mode);
  // 排程台頁面審查 required: an `active` badge whose verdict was carried forward
  // has no measurement sentence (`reason` is null), so the backend's carried
  // explanation is rendered next to the badge instead of only in the warnings
  // list further down the page.
  const carriedNote = fastMarketAdjacentNote(today.fast_market);

  return (
    <div className="sticky top-0 z-10 border-b border-neutral-800 bg-black/95 backdrop-blur">
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
          {/* Step 2 的核取句由後端渲染後隨 `/today` 一起送來（凍結天數與預計
              恢復日是當日參數與交易日曆的函式），這裡只負責傳遞。 */}
          <EmergencyExitControl exitConfirm={today.exit_confirm} />
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
