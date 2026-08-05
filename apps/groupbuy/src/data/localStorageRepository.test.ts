// @vitest-environment jsdom
//
// localStorageRepository 是「唯一存取真實 localStorage 的地方」，也是資料毀損防線的
// 最後一道關卡——runtime 逐欄位驗證讀回來的資料，壞的整筆丟棄並備份。這份測試逐分支
// 覆蓋每一種「壞資料」形狀，以及 StorageError（quota 滿 / storage 被停用）路徑。
//
// 需要 jsdom：LocalStorageRepository 直接讀寫全域 localStorage，vitest 預設的 'node'
// environment 沒有這個全域物件，故本檔用 @vitest-environment jsdom pragma 覆蓋。

import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORRUPT_BACKUP_KEY,
  LocalStorageRepository,
  STORAGE_KEY,
  StorageError,
} from './localStorageRepository';
import { MAX_BUYER_NAME_LENGTH, MAX_ITEM_QTY } from '../types';
import type { Group } from '../types';

function makeValidGroup(overrides: Partial<Group> = {}): Group {
  return {
    id: 'g1',
    name: '週五下午茶團',
    products: [{ id: 'p1', name: '珍奶', price: 60 }],
    orders: [{ id: 'o1', buyerName: '小明', createdAt: 1000, items: [{ productId: 'p1', qty: 2 }] }],
    createdAt: 0,
    closed: false,
    ...overrides,
  };
}

describe('LocalStorageRepository.loadGroups', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('key 不存在 → 空陣列、未毀損', async () => {
    const repo = new LocalStorageRepository();
    const result = await repo.loadGroups();
    expect(result).toEqual({ groups: [], corrupted: false });
  });

  it('讀到合法資料 → 原樣還原、未毀損', async () => {
    const group = makeValidGroup();
    localStorage.setItem(STORAGE_KEY, JSON.stringify([group]));
    const repo = new LocalStorageRepository();
    const result = await repo.loadGroups();
    expect(result.corrupted).toBe(false);
    expect(result.groups).toEqual([group]);
  });

  it('JSON 整包壞掉（無法 parse）→ 空陣列、已毀損、備份原始字串', async () => {
    localStorage.setItem(STORAGE_KEY, '{not valid json');
    const repo = new LocalStorageRepository();
    const result = await repo.loadGroups();
    expect(result).toEqual({ groups: [], corrupted: true });
    expect(localStorage.getItem(CORRUPT_BACKUP_KEY)).toBe('{not valid json');
  });

  it('資料不是陣列（例如整包變成物件）→ 空陣列、已毀損、備份原始字串', async () => {
    const raw = JSON.stringify({ oops: 'not an array' });
    localStorage.setItem(STORAGE_KEY, raw);
    const repo = new LocalStorageRepository();
    const result = await repo.loadGroups();
    expect(result).toEqual({ groups: [], corrupted: true });
    expect(localStorage.getItem(CORRUPT_BACKUP_KEY)).toBe(raw);
  });

  it('localStorage.getItem 丟例外（storage 被停用）→ 視為空資料，不視為毀損', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });
    const repo = new LocalStorageRepository();
    const result = await repo.loadGroups();
    expect(result).toEqual({ groups: [], corrupted: false });
    expect(errSpy).toHaveBeenCalled();
  });

  it('一筆合法一筆毀損 → 合法留下、毀損那筆整筆丟棄，corrupted=true 且備份原始內容', async () => {
    const good = makeValidGroup({ id: 'good' });
    const bad = { id: 'bad', name: 123 /* 型別錯 */ };
    const raw = JSON.stringify([good, bad]);
    localStorage.setItem(STORAGE_KEY, raw);
    const repo = new LocalStorageRepository();
    const result = await repo.loadGroups();
    expect(result.corrupted).toBe(true);
    expect(result.groups).toEqual([good]);
    expect(localStorage.getItem(CORRUPT_BACKUP_KEY)).toBe(raw);
  });

  describe('group 欄位逐一毀損（每種都應整筆丟棄該 group）', () => {
    const cases: Array<[string, (g: Group) => unknown]> = [
      ['id 缺失', (g) => ({ ...g, id: undefined })],
      ['id 為空字串', (g) => ({ ...g, id: '' })],
      ['name 型別錯', (g) => ({ ...g, name: 123 })],
      ['createdAt 型別錯', (g) => ({ ...g, createdAt: 'yesterday' })],
      ['createdAt 為 NaN', (g) => ({ ...g, createdAt: NaN })],
      ['closed 型別錯', (g) => ({ ...g, closed: 'no' })],
      ['note 型別錯（存在但非字串）', (g) => ({ ...g, note: 123 })],
      ['deadlineAt 型別錯（存在但非數字）', (g) => ({ ...g, deadlineAt: 'soon' })],
      ['deadlineAt 為 NaN', (g) => ({ ...g, deadlineAt: NaN })],
      ['products 不是陣列', (g) => ({ ...g, products: 'nope' })],
      ['orders 不是陣列', (g) => ({ ...g, orders: 'nope' })],
      [
        '商品 id 重複（撞單）',
        (g) => ({
          ...g,
          products: [
            { id: 'dup', name: 'A', price: 1 },
            { id: 'dup', name: 'B', price: 2 },
          ],
        }),
      ],
    ];

    for (const [label, mutate] of cases) {
      it(`${label} → 整團判無效`, async () => {
        const bad = mutate(makeValidGroup());
        localStorage.setItem(STORAGE_KEY, JSON.stringify([bad]));
        const repo = new LocalStorageRepository();
        const result = await repo.loadGroups();
        expect(result.groups).toEqual([]);
        expect(result.corrupted).toBe(true);
      });
    }

    it('note / deadlineAt 缺欄位（舊資料，undefined）→ 合法', async () => {
      const group = makeValidGroup();
      delete (group as { note?: string }).note;
      delete (group as { deadlineAt?: number }).deadlineAt;
      localStorage.setItem(STORAGE_KEY, JSON.stringify([group]));
      const repo = new LocalStorageRepository();
      const result = await repo.loadGroups();
      expect(result.corrupted).toBe(false);
      expect(result.groups).toHaveLength(1);
    });
  });

  describe('product 欄位逐一毀損', () => {
    const cases: Array<[string, (p: unknown) => unknown]> = [
      ['id 缺失', () => ({ name: 'A', price: 1 })],
      ['price 為負數', (p) => ({ ...(p as object), price: -1 })],
      ['price 非整數', (p) => ({ ...(p as object), price: 1.5 })],
      ['image 不是 data:image/ 開頭（XSS 防線）', (p) => ({ ...(p as object), image: 'javascript:alert(1)' })],
    ];
    for (const [label, mutate] of cases) {
      it(`${label} → 整團判無效`, async () => {
        const group = makeValidGroup({ products: [mutate({ id: 'p1', name: 'A', price: 1 }) as never] });
        localStorage.setItem(STORAGE_KEY, JSON.stringify([group]));
        const repo = new LocalStorageRepository();
        const result = await repo.loadGroups();
        expect(result.groups).toEqual([]);
        expect(result.corrupted).toBe(true);
      });
    }

    it('image 為合法 data:image/ URL → 合法', async () => {
      const group = makeValidGroup({
        products: [{ id: 'p1', name: 'A', price: 1, image: 'data:image/jpeg;base64,AAAA' }],
      });
      localStorage.setItem(STORAGE_KEY, JSON.stringify([group]));
      const repo = new LocalStorageRepository();
      const result = await repo.loadGroups();
      expect(result.corrupted).toBe(false);
    });
  });

  describe('order 欄位逐一毀損（【Blocking/Major 修正】note 選填、qty/buyerName 上限）', () => {
    const cases: Array<[string, (o: unknown) => unknown]> = [
      ['id 缺失', () => ({ buyerName: '小明', createdAt: 0, items: [] })],
      [
        `buyerName 超過上限（${MAX_BUYER_NAME_LENGTH + 1} 字）`,
        (o) => ({ ...(o as object), buyerName: '名'.repeat(MAX_BUYER_NAME_LENGTH + 1) }),
      ],
      ['createdAt 型別錯', (o) => ({ ...(o as object), createdAt: 'now' })],
      ['paid 型別錯（存在但非 boolean）', (o) => ({ ...(o as object), paid: 'yes' })],
      ['note 型別錯（存在但非字串）', (o) => ({ ...(o as object), note: 123 })],
      ['items 不是陣列', (o) => ({ ...(o as object), items: 'nope' })],
      ['items 內有品項 qty 非整數', (o) => ({ ...(o as object), items: [{ productId: 'p1', qty: 1.5 }] })],
      ['items 內有品項 qty 為負數', (o) => ({ ...(o as object), items: [{ productId: 'p1', qty: -1 }] })],
      [
        `items 內有品項 qty 超過上限（${MAX_ITEM_QTY + 1}）`,
        (o) => ({ ...(o as object), items: [{ productId: 'p1', qty: MAX_ITEM_QTY + 1 }] }),
      ],
    ];
    for (const [label, mutate] of cases) {
      it(`${label} → 整團判無效`, async () => {
        const baseOrder = { id: 'o1', buyerName: '小明', createdAt: 0, items: [{ productId: 'p1', qty: 1 }] };
        const group = makeValidGroup({ orders: [mutate(baseOrder) as never] });
        localStorage.setItem(STORAGE_KEY, JSON.stringify([group]));
        const repo = new LocalStorageRepository();
        const result = await repo.loadGroups();
        expect(result.groups).toEqual([]);
        expect(result.corrupted).toBe(true);
      });
    }

    it(`buyerName 剛好等於上限（${MAX_BUYER_NAME_LENGTH} 字）→ 合法`, async () => {
      const group = makeValidGroup({
        orders: [
          {
            id: 'o1',
            buyerName: '名'.repeat(MAX_BUYER_NAME_LENGTH),
            createdAt: 0,
            items: [{ productId: 'p1', qty: 1 }],
          },
        ],
      });
      localStorage.setItem(STORAGE_KEY, JSON.stringify([group]));
      const repo = new LocalStorageRepository();
      const result = await repo.loadGroups();
      expect(result.corrupted).toBe(false);
    });

    it(`items 品項 qty 剛好等於上限（${MAX_ITEM_QTY}）→ 合法`, async () => {
      const group = makeValidGroup({
        orders: [{ id: 'o1', buyerName: '小明', createdAt: 0, items: [{ productId: 'p1', qty: MAX_ITEM_QTY }] }],
      });
      localStorage.setItem(STORAGE_KEY, JSON.stringify([group]));
      const repo = new LocalStorageRepository();
      const result = await repo.loadGroups();
      expect(result.corrupted).toBe(false);
    });

    it('【Blocking 修正】order 帶 note（買家備註）→ 合法保留；沒有 note（舊資料）也合法', async () => {
      const withNote = makeValidGroup({
        id: 'g-with-note',
        orders: [
          { id: 'o1', buyerName: '小明', createdAt: 0, note: '不要辣', items: [{ productId: 'p1', qty: 1 }] },
        ],
      });
      const withoutNote = makeValidGroup({
        id: 'g-without-note',
        orders: [{ id: 'o2', buyerName: '小華', createdAt: 0, items: [{ productId: 'p1', qty: 1 }] }],
      });
      localStorage.setItem(STORAGE_KEY, JSON.stringify([withNote, withoutNote]));
      const repo = new LocalStorageRepository();
      const result = await repo.loadGroups();
      expect(result.corrupted).toBe(false);
      expect(result.groups).toHaveLength(2);
      expect(result.groups[0].orders[0].note).toBe('不要辣');
      expect(result.groups[1].orders[0].note).toBeUndefined();
    });
  });
});

describe('LocalStorageRepository.saveGroups', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('正常寫入 → 讀回同樣的資料', async () => {
    const repo = new LocalStorageRepository();
    const group = makeValidGroup();
    await repo.saveGroups([group]);
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!)).toEqual([group]);
  });

  it('localStorage.setItem 丟例外（quota 滿）→ 丟 StorageError，訊息友善', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('QuotaExceededError');
    });
    const repo = new LocalStorageRepository();
    await expect(repo.saveGroups([makeValidGroup()])).rejects.toBeInstanceOf(StorageError);
    await expect(repo.saveGroups([makeValidGroup()])).rejects.toThrow('本機儲存失敗');
  });

  it('資料無法序列化（circular reference）→ 丟 StorageError', async () => {
    const repo = new LocalStorageRepository();
    const circular: Record<string, unknown> = {};
    circular.self = circular;
    // Group 型別本來不該長這樣，這裡刻意用 as never 塞進去模擬「序列化失敗」這個防線。
    await expect(repo.saveGroups(circular as never)).rejects.toBeInstanceOf(StorageError);
    await expect(repo.saveGroups(circular as never)).rejects.toThrow('序列化失敗');
  });
});
