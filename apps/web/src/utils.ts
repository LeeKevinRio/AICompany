// 共用小工具。

// 把輸入轉成非負整數：非數字視為 0，負數歸 0，小數無條件捨去。
export function toNonNegInt(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0;
}
