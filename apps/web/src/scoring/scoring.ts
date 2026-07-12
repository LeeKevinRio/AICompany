// 台灣麻將（16 張）計分純函式。
//
// 規則（CEO 拍板的預設，金額/台數皆可由使用者調整）：
//   單注金額 amount = base + tai × settings.tai（底 + 台數 × 每台金額）
//   - 自摸（selfDraw = true）：其他三家每人各付 amount，贏家收 3 × amount。
//   - 放槍（selfDraw = false）：只有放槍者付 amount，贏家收 amount，另兩家 0。
//
// v2.1 開桌規則（SessionRules，存在每場 Session；未傳入則行為與舊版完全一致）：
//   1. 自摸加台 selfDrawBonusTai：自摸時 effectiveTai = round.tai + selfDrawBonusTai。
//      放槍不受影響。底/台/自摸加台這部分維持四人零和（sum = 0）。
//   2. 東錢 selfDrawDongAmount：自摸者額外「付」一筆東錢進該場「公基金」（kitty），
//      獨立於四人零和——是自摸者的單向流出，不分給其他三家。
//      此為 CEO 定案解讀，刻意寫成獨立、易抽換的函式（calcDong），
//      未來若改成「平分給三家」或「付給莊家」只需改那一段。
//   3. 眼牌 eyeTileEnabled / eyeTileTai（v2.2）：被標記為眼牌的局，
//      台數額外 + eyeTileTai。CEO 拍板：自摸/放槍都算、照一般支付規則，
//      所以是疊進 effectiveTai（維持四人零和），不是新的金流方向。
//
// 疊加順序（effectiveTai）：round.tai → +自摸加台（僅自摸）→ +眼牌加台（自摸/放槍都算）。
// 東錢是獨立的公基金流向，不進 effectiveTai。
//
// 莊家 / 連莊加台：MVP 不自動處理，使用者可自行把加台數加進 round.tai。
//
// 本檔不依賴 React / DOM，純資料進出，方便單元測試與未來原生 app 重用。

import type { Player, Round, SessionRules, Settings } from '../types';
import { DEFAULT_SESSION_RULES } from '../types';

/** 一局每位玩家的金額變化（player id -> +/- 金額） */
export type RoundDelta = Record<string, number>;

/**
 * 一局完整計分結果：
 *  - deltas：底/台/自摸加台的四人輸贏，加總恆為 0（零和性質不被東錢破壞）。
 *  - dong：本局自摸者付給公基金（kitty）的東錢金額（非自摸或關閉時為 0）。
 *  - dongPayerId：付東錢者（即自摸贏家）id；無東錢時為 null。
 */
export interface RoundOutcome {
  deltas: RoundDelta;
  dong: number;
  dongPayerId: string | null;
}

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
 * 眼牌加台（v2.2）：該場啟用眼牌、且該局標記為眼牌時，回傳額外台數，否則 0。
 *
 * 刻意獨立成小函式（比照 calcDong）：自摸/放槍都算、由輸家依現有規則承擔，
 * 是疊進 effectiveTai 的加台，不破壞四人零和。未來若改玩法只動這一段。
 * @returns 本局眼牌加台數（>=0）。
 */
export function calcEyeTileTai(round: Round, rules: SessionRules): number {
  if (!rules.eyeTileEnabled || !round.eyeTile) return 0;
  const tai = rules.eyeTileTai;
  if (!Number.isFinite(tai) || !Number.isInteger(tai) || tai <= 0) return 0;
  return tai;
}

/**
 * 有效台數：底/台計分實際採用的台數。
 * 疊加順序：round.tai → +自摸加台（僅自摸）→ +眼牌加台（自摸/放槍都算）。
 */
export function effectiveTai(round: Round, rules: SessionRules): number {
  let tai = round.tai;
  if (round.selfDraw) {
    const bonus = Number.isInteger(rules.selfDrawBonusTai) && rules.selfDrawBonusTai > 0
      ? rules.selfDrawBonusTai
      : 0;
    tai += bonus;
  }
  tai += calcEyeTileTai(round, rules);
  return tai;
}

/**
 * 東錢計算（CEO 定案：自摸者單向付給公基金 kitty）。
 *
 * 刻意獨立成一個小函式：未來若 CEO 改成「平分給三家」或「付給莊家」，
 * 只要改這一段（與回傳的 dongPayerId / 分配方式），不動四人零和主線。
 *
 * 目前語意：僅自摸觸發；非自摸或金額 <=0 時回 0。
 * @returns 本局自摸者要付進公基金的東錢金額（>=0）。
 */
export function calcDong(round: Round, rules: SessionRules): number {
  if (!round.selfDraw) return 0;
  const amount = rules.selfDrawDongAmount;
  if (!Number.isFinite(amount) || !Number.isInteger(amount) || amount <= 0) return 0;
  return amount;
}

/**
 * 計算「單一局」每位玩家的輸贏金額（底/台，含自摸加台）。
 * 會先驗證 settings 與 round（含玩家 id 合法性），不合法直接 throw。
 *
 * 注意：此回傳「不含東錢」——東錢是獨立的公基金流向，請用 scoreRoundOutcome 取得。
 * 這樣設計確保底/台/自摸加台的四人加總恆為 0（零和），不被東錢破壞。
 *
 * @param rules 開桌規則；未傳入時用 DEFAULT_SESSION_RULES（全 0），行為與舊版完全一致。
 * @returns 以 player id 為 key 的金額變化，所有人加總應為 0。
 */
export function scoreRound(
  round: Round,
  players: Player[],
  settings: Settings,
  rules: SessionRules = DEFAULT_SESSION_RULES,
): RoundDelta {
  assertValidSettings(settings);
  assertValidRound(round, players);

  const delta: RoundDelta = {};
  for (const p of players) delta[p.id] = 0;

  const amount = calcUnitAmount(settings, effectiveTai(round, rules));

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
 * 完整版單局計分：在 scoreRound（底/台零和）之上，再附上東錢/公基金資訊。
 * @returns RoundOutcome（deltas 零和 + dong + dongPayerId）。
 */
export function scoreRoundOutcome(
  round: Round,
  players: Player[],
  settings: Settings,
  rules: SessionRules = DEFAULT_SESSION_RULES,
): RoundOutcome {
  const deltas = scoreRound(round, players, settings, rules);
  const dong = calcDong(round, rules);
  return {
    deltas,
    dong,
    dongPayerId: dong > 0 ? round.winnerId : null,
  };
}

/**
 * 整場每位玩家的累計輸贏（底/台，含自摸加台，不含東錢——維持零和）。
 * @returns 以 player id 為 key 的累計金額。
 */
export function scoreSession(
  rounds: Round[],
  players: Player[],
  settings: Settings,
  rules: SessionRules = DEFAULT_SESSION_RULES,
): RoundDelta {
  const total: RoundDelta = {};
  for (const p of players) total[p.id] = 0;

  for (const round of rounds) {
    const delta = scoreRound(round, players, settings, rules);
    for (const p of players) {
      total[p.id] += delta[p.id] ?? 0;
    }
  }

  return total;
}

/**
 * 整場結算（含公基金）：
 *  - net：每位玩家「實際淨額」= 底台零和輸贏 − 自己付出的東錢。
 *         （自摸者的淨額會少掉他付的東錢；公基金不退還給任何人。）
 *  - zeroSum：底/台/自摸加台的四人零和輸贏（不含東錢，加總恆為 0）。
 *  - kitty：本場公基金累計（所有自摸者付出的東錢總和）。
 *
 * 驗算關係：sum(net) + kitty === sum(zeroSum) === 0，即 sum(net) === -kitty。
 * 也就是四人淨額總和等於「流入公基金的金額」之負值——錢沒有憑空消失。
 */
export interface SessionSettlement {
  net: RoundDelta;
  zeroSum: RoundDelta;
  kitty: number;
}

export function settleSession(
  rounds: Round[],
  players: Player[],
  settings: Settings,
  rules: SessionRules = DEFAULT_SESSION_RULES,
): SessionSettlement {
  const zeroSum: RoundDelta = {};
  const net: RoundDelta = {};
  for (const p of players) {
    zeroSum[p.id] = 0;
    net[p.id] = 0;
  }
  let kitty = 0;

  for (const round of rounds) {
    const { deltas, dong, dongPayerId } = scoreRoundOutcome(round, players, settings, rules);
    for (const p of players) {
      const d = deltas[p.id] ?? 0;
      zeroSum[p.id] += d;
      net[p.id] += d;
    }
    if (dong > 0 && dongPayerId && net[dongPayerId] !== undefined) {
      net[dongPayerId] -= dong;
      kitty += dong;
    }
  }

  return { net, zeroSum, kitty };
}
