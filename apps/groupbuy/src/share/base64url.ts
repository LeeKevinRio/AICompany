// UTF-8 安全的 base64url 編解碼（無後端分享機制的底層）。
// 用途：把團定義 / 回單資料壓進 URL 或短碼；需可容納中文（UTF-8）、URL-safe（不含 + / =）。
//
// 全程不丟例外由呼叫端負責容錯——但 decode 對「非法字元 / 壞字串」一律回傳 null，
// 讓上層 codec 能乾淨地把壞碼判為無效（容錯要厚：買家貼回的字串可能被 LINE 夾帶雜訊）。

/** 把 latin1 二進位字串轉 base64（btoa 只吃 0–255，故先經 TextEncoder 轉 bytes）。 */
function bytesToBinaryString(bytes: Uint8Array): string {
  let bin = '';
  // 逐字元組（避免大陣列 spread 造成 call stack 爆掉）。
  for (let i = 0; i < bytes.length; i += 1) {
    bin += String.fromCharCode(bytes[i]);
  }
  return bin;
}

function binaryStringToBytes(bin: string): Uint8Array {
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) {
    out[i] = bin.charCodeAt(i) & 0xff;
  }
  return out;
}

/** 任意 UTF-8 字串 → base64url（無 padding）。 */
export function encodeBase64Url(text: string): string {
  const bytes = new TextEncoder().encode(text);
  const b64 = btoa(bytesToBinaryString(bytes));
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/**
 * base64url → UTF-8 字串。任何解不開（非法字元、長度異常、非 UTF-8）都回傳 null，絕不丟例外。
 */
export function decodeBase64Url(encoded: string): string | null {
  if (typeof encoded !== 'string' || encoded.length === 0) return null;
  // 只允許 base64url 字元集；夾帶其他字元一律視為壞碼。
  if (!/^[A-Za-z0-9_-]+$/.test(encoded)) return null;
  try {
    const b64 = encoded.replace(/-/g, '+').replace(/_/g, '/');
    // 補回 padding 到 4 的倍數。
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const bin = atob(padded);
    return new TextDecoder('utf-8', { fatal: true }).decode(binaryStringToBytes(bin));
  } catch {
    return null;
  }
}
