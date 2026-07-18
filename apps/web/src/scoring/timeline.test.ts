import { describe, it, expect } from 'vitest';
import {
  buildCumulativeTimeline,
  calcSessionHighlights,
  aggregatePlayerStats,
  aggregateByRosterId,
  collectPlayerNames,
  computePlayerTitles,
  formatSigned,
  rateWithThreshold,
  selectRivalBoard,
  trendDirection,
} from './timeline';
import type { EnemyEntry } from './timeline';
import type { Player, Round, Session, SessionRules, Settings } from '../types';
import { DEFAULT_SESSION_RULES } from '../types';
import { deriveDealerContexts } from './dealer';

const players: Player[] = [
  { id: 'p1', name: 'A' },
  { id: 'p2', name: 'B' },
  { id: 'p3', name: 'C' },
  { id: 'p4', name: 'D' },
];

// 底 100、台 50
const settings: Settings = { base: 100, tai: 50 };

// 無特殊規則（自摸加台 0、東錢 0），維持與舊版相同的零和行為。
const rules: SessionRules = { ...DEFAULT_SESSION_RULES };

function makeRound(partial: Partial<Round>): Round {
  return {
    id: 'r1',
    winnerId: 'p1',
    tai: 0,
    selfDraw: false,
    loserId: 'p2',
    createdAt: 0,
    ...partial,
  };
}

describe('buildCumulativeTimeline', () => {
  it('空局數：只有開局第 0 點，各人皆 0', () => {
    const tl = buildCumulativeTimeline([], players, settings);
    expect(tl).toHaveLength(1);
    expect(tl[0].roundIndex).toBe(0);
    expect(tl[0].cumulative).toEqual({ p1: 0, p2: 0, p3: 0, p4: 0 });
  });

  it('N 局產生 N+1 個資料點', () => {
    const rounds: Round[] = [
      makeRound({ id: 'r1' }),
      makeRound({ id: 'r2' }),
      makeRound({ id: 'r3' }),
    ];
    const tl = buildCumulativeTimeline(rounds, players, settings);
    expect(tl).toHaveLength(4);
    expect(tl.map((p) => p.roundIndex)).toEqual([0, 1, 2, 3]);
  });

  it('累計正確：放槍 + 自摸 逐點累加', () => {
    const rounds: Round[] = [
      // r1：p1 放槍贏 p2，0 台 → p1 +100, p2 -100
      makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 0, selfDraw: false }),
      // r2：p3 自摸，0 台 → p3 +300，其他各 -100
      makeRound({ id: 'r2', winnerId: 'p3', loserId: null, tai: 0, selfDraw: true }),
    ];
    const tl = buildCumulativeTimeline(rounds, players, settings);

    // 第 0 點
    expect(tl[0].cumulative).toEqual({ p1: 0, p2: 0, p3: 0, p4: 0 });
    // 第 1 局後
    expect(tl[1].cumulative).toEqual({ p1: 100, p2: -100, p3: 0, p4: 0 });
    // 第 2 局後
    expect(tl[2].cumulative).toEqual({ p1: 0, p2: -200, p3: 300, p4: -100 });
  });

  it('每一點的累計加總皆為 0（零和）', () => {
    const rounds: Round[] = [
      makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 2, selfDraw: false }),
      makeRound({ id: 'r2', winnerId: 'p4', loserId: null, tai: 1, selfDraw: true }),
      makeRound({ id: 'r3', winnerId: 'p2', loserId: 'p3', tai: 5, selfDraw: false }),
    ];
    const tl = buildCumulativeTimeline(rounds, players, settings);
    for (const point of tl) {
      const sum = players.reduce((acc, p) => acc + point.cumulative[p.id], 0);
      expect(sum).toBe(0);
    }
  });

  it('遇到非法局不丟例外：該局視為 0 變化', () => {
    const rounds: Round[] = [
      makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 1, selfDraw: false }),
      // 非法：放槍卻沒有 loserId
      makeRound({ id: 'r2', winnerId: 'p3', loserId: null, tai: 1, selfDraw: false }),
    ];
    const tl = buildCumulativeTimeline(rounds, players, settings);
    expect(tl).toHaveLength(3);
    // 第 2 局非法 → 累計維持與第 1 局相同
    expect(tl[2].cumulative).toEqual(tl[1].cumulative);
  });
});

describe('calcSessionHighlights', () => {
  it('空局：無 highlights', () => {
    const { highlights } = calcSessionHighlights([], players, settings);
    expect(highlights).toEqual([]);
  });

  it('正確算出本場冠軍 / 放槍王 / 自摸王', () => {
    const rounds: Round[] = [
      // p1 放槍贏 p2
      makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 3, selfDraw: false }),
      // p1 自摸
      makeRound({ id: 'r2', winnerId: 'p1', loserId: null, tai: 0, selfDraw: true }),
      // p3 放槍贏 p2（p2 放槍 2 次）
      makeRound({ id: 'r3', winnerId: 'p3', loserId: 'p2', tai: 1, selfDraw: false }),
    ];
    const { highlights, perPlayer } = calcSessionHighlights(rounds, players, settings);

    const champ = highlights.find((h) => h.key === 'champion');
    expect(champ?.playerName).toBe('A'); // p1 累計最高

    const gun = highlights.find((h) => h.key === 'gunKing');
    expect(gun?.playerName).toBe('B'); // p2 放槍 2 次

    const sd = highlights.find((h) => h.key === 'selfDrawKing');
    expect(sd?.playerName).toBe('A'); // p1 自摸 1 次

    expect(perPlayer.p2.gunned).toBe(2);
    expect(perPlayer.p1.selfDraws).toBe(1);
    expect(perPlayer.p1.wins).toBe(2);
  });

  it('邊界：只有一局且金額為 0 時，最慘烈/最快結束局 guard 一致都不輸出', () => {
    // base 0、tai 0 → 單局金額為 0，兩個標籤都不該出現（避免靜默輸出怪結果）。
    const zeroSettings: Settings = { base: 0, tai: 0 };
    const rounds: Round[] = [
      makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 0, selfDraw: false }),
    ];
    const { highlights } = calcSessionHighlights(rounds, players, zeroSettings);
    expect(highlights.find((h) => h.key === 'biggestRound')).toBeUndefined();
    expect(highlights.find((h) => h.key === 'smallestRound')).toBeUndefined();
  });
});

describe('aggregatePlayerStats', () => {
  function makeSession(partial: Partial<Session>): Session {
    return {
      id: 's1',
      name: '場',
      players: players.map((p) => ({ ...p })),
      settings: { ...settings },
      rules: { ...rules },
      rounds: [],
      createdAt: 0,
      ...partial,
    };
  }

  it('跨場彙整總輸贏與場次', () => {
    const sessions: Session[] = [
      makeSession({
        id: 's1',
        createdAt: 1,
        rounds: [makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 0, selfDraw: false })],
      }),
      makeSession({
        id: 's2',
        createdAt: 2,
        rounds: [makeRound({ id: 'r2', winnerId: 'p2', loserId: 'p1', tai: 0, selfDraw: false })],
      }),
    ];
    const stats = aggregatePlayerStats(sessions, 'A');
    expect(stats.sessionsPlayed).toBe(2);
    // s1: A +100；s2: A -100 → 總 0
    expect(stats.totalAmount).toBe(0);
    expect(stats.history.map((h) => h.amount)).toEqual([100, -100]);
  });

  it('連贏 / 連輸 / 勝率計算', () => {
    const sessions: Session[] = [
      makeSession({ id: 's1', createdAt: 1, rounds: [makeRound({ winnerId: 'p1', loserId: 'p2' })] }), // A +100 贏
      makeSession({ id: 's2', createdAt: 2, rounds: [makeRound({ winnerId: 'p1', loserId: 'p2' })] }), // A +100 贏
      makeSession({ id: 's3', createdAt: 3, rounds: [makeRound({ winnerId: 'p2', loserId: 'p1' })] }), // A -100 輸
    ];
    const stats = aggregatePlayerStats(sessions, 'A');
    expect(stats.longestWinStreak).toBe(2);
    expect(stats.longestLoseStreak).toBe(1);
    expect(stats.winRate).toBeCloseTo(2 / 3);
  });
});

describe('aggregateBy 同一場多個同名座位都加總（修正漏帳）', () => {
  function makeSession(partial: Partial<Session>): Session {
    return {
      id: 's1',
      name: '場',
      players: players.map((p) => ({ ...p })),
      settings: { ...settings },
      rules: { ...rules },
      rounds: [],
      createdAt: 0,
      ...partial,
    };
  }

  it('同名（aggregatePlayerStats）：同場兩個同名座位的輸贏/次數都算到，不只取第一個', () => {
    // p1 與 p3 都叫「阿明」（同名＝同一人）。
    // r1：p1 放槍贏 p2 → p1 +100；r2：p3 放槍贏 p4 → p3 +100。
    const session = makeSession({
      players: [
        { id: 'p1', name: '阿明' },
        { id: 'p2', name: 'B' },
        { id: 'p3', name: '阿明' },
        { id: 'p4', name: 'D' },
      ],
      rounds: [
        makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 0, selfDraw: false }),
        makeRound({ id: 'r2', winnerId: 'p3', loserId: 'p4', tai: 0, selfDraw: false }),
      ],
    });

    const stats = aggregatePlayerStats([session], '阿明');
    // 兩個同名座位都算到：+100（p1）+100（p3）= +200。若只取第一個座位只會是 +100（漏帳）。
    expect(stats.totalAmount).toBe(200);
    expect(stats.sessionsPlayed).toBe(1);
    // 胡牌次數也加總兩座位：p1 一胡 + p3 一胡 = 2。
    expect(stats.totalWins).toBe(2);
  });

  it('rosterId（aggregateByRosterId）：同場兩個同 rosterId 座位都加總', () => {
    const rosterId = 'roster-ming';
    const session = makeSession({
      players: [
        { id: 'p1', name: '阿明', rosterId },
        { id: 'p2', name: 'B' },
        { id: 'p3', name: '阿明', rosterId },
        { id: 'p4', name: 'D' },
      ],
      rounds: [
        makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 0, selfDraw: false }),
        makeRound({ id: 'r2', winnerId: 'p3', loserId: 'p4', tai: 0, selfDraw: false }),
      ],
    });

    const stats = aggregateByRosterId([session], rosterId, '阿明');
    expect(stats.totalAmount).toBe(200);
    expect(stats.sessionsPlayed).toBe(1);
    expect(stats.totalWins).toBe(2);
  });

  it('零回歸：每場最多一個同名座位時，加總結果與舊版（取第一個）一致', () => {
    // 一般情形：只有 p1 叫「阿明」，其餘不同名。
    const session = makeSession({
      players: [
        { id: 'p1', name: '阿明' },
        { id: 'p2', name: 'B' },
        { id: 'p3', name: 'C' },
        { id: 'p4', name: 'D' },
      ],
      rounds: [makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 0, selfDraw: false })],
    });

    const stats = aggregatePlayerStats([session], '阿明');
    expect(stats.totalAmount).toBe(100);
    expect(stats.sessionsPlayed).toBe(1);
    expect(stats.totalWins).toBe(1);
  });
});

describe('aggregateBy 數據系統 Phase 1 新欄位（totalRounds / totalWinTai / bestRoundAmount）', () => {
  function makeSession(partial: Partial<Session>): Session {
    return {
      id: 's1',
      name: '場',
      players: players.map((p) => ({ ...p })),
      settings: { ...settings },
      rules: { ...rules },
      rounds: [],
      createdAt: 0,
      ...partial,
    };
  }

  it('totalRounds = 各場 rounds.length 之和（單一座位）', () => {
    const sessions: Session[] = [
      makeSession({
        id: 's1',
        createdAt: 1,
        rounds: [
          makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2' }),
          makeRound({ id: 'r2', winnerId: 'p2', loserId: 'p1' }),
        ],
      }),
      makeSession({
        id: 's2',
        createdAt: 2,
        rounds: [makeRound({ id: 'r3', winnerId: 'p3', loserId: 'p1' })],
      }),
    ];
    const stats = aggregatePlayerStats(sessions, 'A');
    expect(stats.totalRounds).toBe(3); // 2 + 1
  });

  it('totalRounds 同場多個同名座位：rounds.length × 座位數', () => {
    // p1 與 p3 都叫「阿明」，一場 2 局 → 分母 2 × 2 = 4，與 totalWins/totalGunned 的多座位加總一致。
    const session = makeSession({
      players: [
        { id: 'p1', name: '阿明' },
        { id: 'p2', name: 'B' },
        { id: 'p3', name: '阿明' },
        { id: 'p4', name: 'D' },
      ],
      rounds: [
        makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2' }),
        makeRound({ id: 'r2', winnerId: 'p3', loserId: 'p4' }),
      ],
    });
    const stats = aggregatePlayerStats([session], '阿明');
    expect(stats.totalRounds).toBe(4);
    expect(stats.totalWins).toBe(2);
  });

  it('totalWinTai 累加胡牌局的 r.tai（不含自摸加台）', () => {
    // 自摸加台開 2 台，驗證 totalWinTai 用 r.tai（3 + 2）而非 effectiveTai（含 bonus）。
    const bonusRules: SessionRules = { selfDrawBonusTai: 2, selfDrawDongAmount: 0, eyeTileEnabled: false, eyeTileTai: 0, dealerEnabled: false, dealerBaseTai: 0, dealerStreakTaiPerStreak: 0, dealerTaiScope: 'dealer' };
    const session = makeSession({
      rules: bonusRules,
      rounds: [
        makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 3, selfDraw: false }),
        makeRound({ id: 'r2', winnerId: 'p1', loserId: null, tai: 2, selfDraw: true }),
      ],
    });
    const stats = aggregatePlayerStats([session], 'A');
    expect(stats.totalWinTai).toBe(5); // 3 + 2（非 3 + (2+2)=7）
  });

  it('bestRoundAmount：自摸收益（×(人數-1)）與放槍收益取最大', () => {
    // base 100 / 台 50。r1 放槍 3 台 → 100+3×50=250；r2 自摸 0 台 → 100×3=300。
    const session = makeSession({
      rounds: [
        makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 3, selfDraw: false }),
        makeRound({ id: 'r2', winnerId: 'p1', loserId: null, tai: 0, selfDraw: true }),
      ],
    });
    const stats = aggregatePlayerStats([session], 'A');
    expect(stats.bestRoundAmount).toBe(300);
  });

  it('邊界：0 局（有出場但無局）→ 三新欄位皆 0，sessionsPlayed 仍計 1', () => {
    const session = makeSession({ rounds: [] });
    const stats = aggregatePlayerStats([session], 'A');
    expect(stats.sessionsPlayed).toBe(1);
    expect(stats.totalRounds).toBe(0);
    expect(stats.totalWinTai).toBe(0);
    expect(stats.bestRoundAmount).toBe(0);
  });

  it('邊界：0 胡（有局但此人未胡）→ totalWinTai / bestRoundAmount 為 0，totalRounds 照算', () => {
    const session = makeSession({
      rounds: [
        makeRound({ id: 'r1', winnerId: 'p2', loserId: 'p1' }),
        makeRound({ id: 'r2', winnerId: 'p3', loserId: 'p1' }),
      ],
    });
    const stats = aggregatePlayerStats([session], 'A');
    expect(stats.totalWins).toBe(0);
    expect(stats.totalWinTai).toBe(0);
    expect(stats.bestRoundAmount).toBe(0);
    expect(stats.totalRounds).toBe(2);
    expect(stats.totalGunned).toBe(2);
  });
});

describe('rateWithThreshold（率值 + 樣本門檻）', () => {
  it('分母為 0：insufficient（顯示「—」）', () => {
    expect(rateWithThreshold(3, 0, 10)).toEqual({ insufficient: true, pct: 0 });
  });

  it('分母 < 門檻：insufficient（胡牌率 N<10）', () => {
    expect(rateWithThreshold(2, 9, 10)).toEqual({ insufficient: true, pct: 0 });
  });

  it('分母 = 門檻：顯示率值（四捨五入整數百分比）', () => {
    expect(rateWithThreshold(3, 10, 10)).toEqual({ insufficient: false, pct: 30 });
  });

  it('自摸率門檻 5：totalWins<5 為 insufficient，>=5 顯示', () => {
    expect(rateWithThreshold(1, 4, 5)).toEqual({ insufficient: true, pct: 0 });
    expect(rateWithThreshold(2, 5, 5)).toEqual({ insufficient: false, pct: 40 });
  });

  it('百分比四捨五入', () => {
    expect(rateWithThreshold(1, 3, 1).pct).toBe(33); // 33.33 → 33
    expect(rateWithThreshold(2, 3, 1).pct).toBe(67); // 66.67 → 67
  });
});

describe('collectPlayerNames', () => {
  it('去重並依出場次數排序', () => {
    const base: Session = {
      id: 's',
      name: '場',
      players: players.map((p) => ({ ...p })),
      settings: { ...settings },
      rules: { ...rules },
      rounds: [],
      createdAt: 0,
    };
    const s1: Session = { ...base, id: 's1', players: [
      { id: 'p1', name: '小明' },
      { id: 'p2', name: '阿美' },
      { id: 'p3', name: '老王' },
      { id: 'p4', name: '小芳' },
    ] };
    const s2: Session = { ...base, id: 's2', players: [
      { id: 'p1', name: '小明' },
      { id: 'p2', name: '阿美' },
      { id: 'p3', name: '阿志' },
      { id: 'p4', name: '小芳' },
    ] };
    const names = collectPlayerNames([s1, s2]);
    // 小明 / 阿美 / 小芳 出現 2 次，排前面
    expect(names.slice(0, 3).sort()).toEqual(['小明', '小芳', '阿美'].sort());
    expect(names).toContain('阿志');
    expect(names).toContain('老王');
  });
});

describe('formatSigned', () => {
  it('正負零與千位逗號', () => {
    expect(formatSigned(1200)).toBe('+1,200');
    expect(formatSigned(-800)).toBe('-800');
    expect(formatSigned(0)).toBe('0');
    expect(formatSigned(12500)).toBe('+12,500');
  });
});

// ---- 數據系統 Phase 2 / 3：批次 B 新增純函式 ----

describe('trendDirection（清單頁趨勢符號）', () => {
  it('場次不足 2 場：回 null（不顯示符號）', () => {
    expect(trendDirection(500, 1)).toBeNull();
    expect(trendDirection(0, 0)).toBeNull();
  });

  it('recentAvg 正/負/零 對應 up/down/flat（場次達 2）', () => {
    expect(trendDirection(300, 2)).toBe('up');
    expect(trendDirection(-300, 5)).toBe('down');
    expect(trendDirection(0, 3)).toBe('flat');
  });
});

describe('computePlayerTitles（稱號徽章觸發規則）', () => {
  const base = {
    totalWins: 0,
    totalSelfDraws: 0,
    totalGunned: 0,
    totalRounds: 0,
    totalWinTai: 0,
  };

  it('無任何達標：回空陣列', () => {
    expect(computePlayerTitles(base)).toEqual([]);
  });

  it('自摸機器：自摸率 ≥60% 且 totalWins ≥10（邊界 6/10）', () => {
    const titles = computePlayerTitles({ ...base, totalWins: 10, totalSelfDraws: 6, totalRounds: 40 });
    expect(titles.map((t) => t.key)).toContain('selfDrawMachine');
    // 樣本數不足一格：totalWins=9 不觸發
    expect(computePlayerTitles({ ...base, totalWins: 9, totalSelfDraws: 6, totalRounds: 40 }).map((t) => t.key)).not.toContain('selfDrawMachine');
  });

  it('鐵壁守門：放槍率 ≤10% 且 totalRounds ≥30（邊界 3/30）', () => {
    expect(computePlayerTitles({ ...base, totalRounds: 30, totalGunned: 3 }).map((t) => t.key)).toContain('ironWall');
    // totalRounds=29 未達門檻
    expect(computePlayerTitles({ ...base, totalRounds: 29, totalGunned: 2 }).map((t) => t.key)).not.toContain('ironWall');
  });

  it('炮王：放槍率 ≥35% 且 totalRounds ≥20（邊界 7/20）', () => {
    expect(computePlayerTitles({ ...base, totalRounds: 20, totalGunned: 7 }).map((t) => t.key)).toContain('gunKing');
  });

  it('胡王：胡牌率 ≥30% 且 totalRounds ≥30（邊界 9/30）', () => {
    expect(computePlayerTitles({ ...base, totalRounds: 30, totalWins: 9 }).map((t) => t.key)).toContain('winKing');
  });

  it('等大台：平均台數 ≥4.0 且 totalWins ≥10（邊界 40/10）', () => {
    expect(computePlayerTitles({ ...base, totalWins: 10, totalWinTai: 40, totalRounds: 40 }).map((t) => t.key)).toContain('highTai');
  });

  it('最多 2 個：超過時取樣本分母大者（代表性優先）', () => {
    // 同時觸發 ironWall(40) / winKing(40) / highTai(12) / selfDrawMachine(12)。
    const titles = computePlayerTitles({
      totalRounds: 40,
      totalGunned: 4, // 放槍率 10% → ironWall
      totalWins: 12, // 胡牌率 30% → winKing
      totalSelfDraws: 8, // 自摸率 66.7% → selfDrawMachine
      totalWinTai: 48, // 平均 4.0 台 → highTai
    });
    expect(titles).toHaveLength(2);
    // 分母 40 的 ironWall / winKing 勝出；並列以固定序（ironWall 先）。
    expect(titles.map((t) => t.key)).toEqual(['ironWall', 'winKing']);
  });

  it('回傳項帶顯示中繼資料（label / emoji / typeClass）', () => {
    const [t] = computePlayerTitles({ ...base, totalRounds: 20, totalGunned: 7 });
    expect(t).toMatchObject({ key: 'gunKing', label: '炮王', emoji: '💥', typeClass: 'type-gun-king' });
  });
});

describe('selectRivalBoard（冤家榜門檻 / 空狀態 / 名次）', () => {
  const mk = (partial: Partial<EnemyEntry>): EnemyEntry => ({
    name: 'X',
    rosterId: null,
    shotByMe: 0,
    shotByThem: 0,
    coPlayedRounds: 0,
    ...partial,
  });

  it('無跨場資料（空 board 且 totalRounds=0）→ hidden（整塊不 render）', () => {
    expect(selectRivalBoard([], 0).status).toBe('hidden');
  });

  it('有跨場局但所有對手 < 10 局 → empty（成長路徑空狀態）', () => {
    const board = [mk({ name: '小明', coPlayedRounds: 9, shotByMe: 3 })];
    const view = selectRivalBoard(board, 9);
    expect(view.status).toBe('empty');
    expect(view.rivals).toEqual([]);
  });

  it('門檻邊界：coPlayedRounds = 10 即列入（10 顯示、9 不顯示）', () => {
    expect(selectRivalBoard([mk({ coPlayedRounds: 10 })], 10).status).toBe('list');
    expect(selectRivalBoard([mk({ coPlayedRounds: 9 })], 10).status).toBe('empty');
  });

  it('依互動次數（放槍給我＋我放槍給他）降序、限 3 名', () => {
    const board = [
      mk({ name: 'A', coPlayedRounds: 20, shotByMe: 1, shotByThem: 1 }), // 互動 2
      mk({ name: 'B', coPlayedRounds: 20, shotByMe: 4, shotByThem: 2 }), // 互動 6
      mk({ name: 'C', coPlayedRounds: 20, shotByMe: 0, shotByThem: 3 }), // 互動 3
      mk({ name: 'D', coPlayedRounds: 20, shotByMe: 5, shotByThem: 5 }), // 互動 10
      mk({ name: 'E', coPlayedRounds: 5, shotByMe: 9, shotByThem: 9 }), // 未達門檻
    ];
    const view = selectRivalBoard(board, 90);
    expect(view.status).toBe('list');
    expect(view.rivals.map((r) => r.name)).toEqual(['D', 'B', 'C']);
  });
});

describe('aggregateBy 冤家榜（enemyBoard 放槍配對）', () => {
  function makeSession(partial: Partial<Session>): Session {
    return {
      id: 's1',
      name: '場',
      players: players.map((p) => ({ ...p })),
      settings: { ...settings },
      rules: { ...rules },
      rounds: [],
      createdAt: 0,
      ...partial,
    };
  }

  it('shotByMe / shotByThem / coPlayedRounds 正確，且自己不在榜上', () => {
    // 以 A(p1) 為視角：
    //  r1：p1 放槍贏 p2 → B(p2) 放槍給我 → shotByThem[B]+1
    //  r2：p1 放槍給 p3（p3 贏、p1 輸）→ 我放槍給 C(p3) → shotByMe[C]+1
    //  r3：p2 自摸 → 自摸局不列入配對
    const session = makeSession({
      rounds: [
        makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', selfDraw: false }),
        makeRound({ id: 'r2', winnerId: 'p3', loserId: 'p1', selfDraw: false }),
        makeRound({ id: 'r3', winnerId: 'p2', loserId: null, selfDraw: true }),
      ],
    });
    const stats = aggregatePlayerStats([session], 'A');
    const byName = Object.fromEntries(stats.enemyBoard.map((e) => [e.name, e]));

    expect(Object.keys(byName).sort()).toEqual(['B', 'C', 'D']); // 不含自己 A
    expect(byName.B).toMatchObject({ shotByMe: 0, shotByThem: 1, coPlayedRounds: 3 });
    expect(byName.C).toMatchObject({ shotByMe: 1, shotByThem: 0, coPlayedRounds: 3 });
    expect(byName.D).toMatchObject({ shotByMe: 0, shotByThem: 0, coPlayedRounds: 3 });
  });

  it('rosterId 對手：entry 帶對手 rosterId 供 UI 查頭像', () => {
    const session = makeSession({
      players: [
        { id: 'p1', name: 'A' },
        { id: 'p2', name: 'B', rosterId: 'roster-b' },
        { id: 'p3', name: 'C' },
        { id: 'p4', name: 'D' },
      ],
      rounds: [makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', selfDraw: false })],
    });
    const stats = aggregatePlayerStats([session], 'A');
    const b = stats.enemyBoard.find((e) => e.name === 'B');
    expect(b?.rosterId).toBe('roster-b');
    expect(b?.shotByThem).toBe(1);
  });

  it('跨場累計：同一對手多場的同場局數與放槍次數相加', () => {
    const sessions: Session[] = [
      makeSession({
        id: 's1',
        createdAt: 1,
        rounds: [
          makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', selfDraw: false }),
          makeRound({ id: 'r2', winnerId: 'p2', loserId: 'p1', selfDraw: false }),
        ],
      }),
      makeSession({
        id: 's2',
        createdAt: 2,
        rounds: [makeRound({ id: 'r3', winnerId: 'p1', loserId: 'p2', selfDraw: false })],
      }),
    ];
    const stats = aggregatePlayerStats(sessions, 'A');
    const b = stats.enemyBoard.find((e) => e.name === 'B');
    // 同場局數 = 2 + 1 = 3；我放槍給 B（r2）1 次；B 放槍給我（r1、r3）2 次。
    expect(b).toMatchObject({ coPlayedRounds: 3, shotByMe: 1, shotByThem: 2 });
  });
});

// v2.3 批次 2：流局排除率值分母 + 連莊金額歸戶
describe('v2.3 — 流局 / 連莊對統計的影響', () => {
  const dealerOnlyRules: SessionRules = {
    selfDrawBonusTai: 0, selfDrawDongAmount: 0, eyeTileEnabled: false, eyeTileTai: 0,
    dealerEnabled: true, dealerBaseTai: 1, dealerStreakTaiPerStreak: 2, dealerTaiScope: 'dealer',
  };

  function makeSession(partial: Partial<Session>): Session {
    return {
      id: 's1',
      name: '場',
      players: players.map((p) => ({ ...p })),
      settings: { ...settings },
      rules: { ...rules },
      rounds: [],
      createdAt: 0,
      ...partial,
    };
  }

  it('流局不計胡牌率 / 放槍率分母（totalRounds），也不計 wins / gunned', () => {
    const sessions: Session[] = [
      makeSession({
        rounds: [
          makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', selfDraw: false }),
          { id: 'r2', winnerId: '', loserId: null, tai: 0, selfDraw: false, createdAt: 0, drawn: true },
          makeRound({ id: 'r3', winnerId: 'p1', loserId: 'p2', selfDraw: false }),
          makeRound({ id: 'r4', winnerId: 'p2', loserId: 'p1', selfDraw: false }),
        ],
      }),
    ];
    const stats = aggregatePlayerStats(sessions, 'A'); // A = p1
    // 4 局但流局 1 局 → 分母 3
    expect(stats.totalRounds).toBe(3);
    expect(stats.totalWins).toBe(2); // r1、r3
    expect(stats.totalGunned).toBe(1); // r4 放槍
  });

  it('全流局場：totalRounds=0、無 wins/gunned、金額 0', () => {
    const sessions: Session[] = [
      makeSession({
        rounds: [
          { id: 'r1', winnerId: '', loserId: null, tai: 0, selfDraw: false, createdAt: 0, drawn: true },
          { id: 'r2', winnerId: '', loserId: null, tai: 0, selfDraw: false, createdAt: 0, drawn: true },
        ],
      }),
    ];
    const stats = aggregatePlayerStats(sessions, 'A');
    expect(stats.totalRounds).toBe(0);
    expect(stats.totalWins).toBe(0);
    expect(stats.totalGunned).toBe(0);
    expect(stats.totalAmount).toBe(0);
  });

  it('連莊場：歸戶金額含連莊加台（aggregateBy 內部推導 dealerCtx）', () => {
    // dealerStartSeat p1、p1 自摸 2 台：莊台 1 → 3 台，單注 250，p1 收 750（無莊台則 600）。
    const sessions: Session[] = [
      makeSession({
        rules: dealerOnlyRules,
        dealerStartSeat: 'p1',
        rounds: [makeRound({ id: 'r1', winnerId: 'p1', loserId: null, tai: 2, selfDraw: true })],
      }),
    ];
    const stats = aggregatePlayerStats(sessions, 'A');
    expect(stats.totalAmount).toBe(750);
  });

  it('走勢圖含流局：流局點與前一點持平（無金額變化）', () => {
    const rounds: Round[] = [
      makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 0, selfDraw: false }), // p1 +100
      { id: 'r2', winnerId: '', loserId: null, tai: 0, selfDraw: false, createdAt: 0, drawn: true },
    ];
    const tl = buildCumulativeTimeline(rounds, players, settings, rules);
    expect(tl).toHaveLength(3);
    // 第 1 點 p1 +100；第 2 點（流局）維持 +100
    expect(tl[1].cumulative.p1).toBe(100);
    expect(tl[2].cumulative.p1).toBe(100);
  });

  it('deriveDealerContexts 對齊 rounds：可直接餵給 buildCumulativeTimeline', () => {
    const s = makeSession({
      rules: dealerOnlyRules,
      dealerStartSeat: 'p1',
      rounds: [makeRound({ id: 'r1', winnerId: 'p1', loserId: null, tai: 2, selfDraw: true })],
    });
    const ctxs = deriveDealerContexts(s);
    const tl = buildCumulativeTimeline(s.rounds, s.players, s.settings, s.rules, ctxs);
    expect(tl[1].cumulative.p1).toBe(750);
  });
});
