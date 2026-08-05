// 開團表單「單價」欄位的輸入層驗證（純函式，不依賴 React / DOM）。
//
// 問題背景：v2.0 createGroup()（useGroups.ts）對價格只有「靜默防呆」——
// 非負整數用 Math.floor 砍掉小數（12.5 -> 12，無警告），負數直接轉成 0（無警告）。
// 這對主揪來說是「悄悄改了我填的價格」，QA 實機測試（T2）證實會誤導。
//
// 修法：把驗證挪到表單「就地擋下」，非法值直接顯示錯誤、不讓送出；
// createGroup() 裡原本的 floor/clamp 防線保留，但降級為第二道防線，不再是唯一防線。

/**
 * 驗證開團表單單價輸入字串是否合法。
 * 合法值：空字串（視為 0，例如免費贈品）或純數字的非負整數字串（可有前導零）。
 * 小數點、負號、非數字字元一律不合法。
 */
export function isValidPriceInput(raw: string): boolean {
  const trimmed = raw.trim();
  if (trimmed === '') return true;
  return /^\d+$/.test(trimmed);
}

/** 單價輸入不合法時顯示給主揪看的錯誤文字。 */
export const PRICE_INPUT_ERROR_MESSAGE = '單價需為 0 或正整數（元）';

/**
 * 把已驗證合法的單價輸入字串轉成實際數字。呼叫前務必先過 isValidPriceInput 檢查，
 * 否則對非法字串呼叫本函式的行為未定義（不做二次防呆，避免跟表單驗證的錯誤訊息打架）。
 */
export function parseValidPriceInput(raw: string): number {
  const trimmed = raw.trim();
  return trimmed === '' ? 0 : Number(trimmed);
}
