// 第一版資料實作：存在瀏覽器 localStorage，重整不遺失。
// 介面符合 StorageRepository，未來可替換成雲端 / IndexedDB 版本。

import type { Player, Round, Session, Settings } from '../types';
import type { LoadResult, StorageRepository } from './repository';

const STORAGE_KEY = 'mahjong-score:sessions:v1';
// 偵測到半壞資料時，把原始內容備份到這個 key，方便事後檢視。
const CORRUPT_BACKUP_KEY = 'mahjong-sessions-corrupt-backup';

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

function isValidPlayer(v: unknown): v is Player {
  if (typeof v !== 'object' || v === null) return false;
  const p = v as Record<string, unknown>;
  return isNonEmptyString(p.id) && typeof p.name === 'string';
}

function isValidSettings(v: unknown): v is Settings {
  if (typeof v !== 'object' || v === null) return false;
  const s = v as Record<string, unknown>;
  return isFiniteNonNegInt(s.base) && isFiniteNonNegInt(s.tai);
}

function isValidRound(v: unknown, playerIds: Set<string>): v is Round {
  if (typeof v !== 'object' || v === null) return false;
  const r = v as Record<string, unknown>;
  if (!isNonEmptyString(r.id)) return false;
  if (typeof r.createdAt !== 'number' || !Number.isFinite(r.createdAt)) return false;
  if (!isFiniteNonNegInt(r.tai)) return false;
  if (typeof r.selfDraw !== 'boolean') return false;
  if (!isNonEmptyString(r.winnerId) || !playerIds.has(r.winnerId)) return false;

  if (r.selfDraw) {
    // 自摸：loserId 必須為 null
    return r.loserId === null;
  }
  // 放槍：loserId 必須是合法、存在且不等於贏家的玩家
  return (
    isNonEmptyString(r.loserId) &&
    playerIds.has(r.loserId) &&
    r.loserId !== r.winnerId
  );
}

function isValidSession(v: unknown): v is Session {
  if (typeof v !== 'object' || v === null) return false;
  const s = v as Record<string, unknown>;
  if (!isNonEmptyString(s.id)) return false;
  if (typeof s.name !== 'string') return false;
  if (typeof s.createdAt !== 'number' || !Number.isFinite(s.createdAt)) return false;
  if (!isValidSettings(s.settings)) return false;
  if (!Array.isArray(s.players) || !s.players.every(isValidPlayer)) return false;
  if (!Array.isArray(s.rounds)) return false;

  // MVP 規則：固定 4 人，且 player id 必須全部唯一。
  // 若殘留非 4 人或重複 id 的 session，自摸分支的 (players.length - 1)
  // 會算出錯誤金額、重複 id 也會讓 RoundDelta 互相覆蓋，因此一律判為毀損。
  if (s.players.length !== 4) return false;
  const playerIds = new Set((s.players as Player[]).map((p) => p.id));
  if (playerIds.size !== 4) return false;

  return (s.rounds as unknown[]).every((r) => isValidRound(r, playerIds));
}

export class LocalStorageRepository implements StorageRepository {
  async loadSessions(): Promise<LoadResult> {
    let raw: string | null;
    try {
      raw = localStorage.getItem(STORAGE_KEY);
    } catch (err) {
      // storage 被停用（例如某些無痕模式）時讀取也可能丟例外。
      console.error('讀取本機資料失敗，將以空資料開始：', err);
      return { sessions: [], corrupted: false };
    }

    if (!raw) return { sessions: [], corrupted: false };

    let data: unknown;
    try {
      data = JSON.parse(raw);
    } catch (err) {
      // JSON 整包壞掉：備份原始字串後重置。
      console.error('本機資料無法解析（JSON 毀損），已備份並重置：', err);
      this.backupCorrupt(raw);
      return { sessions: [], corrupted: true };
    }

    if (!Array.isArray(data)) {
      console.error('本機資料格式非陣列，已備份並重置。');
      this.backupCorrupt(raw);
      return { sessions: [], corrupted: true };
    }

    // 逐筆驗證：合法的留下，壞的丟棄。
    // 注意：目前只要一筆 round 毀損，整個 session 就會被丟棄（粗粒度）。
    // 逐 round 丟棄列為 TODO（見 work/mahjong-app-架構.md）。
    const valid: Session[] = [];
    let droppedAny = false;
    for (const item of data) {
      if (isValidSession(item)) {
        valid.push(item);
      } else {
        droppedAny = true;
        // 明確記下被丟棄的 session id/name，方便除錯（取不到就標示無法辨識）。
        const meta = item as Record<string, unknown> | null;
        const id = meta && typeof meta.id === 'string' ? meta.id : '(無法辨識 id)';
        const name = meta && typeof meta.name === 'string' ? meta.name : '(無法辨識 name)';
        console.error(`丟棄毀損 session：id=${id}、name=${name}`);
      }
    }

    if (droppedAny) {
      console.error('部分本機 session 資料毀損，已丟棄壞資料並備份原始內容。');
      this.backupCorrupt(raw);
    }

    return { sessions: valid, corrupted: droppedAny };
  }

  async saveSessions(sessions: Session[]): Promise<void> {
    let serialized: string;
    try {
      serialized = JSON.stringify(sessions);
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
