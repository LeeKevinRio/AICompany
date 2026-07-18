import { describe, it, expect } from 'vitest';
import { seatOccupantAt, occupantPlayersAt, hasSubstitutions } from './substitution';
import { deriveTableState } from './dealer';
import type { Player, Round, Session, Substitution } from '../types';
import { DEFAULT_NEW_SESSION_RULES, DEFAULT_SESSION_RULES } from '../types';

const players: Player[] = [
  { id: 'p1', name: 'A' },
  { id: 'p2', name: 'B' },
  { id: 'p3', name: 'C' },
  { id: 'p4', name: 'D' },
];

let seq = 0;
function win(winnerId: string, loserId: string): Round {
  return { id: `r${seq++}`, winnerId, loserId, tai: 1, selfDraw: false, createdAt: 0 };
}

function makeSession(partial: Partial<Session> = {}): Session {
  return {
    id: 's1',
    name: 'S',
    players,
    settings: { base: 100, tai: 50 },
    rules: DEFAULT_SESSION_RULES,
    rounds: [],
    createdAt: 0,
    ...partial,
  };
}

describe('seatOccupantAt — 無換人（零回歸）', () => {
  it('無 substitutions → 任一局任一座位皆回初始佔用者', () => {
    const s = makeSession();
    expect(seatOccupantAt(s, 'p2', 0).name).toBe('B');
    expect(seatOccupantAt(s, 'p2', 99).name).toBe('B');
    expect(seatOccupantAt(s, 'p4', 5)).toMatchObject({ id: 'p4', name: 'D' });
  });

  it('座位不存在 → 回以 seatId 命名的占位（不回 undefined）', () => {
    const s = makeSession();
    expect(seatOccupantAt(s, 'pX', 0)).toEqual({ id: 'pX', name: 'pX' });
  });
});

describe('seatOccupantAt — 單座位單次換人', () => {
  const subs: Substitution[] = [{ seatId: 'p2', fromRoundIndex: 3, name: '阿明' }];
  const s = makeSession({ substitutions: subs });

  it('接手局之前仍是前一位（第 2 局 = B）', () => {
    expect(seatOccupantAt(s, 'p2', 2).name).toBe('B');
  });

  it('接手局起是新玩家（第 3 局 = 阿明，含邊界 fromRoundIndex）', () => {
    expect(seatOccupantAt(s, 'p2', 3).name).toBe('阿明');
    expect(seatOccupantAt(s, 'p2', 10).name).toBe('阿明');
  });

  it('不影響其他座位', () => {
    expect(seatOccupantAt(s, 'p1', 5).name).toBe('A');
  });
});

describe('seatOccupantAt — 單座位多次換人', () => {
  // p2：第 2 局起換阿明、第 5 局起再換小美。
  const subs: Substitution[] = [
    { seatId: 'p2', fromRoundIndex: 2, name: '阿明' },
    { seatId: 'p2', fromRoundIndex: 5, name: '小美' },
  ];
  const s = makeSession({ substitutions: subs });

  it('依 fromRoundIndex 取「≤ roundIndex 中最大者」', () => {
    expect(seatOccupantAt(s, 'p2', 1).name).toBe('B'); // 初始
    expect(seatOccupantAt(s, 'p2', 2).name).toBe('阿明'); // 第一次接手
    expect(seatOccupantAt(s, 'p2', 4).name).toBe('阿明');
    expect(seatOccupantAt(s, 'p2', 5).name).toBe('小美'); // 第二次接手
    expect(seatOccupantAt(s, 'p2', 9).name).toBe('小美');
  });

  it('substitutions 陣列順序顛倒也不影響（取最大 fromRoundIndex）', () => {
    const rev = makeSession({ substitutions: [...subs].reverse() });
    expect(seatOccupantAt(rev, 'p2', 6).name).toBe('小美');
  });
});

describe('seatOccupantAt — 同座位同 fromRoundIndex 兩筆（>= 等號分支 / 後進覆蓋）', () => {
  // 防禦性：資料層 addSubstitution 已改為「同座位同 index 覆蓋」，正常不會產生兩筆；
  // 但解析函式仍要對這種歷史/異常資料有明確語義——同 fromRoundIndex 取「陣列後出現者」。
  const subs: Substitution[] = [
    { seatId: 'p2', fromRoundIndex: 2, name: '先換' },
    { seatId: 'p2', fromRoundIndex: 2, name: '後換' },
  ];
  const s = makeSession({ substitutions: subs });

  it('走 >= 等號分支：同 fromRoundIndex 由後出現者覆蓋', () => {
    expect(seatOccupantAt(s, 'p2', 2).name).toBe('後換');
    expect(seatOccupantAt(s, 'p2', 9).name).toBe('後換');
  });

  it('接手前仍是初始佔用者，不受兩筆同 index 影響', () => {
    expect(seatOccupantAt(s, 'p2', 1).name).toBe('B');
  });
});

describe('seatOccupantAt — 跨座位換人', () => {
  const subs: Substitution[] = [
    { seatId: 'p1', fromRoundIndex: 2, name: '換一' },
    { seatId: 'p3', fromRoundIndex: 4, name: '換三' },
  ];
  const s = makeSession({ substitutions: subs });

  it('各座位獨立解析，互不干擾', () => {
    expect(seatOccupantAt(s, 'p1', 3).name).toBe('換一');
    expect(seatOccupantAt(s, 'p3', 3).name).toBe('C'); // p3 第 4 局才換
    expect(seatOccupantAt(s, 'p3', 4).name).toBe('換三');
    expect(seatOccupantAt(s, 'p2', 3).name).toBe('B'); // 從未換
  });
});

describe('seatOccupantAt — 第 0 局邊界', () => {
  it('fromRoundIndex=0 → 從第 0 局起即為新玩家', () => {
    const s = makeSession({ substitutions: [{ seatId: 'p2', fromRoundIndex: 0, name: '零起' }] });
    expect(seatOccupantAt(s, 'p2', 0).name).toBe('零起');
  });

  it('roundIndex=-1（分隔列查前一位用）→ 一律回初始佔用者', () => {
    const s = makeSession({ substitutions: [{ seatId: 'p2', fromRoundIndex: 0, name: '零起' }] });
    expect(seatOccupantAt(s, 'p2', -1).name).toBe('B');
  });
});

describe('seatOccupantAt — rosterId 有無', () => {
  it('接手者帶 rosterId → 解析結果含該 rosterId（供名冊聚合 / 頭像）', () => {
    const s = makeSession({
      substitutions: [{ seatId: 'p2', fromRoundIndex: 1, name: '阿明', rosterId: 'ros-9' }],
    });
    expect(seatOccupantAt(s, 'p2', 2)).toEqual({ id: 'p2', name: '阿明', rosterId: 'ros-9' });
  });

  it('接手者無 rosterId → rosterId 為 undefined（fallback 名字聚合）', () => {
    const s = makeSession({ substitutions: [{ seatId: 'p2', fromRoundIndex: 1, name: '阿明' }] });
    expect(seatOccupantAt(s, 'p2', 2).rosterId).toBeUndefined();
  });

  it('初始佔用者保留其 rosterId', () => {
    const withRoster = makeSession({
      players: [{ id: 'p1', name: 'A', rosterId: 'ros-1' }, ...players.slice(1)],
    });
    expect(seatOccupantAt(withRoster, 'p1', 0).rosterId).toBe('ros-1');
  });
});

describe('occupantPlayersAt / hasSubstitutions', () => {
  it('occupantPlayersAt 回「該局四座位當下佔用者」，保持座位順序', () => {
    const s = makeSession({ substitutions: [{ seatId: 'p2', fromRoundIndex: 2, name: '阿明' }] });
    expect(occupantPlayersAt(s, 3).map((p) => p.name)).toEqual(['A', '阿明', 'C', 'D']);
    expect(occupantPlayersAt(s, 1).map((p) => p.name)).toEqual(['A', 'B', 'C', 'D']);
  });

  it('hasSubstitutions：有 / 無', () => {
    expect(hasSubstitutions(makeSession())).toBe(false);
    expect(
      hasSubstitutions(makeSession({ substitutions: [{ seatId: 'p1', fromRoundIndex: 0, name: 'x' }] })),
    ).toBe(true);
  });
});

describe('與連莊互動（整合）：換人不影響莊家輪轉', () => {
  // 連莊啟用 + 有換人，deriveTableState 應與「同 rounds 但無換人」完全一致
  //（莊掛座位、fold 只看 rounds，不看 substitutions）。
  const rounds = [win('p2', 'p1'), win('p1', 'p3'), win('p1', 'p4'), win('p3', 'p2')];
  const base = makeSession({
    rules: { ...DEFAULT_NEW_SESSION_RULES },
    dealerStartSeat: 'p1',
    rounds,
  });
  const withSub = makeSession({
    rules: { ...DEFAULT_NEW_SESSION_RULES },
    dealerStartSeat: 'p1',
    rounds,
    substitutions: [{ seatId: 'p2', fromRoundIndex: 2, name: '阿明' }],
  });

  it('perRound（莊家 / 圈風 / 連莊）逐局一致', () => {
    expect(deriveTableState(withSub).perRound).toEqual(deriveTableState(base).perRound);
  });

  it('current（下一局莊 / 風）一致', () => {
    expect(deriveTableState(withSub).current).toEqual(deriveTableState(base).current);
  });
});
