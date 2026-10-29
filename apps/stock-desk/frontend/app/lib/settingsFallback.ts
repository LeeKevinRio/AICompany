/**
 * Settings-section fallback (ADR-0032, N-156): the front end's half.
 *
 * Every sentence about a fallback comes from the backend
 * (`SettingsResponse.settings_fallback`, `partial_save_notice`, the 409
 * `detail`, `settings_fallback_notice`) and is rendered verbatim (K-6). This
 * module composes none of them. It holds only
 *
 *   - the two literals 風控 2026-10-29 N-156 字面定稿 第 1 項 fixed for the
 *     net-worth section and the backend does not send (badge, current value);
 *   - the pure decisions around the PUT body (K-11) and the order of the two
 *     confirmations (DL-6), so they are unit-tested without a DOM.
 *
 * Whether a section fell back is read from `settings_fallback.sections` and
 * nowhere else: never from a value, a freshness string or a default.
 */

import { resolveWideningSubmitForFields, type CapWidening } from "./riskWidening";
import type { AppSettingsPatch, SettingsFallbackView, SettingsResponse } from "./types";

/** 風控 第 1 項 table, row「NetWorthSection 徽章」. */
export const NET_WORTH_FALLBACK_BADGE_LABEL = "使用預設值";

/** 風控 第 1 項 table, row「目前儲存的數值：」. */
export const NET_WORTH_FALLBACK_VALUE_LABEL = "無法顯示";

/** The three sections `SettingsForm` saves; `net_worth` has its own form. */
export const FORM_SECTION_IDS = ["risk_budget", "cost_model", "alerts"] as const;
export type FormSectionId = (typeof FORM_SECTION_IDS)[number];

/** The fallback sections of a response, or none. */
export function fallbackSectionsOf(fallback: SettingsFallbackView | null): readonly string[] {
  return fallback === null ? [] : fallback.sections;
}

/** Whether `section` fell back, judged by `settings_fallback.sections` only. */
export function isFallbackSection(settings: SettingsResponse, section: string): boolean {
  return fallbackSectionsOf(settings.settings_fallback).includes(section);
}

/** The line under `section`'s h2, or `null` when it did not fall back. */
export function sectionMarkerOf(settings: SettingsResponse, section: string): string | null {
  if (!isFallbackSection(settings, section)) return null;
  return settings.settings_fallback?.section_markers[section] ?? null;
}

/** The `SettingsForm` sections that fell back, in the backend's order. */
export function formFallbackSections(settings: SettingsResponse): FormSectionId[] {
  return FORM_SECTION_IDS.filter((section) => isFallbackSection(settings, section));
}

/**
 * Which of the form's sections a save carries (K-11): a section that did not
 * fall back always; one that did only when the user confirmed overwriting it.
 * An unconfirmed fallback section is not in the PUT body at all, so what the
 * page shows for it (a default, not the stored content) can never be written.
 */
export function carriedFormSections(
  fallback: readonly FormSectionId[],
  confirmed: ReadonlySet<string>,
): { carried: FormSectionId[]; overwrite: FormSectionId[] } {
  const overwrite = fallback.filter((section) => confirmed.has(section));
  const carried = FORM_SECTION_IDS.filter(
    (section) => !fallback.includes(section) || confirmed.has(section),
  );
  return { carried, overwrite };
}

/**
 * What a `SettingsForm` submit does next. The order is fixed (DL-6):
 *
 *   1. the overwrite panel, while fallback sections exist and the user has not
 *      answered it;
 *   2. only then the existing widening confirmation, and only for a risk budget
 *      that this save actually carries (an unconfirmed fallback risk budget is
 *      not written, so there is nothing to widen);
 *   3. the write.
 *
 * `confirmed` is `null` until the panel has been answered.
 */
export type FormSaveStep =
  | { action: "open_overwrite_panel" }
  | { action: "confirm_widening"; pending: Partial<Record<string, CapWidening>> }
  | { action: "write"; carried: FormSectionId[]; overwrite: FormSectionId[] };

export function resolveFormSaveStep(input: {
  fallback: readonly FormSectionId[];
  confirmed: ReadonlySet<string> | null;
  /** The raise each widening-gated risk-budget field would write, as typed. */
  widenings: Record<string, CapWidening | null>;
  /** The raises the widening confirmation is currently showing. */
  shown: Partial<Record<string, CapWidening>>;
}): FormSaveStep {
  if (input.fallback.length > 0 && input.confirmed === null) {
    return { action: "open_overwrite_panel" };
  }
  const { carried, overwrite } = carriedFormSections(input.fallback, input.confirmed ?? new Set());
  const widenings = carried.includes("risk_budget") ? input.widenings : {};
  const decision = resolveWideningSubmitForFields(widenings, input.shown);
  if (decision.action === "confirm") {
    return { action: "confirm_widening", pending: decision.pending };
  }
  return { action: "write", carried, overwrite };
}

/**
 * The PUT body for a form save: only the carried sections, and
 * `overwrite_fallback_sections` only when something is being overwritten.
 */
export function buildFormPatch(
  sections: Pick<AppSettingsPatch, FormSectionId>,
  carried: readonly FormSectionId[],
  overwrite: readonly FormSectionId[],
): AppSettingsPatch {
  const patch: AppSettingsPatch = {};
  for (const section of carried) {
    const value = sections[section];
    if (value === undefined) continue;
    Object.assign(patch, { [section]: value });
  }
  if (overwrite.length > 0) patch.overwrite_fallback_sections = [...overwrite];
  return patch;
}

/**
 * The PUT body for a net-worth save. `overwrite` names the section only once
 * the user confirmed the overwrite panel; otherwise the body is exactly what it
 * always was (and the backend refuses a fallback section with a 409 that
 * writes nothing).
 */
export function buildNetWorthPatch(amount: number, overwrite: boolean): AppSettingsPatch {
  const patch: AppSettingsPatch = { net_worth: { total_net_worth_twd: amount } };
  if (overwrite) patch.overwrite_fallback_sections = ["net_worth"];
  return patch;
}
