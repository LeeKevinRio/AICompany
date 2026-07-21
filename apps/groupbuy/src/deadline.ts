// 到期時間判定純函式（不依賴 React / DOM，方便單元測試）。
//
// 時區 / 時鐘處理原則：
//   - deadlineAt 一律存「絕對 epoch 毫秒」（UTC 基準）。開團頁的 datetime-local 是主揪的
//     「當地牆上時間」，用 new Date(value).getTime() 轉成 epoch——已內含主揪當地時區偏移，
//     故存進去的是明確的時間點，跨時區比較不會錯亂。
//   - 判定 isExpired 用「當下時鐘」比較（render / 送單時計算），不做背景 timer 輪詢。
//   - 買家 JoinPage 的過期判定以「買家裝置時鐘」為準（無後端可校時）：若買家裝置時間不準，
//     可能誤判可填 / 不可填。此為無後端架構的已知限制，非 bug。

/** deadlineAt 是否為有效時間戳。 */
function isValidDeadline(deadlineAt: number | undefined): deadlineAt is number {
  return typeof deadlineAt === 'number' && Number.isFinite(deadlineAt);
}

/**
 * 是否已過期。無截止時間（undefined / 非法）一律回 false（＝永不過期）。
 * now 由呼叫端傳入（通常 Date.now()），方便測試注入固定時間。
 */
export function isExpired(deadlineAt: number | undefined, now: number): boolean {
  if (!isValidDeadline(deadlineAt)) return false;
  return now > deadlineAt;
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * 產生人類可讀的倒數字串（「還剩 2 小時」等）。
 * 無截止時間 → null（呼叫端不顯示倒數）；已到期 → 「已截止」。
 */
export function formatCountdown(deadlineAt: number | undefined, now: number): string | null {
  if (!isValidDeadline(deadlineAt)) return null;
  const diff = deadlineAt - now;
  if (diff <= 0) return '已截止';
  if (diff >= DAY) return `還剩 ${Math.floor(diff / DAY)} 天`;
  if (diff >= HOUR) return `還剩 ${Math.floor(diff / HOUR)} 小時`;
  if (diff >= MINUTE) return `還剩 ${Math.floor(diff / MINUTE)} 分鐘`;
  return '即將截止';
}

/**
 * 團是否「實質上已關閉」＝主揪手動截止 或 已過期。
 * 送單 / 匯入 / 代填的統一擋門條件（資料層與 UI 都用這個）。
 */
export function isGroupClosed(
  group: { closed: boolean; deadlineAt?: number },
  now: number,
): boolean {
  return group.closed || isExpired(group.deadlineAt, now);
}
