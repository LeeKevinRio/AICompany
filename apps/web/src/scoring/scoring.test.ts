import { describe, it, expect } from 'vitest';
import {
  assertValidRound,
  calcDong,
  calcEyeTileTai,
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
  const rules: SessionRules = { selfDrawBonusTai: 1, selfDrawDongAmount: 0, eyeTileEnabled: false, eyeTileTai: 0, dealerEnabled: false, dealerBaseTai: 0, dealerStreakTaiPerStreak: 0, dealerTaiScope: 'dealer' };

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
    const on: SessionRules = { selfDrawBonusTai: 0, selfDrawDongAmount: 100, eyeTileEnabled: false, eyeTileTai: 0, dealerEnabled: false, dealerBaseTai: 0, dealerStreakTaiPerStreak: 0, dealerTaiScope: 'dealer' };
    expect(calcDong(makeRound({ selfDraw: true, loserId: null }), on)).toBe(100);
    expect(calcDong(makeRound({ selfDraw: false }), on)).toBe(0);
    const off: SessionRules = { selfDrawBonusTai: 0, selfDrawDongAmount: 0, eyeTileEnabled: false, eyeTileTai: 0, dealerEnabled: false, dealerBaseTai: 0, dealerStreakTaiPerStreak: 0, dealerTaiScope: 'dealer' };
    expect(calcDong(makeRound({ selfDraw: true, loserId: null }), off)).toBe(0);
  });

  it('東錢是底台之外的獨立線：scoreRound 的四人 deltas 仍零和', () => {
    const rules: SessionRules = { selfDrawBonusTai: 1, selfDrawDongAmount: 100, eyeTileEnabled: false, eyeTileTai: 0, dealerEnabled: false, dealerBaseTai: 0, dealerStreakTaiPerStreak: 0, dealerTaiScope: 'dealer' };
    const round = makeRound({ winnerId: 'p1', loserId: null, tai: 2, selfDraw: true });
    const { deltas, dong, dongPayerId } = scoreRoundOutcome(round, players, settings, rules);
    // 底/台/自摸加台四人加總恆為 0（東錢不破壞零和）
    expect(deltas.p1 + deltas.p2 + deltas.p3 + deltas.p4).toBe(0);
    expect(dong).toBe(100);
    expect(dongPayerId).toBe('p1');
  });

  it('CEO 範例：底100 台50 自摸+1台 東錢100，輸入 2 台自摸', () => {
    // 自摸者底台收益 +750（250×3），三家各付 250；東錢 100 進公基金。
    const rules: SessionRules = { selfDrawBonusTai: 1, selfDrawDongAmount: 100, eyeTileEnabled: false, eyeTileTai: 0, dealerEnabled: false, dealerBaseTai: 0, dealerStreakTaiPerStreak: 0, dealerTaiScope: 'dealer' };
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
    const rules: SessionRules = { selfDrawBonusTai: 1, selfDrawDongAmount: 100, eyeTileEnabled: false, eyeTileTai: 0, dealerEnabled: false, dealerBaseTai: 0, dealerStreakTaiPerStreak: 0, dealerTaiScope: 'dealer' };
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
    const rules: SessionRules = { selfDrawBonusTai: 1, selfDrawDongAmount: 100, eyeTileEnabled: false, eyeTileTai: 0, dealerEnabled: false, dealerBaseTai: 0, dealerStreakTaiPerStreak: 0, dealerTaiScope: 'dealer' };
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', tai: 2, selfDraw: false });
    const { kitty, net } = settleSession([round], players, settings, rules);
    expect(kitty).toBe(0);
    expect(net.p1 + net.p2 + net.p3 + net.p4).toBe(0);
  });
});

describe('v2.2 規則 — 眼牌（eyeTileEnabled / eyeTileTai）', () => {
  // 眼牌開、加 1 台；自摸加台關（隔離眼牌效果）。
  const rules: SessionRules = {
    selfDrawBonusTai: 0,
    selfDrawDongAmount: 0,
    eyeTileEnabled: true,
    eyeTileTai: 1,
    dealerEnabled: false,
    dealerBaseTai: 0,
    dealerStreakTaiPerStreak: 0,
    dealerTaiScope: 'dealer',
  };

  it('calcEyeTileTai：啟用+標記才加台；未啟用/未標記/台數<=0 皆 0', () => {
    expect(calcEyeTileTai(makeRound({ eyeTile: true }), rules)).toBe(1);
    // 未標記眼牌（含舊資料 undefined）→ 0
    expect(calcEyeTileTai(makeRound({ eyeTile: false }), rules)).toBe(0);
    expect(calcEyeTileTai(makeRound({}), rules)).toBe(0);
    // 該場未啟用眼牌 → 即使標記也 0
    const off: SessionRules = { ...rules, eyeTileEnabled: false };
    expect(calcEyeTileTai(makeRound({ eyeTile: true }), off)).toBe(0);
  });

  it('calcEyeTileTai 邊界：啟用眼牌但 eyeTileTai=0 → 不加台（含 effectiveTai）', () => {
    const zeroTai: SessionRules = { ...rules, eyeTileEnabled: true, eyeTileTai: 0 };
    expect(calcEyeTileTai(makeRound({ eyeTile: true }), zeroTai)).toBe(0);
    // effectiveTai 疊加後也不受影響（放槍 2 台維持 2 台）
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', tai: 2, selfDraw: false, eyeTile: true });
    expect(effectiveTai(round, zeroTai)).toBe(2);
  });

  it('情境一 眼牌自摸：2 台 +眼 1 台 = 3 台，贏家收 3 倍，四人零和', () => {
    const round = makeRound({ winnerId: 'p1', loserId: null, tai: 2, selfDraw: true, eyeTile: true });
    expect(effectiveTai(round, rules)).toBe(3);
    const d = scoreRound(round, players, settings, rules);
    expect(d.p1).toBe(750); // 250 × 3
    expect(d.p2).toBe(-250);
    expect(d.p3).toBe(-250);
    expect(d.p4).toBe(-250);
    expect(d.p1 + d.p2 + d.p3 + d.p4).toBe(0);
  });

  it('情境二 眼牌放槍：2 台 +眼 1 台 = 3 台（放槍也算），四人零和', () => {
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', tai: 2, selfDraw: false, eyeTile: true });
    expect(effectiveTai(round, rules)).toBe(3);
    const d = scoreRound(round, players, settings, rules);
    expect(d.p1).toBe(250);
    expect(d.p2).toBe(-250);
    expect(d.p3).toBe(0);
    expect(d.p4).toBe(0);
    expect(d.p1 + d.p2 + d.p3 + d.p4).toBe(0);
  });

  it('情境三 未啟用眼牌：即使標記 eyeTile 也不加台（放槍 2 台仍 200）', () => {
    const off: SessionRules = { ...rules, eyeTileEnabled: false };
    const round = makeRound({ winnerId: 'p1', loserId: 'p2', tai: 2, selfDraw: false, eyeTile: true });
    expect(effectiveTai(round, off)).toBe(2);
    const d = scoreRound(round, players, settings, off);
    expect(d.p1).toBe(200);
    expect(d.p2).toBe(-200);
    expect(d.p1 + d.p2 + d.p3 + d.p4).toBe(0);
  });

  it('情境四 舊資料（round 無 eyeTile）：啟用眼牌也不加台，行為與今天一致', () => {
    const round = makeRound({ winnerId: 'p1', loserId: null, tai: 2, selfDraw: true });
    expect(effectiveTai(round, rules)).toBe(2);
    const d = scoreRound(round, players, settings, rules);
    expect(d.p1).toBe(600); // 200 × 3，未加眼牌
    expect(d.p1 + d.p2 + d.p3 + d.p4).toBe(0);
  });

  it('自摸加台與眼牌可疊加：自摸 +1 台 + 眼 +1 台，四人零和且 dong 不破壞零和', () => {
    const both: SessionRules = {
      selfDrawBonusTai: 1,
      selfDrawDongAmount: 100,
      eyeTileEnabled: true,
      eyeTileTai: 1,
      dealerEnabled: false,
      dealerBaseTai: 0,
      dealerStreakTaiPerStreak: 0,
      dealerTaiScope: 'dealer',
    };
    // 2 台 → +自摸 1 +眼 1 = 4 台，amount = 100 + 4×50 = 300
    const round = makeRound({ winnerId: 'p1', loserId: null, tai: 2, selfDraw: true, eyeTile: true });
    expect(effectiveTai(round, both)).toBe(4);
    const { deltas, dong } = scoreRoundOutcome(round, players, settings, both);
    expect(deltas.p1).toBe(900); // 300 × 3
    expect(deltas.p1 + deltas.p2 + deltas.p3 + deltas.p4).toBe(0);
    expect(dong).toBe(100);
    // 含公基金的整場驗算：四人淨額總和 = −kitty
    const { net, kitty } = settleSession([round], players, settings, both);
    expect(net.p1 + net.p2 + net.p3 + net.p4).toBe(-kitty);
  });

  it('settleSession 全放槍眼牌局：無自摸故 kitty=0，整場嚴格零和', () => {
    // 三局皆放槍且標記眼牌（+1 台）；放槍不觸發 dong，故公基金應為 0。
    const rounds: Round[] = [
      makeRound({ id: 'r1', winnerId: 'p1', loserId: 'p2', tai: 2, selfDraw: false, eyeTile: true }), // 3 台
      makeRound({ id: 'r2', winnerId: 'p3', loserId: 'p4', tai: 0, selfDraw: false, eyeTile: true }), // 1 台
      makeRound({ id: 'r3', winnerId: 'p2', loserId: 'p1', tai: 5, selfDraw: false, eyeTile: true }), // 6 台
    ];
    const { net, zeroSum, kitty } = settleSession(rounds, players, settings, rules);
    // 無自摸 → 無東錢 → kitty 恆為 0
    expect(kitty).toBe(0);
    // kitty=0 時 net 與 zeroSum 完全一致，且四人嚴格零和
    expect(net.p1 + net.p2 + net.p3 + net.p4).toBe(0);
    expect(zeroSum.p1 + zeroSum.p2 + zeroSum.p3 + zeroSum.p4).toBe(0);
    expect(net).toEqual(zeroSum);
    // 逐項驗算：r1 p1 收 250 / p2 付 250；r2 p3 收 150 / p4 付 150；r3 p2 收 400 / p1 付 400
    expect(net.p1).toBe(250 - 400); // -150
    expect(net.p2).toBe(-250 + 400); // 150
    expect(net.p3).toBe(150); // 0 台 +眼 1 台 = 1 台 → 100+50
    expect(net.p4).toBe(-150);
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

// v2.3 批次 2：流局 + 連莊加台
describe('v2.3 — 流局（drawn）', () => {
  it('scoreRound 流局：四人全 0', () => {
    const r = makeRound({ winnerId: '', loserId: null, tai: 0, selfDraw: false, drawn: true });
    const d = scoreRound(r, players, settings);
    expect(d).toEqual({ p1: 0, p2: 0, p3: 0, p4: 0 });
  });

  it('scoreRoundOutcome 流局：deltas 全 0、dong 0（非自摸天然不觸發東錢）', () => {
    const r = makeRound({ winnerId: '', loserId: null, tai: 0, selfDraw: false, drawn: true });
    const { deltas, dong, dongPayerId } = scoreRoundOutcome(r, players, settings, {
      selfDrawBonusTai: 0, selfDrawDongAmount: 100, eyeTileEnabled: false, eyeTileTai: 0,
      dealerEnabled: false, dealerBaseTai: 0, dealerStreakTaiPerStreak: 0, dealerTaiScope: 'dealer',
    });
    expect(deltas.p1 + deltas.p2 + deltas.p3 + deltas.p4).toBe(0);
    expect(dong).toBe(0);
    expect(dongPayerId).toBeNull();
  });

  it('assertValidRound 流局：winnerId 必須空字串、loserId 必須 null', () => {
    expect(() => assertValidRound(
      makeRound({ winnerId: 'p1', loserId: null, drawn: true }), players,
    )).toThrow();
    expect(() => assertValidRound(
      makeRound({ winnerId: '', loserId: 'p2', selfDraw: false, drawn: true }), players,
    )).toThrow();
    // 合法流局不 throw
    expect(() => assertValidRound(
      makeRound({ winnerId: '', loserId: null, selfDraw: false, drawn: true }), players,
    )).not.toThrow();
  });

  it('assertValidRound 流局防呆（批次 3）：selfDraw 必須為 false', () => {
    // 流局無人胡牌，selfDraw=true 會讓 calcDong 誤算東錢金流 → 明確擋下。
    expect(() => assertValidRound(
      makeRound({ winnerId: '', loserId: null, selfDraw: true, drawn: true }), players,
    )).toThrow();
  });
});

describe('v2.3 — 連莊加台（scope=dealer，只牽涉莊家的支付）', () => {
  // 做莊 1 台、連 N 拉 N = 2N 台；隔離其他規則（自摸加台 / 眼牌 / 東錢皆關）。
  const dRules: SessionRules = {
    selfDrawBonusTai: 0, selfDrawDongAmount: 0, eyeTileEnabled: false, eyeTileTai: 0,
    dealerEnabled: true, dealerBaseTai: 1, dealerStreakTaiPerStreak: 2, dealerTaiScope: 'dealer',
  };

  it('自摸且莊家=贏家：所有支付都加莊 1 台，四人零和', () => {
    // 2 台 + 莊 1 台 = 3 台，單注 = 100+3×50 = 250
    const r = makeRound({ winnerId: 'p1', loserId: null, tai: 2, selfDraw: true });
    const d = scoreRound(r, players, settings, dRules, { dealerId: 'p1', streak: 0 });
    expect(d.p1).toBe(750); // 250 × 3
    expect(d.p2).toBe(-250);
    expect(d.p3).toBe(-250);
    expect(d.p4).toBe(-250);
    expect(d.p1 + d.p2 + d.p3 + d.p4).toBe(0);
  });

  it('自摸且莊家=輸家之一：只有莊家那筆加台，其餘正常，仍零和', () => {
    // 贏家 p2、莊家 p1。p1 付 3 台=250，p3/p4 付 2 台=200
    const r = makeRound({ winnerId: 'p2', loserId: null, tai: 2, selfDraw: true });
    const d = scoreRound(r, players, settings, dRules, { dealerId: 'p1', streak: 0 });
    expect(d.p1).toBe(-250);
    expect(d.p3).toBe(-200);
    expect(d.p4).toBe(-200);
    expect(d.p2).toBe(650); // 250+200+200
    expect(d.p1 + d.p2 + d.p3 + d.p4).toBe(0);
  });

  it('放槍：贏家為莊 → 加台；莊家未牽涉 → 不加台', () => {
    // 贏家 p1=莊、放槍 p2：加莊台，3 台=250
    const involved = scoreRound(
      makeRound({ winnerId: 'p1', loserId: 'p2', tai: 2, selfDraw: false }),
      players, settings, dRules, { dealerId: 'p1', streak: 0 },
    );
    expect(involved.p1).toBe(250);
    expect(involved.p2).toBe(-250);
    // 贏家 p3、放槍 p4，莊家 p1 未牽涉 → 不加台，2 台=200
    const notInvolved = scoreRound(
      makeRound({ winnerId: 'p3', loserId: 'p4', tai: 2, selfDraw: false }),
      players, settings, dRules, { dealerId: 'p1', streak: 0 },
    );
    expect(notInvolved.p3).toBe(200);
    expect(notInvolved.p4).toBe(-200);
  });

  it('連莊疊台：streak=1 → 莊台 = 1 + 2×1 = 3 台', () => {
    // 0 台 + 莊 3 台 = 3 台，單注 250；自摸莊家=贏家
    const r = makeRound({ winnerId: 'p1', loserId: null, tai: 0, selfDraw: true });
    const d = scoreRound(r, players, settings, dRules, { dealerId: 'p1', streak: 1 });
    expect(d.p1).toBe(750);
  });

  it('未傳 dealerCtx：無連莊加台（零回歸，與舊版一致）', () => {
    const r = makeRound({ winnerId: 'p1', loserId: null, tai: 2, selfDraw: true });
    const d = scoreRound(r, players, settings, dRules);
    expect(d.p1).toBe(600); // 2 台 = 200 × 3，無莊台
  });

  it('dealerEnabled 關：即使傳 dealerCtx 也不加台', () => {
    const offRules: SessionRules = { ...dRules, dealerEnabled: false };
    const r = makeRound({ winnerId: 'p1', loserId: null, tai: 2, selfDraw: true });
    const d = scoreRound(r, players, settings, offRules, { dealerId: 'p1', streak: 3 });
    expect(d.p1).toBe(600);
  });

  it('scope=table：莊家未牽涉的支付也加台（全桌墊高）', () => {
    const tableRules: SessionRules = { ...dRules, dealerTaiScope: 'table' };
    // 贏家 p3、放槍 p4、莊家 p1 未牽涉，但 table scope → 仍加莊 1 台，3 台=250
    const d = scoreRound(
      makeRound({ winnerId: 'p3', loserId: 'p4', tai: 2, selfDraw: false }),
      players, settings, tableRules, { dealerId: 'p1', streak: 0 },
    );
    expect(d.p3).toBe(250);
    expect(d.p4).toBe(-250);
  });

  it('連莊加台維持整場零和（含流局混入）', () => {
    const rounds: Round[] = [
      makeRound({ id: 'r1', winnerId: 'p1', loserId: null, tai: 2, selfDraw: true }),
      makeRound({ id: 'r2', winnerId: '', loserId: null, tai: 0, selfDraw: false, drawn: true }),
      makeRound({ id: 'r3', winnerId: 'p2', loserId: 'p1', tai: 3, selfDraw: false }),
    ];
    const ctxs = [
      { dealerId: 'p1', streak: 0 },
      { dealerId: 'p1', streak: 1 },
      { dealerId: 'p1', streak: 2 },
    ];
    const t = scoreSession(rounds, players, settings, dRules, ctxs);
    expect(t.p1 + t.p2 + t.p3 + t.p4).toBe(0);
    const { net, kitty } = settleSession(rounds, players, settings, dRules, ctxs);
    // 加 kitty 歸零式，避免 kitty=0 時 -kitty 產生 -0 與 Object.is 不符。
    expect(net.p1 + net.p2 + net.p3 + net.p4 + kitty).toBe(0);
  });
});
