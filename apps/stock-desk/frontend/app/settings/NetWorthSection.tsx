"use client";

/**
 * The account net worth the user reports themselves (FR-9).
 *
 * It is a section of the settings document but **not** part of the main
 * settings form, and that separation is load-bearing rather than cosmetic:
 * every `PUT` that carries this section re-stamps its report time server-side,
 * so folding it into the "儲存設定" button would let saving a fee rate refresh a
 * figure the user never looked at — and the freshness rule (7-day notice,
 * 30-day expiry) would then be measuring the wrong event.
 *
 * Three things this component must not do, each mirroring a backend rule:
 *   - no client-side clamping or rounding. Whatever is typed is sent as typed,
 *     and a refusal comes back as the backend's own message (`app/settings/
 *     net_worth.py`), because a silently corrected number is one the user
 *     would later believe they had entered.
 *   - no currency conversion, and no second currency field: this is TWD only,
 *     and the note says so before the number is typed rather than after.
 *   - no claim of freshness of its own. `freshness`/`age_days` come from the
 *     same helper the risk layer uses, so this panel cannot say "fresh" about
 *     a figure the gross-exposure cap has already stopped using.
 */

import { useState } from "react";
import { ApiError } from "../lib/api";
import { formatDateTime, formatMoneyNumber } from "../lib/format";
import { useUpdateSettings } from "../lib/queries";
import type { NetWorthFreshness, SettingsResponse } from "../lib/types";

/** FR-9 (f): the exact label the risk decision fixed. */
const NET_WORTH_LABEL = "帳戶總淨值（新台幣）";

const FRESHNESS_LABELS: Record<NetWorthFreshness, string> = {
  absent: "尚未輸入",
  fresh: "已更新",
  ageing: "建議更新",
  expired: "已過期",
};

function freshnessClass(freshness: NetWorthFreshness): string {
  switch (freshness) {
    case "fresh":
      return "border-emerald-800 bg-emerald-950/40 text-emerald-300";
    case "ageing":
      return "border-amber-800 bg-amber-950/40 text-amber-300";
    case "expired":
      return "border-rose-800 bg-rose-950/40 text-rose-300";
    case "absent":
    default:
      return "border-neutral-700 bg-neutral-900 text-neutral-300";
  }
}

export function NetWorthSection({ settings }: { settings: SettingsResponse }) {
  const block = settings.net_worth;
  const [value, setValue] = useState<string>(
    block.total_net_worth_twd === null ? "" : String(block.total_net_worth_twd),
  );
  const mutation = useUpdateSettings();
  const fieldError = mutation.error instanceof ApiError
    ? mutation.error.fieldErrors["total_net_worth_twd"]
    : undefined;
  // A refusal from the book-level bands (below the valued positions) arrives as
  // a plain `detail` string, not a field error: it is a sentence the user has
  // to read, so it is rendered at full width rather than as small print.
  const rejection =
    mutation.error instanceof ApiError && !fieldError ? mutation.error.message : undefined;
  // Warnings belong to the response of the write that produced them; a later
  // read cannot recompute them without pricing the whole book.
  const warnings = mutation.isSuccess ? mutation.data.net_worth.warnings : [];

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Sent exactly as typed. `Number("")` is 0, which the backend refuses with
    // its own message — deliberately not pre-empted here, so there is one
    // authority on what this field accepts.
    mutation.mutate({ net_worth: { total_net_worth_twd: Number(value) } });
  }

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">帳戶總淨值</h2>
        <span
          className={`rounded border px-2 py-0.5 text-xs ${freshnessClass(block.freshness)}`}
        >
          {FRESHNESS_LABELS[block.freshness]}
          {block.age_days !== null && `（已 ${block.age_days} 天未更新）`}
        </span>
      </div>
      <p className="mt-1 text-xs text-neutral-500">
        這個數字只用在「總曝險上限」（第 3 條）的分母：曝險比率 = 系統已估值的部位市值合計 ÷ 你自報的帳戶總淨值。
        分子由系統計算、分母由你自行輸入，兩者來源不同；系統不會查核這個數字。
      </p>

      <form onSubmit={handleSubmit} className="mt-4 space-y-3">
        <div>
          <label htmlFor="net_worth.total_net_worth_twd" className="block text-sm text-neutral-300">
            {NET_WORTH_LABEL}
          </label>
          {/*
            Text input, like every other numeric field on this page: the browser
            must not be the thing that judges the value (see `SettingsForm`).
          */}
          <input
            id="net_worth.total_net_worth_twd"
            inputMode="decimal"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 sm:max-w-xs"
          />
          <p className="mt-1 text-xs text-amber-300">
            若你有外幣資產，請自行換算為台幣後填入；系統不會為此欄位做匯率換算。
          </p>
          {fieldError && <p className="mt-1 text-xs text-red-400">{fieldError}</p>}
        </div>

        <dl className="grid grid-cols-1 gap-1 text-xs text-neutral-400 sm:grid-cols-2">
          <div className="flex gap-2">
            <dt>目前儲存的數值：</dt>
            <dd className="text-neutral-200">
              {block.total_net_worth_twd === null
                ? "尚未輸入"
                : formatMoneyNumber(block.total_net_worth_twd, "TWD", 0)}
            </dd>
          </div>
          <div className="flex gap-2">
            <dt>上次更新時間：</dt>
            <dd className="text-neutral-200">
              {block.updated_at === null ? "—" : formatDateTime(block.updated_at)}
            </dd>
          </div>
        </dl>

        {block.notes.map((note) => (
          <p
            key={note}
            className={`text-xs ${
              block.freshness === "expired" ? "text-rose-300" : "text-neutral-500"
            }`}
          >
            {note}
          </p>
        ))}

        <button
          type="submit"
          disabled={mutation.isPending}
          className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mutation.isPending ? "儲存中…" : "更新帳戶總淨值"}
        </button>

        {rejection && (
          <p
            role="alert"
            className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300"
          >
            {rejection}
          </p>
        )}
        {warnings.map((warning) => (
          <p
            key={warning}
            role="alert"
            className="rounded-md border border-amber-700 bg-amber-950/50 px-4 py-3 text-sm font-medium text-amber-200"
          >
            {warning}
          </p>
        ))}
        {mutation.isSuccess && (
          <p
            role="status"
            className="rounded-md border border-emerald-900 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300"
          >
            帳戶總淨值已更新，更新時間以本次儲存為準。
          </p>
        )}
      </form>
    </section>
  );
}
