// v2.4（批次 3 修）：刪局時同步修正換人時間軸（fromRoundIndex 左移）的資料層測試。
//
// 核心風險：刪掉某局後其後局全部前移一格，若 substitution.fromRoundIndex 不跟著左移，
// 歸戶邊界就會靜默漂移——接手者的首局被錯歸前任。這裡直接測純函式 removeRoundFromSession，
// 並用 seatOccupantAt 驗「剩餘 rounds 上各局的歸戶」是否維持原意。

import { describe, it, expect } from 'vitest';
import { removeRoundFromSession } from './useSessions';
import { seatOccupantAt } from '../scoring/substitution';
import type { Round, Session, Substitution } from '../types';
import { DEFAULT_SESSION_RULES } from '../types';

function makeRound(id: string): Round {
  return { id, winnerId: 'p1', tai: 1, selfDraw: false, loserId: 'p2', createdAt: 0 };
}

// 5 局 r0..r4；p2 座位第 3 局（含）起換成阿明 → r0,r1,r2 歸 B、r3,r4 歸阿明。
function makeSession(subs?: Substitution[]): Session {
  return {
    id: 's1',
    name: 'S',
    players: [
      { id: 'p1', name: 'A' },
      { id: 'p2', name: 'B' },
      { id: 'p3', name: 'C' },
      { id: 'p4', name: 'D' },
    ],
    settings: { base: 100, tai: 50 },
    rules: { ...DEFAULT_SESSION_RULES },
    rounds: ['r0', 'r1', 'r2', 'r3', 'r4'].map(makeRound),
    createdAt: 0,
    ...(subs ? { substitutions: subs } : {}),
  };
}

const subP2At3: Substitution[] = [{ seatId: 'p2', fromRoundIndex: 3, name: '阿明' }];

describe('removeRoundFromSession — 換人時間軸同步修正', () => {
  it('刪換人點「之前」的局 → fromRoundIndex 左移，歸戶維持不變', () => {
    const next = removeRoundFromSession(makeSession(subP2At3), 'r1');
    // rounds 前移：r0,r2,r3,r4；fromRoundIndex 3 → 2。
    expect(next.rounds.map((r) => r.id)).toEqual(['r0', 'r2', 'r3', 'r4']);
    expect(next.substitutions?.[0].fromRoundIndex).toBe(2);
    // 歸戶不變：剩餘 rounds 的第 0/1 局（r0,r2）仍歸 B，第 2/3 局（r3,r4）仍歸阿明。
    expect(seatOccupantAt(next, 'p2', 1).name).toBe('B'); // r2
    expect(seatOccupantAt(next, 'p2', 2).name).toBe('阿明'); // r3
  });

  it('刪換人點「之後」的局 → fromRoundIndex 不動，接手段不受影響', () => {
    const next = removeRoundFromSession(makeSession(subP2At3), 'r4');
    expect(next.rounds.map((r) => r.id)).toEqual(['r0', 'r1', 'r2', 'r3']);
    expect(next.substitutions?.[0].fromRoundIndex).toBe(3);
    expect(seatOccupantAt(next, 'p2', 2).name).toBe('B'); // r2
    expect(seatOccupantAt(next, 'p2', 3).name).toBe('阿明'); // r3 仍歸接手者
  });

  it('邊界：刪「正好是 fromRoundIndex 那一局」（接手者首局）→ 邊界不動，接手者少算一局', () => {
    const next = removeRoundFromSession(makeSession(subP2At3), 'r3');
    // 刪掉 index=3（接手者首局），r4 遞補到 index 3；fromRoundIndex 維持 3。
    expect(next.rounds.map((r) => r.id)).toEqual(['r0', 'r1', 'r2', 'r4']);
    expect(next.substitutions?.[0].fromRoundIndex).toBe(3);
    // 接手邊界仍在 index 3：r4 歸阿明、r2 歸 B。接手者只是少算了原 r3 一局。
    expect(seatOccupantAt(next, 'p2', 2).name).toBe('B'); // r2
    expect(seatOccupantAt(next, 'p2', 3).name).toBe('阿明'); // r4
  });

  it('找不到該 roundId → 原樣返回，絕不亂動 substitutions', () => {
    const s = makeSession(subP2At3);
    const next = removeRoundFromSession(s, 'nope');
    expect(next).toBe(s);
    expect(next.substitutions?.[0].fromRoundIndex).toBe(3);
  });

  it('無 substitutions 的場 → 只刪局、不新增 substitutions 欄位', () => {
    const next = removeRoundFromSession(makeSession(), 'r2');
    expect(next.rounds.map((r) => r.id)).toEqual(['r0', 'r1', 'r3', 'r4']);
    expect(next.substitutions).toBeUndefined();
  });

  it('多筆換人：只左移「> deletedIndex」的那些，其餘不動', () => {
    const subs: Substitution[] = [
      { seatId: 'p2', fromRoundIndex: 1, name: '阿明' },
      { seatId: 'p3', fromRoundIndex: 4, name: '小美' },
    ];
    const next = removeRoundFromSession(makeSession(subs), 'r2'); // deletedIndex=2
    // p2 的 1 不 > 2 → 維持 1；p3 的 4 > 2 → 3。
    expect(next.substitutions?.find((x) => x.seatId === 'p2')?.fromRoundIndex).toBe(1);
    expect(next.substitutions?.find((x) => x.seatId === 'p3')?.fromRoundIndex).toBe(3);
  });
});
