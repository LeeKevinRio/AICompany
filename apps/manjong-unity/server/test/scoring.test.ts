import { describe, expect, it } from 'vitest';
import { scoreFlowerWin, scoreWin, settle, type WinInput } from '../src/engine/scoring.js';
import { meld, names, tiles } from './helpers.js';

/** Non-dealer in the south seat during the east round, winning by discard unless overridden. */
function score(concealed: string, winTile: string, extra: Partial<WinInput> = {}) {
  const result = scoreWin({
    concealed: tiles(concealed),
    melds: [],
    flowers: [],
    winTile,
    selfDraw: false,
    seatWind: 'S',
    roundWind: 'E',
    ...extra,
  });
  if (!result) throw new Error('expected a winning hand');
  return { total: result.total, names: names(result.items) };
}

describe('tai table', () => {
  it('平胡 + 門清', () => {
    const r = score('123m 456m 234s 567s 88s 234p', '4p');
    expect(r.names.sort()).toEqual(['平胡', '門清'].sort());
    expect(r.total).toBe(3);
  });

  it('平胡 requires a two-sided wait (edge wait is 獨聽 instead)', () => {
    const r = score('123m 456m 234s 567s 88s 789p', '7p');
    expect(r.names).not.toContain('平胡');
    expect(r.names).toContain('獨聽');
  });

  it('門清自摸 replaces 門清 + 自摸, 獨聽 for a closed wait', () => {
    const r = score('123m 456m 234s 567s 88s 234p', '3p', { selfDraw: true });
    expect(r.names.sort()).toEqual(['獨聽', '門清自摸'].sort());
    expect(r.total).toBe(4);
  });

  it('自摸 alone when the hand is open', () => {
    const r = score('123m 456m 234s 88s 234p', '3p', { selfDraw: true, melds: [meld('chi', '567s', 0)] });
    expect(r.names).toContain('自摸');
    expect(r.names).not.toContain('門清自摸');
    expect(r.names).not.toContain('門清');
  });

  it('碰碰胡 + 三暗刻; a triplet completed by a discard is not concealed', () => {
    const r = score('111m 999p N N N 22s 333s', '3s', { melds: [meld('pon', '555s')] });
    expect(r.names.sort()).toEqual(['三暗刻', '碰碰胡'].sort());
    expect(r.total).toBe(6);
  });

  it('四暗刻 when the same hand is self-drawn', () => {
    const r = score('111m 999p N N N 22s 333s', '3s', { melds: [meld('pon', '555s')], selfDraw: true });
    expect(r.names.sort()).toEqual(['四暗刻', '碰碰胡', '自摸'].sort());
    expect(r.total).toBe(10);
  });

  it('五暗刻 replaces 三暗刻 / 四暗刻', () => {
    const r = score('111m 999p N N N 555s 22s 333s', '3s', { selfDraw: true });
    expect(r.names.sort()).toEqual(['五暗刻', '碰碰胡', '門清自摸'].sort());
    expect(r.total).toBe(15);
  });

  it('暗槓 counts as a concealed triplet and keeps 門清', () => {
    const r = score('111m 999p 22s 333s', '3s', {
      melds: [meld('ankan', '5555s', 0), meld('ankan', 'N N N N', 0)],
      selfDraw: true,
    });
    expect(r.names).toContain('五暗刻');
    expect(r.names).toContain('門清自摸');
  });

  it('混一色', () => {
    const r = score('123m 345m 678m 999m N N N 55m', 'N');
    expect(r.names).toContain('混一色');
    expect(r.names).toContain('門清');
  });

  it('清一色', () => {
    const r = score('112233445566789m 99m', '7m');
    expect(r.names.sort()).toEqual(['清一色', '門清'].sort());
    expect(r.total).toBe(9);
  });

  it('大三元 replaces dragon triplets and 小三元, and stacks with 三暗刻', () => {
    const r = score('RD RD RD GD GD GD WD WD WD 123m 456p 7s 7s', '7s');
    expect(r.names.sort()).toEqual(['三暗刻', '大三元', '獨聽', '門清'].sort());
    expect(r.total).toBe(12);
  });

  it('小三元 replaces the two dragon triplets', () => {
    const r = score('RD RD RD GD GD GD WD WD 123m 456p 789s', '9s');
    expect(r.names).toContain('小三元');
    expect(r.names).not.toContain('紅中');
    expect(r.names).not.toContain('青發');
    expect(r.total).toBe(5);
  });

  it('single dragon triplets each score 1', () => {
    const r = score('RD RD RD GD GD GD 123m 456p 789s 11m', '9s');
    expect(r.names).toContain('紅中');
    expect(r.names).toContain('青發');
  });

  it('大四喜 replaces wind triplets', () => {
    const r = score('E E E S S S W W W N N N 234p 1m 1m', '1m');
    expect(r.names.sort()).toEqual(['四暗刻', '大四喜', '獨聽', '門清'].sort());
    expect(r.total).toBe(23);
  });

  it('小四喜 replaces 圈風 / 門風', () => {
    const r = score('E E E S S S W W W N N 123m 456m', '6m');
    expect(r.names.sort()).toEqual(['三暗刻', '小四喜', '混一色', '門清'].sort());
    expect(r.total).toBe(15);
  });

  it('圈風 and 門風 both score for the dealer in the east round', () => {
    const r = score('E E E 123m 456p 789s 234s 11m', '1m', { seatWind: 'E' });
    expect(r.names).toContain('圈風刻');
    expect(r.names).toContain('門風刻');
  });

  it('字一色 replaces 混一色', () => {
    const r = score('E E E S S S RD RD RD GD GD GD WD WD WD N N', 'N');
    expect(r.names).toContain('字一色');
    expect(r.names).not.toContain('混一色');
  });

  it('嚦咕嚦咕 does not add 門清', () => {
    const ron = score('11m 22m 33m 55p 66p 77s 88s E E E', 'E');
    expect(ron.names).toEqual(['嚦咕嚦咕']);
    const tsumo = score('11m 22m 33m 55p 66p 77s 88s E E E', 'E', { selfDraw: true });
    expect(tsumo.names.sort()).toEqual(['嚦咕嚦咕', '自摸'].sort());
    expect(tsumo.total).toBe(9);
  });

  it('全求人 does not add 獨聽', () => {
    const r = score('N N', 'N', {
      melds: [meld('chi', '123m'), meld('chi', '456p'), meld('pon', '777s'), meld('pon', '999p'), meld('chi', '345s')],
    });
    expect(r.names).toEqual(['全求人']);
    expect(r.total).toBe(2);
  });

  it('picks the decomposition with the most tai', () => {
    const r = score('111m 222m 333m 456p 789s 55s', '3m', { selfDraw: true });
    expect(r.names).toContain('三暗刻');
  });

  it('正花 and 花槓', () => {
    const base = '123m 456m 234s 567s 88s 234p';
    const seat = score(base, '4p', { flowers: ['F2', 'F6', 'F1'] });
    expect(seat.names).toContain('正花 ×2');
    expect(seat.names).not.toContain('平胡'); // flowers break 平胡
    const set = score(base, '4p', { flowers: ['F1', 'F2', 'F3', 'F4', 'F6'] });
    expect(set.names).toContain('花槓（春夏秋冬）');
    expect(set.names).toContain('正花'); // only 蘭 (F6); 夏 is inside the completed set
    const plants = score(base, '4p', { flowers: ['F5', 'F6', 'F7', 'F8', 'F2'] });
    expect(plants.names).toContain('花槓（梅蘭竹菊）');
    expect(plants.names).toContain('正花'); // 夏 (F2) only
  });

  it('situational items', () => {
    const base = '123m 456m 234s 567s 88s 234p';
    expect(score(base, '4p', { robKong: true }).names).toContain('搶槓');
    expect(score(base, '4p', { selfDraw: true, kongBloom: true }).names).toContain('槓上開花');
    expect(score(base, '4p', { selfDraw: true, lastTile: true }).names).toContain('海底撈月');
    expect(score(base, '4p', { lastTile: true }).names).toContain('河底撈魚');
  });

  it('天胡 / 地胡 drop 門清自摸, 人胡 drops 門清', () => {
    const base = '123m 456m 234s 567s 88s 234p';
    const heaven = score(base, '4p', { selfDraw: true, heaven: true, seatWind: 'E' });
    expect(heaven.names).toContain('天胡');
    expect(heaven.names).not.toContain('門清自摸');
    const earth = score(base, '4p', { selfDraw: true, earth: true });
    expect(earth.names).toContain('地胡');
    expect(earth.names).not.toContain('自摸');
    const human = score(base, '4p', { human: true });
    expect(human.names).toContain('人胡');
    expect(human.names).not.toContain('門清');
  });

  it('flower wins', () => {
    expect(scoreFlowerWin('eightFlowers')).toEqual({ items: [{ name: '八仙過海', tai: 8 }], total: 8 });
    expect(scoreFlowerWin('sevenRobOne')).toEqual({ items: [{ name: '七搶一', tai: 8 }], total: 8 });
  });

  it('returns null for an incomplete hand', () => {
    expect(
      scoreWin({
        concealed: tiles('123m 456m 234s 567s 88s 239p'),
        melds: [],
        flowers: [],
        winTile: '9p',
        selfDraw: false,
        seatWind: 'S',
        roundWind: 'E',
      }),
    ).toBeNull();
  });
});

describe('settlement (底 100 / 每台 50)', () => {
  it('discard win between non-dealers: only the discarder pays', () => {
    expect(settle({ winner: 1, payers: [2], tai: 3, dealer: 0, streak: 0 })).toEqual([0, 250, -250, 0]);
  });

  it('dealer bonus (莊 1 + 連 N 拉 N) applies to dealer-involved payments only', () => {
    // Dealer seat 0 on streak 1 wins by discard: 3 + 1 + 2 = 6 tai.
    expect(settle({ winner: 0, payers: [3], tai: 3, dealer: 0, streak: 1 })).toEqual([400, 0, 0, -400]);
    // Non-dealer self-draw: only the dealer pays the bonus.
    const d = settle({ winner: 1, payers: [0, 2, 3], tai: 2, dealer: 0, streak: 0 });
    expect(d).toEqual([-250, 650, -200, -200]);
  });

  it('is zero-sum', () => {
    const d = settle({ winner: 2, payers: [0, 1, 3], tai: 7, dealer: 3, streak: 2 });
    expect(d.reduce((a, b) => a + b, 0)).toBe(0);
  });
});
