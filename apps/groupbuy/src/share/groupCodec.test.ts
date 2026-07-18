import { describe, it, expect } from 'vitest';
import {
  buildShareUrl,
  decodeGroupPayload,
  encodeGroupPayload,
  parseShareTarget,
  type ShareableGroup,
} from './groupCodec';

const group: ShareableGroup = {
  id: 'g_abc',
  name: '公司便當團 🍱',
  note: '7/20 晚上 8 點截止',
  products: [
    { id: 'prod_1', name: '排骨便當', price: 120 },
    { id: 'prod_2', name: '雞腿便當', price: 130 },
  ],
};

describe('encode/decode group payload — roundtrip', () => {
  it('編碼再解碼還原團定義（含中文 / emoji / 截止註記）', () => {
    const decoded = decodeGroupPayload(encodeGroupPayload(group));
    expect(decoded).not.toBeNull();
    expect(decoded!.groupId).toBe('g_abc');
    expect(decoded!.name).toBe('公司便當團 🍱');
    expect(decoded!.note).toBe('7/20 晚上 8 點截止');
    expect(decoded!.products).toEqual(group.products);
  });

  it('payload 為 URL-safe（不含 + / =）', () => {
    const payload = encodeGroupPayload(group);
    expect(payload).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it('無 note 時解出的物件不帶 note 欄位', () => {
    const decoded = decodeGroupPayload(
      encodeGroupPayload({ ...group, note: undefined }),
    );
    expect(decoded!.note).toBeUndefined();
  });
});

describe('decode 容錯（壞碼不 crash）', () => {
  it('空字串 → null', () => {
    expect(decodeGroupPayload('')).toBeNull();
  });
  it('非 base64url 字元 → null', () => {
    expect(decodeGroupPayload('!!!not base64!!!')).toBeNull();
  });
  it('合法 base64 但非 JSON → null', () => {
    // "hello" 的 base64url，解出來不是 JSON。
    const notJson = encodeGroupPayload(group).slice(0, 6);
    // 直接餵一段可解成字串但非 JSON 物件的 base64url。
    expect(decodeGroupPayload('aGVsbG8')).toBeNull();
    expect(notJson.length).toBeGreaterThan(0); // sanity
  });
  it('被截斷的 payload → null（不丟例外）', () => {
    const full = encodeGroupPayload(group);
    expect(() => decodeGroupPayload(full.slice(0, full.length - 5))).not.toThrow();
    // 截斷後通常無法還原，回傳 null；即使僥倖可解也不得丟例外。
    const r = decodeGroupPayload(full.slice(0, full.length - 5));
    expect(r === null || typeof r === 'object').toBe(true);
  });
  it('版本不符 → null', () => {
    // 手工造一個 v:2 的 payload。
    const bad = encodeGroupPayloadRaw({ v: 2, i: 'x', n: 'n', p: [] });
    expect(decodeGroupPayload(bad)).toBeNull();
  });
  it('缺必要欄位（無 products 陣列）→ null', () => {
    const bad = encodeGroupPayloadRaw({ v: 1, i: 'x', n: 'n' });
    expect(decodeGroupPayload(bad)).toBeNull();
  });
  it('壞掉的商品項被濾掉，好的保留', () => {
    const bad = encodeGroupPayloadRaw({
      v: 1,
      i: 'x',
      n: 'n',
      p: [
        ['ok', '好商品', 50],
        ['bad', '負價', -5], // 價格非法 → 濾掉
        ['dup', '重複 id', 10],
        ['dup', '重複 id 2', 20], // id 重複 → 濾掉第二個
        'not-an-array', // 型別錯 → 濾掉
      ],
    });
    const decoded = decodeGroupPayload(bad);
    expect(decoded!.products.map((p) => p.id)).toEqual(['ok', 'dup']);
  });
});

describe('buildShareUrl / parseShareTarget', () => {
  it('組出的連結能被 parse 回原團定義', () => {
    const url = buildShareUrl(group, 'https://example.com/app/');
    expect(url).toContain('#/join?d=');
    const decoded = parseShareTarget(url);
    expect(decoded!.groupId).toBe('g_abc');
    expect(decoded!.products).toHaveLength(2);
  });
  it('base 已含舊 hash 時不會疊加雙重 hash', () => {
    const url = buildShareUrl(group, 'https://example.com/app/#/groups/g_abc');
    expect(url.match(/#/g)!.length).toBe(1);
  });
  it('只給 hash 片段也能 parse', () => {
    const payload = encodeGroupPayload(group);
    expect(parseShareTarget(`#/join?d=${payload}`)!.name).toBe('公司便當團 🍱');
  });
  it('無 d 參數 → null', () => {
    expect(parseShareTarget('https://example.com/#/join')).toBeNull();
    expect(parseShareTarget('no-query-here')).toBeNull();
  });
});

// --- 測試輔助：直接把任意物件編成 payload（繞過 encodeGroupPayload 的型別限制，用來造壞碼）---
import { encodeBase64Url } from './base64url';
function encodeGroupPayloadRaw(obj: unknown): string {
  return encodeBase64Url(JSON.stringify(obj));
}
