import { describe, it, expect, vi } from 'vitest';
import { applySubmitOrder, loadGroupsWithRecovery } from './useGroups';
import { calcUnpaidTotal } from '../calc/calc';
import type { LoadResult, StorageRepository } from '../data/repository';
import type { Group, Order } from '../types';

function makeGroup(id: string): Group {
  return {
    id,
    name: `團 ${id}`,
    products: [],
    orders: [],
    createdAt: 0,
    closed: false,
  };
}

/** 可注入 loadGroups 回傳值、並記錄 saveGroups 呼叫的假 repository。 */
function fakeRepo(loadResult: LoadResult): {
  repo: StorageRepository;
  saved: Group[][];
} {
  const saved: Group[][] = [];
  const repo: StorageRepository = {
    loadGroups: async () => loadResult,
    saveGroups: async (groups) => {
      saved.push(groups);
    },
  };
  return { repo, saved };
}

describe('loadGroupsWithRecovery', () => {
  it('毀損時把清理後的乾淨資料立即寫回（打破重複毀損警告迴圈）', async () => {
    const clean = [makeGroup('a')];
    const { repo, saved } = fakeRepo({ groups: clean, corrupted: true });
    const result = await loadGroupsWithRecovery(repo);

    expect(result.corrupted).toBe(true);
    expect(result.groups).toBe(clean);
    // 關鍵：毀損清理後必須寫回一次，且寫回的是清理後的乾淨資料。
    expect(saved).toHaveLength(1);
    expect(saved[0]).toBe(clean);
  });

  it('未毀損時不寫回（避免多餘寫入）', async () => {
    const { repo, saved } = fakeRepo({ groups: [makeGroup('a')], corrupted: false });
    await loadGroupsWithRecovery(repo);
    expect(saved).toHaveLength(0);
  });

  it('寫回失敗只記 log、不丟例外（仍回傳讀到的乾淨資料）', async () => {
    const clean = [makeGroup('a')];
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const repo: StorageRepository = {
      loadGroups: async () => ({ groups: clean, corrupted: true }),
      saveGroups: async () => {
        throw new Error('quota 滿');
      },
    };

    const result = await loadGroupsWithRecovery(repo);
    expect(result.groups).toBe(clean);
    expect(errSpy).toHaveBeenCalled();
    errSpy.mockRestore();
  });
});

describe('applySubmitOrder', () => {
  const makeId = () => 'o_new';

  it('同名覆蓋：換品項、保留 id/createdAt', () => {
    const orders: Order[] = [
      { id: 'o1', buyerName: '小明', createdAt: 111, items: [{ productId: 'a', qty: 1 }] },
    ];
    const next = applySubmitOrder(orders, '小明', [{ productId: 'a', qty: 3 }], makeId, 999);
    expect(next).toHaveLength(1);
    expect(next[0].id).toBe('o1');
    expect(next[0].createdAt).toBe(111);
    expect(next[0].items).toEqual([{ productId: 'a', qty: 3 }]);
  });

  it('【Blocking 修正】同名覆蓋已付訂單 → paid 歸零，重新計入未收款', () => {
    const products = [{ id: 'a', name: '便當', price: 100 }];
    const before: Group = {
      id: 'g1',
      name: 't',
      products,
      orders: [
        { id: 'o1', buyerName: '小明', createdAt: 0, paid: true, items: [{ productId: 'a', qty: 1 }] },
      ],
      createdAt: 0,
      closed: false,
    };
    // 收款前：小明已付 → 未收款 0（結清）。
    expect(calcUnpaidTotal(before)).toBe(0);

    // 小明改單加量（1→2）覆蓋。
    const nextOrders = applySubmitOrder(
      before.orders,
      '小明',
      [{ productId: 'a', qty: 2 }],
      makeId,
      500,
    );
    expect(nextOrders[0].paid).toBeUndefined(); // paid 被重置

    const after: Group = { ...before, orders: nextOrders };
    // 改單後應重新計入未收款：100 × 2 = 200，而非誤顯已結清。
    expect(calcUnpaidTotal(after)).toBe(200);
  });

  it('不同名 → 新增一張，makeId / now 生效', () => {
    const orders: Order[] = [
      { id: 'o1', buyerName: '小明', createdAt: 0, items: [] },
    ];
    const next = applySubmitOrder(orders, '小華', [{ productId: 'a', qty: 1 }], makeId, 777);
    expect(next).toHaveLength(2);
    expect(next[1]).toEqual({
      id: 'o_new',
      buyerName: '小華',
      createdAt: 777,
      items: [{ productId: 'a', qty: 1 }],
    });
  });
});
