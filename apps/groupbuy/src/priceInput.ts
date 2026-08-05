// 開團表單「單價」欄位的輸入層驗證（純函式，不依賴 React / DOM）。
//
// 問題背景：v2.0 createGroup()（useGroups.ts）對價格只有「靜默防呆」——
// 非負整數用 Math.floor 砍掉小數（12.5 -> 12，無警告），負數直接轉成 0（無警告）。
// 這對主揪來說是「悄悄改了我填的價格」，QA 實機測試（T2）證實會誤導。
//
// 修法：把驗證挪到表單「就地擋下」，非法值直接顯示錯誤、不讓送出；
// createGroup() 裡原本的 floor/clamp 防線保留，但降級為第二道防線，不再是唯一防線。

/**
 * 單價輸入位數上限（【QA 複審 non-blocking #3】）。
 *
 * 問題：原本 isValidPriceInput 只用 /^\d+$/ 驗證「純數字」，沒有位數上限——貼幾百位數字
 * 一樣通過這個 regex（畢竟每個字元都是數字），到了 parseValidPriceInput 用 Number() 轉換
 * 時會溢位成 Infinity，接著在 createGroup()（useGroups.ts）的第二道防線
 * `Number.isFinite(p.price) ? ... : 0` 判定為非有限數，又被靜默轉成 $0——繞了一圈，還是
 * 掉回「非法輸入被靜默改成 0」的原始問題，只是觸發路徑更隱蔽。
 * 7 位數上限（最大 9,999,999）在「千萬元級以下」，遠超合理團購單價，同時排除這整條溢位路徑。
 */
export const MAX_PRICE_DIGITS = 7;

/**
 * 驗證開團表單單價輸入字串是否合法。
 * 合法值：空字串（視為 0，例如免費贈品）或不超過 MAX_PRICE_DIGITS 位數的非負整數字串
 * （可有前導零）。小數點、負號、非數字字元、超過位數上限一律不合法。
 */
export function isValidPriceInput(raw: string): boolean {
  const trimmed = raw.trim();
  if (trimmed === '') return true;
  if (!/^\d+$/.test(trimmed)) return false;
  return trimmed.length <= MAX_PRICE_DIGITS;
}

/** 單價輸入不合法時顯示給主揪看的錯誤文字。 */
export const PRICE_INPUT_ERROR_MESSAGE = `單價需為 0 或正整數（元，最多 ${MAX_PRICE_DIGITS} 位數）`;

/**
 * 把已驗證合法的單價輸入字串轉成實際數字。呼叫前務必先過 isValidPriceInput 檢查，
 * 否則對非法字串呼叫本函式的行為未定義（不做二次防呆，避免跟表單驗證的錯誤訊息打架）。
 */
export function parseValidPriceInput(raw: string): number {
  const trimmed = raw.trim();
  return trimmed === '' ? 0 : Number(trimmed);
}
