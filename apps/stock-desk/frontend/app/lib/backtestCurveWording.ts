/**
 * 回測頁權益曲線圖字面（CEO 2026-09-09「我要的是像曲線圖那樣的」；creative-lead
 * 定稿，risk-compliance-officer 逐字審）。字面（含標點）不得再改動；
 * `componentWordingScan.test.ts` 逐字釘住＋禁用詞掃描。色彩不承載價值判斷（S1）：
 * 兩序列用經 dataviz 驗證的類別色＋實線／虛線＋圖例＋線尾標籤，回撤用單一色相。
 */

export const EQUITY_CURVE_TITLE = "權益曲線：策略 vs Buy & Hold";

/** 每段（樣本內／樣本外）各自以自己的第一根為 100，與下方表格逐段比較的口徑一致。 */
export const EQUITY_CURVE_AXIS_NOTE = "縱軸為指數化權益（每段起點皆為 100），非實際金額";

export const EQUITY_CURVE_LEGEND_STRATEGY = "策略";
export const EQUITY_CURVE_LEGEND_BUY_AND_HOLD = "Buy & Hold";

export const EQUITY_CURVE_SEGMENT_IN_SAMPLE = "樣本內";
export const EQUITY_CURVE_SEGMENT_OUT_OF_SAMPLE = "樣本外";
export const EQUITY_CURVE_SPLIT_NOTE = "樣本切分線：左為樣本內，右為樣本外，未參與任何參數選擇";

/** 「段內」：每段各自從第一根起算相對高點（與表格 max_drawdown 同口徑），不是全期回撤（風控 REQ-6）。 */
export const DRAWDOWN_CHART_TITLE = "策略回撤－段內（%）";
export const DRAWDOWN_CHART_NOTE = "僅顯示策略回撤，Buy & Hold 不納入本圖";

export const EQUITY_CURVE_TOOLTIP_DATE = "日期";
export const EQUITY_CURVE_TOOLTIP_STRATEGY = "策略（指數化）";
export const EQUITY_CURVE_TOOLTIP_BUY_AND_HOLD = "Buy & Hold（指數化）";
export const EQUITY_CURVE_TOOLTIP_DRAWDOWN = "策略回撤（段內）";

/** 風控 REQ-4: N is the two segments' total; the tables below list each segment as 「N（結算 M）」. */
export function buildTradeCountNote(count: number): string {
  return `交易次數合計：${count}（樣本內外加總；逐段筆數見下方表格）`;
}

/**
 * 風控 REQ-2: the named segment exists but one of its series has fewer than
 * `MIN_SEGMENT_POINTS` drawable points (finite values after re-basing) — the
 * number in the sentence is that threshold, pinned to the constant by test.
 */
export function buildSegmentInsufficientNote(segmentLabel: string): string {
  return `${segmentLabel}未繪製曲線，因資料筆數不足（少於 2 根）`;
}

/** 風控 REQ-2: only one segment exists in this run; `shownLabel` is the one on the chart. */
export function buildSingleSegmentNote(shownLabel: string): string {
  return `本圖僅顯示${shownLabel}，另一段未包含在本次回測範圍`;
}

export const EQUITY_CURVE_ARIA_LABEL = "策略與 Buy & Hold 權益曲線，含樣本內外分隔與策略回撤面積圖";
/** 風控 REQ-7: used whenever the split line is not on screen (single segment). */
export const EQUITY_CURVE_ARIA_LABEL_SINGLE_SEGMENT = "策略與 Buy & Hold 權益曲線，含策略回撤面積圖";

/** 風控 REQ-5: states the checked fact (neither segment has both series >= 2 bars) without naming a culprit series. */
export const EQUITY_CURVE_EMPTY_STATEMENT = "本次回測樣本內外皆無足夠的每日權益資料，故無法繪製曲線圖。";

/** Restates the report-level standing disclaimer that sits directly above the chart. */
export const EQUITY_CURVE_GUIDANCE = "本圖同上方提醒：僅為歷史統計描述，不代表未來會重演。";
