// @vitest-environment jsdom
//
// useGroups() 是唯一的資料存取入口，內部直接綁定真實的 LocalStorageRepository（模組層級
// 單例），要驗證 submitOrder 的回傳值與多分頁 'storage' 事件同步行為，最貼近實況的作法
// 就是用 @testing-library/react 的 renderHook 掛載真正的 hook、配上 jsdom 提供的真實
// localStorage / window 事件機制，而不是再造一個假 repo。

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useGroups } from './useGroups';
import { STORAGE_KEY } from '../data/localStorageRepository';
import type { Group } from '../types';

function seedGroup(overrides: Partial<Group> = {}): Group {
  return {
    id: 'g1',
    name: '測試團',
    products: [{ id: 'p1', name: '珍奶', price: 60 }],
    orders: [],
    createdAt: 0,
    closed: false,
    ...overrides,
  };
}

describe('useGroups — submitOrder 回傳結果（【Blocking 修正】不再假成功）', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('正常送單 → { ok: true }，且訂單真的寫進 groups', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([seedGroup()]));
    const { result } = renderHook(() => useGroups());
    await waitFor(() => expect(result.current.loaded).toBe(true));

    let submitResult;
    act(() => {
      submitResult = result.current.submitOrder('g1', '小明', [{ productId: 'p1', qty: 2 }], '不要辣');
    });

    expect(submitResult).toEqual({ ok: true });
    await waitFor(() => {
      const order = result.current.groups[0].orders.find((o) => o.buyerName === '小明');
      expect(order).toBeDefined();
      expect(order!.note).toBe('不要辣');
    });
  });

  it('團已手動截止 → { ok: false, reason: "closed" }，不寫入訂單（不是假成功）', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([seedGroup({ closed: true })]));
    const { result } = renderHook(() => useGroups());
    await waitFor(() => expect(result.current.loaded).toBe(true));

    let submitResult;
    act(() => {
      submitResult = result.current.submitOrder('g1', '小明', [{ productId: 'p1', qty: 1 }]);
    });

    expect(submitResult).toEqual({ ok: false, reason: 'closed' });
    expect(result.current.groups[0].orders).toHaveLength(0);
  });

  it('團的截止時間已過（deadlineAt 在過去）→ { ok: false, reason: "closed" }', async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([seedGroup({ deadlineAt: Date.now() - 60_000 })]),
    );
    const { result } = renderHook(() => useGroups());
    await waitFor(() => expect(result.current.loaded).toBe(true));

    let submitResult;
    act(() => {
      submitResult = result.current.submitOrder('g1', '小明', [{ productId: 'p1', qty: 1 }]);
    });

    expect(submitResult).toEqual({ ok: false, reason: 'closed' });
    expect(result.current.groups[0].orders).toHaveLength(0);
  });

  it('找不到對應團 → { ok: false, reason: "group-not-found" }', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([seedGroup()]));
    const { result } = renderHook(() => useGroups());
    await waitFor(() => expect(result.current.loaded).toBe(true));

    let submitResult;
    act(() => {
      submitResult = result.current.submitOrder('no-such-group', '小明', [{ productId: 'p1', qty: 1 }]);
    });

    expect(submitResult).toEqual({ ok: false, reason: 'group-not-found' });
  });

  it('買家名字空白 → { ok: false, reason: "empty-name" }', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([seedGroup()]));
    const { result } = renderHook(() => useGroups());
    await waitFor(() => expect(result.current.loaded).toBe(true));

    let submitResult;
    act(() => {
      submitResult = result.current.submitOrder('g1', '   ', [{ productId: 'p1', qty: 1 }]);
    });

    expect(submitResult).toEqual({ ok: false, reason: 'empty-name' });
  });
});

describe('useGroups — 多分頁 storage 事件同步（【Blocking 修正】避免整包互吃）', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('收到本 app key 的 storage 事件 → 以 localStorage 目前內容重新載入 groups', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([seedGroup({ id: 'g1', name: '原本的團' })]));
    const { result } = renderHook(() => useGroups());
    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.groups).toHaveLength(1);

    // 模擬「別的分頁」寫入了一份不同的資料（多一個團）。真實瀏覽器只會在其他分頁收到
    // 'storage' 事件（自己那分頁 setItem 不會觸發），但我們只是要驗證 handler 邏輯本身，
    // 直接改寫 localStorage 再手動 dispatch 這個事件即可。
    const otherTabGroups = [
      seedGroup({ id: 'g1', name: '原本的團' }),
      seedGroup({ id: 'g2', name: '別分頁新開的團' }),
    ];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(otherTabGroups));

    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', { key: STORAGE_KEY, newValue: JSON.stringify(otherTabGroups) }),
      );
    });

    await waitFor(() => expect(result.current.groups).toHaveLength(2));
    expect(result.current.groups.map((g) => g.id).sort()).toEqual(['g1', 'g2']);
  });

  it('storage 事件 key 是別的 app（不相關 key）→ 忽略，不重新載入', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([seedGroup()]));
    const { result } = renderHook(() => useGroups());
    await waitFor(() => expect(result.current.loaded).toBe(true));

    // 另一個 key 的變動（例如同網域下別的 app 用的 localStorage key），不該讓這裡重新載入
    // 到跟目前 STORAGE_KEY 無關的內容；用「groups 陣列參照沒變」間接驗證沒有觸發 setGroups。
    const before = result.current.groups;
    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', { key: 'some-other-app:data', newValue: '{}' }),
      );
    });

    // 給一個 microtask 空檔，確保「真的沒有」非同步重新載入在跑。
    await Promise.resolve();
    expect(result.current.groups).toBe(before);
  });

  it('event.key 為 null（localStorage.clear()）→ 視為需要重新同步', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([seedGroup()]));
    const { result } = renderHook(() => useGroups());
    await waitFor(() => expect(result.current.loaded).toBe(true));

    localStorage.clear();
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: null }));
    });

    await waitFor(() => expect(result.current.groups).toHaveLength(0));
  });
});
