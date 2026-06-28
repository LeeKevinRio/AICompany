// 資料層抽象。
// UI 與 hook 只認這個 interface，不直接碰 localStorage。
// 未來換成 IndexedDB 或雲端 API，只要新增一個 implements 即可，UI 不動。

import type { Session } from '../types';

/** 讀取結果：除了 sessions，另外回報是否偵測到毀損資料（供 UI 提示）。 */
export interface LoadResult {
  sessions: Session[];
  /** true 表示讀到的資料有毀損，已丟棄壞資料（可能已重置）。 */
  corrupted: boolean;
}

export interface StorageRepository {
  /** 讀取全部場次（含毀損偵測結果） */
  loadSessions(): Promise<LoadResult>;
  /** 寫入全部場次（整包覆蓋，MVP 資料量小可接受）。失敗時 throw StorageError。 */
  saveSessions(sessions: Session[]): Promise<void>;
}
