/**
 * 「一眼一句」新字面（dev-lead 收斂稿 §5，`work/stock-desk-一眼一句-實作規格.md`）—
 * 個股頁六區塊統一的「標題列→主視覺／主數字→一句結論→詳細」模板所需的
 * `<details>` 入口字與新一句結論。字面（含標點）待風控逐字審，落地時一字不改；
 * 任何變更視為漂移須重送風控。`componentWordingScan.test.ts` 逐字釘住。
 *
 * 個股頁常數（本檔）由 frontend-engineer A 建立；首頁（風險儀表／警示狀態列）
 * 常數由 frontend-engineer B 以 Edit 追加於本檔尾端（分工見實作規格 §6）。
 */

/** 個股頁六區塊通用的 `<details>` 入口字（未特化的備援，目前各區塊皆用專屬字面）。 */
export const DETAILS_SUMMARY_GENERIC = "詳細說明與依據";

export const DETAILS_SUMMARY_OPERATION = "詳細：反面論點、失效條件與假設";

export const DETAILS_SUMMARY_KEY_LEVELS = "查看計算依據";

export const DETAILS_SUMMARY_ENTRY = "詳細：六條逐項明細";

export const DETAILS_SUMMARY_TECHNICAL = "詳細：七張指標卡與風險量測";

/** 技術分析主視圖一句結論：「近 {n} 根日線，收盤 {x}。」 */
export function buildTechOneLiner(n: number, x: string): string {
  return `近 ${n} 根日線，收盤 ${x}。`;
}

/** 關鍵價位參考主視圖一句結論：「收盤 {x}，位於近 {n} 根區間{zone}。」 */
export function buildKeyLevelsOneLiner(
  x: string,
  n: number,
  zone: string,
): string {
  return `收盤 ${x}，位於近 ${n} 根區間${zone}。`;
}

/** 建議卡 summary 列「命中 {n} 條」（既有 Section 標題字面拆用）。 */
export function buildAdviceHitCount(n: number): string {
  return `命中 ${n} 條`;
}

/* ============================================================================
 * 首頁常數（frontend-engineer B，實作規格 §3、§6）：風險儀表「詳細」入口字、
 * 警示狀態列三態。字面同樣待風控逐字審，落地時一字不改。
 * ==========================================================================*/

/** 首頁風險儀表「詳細」summary 入口字（`RiskGauge.tsx`，視覺規範 B.3）。 */
export const DETAILS_SUMMARY_RISK_GAUGE = "詳細：各項判定依據、假設與資料來源";

/** 警示狀態列狀態 A（沒有任何規則，`AlertStatusStrip.tsx`，視覺規範 B.4）。 */
export const ALERTS_NO_RULES = "尚未設定警示規則";
export const ALERTS_NO_RULES_LINK = "去設定";

/**
 * 警示狀態列狀態 B（有規則、沒觸發）——`n` 為規則**總數**（不分 enabled/
 * disabled）。字面用「已設定」而非「啟用中」，指的正是「有沒有設定過規則」
 * 這件事實；若改用 enabled 數，規則全部停用時會印出「0 條規則已設定」，
 * 讀者會誤以為根本沒設定過規則（qa 2026-09-19 追加 low 修正）。
 */
export function buildAlertsRulesNoEvents(n: number): string {
  return `${n} 條規則已設定，目前沒有待處理警示`;
}

/**
 * 狀態 B 右側時間戳。措辭刻意用「查詢時間」而非「最近評估」——系統目前沒有
 * 排程實際評估時間欄位，只有 `AlertEventListResponse.as_of`（查詢回應時間），
 * 誠實標示避免暗示排程剛評估過（實作規格 §3.3、視覺規範 B.4）。
 */
export function buildAlertsQueriedAt(t: string): string {
  return `查詢時間：${t}`;
}

/** 警示狀態列狀態 C（有待處理事件）標題句。 */
export function buildAlertsPendingCount(n: number): string {
  return `${n} 條待處理警示`;
}

/** 既有字面沿用（原 `PendingAlertsPanel.tsx` 的管理連結文字）。 */
export const ALERTS_MANAGE_LINK = "管理警示規則";

/**
 * 警示狀態列狀態 D（排程總開關關閉，`AppSettings.alerts.enabled === false`）
 * ——風控 2026-09-19 required：總開關關閉時排程整個 tick 跳過，此時狀態 B
 * 「N 條規則已設定，目前沒有待處理警示」會被誤讀成「剛查過、沒事」，須另立
 * 一態。字面為 creative-lead 文案稿 B4 狀態三候選 1，僅陳述排程未啟用這件
 * 事實，不下任何安心／無事的判斷語，已核可。
 */
export const ALERTS_SCHEDULER_DISABLED = "排程目前未啟用，警示評估暫不會更新";

/** 警示狀態列查詢失敗前綴（`AlertStatusStrip.tsx`）。 */
export const ALERTS_LOAD_ERROR_PREFIX = "無法載入警示狀態：";
