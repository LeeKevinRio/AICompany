/**
 * 個股頁減負（work/stock-desk-個股頁減負-PRD.md）新增的面向使用者字面 —
 * 區塊導讀（FR-2）、頁級揭露區標題與導語（FR-3）、建議卡交叉引用句（FR-4 方向 A）。
 * creative-lead 起草（work/stock-desk-個股頁減負-文案起草.md），
 * risk-compliance-officer 逐字覆核（work/reviews/2026-09-02-個股頁減負-*.md）；
 * 字面（含標點）不得再改動，任何變更視為漂移須重送風控。
 * `componentWordingScan.test.ts` 逐字釘住＋禁用詞掃描。
 *
 * 落地條件（風控）：導讀 ≥ text-sm、視覺權重不得超過同區揭露句；頁級揭露區常駐、
 * 載入即可見、不可摺疊、字面為靜態常數（不依賴任何 query 狀態）。
 */

/* ---------- FR-2 區塊導讀（五則；建議卡導讀依風控裁定刪除，由銜接句承擔） ---------- */

export const OPERATION_SUMMARY_TAGLINE = "這裡先給一句規則評估結論，細節在下方逐項展開。";

export const KEY_LEVELS_TAGLINE = "這裡是系統依公式算出的參考價位，算法列在下方。";

export const TECHNICAL_CHART_TAGLINE = "這裡呈現價格與均線圖表，方便比對數字與圖形。";

export const TECHNICAL_INDICATORS_TAGLINE = "這裡列出技術指標數值，用途與計算方式見下方說明。";

export const LEVERAGE_CHAPTER_TAGLINE = "這裡說明槓桿 ETF 的損耗特性，含拆解與假設情境試算。";

/* ---------- FR-3 頁級揭露區 ---------- */

export const PAGE_LEVEL_DISCLOSURE_SECTION_TITLE = "本頁資料與計算揭露";

export const PAGE_LEVEL_DISCLOSURE_SECTION_INTRO =
  "以下為本頁共用的資料來源與更新頻率說明；各項計算方式與限制，另列於對應區塊。";

/* ---------- FR-4 方向 A：建議卡交叉引用句（繼承 R3 呈現規格） ---------- */

export const ADVICE_CARD_XREF_TO_SUMMARY =
  "結論、信心等級、免責事項、反面論點、失效條件與建議數量區間，已完整列於上方操作摘要；" +
  "本卡以下僅列命中規則、風險上限檢查與資料完整度等規則明細；規則明細本身不是結論。";
