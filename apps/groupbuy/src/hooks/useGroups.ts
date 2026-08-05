// 串接 repository 的 React hook。
// 元件只用這個 hook 操作資料，不直接碰 repository / localStorage。

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Group, Order, OrderItem, Product } from '../types';
import { LocalStorageRepository, STORAGE_KEY } from '../data/localStorageRepository';
import type { LoadResult, StorageRepository } from '../data/repository';
import { isGroupClosed } from '../deadline';

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

/** 開團時帶入的單一商品（名稱 + 單價 + 可選圖片 data URL）。 */
export interface NewProduct {
  name: string;
  price: number;
  image?: string;
}

/**
 * submitOrder 的結果：呼叫端（UI）必須依此決定要不要顯示成功畫面 / 錯誤訊息，
 * 不能假設呼叫就一定成功（例如團已截止時，資料層會拒絕寫入）。
 */
export type SubmitOrderResult =
  | { ok: true }
  | { ok: false; reason: 'empty-name' | 'group-not-found' | 'closed' };

/**
 * 建立一個團：把輸入的商品清單正規化成帶 id 的 Product。
 * 名稱空白的品項一律略過（避免建出無名商品）。
 */
function createGroup(
  name: string,
  note: string,
  products: NewProduct[],
  deadlineAt?: number,
): Group {
  const cleanProducts: Product[] = products
    .filter((p) => p.name.trim() !== '')
    .map((p) => ({
      id: genId('prod'),
      name: p.name.trim(),
      price: Number.isFinite(p.price) && p.price >= 0 ? Math.floor(p.price) : 0,
      ...(p.image ? { image: p.image } : {}),
    }));
  const trimmedNote = note.trim();
  return {
    id: genId('g'),
    name: name.trim() || `${new Date().toLocaleDateString('zh-TW')} 團`,
    ...(trimmedNote ? { note: trimmedNote } : {}),
    ...(typeof deadlineAt === 'number' && Number.isFinite(deadlineAt) ? { deadlineAt } : {}),
    products: cleanProducts,
    orders: [],
    createdAt: Date.now(),
    closed: false,
  };
}

/** 正規化備註：空白 / undefined 一律視為「無備註」，避免 `''` 與 `undefined` 被判成不同內容。 */
function normalizeNote(note: string | undefined): string | undefined {
  const trimmed = note?.trim();
  return trimmed ? trimmed : undefined;
}

/** 把品項清單攤成 productId -> 累加數量的 map，比較時忽略陣列順序、合併重複 productId。 */
function toQtyMap(items: OrderItem[]): Map<string, number> {
  const map = new Map<string, number>();
  for (const item of items) map.set(item.productId, (map.get(item.productId) ?? 0) + item.qty);
  return map;
}

/**
 * 判斷「重新送出」的內容是否與既有訂單完全相同（品項＋數量＋備註）。
 * 用於重複匯入 / 重複代填時判斷是否要重置 paid（冪等：內容沒變就不該打回未收款）。
 */
function isSameOrderContent(
  existing: Order,
  items: OrderItem[],
  note: string | undefined,
): boolean {
  if (normalizeNote(existing.note) !== normalizeNote(note)) return false;
  const a = toQtyMap(existing.items);
  const b = toQtyMap(items);
  if (a.size !== b.size) return false;
  for (const [productId, qty] of a) {
    if (b.get(productId) !== qty) return false;
  }
  return true;
}

/**
 * 送單的核心 upsert 邏輯（同名覆蓋 / 新增），抽成純函式方便單元測試。
 *
 * 關鍵財務正確性：同名覆蓋且內容（品項＋數量＋備註）有變動時，paid 一律重置為 undefined
 * （未收款）。理由——改單（尤其加價）等於「重新確認收款」，若沿用舊 paid:true，主揪
 * dashboard 會把改動後的訂單誤算成已結清，造成財務誤報。保留原 id / createdAt（仍是同一個人的單）。
 *
 * 冪等例外：若重新送出的內容跟既有訂單完全相同（例如買家重複貼同一張回單碼、或主揪重複匯入
 * 同一張回單），視為「沒有改動」，保留原本的 paid 狀態，不強制打回未收款。
 */
export function applySubmitOrder(
  orders: Order[],
  buyerName: string,
  cleanItems: OrderItem[],
  note: string | undefined,
  makeId: () => string,
  now: number,
): Order[] {
  const existing = orders.find((o) => o.buyerName === buyerName);
  const cleanNote = normalizeNote(note);
  if (existing) {
    if (isSameOrderContent(existing, cleanItems, cleanNote)) {
      // 內容完全相同：冪等，不改動（含 paid），避免重複匯入把已收款打回未收款。
      return orders;
    }
    return orders.map((o) =>
      o.id === existing.id
        ? { ...o, items: cleanItems, paid: undefined, note: cleanNote }
        : o,
    );
  }
  return [
    ...orders,
    {
      id: makeId(),
      buyerName,
      items: cleanItems,
      createdAt: now,
      ...(cleanNote ? { note: cleanNote } : {}),
    },
  ];
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

  // 多分頁同步（純前端 MVP 合比例的修法，寫回前重讀合併的完整方案留給後端化）：
  // 沒有這段的話，兩個分頁各自持有一份 groups 在記憶體裡，後寫入的分頁整包 saveGroups
  // 會把另一分頁不知道的變動整包覆蓋掉（互吃資料）。'storage' 事件只會在「其他」分頁寫入
  // 同一個 key 時觸發（同一分頁自己 setItem 不會收到），聽到就以 localStorage 最新內容為準
  // 重新 loadGroups 進這個分頁的 React state。
  useEffect(() => {
    if (!loaded) return;
    function handleStorageEvent(event: StorageEvent) {
      // event.key === null 代表 localStorage.clear()（整包被清空），也要處理；
      // 其餘 key 跟本 app 無關，忽略。
      if (event.key !== null && event.key !== STORAGE_KEY) return;
      // 這次的 groups 變動是從別分頁同步進來的，不需要再寫回一次
      //（本來就是從 storage 讀出來的最新內容，寫回是無謂的 round-trip）。
      skipNextSave.current = true;
      repo.loadGroups().then(
        (result) => {
          setGroups(result.groups);
          // 別分頁寫入的資料若剛好也偵測到毀損，一併提示；已經是 true 就不要被蓋回 false。
          setDataCorrupted((prev) => prev || result.corrupted);
        },
        (err) => {
          console.error('多分頁同步：重新載入資料失敗：', err);
        },
      );
    }
    window.addEventListener('storage', handleStorageEvent);
    return () => window.removeEventListener('storage', handleStorageEvent);
  }, [loaded]);

  /** 新增一個團，回傳新團 id（供路由 navigate 進後台）。 */
  const addGroup = useCallback(
    (name: string, note: string, products: NewProduct[], deadlineAt?: number): string => {
      const g = createGroup(name, note, products, deadlineAt);
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
   *
   * 【Blocking 修正】回傳明確的成功 / 失敗結果（含拒絕原因），呼叫端（OrderPage 現場代填、
   * DashboardPage 回單碼匯入）必須依結果決定要不要顯示成功畫面——不能像之前一樣，資料層已截止
   * 靜默不寫入、UI 卻無條件顯示「已送出」的假成功畫面。
   *
   * 實作注意：React 18 的 setState 函式型 updater 不保證同步執行（它會被排入佇列，實際呼叫
   * 時機可能晚於 setGroups() 這行呼叫本身已經返回之後）。所以「找不找得到團 / 團是否已截止」
   * 這個要「立刻同步回傳」給呼叫端的判斷，必須用當下已知最新的 groups（因此 submitOrder 依賴
   * groups，不能再用空依賴陣列）先算好，不能指望在 setGroups 的 updater 內部才寫回一個外層變數
   * 讓呼叫端同步讀到——那個變數在 submitOrder return 的當下很可能還沒被賦值。
   * setGroups 內部仍保留同一道 isGroupClosed 檢查作為寫入當下的最終防線（避免理論上的競態：
   * 例如兩個分頁幾乎同時送單），只是不再靠它來決定同步回傳值。
   */
  const submitOrder = useCallback(
    (groupId: string, buyerName: string, items: OrderItem[], note?: string): SubmitOrderResult => {
      const name = buyerName.trim();
      if (!name) return { ok: false, reason: 'empty-name' };

      const group = groups.find((g) => g.id === groupId);
      if (!group) return { ok: false, reason: 'group-not-found' };
      // 資料層擋已截止（不只靠 UI）：手動 closed 或已過期都一律不接受新單 / 覆蓋。
      if (isGroupClosed(group, Date.now())) return { ok: false, reason: 'closed' };

      const cleanItems = items.filter((i) => i.qty > 0);
      setGroups((prev) =>
        prev.map((g) => {
          if (g.id !== groupId) return g;
          // 寫入當下再擋一次已截止：避免呼叫端讀到上面的同步結果之後、setGroups 實際 commit
          // 之前的極短暫窗口內，團被別的分頁 / 別的操作截止，仍寫入一筆理應被拒絕的訂單。
          if (isGroupClosed(g, Date.now())) return g;
          return {
            ...g,
            orders: applySubmitOrder(g.orders, name, cleanItems, note, () => genId('o'), Date.now()),
          };
        }),
      );
      return { ok: true };
    },
    [groups],
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
