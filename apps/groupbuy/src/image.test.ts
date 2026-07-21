import { describe, it, expect } from 'vitest';
import { computeScaledSize, estimateDataUrlBytes, estimateGroupsBytes } from './image';

describe('computeScaledSize', () => {
  it('長邊超過上限 → 等比縮到長邊 = maxEdge', () => {
    expect(computeScaledSize(1024, 512, 512)).toEqual({ width: 512, height: 256 });
    expect(computeScaledSize(512, 1024, 512)).toEqual({ width: 256, height: 512 });
  });
  it('小於上限 → 不放大', () => {
    expect(computeScaledSize(100, 80, 512)).toEqual({ width: 100, height: 80 });
  });
  it('正好等於上限 → 不變', () => {
    expect(computeScaledSize(512, 300, 512)).toEqual({ width: 512, height: 300 });
  });
  it('非法尺寸 → 0', () => {
    expect(computeScaledSize(0, 100)).toEqual({ width: 0, height: 0 });
    expect(computeScaledSize(-5, 100)).toEqual({ width: 0, height: 0 });
  });
  it('四捨五入到整數像素', () => {
    // 300x100 縮到長邊 128：scale=128/300 → 高 = round(100*0.4267)=43
    expect(computeScaledSize(300, 100, 128)).toEqual({ width: 128, height: 43 });
  });
});

describe('estimateDataUrlBytes', () => {
  it('估算 base64 payload 位元組數（含 padding 校正）', () => {
    // "TWFu" = 3 bytes（無 padding）
    expect(estimateDataUrlBytes('data:image/jpeg;base64,TWFu')).toBe(3);
    // "TQ==" = 1 byte
    expect(estimateDataUrlBytes('data:image/jpeg;base64,TQ==')).toBe(1);
    // "TWE=" = 2 bytes
    expect(estimateDataUrlBytes('data:image/jpeg;base64,TWE=')).toBe(2);
  });
  it('空字串 → 0', () => {
    expect(estimateDataUrlBytes('')).toBe(0);
  });
  it('沒有逗號前綴也能算（純 base64）', () => {
    expect(estimateDataUrlBytes('TWFu')).toBe(3);
  });
});

describe('estimateGroupsBytes', () => {
  it('回傳 JSON 序列化後的字元數', () => {
    expect(estimateGroupsBytes({ a: 1 })).toBe(JSON.stringify({ a: 1 }).length);
  });
  it('無法序列化（循環參照）→ 0，不丟例外', () => {
    const cyclic: Record<string, unknown> = {};
    cyclic.self = cyclic;
    expect(() => estimateGroupsBytes(cyclic)).not.toThrow();
    expect(estimateGroupsBytes(cyclic)).toBe(0);
  });
});
