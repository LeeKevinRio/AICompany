import { describe, it, expect } from 'vitest';
import {
  calcDong,
  calcUnitAmount,
  effectiveTai,
  scoreRound,
  scoreRoundOutcome,
  scoreSession,
  settleSession,
} from './scoring';
import type { Player, Round, SessionRules, Settings } from '../types';

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

describe('v2.1 規則 — 自摸加台（selfDrawBonusTai）', () => {
  const rules: SessionRules = { selfDrawBonusTai: 1, selfDrawDongAmount: 0 };

  it('effectiveTai：自摸時加台，放槍不加', () => {
    expect(effectiveTai(makeRound({ tai: 2, selfDraw: true, loserId: null }), rules)).toBe(3);
    expect(effectiveTai(makeRound({ tai: 2, selfDraw: false }), rules)).toBe(2);
  });

  it('自摸 2 台 + 加 1 台：effectiveTai=3，amount=250，仍零和', () => {
    const round = makeRound({ winnerId: 'p1', loserId: null, tai: 2, selfDraw: true });
    const d = scoreRound(round, players, settings, rules);
    expect(d.p1).toBe(750); // 250 × 3
    expect(d.p2).toBe(-250);
    expect(d.p3).toBe(-250);
    expect(d.p4).toBe(-250);
    expect(d.p1 + d.p2 + d.p3 + d.p4).toBe(0);
  });

  it('放槍不受自摸加台影響：2 台仍 200', () => {
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', tai: 2, selfDraw: false });
    const d = scoreRound(round, players, settings, rules);
    expect(d.p1).toBe(200);
    expect(d.p2).toBe(-200);
    expect(d.p1 + d.p2 + d.p3 + d.p4).toBe(0);
  });

  it('未傳 rules：行為與舊版完全一致（不加台）', () => {
    const round = makeRound({ winnerId: 'p1', loserId: null, tai: 2, selfDraw: true });
    const d = scoreRound(round, players, settings);
    expect(d.p1).toBe(600); // 200 × 3，未加台
  });
});

describe('v2.1 規則 — 東錢 / 公基金（selfDrawDongAmount）', () => {
  it('calcDong：自摸收、放槍不收、關閉為 0', () => {
    const on: SessionRules = { selfDrawBonusTai: 0, selfDrawDongAmount: 100 };
    expect(calcDong(makeRound({ selfDraw: true, loserId: null }), on)).toBe(100);
    expect(calcDong(makeRound({ selfDraw: false }), on)).toBe(0);
    const off: SessionRules = { selfDrawBonusTai: 0, selfDrawDongAmount: 0 };
    expect(calcDong(makeRound({ selfDraw: true, loserId: null }), off)).toBe(0);
  });

  it('東錢是底台之外的獨立線：scoreRound 的四人 deltas 仍零和', () => {
    const rules: SessionRules = { selfDrawBonusTai: 1, selfDrawDongAmount: 100 };
    const round = makeRound({ winnerId: 'p1', loserId: null, tai: 2, selfDraw: true });
    const { deltas, dong, dongPayerId } = scoreRoundOutcome(round, players, settings, rules);
    // 底/台/自摸加台四人加總恆為 0（東錢不破壞零和）
    expect(deltas.p1 + deltas.p2 + deltas.p3 + deltas.p4).toBe(0);
    expect(dong).toBe(100);
    expect(dongPayerId).toBe('p1');
  });

  it('CEO 範例：底100 台50 自摸+1台 東錢100，輸入 2 台自摸', () => {
    // 自摸者底台收益 +750（250×3），三家各付 250；東錢 100 進公基金。
    const rules: SessionRules = { selfDrawBonusTai: 1, selfDrawDongAmount: 100 };
    const round = makeRound({ winnerId: 'p1', loserId: null, tai: 2, selfDraw: true });
    const { net, kitty } = settleSession([round], players, settings, rules);

    // 自摸者淨額 = +750（底台）− 100（付出的東錢）= +650
    expect(net.p1).toBe(650);
    // 三家各付底台 250（東錢不分攤給三家）
    expect(net.p2).toBe(-250);
    expect(net.p3).toBe(-250);
    expect(net.p4).toBe(-250);
    // 公基金 +100
    expect(kitty).toBe(100);
    // 錢沒有憑空消失：四人淨額總和 = −公基金
    expect(net.p1 + net.p2 + net.p3 + net.p4).toBe(-kitty);
  });

  it('多次自摸：公基金累加，淨額總和恆等於 −kitty', () => {
    const rules: SessionRules = { selfDrawBonusTai: 1, selfDrawDongAmount: 100 };
    const rounds: Round[] = [
      makeRound({ id: 'r1', winnerId: 'p1', loserId: null, tai: 0, selfDraw: true }),
      makeRound({ id: 'r2', winnerId: 'p2', loserId: null, tai: 3, selfDraw: true }),
      makeRound({ id: 'r3', winnerId: 'p3', loserId: 'p4', tai: 2, selfDraw: false }), // 放槍不收東錢
    ];
    const { net, zeroSum, kitty } = settleSession(rounds, players, settings, rules);
    expect(kitty).toBe(200); // 兩次自摸各 100
    // 底台零和：四人加總為 0
    expect(zeroSum.p1 + zeroSum.p2 + zeroSum.p3 + zeroSum.p4).toBe(0);
    // 淨額總和 = −kitty
    expect(net.p1 + net.p2 + net.p3 + net.p4).toBe(-200);
  });

  it('放槍局不收東錢，公基金為 0', () => {
    const rules: SessionRules = { selfDrawBonusTai: 1, selfDrawDongAmount: 100 };
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', tai: 2, selfDraw: false });
    const { kitty, net } = settleSession([round], players, settings, rules);
    expect(kitty).toBe(0);
    expect(net.p1 + net.p2 + net.p3 + net.p4).toBe(0);
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
