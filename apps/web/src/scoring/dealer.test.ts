import { describe, it, expect } from 'vitest';
import { deriveTableState, deriveDealerContexts, WINDS } from './dealer';
import type { Player, Round, Session, SessionRules, Settings } from '../types';
import { DEFAULT_NEW_SESSION_RULES, DEFAULT_SESSION_RULES } from '../types';

const players: Player[] = [
  { id: 'p1', name: 'A' },
  { id: 'p2', name: 'B' },
  { id: 'p3', name: 'C' },
  { id: 'p4', name: 'D' },
];

const settings: Settings = { base: 100, tai: 50 };

// 連莊啟用的規則（CEO 拍板：做莊 1 台、連 N 拉 N = 2N 台、只牽涉莊家）。
const dealerRules: SessionRules = { ...DEFAULT_NEW_SESSION_RULES };

let seq = 0;
function makeSession(partial: Partial<Session> = {}): Session {
  return {
    id: 's1',
    name: 'S',
    players,
    settings,
    rules: dealerRules,
    rounds: [],
    createdAt: 0,
    dealerStartSeat: 'p1',
    ...partial,
  };
}

/** 一筆放槍局（winner 胡、loser 放槍）。 */
function win(winnerId: string, loserId: string): Round {
  return { id: `r${seq++}`, winnerId, loserId, tai: 1, selfDraw: false, createdAt: 0 };
}
/** 一筆自摸局。 */
function selfDraw(winnerId: string): Round {
  return { id: `r${seq++}`, winnerId, loserId: null, tai: 1, selfDraw: true, createdAt: 0 };
}
/** 一筆流局。 */
function drawn(): Round {
  return { id: `r${seq++}`, winnerId: '', loserId: null, tai: 0, selfDraw: false, createdAt: 0, drawn: true };
}

describe('WINDS 常數', () => {
  it('東南西北順序', () => {
    expect(WINDS).toEqual(['東', '南', '西', '北']);
  });
});

describe('deriveTableState — 未啟用（靜默）情境', () => {
  it('舊資料無 dealerStartSeat → active=false、perRound 空、current null', () => {
    const s = makeSession({ dealerStartSeat: undefined, rounds: [win('p2', 'p3')] });
    const ts = deriveTableState(s);
    expect(ts.active).toBe(false);
    expect(ts.perRound).toEqual([]);
    expect(ts.current).toBeNull();
  });

  it('dealerEnabled 關（即使有 dealerStartSeat）→ active=false', () => {
    const s = makeSession({ rules: DEFAULT_SESSION_RULES, rounds: [win('p2', 'p3')] });
    expect(deriveTableState(s).active).toBe(false);
  });

  it('dealerStartSeat 指向不存在座位 → active=false（不丟資料、靜默不啟用）', () => {
    const s = makeSession({ dealerStartSeat: 'pX' });
    expect(deriveTableState(s).active).toBe(false);
  });

  it('deriveDealerContexts 未啟用時回空陣列（呼叫端 index 取值天然 undefined）', () => {
    const s = makeSession({ dealerStartSeat: undefined, rounds: [win('p2', 'p3')] });
    expect(deriveDealerContexts(s)).toEqual([]);
  });
});

describe('deriveTableState — 首坐莊 / 基本輪轉', () => {
  it('空 rounds：current = 首莊、東風東局、streak 0', () => {
    const ts = deriveTableState(makeSession({ dealerStartSeat: 'p1' }));
    expect(ts.active).toBe(true);
    expect(ts.perRound).toEqual([]);
    expect(ts.current).toEqual({ dealerId: 'p1', circleWind: '東', roundWind: '東', streak: 0 });
  });

  it('首莊可為非 p1（如 p3）：輪轉序 p3→p4→p1→p2', () => {
    // 三局都由「當時的非莊家」胡 → 三次過莊（贏家避開當局莊家 p3、p4、p1）。
    const rounds = [win('p1', 'p3'), win('p1', 'p4'), win('p2', 'p1')];
    const ts = deriveTableState(makeSession({ dealerStartSeat: 'p3', rounds }));
    expect(ts.perRound.map((r) => r.dealerId)).toEqual(['p3', 'p4', 'p1']);
    expect(ts.current?.dealerId).toBe('p2');
  });

  it('別家胡 → 過莊（下一座位、東風南局、streak 0）', () => {
    const s = makeSession({ rounds: [win('p2', 'p3')] });
    const ts = deriveTableState(s);
    expect(ts.perRound[0]).toMatchObject({ dealerId: 'p1', circleWind: '東', roundWind: '東', streak: 0 });
    expect(ts.current).toEqual({ dealerId: 'p2', circleWind: '東', roundWind: '南', streak: 0 });
  });

  it('莊家放槍（別家胡）也是過莊', () => {
    // p1 是莊，p1 放槍給 p2 → winner p2 ≠ 莊 → 過莊
    const s = makeSession({ rounds: [win('p2', 'p1')] });
    expect(deriveTableState(s).current?.dealerId).toBe('p2');
  });
});

describe('deriveTableState — 連莊（莊家胡 / 流局）', () => {
  it('莊家胡 → 連莊（同一人、streak+1、圈風局風不動）', () => {
    const s = makeSession({ rounds: [win('p1', 'p2')] });
    const ts = deriveTableState(s);
    expect(ts.perRound[0].streak).toBe(0);
    expect(ts.current).toEqual({ dealerId: 'p1', circleWind: '東', roundWind: '東', streak: 1 });
  });

  it('莊家自摸 → 連莊', () => {
    const s = makeSession({ rounds: [selfDraw('p1')] });
    expect(deriveTableState(s).current).toMatchObject({ dealerId: 'p1', streak: 1 });
  });

  it('莊家連三拉三：streak 累加到 3、每局 perRound streak 為 0,1,2', () => {
    const s = makeSession({ rounds: [win('p1', 'p2'), win('p1', 'p3'), win('p1', 'p4')] });
    const ts = deriveTableState(s);
    expect(ts.perRound.map((r) => r.streak)).toEqual([0, 1, 2]);
    expect(ts.current).toMatchObject({ dealerId: 'p1', streak: 3, roundWind: '東' });
  });

  it('流局 → 莊家連莊（drawn 視為續莊）', () => {
    const s = makeSession({ rounds: [drawn()] });
    const ts = deriveTableState(s);
    expect(ts.perRound[0]).toMatchObject({ dealerId: 'p1', streak: 0 });
    expect(ts.current).toMatchObject({ dealerId: 'p1', streak: 1 });
  });

  it('流局連莊多次後別家胡 → 過莊、streak 歸 0', () => {
    const s = makeSession({ rounds: [drawn(), drawn(), win('p3', 'p4')] });
    const ts = deriveTableState(s);
    // 兩次流局：streak 0→1→2；第三局仍是 p1 當莊（streak 2）別家 p3 胡 → 過莊
    expect(ts.perRound.map((r) => r.streak)).toEqual([0, 1, 2]);
    expect(ts.perRound[2].dealerId).toBe('p1');
    expect(ts.current).toMatchObject({ dealerId: 'p2', roundWind: '南', streak: 0 });
  });
});

describe('deriveTableState — 圈風輪轉（防「北風圈消失」）', () => {
  it('東南西北完整一輪（4 次過莊）：圈風 東→南、莊回到首莊', () => {
    const rounds = [win('p2', 'p1'), win('p3', 'p1'), win('p4', 'p1'), win('p1', 'p2')];
    // 每局莊家都沒胡 → 4 次過莊
    const ts = deriveTableState(makeSession({ rounds }));
    expect(ts.perRound.map((r) => r.roundWind)).toEqual(['東', '南', '西', '北']);
    expect(ts.perRound.map((r) => r.circleWind)).toEqual(['東', '東', '東', '東']);
    // 過滿四莊 → 進南風圈，莊回到 p1
    expect(ts.current).toEqual({ dealerId: 'p1', circleWind: '南', roundWind: '東', streak: 0 });
  });

  it('四圈十六莊完整輪轉：北風北局存在、無風位消失，莊回首莊', () => {
    // 16 局都別家胡（莊家從不連莊）→ 16 次過莊
    const rounds: Round[] = [];
    // 依當前莊家推導誰是莊，讓每局都由「非莊家」胡（放槍給莊家）
    let dealerIdx = 0;
    for (let t = 0; t < 16; t++) {
      const dealer = players[dealerIdx % 4].id;
      const other = players[(dealerIdx + 1) % 4].id;
      rounds.push(win(other, dealer)); // other 胡、莊放槍 → 過莊
      dealerIdx++;
    }
    const ts = deriveTableState(makeSession({ rounds }));
    // 第 0 局：東風東局；第 15 局：北風北局
    expect(ts.perRound[0]).toMatchObject({ circleWind: '東', roundWind: '東' });
    expect(ts.perRound[15]).toMatchObject({ circleWind: '北', roundWind: '北' });
    // 四圈的圈風序列正確、每圈四局
    expect(ts.perRound.map((r) => r.circleWind)).toEqual([
      '東', '東', '東', '東',
      '南', '南', '南', '南',
      '西', '西', '西', '西',
      '北', '北', '北', '北',
    ]);
    // 過滿 16 莊 → 回到第五圈（東風圈）東局、莊回首莊 p1
    expect(ts.current).toEqual({ dealerId: 'p1', circleWind: '東', roundWind: '東', streak: 0 });
  });

  it('連莊插入不推進圈風：連莊局圈風/局風凍結，過莊才前進', () => {
    // p1 連莊 2 次後別家胡過莊，再別家胡過莊
    const rounds = [win('p1', 'p2'), win('p1', 'p3'), win('p2', 'p4'), win('p3', 'p1')];
    const ts = deriveTableState(makeSession({ rounds }));
    // 前三局莊都是 p1（連莊 streak 0,1,2），圈風局風都停在東風東局
    expect(ts.perRound.slice(0, 3).map((r) => r.roundWind)).toEqual(['東', '東', '東']);
    expect(ts.perRound[2]).toMatchObject({ dealerId: 'p1', roundWind: '東', streak: 2 });
    // 第三局 p2 胡 → 過莊到 p2（東風南局）；第四局 p2 當莊、p3 胡 → 過莊
    expect(ts.perRound[3]).toMatchObject({ dealerId: 'p2', roundWind: '南', streak: 0 });
    expect(ts.current).toMatchObject({ dealerId: 'p3', roundWind: '西' });
  });
});

describe('deriveDealerContexts', () => {
  it('攤成對齊 rounds 的 DealerContext 陣列（dealerId + streak）', () => {
    const s = makeSession({ rounds: [win('p1', 'p2'), win('p3', 'p4')] });
    expect(deriveDealerContexts(s)).toEqual([
      { dealerId: 'p1', streak: 0 },
      { dealerId: 'p1', streak: 1 },
    ]);
  });
});
