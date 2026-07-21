// 第一版資料實作：存在瀏覽器 localStorage，重整不遺失。
// 介面符合 StorageRepository，未來可替換成雲端 / IndexedDB 版本。
// 逐層 runtime 驗證讀回來的結構，壞的團整筆丟棄並備份原始內容。

import type { Group, Order, OrderItem, Product } from '../types';
import type { LoadResult, StorageRepository } from './repository';

const STORAGE_KEY = 'groupbuy:groups:v1';
// 偵測到半壞資料時，把原始內容備份到這個 key，方便事後檢視。
const CORRUPT_BACKUP_KEY = 'groupbuy:groups:corrupt-backup';

/** 可辨識的儲存錯誤：quota 滿、無痕模式停用 storage 等都會丟這個。 */
export class StorageError extends Error {
  // 保留原始錯誤，方便除錯（不依賴 ES2022 的 Error cause）。
  readonly cause?: unknown;
  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = 'StorageError';
    this.cause = cause;
  }
}

// ---- runtime validators：逐層驗證讀回來的資料結構與型別 ----

function isNonEmptyString(v: unknown): v is string {
  return typeof v === 'string' && v.length > 0;
}

function isFiniteNonNegInt(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v) && Number.isInteger(v) && v >= 0;
}

function isValidProduct(v: unknown): v is Product {
  if (typeof v !== 'object' || v === null) return false;
  const p = v as Record<string, unknown>;
  if (!isNonEmptyString(p.id) || typeof p.name !== 'string' || !isFiniteNonNegInt(p.price))
    return false;
  // image 為可選字串（data URL）；存在但非字串視為毀損。
  if (p.image !== undefined && typeof p.image !== 'string') return false;
  return true;
}

function isValidOrderItem(v: unknown): v is OrderItem {
  if (typeof v !== 'object' || v === null) return false;
  const i = v as Record<string, unknown>;
  // 只驗結構：productId 為非空字串、qty 為非負整數。
  // 刻意「不」要求 productId 指向現存商品——與 calc.ts 的容錯設計對齊
  //（找不到商品的品項在統計時一律略過）。未來若加入刪商品功能，殘留的舊品項
  // 不該讓整團被判毀損而整筆丟棄。
  return isNonEmptyString(i.productId) && isFiniteNonNegInt(i.qty);
}

function isValidOrder(v: unknown): v is Order {
  if (typeof v !== 'object' || v === null) return false;
  const o = v as Record<string, unknown>;
  if (!isNonEmptyString(o.id)) return false;
  if (typeof o.buyerName !== 'string') return false;
  if (typeof o.createdAt !== 'number' || !Number.isFinite(o.createdAt)) return false;
  // paid 為可選 boolean（舊資料無此欄位 → undefined，合法）；存在但型別錯視為毀損。
  if (o.paid !== undefined && typeof o.paid !== 'boolean') return false;
  if (!Array.isArray(o.items)) return false;
  return o.items.every((item) => isValidOrderItem(item));
}

function isValidGroup(v: unknown): v is Group {
  if (typeof v !== 'object' || v === null) return false;
  const g = v as Record<string, unknown>;
  if (!isNonEmptyString(g.id)) return false;
  if (typeof g.name !== 'string') return false;
  if (typeof g.createdAt !== 'number' || !Number.isFinite(g.createdAt)) return false;
  if (typeof g.closed !== 'boolean') return false;
  if (g.note !== undefined && typeof g.note !== 'string') return false;
  // deadlineAt 為可選時間戳（舊資料無此欄位 → undefined，合法）；存在但非有限數視為毀損。
  if (g.deadlineAt !== undefined && (typeof g.deadlineAt !== 'number' || !Number.isFinite(g.deadlineAt)))
    return false;
  if (!Array.isArray(g.products) || !g.products.every(isValidProduct)) return false;

  // 商品 id 必須唯一（否則品項定價會撞單）。
  const productIds = new Set((g.products as Product[]).map((p) => p.id));
  if (productIds.size !== g.products.length) return false;

  if (!Array.isArray(g.orders)) return false;
  return (g.orders as unknown[]).every((o) => isValidOrder(o));
}

export class LocalStorageRepository implements StorageRepository {
  async loadGroups(): Promise<LoadResult> {
    let raw: string | null;
    try {
      raw = localStorage.getItem(STORAGE_KEY);
    } catch (err) {
      // storage 被停用（例如某些無痕模式）時讀取也可能丟例外。
      console.error('讀取本機資料失敗，將以空資料開始：', err);
      return { groups: [], corrupted: false };
    }

    if (!raw) return { groups: [], corrupted: false };

    let data: unknown;
    try {
      data = JSON.parse(raw);
    } catch (err) {
      // JSON 整包壞掉：備份原始字串後重置。
      console.error('本機資料無法解析（JSON 毀損），已備份並重置：', err);
      this.backupCorrupt(raw);
      return { groups: [], corrupted: true };
    }

    if (!Array.isArray(data)) {
      console.error('本機資料格式非陣列，已備份並重置。');
      this.backupCorrupt(raw);
      return { groups: [], corrupted: true };
    }

    // 逐筆驗證：合法的留下，壞的丟棄（粗粒度：一筆壞就丟整團）。
    const valid: Group[] = [];
    let droppedAny = false;
    for (const item of data) {
      if (isValidGroup(item)) {
        valid.push(item);
      } else {
        droppedAny = true;
        const meta = item as Record<string, unknown> | null;
        const id = meta && typeof meta.id === 'string' ? meta.id : '(無法辨識 id)';
        const name = meta && typeof meta.name === 'string' ? meta.name : '(無法辨識 name)';
        console.error(`丟棄毀損 group：id=${id}、name=${name}`);
      }
    }

    if (droppedAny) {
      console.error('部分本機 group 資料毀損，已丟棄壞資料並備份原始內容。');
      this.backupCorrupt(raw);
    }

    return { groups: valid, corrupted: droppedAny };
  }

  async saveGroups(groups: Group[]): Promise<void> {
    let serialized: string;
    try {
      serialized = JSON.stringify(groups);
    } catch (err) {
      throw new StorageError('資料序列化失敗，無法儲存。', err);
    }

    try {
      localStorage.setItem(STORAGE_KEY, serialized);
    } catch (err) {
      // quota exceeded、Safari 無痕模式、storage 被停用都會走到這。
      throw new StorageError('本機儲存失敗（可能空間已滿或瀏覽器停用儲存）。', err);
    }
  }

  /** 備份原始毀損資料到 quarantine key；備份失敗不影響主流程。 */
  private backupCorrupt(raw: string): void {
    try {
      localStorage.setItem(CORRUPT_BACKUP_KEY, raw);
    } catch {
      // 連備份都寫不進去（例如 quota 滿）就算了，不要再丟例外。
    }
  }
}
