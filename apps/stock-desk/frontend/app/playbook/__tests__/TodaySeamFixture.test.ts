/**
 * SEAM-T8 (ADR-0035 補充四 S-4): the 排程台 renders a `/today` body from a
 * backend that predates the seam -- no `pending_exit_directives`,
 * `entry_before_exit_directives`, `entry_before_exit_blocked_directives`, and
 * no `entry_before_exit_note` on any directive line -- without an error, and
 * renders it exactly as it renders the same body with the new keys present and
 * empty. No view reads the new keys yet.
 *
 * The old bodies are the ones the backend recorded on the pre-seam code
 * (`backend/tests/golden/seam/pre_seam_responses.json`, SEAM-T2), so the
 * fixture is a real response shape rather than a hand-written one.
 */
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type {
  PlaybookDirectiveLine,
  PlaybookRuleSetResponse,
  PlaybookTodayResponse,
} from "../../lib/types";

const state = vi.hoisted(() => ({ today: undefined as unknown }));

const RULE_SET: PlaybookRuleSetResponse = {
  user_authored: false,
  rules_version: null,
  rules_effective_date: null,
  attribution: "SENTINEL-RULESET-ATTRIBUTION",
  rules: [{ rule_id: "R1", text: "SENTINEL-RULE-TEXT" }],
  params: [{ field: "SENTINEL-PARAM-FIELD", value: "SENTINEL-PARAM-VALUE" }],
  deploy_ratio_pct: "70%",
  cash: "0",
  total_deploy: "0",
  total_deploy_set_at: null,
  total_deploy_source: null,
  as_of: "2026-08-11T00:00:00+00:00",
};

vi.mock("../../lib/queries", () => ({
  usePlaybookToday: () => ({
    isPending: false,
    isError: false,
    isSuccess: true,
    error: null,
    data: state.today,
  }),
  usePlaybookRuleSet: () => ({
    isPending: false,
    isError: false,
    isSuccess: true,
    error: null,
    data: RULE_SET,
  }),
  useConfirmPlaybookRules: () => ({
    mutate: () => undefined,
    isPending: false,
    isError: false,
    error: null,
  }),
  useEmergencyExit: () => ({
    mutate: () => undefined,
    reset: () => undefined,
    isPending: false,
    isError: false,
    error: null,
  }),
}));

const { default: PlaybookPage } = await import("../page");
// The page reads the exit receipt store (ADR-0037), mounted by `providers.tsx` in the app.
const { ExitReceiptStoreProvider } = await import("../../lib/exitReceiptContext");

const SEAM_LISTS = [
  "pending_exit_directives",
  "entry_before_exit_directives",
  "entry_before_exit_blocked_directives",
] as const;

type Recorded = Record<string, Record<string, Record<string, unknown>>>;

const RECORDED = JSON.parse(
  readFileSync(
    new URL("../../../../backend/tests/golden/seam/pre_seam_responses.json", import.meta.url),
    "utf8",
  ),
) as Recorded;

/** A recorded pre-seam body, with the `as_of` stamps the record dropped put back. */
function preSeam(scenario: string, name: string): PlaybookTodayResponse {
  const recorded = RECORDED[scenario]?.[name];
  if (recorded === undefined) throw new Error(`no recorded body ${scenario}/${name}`);
  const body = recorded as unknown as PlaybookTodayResponse;
  const settlement = body.settlement;
  return {
    ...body,
    settlement: settlement === null ? null : { ...settlement, as_of: "2026-08-11T00:00:00+00:00" },
    as_of: "2026-08-11T00:00:00+00:00",
  };
}

/** The same body as a seam backend sends it: new lists empty, every note `null`. */
function withSeamKeys(body: PlaybookTodayResponse): PlaybookTodayResponse {
  const noted = (line: PlaybookDirectiveLine): PlaybookDirectiveLine => ({
    ...line,
    entry_before_exit_note: null,
  });
  return {
    ...body,
    directives: body.directives.map(noted),
    pending_exit_directives: [],
    entry_before_exit_directives: [],
    entry_before_exit_blocked_directives: [],
  };
}

function render(body: PlaybookTodayResponse): string {
  state.today = body;
  return renderToStaticMarkup(
    createElement(ExitReceiptStoreProvider, null, createElement(PlaybookPage)),
  );
}

const CASES: [string, string][] = [
  ["authored", "today"],
  ["after_exit", "today"],
  ["after_exit", "today_next_day"],
  ["unauthored", "today"],
];

describe("SEAM-T8: a pre-seam /today body", () => {
  it.each(CASES)("%s / %s lacks every new key", (scenario, name) => {
    const body = preSeam(scenario, name) as unknown as Record<string, unknown>;
    for (const key of SEAM_LISTS) expect(key in body).toBe(false);
    for (const line of preSeam(scenario, name).directives) {
      expect("entry_before_exit_note" in line).toBe(false);
    }
  });

  it.each(CASES)("%s / %s renders, and renders as the seam body does", (scenario, name) => {
    const old = preSeam(scenario, name);
    const markup = render(old);
    expect(markup).toContain("排程台");
    expect(markup).not.toContain("無法載入排程台資料");
    expect(render(withSeamKeys(old))).toBe(markup);
  });

  it("the fixtures exercise a ledger line and a settlement", () => {
    expect(preSeam("authored", "today").directives.length).toBeGreaterThan(0);
    expect(preSeam("after_exit", "today_next_day").settlement?.executed).toBeGreaterThan(0);
  });
});
