import type { AdviceCard } from "../../lib/types";
import { actionRawLabel, formatDateTime, formatNumber, formatPercent, ruleDirectionLabel } from "../../lib/format";
import { ADVICE_CARD_XREF_TO_SUMMARY } from "../../lib/sectionTaglines";
import { directionShares, ruleDirection } from "../../lib/ruleDirection";
import { LimitsCheckList } from "./LimitsCheckList";

/**
 * 圖形化 item 3 (CEO 2026-09-06): each matched rule carries a direction chip
 * (the existing `ruleDirectionLabel` word) and the 命中規則方向 section leads
 * with a 100% stacked bar of the direction weights. The direction per rule is
 * read back from `direction_weights[].actions` (`app/lib/ruleDirection.ts`),
 * never re-derived client-side.
 *
 * 風控 2026-09-06 圖形化審查 R1 / R5 / S-d 落地：
 * - R1: no glyph on the chip at all — a triangle beside 建設性 (= `add`) is an
 *   up-arrow next to an add rule; `componentWordingScan.test.ts` rejects
 *   arrow/triangle glyphs in this file.
 * - S-d: the chip is fully neutral (word only); the bar segments are three
 *   NEUTRAL greys told apart by the legend + labels, never a hue that the
 *   page already uses for a conclusion (sky = 進場評估 badge) or a warning.
 * - R5: the bar is a new derived number, so it carries its own standing
 *   qualifier (`DIRECTION_SHARE_QUALIFIER`, ≥ text-sm / ≥ neutral-400, never
 *   in <details>) saying what the share is and that it is not a probability.
 */
const DIRECTION_CHIP_CLASS = "border-neutral-700 bg-neutral-900 text-neutral-300";

const DIRECTION_BAR_CLASS: Record<string, string> = {
  constructive: "bg-neutral-300",
  defensive: "bg-neutral-500",
  neutral: "bg-neutral-700",
};

export const DIRECTION_BAR_ARIA_LABEL = "命中規則方向權重占比";

/** creative-lead 起草（候選 A）→ risk-compliance-officer 逐字審；字面（含標點）不得再改動。 */
export const DIRECTION_SHARE_QUALIFIER =
  "占比為各方向命中規則權重佔全部命中規則權重總和的比例，不代表機率、達成率或建議強度。";

function DirectionChip({ direction }: { direction: string }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${DIRECTION_CHIP_CLASS}`}>
      {ruleDirectionLabel(direction)}
    </span>
  );
}

/** 100% stacked bar of the direction weights; 2px surface gaps, ≤24px thick, legend + qualifier beneath. */
function DirectionWeightBar({ advice }: { advice: AdviceCard }) {
  const shares = directionShares(advice.direction_weights);
  if (shares.every((s) => s.sharePct === 0)) return null;
  return (
    <div className="mb-3">
      <div role="img" aria-label={DIRECTION_BAR_ARIA_LABEL} className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full">
        {shares
          .filter((s) => s.sharePct > 0)
          .map((s) => (
            <div
              key={s.direction}
              className={`h-full ${DIRECTION_BAR_CLASS[s.direction] ?? DIRECTION_BAR_CLASS.neutral}`}
              style={{ width: `${s.sharePct}%` }}
            />
          ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-400">
        {shares.map((s) => (
          <li key={s.direction} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className={`inline-block h-2.5 w-2.5 rounded-full ${DIRECTION_BAR_CLASS[s.direction] ?? DIRECTION_BAR_CLASS.neutral}`}
            />
            {ruleDirectionLabel(s.direction)} {s.sharePct.toFixed(0)}%
          </li>
        ))}
      </ul>
      {/* R5: standing qualifier, same block as the bar, ≥ text-sm / ≥ neutral-400, never collapsible. */}
      <p className="mt-2 text-sm text-neutral-400">{DIRECTION_SHARE_QUALIFIER}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h3 className="text-sm font-semibold text-neutral-200">{title}</h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}

/**
 * True only when the matched rules really point opposite ways.
 *
 * The backend's directions are `constructive` / `defensive` / `neutral`
 * (`ACTION_DIRECTION` in `app/advice/engine.py`); only the first two are
 * opposed. `neutral` (the `hold` actions) is a third category, not a side, so
 * a defensive + neutral mix is *not* an opposition and must not claim one —
 * counting `direction_weights.length > 1` would have made that claim.
 */
export function hasOpposingDirections(advice: AdviceCard): boolean {
  const directions = new Set(advice.direction_weights.map((dw) => dw.direction));
  return directions.has("defensive") && directions.has("constructive");
}

export function AdviceCardView({ advice }: { advice: AdviceCard }) {
  const hasBlockedNotices = advice.blocked_notices.length > 0;

  return (
    <div className="rounded-lg border border-neutral-800 p-5">
      {/*
        個股頁減負 FR-4 方向 A（風控預審 C5–C7；逐字審第一輪）：headline／信心等級／
        confidenceMeaning／disclaimer／建議數量區間／反面論點／失效條件 同進同退，
        全部移出本卡——它們在上方「操作摘要」完整且唯一呈現（C5/C6）。本卡收斂為
        純規則明細，最上方以交叉引用句銜接。

        R3 fix (risk-final-review.md) 的承載體改為這句銜接句：繼承 R3 呈現規格——
        卡片最上方、≥ text-sm、≥ text-neutral-200、不可摺疊（風控逐字審第一輪
        required）。不得再於本卡單獨放回 headline 而不帶 disclaimer（C5 紅線）。
      */}
      <p className="rounded-md border border-neutral-700 bg-neutral-900/80 px-3 py-2 text-sm text-neutral-200">
        {ADVICE_CARD_XREF_TO_SUMMARY}
      </p>
      <p className="mt-2 text-xs text-neutral-500">
        規則版本 {advice.rules_version}｜資料時間：{formatDateTime(advice.as_of)}｜觀察區間：
        {advice.observation_window.start ?? "—"} ~ {advice.observation_window.end ?? "—"}
        （{advice.observation_window.bars ?? "—"} 根日線）
      </p>

      {hasBlockedNotices && (
        <div
          role="alert"
          className="mt-4 rounded-md border border-rose-800 bg-rose-950/50 px-4 py-3 text-sm text-rose-300"
        >
          <p className="font-semibold">加碼建議被風險上限擋下</p>
          <ul className="mt-1 list-disc pl-5">
            {advice.blocked_notices.map((notice, i) => (
              <li key={i}>{notice}</li>
            ))}
          </ul>
        </div>
      )}

      {advice.downgrade_notices.length > 0 && (
        <div className="mt-4 rounded-md border border-amber-800 bg-amber-950/40 px-4 py-3 text-sm text-amber-300">
          <ul className="list-disc pl-5">
            {advice.downgrade_notices.map((notice, i) => (
              <li key={i}>{notice}</li>
            ))}
          </ul>
        </div>
      )}

      <Section title={`命中規則（${advice.matched_rules.length} 條）`}>
        {advice.matched_rules.length === 0 ? (
          <p className="text-sm text-neutral-500">目前沒有規則命中。</p>
        ) : (
          <ul className="space-y-2">
            {advice.matched_rules.map((rule) => {
              const direction = ruleDirection(advice, rule.action);
              return (
              <li key={rule.id} className="rounded-md border border-neutral-800 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex flex-wrap items-center gap-2">
                    {direction !== null && <DirectionChip direction={direction} />}
                    <span className="font-medium text-neutral-100">{rule.name}</span>
                  </span>
                  <span className="text-xs text-neutral-400">
                    權重 {formatNumber(rule.weight, 2)}
                  </span>
                </div>
                <p className="mt-1 text-neutral-400">{rule.explanation}</p>
                <p className="mt-1 text-xs text-neutral-600">{rule.weight_meaning}</p>
              </li>
              );
            })}
          </ul>
        )}
      </Section>

      {/*
        D2 item 3 (限制清單 #10 / 機會清單 D2): the backend has always computed
        `direction_weights` and `has_conflict` (`app/advice/engine.py`,
        verified) but neither ever reached this screen — a reader could not
        tell whether opposing evidence matched alongside the winning
        direction. Rendered as-is (no re-derivation): `direction_weights` is
        the per-direction breakdown, `has_conflict` (`len(matched action
        types) > 1`, not necessarily a different *direction* — see the
        backend's own `_direction_weights`) is surfaced separately as its own
        factual note rather than folded into a "conflict" claim the flag does
        not always support.
      */}
      {advice.direction_weights.length > 0 && (
        <Section title="命中規則方向">
          <DirectionWeightBar advice={advice} />
          <ul className="space-y-1 text-sm text-neutral-300">
            {advice.direction_weights.map((dw) => (
              <li key={dw.direction}>
                {ruleDirectionLabel(dw.direction)}：權重 {formatNumber(dw.weight, 2)}（命中動作：
                {dw.actions.map(actionRawLabel).join("、")}）
              </li>
            ))}
          </ul>
          {advice.has_conflict && (
            <p className="mt-2 text-xs text-amber-300">本次命中規則涵蓋一種以上動作，方向分布如上列所示。</p>
          )}
          {/*
            D2 suggested (波次1文案裁決.md「D 批」，2026-08-10，裁決建議句):
            `has_conflict` only means "more than one matched action type", not
            necessarily an opposing *direction* (see the backend comment this
            file already quotes above). A *real* opposite is constructive and
            defensive both present (`hasOpposingDirections`) — the headline
            action above is derived from the highest-weight direction only, so
            a reader needs this sentence specifically then, not merely when
            actions differ within the same direction, and not when the second
            direction is the neutral `hold` bucket.
            個股頁減負 FR-4 方向 A（風控第二輪 R-1）：headline 已移至操作摘要，
            本句指涉改為「上方操作摘要的結論」，並統一為全形逗號。
          */}
          {hasOpposingDirections(advice) && (
            <p className="mt-2 text-xs text-amber-300">
              本次同時命中方向相反的規則，上方操作摘要的結論只代表權重較高的一方。
            </p>
          )}
        </Section>
      )}

      <Section title="風險上限檢查">
        <LimitsCheckList limits={advice.limits_check} />
      </Section>

      <Section title="資料完整度">
        <p className="text-sm text-neutral-400">
          規則共 {advice.evaluation.total_rules} 條，可評估 {advice.evaluation.evaluated_rules}{" "}
          條，命中 {advice.evaluation.matched_rules} 條，資料完整度{" "}
          {formatPercent(advice.evaluation.data_completeness)}。
        </p>
        {advice.evaluation.skipped_rules.length > 0 && (
          <details className="mt-2 text-sm text-neutral-500">
            <summary className="cursor-pointer text-neutral-400">
              因資料不足被跳過的規則（{advice.evaluation.skipped_rules.length} 條）
            </summary>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {advice.evaluation.skipped_rules.map((skipped) => (
                <li key={skipped.id}>
                  {skipped.name}：{skipped.reason}
                </li>
              ))}
            </ul>
          </details>
        )}
      </Section>
    </div>
  );
}
