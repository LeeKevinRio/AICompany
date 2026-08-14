/**
 * Single source of truth for the Traditional Chinese wording used by the
 * operation-summary panel (FR-C1/FR-C6/FR-C7) and by nothing else.
 *
 * DRAFT WORDING NOTICE: every string exported here is a *drafting-stage*
 * judgement call under risk-compliance-officer's 2026-08-02 "措辭原則清單"
 * (`work/stock-desk-phase8-風控定調.md`), not a finalized copy. §6 of that
 * document explicitly keeps this batch's summary/candidate wording open for
 * a later dedicated review ("FR-C6/C7 的定稿文案 ... 仍須另案送風控複審").
 * Do not ship without that follow-up review.
 *
 * Every entry below is justified against a specific clause of the same
 * document so a reviewer can trace wording back to its permission:
 *   - §1.2 whitelist table -> `HELD_ACTION_LABELS`
 *   - §3.1/§3.2 candidate-mode vocabulary reduction -> `CANDIDATE_*`
 *   - §2 (8 required elements) -> the `build*` helpers below
 *   - §5 (non-realtime disclosure rules) -> `NON_REALTIME_NOTICE`
 *
 * `test_advice_wording_frontend.test.ts` scans every string literal declared
 * in this file against `FRONTEND_FORBIDDEN_TERMS_SAMPLE` (a local mirror of
 * §1.3's banned list) so this file cannot silently regress a red-line term.
 * That test only covers *this* file by design (§1.3's "required" clause: the
 * scan must reach the front-end wording surface, which previously had none).
 */

import type { CardAction, Confidence } from "./types";

/**
 * §1.2 whitelist, one canonical label per `CardAction`, used only in
 * *held* mode (the candidate-mode vocabulary is deliberately smaller — see
 * `CANDIDATE_NOT_SUPPORTIVE_TEXT` below, §3.2). Every label is name-formed
 * (not a verb phrase directed at the user) and carries no promise.
 */
export const HELD_ACTION_LABELS: Record<CardAction, string> = {
  add: "加碼參考",
  hold: "續抱/維持現狀",
  reduce: "減碼參考",
  take_profit: "分批獲利了結參考",
  stop_loss: "停損評估",
  insufficient_data: "資料不足，本次不提供操作評估",
};

/** §1.1: every action label's first appearance must carry an explicit source. */
export const ATTRIBUTION_PREFIX = "規則評估";

/** Builds the attributed headline for a held-mode action label (§1.1 required). */
export function buildAttributedHeadline(action: CardAction): string {
  return `${ATTRIBUTION_PREFIX}：${HELD_ACTION_LABELS[action]}`;
}

/** FR-C7(b): candidate-mode heading, replacing the held-mode action label entirely. */
export const CANDIDATE_HEADING_LABEL = "進場評估";

/**
 * §3.1: `add` in candidate mode may only be stated as a fact composition,
 * never as a positive conclusion ("可以進場" and siblings are vetoed
 * outright). `constructiveCount` is the number of matched rules whose action
 * is `add` — always > 0 and never alongside a matched defensive rule when the
 * engine's aggregated action is `add` (see `build_advice` in
 * `app/advice/engine.py`, the `add` + defensive-downgrade branch).
 */
export function buildCandidateSupportiveComposition(constructiveCount: number): string {
  return `規則評估未命中防禦型規則，建設性規則命中 ${constructiveCount} 條。`;
}

/** §3.1: the mandatory second sentence that must follow the composition above, verbatim. */
export const CANDIDATE_SUPPORTIVE_DISCLAIMER = "這不構成進場理由。";

/**
 * §3 footer + AC-C7.3: the *only* permitted wording for every non-`add`
 * outcome in candidate mode (hold, reduce, stop_loss, take_profit alike —
 * held-mode verbs are banned here per §3.2). Softened variants ("可再觀察"
 * "時機未到" "可留意") are explicitly forbidden and must never replace this.
 */
export const CANDIDATE_NOT_SUPPORTIVE_TEXT = "本次規則評估未支持進場";

/** §2 item 8 / FR-C7(b): the always-on candidate-mode evidence-limit notice, verbatim. */
export const CANDIDATE_EVIDENCE_NOTICE =
  "未持有此標的：以候選部位（0 股）評估，依賴持倉資料的規則未參與評估，證據較持倉評估少。";

/** §3.4: attached beside `confidence` whenever the card is in candidate mode. */
export const CANDIDATE_CONFIDENCE_NOT_COMPARABLE_NOTE =
  "候選評估的規則覆蓋率低於持倉評估，本等級不可與持倉評估的等級直接比較。";

/** §3.3 required: quantified evidence-density disclosure, paired with the notice above. */
export function buildCandidateCoverageStatement(
  dataCompleteness: number,
  skippedRuleCount: number,
): string {
  const pct = Math.round(dataCompleteness * 1000) / 10;
  return `本次規則覆蓋度 ${pct}%，因依賴持倉資料而被跳過的規則共 ${skippedRuleCount} 條。`;
}

/**
 * AC-C7.2: the basis note attached to a candidate-mode buildable quantity
 * range. risk-final-review.md 最終複審(2026-08-09)新列管:「總資產」裸詞須補
 * `SettingsForm.tsx` 已用的限定語(已估值部位市值,不含現金),否則與設定頁的
 * 「帳戶總淨值」分母混淆 —— 同時清償限制清單 #10 D2 項 2(建議卡「總資產」未
 * 加限定語)。半形括號比照 SettingsForm.tsx 既有寫法,維持全檔一致。
 *
 * 波次1文案裁決.md「追認」項(2026-08-10):限定語補全為「已估值部位市值,不含
 * 現金」——原句只寫了「已估值部位市值」,漏了「不含現金」半句,一併補上並與
 * `SettingsForm.tsx` 四處(RISK_BUDGET_FIELDS 內)同步改寫。
 */
export const CANDIDATE_QUANTITY_BASIS_NOTE = "以你目前的總資產(已估值部位市值,不含現金)與上限推導。";

/**
 * FR-2 / Phase 6 放行條件 (b): the existing generic "no quantity range"
 * copy, reused verbatim everywhere `quantity_range` is absent. Do NOT
 * rewrite this to name a specific cause until risk-compliance-officer signs
 * off on the per-cause copy (AC-2.2) — see `AdviceCardView.tsx`'s identical
 * inline string, which this constant mirrors on purpose.
 */
export const QUANTITY_RANGE_ABSENCE_TEXT = "此建議未附帶數量區間（無法從風險上限推導）。";

/** §2 item 6: the fixed "this is a rule engine, not a prediction" statement. */
export function buildRulesStatement(rulesVersion: string): string {
  return `本評估由固定規則集（版本 ${rulesVersion}）計算，非預測模型。`;
}

/** AC-C8.2 / §2 item 3: the fixed data-basis-date statement, verbatim wording. */
export function buildAsOfStatement(dateIso: string): string {
  return `本評估基於 ${dateIso} 收盤資料。`;
}

/**
 * S5 fix (risk-final-review.md 列管項:「as-of 語句可能退化為破折號空句」;
 * 裁決僅有方向、無既定字面,本句為自擬保守句,待風控覆核): §2 item 3 requires
 * the as-of statement to be present on *every* card, but the previous call
 * site (`operationSummary.ts`'s `buildRequiredElements`) fell back to the
 * placeholder string `"—"` when the envelope carried neither
 * `last_bar_date` nor `observation_window.end`, producing an unreadable
 * "本評估基於 —收盤資料。" — a sentence that *looks* like it discloses a
 * basis date while actually disclosing nothing. This sentence states the
 * gap honestly instead of hiding it behind a dash.
 */
export const AS_OF_DATE_UNKNOWN_STATEMENT = "本評估未取得收盤資料的日期，無法標示評估所依據的資料時間。";

/**
 * AC-C8.2 / 風控複審 2026-08-09 裁決 b: the extra prominent notice for data
 * whose calendar-day age has crossed `STALE_CALENDAR_DAY_THRESHOLD`
 * (`tradingCalendar.ts`). States the actual basis date and the calendar-day
 * gap instead of a vague "超過一個交易日" so the reader is not left to guess
 * the magnitude the fixed sentence used to hide.
 */
export function buildStaleDataProminentNotice(lastBarDate: string, days: number): string {
  // risk-final-review.md 最終複審(2026-08-09)新列管:半形逗號統一為全形,與本檔
  // 其餘句子(§3.1/§3.3 等)的標點慣例一致;文字內容不變,僅標點字元置換。
  return `本評估所依據的收盤資料為 ${lastBarDate}，距今已 ${days} 個日曆日未更新，僅供參考，不代表最新市況。`;
}

/**
 * §2 item 4 / §5: the system-level non-realtime disclosure. Every "即時" is
 * used to *deny* real-time capability, never to claim it (§5.1); "最新" only
 * modifies "系統手上的資料" (§5.3); update cadence is qualified with
 * "排程啟用時" so it never reads as a promise when the scheduler process is
 * not running (§5.4/AC-C8.4).
 */
export const NON_REALTIME_NOTICE =
  "本產品採免費日線資料源，非即時報價系統；台股日線為盤後資料。" +
  "排程啟用時，資料約每 24 小時更新一次、警示評估約每 60 分鐘評估一次。" +
  "以下評估以系統手上最新一份資料計算，反映的是打開頁面當下、系統能取得的資料，不代表市場當下狀況。";

const CONFIDENCE_LABELS: Record<Confidence, string> = {
  low: "低",
  medium: "中",
  high: "高",
};

export function summaryConfidenceLabel(value: Confidence): string {
  return CONFIDENCE_LABELS[value];
}

/**
 * A local mirror of the backend's §1.3 禁用清單 (see
 * `apps/stock-desk/backend/tests/test_advice_wording.py`'s
 * `FORBIDDEN_TERMS`/`FORBIDDEN_ADVICE_TERMS`), extended with the front-end
 * facing categories that file does not scan (this module is the file that
 * scan was missing). Exported so the guard test can import the same list
 * instead of re-typing it and drifting.
 *
 * S6 fix (work/reviews/risk-final-review.md 列管項:「禁用詞清單前後端鏡像漂
 * 移」): the 保證性/價格目標 sections below are now guarded against drifting
 * from the backend by `sharedForbiddenTerms.test.ts`, which reads the same
 * `shared/forbidden-terms.json` the backend's `test_advice_wording.py`
 * reads and asserts every term there is present in this list — that scan
 * caught `穩賠` (present in the backend's `loader.BANNED_PHRASES`, missing
 * here) and is added below to close the gap it found.
 */
export const FRONTEND_FORBIDDEN_TERMS: readonly string[] = [
  // 保證性
  "保證",
  "必漲",
  "必跌",
  "必賺",
  "穩賺",
  "穩賠",
  "包賺",
  "零風險",
  "無風險",
  "一定會",
  // 價格目標
  "目標價",
  "合理價",
  "上看",
  "target_price",
  "price_target",
  "fair_value",
  // 技術位置擬人化
  "支撐位",
  "壓力位",
  "防守價",
  "停利價",
  "出場價",
  "進場價",
  "buy point",
  "sell point",
  // 祈使/急迫
  "快買",
  "快賣",
  "立即",
  "馬上",
  "趕快",
  "進場時機",
  "最佳買點",
  "逢低買進",
  "抄底",
  "追高",
  "攤平",
  // 部位規模指令
  "all-in",
  "全押",
  "梭哈",
  "重壓",
  "押身家",
  // 預測/確定性
  "將會",
  "即將",
  "預計上漲",
  "突破在即",
  "有望",
  "可期",
  "潛力股",
  "飆股",
  "強勢股",
  // 機率洗白
  "勝率",
  "成功率",
  "命中率",
  "準確率",
  "高機率",
  // 即時性 (real-time itself is checked separately — see the guard test's
  // own logic, since this module legitimately contains "即時" used to deny
  // it, e.g. "非即時報價"; "real-time" as a bare English claim is still
  // banned unconditionally)
  "real-time",
  "盤中",
  "最新報價",
  "最新股價",
  "最新行情",
  // 行銷語氣
  "穩健獲利",
  "輕鬆賺",
  "躺著賺",
  "專業級判斷",
  "精準",
  // 候選模式正面結論句 (§3.1)
  "可以進場",
  "適合進場",
  "進場條件成立",
  // 候選模式軟化語 (§3 footer)
  "可再觀察",
  "時機未到",
  "可留意",
];
