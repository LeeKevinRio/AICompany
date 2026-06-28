// v2 走勢圖 / 統計用純函式。
//
// 與 scoring.ts 一樣，本檔不依賴 React / DOM，純資料進出，方便單元測試與重用。
// 全部建構在既有 scoreRound / scoreSession 之上，不改動既有計分邏輯。

import type { Player, Round, Session, Settings } from '../types';
import { calcUnitAmount, scoreRound } from './scoring';

/**
 * 走勢圖單一資料點：第 roundIndex 局結束後，各玩家的累計輸贏。
 * roundIndex = 0 代表開局（各人皆 0）。
 */
export interface TimelinePoint {
  roundIndex: number;
  cumulative: Record<string, number>; // player id -> 累計金額
}

/**
 * 建立累計時間序列（折線圖資料）。
 *
 * 對 N 局產生 N+1 個資料點（含第 0 點，代表開局各人皆 0）。
 * 第 i 點 = 截至第 i 局結束後各人的累計。
 *
 * 容錯：若某一局資料非法（scoreRound throw），該局視為 0 變化跳過，
 * 不讓整張圖崩潰（與 UI 層的毀損隔離精神一致）。
 */
export function buildCumulativeTimeline(
  rounds: Round[],
  players: Player[],
  settings: Settings,
): TimelinePoint[] {
  const zero = (): Record<string, number> => {
    const r: Record<string, number> = {};
    for (const p of players) r[p.id] = 0;
    return r;
  };

  const points: TimelinePoint[] = [{ roundIndex: 0, cumulative: zero() }];

  let running = zero();
  rounds.forEach((round, i) => {
    let delta: Record<string, number>;
    try {
      delta = scoreRound(round, players, settings);
    } catch (err) {
      // 單局非法不該讓整張圖爆掉：視為無變化。
      console.error(`走勢圖：第 ${i + 1} 局計分失敗，視為 0 變化：`, err);
      delta = zero();
    }
    const next = { ...running };
    for (const p of players) next[p.id] = (next[p.id] ?? 0) + (delta[p.id] ?? 0);
    running = next;
    points.push({ roundIndex: i + 1, cumulative: next });
  });

  return points;
}

// ---- 趣味統計（本場 highlights） ----

/** 單一趣味標籤 */
export interface Highlight {
  /** 標籤種類 key（champion / gunKing / selfDrawKing / biggestRound） */
  key: 'champion' | 'gunKing' | 'selfDrawKing' | 'biggestRound';
  label: string; // 顯示名稱（如「本場冠軍」）
  playerName: string | null; // 對應玩家名（最慘烈一局為贏家名）
  detail: string; // 補充說明（金額 / 次數）
}

export interface SessionHighlights {
  highlights: Highlight[];
  /** 每位玩家的胡牌 / 自摸 / 放槍次數，供統計摘要用 */
  perPlayer: Record<
    string,
    { wins: number; selfDraws: number; gunned: number }
  >;
}

/**
 * 計算本場趣味統計：本場冠軍、放槍王、自摸王、最慘烈一局。
 * 僅讀現有 Round 資料即可，不需擴充模型。
 */
export function calcSessionHighlights(
  rounds: Round[],
  players: Player[],
  settings: Settings,
): SessionHighlights {
  const nameOf = (id: string | null) => players.find((p) => p.id === id)?.name ?? '—';

  // 各玩家次數統計
  const perPlayer: SessionHighlights['perPlayer'] = {};
  for (const p of players) perPlayer[p.id] = { wins: 0, selfDraws: 0, gunned: 0 };

  // 放槍金額損失累計（用於放槍次數相同時的 tie-break）
  const gunLoss: Record<string, number> = {};
  for (const p of players) gunLoss[p.id] = 0;

  let biggestAmount = -1;
  let biggestWinnerId: string | null = null;

  for (const r of rounds) {
    if (!perPlayer[r.winnerId]) continue; // 防呆：winner 不在玩家清單
    perPlayer[r.winnerId].wins += 1;
    if (r.selfDraw) {
      perPlayer[r.winnerId].selfDraws += 1;
    } else if (r.loserId && perPlayer[r.loserId]) {
      perPlayer[r.loserId].gunned += 1;
      gunLoss[r.loserId] += calcUnitAmount(settings, r.tai);
    }

    // 最慘烈一局：贏家單局收最多者
    const amount = calcUnitAmount(settings, r.tai);
    const won = r.selfDraw ? amount * (players.length - 1) : amount;
    if (won > biggestAmount) {
      biggestAmount = won;
      biggestWinnerId = r.winnerId;
    }
  }

  const highlights: Highlight[] = [];

  if (rounds.length > 0) {
    // 本場冠軍：累計最高
    let champId: string | null = null;
    let champVal = -Infinity;
    for (const p of players) {
      let total = 0;
      for (const r of rounds) {
        try {
          total += scoreRound(r, players, settings)[p.id] ?? 0;
        } catch {
          // 非法局略過
        }
      }
      if (total > champVal) {
        champVal = total;
        champId = p.id;
      }
    }
    if (champId) {
      highlights.push({
        key: 'champion',
        label: '本場冠軍',
        playerName: nameOf(champId),
        detail: formatSigned(champVal),
      });
    }

    // 放槍王：放槍次數最多（次數相同取損失金額最多者）
    let gunId: string | null = null;
    let gunMax = 0;
    for (const p of players) {
      const cnt = perPlayer[p.id].gunned;
      if (cnt === 0) continue;
      if (
        gunId === null ||
        cnt > perPlayer[gunId].gunned ||
        (cnt === perPlayer[gunId].gunned && gunLoss[p.id] > gunLoss[gunId])
      ) {
        gunId = p.id;
        gunMax = cnt;
      }
    }
    if (gunId) {
      highlights.push({
        key: 'gunKing',
        label: '放槍王',
        playerName: nameOf(gunId),
        detail: `放槍 ${gunMax} 次`,
      });
    }

    // 自摸王：自摸次數最多
    let sdId: string | null = null;
    let sdMax = 0;
    for (const p of players) {
      const cnt = perPlayer[p.id].selfDraws;
      if (cnt === 0) continue;
      if (sdId === null || cnt > perPlayer[sdId].selfDraws) {
        sdId = p.id;
        sdMax = cnt;
      }
    }
    if (sdId) {
      highlights.push({
        key: 'selfDrawKing',
        label: '自摸王',
        playerName: nameOf(sdId),
        detail: `自摸 ${sdMax} 次`,
      });
    }

    // 最慘烈一局
    if (biggestWinnerId && biggestAmount > 0) {
      highlights.push({
        key: 'biggestRound',
        label: '最慘烈一局',
        playerName: nameOf(biggestWinnerId),
        detail: `單局 ${formatSigned(biggestAmount)}`,
      });
    }
  }

  return { highlights, perPlayer };
}

// ---- 玩家跨場彙整 ----

/** 跨場單場結果（供玩家頁歷史與走勢） */
export interface PlayerSessionResult {
  sessionId: string;
  sessionName: string;
  createdAt: number;
  amount: number; // 該場該玩家累計輸贏
}

export interface PlayerStats {
  name: string;
  totalAmount: number; // 跨場總輸贏
  sessionsPlayed: number; // 出場場次
  totalWins: number; // 總胡牌局數
  totalSelfDraws: number; // 總自摸局數
  totalGunned: number; // 總放槍局數
  history: PlayerSessionResult[]; // 各場結果（時間正序）
  /** 近期走勢（每場金額，正序），供 sparkline */
  recentTrend: number[];
  longestWinStreak: number; // 最長連贏場數（單場正收益）
  longestLoseStreak: number; // 最長連輸場數
  winRate: number; // 勝率（正收益場次佔比，0~1）
}

/**
 * 以「玩家名字」為識別鍵，跨場彙整某玩家的統計。
 * 注意：v2 接受同名不同人會被合併的限制（見企劃技術風險表）。
 */
export function aggregatePlayerStats(
  sessions: Session[],
  playerName: string,
): PlayerStats {
  const history: PlayerSessionResult[] = [];
  let totalWins = 0;
  let totalSelfDraws = 0;
  let totalGunned = 0;

  // 時間正序處理，方便算連勝/連敗
  const sorted = [...sessions].sort((a, b) => a.createdAt - b.createdAt);

  for (const s of sorted) {
    const player = s.players.find((p) => p.name === playerName);
    if (!player) continue;

    let amount = 0;
    for (const r of s.rounds) {
      try {
        amount += scoreRound(r, s.players, s.settings)[player.id] ?? 0;
      } catch {
        // 非法局略過
      }
      if (r.winnerId === player.id) {
        totalWins += 1;
        if (r.selfDraw) totalSelfDraws += 1;
      }
      if (!r.selfDraw && r.loserId === player.id) {
        totalGunned += 1;
      }
    }

    history.push({
      sessionId: s.id,
      sessionName: s.name,
      createdAt: s.createdAt,
      amount,
    });
  }

  const totalAmount = history.reduce((acc, h) => acc + h.amount, 0);
  const recentTrend = history.map((h) => h.amount);

  // 連勝 / 連敗（以單場正/負收益判斷）
  let longestWinStreak = 0;
  let longestLoseStreak = 0;
  let curWin = 0;
  let curLose = 0;
  let positiveCount = 0;
  for (const h of history) {
    if (h.amount > 0) {
      positiveCount += 1;
      curWin += 1;
      curLose = 0;
      longestWinStreak = Math.max(longestWinStreak, curWin);
    } else if (h.amount < 0) {
      curLose += 1;
      curWin = 0;
      longestLoseStreak = Math.max(longestLoseStreak, curLose);
    } else {
      curWin = 0;
      curLose = 0;
    }
  }

  const winRate = history.length > 0 ? positiveCount / history.length : 0;

  return {
    name: playerName,
    totalAmount,
    sessionsPlayed: history.length,
    totalWins,
    totalSelfDraws,
    totalGunned,
    history,
    recentTrend,
    longestWinStreak,
    longestLoseStreak,
    winRate,
  };
}

/** 從所有 session 蒐集出現過的玩家名字（去重，依出場次數排序） */
export function collectPlayerNames(sessions: Session[]): string[] {
  const count = new Map<string, number>();
  for (const s of sessions) {
    const seen = new Set<string>();
    for (const p of s.players) {
      const name = p.name.trim();
      if (!name || seen.has(name)) continue;
      seen.add(name);
      count.set(name, (count.get(name) ?? 0) + 1);
    }
  }
  return [...count.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-TW'))
    .map(([name]) => name);
}

// ---- 共用格式化 ----

/** 帶正負號與千位逗號的金額字串（0 不加號）。供純函式輸出，UI 也可重用。 */
export function formatSigned(value: number): string {
  const abs = Math.abs(value).toLocaleString('en-US');
  if (value > 0) return `+${abs}`;
  if (value < 0) return `-${abs}`;
  return '0';
}
