import { describe, it, expect } from 'vitest';
import {
  buildCumulativeTimeline,
  calcSessionHighlights,
  aggregatePlayerStats,
  aggregateByRosterId,
  collectPlayerNames,
  formatSigned,
} from './timeline';
import type { Player, Round, Session, SessionRules, Settings } from '../types';
import { DEFAULT_SESSION_RULES } from '../types';

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
