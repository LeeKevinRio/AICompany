import { describe, expect, it } from "vitest";
import { MIN_SEGMENT_POINTS } from "../backtestCurves";
import * as W from "../backtestCurveWording";

/**
 * 風控 2026-09-09 回測權益曲線圖字面逐字釘住（creative-lead 定稿，兩輪風控審）。
 * 任何字面改動都會讓這裡紅燈，等同強制回審；禁用詞掃描在 componentWordingScan.test.ts。
 */
describe("backtestCurveWording — 逐字釘住", () => {
  it("chart chrome", () => {
    expect(W.EQUITY_CURVE_TITLE).toBe("權益曲線：策略 vs Buy & Hold");
    expect(W.EQUITY_CURVE_AXIS_NOTE).toBe("縱軸為指數化權益（每段起點皆為 100），非實際金額");
    expect(W.EQUITY_CURVE_LEGEND_STRATEGY).toBe("策略");
    expect(W.EQUITY_CURVE_LEGEND_BUY_AND_HOLD).toBe("Buy & Hold");
    expect(W.EQUITY_CURVE_SEGMENT_IN_SAMPLE).toBe("樣本內");
    expect(W.EQUITY_CURVE_SEGMENT_OUT_OF_SAMPLE).toBe("樣本外");
    expect(W.EQUITY_CURVE_SPLIT_NOTE).toBe("樣本切分線：左為樣本內，右為樣本外，未參與任何參數選擇");
    expect(W.DRAWDOWN_CHART_TITLE).toBe("策略回撤－段內（%）");
    expect(W.DRAWDOWN_CHART_NOTE).toBe("僅顯示策略回撤，Buy & Hold 不納入本圖");
  });

  it("tooltip field names", () => {
    expect(W.EQUITY_CURVE_TOOLTIP_DATE).toBe("日期");
    expect(W.EQUITY_CURVE_TOOLTIP_STRATEGY).toBe("策略（指數化）");
    expect(W.EQUITY_CURVE_TOOLTIP_BUY_AND_HOLD).toBe("Buy & Hold（指數化）");
    expect(W.EQUITY_CURVE_TOOLTIP_DRAWDOWN).toBe("策略回撤（段內）");
  });

  it("REQ-2 / REQ-4 / REQ-5 / REQ-7 sentences and templates", () => {
    expect(W.buildTradeCountNote(63)).toBe("交易次數合計：63（樣本內外加總；逐段筆數見下方表格）");
    expect(W.buildSegmentInsufficientNote("樣本外")).toBe("樣本外未繪製曲線，因資料筆數不足（少於 2 根）");
    // 風控 REQ-12: the threshold printed in the sentence is the drawing threshold itself.
    expect(W.buildSegmentInsufficientNote("樣本外")).toContain(`少於 ${MIN_SEGMENT_POINTS} 根`);
    expect(W.buildSingleSegmentNote("樣本內")).toBe("本圖僅顯示樣本內，另一段未包含在本次回測範圍");
    expect(W.EQUITY_CURVE_EMPTY_STATEMENT).toBe("本次回測樣本內外皆無足夠的每日權益資料，故無法繪製曲線圖。");
    expect(W.EQUITY_CURVE_ARIA_LABEL).toBe("策略與 Buy & Hold 權益曲線，含樣本內外分隔與策略回撤面積圖");
    expect(W.EQUITY_CURVE_ARIA_LABEL_SINGLE_SEGMENT).toBe("策略與 Buy & Hold 權益曲線，含策略回撤面積圖");
    expect(W.EQUITY_CURVE_GUIDANCE).toBe("本圖同上方提醒：僅為歷史統計描述，不代表未來會重演。");
  });
});
