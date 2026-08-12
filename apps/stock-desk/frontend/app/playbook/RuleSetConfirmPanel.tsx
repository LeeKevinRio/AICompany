"use client";

import { useState } from "react";
import { ErrorPanel } from "../components/ErrorPanel";
import { SkeletonBlock } from "../components/SkeletonBlock";
import { normalizeCapitalInput } from "../lib/playbookView";
import { useConfirmPlaybookRules, usePlaybookRuleSet } from "../lib/queries";

/**
 * 確認規則集 + 資本設定入口, rendered under the 待確認規則集 blocking state
 * (`mode === "unconfirmed"`, see `shouldRenderRuleSetConfirm`).
 *
 * The block that state describes has exactly one exit —
 * `POST /api/playbook/confirm-rules` — and this is it: before it runs, the
 * module holds a system default, produces no rule-driven directive and says so
 * (`attribution`, already rendered above this block by `page.tsx`; it is not
 * repeated here).
 *
 * WORDING: every *rule* sentence on screen is backend-rendered
 * (`rules[].text` is `wording.rule_text` with this version's thresholds already
 * substituted) and every threshold row is a backend `RuleParams` field name and
 * value — this component composes no description of what any rule does. The
 * only hard-coded copy is the block's own functional labels (heading, two
 * sub-headings, the field label, the button, the two failure labels), the two
 * sentences stating what confirming means and the one stating what the capital
 * figure is used for. All of them are risk-compliance-approved literals
 * (五輪定稿 2026-08-12, `work/reviews/快市排程-風控前置意見.md`) and none of
 * them urges, reassures or promises anything.
 *
 * The two confirmation sentences (⑥) sit **above** the capital field and the
 * button, not under them: they state what the user is about to take
 * responsibility for, so they may not arrive after the control that does it.
 * They are never collapsed, never a tooltip, and their core clause
 * 「你自行設定的規則之機械執行結果，非本系統的判斷或建議」 is a verbatim
 * protected region — `__tests__/RuleSetConfirmPanel.test.ts` asserts it against the
 * rendered output, which is the anti-drift guard the ruling required in place
 * of backend-rendering these two.
 *
 * 「帳冊裡的每一筆指令」 is true only because the ledger holds rule-driven lines
 * and nothing else: EMERGENCY_EXIT lines are attributed to the submitted action
 * (`wording.EXIT_ATTRIBUTION`), are returned by `POST /emergency-exit` and are
 * logged for settlement (風控 R16) — they are never merged into
 * `TodayResponse.directives`, which is what `DirectiveLedger` renders. **If that
 * ever changes, this sentence goes back to risk-compliance before the merge**,
 * because it would then claim rule authorship over a line the rules did not
 * produce.
 *
 * The 歸屬語 vocabulary is deliberately reused rather than reinvented: the
 * confirmation sentences say 「你本人設定」 and 「你自行設定的規則」, matching
 * `ATTRIBUTION_NOTE` — the same claim the page will make on every directive
 * once this is confirmed, which is precisely what the user is being asked to
 * take responsibility for.
 *
 * The 資金用途句 (④) is rendered next to the capital field itself, always, never
 * as a `placeholder`, a tooltip or an error-only hint: it states what the figure
 * being typed will be used for while it is being typed. Its ratio is
 * `ruleSet.data.deploy_ratio_pct`, which the backend already renders **with its
 * `%` sign** (`"70%"`): the client substitutes that string as it stands — it
 * must not multiply by 100, must not append a `%` of its own and must not
 * hard-code the number, which would go stale the day the parameter version
 * changes.
 */
export function RuleSetConfirmPanel() {
  const ruleSet = usePlaybookRuleSet(true);
  const mutation = useConfirmPlaybookRules();
  const [capital, setCapital] = useState("");
  const normalized = normalizeCapitalInput(capital);

  function submit() {
    if (normalized === null) return;
    mutation.mutate({ capital: normalized });
  }

  return (
    <section className="mt-6 rounded-md border border-neutral-700 bg-neutral-900/60 px-4 py-4">
      <h2 className="text-lg font-semibold text-neutral-100">確認規則集</h2>

      {ruleSet.isPending && (
        <div className="mt-3 space-y-2">
          <SkeletonBlock className="h-24 w-full" />
          <SkeletonBlock className="h-16 w-full" />
        </div>
      )}

      {ruleSet.isError && (
        <div className="mt-3">
          <ErrorPanel label="無法載入規則集" error={ruleSet.error} />
        </div>
      )}

      {ruleSet.isSuccess && (
        <>
          {/* 規則條文：後端逐字下發（thresholds already substituted），不改寫、不摘要。 */}
          <h3 className="mt-4 text-sm font-medium text-neutral-200">規則條文</h3>
          <ul className="mt-2 space-y-1.5">
            {ruleSet.data.rules.map((rule) => (
              <li key={rule.rule_id} className="text-sm text-neutral-300">
                {rule.text}
              </li>
            ))}
          </ul>

          {/*
            規則參數：欄名是後端 `RuleParams` 的欄位名本身（識別碼，非標籤）——
            後端 `RuleParamItem` 的註解寫明為什麼不在這裡改寫成中文標籤。版本與
            生效日不在此列：確認前沒有屬於使用者的版本可陳述（fail-closed）。
          */}
          <h3 className="mt-4 text-sm font-medium text-neutral-200">規則參數</h3>
          <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
            {ruleSet.data.params.map((param) => (
              <div key={param.field} className="flex justify-between gap-3 text-xs">
                <dt className="font-mono text-neutral-400">{param.field}</dt>
                <dd className="text-neutral-300">{param.value}</dd>
              </div>
            ))}
          </dl>

          {/*
            ⑥ 同意句（五輪定稿逐字）：在資本欄與按鈕之前，常駐、不摺疊、不 tooltip。
            核心子句為逐字保護區，見本檔 JSDoc 與 __tests__/RuleSetConfirmPanel.test.ts。
          */}
          <div className="mt-5 space-y-1">
            <p className="text-sm text-neutral-300">確認即表示這份規則集為你本人設定。</p>
            <p className="text-sm text-neutral-300">
              確認之後，帳冊裡的每一筆指令，都是你自行設定的規則之機械執行結果，非本系統的判斷或建議。
            </p>
          </div>

          <div className="mt-5 flex flex-wrap items-end gap-3">
            <div className="max-w-xl">
              <label htmlFor="playbook-capital" className="block text-sm text-neutral-200">
                資本額（TWD）
              </label>
              <input
                id="playbook-capital"
                type="text"
                inputMode="decimal"
                value={capital}
                onChange={(event) => setCapital(event.target.value)}
                className="mt-1 w-56 rounded-md border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-sm text-neutral-100"
              />
              {/*
                ④ 資金用途句（五輪定稿逐字）：欄位旁常駐，不是 placeholder、不是
                tooltip、不是只在錯誤時顯示。比例由後端下發（已含 %），此處不換算。
              */}
              <p className="mt-2 text-sm text-neutral-300">
                {`這個金額同時設定為你目前可動用的現金；系統會以「此金額 ×${ruleSet.data.deploy_ratio_pct}」計算出部署資金（TOTAL_DEPLOY），之後每一批進場的股數都以這筆部署資金為基礎換算。`}
              </p>
            </div>
            <button
              type="button"
              onClick={submit}
              disabled={normalized === null || mutation.isPending}
              className="rounded-md border border-neutral-500 bg-neutral-800 px-3 py-1.5 text-sm text-neutral-100 hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {mutation.isPending ? "送出中…" : "確認規則集並設定資本額"}
            </button>
          </div>

          {mutation.isError && (
            <div className="mt-3">
              <ErrorPanel label="確認規則集送出失敗" error={mutation.error} />
            </div>
          )}
        </>
      )}
    </section>
  );
}
