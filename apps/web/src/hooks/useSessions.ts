// 串接 repository 的 React hook。
// 元件只用這個 hook 操作資料，不直接碰 repository / localStorage。

import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  GlobalSettings,
  Player,
  RosterPlayer,
  Round,
  Session,
  SessionRules,
  Settings,
} from '../types';
import { DEFAULT_GLOBAL_SETTINGS, DEFAULT_PLAYERS } from '../types';
import { LocalStorageRepository } from '../data/localStorageRepository';
import type { StorageRepository } from '../data/repository';

// 第一版固定用 localStorage 實作；未來要換雲端只改這一行。
const repo: StorageRepository = new LocalStorageRepository();

function genId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

/** 產生全域唯一 UUID（名冊成員用）。crypto.randomUUID 不可用時退回 genId。 */
function genUuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return genId('roster');
}

/** 開桌時帶入的單一玩家（名字 + 可選名冊連結）。 */
export interface NewSessionPlayer {
  name: string;
  rosterId?: string;
}

/**
 * 把所有現有 session 中、名字等於 `name` 且「尚未連結 rosterId」的 Player
 * 回填上 `rosterId`，讓該名玩家的歷史戰績歸到名冊成員（供 aggregateByRosterId 聚合）。
 *
 * 只回填「未連結」的同名 Player，不覆蓋已連結到其他 rosterId 的 Player，
 * 避免把別人的歷史搶過來。純函式，方便單元測試。
 *
 * 名冊以「名字」為識別（CEO 定案：同名＝同一人，不支援同名不同人）：本函式會把
 * **所有** 同名且未連結的 Player 一律歸入同一個 rosterId，涵蓋全部同名未連結場次。
 */
export function linkSessionsToRoster(
  sessions: Session[],
  name: string,
  rosterId: string,
): Session[] {
  const trimmed = name.trim();
  if (!trimmed) return sessions;
  return sessions.map((s) => {
    if (!s.players.some((p) => p.name === trimmed && p.rosterId == null)) return s;
    return {
      ...s,
      players: s.players.map((p) =>
        p.name === trimmed && p.rosterId == null ? { ...p, rosterId } : p,
      ),
    };
  });
}

/**
 * 新建一場：帶入全域預設（底/台 + 規則）與一組玩家（名字 + rosterId）。
 * 規則可由開桌 sheet 覆寫 global.defaultRules。
 */
function createSession(
  name: string,
  global: GlobalSettings,
  players?: NewSessionPlayer[],
  rules?: SessionRules,
): Session {
  const sessionPlayers: Player[] = DEFAULT_PLAYERS.map((p, i) => {
    const incoming = players?.[i];
    const trimmed = incoming?.name?.trim();
    return {
      ...p,
      name: trimmed || p.name,
      rosterId: incoming?.rosterId,
    };
  });
  return {
    id: genId('s'),
    name: name.trim() || `${new Date().toLocaleDateString('zh-TW')} 場`,
    players: sessionPlayers,
    settings: { base: global.defaultBase, tai: global.defaultTai },
    rules: rules ?? { ...global.defaultRules },
    rounds: [],
    createdAt: Date.now(),
  };
}

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [globalSettings, setGlobalSettings] = useState<GlobalSettings>(
    DEFAULT_GLOBAL_SETTINGS,
  );
  const [loaded, setLoaded] = useState(false);
  // 儲存失敗時的錯誤訊息（quota 滿、無痕模式停用 storage 等），供 UI 顯示。
  const [storageError, setStorageError] = useState<string | null>(null);
  // 本機資料毀損、已被丟棄／重置時為 true，供 UI 提示。
  const [dataCorrupted, setDataCorrupted] = useState(false);
  // 避免初次載入時把空資料覆寫回 localStorage。
  const skipNextSave = useRef(true);
  const skipNextGlobalSave = useRef(true);

  // 初次載入
  useEffect(() => {
    repo
      .loadSessions()
      .then((result) => {
        setSessions(result.sessions);
        setGlobalSettings(result.globalSettings);
        setDataCorrupted(result.corrupted);
        setLoaded(true);
      })
      .catch((err) => {
        // 即使 repository 換實作或 init 出錯，也不要讓 app 卡在「載入中」。
        console.error('載入資料失敗：', err);
        setSessions([]);
        setGlobalSettings(DEFAULT_GLOBAL_SETTINGS);
        setDataCorrupted(true);
        setLoaded(true);
      });
  }, []);

  // 任何 sessions 變動都寫回本機
  useEffect(() => {
    if (!loaded) return;
    if (skipNextSave.current) {
      skipNextSave.current = false;
      return;
    }
    repo.saveSessions(sessions).then(
      () => {
        // 儲存成功，清掉先前的錯誤提示。
        setStorageError(null);
      },
      (err) => {
        console.error('儲存資料失敗：', err);
        setStorageError(
          err instanceof Error ? err.message : '資料未成功儲存，重整後可能遺失。',
        );
      },
    );
  }, [sessions, loaded]);

  // 全域設定變動寫回本機
  useEffect(() => {
    if (!loaded) return;
    if (skipNextGlobalSave.current) {
      skipNextGlobalSave.current = false;
      return;
    }
    repo.saveGlobalSettings(globalSettings).then(
      () => setStorageError(null),
      (err) => {
        console.error('儲存全域設定失敗：', err);
        setStorageError(
          err instanceof Error ? err.message : '設定未成功儲存，重整後可能遺失。',
        );
      },
    );
  }, [globalSettings, loaded]);

  // 新增一場，回傳新場 id（供路由 navigate 進詳情頁）
  const addSession = useCallback(
    (name: string, players?: NewSessionPlayer[], rules?: SessionRules): string => {
      const s = createSession(name, globalSettings, players, rules);
      setSessions((prev) => [s, ...prev]);
      return s.id;
    },
    [globalSettings],
  );

  const removeSession = useCallback((id: string) => {
    setSessions((prev) => prev.filter((s) => s.id !== id));
  }, []);

  const renameSession = useCallback((id: string, name: string) => {
    setSessions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, name: name.trim() || s.name } : s)),
    );
  }, []);

  // 更新某一場（用 updater 確保拿到最新值）
  const updateSession = useCallback((id: string, updater: (s: Session) => Session) => {
    setSessions((prev) => prev.map((s) => (s.id === id ? updater(s) : s)));
  }, []);

  const updateSettings = useCallback(
    (id: string, settings: Settings) => {
      updateSession(id, (s) => ({ ...s, settings }));
    },
    [updateSession],
  );

  // v2.1：更新某場的開桌規則（自摸加台 / 東錢）。
  const updateRules = useCallback(
    (id: string, rules: SessionRules) => {
      updateSession(id, (s) => ({ ...s, rules }));
    },
    [updateSession],
  );

  const updatePlayerName = useCallback(
    (id: string, playerId: string, name: string) => {
      // 場內改名＝把這個座位換成「另一個人」，必須一併解除名冊連結（rosterId: undefined），
      // 與開桌 sheet「手動改名→解除連結」一致；否則新名字的局數會被算進原名冊成員。
      // 註：這條路徑與「在名冊個人戰績頁改名（updateRosterPlayer）」不同——後者是改名冊
      // 成員自己的顯示名、應保留 rosterId 連結，不走這裡。
      updateSession(id, (s) => ({
        ...s,
        players: s.players.map((p) =>
          p.id === playerId ? { ...p, name, rosterId: undefined } : p,
        ),
      }));
    },
    [updateSession],
  );

  const addRound = useCallback(
    (id: string, round: Omit<Round, 'id' | 'createdAt'>) => {
      updateSession(id, (s) => ({
        ...s,
        rounds: [...s.rounds, { ...round, id: genId('r'), createdAt: Date.now() }],
      }));
    },
    [updateSession],
  );

  const removeRound = useCallback(
    (id: string, roundId: string) => {
      updateSession(id, (s) => ({
        ...s,
        rounds: s.rounds.filter((r) => r.id !== roundId),
      }));
    },
    [updateSession],
  );

  // 結算 / 取消結算本場（toggle endedAt）
  const toggleEnded = useCallback(
    (id: string) => {
      updateSession(id, (s) =>
        s.endedAt ? { ...s, endedAt: undefined } : { ...s, endedAt: Date.now() },
      );
    },
    [updateSession],
  );

  const updateGlobalSettings = useCallback((next: GlobalSettings) => {
    setGlobalSettings(next);
  }, []);

  // ---- v2.1：玩家名冊 CRUD ----

  /**
   * 新增名冊成員，回傳新成員（名字重複則回傳既有成員，不重複建立）。
   *
   * 【已知限制（CEO 定案）：名冊以「名字」為識別，不支援「同名不同人」】
   * 名冊內名字唯一：對既有同名成員再次「加入名冊」不會建立第二個成員，而是回傳既有成員，
   * 並透過 linkSessionsToRoster 把所有同名且未連結（rosterId == null）的歷史 Player
   * 一律回填到該既有成員。因此兩個現實中不同、但同名的人會被視為同一人合併計分。
   * 這是 CEO 定案接受的取捨——若日後要支援同名不同人，需改以穩定 id 而非名字作識別。
   */
  const addRosterPlayer = useCallback(
    (name: string, avatar?: string): RosterPlayer | null => {
      const trimmed = name.trim();
      if (!trimmed) return null;
      const existing = globalSettings.roster.find((r) => r.name === trimmed);
      if (existing) {
        // 名冊已有同名成員：不重複建立，但仍要回填。否則某場手動打了同名、卻沒從名冊選
        // 的未連結 Player（rosterId == null）會永遠聚合不到既有成員，靜默漏帳。
        // 把同名且未連結的歷史 Player 連到既有成員 existing.id。
        setSessions((prev) => linkSessionsToRoster(prev, trimmed, existing.id));
        return existing;
      }
      const rp: RosterPlayer = {
        id: genUuid(),
        name: trimmed,
        avatar: avatar?.trim() || undefined,
        createdAt: Date.now(),
      };
      setGlobalSettings((g) => ({ ...g, roster: [...g.roster, rp] }));
      // 回填歷史：把現有 session 中同名、尚未連結的 Player 掛上此 rosterId，
      // 讓「加入名冊」後既有戰績不歸零，能被 aggregateByRosterId 聚合到。
      setSessions((prev) => linkSessionsToRoster(prev, trimmed, rp.id));
      return rp;
    },
    [globalSettings.roster],
  );

  /**
   * 改名冊成員名稱 / 頭像。改名時同步更新所有「已連結此 rosterId」場次內 Player 的顯示名稱，
   * 讓歷史顯示與名冊一致（聚合仍以 rosterId 為主，不靠名字）。
   */
  const updateRosterPlayer = useCallback(
    (rosterId: string, patch: { name?: string; avatar?: string }) => {
      const nextName = patch.name?.trim();
      setGlobalSettings((g) => ({
        ...g,
        roster: g.roster.map((r) =>
          r.id === rosterId
            ? {
                ...r,
                name: nextName || r.name,
                avatar:
                  patch.avatar !== undefined ? patch.avatar.trim() || undefined : r.avatar,
              }
            : r,
        ),
      }));
      if (nextName) {
        setSessions((prev) =>
          prev.map((s) => {
            if (!s.players.some((p) => p.rosterId === rosterId)) return s;
            return {
              ...s,
              players: s.players.map((p) =>
                p.rosterId === rosterId ? { ...p, name: nextName } : p,
              ),
            };
          }),
        );
      }
    },
    [],
  );

  /** 從名冊移除成員（不動歷史場次的 Player；該場玩家變回「無掛勾歷史玩家」）。 */
  const removeRosterPlayer = useCallback((rosterId: string) => {
    setGlobalSettings((g) => ({
      ...g,
      roster: g.roster.filter((r) => r.id !== rosterId),
    }));
    setSessions((prev) =>
      prev.map((s) => {
        if (!s.players.some((p) => p.rosterId === rosterId)) return s;
        return {
          ...s,
          players: s.players.map((p) =>
            p.rosterId === rosterId ? { ...p, rosterId: undefined } : p,
          ),
        };
      }),
    );
  }, []);

  // 清空所有資料（場次 + 全域設定）
  const clearAll = useCallback(() => {
    setSessions([]);
    setGlobalSettings(DEFAULT_GLOBAL_SETTINGS);
  }, []);

  const dismissCorruptNotice = useCallback(() => setDataCorrupted(false), []);

  return {
    loaded,
    storageError,
    dataCorrupted,
    dismissCorruptNotice,
    sessions,
    globalSettings,
    addSession,
    removeSession,
    renameSession,
    updateSettings,
    updatePlayerName,
    addRound,
    removeRound,
    toggleEnded,
    updateRules,
    updateGlobalSettings,
    addRosterPlayer,
    updateRosterPlayer,
    removeRosterPlayer,
    clearAll,
  } as const;
}

export type { GlobalSettings, Player, RosterPlayer, Round, Session, SessionRules, Settings };
