// 串接 repository 的 React hook。
// 元件只用這個 hook 操作資料，不直接碰 repository / localStorage。

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Group, OrderItem, Product } from '../types';
import { LocalStorageRepository } from '../data/localStorageRepository';
import type { LoadResult, StorageRepository } from '../data/repository';

// 第一版固定用 localStorage 實作；未來要換雲端只改這一行。
const repo: StorageRepository = new LocalStorageRepository();

/**
 * 載入並「自我修復」毀損：loadGroups 偵測到毀損（corrupted=true）會丟棄壞資料，
 * 但清理後的乾淨狀態必須「立即寫回」localStorage，否則下次開 app 又讀到同一份
 * 毀損 raw、又丟棄、又警告——形成每次開 app 都跳毀損警告的迴圈。
 *
 * 抽成獨立純邏輯函式（只依賴 StorageRepository interface），方便用 fake repo 單元測試，
 * 不必動用 React render。寫回失敗只記 log、不阻斷載入（讀到的乾淨資料仍可用）。
 */
export async function loadGroupsWithRecovery(
  repository: StorageRepository,
): Promise<LoadResult> {
  const result = await repository.loadGroups();
  if (result.corrupted) {
    try {
      await repository.saveGroups(result.groups);
    } catch (err) {
      console.error('毀損清理後寫回失敗（下次開啟可能仍會提示毀損）：', err);
    }
  }
  return result;
}

function genId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

/** 開團時帶入的單一商品（名稱 + 單價）。 */
export interface NewProduct {
  name: string;
  price: number;
}

/**
 * 建立一個團：把輸入的商品清單正規化成帶 id 的 Product。
 * 名稱空白的品項一律略過（避免建出無名商品）。
 */
function createGroup(name: string, note: string, products: NewProduct[]): Group {
  const cleanProducts: Product[] = products
    .filter((p) => p.name.trim() !== '')
    .map((p) => ({
      id: genId('prod'),
      name: p.name.trim(),
      price: Number.isFinite(p.price) && p.price >= 0 ? Math.floor(p.price) : 0,
    }));
  const trimmedNote = note.trim();
  return {
    id: genId('g'),
    name: name.trim() || `${new Date().toLocaleDateString('zh-TW')} 團`,
    ...(trimmedNote ? { note: trimmedNote } : {}),
    products: cleanProducts,
    orders: [],
    createdAt: Date.now(),
    closed: false,
  };
}

export function useGroups() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [loaded, setLoaded] = useState(false);
  // 儲存失敗時的錯誤訊息（quota 滿、無痕模式停用 storage 等），供 UI 顯示。
  const [storageError, setStorageError] = useState<string | null>(null);
  // 本機資料毀損、已被丟棄／重置時為 true，供 UI 提示。
  const [dataCorrupted, setDataCorrupted] = useState(false);
  // 避免初次載入時把空資料覆寫回 localStorage。
  const skipNextSave = useRef(true);

  // 初次載入（含毀損自我修復：清理後立即寫回，避免下次開啟重複毀損警告）
  useEffect(() => {
    loadGroupsWithRecovery(repo)
      .then((result) => {
        setGroups(result.groups);
        setDataCorrupted(result.corrupted);
        setLoaded(true);
      })
      .catch((err) => {
        // 即使 repository 換實作或 init 出錯，也不要讓 app 卡在「載入中」。
        console.error('載入資料失敗：', err);
        setGroups([]);
        setDataCorrupted(true);
        setLoaded(true);
      });
  }, []);

  // 任何 groups 變動都寫回本機
  useEffect(() => {
    if (!loaded) return;
    if (skipNextSave.current) {
      skipNextSave.current = false;
      return;
    }
    repo.saveGroups(groups).then(
      () => setStorageError(null),
      (err) => {
        console.error('儲存資料失敗：', err);
        setStorageError(
          err instanceof Error ? err.message : '資料未成功儲存，重整後可能遺失。',
        );
      },
    );
  }, [groups, loaded]);

  /** 新增一個團，回傳新團 id（供路由 navigate 進後台）。 */
  const addGroup = useCallback(
    (name: string, note: string, products: NewProduct[]): string => {
      const g = createGroup(name, note, products);
      setGroups((prev) => [g, ...prev]);
      return g.id;
    },
    [],
  );

  /** 刪除一個團。 */
  const removeGroup = useCallback((id: string) => {
    setGroups((prev) => prev.filter((g) => g.id !== id));
  }, []);

  /** 切換團的截止狀態（進行中 <-> 已截止）。 */
  const toggleClosed = useCallback((id: string) => {
    setGroups((prev) =>
      prev.map((g) => (g.id === id ? { ...g, closed: !g.closed } : g)),
    );
  }, []);

  /**
   * 送出一張訂單（同名覆蓋）。
   * 同一團內若已有相同 buyerName 的訂單，覆蓋其品項內容；否則新增一張。
   * 數量 <= 0 的品項會被濾掉，避免存進空品項。
   */
  const submitOrder = useCallback(
    (groupId: string, buyerName: string, items: OrderItem[]) => {
      const name = buyerName.trim();
      if (!name) return;
      const cleanItems = items.filter((i) => i.qty > 0);
      setGroups((prev) =>
        prev.map((g) => {
          if (g.id !== groupId) return g;
          // 資料層再擋一次已截止（不只靠 UI）：已截止的團一律不接受新單 / 覆蓋，
          // 避免 UI 繞過或競態下寫入。
          if (g.closed) return g;
          const existing = g.orders.find((o) => o.buyerName === name);
          if (existing) {
            // 同名覆蓋：保留原 id 與 createdAt，只換品項內容。
            return {
              ...g,
              orders: g.orders.map((o) =>
                o.id === existing.id ? { ...o, items: cleanItems } : o,
              ),
            };
          }
          return {
            ...g,
            orders: [
              ...g.orders,
              { id: genId('o'), buyerName: name, items: cleanItems, createdAt: Date.now() },
            ],
          };
        }),
      );
    },
    [],
  );

  /** 切換一張訂單的收款狀態（未收 <-> 已收）。 */
  const togglePaid = useCallback((groupId: string, orderId: string) => {
    setGroups((prev) =>
      prev.map((g) =>
        g.id === groupId
          ? {
              ...g,
              orders: g.orders.map((o) =>
                o.id === orderId ? { ...o, paid: !o.paid } : o,
              ),
            }
          : g,
      ),
    );
  }, []);

  /** 刪除一張訂單。 */
  const removeOrder = useCallback((groupId: string, orderId: string) => {
    setGroups((prev) =>
      prev.map((g) =>
        g.id === groupId
          ? { ...g, orders: g.orders.filter((o) => o.id !== orderId) }
          : g,
      ),
    );
  }, []);

  const dismissCorruptNotice = useCallback(() => setDataCorrupted(false), []);

  return {
    groups,
    loaded,
    storageError,
    dataCorrupted,
    addGroup,
    removeGroup,
    toggleClosed,
    submitOrder,
    togglePaid,
    removeOrder,
    dismissCorruptNotice,
  };
}

export type GroupsApi = ReturnType<typeof useGroups>;
