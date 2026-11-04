import { Fragment, useId, type ReactNode } from "react";
import { formatDateTime } from "../lib/format";
import { usePlaybookToday } from "../lib/queries";
import type { PlaybookPendingExitBlock } from "../lib/types";

const READ_AT_PLACEHOLDER = "{read_at}";

/**
 * Substitute `{read_at}` exactly once (ADR-0039 T22). A function replacer is
 * used so the stamp can never be interpreted as a `$`-pattern.
 */
export function leadWithReadAt(template: string, asOf: string): string {
  return template.replace(READ_AT_PLACEHOLDER, () => formatDateTime(asOf));
}

/**
 * An ISO calendar date (`2026-11-11`) not embedded in a longer digit run.
 * Browsers may break a line after a hyphen, which would split a date the user
 * checks against a broker, so each match is kept on one line.
 */
const ISO_DATE = /(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)/g;

/**
 * Render a backend string verbatim, wrapping only ISO date tokens in an inline
 * `whitespace-nowrap` span. Only text nodes are split: no characters are added,
 * dropped or reordered, and a string without a date is returned untouched.
 */
export function withNoBreakDates(value: string): ReactNode {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of value.matchAll(ISO_DATE)) {
    if (m.index > last) parts.push(value.slice(last, m.index));
    parts.push(
      <span key={m.index} className="whitespace-nowrap">
        {m[0]}
      </span>,
    );
    last = m.index + m[0].length;
  }
  if (parts.length === 0) return value;
  if (last < value.length) parts.push(value.slice(last));
  return <Fragment>{parts}</Fragment>;
}

/** True when the block carries at least one row; otherwise nothing is rendered. */
export function hasPendingExitRows(block: PlaybookPendingExitBlock): boolean {
  return block.sections.some((s) => s.rows.length > 0);
}

/**
 * N-171 group A: the standing disclosure of sell directives that an
 * emergency exit produced and that are not yet settled (ADR-0039).
 *
 * Independent component: it reads only the `["playbook-today"]` query, imports
 * no receipt store and no mutation, and renders only strings the backend sent
 * (`title`, `lead_template`, `label`, `lead`, `text`, `notes`,
 * `entry_before_exit_note`, `closing_notes`). The one front-end substitution
 * is `{read_at}` -> `formatDateTime(as_of)` of the same response. It never
 * re-orders or filters, never reads `pending_exit_directives` (C22, T27), and
 * renders nothing when the block is null, absent or has no rows.
 *
 * Presentation follows work/art/2026-11-04-待執行出清指令區塊-視覺規範.md r1
 * section 1.3 (class skeleton). Do not add truncation, overflow, sticky,
 * break-all, aria-label, title or aria-describedby here. `whitespace-nowrap` is allowed only on the
 * ISO date span built by `withNoBreakDates` (spec r1 section 7 exception); never
 * on a container.
 */
export function PendingExitBlock() {
  const today = usePlaybookToday(true);
  const titleId = useId();
  const labelPrefix = useId();
  if (!today.isSuccess) return null;
  const data = today.data;
  const block = data.pending_exit_block;
  if (block === null || block === undefined || !hasPendingExitRows(block)) return null;
  const labelId = (kind: string) => `${labelPrefix}-${kind}`;

  return (
    <section data-testid="pending-exit-block" aria-labelledby={titleId} className="mb-6 mt-6">
      <h2 id={titleId} className="text-lg font-semibold text-neutral-100">
        {block.title}
      </h2>
      <p className="mt-2 break-words text-sm text-neutral-300">
        {withNoBreakDates(leadWithReadAt(block.lead_template, data.as_of))}
      </p>

      {block.sections.map((s) => (
        <section
          key={s.kind}
          data-kind={s.kind}
          aria-labelledby={s.label !== null ? labelId(s.kind) : undefined}
          className={s.kind === "stale" ? "mt-6 border-t-2 border-neutral-500 pt-4" : "mt-4"}
        >
          {s.label !== null && (
            <h3 id={labelId(s.kind)} className="text-sm font-semibold text-neutral-100">
              {s.label}
            </h3>
          )}
          <p className={`${s.label !== null ? "mt-1 " : ""}break-words text-sm text-neutral-300`}>
            {withNoBreakDates(s.lead)}
          </p>
          <ul className="mt-2 divide-y divide-neutral-800 border-y border-neutral-800">
            {s.rows.map((r) => (
              <li key={`${r.symbol}-${r.batch_no}`} data-testid="pending-exit-row" className="py-3">
                <p className="break-words text-sm text-neutral-100">{withNoBreakDates(r.text)}</p>
                {r.notes.map((n, i) => (
                  <p key={i} className="mt-1 break-words text-sm text-neutral-300">
                    {withNoBreakDates(n)}
                  </p>
                ))}
                {r.entry_before_exit_note !== null && (
                  <p className="mt-1 break-words text-sm text-neutral-300">
                    {withNoBreakDates(r.entry_before_exit_note)}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}

      {block.closing_notes.map((c, i) => (
        <p
          key={i}
          data-testid="pending-exit-closing"
          className="mt-4 break-words text-sm text-neutral-300"
        >
          {withNoBreakDates(c)}
        </p>
      ))}
    </section>
  );
}
