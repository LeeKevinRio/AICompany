// 台灣麻將（16 張）計分純函式。
//
// 規則（CEO 拍板的預設，金額/台數皆可由使用者調整）：
//   單注金額 amount = base + tai × settings.tai（底 + 台數 × 每台金額）
//   - 自摸（selfDraw = true）：其他三家每人各付 amount，贏家收 3 × amount。
//   - 放槍（selfDraw = false）：只有放槍者付 amount，贏家收 amount，另兩家 0。
//
// 莊家 / 連莊加台：MVP 不自動處理，使用者可自行把加台數加進 round.tai。
//
// 本檔不依賴 React / DOM，純資料進出，方便單元測試與未來原生 app 重用。

import type { Player, Round, Settings } from '../types';

/** 一局每位玩家的金額變化（player id -> +/- 金額） */
export type RoundDelta = Record<string, number>;

/**
 * 驗證設定數值合法：base / tai 都必須是 finite 的非負整數。
 * 不合法就 throw，讓資料層／呼叫端能捕捉，避免 NaN 流進計分。
 */
export function assertValidSettings(settings: Settings): void {
  for (const [key, value] of [
    ['base', settings.base],
    ['tai', settings.tai],
  ] as const) {
    if (!Number.isFinite(value) || !Number.isInteger(value) || value < 0) {
      throw new Error(`設定 ${key} 不合法（必須為非負整數）：${value}`);
    }
  }
}

/**
 * 驗證一局資料合法（搭配 players 一起檢查 id 合法性）：
 *   - tai 必須是 finite 的非負整數。
 *   - winner 必須存在於 players。
 *   - 自摸（selfDraw=true）：loserId 必須為 null。
 *   - 放槍（selfDraw=false）：loser 必須存在、loser ≠ winner、loserId 不可為空。
 * 不合法就 throw，不靜默略過整局。
 */
export function assertValidRound(round: Round, players: Player[]): void {
  if (!Number.isFinite(round.tai) || !Number.isInteger(round.tai) || round.tai < 0) {
    throw new Error(`台數不合法（必須為非負整數）：${round.tai}`);
  }

  const playerIds = new Set(players.map((p) => p.id));

  if (!playerIds.has(round.winnerId)) {
    throw new Error(`贏家 id 不在玩家清單內：${round.winnerId}`);
  }

  if (round.selfDraw) {
    // 自摸時不應有放槍者
    if (round.loserId !== null) {
      throw new Error(`自摸時 loserId 必須為 null，實際：${round.loserId}`);
    }
  } else {
    // 放槍：必須有合法且不等於贏家的放槍者
    if (!round.loserId) {
      throw new Error('放槍時必須指定放槍者（loserId 不可為空）');
    }
    if (!playerIds.has(round.loserId)) {
      throw new Error(`放槍者 id 不在玩家清單內：${round.loserId}`);
    }
    if (round.loserId === round.winnerId) {
      throw new Error('放槍者不能是贏家本人');
    }
  }
}

/** 計算單注金額（呼叫前請確保 settings 已驗證） */
export function calcUnitAmount(settings: Settings, tai: number): number {
  return settings.base + tai * settings.tai;
}

/**
 * 計算「單一局」每位玩家的輸贏金額。
 * 會先驗證 settings 與 round（含玩家 id 合法性），不合法直接 throw。
 * @returns 以 player id 為 key 的金額變化，所有人加總應為 0。
 */
export function scoreRound(
  round: Round,
  players: Player[],
  settings: Settings,
): RoundDelta {
  assertValidSettings(settings);
  assertValidRound(round, players);

  const delta: RoundDelta = {};
  for (const p of players) delta[p.id] = 0;

  const amount = calcUnitAmount(settings, round.tai);

  if (round.selfDraw) {
    // 自摸：其他三家各付 amount，贏家收 (人數-1) × amount
    for (const p of players) {
      if (p.id === round.winnerId) {
        delta[p.id] += amount * (players.length - 1);
      } else {
        delta[p.id] -= amount;
      }
    }
  } else {
    // 放槍：只有放槍者付，贏家收（loserId 已於 assertValidRound 保證合法）
    delta[round.winnerId] += amount;
    delta[round.loserId as string] -= amount;
  }

  return delta;
}

/**
 * 計算整場每位玩家的累計輸贏（把每一局相加）。
 * @returns 以 player id 為 key 的累計金額。
 */
export function scoreSession(
  rounds: Round[],
  players: Player[],
  settings: Settings,
): RoundDelta {
  const total: RoundDelta = {};
  for (const p of players) total[p.id] = 0;

  for (const round of rounds) {
    const delta = scoreRound(round, players, settings);
    for (const p of players) {
      total[p.id] += delta[p.id] ?? 0;
    }
  }

  return total;
}
