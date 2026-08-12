import { DataMetaStatusBadge } from "../components/DataMetaStatusBadge";
import type { PlaybookDirectiveLine } from "../lib/types";
import {
  directiveStatusLabel,
  ruleFamilyVisual,
  sortDirectiveLines,
  splitDirectiveLine,
} from "../lib/playbookView";

/**
 * One 帳冊列 (視覺規範 §3): `border-l-4 border-y rounded-none` — deliberately
 * not `AdviceCardView`'s `rounded-lg border p-5` (§3.2/§5 R8: the two
 * containers must be visually distinguishable at a glance).
 *
 * `parts` is `directive.line` (the backend-rendered one-line 動作／股數／
 * 規則／依據資料日／預定執行日／參考價 sentence) split on its own `｜`
 * separator into segments — see `splitDirectiveLine`'s doc comment. Nothing
 * here recomposes a word of that sentence; the segments are only laid out
 * vertically instead of the backend's horizontal pipe-joined form, per §3.3's
 * wireframe, which requires 依據資料日／預定執行日／參考價 to be separately
 * always-visible rather than buried inside one long line (R1/R5).
 */
function DirectiveRow({ item }: { item: PlaybookDirectiveLine }) {
  const { directive } = item;
  const parts = splitDirectiveLine(item.line);
  const visual = ruleFamilyVisual(directive.rule_id);

  return (
    <li
      className={`rounded-none border-y border-neutral-800 border-l-4 px-4 py-3 ${visual.borderClass}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-xs ${visual.chipClass}`}>
          規則 {directive.rule_id}
        </span>
        <span className="text-sm font-medium text-neutral-100">
          {parts[0]}・{parts[1]}・{parts[2]}
        </span>
        <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-300">
          {directiveStatusLabel(directive.status)}
        </span>
      </div>

      {/* 觸發條件：公式與輸入來源逐字可見（R1），backend-rendered as-is. */}
      <p className="mt-2 text-sm text-neutral-400">{directive.rule_summary}</p>

      <div className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs text-neutral-400 sm:grid-cols-3">
        <span>{parts[4]}</span>
        <span>{parts[5]}</span>
        <span>{parts[6]}</span>
      </div>

      <p className="mt-2 text-xs text-neutral-500">{directive.limit_note}</p>

      {/*
        R5: 資料新鮮度不採沉默慣例，恆常顯示一行純文字；`DataMetaStatusBadge`
        only overlays *additionally* on a non-fresh status (returns `null` on
        `fresh`), matching §3.3's "只有在非 fresh 時額外疊加既有徽章樣式".
        `stalenessMinutes`/`isWithinTtl` are `null` because `Directive` carries
        no per-line staleness-minute field (only `data_status`/`source`) —
        known limitation, noted in the hand-off report.
      */}
      <p className="mt-1 flex flex-wrap items-center text-xs text-neutral-400">
        資料狀態 {directive.data_status}・來源 {directive.source}
        <DataMetaStatusBadge
          status={directive.data_status}
          stalenessMinutes={null}
          isWithinTtl={null}
        />
      </p>
    </li>
  );
}

/**
 * `noDirectiveNote` is the backend's own sentence for an empty ledger on a day
 * every rule really was evaluated (四輪收斂裁決 題 12), or `null` on every other
 * day. `null` keeps the bare 「無。」: without the completeness flag the page
 * cannot tell 未命中 from 未評估, and 「無。」 is the honest answer to that
 * uncertainty. The 資料基準日 line stays either way (裁決: 資料基準日行保留).
 */
export function DirectiveLedger({
  directives,
  dataDate,
  noDirectiveNote,
}: {
  directives: PlaybookDirectiveLine[];
  dataDate: string;
  noDirectiveNote: string | null;
}) {
  const sorted = sortDirectiveLines(directives);

  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold text-neutral-100">今日指令帳冊</h2>
      {sorted.length === 0 ? (
        <div className="mt-3 rounded-none border-y border-neutral-800 border-l-4 border-l-neutral-600 px-4 py-3">
          <p className="text-sm text-neutral-300">{noDirectiveNote ?? "無。"}</p>
          <p className="mt-1 text-xs text-neutral-500">資料基準日 {dataDate}</p>
        </div>
      ) : (
        <ul className="mt-3 space-y-3">
          {sorted.map((item, index) => (
            <DirectiveRow
              key={`${item.directive.symbol}-${item.directive.batch_no ?? "—"}-${item.directive.rule_id}-${index}`}
              item={item}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
