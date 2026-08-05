import { describe, it, expect } from 'vitest';
import { decodeReceipt, encodeReceipt, type ReceiptSource } from './receiptCodec';
import { encodeBase64Url } from './base64url';
import { MAX_BUYER_NAME_LENGTH, MAX_ITEM_QTY, MAX_NOTE_LENGTH } from '../types';

/** 手造一段合法簽章的 GBR1 回單碼，供邊界測試組出「合法簽章但欄位超限」的壞碼。 */
function makeRawCode(obj: unknown): string {
  const payload = encodeBase64Url(JSON.stringify(obj));
  let h = 5381;
  for (let i = 0; i < payload.length; i += 1) h = ((h << 5) + h + payload.charCodeAt(i)) >>> 0;
  return `GBR1.${payload}.${h.toString(36)}`;
}

const source: ReceiptSource = {
  groupId: 'g_abc',
  buyerName: '小明',
  note: '不要辣',
  items: [
    { productId: 'prod_1', qty: 2 },
    { productId: 'prod_2', qty: 1 },
  ],
};

describe('encode/decode receipt — roundtrip', () => {
  it('編碼再解碼還原訂單（含中文名 / 備註）', () => {
    const parsed = decodeReceipt(encodeReceipt(source));
    expect(parsed).not.toBeNull();
    expect(parsed!.groupId).toBe('g_abc');
    expect(parsed!.buyerName).toBe('小明');
    expect(parsed!.note).toBe('不要辣');
    expect(parsed!.items).toEqual(source.items);
  });

  it('回單碼帶 GBR1 前綴與 crc（三段）', () => {
    const code = encodeReceipt(source);
    expect(code.startsWith('GBR1.')).toBe(true);
    expect(code.split('.')).toHaveLength(3);
  });

  it('編碼時濾掉 qty<=0 的品項', () => {
    const parsed = decodeReceipt(
      encodeReceipt({
        ...source,
        items: [
          { productId: 'prod_1', qty: 2 },
          { productId: 'prod_2', qty: 0 },
        ],
      }),
    );
    expect(parsed!.items).toEqual([{ productId: 'prod_1', qty: 2 }]);
  });
});

describe('decodeReceipt — 從 LINE 訊息雜訊中擷取', () => {
  it('前後夾帶其他文字仍能抓出回單碼', () => {
    const code = encodeReceipt(source);
    const message = `我要跟團！這是我的回單碼：${code} 謝謝主揪 🙏`;
    const parsed = decodeReceipt(message);
    expect(parsed!.buyerName).toBe('小明');
  });
});

describe('decodeReceipt — 壞碼容錯（特別厚，一律不 crash）', () => {
  it('空字串 → null', () => {
    expect(decodeReceipt('')).toBeNull();
  });
  it('沒有回單碼的純文字 → null', () => {
    expect(decodeReceipt('哈囉我要跟團但忘了貼碼')).toBeNull();
  });
  it('crc 被竄改 / 不符 → null', () => {
    const code = encodeReceipt(source);
    const parts = code.split('.');
    const tampered = `${parts[0]}.${parts[1]}.zzzz`;
    expect(decodeReceipt(tampered)).toBeNull();
  });
  it('payload 被截斷（crc 對不上）→ null，不丟例外', () => {
    const code = encodeReceipt(source);
    const parts = code.split('.');
    const truncated = `${parts[0]}.${parts[1].slice(0, -4)}.${parts[2]}`;
    expect(() => decodeReceipt(truncated)).not.toThrow();
    expect(decodeReceipt(truncated)).toBeNull();
  });
  it('crc 對得上但 payload 非 JSON → null', () => {
    // 手造：payload 是可解碼但非 JSON 的 base64url，crc 用真實算法補上（模擬進階壞碼）。
    const payload = encodeBase64Url('not json at all');
    // 借用內部同款 checksum：djb2/base36。這裡直接算一份對照。
    let h = 5381;
    for (let i = 0; i < payload.length; i += 1) h = ((h << 5) + h + payload.charCodeAt(i)) >>> 0;
    const code = `GBR1.${payload}.${h.toString(36)}`;
    expect(decodeReceipt(code)).toBeNull();
  });
  it('版本不符 → null', () => {
    const payload = encodeBase64Url(JSON.stringify({ v: 9, g: 'x', b: 'n', it: [] }));
    let h = 5381;
    for (let i = 0; i < payload.length; i += 1) h = ((h << 5) + h + payload.charCodeAt(i)) >>> 0;
    expect(decodeReceipt(`GBR1.${payload}.${h.toString(36)}`)).toBeNull();
  });
  it('買家名字空白 → null', () => {
    const payload = encodeBase64Url(JSON.stringify({ v: 1, g: 'x', b: '   ', it: [] }));
    let h = 5381;
    for (let i = 0; i < payload.length; i += 1) h = ((h << 5) + h + payload.charCodeAt(i)) >>> 0;
    expect(decodeReceipt(`GBR1.${payload}.${h.toString(36)}`)).toBeNull();
  });
  it('壞掉的品項濾掉、好的保留（空 items 也允許）', () => {
    const payload = encodeBase64Url(
      JSON.stringify({
        v: 1,
        g: 'x',
        b: '小華',
        it: [
          ['ok', 3],
          ['bad', 0], // qty 0 濾掉
          ['neg', -1], // 負數濾掉
          'nope', // 型別錯濾掉
        ],
      }),
    );
    let h = 5381;
    for (let i = 0; i < payload.length; i += 1) h = ((h << 5) + h + payload.charCodeAt(i)) >>> 0;
    const parsed = decodeReceipt(`GBR1.${payload}.${h.toString(36)}`);
    expect(parsed!.items).toEqual([{ productId: 'ok', qty: 3 }]);
  });
});

describe('【Major 修正】decodeReceipt — 欄位上限：超限判整筆無效，不靜默 clamp', () => {
  it(`買家名字剛好等於上限（${MAX_BUYER_NAME_LENGTH} 字）→ 正常解出`, () => {
    const name = '名'.repeat(MAX_BUYER_NAME_LENGTH);
    const code = makeRawCode({ v: 1, g: 'g1', b: name, it: [['p1', 1]] });
    const parsed = decodeReceipt(code);
    expect(parsed!.buyerName).toBe(name);
  });

  it(`買家名字超過上限（${MAX_BUYER_NAME_LENGTH + 1} 字）→ 整筆判無效（null），不是靜默截斷`, () => {
    const name = '名'.repeat(MAX_BUYER_NAME_LENGTH + 1);
    const code = makeRawCode({ v: 1, g: 'g1', b: name, it: [['p1', 1]] });
    expect(decodeReceipt(code)).toBeNull();
  });

  it(`品項數量剛好等於上限（${MAX_ITEM_QTY}）→ 正常解出`, () => {
    const code = makeRawCode({ v: 1, g: 'g1', b: '小明', it: [['p1', MAX_ITEM_QTY]] });
    const parsed = decodeReceipt(code);
    expect(parsed!.items).toEqual([{ productId: 'p1', qty: MAX_ITEM_QTY }]);
  });

  it(`品項數量超過上限（${MAX_ITEM_QTY + 1}）→ 整筆判無效（null），不是靜默 clamp 回上限`, () => {
    const code = makeRawCode({ v: 1, g: 'g1', b: '小明', it: [['p1', MAX_ITEM_QTY + 1]] });
    expect(decodeReceipt(code)).toBeNull();
  });

  it('多個品項中只要有一項超限，整張回單碼都判無效（不是只丟掉那一項）', () => {
    const code = makeRawCode({
      v: 1,
      g: 'g1',
      b: '小明',
      it: [
        ['ok', 1],
        ['overflow', MAX_ITEM_QTY + 1],
      ],
    });
    expect(decodeReceipt(code)).toBeNull();
  });

  it(`【QA 複審 non-blocking #2】備註剛好等於上限（${MAX_NOTE_LENGTH} 字）→ 正常解出`, () => {
    const note = '不'.repeat(MAX_NOTE_LENGTH);
    const code = makeRawCode({ v: 1, g: 'g1', b: '小明', o: note, it: [['p1', 1]] });
    const parsed = decodeReceipt(code);
    expect(parsed!.note).toBe(note);
  });

  it(`【QA 複審 non-blocking #2】備註超過上限（${MAX_NOTE_LENGTH + 1} 字）→ 整筆判無效（null），不是靜默截斷`, () => {
    const note = '不'.repeat(MAX_NOTE_LENGTH + 1);
    const code = makeRawCode({ v: 1, g: 'g1', b: '小明', o: note, it: [['p1', 1]] });
    expect(decodeReceipt(code)).toBeNull();
  });
});
