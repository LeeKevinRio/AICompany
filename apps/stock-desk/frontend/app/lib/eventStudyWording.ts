/**
 * `/backtest` 頁「五項觀察條件 事件研究」節的前端字面（PRD
 * `work/stock-desk-事件研究網頁版-PRD.md`；風控預審 REQ-W2／W3／W5／W12、SUG-W1／W4；
 * creative-lead 定稿 2026-09-12）。圖表本身與頁首／頁尾每一句都由後端
 * `POST /api/event-study` 回傳（ADR-0008 D-1～D-3），這裡只放**網頁殼**自己的句子；
 * 後端字面一個字都不在前端重打。字面（含標點）不得再改動；
 * `__tests__/eventStudy.test.ts` 逐字釘住，`componentWordingScan.test.ts` 掃禁用詞。
 */

/** 風控 REQ-W3／SUG-W1: the section and its button both carry the 「五項觀察條件」 qualifier. */
export const EVENT_STUDY_SECTION_TITLE = "五項觀察條件 事件研究";
export const EVENT_STUDY_BUTTON_LABEL = "顯示五項觀察條件事件研究";

/**
 * 風控 REQ-W2: standing, body-size, above the button and the first chart. The
 * backtest report above is a costed strategy result; this section is a costless
 * close-to-close price distribution. Three sentences, kept as three items.
 */
export const EVENT_STUDY_SEPARATOR_SENTENCES: readonly string[] = [
  "上方為含手續費、證交稅與滑價的策略績效；本節為收盤對收盤、未計成本的價格分布。",
  "兩組數字衡量基礎不同，不可互推，亦不宜並列比較。",
  "本節不評價優劣，亦不代表兩者互相驗證或預測未來。",
];

/** 風控 REQ-W5: shown while the form no longer matches the report on screen; the button is disabled. */
export const EVENT_STUDY_STALE_FORM_HINT = "事件研究僅按目前回測報告的參數計算，請先重新執行回測。";

export const EVENT_STUDY_LOADING = "正在計算五項觀察條件事件研究，請稍候。";

/**
 * Non-data failures only; `insufficient_data` shows the backend's own `reason` verbatim.
 * 風控 2026-09-12 S-3: a 422 (rejected symbol／range) is permanent, so the sentence
 * promises nothing about retrying (creative-lead redraft, pending 風控 second-round review).
 */
export const EVENT_STUDY_ERROR =
  "事件研究本次未能算出結果；請先確認代號、市場與區間是否被接受，再重新查詢。";

/** 風控 SUG-W4: the page intro no longer names one strategy. */
export const BACKTEST_PAGE_INTRO = "依策略回測單一標的，附同期 Buy & Hold 對照與樣本內／外分列結果。";
