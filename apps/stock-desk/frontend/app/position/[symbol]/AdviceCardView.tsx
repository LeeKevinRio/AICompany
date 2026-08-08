import type { AdviceCard } from "../../lib/types";
import {
  cardActionColorClass,
  confidenceLabel,
  formatDateTime,
  formatNumber,
  formatPercent,
} from "../../lib/format";
import { buildAttributedHeadline } from "../../lib/adviceWording";
import { LimitsCheckList } from "./LimitsCheckList";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h3 className="text-sm font-semibold text-neutral-200">{title}</h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}

export function AdviceCardView({ advice }: { advice: AdviceCard }) {
  const hasBlockedNotices = advice.blocked_notices.length > 0;

  return (
    <div className="rounded-lg border border-neutral-800 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`inline-block rounded-md border px-3 py-1 text-lg font-bold ${cardActionColorClass(
            advice.action,
          )}`}
        >
          {buildAttributedHeadline(advice.action)}
        </span>
        <span className="text-sm text-neutral-400">
          信心等級：{confidenceLabel(advice.confidence)}
        </span>
        <span className="text-xs text-neutral-500">規則版本 {advice.rules_version}</span>
      </div>
      <p className="mt-2 text-xs text-neutral-500">{advice.confidence_meaning}</p>
      <p className="mt-1 text-xs text-neutral-500">
        資料時間：{formatDateTime(advice.as_of)}｜觀察區間：
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

      <Section title="建議數量區間">
        {advice.quantity_range === null ? (
          <p className="text-sm text-neutral-500">此建議未附帶數量區間（無法從風險上限推導）。</p>
        ) : (
          <div className="text-sm text-neutral-300">
            <p>
              {advice.quantity_range.min_shares.toLocaleString("zh-Hant-TW")} ~{" "}
              {advice.quantity_range.max_shares.toLocaleString("zh-Hant-TW")} 股
            </p>
            <p className="mt-1 text-xs text-neutral-500">{advice.quantity_range.basis}</p>
            {!advice.quantity_range.restores_compliance && (
              <div
                role="alert"
                className="mt-2 rounded-md border border-rose-800 bg-rose-950/50 px-4 py-3 text-sm font-semibold text-rose-300"
              >
                此賣出量無法讓上限恢復合規
              </div>
            )}
          </div>
        )}
      </Section>

      <Section title={`命中規則（${advice.matched_rules.length} 條）`}>
        {advice.matched_rules.length === 0 ? (
          <p className="text-sm text-neutral-500">目前沒有規則命中。</p>
        ) : (
          <ul className="space-y-2">
            {advice.matched_rules.map((rule) => (
              <li key={rule.id} className="rounded-md border border-neutral-800 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-neutral-100">{rule.name}</span>
                  <span className="text-xs text-neutral-400">
                    權重 {formatNumber(rule.weight, 2)}
                  </span>
                </div>
                <p className="mt-1 text-neutral-400">{rule.explanation}</p>
                <p className="mt-1 text-xs text-neutral-600">{rule.weight_meaning}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="反面論點">
        {advice.counterarguments.length === 0 ? (
          <p className="text-sm text-neutral-500">無。</p>
        ) : (
          <ul className="list-disc space-y-1 pl-5 text-sm text-neutral-400">
            {advice.counterarguments.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="失效條件">
        {advice.invalidation_conditions.length === 0 ? (
          <p className="text-sm text-neutral-500">無。</p>
        ) : (
          <ul className="list-disc space-y-1 pl-5 text-sm text-neutral-400">
            {advice.invalidation_conditions.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        )}
      </Section>

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

      <p className="mt-6 border-t border-neutral-800 pt-4 text-xs text-neutral-500">
        {advice.disclaimer}
      </p>
    </div>
  );
}
