"use client";

import { useEffect, useRef } from "react";
import type { OverwritePanelView } from "../lib/types";

/**
 * The W-2 overwrite confirmation (ADR-0032; 風控 2026-10-29 N-156 字面定稿
 * 第 6 項), shared by the `SettingsForm` version (one checkbox per fallback
 * section) and the `NetWorthSection` version (no checkbox: its confirm button
 * is the confirmation).
 *
 * Title, paragraphs, checkbox labels and both button labels are the backend's
 * (`SettingsFallbackView.form_overwrite_panel` / `net_worth_overwrite_panel`),
 * rendered as sent. Nothing is pre-checked: a section is overwritten only when
 * the user ticks it. Focus moves to the panel when it opens, so a keyboard
 * user lands on the question they now have to answer.
 */
export function OverwritePanel({
  panel,
  checked,
  onToggle,
  onConfirm,
  onCancel,
  disabled,
}: {
  panel: OverwritePanelView;
  /** The sections currently ticked; the panel starts with none. */
  checked: ReadonlySet<string>;
  onToggle: (section: string, value: boolean) => void;
  onConfirm: () => void;
  onCancel: () => void;
  disabled: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);

  return (
    <div
      ref={ref}
      tabIndex={-1}
      role="group"
      aria-label={panel.title}
      className="mb-3 rounded-md border border-amber-700 bg-amber-950/50 px-4 py-3 text-sm text-amber-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300"
    >
      <p className="font-semibold">{panel.title}</p>
      {panel.paragraphs.map((paragraph, i) => (
        <p key={i} className="mt-1">
          {paragraph}
        </p>
      ))}
      {panel.checkboxes.length > 0 && (
        <ul className="mt-2 space-y-1">
          {panel.checkboxes.map((box) => (
            <li key={box.section}>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={checked.has(box.section)}
                  onChange={(e) => onToggle(box.section, e.target.checked)}
                  className="h-4 w-4"
                />
                {box.label}
              </label>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={onConfirm}
          className="rounded-md bg-neutral-100 px-3 py-1.5 text-sm font-medium text-neutral-900 hover:bg-white active:bg-neutral-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {panel.confirm_label}
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={onCancel}
          className="rounded-md border border-amber-700 px-3 py-1.5 text-sm text-amber-200 hover:bg-amber-900/40 active:bg-amber-900/60 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {panel.cancel_label}
        </button>
      </div>
    </div>
  );
}
