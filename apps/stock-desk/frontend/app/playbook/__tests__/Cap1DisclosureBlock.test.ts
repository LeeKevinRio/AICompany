/**
 * N-155 前端守門 (ADR-0031 F-1 ~ F-4; 風控 2026-10-28 #68 裁決 section 2.2 and its
 * supplement section 3): the 排程台 x 第 1 條 disclosure block.
 *
 * The backend composes every sentence and number; this suite pins the other
 * half of that contract: the screen shows exactly what it was sent, in order,
 * once per screen, and never decides on its own whether or what to show.
 *
 * Sentinel strings are used on purpose (F-1). A fixture holding the real
 * approved sentences would let a component that re-composed them pass; a
 * sentinel can only come out of the component if it was passed through
 * untouched, and any digit or extra word in the block is a visible leak.
 * The verbatim approved wording is guarded on the backend, not here.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type {
  PlaybookCap1Disclosure,
  PlaybookMode,
  PlaybookRuleSetResponse,
  PlaybookTodayResponse,
} from "../../lib/types";

const state = vi.hoisted(() => ({
  today: undefined as unknown,
  ruleSet: undefined as unknown,
}));

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
    data: state.ruleSet,
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

const { Cap1DisclosureBlock } = await import("../Cap1DisclosureBlock");
const { default: PlaybookPage } = await import("../page");
const { RuleSetConfirmPanel } = await import("../RuleSetConfirmPanel");
const { ModeStatusBar } = await import("../ModeStatusBar");

const SRC_ROOT = fileURLToPath(new URL("../../", import.meta.url));

function source(relativeToApp: string): string {
  return readFileSync(join(SRC_ROOT, relativeToApp), "utf8");
}

/* --- Fixtures ---------------------------------------------------------------
 * Sentinels carry no digit and no percent sign, so "no extra number" can be
 * asserted as a plain character-class check on the block's text. */

function disclosure(tag: string): PlaybookCap1Disclosure {
  return {
    title: `SENTINEL-${tag}-TITLE`,
    lines: [
      `SENTINEL-${tag}-LINE-ALPHA`,
      `SENTINEL-${tag}-LINE-BRAVO`,
      `SENTINEL-${tag}-LINE-CHARLIE`,
      `SENTINEL-${tag}-LINE-DELTA`,
    ],
    per_target_pct: "X%",
    cap1_pct: "X%",
    per_target_book_pct: "X%",
  };
}

const TODAY_DISCLOSURE = disclosure("TODAY");
const RULESET_DISCLOSURE = disclosure("RULESET");

const ATTRIBUTION = "SENTINEL-ATTRIBUTION";
const SUMMARY = ["SENTINEL-SUMMARY-ONE", "SENTINEL-SUMMARY-TWO", "SENTINEL-SUMMARY-THREE"];
const WARNING = "SENTINEL-WARNING";
const LEDGER_HEADING = "今日指令帳冊";
const CONFIRM_SENTENCE_1 = "確認即表示這份規則集為你本人設定。";

function today(
  mode: PlaybookMode,
  cap1: PlaybookCap1Disclosure | undefined,
): PlaybookTodayResponse {
  const response: PlaybookTodayResponse = {
    data_date: "2026-10-27",
    execution_date: "2026-10-28",
    mode,
    mode_label: "SENTINEL-MODE-LABEL",
    mode_reason: "SENTINEL-MODE-REASON",
    is_schedule_day: true,
    fast_market: {
      active: false,
      annualized_vol_20d: null,
      large_move_days: 0,
      reason: null,
      carried_forward: false,
      measured_on: null,
      carried_note: null,
    },
    rules_version: 1,
    rules_effective_date: null,
    page_summary: SUMMARY,
    directives: [],
    snapshot: [],
    warnings: [WARNING],
    rules_fully_evaluated: true,
    no_directive_note: null,
    attribution: ATTRIBUTION,
    settlement: null,
    exit_confirm: null,
    as_of: "2026-10-28T00:00:00+00:00",
  };
  return cap1 === undefined ? response : { ...response, cap1_disclosure: cap1 };
}

function ruleSet(cap1: PlaybookCap1Disclosure | undefined): PlaybookRuleSetResponse {
  const response: PlaybookRuleSetResponse = {
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
    as_of: "2026-10-28T00:00:00+00:00",
  };
  return cap1 === undefined ? response : { ...response, cap1_disclosure: cap1 };
}

/** `"absent"` = the backend did not send the field (older backend). */
function renderPage(
  mode: PlaybookMode,
  todayCap1: PlaybookCap1Disclosure | "absent" = TODAY_DISCLOSURE,
  ruleSetCap1: PlaybookCap1Disclosure | "absent" = RULESET_DISCLOSURE,
): string {
  state.today = today(mode, todayCap1 === "absent" ? undefined : todayCap1);
  state.ruleSet = ruleSet(ruleSetCap1 === "absent" ? undefined : ruleSetCap1);
  return renderToStaticMarkup(createElement(PlaybookPage));
}

function renderBlock(value: PlaybookCap1Disclosure | undefined, level: 2 | 3 = 2): string {
  return renderToStaticMarkup(
    createElement(Cap1DisclosureBlock, { disclosure: value, headingLevel: level }),
  );
}

/** The block's own markup: the only element on these screens carrying `aria-labelledby`. */
function blockMarkup(markup: string): string {
  const match = /<section aria-labelledby="[^"]*"[\s\S]*?<\/section>/.exec(markup);
  if (match === null) throw new Error("disclosure block not found in markup");
  return match[0];
}

/** Text nodes of a markup fragment, in document order. */
function textNodes(markup: string): string[] {
  return [...markup.matchAll(/>([^<]+)</g)].map((m) => m[1] ?? "");
}

function count(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

const ALL_MODES: PlaybookMode[] = ["normal", "defense", "frozen", "emergency_frozen", "unconfirmed"];
const NON_UNCONFIRMED: PlaybookMode[] = ["normal", "defense", "frozen", "emergency_frozen"];

/* --- F-1 ------------------------------------------------------------------- */

describe("F-1 哨兵：區塊只渲染後端給的 title 與 lines", () => {
  it("F-1 renders exactly the title then each line, in order, and nothing else", () => {
    const block = blockMarkup(renderBlock(TODAY_DISCLOSURE));

    expect(textNodes(block)).toEqual([TODAY_DISCLOSURE.title, ...TODAY_DISCLOSURE.lines]);
  });

  it("F-1 shows no number: no digit and none of the X% pct sentinels leak out", () => {
    const block = blockMarkup(renderBlock(TODAY_DISCLOSURE));
    const text = textNodes(block).join("\n");

    expect(text).not.toMatch(/\d/);
    expect(text).not.toContain("X%");
    expect(text).not.toContain("%");
  });

  it("F-1 follows the received order and length rather than any fixed shape", () => {
    const reordered: PlaybookCap1Disclosure = {
      ...TODAY_DISCLOSURE,
      lines: ["SENTINEL-Z", "SENTINEL-A", "SENTINEL-A", "SENTINEL-M", "SENTINEL-Q", "SENTINEL-B"],
    };
    const block = blockMarkup(renderBlock(reordered));

    expect(textNodes(block)).toEqual([reordered.title, ...reordered.lines]);
  });

  it("F-1 keeps the title and lines intact on the real screens (today page and confirm panel)", () => {
    const page = blockMarkup(renderPage("normal"));
    expect(textNodes(page)).toEqual([TODAY_DISCLOSURE.title, ...TODAY_DISCLOSURE.lines]);

    const panelPage = blockMarkup(renderPage("unconfirmed"));
    expect(textNodes(panelPage)).toEqual([RULESET_DISCLOSURE.title, ...RULESET_DISCLOSURE.lines]);
  });

  it("F-1 does not display rules_version or any pct field of the disclosure", () => {
    const withExtra = {
      ...TODAY_DISCLOSURE,
      rules_version: 987654,
      per_target_pct: "SENTINEL-PCT-A",
      cap1_pct: "SENTINEL-PCT-B",
      per_target_book_pct: "SENTINEL-PCT-C",
    };
    const markup = renderBlock(withExtra);

    expect(markup).not.toContain("SENTINEL-PCT");
    expect(markup).not.toContain("987654");
  });
});

/* --- F-2 ------------------------------------------------------------------- */

/** Block and line comments removed, so the template-literal check looks at code only. */
function stripComments(code: string): string {
  return code.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

describe("F-2 靜態掃描：元件不換算、不 parse、不拼句、不寫死字面", () => {
  const FORBIDDEN_TOKENS = [
    "deploy_ratio",
    "n_targets",
    "max_position_weight",
    "params",
    "parseFloat",
    "Number(",
    "toFixed",
  ];
  const blockSource = source("playbook/Cap1DisclosureBlock.tsx");

  it("F-2 the component file contains none of the forbidden identifiers", () => {
    for (const token of FORBIDDEN_TOKENS) {
      expect(blockSource, `Cap1DisclosureBlock.tsx must not contain ${token}`).not.toContain(token);
    }
  });

  it("F-2 the component has no template literal (comments aside) and no string concatenation", () => {
    const code = stripComments(blockSource);

    expect(code).not.toContain("`");
    expect(code).not.toMatch(/["']\s*\+|\+\s*["']/);
    expect(code).not.toMatch(/\.join\(|\.replace\(|\.split\(|\.slice\(|\.substring\(/);
    expect(code).not.toMatch(/parseInt|parseFloat|Number\(|toFixed|toLocale|Math\./);
  });

  it("F-2 the component hard-codes no Han text outside comments", () => {
    expect(stripComments(blockSource)).not.toMatch(/[一-鿿　-〿＀-￯]/);
  });

  it("F-2 the callers never wrap a disclosure field in a template literal", () => {
    for (const file of ["playbook/page.tsx", "playbook/RuleSetConfirmPanel.tsx"]) {
      const lines = source(file)
        .split("\n")
        .filter((line) => line.includes("cap1_disclosure") && !line.trim().startsWith("*"));
      expect(lines.length, `${file} should pass cap1_disclosure to the block`).toBeGreaterThan(0);
      for (const line of lines) expect(line).not.toContain("`");
    }
  });

  it("F-2 presentation floor: text-sm on neutral-300, neutral palette, no fold, tooltip, dismiss or icon", () => {
    const code = stripComments(blockSource);

    expect(code).toContain("text-sm");
    expect(code).toContain("text-neutral-300");
    expect(code).not.toMatch(/text-(xs|\[)/);
    expect(code).not.toMatch(/text-neutral-(400|500|600|700)/);
    expect(code).not.toMatch(/amber|red|rose|orange|yellow|emerald|indigo/);
    expect(code).not.toMatch(/<details|<summary|<button|<svg|<img|title=|aria-hidden|onClick|useState|role=/);
  });

  it("F-2 the rendered markup is a plain always-open section: no details, tooltip, button or icon", () => {
    const markup = renderBlock(TODAY_DISCLOSURE);

    expect(markup).not.toMatch(/<details|<summary|<button|<svg|<img|title=|hidden/);
    expect(markup).toContain("text-sm");
    expect(markup).toContain("text-neutral-300");
    expect(markup).not.toMatch(/amber|red-|rose-/);
  });
});

/* --- F-3 ------------------------------------------------------------------- */

describe("F-3 types.ts：揭露欄位只能是字串類", () => {
  const types = source("lib/types.ts");

  function interfaceBody(name: string): string {
    const match = new RegExp(`export interface ${name} \\{([\\s\\S]*?)\\n\\}`).exec(types);
    if (match === null) throw new Error(`interface ${name} not found in types.ts`);
    return match[1] ?? "";
  }

  it("F-3 PlaybookCap1Disclosure has exactly the five string-class fields", () => {
    const fields = interfaceBody("PlaybookCap1Disclosure")
      .split("\n")
      .filter((line) => !line.trim().startsWith("//") && line.trim() !== "")
      .map((line) => line.trim());

    expect(fields).toEqual([
      "title: string;",
      "lines: string[];",
      "per_target_pct: string | null;",
      "cap1_pct: string | null;",
      "per_target_book_pct: string | null;",
    ]);
  });

  it("F-3 carries no numeric, boolean, comparison or status field (and no rules_version)", () => {
    const body = interfaceBody("PlaybookCap1Disclosure");

    expect(body).not.toMatch(/:\s*(number|boolean)/);
    expect(body).not.toMatch(/exceeds|status|flag|rules_version|compare/i);
  });

  it("F-3 both responses carry it as an optional PlaybookCap1Disclosure (older backend omits it)", () => {
    expect(interfaceBody("PlaybookTodayResponse")).toContain(
      "cap1_disclosure?: PlaybookCap1Disclosure;",
    );
    expect(interfaceBody("PlaybookRuleSetResponse")).toContain(
      "cap1_disclosure?: PlaybookCap1Disclosure;",
    );
  });
});

/* --- F-4 ------------------------------------------------------------------- */

describe("F-4 渲染不看 mode 或比較結果", () => {
  it("F-4 confirmed (normal): the block renders on the today page", () => {
    const markup = renderPage("normal");

    expect(count(markup, TODAY_DISCLOSURE.title)).toBe(1);
    for (const line of TODAY_DISCLOSURE.lines) expect(count(markup, line)).toBe(1);
  });

  it("F-4 unconfirmed: the block renders inside the confirm panel", () => {
    const markup = renderPage("unconfirmed");

    expect(count(markup, RULESET_DISCLOSURE.title)).toBe(1);
    for (const line of RULESET_DISCLOSURE.lines) expect(count(markup, line)).toBe(1);
  });

  it("F-4 every mode renders its block exactly once (the host differs, the presence does not)", () => {
    for (const mode of ALL_MODES) {
      const markup = renderPage(mode);
      expect(count(markup, "SENTINEL-TODAY-TITLE") + count(markup, "SENTINEL-RULESET-TITLE"), mode).toBe(1);
      expect(count(markup, "<section aria-labelledby"), mode).toBe(1);
    }
  });

  it("F-4 the block does not depend on its own content: any title and lines are shown", () => {
    const variants: PlaybookCap1Disclosure[] = [
      { ...TODAY_DISCLOSURE, per_target_pct: null, cap1_pct: null, per_target_book_pct: null },
      { ...TODAY_DISCLOSURE, per_target_pct: "X%", cap1_pct: "Y%" },
      { ...TODAY_DISCLOSURE, lines: ["SENTINEL-ONLY-LINE"] },
    ];
    for (const variant of variants) {
      expect(textNodes(blockMarkup(renderBlock(variant)))).toEqual([variant.title, ...variant.lines]);
    }
  });

  it("F-4 the component takes no mode and its source never mentions one", () => {
    const code = stripComments(source("playbook/Cap1DisclosureBlock.tsx"));

    expect(code).not.toMatch(/\bmode\b|unconfirmed|normal|defense|frozen/);
    // The single permitted absence rule: the backend did not send the field.
    expect(code.match(/\bif\s*\(/g)).toHaveLength(1);
    expect(code).toContain("if (disclosure === undefined) return null;");
    // No other comparison or logical operator anywhere (the heading-level pick is a plain literal map).
    expect(code.match(/!==|===|<=|>=|&&|\|\||\?\?/g)).toEqual(["===", "==="]);
  });

  it("F-4 an absent field (older backend) renders nothing and invents nothing, in either host", () => {
    expect(renderBlock(undefined)).toBe("");

    for (const mode of ALL_MODES) {
      const markup = renderPage(mode, "absent", "absent");
      expect(markup, mode).not.toContain("<section aria-labelledby");
    }
  });

  it("F-4 unconfirmed never falls back to the /today copy when /rule-set sent none", () => {
    const markup = renderPage("unconfirmed", TODAY_DISCLOSURE, "absent");

    expect(markup).not.toContain(TODAY_DISCLOSURE.title);
    expect(markup).not.toContain("<section aria-labelledby");
  });
});

/* --- 位置：每個畫面恰好一次 --------------------------------------------------- */

describe("位置：每個畫面恰好一次，順序固定", () => {
  it("unconfirmed 時今日頁不重複出現 /today 那一份", () => {
    const markup = renderPage("unconfirmed");

    expect(markup).not.toContain(TODAY_DISCLOSURE.title);
    for (const line of TODAY_DISCLOSURE.lines) expect(markup).not.toContain(line);
    expect(count(markup, RULESET_DISCLOSURE.title)).toBe(1);
  });

  it("non-unconfirmed modes show only the /today copy and never the confirm panel's", () => {
    for (const mode of NON_UNCONFIRMED) {
      const markup = renderPage(mode);

      expect(count(markup, TODAY_DISCLOSURE.title), mode).toBe(1);
      expect(markup, mode).not.toContain(RULESET_DISCLOSURE.title);
      expect(markup, mode).not.toContain(CONFIRM_SENTENCE_1);
    }
  });

  it("today page order: 歸屬語 → page_summary → warnings → 本區塊 → DirectiveLedger (every non-unconfirmed mode)", () => {
    for (const mode of NON_UNCONFIRMED) {
      const markup = renderPage(mode);
      const at = {
        attribution: markup.indexOf(ATTRIBUTION),
        summary: markup.indexOf(SUMMARY[SUMMARY.length - 1] ?? ""),
        warning: markup.indexOf(WARNING),
        block: markup.indexOf(TODAY_DISCLOSURE.title),
        blockEnd: markup.indexOf(TODAY_DISCLOSURE.lines[TODAY_DISCLOSURE.lines.length - 1] ?? ""),
        ledger: markup.indexOf(LEDGER_HEADING),
      };

      expect(at.attribution, mode).toBeGreaterThanOrEqual(0);
      expect(at.attribution, mode).toBeLessThan(markup.indexOf(SUMMARY[0] ?? ""));
      expect(markup.indexOf(SUMMARY[0] ?? ""), mode).toBeLessThan(at.summary);
      expect(at.summary, mode).toBeLessThan(at.warning);
      expect(at.warning, mode).toBeLessThan(at.block);
      expect(at.blockEnd, mode).toBeLessThan(at.ledger);
    }
  });

  it("confirm panel order: 規則參數 → 本區塊 → ⑥ 同意句 → 資本欄", () => {
    const markup = renderPage("unconfirmed");
    const params = markup.indexOf("SENTINEL-PARAM-VALUE");
    const title = markup.indexOf(RULESET_DISCLOSURE.title);
    const lastLine = markup.indexOf(
      RULESET_DISCLOSURE.lines[RULESET_DISCLOSURE.lines.length - 1] ?? "",
    );
    const consent = markup.indexOf(CONFIRM_SENTENCE_1);
    const field = markup.indexOf('id="playbook-capital"');

    expect(params).toBeGreaterThanOrEqual(0);
    expect(params).toBeLessThan(title);
    expect(lastLine).toBeLessThan(consent);
    expect(consent).toBeLessThan(field);
  });

  it("the confirm panel renders its own block when mounted alone", () => {
    state.ruleSet = ruleSet(RULESET_DISCLOSURE);
    const markup = renderToStaticMarkup(createElement(RuleSetConfirmPanel));

    expect(count(markup, RULESET_DISCLOSURE.title)).toBe(1);
  });

  it("the block is not part of page_summary: the summary block stays exactly the backend's sentences", () => {
    const markup = renderPage("normal");
    const before = markup.slice(0, markup.indexOf(TODAY_DISCLOSURE.title));

    for (const sentence of SUMMARY) expect(count(before, sentence)).toBe(1);
    expect(SUMMARY).not.toContain(TODAY_DISCLOSURE.title);
    expect(source("playbook/page.tsx")).not.toMatch(/page_summary[^\n]*cap1|cap1[^\n]*page_summary/);
  });
});

/* --- EXIT 流程與其他禁區 --------------------------------------------------- */

describe("不得出現在 EXIT 流程、alerts、逐筆指令列、page_summary", () => {
  it("EXIT 流程元件內不出現本區塊（原始碼與渲染輸出）", () => {
    const exitSource = source("playbook/EmergencyExitControl.tsx");
    expect(exitSource).not.toMatch(/Cap1Disclosure|cap1_disclosure|cap1/i);

    state.today = today("normal", TODAY_DISCLOSURE);
    const statusBar = renderToStaticMarkup(
      createElement(ModeStatusBar, { today: state.today as PlaybookTodayResponse }),
    );
    expect(statusBar).toContain("全部出清");
    expect(statusBar).not.toContain(TODAY_DISCLOSURE.title);
    for (const line of TODAY_DISCLOSURE.lines) expect(statusBar).not.toContain(line);
  });

  it("the EXIT flow's props carry only exit_confirm, never the disclosure", () => {
    const statusBarSource = source("playbook/ModeStatusBar.tsx");

    expect(statusBarSource).toContain("<EmergencyExitControl exitConfirm={today.exit_confirm} />");
    expect(statusBarSource).not.toMatch(/Cap1Disclosure|cap1_disclosure/);
  });

  it("only page.tsx and RuleSetConfirmPanel.tsx use the block or read the field (no alerts, ledger row, snapshot, settlement)", () => {
    const allowed = new Set([
      "playbook/Cap1DisclosureBlock.tsx",
      "playbook/page.tsx",
      "playbook/RuleSetConfirmPanel.tsx",
      "lib/types.ts",
    ]);
    const offenders: string[] = [];

    function walk(dir: string): void {
      for (const name of readdirSync(dir)) {
        if (name === "node_modules" || name === ".next" || name === "__tests__") continue;
        const full = join(dir, name);
        if (statSync(full).isDirectory()) {
          walk(full);
          continue;
        }
        if (!/\.(ts|tsx)$/.test(name)) continue;
        const relative = full.slice(SRC_ROOT.length).replaceAll("\\", "/");
        if (allowed.has(relative)) continue;
        if (/Cap1DisclosureBlock|cap1_disclosure|PlaybookCap1Disclosure/.test(readFileSync(full, "utf8"))) {
          offenders.push(relative);
        }
      }
    }
    walk(SRC_ROOT);

    expect(offenders).toEqual([]);
  });

  it("DirectiveLedger rows and the 部位快照 never receive the disclosure", () => {
    for (const file of [
      "playbook/DirectiveLedger.tsx",
      "playbook/PositionSnapshotTable.tsx",
      "playbook/SettlementPanel.tsx",
      "components/AlertStatusStrip.tsx",
      "components/PendingAlertsPanel.tsx",
    ]) {
      expect(source(file), file).not.toMatch(/Cap1Disclosure|cap1_disclosure/);
    }
  });
});
