// localStorageRepository validator 的向後相容測試。
//
// 重點覆蓋：v1 舊格式 session（缺 note / 缺 endedAt）能正確通過、不被誤判毀損；
// 以及 v2 新欄位型別錯（note 非字串、endedAt 非數字）會被正確判為毀損。
//
// validator（isValidSession 等）未對外 export，這裡透過 LocalStorageRepository.loadSessions()
// 的公開行為驗證——以 corrupted 旗標與留下/丟棄的 sessions 作為斷言依據。

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  LocalStorageRepository,
  PRE_IMPORT_GLOBAL_BACKUP_KEY,
  PRE_IMPORT_SESSIONS_BACKUP_KEY,
} from './localStorageRepository';
import type { Player, Round, Session } from '../types';
import { DEFAULT_GLOBAL_SETTINGS } from '../types';

const STORAGE_KEY = 'mahjong-score:sessions:v1';
const GLOBAL_SETTINGS_KEY = 'mahjong-score:global-settings:v1';
const CORRUPT_BACKUP_KEY = 'mahjong-sessions-corrupt-backup';
const CORRUPT_GLOBAL_BACKUP_KEY = 'mahjong-global-settings-corrupt-backup';

// 簡易記憶體版 localStorage（測試環境為 node，無瀏覽器 storage）。
class MemoryStorage {
  private map = new Map<string, string>();
  getItem(k: string): string | null {
    return this.map.has(k) ? this.map.get(k)! : null;
  }
  setItem(k: string, v: string): void {
    this.map.set(k, v);
  }
  removeItem(k: string): void {
    this.map.delete(k);
  }
  clear(): void {
    this.map.clear();
  }
}

let store: MemoryStorage;
beforeEach(() => {
  store = new MemoryStorage();
  (globalThis as { localStorage?: unknown }).localStorage = store;
});

afterEach(() => {
  delete (globalThis as { localStorage?: unknown }).localStorage;
});

const players: Player[] = [
  { id: 'p1', name: 'A' },
  { id: 'p2', name: 'B' },
  { id: 'p3', name: 'C' },
  { id: 'p4', name: 'D' },
];

function makeRound(partial: Partial<Round> = {}): Round {
  return {
    id: 'r1',
    winnerId: 'p1',
    tai: 0,
    selfDraw: false,
    loserId: 'p2',
    createdAt: 1000,
    ...partial,
  };
}

// 注意：刻意回傳 Record，方便在測試裡塞入「不合法型別」的欄位（繞過 TS 型別檢查）。
// base 刻意省略 rules，模擬 v1 舊資料（無 rules 欄位），驗證 migration 補值不誤判毀損。
function makeSession(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const base: Omit<Session, 'rules'> = {
    id: 's1',
    name: '週五場',
    players,
    settings: { base: 100, tai: 50 },
    rounds: [makeRound()],
    createdAt: 2000,
  };
  return { ...base, ...overrides };
}

function seed(data: unknown): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

describe('LocalStorageRepository validator 向後相容', () => {
  it('舊格式 session（round 缺 note）通過、不被判毀損', async () => {
    // 直接用 makeRound 不帶 note，模擬 v1 沒有 note 欄位的資料。
    const session = makeSession({ rounds: [makeRound()] });
    expect('note' in (session.rounds as Round[])[0]).toBe(false);
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
    expect(res.sessions[0].id).toBe('s1');
  });

  it('舊格式 session（缺 endedAt）通過、不被判毀損', async () => {
    const session = makeSession();
    expect('endedAt' in session).toBe(false);
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
    expect(res.sessions[0].endedAt).toBeUndefined();
  });

  it('同時缺 note 與 endedAt 的純 v1 資料完整通過', async () => {
    const session = makeSession({
      rounds: [makeRound(), makeRound({ id: 'r2', selfDraw: true, loserId: null })],
    });
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
    expect(res.sessions[0].rounds).toHaveLength(2);
  });

  it('note 為非字串型別 → 該 session 判毀損並丟棄', async () => {
    const session = makeSession({ rounds: [makeRound({ note: 123 as unknown as string })] });
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(res.sessions).toHaveLength(0);
  });

  it('endedAt 為非數字型別 → 該 session 判毀損並丟棄', async () => {
    const session = makeSession({ endedAt: '2026-01-01' });
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(res.sessions).toHaveLength(0);
  });

  it('壞資料與好資料混雜：只丟壞的、保留好的，並回報 corrupted', async () => {
    const good = makeSession({ id: 'good' });
    // 用字串 endedAt 當真型別錯——注意 NaN 經 JSON.stringify 會變 null（合法未結算），
    // 不能拿來當毀損標記，否則測不到「丟壞的」這條路徑。
    const bad = makeSession({ id: 'bad', endedAt: '壞掉' });
    seed([good, bad]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(res.sessions.map((s) => s.id)).toEqual(['good']);
  });
});

describe('LocalStorageRepository — v2.1 rules migration', () => {
  it('v1 舊場次（無 rules）：不判毀損，補入全 0 的 DEFAULT_SESSION_RULES', async () => {
    const session = makeSession();
    expect('rules' in session).toBe(false);
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
    // 關鍵：補 0 而非 1，否則歷史自摸分數會被改變（眼牌亦補關 / 0）。
    expect(res.sessions[0].rules).toEqual({
      selfDrawBonusTai: 0,
      selfDrawDongAmount: 0,
      eyeTileEnabled: false,
      eyeTileTai: 0,
      dealerEnabled: false,
      dealerBaseTai: 0,
      dealerStreakTaiPerStreak: 0,
      dealerTaiScope: 'dealer',
    });
  });

  it('已存在合法 rules（v2.1 舊格式，無眼牌欄位）：既有欄位保留、眼牌補中性值', async () => {
    const session = makeSession({ rules: { selfDrawBonusTai: 1, selfDrawDongAmount: 100 } });
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    // 舊 rules 缺眼牌欄位 → 補 fallback（關 / 0），既有自摸/東錢數值不動。
    expect(res.sessions[0].rules).toEqual({
      selfDrawBonusTai: 1,
      selfDrawDongAmount: 100,
      eyeTileEnabled: false,
      eyeTileTai: 0,
      dealerEnabled: false,
      dealerBaseTai: 0,
      dealerStreakTaiPerStreak: 0,
      dealerTaiScope: 'dealer',
    });
  });

  it('v2.2 眼牌 rules 完整保留；eyeTile round flag 合法通過', async () => {
    const session = makeSession({
      rules: {
        selfDrawBonusTai: 1,
        selfDrawDongAmount: 0,
        eyeTileEnabled: true,
        eyeTileTai: 2,
      },
      rounds: [makeRound({ eyeTile: true })],
    });
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions[0].rules).toEqual({
      selfDrawBonusTai: 1,
      selfDrawDongAmount: 0,
      eyeTileEnabled: true,
      eyeTileTai: 2,
      dealerEnabled: false,
      dealerBaseTai: 0,
      dealerStreakTaiPerStreak: 0,
      dealerTaiScope: 'dealer',
    });
    expect(res.sessions[0].rounds[0].eyeTile).toBe(true);
  });

  it('eyeTile 為非 boolean 型別 → 該 session 判毀損並丟棄', async () => {
    const session = makeSession({
      rounds: [makeRound({ eyeTile: 'yes' as unknown as boolean })],
    });
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(res.sessions).toHaveLength(0);
  });

  it('rules 型別毀損：不丟整場，正規化回補 0（行為不變）', async () => {
    const session = makeSession({ rules: { selfDrawBonusTai: 'x', selfDrawDongAmount: -5 } });
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
    expect(res.sessions[0].rules).toEqual({
      selfDrawBonusTai: 0,
      selfDrawDongAmount: 0,
      eyeTileEnabled: false,
      eyeTileTai: 0,
      dealerEnabled: false,
      dealerBaseTai: 0,
      dealerStreakTaiPerStreak: 0,
      dealerTaiScope: 'dealer',
    });
  });

  it('Player 帶 rosterId：合法字串通過、非字串判毀損', async () => {
    const ok = makeSession({
      id: 'ok',
      players: players.map((p, i) => (i === 0 ? { ...p, rosterId: 'uuid-1' } : p)),
    });
    seed([ok]);
    let res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions[0].players[0].rosterId).toBe('uuid-1');

    const bad = makeSession({
      id: 'bad',
      players: players.map((p, i) =>
        i === 0 ? { ...p, rosterId: 123 as unknown as string } : p,
      ),
    });
    seed([bad]);
    res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(res.sessions).toHaveLength(0);
  });
});

describe('LocalStorageRepository — 流局 selfDraw 防呆（批次 3）', () => {
  it('流局 selfDraw=true → 該 session 判毀損並丟棄', async () => {
    const session = makeSession({
      rounds: [makeRound({ winnerId: '', loserId: null, selfDraw: true, drawn: true })],
    });
    seed([session]);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(res.sessions).toHaveLength(0);
  });

  it('合法流局（selfDraw=false）通過', async () => {
    const session = makeSession({
      rounds: [makeRound({ winnerId: '', loserId: null, selfDraw: false, drawn: true })],
    });
    seed([session]);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
  });
});

describe('LocalStorageRepository — substitutions migration（批次 3）', () => {
  it('舊場無 substitutions 欄位 → 通過，載回後不帶 substitutions key（行為零變化）', async () => {
    const session = makeSession();
    expect('substitutions' in session).toBe(false);
    seed([session]);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect('substitutions' in res.sessions[0]).toBe(false);
  });

  it('合法 substitutions 保留；壞項目濾掉、不丟整場（換人是純顯示 / 歸戶層）', async () => {
    const session = makeSession({
      substitutions: [
        { seatId: 'p2', fromRoundIndex: 1, name: '阿明', rosterId: 'ros-9' }, // 合法
        { seatId: 'pX', fromRoundIndex: 1, name: '座位不存在' }, // 濾掉
        { seatId: 'p3', fromRoundIndex: -1, name: 'index 負' }, // 濾掉
        { seatId: 'p3', fromRoundIndex: 2, name: '  ' }, // 空名濾掉
        { seatId: 'p4', fromRoundIndex: 2, name: 'ok', rosterId: 123 }, // rosterId 型別錯 → 濾掉
      ],
    });
    seed([session]);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
    expect(res.sessions[0].substitutions).toEqual([
      { seatId: 'p2', fromRoundIndex: 1, name: '阿明', rosterId: 'ros-9' },
    ]);
  });

  it('substitutions 非陣列 → 正規化為空陣列（不丟整場）', async () => {
    const session = makeSession({ substitutions: 'oops' });
    seed([session]);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions[0].substitutions).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// hotfix：舊格式「無值＝null」誤殺回歸。
//
// 根因：多個可選欄位的驗證用 `x !== undefined` 當守門，只放行 undefined。舊格式常把
// 「無值」序列化成 null（例如未結算的 endedAt: null），null 會掉進型別檢查
// （typeof null === 'object'）被誤判毀損、整場丟棄。修法：改用 `x != null` 同時放行
// undefined 與 null，只有「存在且型別錯」才判毀損。以下矩陣逐一守住每個可選欄位。
// ---------------------------------------------------------------------------
describe('LocalStorageRepository — null＝無值 向後相容（hotfix 回歸）', () => {
  it('【重現】CEO 實測的舊格式 session（endedAt: null + 部分 rules）完整載入、不丟', async () => {
    // 這份 JSON 與 hotfix 工單附的重現資料一字不差。
    seed([
      {
        id: 's_legacy_1',
        name: '老牌局',
        createdAt: 1751000000000,
        endedAt: null,
        settings: { base: 100, tai: 50 },
        rules: { selfDrawBonusTai: 1, selfDrawDongAmount: 100 },
        players: [
          { id: 'p1', name: '老甲' },
          { id: 'p2', name: '老乙' },
          { id: 'p3', name: '老丙' },
          { id: 'p4', name: '老丁' },
        ],
        rounds: [
          {
            id: 'r1',
            winnerId: 'p1',
            loserId: 'p2',
            tai: 3,
            selfDraw: false,
            createdAt: 1751000001000,
          },
          {
            id: 'r2',
            winnerId: 'p3',
            loserId: null,
            tai: 2,
            selfDraw: true,
            createdAt: 1751000002000,
            note: '舊備註',
          },
        ],
      },
    ]);

    const res = await new LocalStorageRepository().loadSessions();
    // 關鍵：完全不判毀損、整場保留、兩局都在。
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
    expect(res.sessions[0].id).toBe('s_legacy_1');
    expect(res.sessions[0].rounds).toHaveLength(2);
    // 未結算：endedAt 為 falsy（null 與 undefined 下游行為一致）。
    expect(res.sessions[0].endedAt ?? undefined).toBeUndefined();
    // 缺欄位的舊 rules 由 normalize 補中性值，既有數值不動。
    expect(res.sessions[0].rules).toEqual({
      selfDrawBonusTai: 1,
      selfDrawDongAmount: 100,
      eyeTileEnabled: false,
      eyeTileTai: 0,
      dealerEnabled: false,
      dealerBaseTai: 0,
      dealerStreakTaiPerStreak: 0,
      dealerTaiScope: 'dealer',
    });
    // 沒有壞資料 → 不應該寫備份。
    expect(store.getItem(CORRUPT_BACKUP_KEY)).toBeNull();
  });

  it('endedAt: null → 視為未結算、不丟（先前 !== undefined 會誤殺）', async () => {
    const session = makeSession({ endedAt: null });
    seed([session]);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
    expect(res.sessions[0].endedAt ?? undefined).toBeUndefined();
  });

  it('round note/eyeTile/drawn 為 null → 視為無值、不丟', async () => {
    const session = makeSession({
      rounds: [
        makeRound({
          note: null as unknown as string,
          eyeTile: null as unknown as boolean,
          drawn: null as unknown as boolean,
        }),
      ],
    });
    seed([session]);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
  });

  it('Player rosterId: null → 視為無掛勾、不丟', async () => {
    const session = makeSession({
      players: players.map((p, i) =>
        i === 0 ? { ...p, rosterId: null as unknown as string } : p,
      ),
    });
    seed([session]);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
  });

  it('dealerStartSeat: null → 視為未指定首莊、不丟', async () => {
    const session = makeSession({ dealerStartSeat: null });
    seed([session]);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
  });

  it('substitution rosterId: null → 保留該筆、正規化成 undefined（不濾掉）', async () => {
    const session = makeSession({
      substitutions: [
        { seatId: 'p2', fromRoundIndex: 1, name: '阿明', rosterId: null },
      ],
    });
    seed([session]);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions[0].substitutions).toEqual([
      { seatId: 'p2', fromRoundIndex: 1, name: '阿明', rosterId: undefined },
    ]);
  });

  it('真型別錯仍判毀損：null 寬容不會鬆綁對非 null 髒值的守門', async () => {
    // endedAt 是字串、eyeTile 是字串——都不是 null，仍應被抓成毀損。
    seed([makeSession({ id: 'a', endedAt: '2026-01-01' })]);
    let res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(res.sessions).toHaveLength(0);

    seed([makeSession({ id: 'b', rounds: [makeRound({ eyeTile: 'yes' as unknown as boolean })] })]);
    res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(res.sessions).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// 歷代格式矩陣：純 v1 / v2（結算）/ v2.2（眼牌後）/ v2.3（連莊後）/ v2.4（換人後）
// 混雜一批一起載入，全部不誤殺、無備份。守住「遷移不回歸」這條資料安全線。
// ---------------------------------------------------------------------------
describe('LocalStorageRepository — 歷代格式矩陣一起載入', () => {
  it('五種歷代格式混雜 → 全數保留、不判毀損、不寫備份', async () => {
    const v1 = makeSession({ id: 'v1' }); // 純 v1：無 rules / endedAt / note
    const v2Ended = makeSession({ id: 'v2', endedAt: null }); // v2 舊格式未結算＝null
    const v22Eye = makeSession({
      id: 'v22',
      rules: { selfDrawBonusTai: 1, selfDrawDongAmount: 0, eyeTileEnabled: true, eyeTileTai: 1 },
      rounds: [makeRound({ eyeTile: true })],
    });
    const v23Dealer = makeSession({
      id: 'v23',
      dealerStartSeat: 'p1',
      rounds: [makeRound(), makeRound({ id: 'r2', winnerId: '', loserId: null, drawn: true })],
    });
    const v24Sub = makeSession({
      id: 'v24',
      substitutions: [{ seatId: 'p2', fromRoundIndex: 1, name: '換人' }],
    });
    seed([v1, v2Ended, v22Eye, v23Dealer, v24Sub]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions.map((s) => s.id)).toEqual(['v1', 'v2', 'v22', 'v23', 'v24']);
    // 全部合法 → 不應寫任何備份。
    expect(store.getItem(CORRUPT_BACKUP_KEY)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 備份保證：丟棄任何資料前必須先備份（session 與 global settings 兩條路徑）。
// ---------------------------------------------------------------------------
describe('LocalStorageRepository — 毀損必備份（資料安全）', () => {
  it('真毀損 session 被丟棄時，原始內容寫入 session 備份 key', async () => {
    const raw = [makeSession({ id: 'bad', endedAt: '壞掉' })];
    seed(raw);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(store.getItem(CORRUPT_BACKUP_KEY)).toBe(JSON.stringify(raw));
  });

  it('sessions JSON 整包壞掉 → 備份原始字串並重置', async () => {
    localStorage.setItem(STORAGE_KEY, '{壞掉的 json');
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(store.getItem(CORRUPT_BACKUP_KEY)).toBe('{壞掉的 json');
  });

  it('全域設定結構不合法 → 退回預設前先備份（不靜默丟失名冊）', async () => {
    // defaultBase 型別錯 → parseGlobalSettings 回 null；roster 不該無聲蒸發。
    const rawGlobal = JSON.stringify({
      defaultBase: 'x',
      defaultTai: 50,
      knownPlayers: [],
      roster: [{ id: 'ros-1', name: '阿明', createdAt: 1 }],
    });
    localStorage.setItem(GLOBAL_SETTINGS_KEY, rawGlobal);
    const res = await new LocalStorageRepository().loadSessions();
    // 全域設定退回預設，但原始內容已備份可救回。
    expect(res.globalSettings.roster).toEqual([]);
    expect(store.getItem(CORRUPT_GLOBAL_BACKUP_KEY)).toBe(rawGlobal);
  });

  it('RosterPlayer avatar: null → 保留該筆、正規化成 undefined（不靜默丟棄）', async () => {
    const rawGlobal = JSON.stringify({
      defaultBase: 100,
      defaultTai: 50,
      knownPlayers: [],
      roster: [{ id: 'ros-1', name: '阿明', avatar: null, createdAt: 1 }],
    });
    localStorage.setItem(GLOBAL_SETTINGS_KEY, rawGlobal);
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.globalSettings.roster).toHaveLength(1);
    expect(res.globalSettings.roster[0]).toEqual({
      id: 'ros-1',
      name: '阿明',
      avatar: undefined,
      createdAt: 1,
    });
  });

  it('全域設定 JSON 整包壞掉 → 備份並退回預設', async () => {
    localStorage.setItem(GLOBAL_SETTINGS_KEY, '{壞掉');
    const res = await new LocalStorageRepository().loadSessions();
    expect(res.globalSettings).toEqual(DEFAULT_GLOBAL_SETTINGS);
    expect(store.getItem(CORRUPT_GLOBAL_BACKUP_KEY)).toBe('{壞掉');
  });
});

describe('LocalStorageRepository — 匯入前保命備份', () => {
  it('backupBeforeImport 把現有 sessions 與全域設定原樣隔離到 pre-import key', () => {
    const rawSessions = JSON.stringify([makeSession()]);
    const rawGlobal = JSON.stringify(DEFAULT_GLOBAL_SETTINGS);
    localStorage.setItem(STORAGE_KEY, rawSessions);
    localStorage.setItem(GLOBAL_SETTINGS_KEY, rawGlobal);

    new LocalStorageRepository().backupBeforeImport();

    // 原樣（未經序列化往返）備份，誤匯入後可整份貼回救援。
    expect(store.getItem(PRE_IMPORT_SESSIONS_BACKUP_KEY)).toBe(rawSessions);
    expect(store.getItem(PRE_IMPORT_GLOBAL_BACKUP_KEY)).toBe(rawGlobal);
    // 原始資料不動（備份只是複製，不搬走）。
    expect(store.getItem(STORAGE_KEY)).toBe(rawSessions);
  });

  it('現有資料為空（全新裝置）→ 不寫入空備份，也不丟例外', () => {
    expect(() => new LocalStorageRepository().backupBeforeImport()).not.toThrow();
    expect(store.getItem(PRE_IMPORT_SESSIONS_BACKUP_KEY)).toBeNull();
    expect(store.getItem(PRE_IMPORT_GLOBAL_BACKUP_KEY)).toBeNull();
  });

  it('成功備份 → 回 true', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([makeSession()]));
    localStorage.setItem(GLOBAL_SETTINGS_KEY, JSON.stringify(DEFAULT_GLOBAL_SETTINGS));
    expect(new LocalStorageRepository().backupBeforeImport()).toBe(true);
  });

  it('現有資料為空 → 回 true（沒東西要保留），並清掉上一次殘留的 pre-import 備份鍵', () => {
    // 塞入上一次匯入殘留的過期備份，驗證會被清掉——否則 rollback 會讀到錯的原始資料。
    localStorage.setItem(PRE_IMPORT_SESSIONS_BACKUP_KEY, 'stale-sessions');
    localStorage.setItem(PRE_IMPORT_GLOBAL_BACKUP_KEY, 'stale-global');
    expect(new LocalStorageRepository().backupBeforeImport()).toBe(true);
    expect(store.getItem(PRE_IMPORT_SESSIONS_BACKUP_KEY)).toBeNull();
    expect(store.getItem(PRE_IMPORT_GLOBAL_BACKUP_KEY)).toBeNull();
  });

  it('備份寫入失敗（storage setItem 丟例外）→ 回 false，供 UI 警示', () => {
    const failing = new ToggleFailStorage();
    (globalThis as { localStorage?: unknown }).localStorage = failing;
    // 先在不失敗的情況下塞入現有資料，再開啟「global 備份鍵寫入必失敗」。
    failing.setItem(STORAGE_KEY, JSON.stringify([makeSession()]));
    failing.setItem(GLOBAL_SETTINGS_KEY, JSON.stringify(DEFAULT_GLOBAL_SETTINGS));
    failing.failKey = PRE_IMPORT_GLOBAL_BACKUP_KEY;
    expect(new LocalStorageRepository().backupBeforeImport()).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// importBackup 原子寫入 / rollback（批次修正）：
// global 寫成功後 sessions 寫失敗（quota 滿），必須把 global 回貼匯入前原狀，
// 不可留下「新設定＋舊牌局」的混合狀態。
// ---------------------------------------------------------------------------

// 可切換讓某個 key 的 setItem 失敗的記憶體 storage（模擬 quota 滿只在某次寫入炸開）。
class ToggleFailStorage extends MemoryStorage {
  failKey: string | null = null;
  setItem(k: string, v: string): void {
    if (k === this.failKey) throw new Error('QuotaExceededError（測試模擬）');
    super.setItem(k, v);
  }
}

describe('LocalStorageRepository — importBackup 原子寫入 / rollback', () => {
  it('兩寫都成功 → global 與 sessions 都落地', async () => {
    const repo = new LocalStorageRepository();
    const payload = {
      globalSettings: { ...DEFAULT_GLOBAL_SETTINGS, defaultBase: 300 },
      sessions: [makeSession({ id: 'new' })] as unknown as Session[],
    };
    await repo.importBackup(payload);
    expect(JSON.parse(store.getItem(GLOBAL_SETTINGS_KEY)!).defaultBase).toBe(300);
    expect(JSON.parse(store.getItem(STORAGE_KEY)!)[0].id).toBe('new');
  });

  it('第二寫（saveSessions）失敗 → 回貼匯入前的 global，並上拋錯誤（不留混合狀態）', async () => {
    const failing = new ToggleFailStorage();
    (globalThis as { localStorage?: unknown }).localStorage = failing;

    // 匯入前現有資料（defaultBase 999 是要被保住的原狀）。
    const originalGlobal = JSON.stringify({ ...DEFAULT_GLOBAL_SETTINGS, defaultBase: 999 });
    const originalSessions = JSON.stringify([makeSession({ id: 'old' })]);
    failing.setItem(GLOBAL_SETTINGS_KEY, originalGlobal);
    failing.setItem(STORAGE_KEY, originalSessions);

    const repo = new LocalStorageRepository();
    // 前置：先保命備份（rollback 依據）。
    expect(repo.backupBeforeImport()).toBe(true);

    // 讓 sessions（第二寫）失敗。
    failing.failKey = STORAGE_KEY;
    const payload = {
      globalSettings: { ...DEFAULT_GLOBAL_SETTINGS, defaultBase: 111 },
      sessions: [makeSession({ id: 'imported' })] as unknown as Session[],
    };

    await expect(repo.importBackup(payload)).rejects.toThrow();

    // 關鍵：global 已回貼成匯入前原狀（999），不是匯入中途寫進去的 111。
    expect(JSON.parse(failing.getItem(GLOBAL_SETTINGS_KEY)!).defaultBase).toBe(999);
    // sessions 因寫入失敗維持原狀（old），未被覆蓋。
    expect(JSON.parse(failing.getItem(STORAGE_KEY)!)[0].id).toBe('old');
  });

  it('匯入前沒有全域設定（全新裝置）→ 第二寫失敗時 rollback＝移除 global，回到本來就沒有的原狀', async () => {
    const failing = new ToggleFailStorage();
    (globalThis as { localStorage?: unknown }).localStorage = failing;
    // 沒有任何現有資料。
    const repo = new LocalStorageRepository();
    expect(repo.backupBeforeImport()).toBe(true);

    failing.failKey = STORAGE_KEY;
    const payload = {
      globalSettings: { ...DEFAULT_GLOBAL_SETTINGS, defaultBase: 111 },
      sessions: [makeSession({ id: 'imported' })] as unknown as Session[],
    };
    await expect(repo.importBackup(payload)).rejects.toThrow();

    // rollback 應移除 global（原本就沒有），而非留下匯入中途寫入的 111。
    expect(failing.getItem(GLOBAL_SETTINGS_KEY)).toBeNull();
  });
});
