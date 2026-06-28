// 串接 repository 的 React hook。
// 元件只用這個 hook 操作資料，不直接碰 repository / localStorage。

import { useCallback, useEffect, useRef, useState } from 'react';
import type { GlobalSettings, Player, Round, Session, Settings } from '../types';
import { DEFAULT_GLOBAL_SETTINGS, DEFAULT_PLAYERS } from '../types';
import { LocalStorageRepository } from '../data/localStorageRepository';
import type { StorageRepository } from '../data/repository';

// 第一版固定用 localStorage 實作；未來要換雲端只改這一行。
const repo: StorageRepository = new LocalStorageRepository();

function genId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

/** 新建一場：可帶入全域預設（底/台）與一組玩家名字。 */
function createSession(
  name: string,
  global: GlobalSettings,
  playerNames?: string[],
): Session {
  const players: Player[] = DEFAULT_PLAYERS.map((p, i) => ({
    ...p,
    name: playerNames?.[i]?.trim() || p.name,
  }));
  return {
    id: genId('s'),
    name: name.trim() || `${new Date().toLocaleDateString('zh-TW')} 場`,
    players,
    settings: { base: global.defaultBase, tai: global.defaultTai },
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
    (name: string, playerNames?: string[]): string => {
      const s = createSession(name, globalSettings, playerNames);
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

  const updatePlayerName = useCallback(
    (id: string, playerId: string, name: string) => {
      updateSession(id, (s) => ({
        ...s,
        players: s.players.map((p) => (p.id === playerId ? { ...p, name } : p)),
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
    updateGlobalSettings,
    clearAll,
  } as const;
}

export type { GlobalSettings, Player, Round, Session, Settings };
