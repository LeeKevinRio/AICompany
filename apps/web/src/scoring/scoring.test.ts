import { describe, it, expect } from 'vitest';
import { calcUnitAmount, scoreRound, scoreSession } from './scoring';
import type { Player, Round, Settings } from '../types';

const players: Player[] = [
  { id: 'p1', name: 'A' },
  { id: 'p2', name: 'B' },
  { id: 'p3', name: 'C' },
  { id: 'p4', name: 'D' },
];

// 底 100、台 50
const settings: Settings = { base: 100, tai: 50 };

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

describe('calcUnitAmount', () => {
  it('底 + 台數 × 台', () => {
    expect(calcUnitAmount(settings, 0)).toBe(100); // 100 + 0×50
    expect(calcUnitAmount(settings, 3)).toBe(250); // 100 + 3×50
  });
});

describe('scoreRound — 放槍', () => {
  it('3 台放槍：只有放槍者付，贏家收，另兩家 0', () => {
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', tai: 3, selfDraw: false });
    const d = scoreRound(round, players, settings);
    expect(d.p1).toBe(250); // 收 100+3×50
    expect(d.p2).toBe(-250); // 放槍者付
    expect(d.p3).toBe(0);
    expect(d.p4).toBe(0);
    // 加總為 0
    expect(d.p1 + d.p2 + d.p3 + d.p4).toBe(0);
  });
});

describe('scoreRound — 自摸', () => {
  it('3 台自摸：其他三家各付，贏家收 3 倍', () => {
    const round = makeRound({ winnerId: 'p1', loserId: null, tai: 3, selfDraw: true });
    const d = scoreRound(round, players, settings);
    expect(d.p1).toBe(750); // 250 × 3
    expect(d.p2).toBe(-250);
    expect(d.p3).toBe(-250);
    expect(d.p4).toBe(-250);
    expect(d.p1 + d.p2 + d.p3 + d.p4).toBe(0);
  });
});

describe('scoreRound — edge cases 與驗證', () => {
  it('tai=0 的自摸：每家各付 base，贏家收 3 倍', () => {
    const round = makeRound({ winnerId: 'p1', loserId: null, tai: 0, selfDraw: true });
    const d = scoreRound(round, players, settings);
    expect(d.p1).toBe(300); // 100 × 3
    expect(d.p2).toBe(-100);
    expect(d.p3).toBe(-100);
    expect(d.p4).toBe(-100);
    expect(d.p1 + d.p2 + d.p3 + d.p4).toBe(0);
  });

  it('base=0 且 tai=0：金額全為 0', () => {
    const zeroSettings: Settings = { base: 0, tai: 0 };
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', tai: 5, selfDraw: false });
    const d = scoreRound(round, players, zeroSettings);
    expect(d.p1).toBe(0);
    expect(d.p2).toBe(0);
    expect(d.p3).toBe(0);
    expect(d.p4).toBe(0);
  });

  it('放槍 loserId 缺失應 throw', () => {
    const round = makeRound({ winnerId: 'p1', loserId: null, selfDraw: false });
    expect(() => scoreRound(round, players, settings)).toThrow();
  });

  it('放槍者不在 players 內應 throw', () => {
    const round = makeRound({ winnerId: 'p1', loserId: 'pX', selfDraw: false });
    expect(() => scoreRound(round, players, settings)).toThrow();
  });

  it('放槍者等於贏家應 throw', () => {
    const round = makeRound({ winnerId: 'p1', loserId: 'p1', selfDraw: false });
    expect(() => scoreRound(round, players, settings)).toThrow();
  });

  it('winner 不在 players 內應 throw', () => {
    const round = makeRound({ winnerId: 'pX', loserId: 'p2', selfDraw: false });
    expect(() => scoreRound(round, players, settings)).toThrow();
  });

  it('自摸時 loserId 不為 null 應 throw（不可靜默忽略）', () => {
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', selfDraw: true });
    expect(() => scoreRound(round, players, settings)).toThrow();
  });

  it('settings 含負數應 throw', () => {
    const badSettings: Settings = { base: -100, tai: 50 };
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', selfDraw: false });
    expect(() => scoreRound(round, players, badSettings)).toThrow();
  });

  it('settings 含小數應 throw', () => {
    const badSettings: Settings = { base: 100.5, tai: 50 };
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', selfDraw: false });
    expect(() => scoreRound(round, players, badSettings)).toThrow();
  });

  it('台數為負應 throw', () => {
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', tai: -1, selfDraw: false });
    expect(() => scoreRound(round, players, settings)).toThrow();
  });
});

describe('scoreSession — 多局累計', () => {
  it('放槍 + 自摸 累加', () => {
    const rounds: Round[] = [
      makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 0, selfDraw: false }), // p1 +100, p2 -100
      makeRound({ id: 'r2', winnerId: 'p3', loserId: null, tai: 0, selfDraw: true }), // p3 +300, 其他 -100
    ];
    const t = scoreSession(rounds, players, settings);
    expect(t.p1).toBe(100 - 100); // 0
    expect(t.p2).toBe(-100 - 100); // -200
    expect(t.p3).toBe(0 + 300); // 300
    expect(t.p4).toBe(0 - 100); // -100
    expect(t.p1 + t.p2 + t.p3 + t.p4).toBe(0);
  });
});
