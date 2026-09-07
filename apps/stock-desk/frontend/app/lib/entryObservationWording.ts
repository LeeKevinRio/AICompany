import type { ConditionId, ConditionStatus } from "./entryObservation";
import type { BasisItem } from "../position/[symbol]/KeyLevelsPanel";
import type { FooterItem } from "../components/PageFooterDisclosures";

/**
 * 六項觀察條件面板字面（CEO 需求 2026-09-06「進場點的觀察」；PRD
 * `work/stock-desk-進場觀察條件-PRD.md` §4b，風控預審 R-01～R-22）。creative-lead 起草
 * （路徑 B：標題不含「進場」），risk-compliance-officer 逐字審；字面（含標點）不得再改動，
 * 任何變更視為漂移須重送風控。`componentWordingScan.test.ts` 逐字釘住＋禁用詞掃描＋
 * 本案組合正則（條件成立／進場…成立／成立率／分數／還差／全部成立／進場點／買點／時機）。
 */

export const ENTRY_PANEL_TITLE = "六項觀察條件";

export const ENTRY_PANEL_TAGLINE = "這裡逐條列出六項條件的現況，明細列於下方。";

/** R-05: a sentence, never a fraction; the 無法判定 clause appears whenever unavailable > 0 (T11). */
export function buildConditionCount(met: number, unavailable: number): string {
  const head = `6 條中成立 ${met} 條`;
  return unavailable > 0 ? `${head}，其中 ${unavailable} 條無法判定。` : `${head}。`;
}

export const ENTRY_STATUS_LABELS: Record<ConditionStatus, string> = {
  met: "成立",
  unmet: "未成立",
  unavailable: "無法判定",
};

/** R-11: named by data item; the range row prints its real bar count (R-14) via `buildRangeConditionLabel`. */
export const ENTRY_CONDITION_LABELS: Record<Exclude<ConditionId, "range">, string> = {
  trend: "收盤與 MA60",
  pullback: "距 MA20",
  momentum: "RSI(14)",
  volume: "成交量 z",
  rules: "防禦型規則",
};

export function buildRangeConditionLabel(rangeBarCount: number | null): string {
  return rangeBarCount === null ? "位階" : `近 ${rangeBarCount} 根位階`;
}

/** Thresholds printed beside each name (R-11) — the numbers match `entryObservation.ts`. */
export const ENTRY_CONDITION_THRESHOLDS: Record<ConditionId, string> = {
  range: "≤ 70%",
  trend: "收盤 > MA60",
  pullback: "±3% 內",
  momentum: "30–70（不含端點）",
  volume: "−2～2（不含端點）",
  rules: "= 0（未持有時無法判定）",
};

/** The observed-value column for the rules row (命中數 moved out of the name). */
export function buildDefensiveHitsText(count: number): string {
  return `命中 ${count} 條`;
}

/* ---------- E-1～E-4：面板內常駐（不適用 2026-09-06 兩次下沉裁定） ---------- */

export const ENTRY_E1_QUALIFIER =
  "以上六條門檻皆為本面板自訂之固定值；成立數僅為符合門檻的條數，不代表機率、達成率或任何買賣判斷。";

export const ENTRY_E2_XREF = "本面板不是操作摘要結論的一部分；結論、信心等級與免責事項見上方操作摘要。";

export const ENTRY_E3_DASH_NOTE = "「—」代表無法判定，不代表數值為零，也不代表未成立。";

/**
 * E-4: the three queries' own timestamps (full `formatDateTime` output — the
 * year is never dropped). Collapses to one stamp only when all three match.
 */
export function buildDataTimesLine(
  bars: string | null,
  signals: string | null,
  advice: string | null,
  /** 風控 REQ-3: computed by the caller from the RAW ISO stamps, not from the display strings. */
  synchronized: boolean,
): string {
  const b = bars ?? "—";
  const s = signals ?? "—";
  const a = advice ?? "—";
  if (synchronized && bars !== null) {
    return `資料時間：${b}（日線／指標／規則評估同步）`;
  }
  return `資料時間：日線 ${b}｜指標 ${s}｜規則評估 ${a}`;
}

export const ENTRY_NO_DATA_STATEMENT = "目前資料不足，六條條件均無法判定。";

/* ---------- 價位階梯：MA20 ±3% 標籤（R-18：直接印門檻） ---------- */

export const LADDER_BAND_TAG = "MA20 ±3%";

/** 風控 REQ-2：指向標籤而非「此列」（多列同時命中時指涉明確）。 */
export const LADDER_BAND_NOTE = "有「MA20 ±3%」標籤的列，價位皆在該範圍內。";

/* ---------- 頁尾組（組名＝面板標題） ---------- */

export function buildEntryBasisRange(n: number | null): BasisItem {
  const nn = n === null ? "N" : String(n);
  return {
    formula: [`位階(近${nn}根)＝(收盤−近${nn}根最低價)/(近${nn}根最高價−近${nn}根最低價)×100%；門檻 ≤ 70%`],
    qualifier: "未滿 60 根日線或區間最高最低價相同時，本條無法判定。",
  };
}

export const ENTRY_BASIS_TREND: BasisItem = {
  formula: ["MA60＝近60根收盤價簡單平均；門檻：收盤 > MA60"],
  qualifier: "收盤與 MA60 皆取自同一批日線資料，兩者不會分屬不同批次。",
};

export const ENTRY_BASIS_PULLBACK: BasisItem = {
  formula: ["距MA20＝|收盤/MA20−1|×100%；門檻 ≤ 3%"],
  qualifier: "MA20 無法取得或為零時，本條無法判定。",
};

export const ENTRY_BASIS_MOMENTUM: BasisItem = {
  formula: ["RSI(14)＝14 期相對強弱指標；門檻：30 < RSI(14) < 70（不含端點）"],
  qualifier: "RSI(14) 資料不足時，本條無法判定；30、70 兩端點本身不算成立。",
};

export const ENTRY_BASIS_VOLUME: BasisItem = {
  formula: ["成交量z＝(當日成交量−近 20 根成交量平均)/近 20 根成交量標準差（母體）；門檻：−2 < z < 2（不含端點）"],
  qualifier: "z 值資料不足時，本條無法判定；−2、2 兩端點本身不算成立。",
};

export const ENTRY_BASIS_RULES: BasisItem = {
  formula: ["防禦型規則命中數＝本次規則評估中，方向為防禦型之命中規則筆數；門檻 ＝ 0"],
  qualifier: "未持有此標的，或持有狀態未定時，本條一律無法判定，不因未命中而視為成立。",
};

/** R-14: the 位階≠估值 semantic restated for this panel (not verbatim `buildRangeNotValuationNote`). */
export function buildEntryRangeNotValuationNote(n: number | null): string {
  const nn = n === null ? "N" : String(n);
  return `位階數字僅反映價格在近 ${nn} 根區間中的相對位置，與便宜或昂貴的估值判斷無關。`;
}

export function buildEntryFooterItems(rangeBarCount: number | null): FooterItem[] {
  return [
    buildEntryBasisRange(rangeBarCount),
    ENTRY_BASIS_TREND,
    ENTRY_BASIS_PULLBACK,
    ENTRY_BASIS_MOMENTUM,
    ENTRY_BASIS_VOLUME,
    ENTRY_BASIS_RULES,
    buildEntryRangeNotValuationNote(rangeBarCount),
  ];
}
