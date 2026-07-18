// v2 走勢圖 / 統計用純函式。
//
// 與 scoring.ts 一樣，本檔不依賴 React / DOM，純資料進出，方便單元測試與重用。
// 全部建構在既有 scoreRound / scoreSession 之上，不改動既有計分邏輯。

import type { Player, Round, Session, SessionRules, Settings } from '../types';
import { DEFAULT_SESSION_RULES } from '../types';
import type { DealerContext } from './scoring';
import { calcDong, calcUnitAmount, effectiveTai, scoreRound } from './scoring';
import { deriveDealerContexts } from './dealer';
import { seatOccupantAt } from './substitution';

/** 讀取 session 的規則；舊資料無 rules 欄位時回 DEFAULT_SESSION_RULES（全 0，行為不變）。 */
export function rulesOf(session: Pick<Session, 'rules'>): SessionRules {
  return session.rules ?? DEFAULT_SESSION_RULES;
}

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
  rules: SessionRules = DEFAULT_SESSION_RULES,
  dealerCtxs?: readonly (DealerContext | undefined)[],
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
    let dong = 0;
    try {
      delta = scoreRound(round, players, settings, rules, dealerCtxs?.[i]);
      // 走勢圖以「淨額」呈現：自摸者付出的東錢算進他自己的曲線（單向流出，不分給他人）。
      dong = calcDong(round, rules);
    } catch (err) {
      // 單局非法不該讓整張圖爆掉：視為無變化。
      console.error(`走勢圖：第 ${i + 1} 局計分失敗，視為 0 變化：`, err);
      delta = zero();
      dong = 0;
    }
    const next = { ...running };
    for (const p of players) next[p.id] = (next[p.id] ?? 0) + (delta[p.id] ?? 0);
    if (dong > 0 && next[round.winnerId] !== undefined) {
      next[round.winnerId] -= dong;
    }
    running = next;
    points.push({ roundIndex: i + 1, cumulative: next });
  });

  return points;
}

// ---- 趣味統計（本場 highlights） ----

/** 單一趣味標籤 */
export interface Highlight {
  /** 標籤種類 key */
  key: 'champion' | 'gunKing' | 'selfDrawKing' | 'biggestRound' | 'smallestRound';
  label: string; // 顯示名稱（如「本場冠軍」）
  playerName: string | null; // 對應玩家名（最慘烈一局為贏家名）
  detail: string; // 補充說明（金額 / 次數）
}

/**
 * 趣味標籤對應 emoji（單一出處）。原本 Highlights 元件與 SettlePage 各自複製一份，
 * 收斂到資料函式旁，型別綁定 Highlight['key'] 避免遺漏或不同步。
 */
export const HIGHLIGHT_EMOJI: Record<Highlight['key'], string> = {
  champion: '🏆',
  gunKing: '💥',
  selfDrawKing: '🀄',
  biggestRound: '🔥',
  smallestRound: '⚡',
};

export interface SessionHighlights {
  highlights: Highlight[];
  /** 每位玩家的胡牌 / 自摸 / 放槍次數，供統計摘要用 */
  perPlayer: Record<
    string,
    { wins: number; selfDraws: number; gunned: number }
  >;
  /** v2.1：本場公基金（東錢）累計金額。 */
  kitty: number;
  /** v2.1 建議做（匯率換算）：每局平均底台金額、平均台數。無局數時皆為 0。 */
  avgRoundAmount: number;
  avgTai: number;
}

/**
 * 計算本場趣味統計：本場冠軍、放槍王、自摸王、最慘烈一局。
 * 僅讀現有 Round 資料即可，不需擴充模型。
 */
export function calcSessionHighlights(
  rounds: Round[],
  players: Player[],
  settings: Settings,
  rules: SessionRules = DEFAULT_SESSION_RULES,
  dealerCtxs?: readonly (DealerContext | undefined)[],
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
  // v2.1 建議做：最快結束（台數最低）一局——以贏家單局收最少者代表。
  let smallestAmount = Infinity;
  let smallestWinnerId: string | null = null;

  let kitty = 0;
  let taiSum = 0;
  let unitAmountSum = 0;
  // v2.3：流局不計入「平均每局」分母（無底台事件），與胡牌率分母定義一致。
  let scoredCount = 0;

  rounds.forEach((r, i) => {
    // v2.3：流局（winnerId=''）不計胡/放槍/平均，直接跳過（自然不動 perPlayer / 分母）。
    if (r.drawn || !perPlayer[r.winnerId]) return; // 防呆：流局 / winner 不在玩家清單
    scoredCount += 1;
    perPlayer[r.winnerId].wins += 1;
    if (r.selfDraw) {
      perPlayer[r.winnerId].selfDraws += 1;
      kitty += calcDong(r, rules);
    } else if (r.loserId && perPlayer[r.loserId]) {
      perPlayer[r.loserId].gunned += 1;
      // effectiveTai 對放槍局＝r.tai＋眼牌台（selfDrawBonus 只在自摸時加，此處天然不含）；
      // 眼牌台放槍也算，輸家實際損失含眼牌台，tie-break 才語義一致。
      gunLoss[r.loserId] += calcUnitAmount(settings, effectiveTai(r, rules));
    }

    // 含自摸加台的有效台數 / 單注金額（供匯率換算；平均台數刻意不含連莊加台）。
    const eTai = effectiveTai(r, rules);
    const amount = calcUnitAmount(settings, eTai);
    taiSum += eTai;
    unitAmountSum += amount;

    // 「最慘烈 / 最快一局」以贏家實收（含連莊加台）判定，用 scoreRound 的贏家 delta 才精準。
    let won = r.selfDraw ? amount * (players.length - 1) : amount;
    try {
      won = scoreRound(r, players, settings, rules, dealerCtxs?.[i])[r.winnerId] ?? won;
    } catch {
      // 非法局：退回不含連莊加台的估值
    }
    if (won > biggestAmount) {
      biggestAmount = won;
      biggestWinnerId = r.winnerId;
    }
    if (won < smallestAmount) {
      smallestAmount = won;
      smallestWinnerId = r.winnerId;
    }
  });

  const highlights: Highlight[] = [];

  if (rounds.length > 0) {
    // 本場冠軍：累計最高
    let champId: string | null = null;
    let champVal = -Infinity;
    for (const p of players) {
      let total = 0;
      rounds.forEach((r, i) => {
        try {
          total += scoreRound(r, players, settings, rules, dealerCtxs?.[i])[p.id] ?? 0;
          // 公基金為自摸者單向流出，冠軍以「淨額」判定才公允。
          if (r.selfDraw && r.winnerId === p.id) total -= calcDong(r, rules);
        } catch {
          // 非法局略過
        }
      });
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

    // 最慘烈一局（贏家單局收最多）。要求金額 > 0 且確實有對應贏家。
    if (biggestWinnerId && biggestAmount > 0) {
      highlights.push({
        key: 'biggestRound',
        label: '最慘烈一局',
        playerName: nameOf(biggestWinnerId),
        detail: `單局 ${formatSigned(biggestAmount)}`,
      });
    }

    // v2.1 建議做：最快結束一局（台數最低、贏家單局收最少）。
    // guard 與「最慘烈一局」對齊：要求贏家存在、金額 > 0（排除 0 元邊界，避免只有一局
    // 且金額為 0 時靜默輸出怪結果），且與最慘烈一局不同金額時才顯示（避免單局牌局兩標籤指同一局）。
    if (
      smallestWinnerId &&
      smallestAmount > 0 &&
      smallestAmount !== biggestAmount
    ) {
      highlights.push({
        key: 'smallestRound',
        label: '最快結束局',
        playerName: nameOf(smallestWinnerId),
        detail: `單局 ${formatSigned(smallestAmount)}`,
      });
    }
  }

  // v2.3：平均分母改用 scoredCount（排除流局），避免流局稀釋每局平均底台 / 台數。
  const avgRoundAmount = scoredCount > 0 ? Math.round(unitAmountSum / scoredCount) : 0;
  const avgTai = scoredCount > 0 ? taiSum / scoredCount : 0;

  return { highlights, perPlayer, kitty, avgRoundAmount, avgTai };
}

// ---- 玩家跨場彙整 ----

/** 跨場單場結果（供玩家頁歷史與走勢） */
export interface PlayerSessionResult {
  sessionId: string;
  sessionName: string;
  createdAt: number;
  amount: number; // 該場該玩家累計輸贏
}

/**
 * 數據系統 Phase 3：冤家榜單筆——某一位「對手」與本玩家的跨場放槍配對統計。
 * 對手識別鍵優先用 rosterId、無 rosterId 時 fallback 用名字（與聚合邏輯一致）；
 * name / rosterId 供 UI 顯示與頭像查詢，coPlayedRounds 作為門檻分母。
 */
export interface EnemyEntry {
  /** 對手顯示名稱（取最近一場的名字） */
  name: string;
  /** 對手的 rosterId（名冊成員才有；純名字對手為 null）。供 UI 查頭像 / 代表色。 */
  rosterId: string | null;
  /** 我放槍給他的次數（r.loserId 為我、r.winnerId 為他，且非自摸） */
  shotByMe: number;
  /** 他放槍給我的次數（r.winnerId 為我、r.loserId 為他，且非自摸） */
  shotByThem: number;
  /** 同場局數（我與他同桌的總局數），作為冤家榜門檻分母 */
  coPlayedRounds: number;
}

export interface PlayerStats {
  name: string;
  totalAmount: number; // 跨場總輸贏（淨額，含自摸付出的東錢）
  sessionsPlayed: number; // 出場場次
  totalWins: number; // 總胡牌局數
  totalSelfDraws: number; // 總自摸局數
  totalGunned: number; // 總放槍局數
  /** 數據系統 Phase 1：此玩家上桌的總局數（各符合場次 rounds.length × 符合座位數之和），
   *  作為胡牌率 / 放槍率的分母。同場多個同名/同 rosterId 座位時乘上座位數，與
   *  totalWins / totalGunned 的「多座位加總」語意一致，避免率值分母被低估。 */
  totalRounds: number;
  /** 數據系統 Phase 1：所有胡牌局的台數總和（分子），除以 totalWins → 平均台數。
   *  刻意用 r.tai（玩家申報台數）而非 effectiveTai，反映「習慣胡幾台的牌」，不含自摸加台的規則加成。 */
  totalWinTai: number;
  /** 數據系統 Phase 1：跨場單局最高收益金額（自摸＝單注×(人數-1)，放槍＝單注）。無胡牌時為 0。 */
  bestRoundAmount: number;
  history: PlayerSessionResult[]; // 各場結果（時間正序）
  /** 近期走勢（每場金額，正序），供 sparkline */
  recentTrend: number[];
  longestWinStreak: number; // 最長連贏場數（單場正收益）
  longestLoseStreak: number; // 最長連輸場數
  winRate: number; // 勝率（正收益場次佔比，0~1）
  /** v2.1 建議做：近 5 場場均輸贏（不足 5 場以實際場數平均；無場次為 0）。 */
  recentAvg: number;
  /** 數據系統 Phase 3：跨場對手放槍配對（冤家榜原始資料，未套門檻 / 未排序）。
   *  以對手名字排序求穩定輸出；門檻篩選與名次排序交給 selectRivalBoard。 */
  enemyBoard: EnemyEntry[];
}

/**
 * 跨場彙整核心：以 `matchOccupant` 判定「某座位在某局的實際佔用者是不是本人」後逐局加總。
 * - 金額採「淨額」：底/台/自摸加台（含 session 規則）再扣掉自己付出的東錢。
 * - 舊資料無 rules 欄位時用 DEFAULT_SESSION_RULES（全 0），行為與 v2 一致。
 *
 * v2.4（批次 3）換人歸戶：座位的實際佔用者可能隨局數改變（seatOccupantAt 解析）。
 * 因此**逐局**判定「這局哪些座位是本人」——某局的座位輸贏 / 胡 / 放槍歸給該局實際在座者，
 * 接手者自成一帳（從接手局起算，不繼承前人累計）；`totalRounds`（三率卡分母）＝
 * 本人實際在桌的（非流局）局數。舊場 / 無換人時每局佔用者恆等於初始 players，
 * 逐局加總與舊版「整場固定座位」完全一致（零回歸）。
 *
 * 同一局可能有多個符合座位（例如同名的兩個座位）。依 CEO 定案「同名＝同一人」，
 * 同局所有符合座位的貢獻全部加總，避免漏帳；每局最多一個符合座位（常態）時行為不變。
 */
function aggregateBy(
  sessions: Session[],
  displayName: string,
  matchOccupant: (occ: Player) => boolean,
): PlayerStats {
  const history: PlayerSessionResult[] = [];
  let totalWins = 0;
  let totalSelfDraws = 0;
  let totalGunned = 0;
  let totalRounds = 0;
  let totalWinTai = 0;
  let bestRoundAmount = 0;

  // 冤家榜：以「對手識別鍵」累計跨場放槍配對。鍵優先 rosterId、fallback 名字（前綴避免撞鍵）。
  const enemyMap = new Map<string, EnemyEntry>();
  const enemyKey = (p: Player) => (p.rosterId != null ? `rid:${p.rosterId}` : `nm:${p.name}`);
  const touchEnemy = (p: Player): EnemyEntry => {
    const key = enemyKey(p);
    let e = enemyMap.get(key);
    if (!e) {
      e = { name: p.name, rosterId: p.rosterId ?? null, shotByMe: 0, shotByThem: 0, coPlayedRounds: 0 };
      enemyMap.set(key, e);
    } else {
      // 時間正序處理，較新場次覆蓋顯示名（對手改名時取最近一次名字）。
      e.name = p.name;
    }
    return e;
  };

  // 時間正序處理，方便算連勝/連敗
  const sorted = [...sessions].sort((a, b) => a.createdAt - b.createdAt);

  for (const s of sorted) {
    // 是否參與本場：本人為某座位的初始佔用者，或為某筆換人的接手者。
    // 涵蓋「0 局場（只初始入座）」與「僅以接手者身分出現」兩種情形；舊場無 substitutions
    // 時等同「本人是否為初始 players 之一」，與舊版 matched.length>0 判定一致（零回歸）。
    const participates =
      s.players.some((p) => matchOccupant(p)) ||
      (s.substitutions ?? []).some((sub) =>
        matchOccupant({ id: sub.seatId, name: sub.name, rosterId: sub.rosterId }),
      );
    if (!participates) continue;

    const rules = rulesOf(s);
    // v2.3：連莊加台需知每局莊家 / 連莊數——由 deriveTableState 推導（舊場 / 未啟用回空陣列，零回歸）。
    const dealerCtxs = deriveDealerContexts(s);
    let amount = 0;

    s.rounds.forEach((r, ri) => {
      // v2.4：逐局解析四個座位當下佔用者，判定「這局哪些座位是本人 / 誰是對手」。
      const occupants = s.players.map((p) => seatOccupantAt(s, p.id, ri));
      const mySeats = occupants.filter((o) => matchOccupant(o));
      const myIds = new Set(mySeats.map((o) => o.id));
      const nonDrawn = !r.drawn;

      const dctx = dealerCtxs[ri];
      // 每局只算一次計分（含連莊加台），供淨額 / 最高收益共用。
      let delta: Record<string, number> | null = null;
      try {
        delta = scoreRound(r, s.players, s.settings, rules, dctx);
      } catch {
        delta = null; // 非法局略過
      }

      // 本人這局實際在座的座位：逐座加總金額 / 胡 / 放槍。
      for (const mine of mySeats) {
        if (delta) {
          amount += delta[mine.id] ?? 0;
          // 自己自摸付的東錢是淨流出，從淨額扣除。
          if (r.selfDraw && r.winnerId === mine.id) amount -= calcDong(r, rules);
        }
        // 流局 winnerId=''、loserId=null，天然不會命中任何座位（不計胡 / 放槍）。
        if (r.winnerId === mine.id) {
          totalWins += 1;
          if (r.selfDraw) totalSelfDraws += 1;
          // 平均台數分子用 r.tai（申報台數），不含自摸 / 連莊加台。
          totalWinTai += r.tai;
          // 跨場單局最高收益：直接取贏家的計分 delta（已含連莊 / 眼牌加台）。
          const won = delta ? (delta[mine.id] ?? 0) : 0;
          if (won > bestRoundAmount) bestRoundAmount = won;
        }
        if (!r.selfDraw && r.loserId === mine.id) {
          totalGunned += 1;
        }
      }

      // 分母 / 冤家榜只在「本人這局有在桌」時累計（接手前的局不算本人在桌）。
      if (mySeats.length > 0) {
        // 三率卡分母：本人這局實際在桌的座位數（流局不計）。每局一座位（常態）時等同 +1。
        if (nonDrawn) totalRounds += mySeats.length;
        // 同場局數：本人這局在桌，與每個非本人座位（該局實際佔用者）同桌一局（流局不計）。
        if (nonDrawn) {
          for (const opp of occupants) {
            if (!myIds.has(opp.id)) touchEnemy(opp).coPlayedRounds += 1;
          }
        }
        // 冤家榜配對（每局最多一筆）：放槍是「有輸家」的局，自摸 / 流局（loserId=null）不列入。
        if (!r.selfDraw && r.loserId != null && r.winnerId) {
          const iShot = myIds.has(r.loserId) && !myIds.has(r.winnerId);
          const iWon = myIds.has(r.winnerId) && !myIds.has(r.loserId);
          if (iShot) {
            touchEnemy(seatOccupantAt(s, r.winnerId, ri)).shotByMe += 1; // 我放槍給贏家
          } else if (iWon) {
            touchEnemy(seatOccupantAt(s, r.loserId, ri)).shotByThem += 1; // 輸家放槍給我
          }
        }
      }
    });

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
  const last5 = recentTrend.slice(-5);
  const recentAvg =
    last5.length > 0 ? Math.round(last5.reduce((a, b) => a + b, 0) / last5.length) : 0;

  // 冤家榜原始資料：依名字排序求穩定輸出（門檻與名次由 selectRivalBoard 決定）。
  const enemyBoard = [...enemyMap.values()].sort((a, b) =>
    a.name.localeCompare(b.name, 'zh-TW'),
  );

  return {
    name: displayName,
    totalAmount,
    sessionsPlayed: history.length,
    totalWins,
    totalSelfDraws,
    totalGunned,
    totalRounds,
    totalWinTai,
    bestRoundAmount,
    history,
    recentTrend,
    longestWinStreak,
    longestLoseStreak,
    winRate,
    recentAvg,
    enemyBoard,
  };
}

/**
 * 以「玩家名字」為識別鍵，跨場彙整某玩家的統計。
 * 注意：依 CEO 定案「同名＝同一人」，同一場有多個同名座位會全部加總（不漏帳）。
 */
export function aggregatePlayerStats(
  sessions: Session[],
  playerName: string,
): PlayerStats {
  return aggregateBy(sessions, playerName, (occ) => occ.name === playerName);
}

/**
 * 以「玩家名字」彙整，但**只算尚未連結到名冊（rosterId == null）的同名場次**。
 *
 * 用於「名冊已有同名成員（已連結若干場）」與「仍有同名未連結場次」並存的過渡狀態：
 * 名冊成員那邊以 aggregateByRosterId 聚合已連結場次，歷史「唯名字」卡片若仍用
 * aggregatePlayerStats（純名字）會把已連結場次也算進去 → 雙重計算。改用本函式後，
 * 歷史卡片只反映尚未歸入名冊的場次，與名冊成員的數字不重疊。
 *
 * matchPlayer 用 `p.rosterId == null` 同時涵蓋 null / undefined。
 */
export function aggregateUnlinkedByName(
  sessions: Session[],
  playerName: string,
): PlayerStats {
  return aggregateBy(
    sessions,
    playerName,
    (occ) => occ.name === playerName && occ.rosterId == null,
  );
}

/**
 * v2.1：以 RosterPlayer.id 為識別鍵跨場彙整——以 rosterId 精準對應「同一個人」，
 * 不受改名影響。`displayName` 通常傳名冊目前的顯示名稱。
 */
export function aggregateByRosterId(
  sessions: Session[],
  rosterId: string,
  displayName: string,
): PlayerStats {
  return aggregateBy(sessions, displayName, (occ) => occ.rosterId === rosterId);
}

/**
 * 從所有 session 蒐集出現過的玩家名字（去重，依出場次數排序）。
 * v2.4：除了初始入座的 players，也掃 substitutions 的接手者——否則「僅以接手者身分出現」
 * 的玩家（如中途上桌的戊）雖然統計算得出（aggregateBy 有 participates 判定），玩家頁卻列不出他。
 * 同場內同名只計一次（players 與 substitutions 共用一個 seen），去重與名冊連結邏輯與 players 一致。
 */
export function collectPlayerNames(sessions: Session[]): string[] {
  const count = new Map<string, number>();
  for (const s of sessions) {
    const seen = new Set<string>();
    const tally = (rawName: string) => {
      const name = rawName.trim();
      if (!name || seen.has(name)) return;
      seen.add(name);
      count.set(name, (count.get(name) ?? 0) + 1);
    };
    for (const p of s.players) tally(p.name);
    for (const sub of s.substitutions ?? []) tally(sub.name);
  }
  return [...count.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-TW'))
    .map(([name]) => name);
}

// ---- 數據系統 Phase 1：率值 + 樣本門檻 ----

/**
 * 把「分子 / 分母 + 樣本門檻」算成可直接顯示的率值狀態（誠實標注紅線）。
 *
 * - 分母 < minSample（或分母 <= 0）→ `insufficient: true`，UI 顯示「—」而非假數字。
 * - 否則回四捨五入後的整數百分比。
 *
 * 門檻：胡牌率 / 放槍率 minSample = 10（分母為總局數）；自摸率 minSample = 5（分母為胡牌次數）。
 */
export function rateWithThreshold(
  numerator: number,
  denominator: number,
  minSample: number,
): { insufficient: boolean; pct: number } {
  if (denominator <= 0 || denominator < minSample) {
    return { insufficient: true, pct: 0 };
  }
  return { insufficient: false, pct: Math.round((numerator / denominator) * 100) };
}

// ---- 數據系統 Phase 2：趨勢符號 ----

export type TrendDirection = 'up' | 'down' | 'flat';

/**
 * 清單頁近期趨勢符號方向（規範 4-2）：
 * - recentAvg > 0 → 'up'（↑）；< 0 → 'down'（↓）；=== 0 → 'flat'（→）
 * - 場次不足 2 場（無法判斷趨勢）→ null（UI 顯示空白佔位、不畫符號）
 *
 * recentAvg 即 PlayerStats.recentAvg（近 5 場均），已是四捨五入整數；此處只判正負零。
 */
export function trendDirection(
  recentAvg: number,
  sessionsPlayed: number,
): TrendDirection | null {
  if (sessionsPlayed < 2) return null;
  if (recentAvg > 0) return 'up';
  if (recentAvg < 0) return 'down';
  return 'flat';
}

// ---- 數據系統 Phase 2：稱號徽章 ----

export type TitleKey =
  | 'selfDrawMachine' // 自摸機器
  | 'ironWall' // 鐵壁守門
  | 'gunKing' // 炮王
  | 'winKing' // 胡王
  | 'highTai'; // 等大台

export interface PlayerTitle {
  key: TitleKey;
  label: string;
  emoji: string;
  /** CSS modifier class（.title-chip.type-xxx，見視覺規範 8-5） */
  typeClass: string;
  /** 代表性排序用：觸發門檻的樣本分母（越大越有代表性，用於超過 2 個時取捨） */
  sample: number;
}

/** 各稱號的顯示中繼資料（emoji / 文字 / 語意 CSS class）。 */
const TITLE_META: Record<TitleKey, { label: string; emoji: string; typeClass: string }> = {
  selfDrawMachine: { label: '自摸機器', emoji: '🀄', typeClass: 'type-self-draw' },
  ironWall: { label: '鐵壁守門', emoji: '🛡️', typeClass: 'type-iron-wall' },
  gunKing: { label: '炮王', emoji: '💥', typeClass: 'type-gun-king' },
  winKing: { label: '胡王', emoji: '🏆', typeClass: 'type-win-king' },
  highTai: { label: '等大台', emoji: '💎', typeClass: 'type-high-tai' },
};

/** key 的固定優先序（sample 並列時的 tie-break，維持穩定輸出）。 */
const TITLE_ORDER: TitleKey[] = ['ironWall', 'winKing', 'gunKing', 'selfDrawMachine', 'highTai'];

/**
 * 依企劃「稱號觸發條件」計算玩家達成的稱號（保守門檻，避免太容易得到）。
 *
 * | 稱號     | 觸發條件                         | 樣本分母 |
 * | 自摸機器 | 自摸率 ≥ 60% 且 totalWins ≥ 10   | totalWins |
 * | 鐵壁守門 | 放槍率 ≤ 10% 且 totalRounds ≥ 30 | totalRounds |
 * | 炮王     | 放槍率 ≥ 35% 且 totalRounds ≥ 20 | totalRounds |
 * | 胡王     | 胡牌率 ≥ 30% 且 totalRounds ≥ 30 | totalRounds |
 * | 等大台   | 平均台數 ≥ 4.0 且 totalWins ≥ 10 | totalWins |
 *
 * 率值以原始比值（非四捨五入的百分比）比對門檻，避免顯示層 rounding 造成邊界誤判。
 * 最多回傳 2 個：超過時依「樣本分母大→小」（最有代表性者優先）取捨、並列以固定序穩定。
 */
export function computePlayerTitles(
  stats: Pick<
    PlayerStats,
    'totalWins' | 'totalSelfDraws' | 'totalGunned' | 'totalRounds' | 'totalWinTai'
  >,
): PlayerTitle[] {
  const { totalWins, totalSelfDraws, totalGunned, totalRounds, totalWinTai } = stats;
  const selfDrawRate = totalWins > 0 ? totalSelfDraws / totalWins : 0;
  const gunRate = totalRounds > 0 ? totalGunned / totalRounds : 0;
  const winRate = totalRounds > 0 ? totalWins / totalRounds : 0;
  const avgTai = totalWins > 0 ? totalWinTai / totalWins : 0;

  const hit: { key: TitleKey; sample: number }[] = [];
  if (totalWins >= 10 && selfDrawRate >= 0.6) hit.push({ key: 'selfDrawMachine', sample: totalWins });
  if (totalRounds >= 30 && gunRate <= 0.1) hit.push({ key: 'ironWall', sample: totalRounds });
  if (totalRounds >= 20 && gunRate >= 0.35) hit.push({ key: 'gunKing', sample: totalRounds });
  if (totalRounds >= 30 && winRate >= 0.3) hit.push({ key: 'winKing', sample: totalRounds });
  if (totalWins >= 10 && avgTai >= 4.0) hit.push({ key: 'highTai', sample: totalWins });

  return hit
    .sort((a, b) => b.sample - a.sample || TITLE_ORDER.indexOf(a.key) - TITLE_ORDER.indexOf(b.key))
    .slice(0, 2)
    .map(({ key, sample }) => ({ key, sample, ...TITLE_META[key] }));
}

// ---- 數據系統 Phase 3：冤家榜名次選取 ----

export interface RivalBoardView {
  /** 'list'＝有達門檻對手；'empty'＝有跨場局但無人達門檻；'hidden'＝無跨場資料，整塊不 render */
  status: 'list' | 'empty' | 'hidden';
  rivals: EnemyEntry[];
}

/**
 * 從冤家榜原始資料挑出可顯示名次（規範 6-1 顯示條件）：
 * - 只保留 coPlayedRounds ≥ minCoPlayed（預設 10）的對手；依互動次數（放槍給我＋我放槍給他）
 *   降序、同場局數降序、名字序 tie-break，取前 limit 名（預設 3）。
 * - 有達門檻對手 → status 'list'。
 * - 無人達門檻但玩家確有跨場局（totalRounds > 0 且存在對手）→ 'empty'（顯示成長路徑空狀態）。
 * - 全無跨場資料 → 'hidden'（整塊不 render）。
 */
export function selectRivalBoard(
  enemyBoard: EnemyEntry[],
  totalRounds: number,
  minCoPlayed = 10,
  limit = 3,
): RivalBoardView {
  const qualified = enemyBoard
    .filter((e) => e.coPlayedRounds >= minCoPlayed)
    .sort(
      (a, b) =>
        b.shotByMe + b.shotByThem - (a.shotByMe + a.shotByThem) ||
        b.coPlayedRounds - a.coPlayedRounds ||
        a.name.localeCompare(b.name, 'zh-TW'),
    )
    .slice(0, limit);
  if (qualified.length > 0) return { status: 'list', rivals: qualified };
  if (totalRounds > 0 && enemyBoard.length > 0) return { status: 'empty', rivals: [] };
  return { status: 'hidden', rivals: [] };
}

// ---- 共用格式化 ----

/** 帶正負號與千位逗號的金額字串（0 不加號）。供純函式輸出，UI 也可重用。 */
export function formatSigned(value: number): string {
  const abs = Math.abs(value).toLocaleString('en-US');
  if (value > 0) return `+${abs}`;
  if (value < 0) return `-${abs}`;
  return '0';
}
