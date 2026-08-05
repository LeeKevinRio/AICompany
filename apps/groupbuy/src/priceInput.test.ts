import { describe, expect, it } from 'vitest';
import { isValidPriceInput, parseValidPriceInput } from './priceInput';

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
