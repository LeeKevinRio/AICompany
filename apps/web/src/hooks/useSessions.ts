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
  Substitution,
} from '../types';
import { DEFAULT_GLOBAL_SETTINGS, DEFAULT_PLAYERS } from '../types';
import { LocalStorageRepository } from '../data/localStorageRepository';
import type { BackupPayload } from '../data/backup';
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
 * 純函式：從一場中刪掉某一局，並同步左移換人時間軸的 fromRoundIndex。
 *
 * 為何要動 substitutions：fromRoundIndex 是「接手者從第幾局（含）起接手」的 0-based index，
 * 對齊 rounds 陣列位置。刪掉 index=deletedIndex 的那局後，其後所有局會前移一格，
 * 若 fromRoundIndex 不跟著左移，接手邊界就會靜默漂移——接手者的首局會被錯歸前任。
 *
 * 規則（邊界定義）：
 *  - fromRoundIndex > deletedIndex：接手邊界在被刪局之後，整段右側左移一格 → -1。
 *  - fromRoundIndex ≤ deletedIndex：被刪的是接手者名下（或前任名下）的局，接手邊界不動；
 *    特別是「剛好刪掉接手者首局」（fromRoundIndex === deletedIndex）時，接手點仍落在同一
 *    index（原本第 fromRoundIndex+1 局遞補上來），接手者只是少算一局，歸戶邊界不變。
 *  - 找不到該局（deletedIndex < 0，理論上不會發生）：原樣返回，絕不亂動 substitutions。
 *
 * 抽成純函式方便單元測試（與 linkSessionsToRoster 同一種「可測純資料轉換」模式）。
 */
export function removeRoundFromSession(s: Session, roundId: string): Session {
  const deletedIndex = s.rounds.findIndex((r) => r.id === roundId);
  if (deletedIndex < 0) return s;
  const rounds = s.rounds.filter((r) => r.id !== roundId);
  if (!s.substitutions) return { ...s, rounds };
  const substitutions = s.substitutions.map((sub) =>
    sub.fromRoundIndex > deletedIndex
      ? { ...sub, fromRoundIndex: sub.fromRoundIndex - 1 }
      : sub,
  );
  return { ...s, rounds, substitutions };
}

/**
 * 新建一場：帶入全域預設（底/台 + 規則）與一組玩家（名字 + rosterId）。
 * 底/台與規則皆可由開桌 sheet 覆寫 global 預設（#1：底/台改為開局時設定）。
 */
function createSession(
  name: string,
  global: GlobalSettings,
  players?: NewSessionPlayer[],
  rules?: SessionRules,
  settings?: Settings,
  dealerStartSeat?: string,
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
  const effectiveRules = rules ?? { ...global.defaultRules };
  // v2.3：只有連莊啟用（dealerEnabled）且有指定首莊座位時才寫入 dealerStartSeat；
  // 否則留 undefined → 連莊功能靜默不啟用（與舊場一致）。
  const seatIds = new Set(sessionPlayers.map((p) => p.id));
  const startSeat =
    effectiveRules.dealerEnabled && dealerStartSeat && seatIds.has(dealerStartSeat)
      ? dealerStartSeat
      : undefined;
  return {
    id: genId('s'),
    name: name.trim() || `${new Date().toLocaleDateString('zh-TW')} 場`,
    players: sessionPlayers,
    settings: settings ?? { base: global.defaultBase, tai: global.defaultTai },
    rules: effectiveRules,
    rounds: [],
    createdAt: Date.now(),
    ...(startSeat ? { dealerStartSeat: startSeat } : {}),
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
    (
      name: string,
      players?: NewSessionPlayer[],
      rules?: SessionRules,
      settings?: Settings,
      dealerStartSeat?: string,
    ): string => {
      const s = createSession(name, globalSettings, players, rules, settings, dealerStartSeat);
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
      // 刪局同時修正換人時間軸（fromRoundIndex 左移），避免歸戶邊界漂移。詳見 removeRoundFromSession。
      updateSession(id, (s) => removeRoundFromSession(s, roundId));
    },
    [updateSession],
  );

  // v2.4（批次 3）：中途換人——某座位自「當前局起」（fromRoundIndex = 目前已記局數）換成新玩家。
  // 防呆：接手者名字必填；fromRoundIndex 一律鎖成 s.rounds.length（不允許改寫過去局的歸屬）。
  // 只影響歸戶 / 顯示層，金流零和不動（scoreRound / settleSession 完全不看 substitutions）。
  const addSubstitution = useCallback(
    (id: string, seatId: string, name: string, rosterId?: string) => {
      const trimmed = name.trim();
      if (!trimmed) return;
      updateSession(id, (s) => {
        if (!s.players.some((p) => p.id === seatId)) return s;
        const fromRoundIndex = s.rounds.length;
        const sub: Substitution = {
          seatId,
          fromRoundIndex,
          name: trimmed,
          ...(rosterId ? { rosterId } : {}),
        };
        const existing = s.substitutions ?? [];
        // 防呆：同座位、同 fromRoundIndex 已有一筆（尚未記局就連換兩次）→ 覆蓋而非追加，
        // 避免堆疊無效中間筆。這與 seatOccupantAt「同 fromRoundIndex 取後出現者（>=）」的
        // 後進覆蓋語義一致——這裡直接讓資料層只留最後一筆，更乾淨。
        const dupIdx = existing.findIndex(
          (x) => x.seatId === seatId && x.fromRoundIndex === fromRoundIndex,
        );
        const substitutions =
          dupIdx >= 0
            ? existing.map((x, i) => (i === dupIdx ? sub : x))
            : [...existing, sub];
        return { ...s, substitutions };
      });
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

  /**
   * 覆蓋匯入前先隔離現有資料（誤匯入還救得回來），回傳是否備份成功。
   * 由 UI 在開啟確認 sheet 時呼叫：若回 false 就在 sheet 上警示「無法自動備份」，
   * 不要照樣承諾「覆蓋前會自動保留」。也是 importBackup rollback 的依據（須先呼叫）。
   */
  const backupBeforeImport = useCallback((): boolean => repo.backupBeforeImport(), []);

  /**
   * 匯入備份（整份覆蓋）。payload 必須是已通過 validateBackup 的資料，
   * 且呼叫端須已先呼叫 backupBeforeImport（保命備份 + rollback 依據）。
   *
   * 步驟順序是刻意的：先原子寫 storage（repo.importBackup 內含 global rollback）→
   * 成功後才更新畫面 state。若寫入失敗（quota 滿等）會 throw，此時 state 完全沒動、
   * storage 也已 rollback，畫面仍是舊資料，不會出現「畫面顯示已匯入、實際存的是舊資料」的假成功。
   */
  const importBackup = useCallback(async (payload: BackupPayload): Promise<void> => {
    await repo.importBackup(payload);
    // storage 已由 repo.importBackup 直寫落地；接下來 setState 會觸發兩個 auto-save useEffect，
    // 對同一份資料重複寫入。設 skip 旗標讓那一輪略過（真正的落地已完成），避免雙重寫入。
    skipNextSave.current = true;
    skipNextGlobalSave.current = true;
    setGlobalSettings(payload.globalSettings);
    setSessions(payload.sessions);
    setStorageError(null);
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
    addSubstitution,
    toggleEnded,
    updateRules,
    updateGlobalSettings,
    addRosterPlayer,
    updateRosterPlayer,
    removeRosterPlayer,
    backupBeforeImport,
    importBackup,
    clearAll,
  } as const;
}

export type {
  GlobalSettings,
  Player,
  RosterPlayer,
  Round,
  Session,
  SessionRules,
  Settings,
  Substitution,
};
