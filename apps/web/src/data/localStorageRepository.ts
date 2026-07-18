// 第一版資料實作：存在瀏覽器 localStorage，重整不遺失。
// 介面符合 StorageRepository，未來可替換成雲端 / IndexedDB 版本。

import type {
  GlobalSettings,
  Player,
  RosterPlayer,
  Round,
  Session,
  SessionRules,
  Settings,
  Substitution,
} from '../types';
import {
  DEFAULT_GLOBAL_SETTINGS,
  DEFAULT_NEW_SESSION_RULES,
  DEFAULT_SESSION_RULES,
  MAX_KNOWN_PLAYERS,
  MAX_NOTE_LENGTH,
} from '../types';
import type { LoadResult, StorageRepository } from './repository';

// 沿用 v1 的 sessions key（v2 向下相容讀同一份），新增獨立的全域設定 key。
const STORAGE_KEY = 'mahjong-score:sessions:v1';
const GLOBAL_SETTINGS_KEY = 'mahjong-score:global-settings:v1';
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
  if (!isNonEmptyString(p.id) || typeof p.name !== 'string') return false;
  // v2.1：rosterId 為可選字串（舊資料無此欄位 → undefined，合法）。
  // 型別錯（存在但非字串）視為毀損，避免污染跨場聚合。
  if (p.rosterId !== undefined && typeof p.rosterId !== 'string') return false;
  return true;
}

/**
 * v2.1：把任意值正規化成合法的 SessionRules。
 * 任一欄位缺失/型別錯，就回退到「migration 預設」（fallback，預設全 0），
 * 確保舊場次（無 rules）計分行為不變。
 */
function normalizeSessionRules(v: unknown, fallback: SessionRules): SessionRules {
  if (typeof v !== 'object' || v === null) return { ...fallback };
  const r = v as Record<string, unknown>;
  const selfDrawBonusTai = isFiniteNonNegInt(r.selfDrawBonusTai)
    ? r.selfDrawBonusTai
    : fallback.selfDrawBonusTai;
  const selfDrawDongAmount = isFiniteNonNegInt(r.selfDrawDongAmount)
    ? r.selfDrawDongAmount
    : fallback.selfDrawDongAmount;
  // v2.2：眼牌規則。缺值/型別錯 → 回退 fallback（migration 全關 / 中性值，歷史分數不變）。
  const eyeTileEnabled =
    typeof r.eyeTileEnabled === 'boolean' ? r.eyeTileEnabled : fallback.eyeTileEnabled;
  const eyeTileTai = isFiniteNonNegInt(r.eyeTileTai) ? r.eyeTileTai : fallback.eyeTileTai;
  // v2.3：連莊規則。缺值/型別錯 → 回退 fallback（migration 全關 / 中性值，歷史分數不變）。
  const dealerEnabled =
    typeof r.dealerEnabled === 'boolean' ? r.dealerEnabled : fallback.dealerEnabled;
  const dealerBaseTai = isFiniteNonNegInt(r.dealerBaseTai)
    ? r.dealerBaseTai
    : fallback.dealerBaseTai;
  const dealerStreakTaiPerStreak = isFiniteNonNegInt(r.dealerStreakTaiPerStreak)
    ? r.dealerStreakTaiPerStreak
    : fallback.dealerStreakTaiPerStreak;
  const dealerTaiScope =
    r.dealerTaiScope === 'table' || r.dealerTaiScope === 'dealer'
      ? r.dealerTaiScope
      : fallback.dealerTaiScope;
  return {
    selfDrawBonusTai,
    selfDrawDongAmount,
    eyeTileEnabled,
    eyeTileTai,
    dealerEnabled,
    dealerBaseTai,
    dealerStreakTaiPerStreak,
    dealerTaiScope,
  };
}

/**
 * v2.4（批次 3）：把任意值正規化成乾淨的 substitutions 陣列（中途換人時間軸）。
 * 非陣列 → 空陣列；逐筆過濾——seatId 必須指向存在座位、fromRoundIndex 非負整數、name 非空。
 * 壞的項目濾掉而非整場丟棄（換人是純顯示 / 歸戶層，毀損不該連累金流正確的歷史場次）。
 */
function normalizeSubstitutions(v: unknown, playerIds: Set<string>): Substitution[] {
  if (!Array.isArray(v)) return [];
  const out: Substitution[] = [];
  for (const item of v) {
    if (typeof item !== 'object' || item === null) continue;
    const s = item as Record<string, unknown>;
    if (!isNonEmptyString(s.seatId) || !playerIds.has(s.seatId)) continue;
    if (!isFiniteNonNegInt(s.fromRoundIndex)) continue;
    if (typeof s.name !== 'string' || s.name.trim() === '') continue;
    if (s.rosterId !== undefined && typeof s.rosterId !== 'string') continue;
    out.push({
      seatId: s.seatId,
      fromRoundIndex: s.fromRoundIndex,
      name: s.name,
      rosterId: typeof s.rosterId === 'string' ? s.rosterId : undefined,
    });
  }
  return out;
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

  // v2：note 為可選字串（舊資料無此欄位 → undefined，合法）。
  // 若存在但型別錯（非字串）或超長，視為毀損，避免污染明細顯示。
  if (r.note !== undefined) {
    if (typeof r.note !== 'string' || r.note.length > MAX_NOTE_LENGTH) return false;
  }

  // v2.2：eyeTile 為可選 boolean（舊資料無此欄位 → undefined，合法）。
  // 型別錯（存在但非 boolean）視為毀損，避免污染計分。
  if (r.eyeTile !== undefined && typeof r.eyeTile !== 'boolean') return false;

  // v2.3：drawn 為可選 boolean（舊資料無此欄位 → undefined，合法）。
  if (r.drawn !== undefined && typeof r.drawn !== 'boolean') return false;

  // v2.3：流局（drawn=true）——winnerId 必須為空字串、loserId 必須為 null（採方案 A 判別式）。
  // 提前 return，避免下方對 winnerId 的「非空且在玩家清單」檢查誤把流局判成毀損。
  // 批次 3 防呆補強：流局 selfDraw 必為 false（selfDraw 型別已於上方驗過為 boolean），
  // 否則計分會誤把流局當自摸算出東錢，破壞「流局全 0」不變量。
  if (r.drawn === true) {
    return r.winnerId === '' && r.loserId === null && r.selfDraw === false;
  }

  // 非流局：winnerId 必填、合法且在玩家清單內。
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

  // v2：endedAt 為可選時間戳（舊資料無此欄位 → undefined，合法）。
  if (s.endedAt !== undefined) {
    if (typeof s.endedAt !== 'number' || !Number.isFinite(s.endedAt)) return false;
  }

  // v2.3：dealerStartSeat 為可選字串（舊資料無此欄位 → undefined，合法）。
  // 只驗型別；若指向不存在的座位，deriveTableState 會自行判為未啟用，不必因此丟棄整場。
  if (s.dealerStartSeat !== undefined && typeof s.dealerStartSeat !== 'string') return false;

  // v2.1：rules 不在此判毀損——舊場次本就沒有 rules，會在 migration 階段補入
  //（DEFAULT_SESSION_RULES，全 0，行為不變）。型別錯也只是被正規化覆蓋，不丟整場資料。

  // MVP 規則：固定 4 人，且 player id 必須全部唯一。
  // 若殘留非 4 人或重複 id 的 session，自摸分支的 (players.length - 1)
  // 會算出錯誤金額、重複 id 也會讓 RoundDelta 互相覆蓋，因此一律判為毀損。
  if (s.players.length !== 4) return false;
  const playerIds = new Set((s.players as Player[]).map((p) => p.id));
  if (playerIds.size !== 4) return false;

  return (s.rounds as unknown[]).every((r) => isValidRound(r, playerIds));
}

/** v2：驗證全域設定結構；任何欄位不合法即回傳 null（呼叫端退回預設值）。 */
function parseGlobalSettings(v: unknown): GlobalSettings | null {
  if (typeof v !== 'object' || v === null) return null;
  const g = v as Record<string, unknown>;
  if (!isFiniteNonNegInt(g.defaultBase)) return null;
  if (!isFiniteNonNegInt(g.defaultTai)) return null;
  if (!Array.isArray(g.knownPlayers)) return null;
  // 常用玩家：只留非空字串、去重、限制上限，毀損的項目直接濾掉而非整包丟棄。
  const seen = new Set<string>();
  const knownPlayers: string[] = [];
  for (const item of g.knownPlayers) {
    if (typeof item !== 'string') continue;
    const name = item.trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    knownPlayers.push(name);
    if (knownPlayers.length >= MAX_KNOWN_PLAYERS) break;
  }
  // v2.1：玩家名冊。逐筆驗證，壞的項目濾掉而非整包丟棄；id 去重。
  const roster: RosterPlayer[] = [];
  const seenIds = new Set<string>();
  if (Array.isArray(g.roster)) {
    for (const item of g.roster) {
      if (typeof item !== 'object' || item === null) continue;
      const rp = item as Record<string, unknown>;
      if (!isNonEmptyString(rp.id) || seenIds.has(rp.id)) continue;
      if (typeof rp.name !== 'string') continue;
      if (typeof rp.createdAt !== 'number' || !Number.isFinite(rp.createdAt)) continue;
      if (rp.avatar !== undefined && typeof rp.avatar !== 'string') continue;
      seenIds.add(rp.id);
      roster.push({
        id: rp.id,
        name: rp.name,
        avatar: typeof rp.avatar === 'string' ? rp.avatar : undefined,
        createdAt: rp.createdAt,
      });
    }
  }

  // v2.1：開桌規則預設（缺值用「新開桌預設」補：自摸加台 1、東錢 100）。
  const defaultRules = normalizeSessionRules(g.defaultRules, DEFAULT_NEW_SESSION_RULES);

  // v2.1：單場輸贏警戒線（缺值/型別錯 → 0=關閉）。
  const loseAlertThreshold = isFiniteNonNegInt(g.loseAlertThreshold)
    ? g.loseAlertThreshold
    : 0;

  return {
    defaultBase: g.defaultBase,
    defaultTai: g.defaultTai,
    knownPlayers,
    roster,
    defaultRules,
    loseAlertThreshold,
  };
}

export class LocalStorageRepository implements StorageRepository {
  async loadSessions(): Promise<LoadResult> {
    const globalSettings = this.loadGlobalSettings();

    let raw: string | null;
    try {
      raw = localStorage.getItem(STORAGE_KEY);
    } catch (err) {
      // storage 被停用（例如某些無痕模式）時讀取也可能丟例外。
      console.error('讀取本機資料失敗，將以空資料開始：', err);
      return { sessions: [], globalSettings, corrupted: false };
    }

    if (!raw) return { sessions: [], globalSettings, corrupted: false };

    let data: unknown;
    try {
      data = JSON.parse(raw);
    } catch (err) {
      // JSON 整包壞掉：備份原始字串後重置。
      console.error('本機資料無法解析（JSON 毀損），已備份並重置：', err);
      this.backupCorrupt(raw);
      return { sessions: [], globalSettings, corrupted: true };
    }

    if (!Array.isArray(data)) {
      console.error('本機資料格式非陣列，已備份並重置。');
      this.backupCorrupt(raw);
      return { sessions: [], globalSettings, corrupted: true };
    }

    // 逐筆驗證：合法的留下，壞的丟棄。
    // 注意：目前只要一筆 round 毀損，整個 session 就會被丟棄（粗粒度）。
    // 逐 round 丟棄列為 TODO（見 work/mahjong-app-架構.md）。
    const valid: Session[] = [];
    let droppedAny = false;
    for (const item of data) {
      if (isValidSession(item)) {
        // v2.1 migration：舊場次無 rules → 補 DEFAULT_SESSION_RULES（全 0，計分行為不變）。
        const raw = item as unknown as Record<string, unknown>;
        // v2.4 migration：substitutions 只在原本就有此欄位時才正規化寫回；舊場無此欄位
        // 保持不帶 key（等同空時間軸），行為零變化。
        const playerIds = new Set(item.players.map((p) => p.id));
        valid.push({
          ...item,
          rules: normalizeSessionRules(raw.rules, DEFAULT_SESSION_RULES),
          ...(raw.substitutions !== undefined
            ? { substitutions: normalizeSubstitutions(raw.substitutions, playerIds) }
            : {}),
        });
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

    return { sessions: valid, globalSettings, corrupted: droppedAny };
  }

  /**
   * v2：讀取全域設定。讀不到、JSON 壞掉或結構不合法都回傳預設值，不影響主流程。
   * 全域設定是輕量、可重建的偏好，毀損時不需通報使用者，靜默退回預設即可。
   */
  private loadGlobalSettings(): GlobalSettings {
    let raw: string | null;
    try {
      raw = localStorage.getItem(GLOBAL_SETTINGS_KEY);
    } catch {
      return { ...DEFAULT_GLOBAL_SETTINGS };
    }
    if (!raw) return { ...DEFAULT_GLOBAL_SETTINGS };
    try {
      const parsed = parseGlobalSettings(JSON.parse(raw));
      return parsed ?? { ...DEFAULT_GLOBAL_SETTINGS };
    } catch {
      return { ...DEFAULT_GLOBAL_SETTINGS };
    }
  }

  async saveGlobalSettings(settings: GlobalSettings): Promise<void> {
    let serialized: string;
    try {
      serialized = JSON.stringify(settings);
    } catch (err) {
      throw new StorageError('全域設定序列化失敗，無法儲存。', err);
    }
    try {
      localStorage.setItem(GLOBAL_SETTINGS_KEY, serialized);
    } catch (err) {
      throw new StorageError('全域設定儲存失敗（可能空間已滿或瀏覽器停用儲存）。', err);
    }
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
