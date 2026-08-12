import type { PlaybookSettlementResponse } from "../lib/types";

/**
 * 結算區塊 (CEO 裁決七 T+1 結算, `TodayResponse.settlement`).
 * `settlement.warnings` already carries every unsettled line's reason plus
 * the rendered `SETTLEMENT_SUMMARY`/`SETTLEMENT_NOTHING_PENDING` sentence as
 * its last entry (`app/playbook/service.py::settle_pending`, verified) — this
 * component renders that list as-is, never recomputing a summary sentence of
 * its own. `settled`/`unsettled` line strings are `wording.directive_line`
 * output too (same as the ledger).
 */
export function SettlementPanel({ settlement }: { settlement: PlaybookSettlementResponse | null }) {
  if (settlement === null) return null;

  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold text-neutral-100">結算</h2>
      <div className="mt-3 rounded-md border border-neutral-800 p-4 text-sm text-neutral-300">
        {settlement.warnings.map((warning, i) => (
          <p key={i} className={i > 0 ? "mt-2" : ""}>
            {warning}
          </p>
        ))}

        {settlement.settled.length > 0 && (
          <ul className="mt-3 space-y-1 text-xs text-neutral-400">
            {settlement.settled.map((item) => (
              <li key={item.directive_id}>{item.line}</li>
            ))}
          </ul>
        )}

        {settlement.unsettled.length > 0 && (
          <ul className="mt-3 space-y-1 text-xs text-neutral-400">
            {settlement.unsettled.map((item) => (
              <li key={item.directive_id}>
                {item.line}｜{item.reason}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
