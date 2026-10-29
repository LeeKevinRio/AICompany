/**
 * #61 batch one, plan D (CEO #62, 2026-10-26): the Kelly sunset on screen —
 * cap 5's「計算方式有誤」line after its detail (日落期間字面表, required) and
 * the two paused write controls. The Kelly lead (#3) is pinned in
 * `kellyGuidanceSentencePairing.test.ts`.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RiskGaugeView } from "../../components/RiskGauge";
import { LimitsCheckList } from "../../position/[symbol]/LimitsCheckList";
import { KellyManualInputForm } from "../../settings/KellyManualInputForm";
import { CAP5_SUNSET_UNRELIABLE_NOTE, showsCap5SunsetNote } from "../cap1SunsetWording";
import type { BookLimitCheck, LimitCheck, LimitStatus, PortfolioLimitsResponse } from "../types";

function bookCheck(overrides: Partial<BookLimitCheck>): BookLimitCheck {
  return {
    index: 1,
    limit_id: "single_position_weight",
    name: "單一標的佔比上限",
    status: "violated",
    observed: 0.12,
    threshold: 0.1,
    detail: "detail",
    worst_symbol: "2330",
    evaluated_count: 3,
    violated_count: 2,
    excluded: [],
    ...overrides,
  };
}

function gauge(limits: BookLimitCheck[], notice: string | null): string {
  const data: PortfolioLimitsResponse = {
    limits,
    notes: [],
    sources: [],
    cap1_migration_notice: notice,
    as_of: "2026-10-27T00:00:00Z",
  };
  return renderToStaticMarkup(createElement(RiskGaugeView, { data }));
}

const CAP5: BookLimitCheck = bookCheck({
  index: 5,
  limit_id: "kelly_fraction",
  name: "分數 Kelly 部位上限",
  status: "passed",
  observed: 0.05,
  worst_symbol: null,
  violated_count: 0,
  detail: "CAP5_DETAIL",
});

describe("cap 5 sunset line (日落期間字面表)", () => {
  it("is the approved sentence verbatim", () => {
    expect(CAP5_SUNSET_UNRELIABLE_NOTE).toBe("計算方式有誤，算出的數字不可靠。");
  });

  it.each<[LimitStatus, boolean]>([
    ["passed", true],
    ["violated", true],
    ["not_evaluable", false],
  ])("cap 5 %s -> shown: %s", (status, shown) => {
    expect(showsCap5SunsetNote("kelly_fraction", status)).toBe(shown);
    expect(showsCap5SunsetNote("single_position_weight", status)).toBe(false);
  });

  it("follows cap 5's detail in the gauge's details list", () => {
    const html = gauge([bookCheck({}), CAP5], null);
    expect(html.indexOf(CAP5_SUNSET_UNRELIABLE_NOTE)).toBeGreaterThan(html.indexOf("CAP5_DETAIL"));
    const blocked = gauge([bookCheck({}), { ...CAP5, status: "not_evaluable" }], null);
    expect(blocked).not.toContain(CAP5_SUNSET_UNRELIABLE_NOTE);
  });
});

function limit(overrides: Partial<LimitCheck>): LimitCheck {
  return {
    index: 1,
    id: "single_position_weight",
    name: "單一標的佔比上限",
    status: "violated",
    detail: "CAP1_DETAIL",
    observed: 0.12,
    threshold: 0.1,
    ...overrides,
  };
}

describe("LimitsCheckList cap 5 line", () => {
  it("follows cap 5's detail and only while cap 5 is passed or violated", () => {
    const cap5 = limit({ index: 5, id: "kelly_fraction", name: "分數 Kelly 部位上限", status: "violated", detail: "CAP5_DETAIL" });
    const html = renderToStaticMarkup(createElement(LimitsCheckList, { limits: [limit({}), cap5] }));
    expect(html.indexOf(CAP5_SUNSET_UNRELIABLE_NOTE)).toBeGreaterThan(html.indexOf("CAP5_DETAIL"));
    const blocked = renderToStaticMarkup(
      createElement(LimitsCheckList, { limits: [{ ...cap5, status: "not_evaluable" }] }),
    );
    expect(blocked).not.toContain(CAP5_SUNSET_UNRELIABLE_NOTE);
  });
});

describe("paused Kelly manual submit (plan D)", () => {
  it("shows the backend's paused label and is disabled", () => {
    const html = renderToStaticMarkup(
      createElement(
        QueryClientProvider,
        { client: new QueryClient() },
        createElement(KellyManualInputForm, {
          symbol: "2330",
          market: "TW",
          current: null,
          writesPausedLabel: "PAUSED_STAND_IN",
        }),
      ),
    );
    expect(html).toMatch(/<button type="submit" disabled=""[^>]*>PAUSED_STAND_IN<\/button>/);
  });
});

describe("paused Kelly import trigger (plan D)", () => {
  const source = readFileSync(
    fileURLToPath(new URL("../../settings/KellyImportDialog.tsx", import.meta.url)),
    "utf-8",
  );

  it("labels the trigger with the backend's paused label (also its aria-label) and disables it", () => {
    expect(source).toContain(
      "const triggerLabel = disclosures.writes_paused_label ?? disclosures.import_trigger_label;",
    );
    expect(source).toContain("aria-label={triggerLabel}");
    expect(source).toContain("disabled={writesPaused || mutation.isPending");
  });
});
