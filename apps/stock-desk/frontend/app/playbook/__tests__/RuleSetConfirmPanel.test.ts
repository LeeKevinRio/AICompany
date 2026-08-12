/**
 * 五輪定稿 (2026-08-12) anti-drift guard for the 確認規則集 block's two
 * risk-compliance-approved sentence groups.
 *
 * The ruling gave dev a choice: render these sentences from the backend, or
 * keep them in the component and pin them with a front-end test. They stayed in
 * the component (they describe what *this screen's button* does, and there is no
 * endpoint whose job that is), so this suite is the other half of that choice:
 * it renders the block and asserts the approved text against the **rendered
 * output**, not against a constant the component imports — a test that shared a
 * constant with the code it guards would agree with any rewording.
 *
 * The literals below are therefore deliberately typed out a second time. They
 * are copied from 「五輪定稿(2026-08-12)」 in
 * `work/reviews/快市排程-風控前置意見.md` and may not be edited to make a test
 * pass: a failure here means the screen drifted from the approved wording, and
 * the fix is either the screen or a new ruling.
 *
 * `componentWordingScan.test.ts` already scans this component's source for
 * §1.3 banned terms; that scan and this one answer different questions
 * (「有沒有寫進禁用詞」 vs 「核可的句子還在不在、字面有沒有變」).
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { PlaybookRuleSetResponse } from "../../lib/types";

/** ⑥ sentence 1, verbatim. */
const CONFIRM_SENTENCE_1 = "確認即表示這份規則集為你本人設定。";

/** ⑥ sentence 2, verbatim. */
const CONFIRM_SENTENCE_2 =
  "確認之後，帳冊裡的每一筆指令，都是你自行設定的規則之機械執行結果，非本系統的判斷或建議。";

/** ⑥ 核心子句: the verbatim-protected region inside sentence 2. */
const CORE_CLAUSE = "你自行設定的規則之機械執行結果，非本系統的判斷或建議";

/** ④ 資金用途句, verbatim, with the backend-supplied ratio string substituted. */
function capitalUseSentence(deployRatioPct: string): string {
  return (
    `這個金額同時設定為你目前可動用的現金；系統會以「此金額 ×${deployRatioPct}」` +
    "計算出部署資金（TOTAL_DEPLOY），之後每一批進場的股數都以這筆部署資金為基礎換算。"
  );
}

const state = vi.hoisted(() => ({ deployRatioPct: "70%" }));

vi.mock("../../lib/queries", () => ({
  usePlaybookRuleSet: () => ({
    isPending: false,
    isError: false,
    isSuccess: true,
    error: null,
    data: ruleSet(state.deployRatioPct),
  }),
  useConfirmPlaybookRules: () => ({
    mutate: () => undefined,
    isPending: false,
    isError: false,
    error: null,
  }),
}));

const { RuleSetConfirmPanel } = await import("../RuleSetConfirmPanel");

function ruleSet(deployRatioPct: string): PlaybookRuleSetResponse {
  return {
    user_authored: false,
    rules_version: null,
    rules_effective_date: null,
    attribution: "目前使用的是系統預設規則集，尚無你本人的設定或修改紀錄。",
    rules: [{ rule_id: "R1", text: "R1 排程日進場：排程日買進該檔下一批。" }],
    params: [{ field: "deploy_ratio", value: "0.70" }],
    deploy_ratio_pct: deployRatioPct,
    cash: "0",
    total_deploy: "0",
    total_deploy_set_at: null,
    total_deploy_source: null,
    as_of: "2026-08-12T00:00:00+00:00",
  };
}

function render(deployRatioPct = "70%"): string {
  state.deployRatioPct = deployRatioPct;
  return renderToStaticMarkup(createElement(RuleSetConfirmPanel));
}

describe("RuleSetConfirmPanel — ⑥ 同意兩句 (五輪定稿逐字)", () => {
  it("renders both approved sentences verbatim", () => {
    const markup = render();

    expect(markup).toContain(CONFIRM_SENTENCE_1);
    expect(markup).toContain(CONFIRM_SENTENCE_2);
  });

  it("keeps the 核心子句 in one piece, unsplit and unabbreviated", () => {
    expect(render()).toContain(CORE_CLAUSE);
  });

  it("puts both sentences before the capital field and the button", () => {
    const markup = render();

    const sentenceOne = markup.indexOf(CONFIRM_SENTENCE_1);
    const sentenceTwo = markup.indexOf(CONFIRM_SENTENCE_2);
    const field = markup.indexOf('id="playbook-capital"');
    const button = markup.indexOf("確認規則集並設定資本額");

    expect(sentenceOne).toBeGreaterThanOrEqual(0);
    expect(sentenceOne).toBeLessThan(sentenceTwo);
    expect(sentenceTwo).toBeLessThan(field);
    expect(field).toBeLessThan(button);
  });

  it("no longer carries the superseded single-sentence version", () => {
    expect(render()).not.toContain("之後的指令將以此為據");
  });
});

describe("RuleSetConfirmPanel — ④ 資金用途句 (五輪定稿逐字)", () => {
  it("renders the approved sentence verbatim next to the capital field", () => {
    expect(render("70%")).toContain(capitalUseSentence("70%"));
  });

  it("substitutes the backend string as it stands: no ×100, no self-appended %", () => {
    // A client that scaled or re-formatted the ratio would show 「×0.7」,
    // 「×7000%」 or 「×70%%」 here; the backend already sent 「70%」.
    const markup = render("70%");
    expect(markup).toContain("×70%」");
    expect(markup).not.toContain("×0.7");
    expect(markup).not.toContain("%%");
  });

  it("follows the parameter version rather than a hard-coded number", () => {
    const markup = render("12.5%");

    expect(markup).toContain(capitalUseSentence("12.5%"));
    expect(markup).not.toContain("70%");
  });

  it("is always on screen: never a placeholder, a tooltip or an error-only hint", () => {
    const markup = render();

    expect(markup).not.toContain("placeholder=");
    expect(markup).not.toContain("title=");
    // 「分母」 is the framing the ruling forbade for this sentence.
    expect(markup).not.toContain("分母");
  });
});
