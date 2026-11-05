import { Fragment, type ReactNode } from "react";

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
 * Shared by every surface that renders `entry_before_exit_*` (N-171, N-168).
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
