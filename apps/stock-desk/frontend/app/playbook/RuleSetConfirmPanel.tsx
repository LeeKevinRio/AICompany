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
 * sub-headings, the field label, the button, the two failure labels) and the
 * one sentence stating what confirming means, all of which go to
 * risk-compliance with this batch and are listed verbatim in the hand-off
 * report. None of them urges, reassures or promises anything.
 *
 * The 歸屬語 vocabulary is deliberately reused rather than reinvented: the
 * confirmation sentence says 「你本人設定」, matching `ATTRIBUTION_NOTE`'s
 * 「你自行設定的規則」 — the same claim the page will make on every directive
 * once this is confirmed, which is precisely what the user is being asked to
 * take responsibility for.
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

          <div className="mt-5 flex flex-wrap items-end gap-3">
            <div>
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

          <p className="mt-3 text-sm text-neutral-300">
            確認即表示這份規則集為你本人設定，之後的指令將以此為據。
          </p>

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
