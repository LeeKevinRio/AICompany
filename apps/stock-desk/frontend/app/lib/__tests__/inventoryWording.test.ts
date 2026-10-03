import { describe, expect, it } from "vitest";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";
import * as wording from "../inventoryWording";
import { deleteButtonState } from "../positionFormSubmit";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";

/**
 * Pins every user-visible literal of the inventory page (PRD section 6,
 * visual spec section 8, risk-compliance second-pass sign-off 2026-10-03).
 */

describe("S1..S21 / V1..V3 literals are pinned verbatim", () => {
  it("S1 / S2 / S3: nav label, h1, header button", () => {
    expect(wording.INVENTORY_NAV_LABEL).toBe("庫存");
    expect(wording.INVENTORY_PAGE_TITLE).toBe("庫存");
    expect(wording.INVENTORY_ROUTE).toBe("/positions");
    expect(wording.INVENTORY_ADD_BUTTON).toBe("新增");
  });

  it("S4 / S5 / S6 and V1 / V2: row actions and pending labels", () => {
    expect(wording.ROW_EDIT_LABEL).toBe("修改");
    expect(wording.ROW_SAVE_LABEL).toBe("儲存");
    expect(wording.ROW_CANCEL_LABEL).toBe("取消");
    expect(wording.ROW_MORE_LABEL).toBe("更多");
    expect(wording.ROW_REMOVE_LABEL).toBe("移除");
    expect(wording.ROW_SAVING_LABEL).toBe("儲存中…");
    expect(wording.ROW_REMOVING_LABEL).toBe("移除中…");
  });

  it("S7: remove confirmation (risk-approved final text) with a thousands-separated quantity", () => {
    expect(wording.REMOVE_CONFIRM_SENTENCE).toBe(
      "確定移除本系統中 {代號} 的持倉紀錄（{數量} 股）？此動作無法復原。",
    );
    expect(wording.buildRemoveConfirmSentence("2330", "1,000")).toBe(
      "確定移除本系統中 2330 的持倉紀錄（1,000 股）？此動作無法復原。",
    );
  });

  it("S8: removed toast (risk-approved final text)", () => {
    expect(wording.REMOVED_TOAST).toBe("已移除 {代號} 的持倉紀錄");
    expect(wording.buildRemovedToast("2330")).toBe("已移除 2330 的持倉紀錄");
  });

  it("S9 / S10 / S12: failure labels and already-gone notice", () => {
    expect(wording.REMOVE_FAILED_LABEL).toBe("移除失敗");
    expect(wording.REMOVED_ALREADY_GONE).toBe("此持倉已不存在");
    expect(wording.SAVE_FAILED_LABEL).toBe("儲存失敗");
  });

  it("S13 / S14 / S15: sections and add success", () => {
    expect(wording.ADD_SECTION_TITLE).toBe("新增持倉");
    expect(wording.ADD_SUBMIT_LABEL).toBe("新增");
    expect(wording.ADD_PENDING_LABEL).toBe("新增中…");
    expect(wording.buildAddedToast("2330")).toBe("已新增「2330」");
    expect(wording.CSV_SECTION_TITLE).toBe("CSV 匯入");
  });

  it("S16 / S17 / S18 / S19: load failure, empty state, home link", () => {
    expect(wording.LIST_LOAD_FAILED_LABEL).toBe("載入失敗");
    expect(wording.LIST_RETRY_LABEL).toBe("重試");
    expect(wording.EMPTY_TITLE).toBe("尚無持倉");
    expect(wording.EMPTY_ADD_LINK).toBe("新增持倉");
    expect(wording.HOME_LINK_TO_INVENTORY).toBe("到庫存修改");
  });

  it("S21: column labels reuse the existing wording", () => {
    expect(wording.INVENTORY_COLUMN_LABELS).toEqual({
      symbol: "代號",
      market: "市場",
      quantity: "數量",
      avgCost: "平均成本（原幣）",
      note: "備註",
    });
  });

  it("S20: accessible names", () => {
    expect(wording.editAriaLabel("2330")).toBe("修改 2330 持倉");
    expect(wording.removeAriaLabel("2330")).toBe("移除 2330 持倉");
    expect(wording.moreAriaLabel("2330")).toBe("更多：修改 2330 的其他欄位");
    expect(wording.quantityInputAriaLabel("2330")).toBe("2330 數量");
    expect(wording.avgCostInputAriaLabel("2330")).toBe("2330 平均成本（原幣）");
    expect(wording.noteInputAriaLabel("2330")).toBe("2330 備註");
    expect(wording.disclosureAriaLabel(wording.ADD_SECTION_TITLE)).toBe("展開／收合 新增持倉");
    expect(wording.disclosureAriaLabel(wording.CSV_SECTION_TITLE)).toBe("展開／收合 CSV 匯入");
    expect(wording.LIST_ARIA_LABEL).toBe("持倉列表");
  });

  it("S20 label-in-name: each accessible name contains its visible label text", () => {
    expect(wording.moreAriaLabel("2330")).toContain(wording.ROW_MORE_LABEL);
    expect(wording.avgCostInputAriaLabel("2330")).toContain(wording.INVENTORY_COLUMN_LABELS.avgCost);
    expect(wording.quantityInputAriaLabel("2330")).toContain(wording.INVENTORY_COLUMN_LABELS.quantity);
    expect(wording.noteInputAriaLabel("2330")).toContain(wording.INVENTORY_COLUMN_LABELS.note);
    expect(wording.editAriaLabel("2330")).toContain(wording.ROW_EDIT_LABEL);
    expect(wording.removeAriaLabel("2330")).toContain(wording.ROW_REMOVE_LABEL);
    expect(wording.MORE_BUTTON_ARIA_LABEL).toBe("更多：修改 {代號} 的其他欄位");
    expect(wording.AVG_COST_INPUT_ARIA_LABEL).toBe("{代號} 平均成本（原幣）");
  });

  it("V3: original-value hint carries only the original value", () => {
    expect(wording.ORIGINAL_VALUE_HINT).toBe("原 {原值}");
    expect(wording.buildOriginalValueHint("1,000")).toBe("原 1,000");
  });

  it("V2: deleteButtonState uses 移除 / 移除中…", () => {
    expect(deleteButtonState(null, 1)).toEqual({ disabled: false, label: "移除" });
    expect(deleteButtonState(1, 1)).toEqual({ disabled: true, label: "移除中…" });
  });

  it("D6: there is no 已儲存 literal anywhere in the wording module", () => {
    expect(JSON.stringify(Object.values(wording).map(String))).not.toContain("已儲存");
  });
});

/** Every string the module exports, plus every builder's sample output. */
function allSamples(): string[] {
  const out: string[] = [];
  for (const value of Object.values(wording)) {
    if (typeof value === "string") out.push(value);
    else if (typeof value === "function") {
      out.push((value as (...args: string[]) => string)("2330", "1,000"));
    } else if (typeof value === "object" && value !== null) {
      out.push(...Object.values(value as Record<string, string>));
    }
  }
  return out;
}

describe("risk-compliance required items on the inventory wording", () => {
  it("required 3: no sentence starts with 建議 / 應 / 請 (front end invents no advisory prompt)", () => {
    for (const text of allSamples()) {
      expect(text, text).not.toMatch(/^(建議|應|請)/);
    }
  });

  it("required 5: 立即 / 即時 never appear in a string or aria name", () => {
    for (const text of allSamples()) {
      expect(text, text).not.toContain("立即");
      expect(text, text).not.toContain("即時");
    }
  });

  it("zero hits against the front-end forbidden-term list, no bare real-time claim", () => {
    for (const text of allSamples()) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, text);
      expect(findBareRealtimeClaims(text)).toEqual([]);
    }
  });

  it("S7 does not read like a trade ticket: no sell / order / execution verbs", () => {
    for (const verb of ["賣出", "出清", "下單", "成交", "買進"]) {
      expect(wording.REMOVE_CONFIRM_SENTENCE).not.toContain(verb);
      expect(wording.REMOVED_TOAST).not.toContain(verb);
    }
    expect(wording.REMOVE_CONFIRM_SENTENCE).toContain("持倉紀錄");
    expect(wording.REMOVE_CONFIRM_SENTENCE).toContain("無法復原");
  });
});
