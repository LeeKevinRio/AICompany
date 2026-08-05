import { describe, expect, it } from 'vitest';
import { isValidPriceInput, MAX_PRICE_DIGITS, parseValidPriceInput } from './priceInput';

describe('【Major 修正】isValidPriceInput — 就地擋下非法單價，不再靜默 floor/clamp', () => {
  it.each(['0', '1', '60', '007', '999999'])('非負整數字串 %s → 合法', (raw) => {
    expect(isValidPriceInput(raw)).toBe(true);
  });

  it.each(['', '   '])('空白字串（視為 0，免費贈品情境）→ 合法：%s', (raw) => {
    expect(isValidPriceInput(raw)).toBe(true);
  });

  it.each(['-1', '-60'])('負數 %s → 不合法（不該被靜默轉成 0）', (raw) => {
    expect(isValidPriceInput(raw)).toBe(false);
  });

  it.each(['12.5', '0.1', '1.'])('小數 %s → 不合法（不該被靜默 floor 掉）', (raw) => {
    expect(isValidPriceInput(raw)).toBe(false);
  });

  it.each(['abc', '1e3', 'NaN', '1,000', '$5'])('非數字字元 %s → 不合法', (raw) => {
    expect(isValidPriceInput(raw)).toBe(false);
  });
});

describe('【QA 複審 non-blocking #3】isValidPriceInput — 位數上限，擋掉 Number() 溢位成 Infinity 的極端路徑', () => {
  it(`剛好等於上限（${MAX_PRICE_DIGITS} 位數）→ 合法`, () => {
    expect(isValidPriceInput('9'.repeat(MAX_PRICE_DIGITS))).toBe(true);
  });

  it(`超過上限（${MAX_PRICE_DIGITS + 1} 位數）→ 不合法`, () => {
    expect(isValidPriceInput('1'.repeat(MAX_PRICE_DIGITS + 1))).toBe(false);
  });

  it('極端情境還原：幾百位數字原本能通過純數字 regex，經 Number() 會變 Infinity——現在應該直接被擋下', () => {
    const huge = '9'.repeat(400);
    // 回歸防線：確認這確實會溢位成 Infinity（不是這個測試本身壞掉），
    // 印證「原本會被下游第二道防線靜默轉成 0」這條路徑真實存在。
    expect(Number(huge)).toBe(Infinity);
    expect(isValidPriceInput(huge)).toBe(false);
  });
});

describe('parseValidPriceInput', () => {
  it('空白字串 → 0', () => {
    expect(parseValidPriceInput('')).toBe(0);
    expect(parseValidPriceInput('  ')).toBe(0);
  });

  it('數字字串 → 對應數字', () => {
    expect(parseValidPriceInput('60')).toBe(60);
    expect(parseValidPriceInput('007')).toBe(7);
  });
});
