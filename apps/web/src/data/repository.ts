// 資料層抽象。
// UI 與 hook 只認這個 interface，不直接碰 localStorage。
// 未來換成 IndexedDB 或雲端 API，只要新增一個 implements 即可，UI 不動。

import type { GlobalSettings, Session } from '../types';

/** 匯入備份（整份覆蓋）要寫入的內容：全域設定 + 全部場次。 */
export interface ImportPayload {
  globalSettings: GlobalSettings;
  sessions: Session[];
}

/** 讀取結果：除了 sessions，另外回報是否偵測到毀損資料（供 UI 提示）。 */
export interface LoadResult {
  sessions: Session[];
  /** v2：全域設定（讀不到或毀損時回傳預設值）。 */
  globalSettings: GlobalSettings;
  /** true 表示讀到的資料有毀損，已丟棄壞資料（可能已重置）。 */
  corrupted: boolean;
}

export interface StorageRepository {
  /** 讀取全部場次與全域設定（含毀損偵測結果） */
  loadSessions(): Promise<LoadResult>;
  /** 寫入全部場次（整包覆蓋，MVP 資料量小可接受）。失敗時 throw StorageError。 */
  saveSessions(sessions: Session[]): Promise<void>;
  /** v2：寫入全域設定。失敗時 throw StorageError。 */
  saveGlobalSettings(settings: GlobalSettings): Promise<void>;
  /**
   * 匯入備份（整份覆蓋）前，先把現有資料原封不動備份到隔離區，讓誤匯入救得回來。
   * 回傳是否成功備份：storage 停用 / 寫入失敗（quota 滿）時回 false，
   * 供 UI 提前警示「無法自動備份」而非照樣承諾（現有資料為空時視為成功——本來就沒東西要保留）。
   */
  backupBeforeImport(): boolean;

  /**
   * 匯入備份（整份覆蓋）：把全域設定與全部場次視為單一原子操作寫入。
   * 兩寫其一失敗（quota 滿等）會 throw StorageError；若 global 已寫成功但 sessions 失敗，
   * 會先把 global 回貼匯入前的原始內容（rollback），確保不留下「新設定＋舊牌局」的混合狀態。
   * 前置條件：呼叫前必須先呼叫 backupBeforeImport()，rollback 以其保命備份為依據。
   */
  importBackup(payload: ImportPayload): Promise<void>;
}
