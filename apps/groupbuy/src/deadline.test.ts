import { describe, it, expect } from 'vitest';
import { formatCountdown, isExpired, isGroupClosed } from './deadline';

const NOW = 1_000_000_000_000; // 固定基準時間

describe('isExpired', () => {
  it('無截止時間 → 永不過期', () => {
    expect(isExpired(undefined, NOW)).toBe(false);
  });
  it('非法時間戳（NaN）→ 不過期', () => {
    expect(isExpired(NaN, NOW)).toBe(false);
  });
  it('now 超過 deadline → 過期', () => {
    expect(isExpired(NOW - 1, NOW)).toBe(true);
  });
  it('now 等於 deadline → 尚未過期（> 才算）', () => {
    expect(isExpired(NOW, NOW)).toBe(false);
  });
  it('deadline 在未來 → 未過期', () => {
    expect(isExpired(NOW + 1000, NOW)).toBe(false);
  });
});

describe('formatCountdown', () => {
  it('無截止時間 → null', () => {
    expect(formatCountdown(undefined, NOW)).toBeNull();
  });
  it('已過期 → 已截止', () => {
    expect(formatCountdown(NOW - 1, NOW)).toBe('已截止');
  });
  it('剩 2 天多 → 還剩 2 天', () => {
    expect(formatCountdown(NOW + 2.5 * 24 * 3600_000, NOW)).toBe('還剩 2 天');
  });
  it('剩 3 小時多 → 還剩 3 小時', () => {
    expect(formatCountdown(NOW + 3.5 * 3600_000, NOW)).toBe('還剩 3 小時');
  });
  it('剩 10 分鐘多 → 還剩 10 分鐘', () => {
    expect(formatCountdown(NOW + 10.5 * 60_000, NOW)).toBe('還剩 10 分鐘');
  });
  it('剩不到 1 分鐘 → 即將截止', () => {
    expect(formatCountdown(NOW + 30_000, NOW)).toBe('即將截止');
  });
});

describe('isGroupClosed', () => {
  it('手動 closed → true（不論到期）', () => {
    expect(isGroupClosed({ closed: true }, NOW)).toBe(true);
  });
  it('未 closed 但已過期 → true', () => {
    expect(isGroupClosed({ closed: false, deadlineAt: NOW - 1 }, NOW)).toBe(true);
  });
  it('未 closed 未過期 → false', () => {
    expect(isGroupClosed({ closed: false, deadlineAt: NOW + 1000 }, NOW)).toBe(false);
  });
  it('未 closed 無截止時間 → false', () => {
    expect(isGroupClosed({ closed: false }, NOW)).toBe(false);
  });
});
