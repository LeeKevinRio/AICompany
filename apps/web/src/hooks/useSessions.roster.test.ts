// 玩家名冊整合的資料層測試：
// #1 「加入名冊」回填歷史同名 Player 的 rosterId（戰績不歸零）
// #2 場內改名解除 rosterId（改名後不再歸錯名冊成員）
//
// 不掛 React：直接測純函式 linkSessionsToRoster，並用 aggregateByRosterId 驗證
// 回填／解除後的跨場聚合結果是否如預期。

import { describe, it, expect } from 'vitest';
import { linkSessionsToRoster } from './useSessions';
import { aggregateByRosterId, aggregateUnlinkedByName } from '../scoring/timeline';
import type { RosterPlayer, Round, Session } from '../types';
import { DEFAULT_SESSION_RULES } from '../types';

function makeSession(partial: Partial<Session> & Pick<Session, 'id'>): Session {
  return {
    name: '測試場',
    players: [
      { id: 'p1', name: '阿明' },
      { id: 'p2', name: '阿華' },
      { id: 'p3', name: '阿強' },
      { id: 'p4', name: '阿龍' },
    ],
    settings: { base: 100, tai: 50 },
    rules: { ...DEFAULT_SESSION_RULES },
    rounds: [],
    createdAt: 0,
    ...partial,
  };
}

// 阿明（p1）放槍贏阿華（p2）0 台：p1 +100、p2 -100。
const round: Round = {
  id: 'r1',
  winnerId: 'p1',
  tai: 0,
  selfDraw: false,
  loserId: 'p2',
  createdAt: 0,
};

describe('linkSessionsToRoster（#1 加入名冊回填歷史）', () => {
  it('回填同名且未連結的 Player → aggregateByRosterId 能聚合到歷史戰績', () => {
    const sessions = [makeSession({ id: 's1', rounds: [round] })];
    const rosterId = 'roster-ming';

    // 回填前：rosterId 尚未掛到任何 Player，聚合不到任何場次。
    expect(aggregateByRosterId(sessions, rosterId, '阿明').sessionsPlayed).toBe(0);

    const linked = linkSessionsToRoster(sessions, '阿明', rosterId);
    const stats = aggregateByRosterId(linked, rosterId, '阿明');

    // 回填後：歷史那場歸到名冊成員，戰績不歸零。
    expect(stats.sessionsPlayed).toBe(1);
    expect(stats.totalAmount).toBe(100);
    expect(linked[0].players[0].rosterId).toBe(rosterId);
  });

  it('不覆蓋已連結到其他 rosterId 的同名 Player', () => {
    const sessions = [
      makeSession({
        id: 's1',
        players: [
          { id: 'p1', name: '阿明', rosterId: 'roster-other' },
          { id: 'p2', name: '阿華' },
          { id: 'p3', name: '阿強' },
          { id: 'p4', name: '阿龍' },
        ],
        rounds: [round],
      }),
    ];

    const linked = linkSessionsToRoster(sessions, '阿明', 'roster-ming');

    // 已連結別人的座位不該被搶走。
    expect(linked[0].players[0].rosterId).toBe('roster-other');
    expect(aggregateByRosterId(linked, 'roster-ming', '阿明').sessionsPlayed).toBe(0);
  });

  it('名字不同的 Player 不受影響', () => {
    const sessions = [makeSession({ id: 's1', rounds: [round] })];
    const linked = linkSessionsToRoster(sessions, '阿明', 'roster-ming');
    // 其餘三人維持未連結。
    expect(linked[0].players.slice(1).every((p) => p.rosterId == null)).toBe(true);
  });
});

describe('addRosterPlayer existing 分支回填（名冊已有同名成員）', () => {
  // 模擬 addRosterPlayer 的 existing 分支核心邏輯：名冊已有同名成員時不新增重複成員，
  // 但仍對同名且未連結的歷史 Player 呼叫 linkSessionsToRoster 回填到既有成員 id。
  function addRosterPlayerSim(
    roster: RosterPlayer[],
    sessions: Session[],
    name: string,
  ): { roster: RosterPlayer[]; sessions: Session[]; result: RosterPlayer } {
    const trimmed = name.trim();
    const existing = roster.find((r) => r.name === trimmed);
    if (existing) {
      // existing 分支：不新增成員，回填未連結同名 Player 到 existing.id。
      return {
        roster,
        sessions: linkSessionsToRoster(sessions, trimmed, existing.id),
        result: existing,
      };
    }
    const rp: RosterPlayer = { id: 'roster-new', name: trimmed, createdAt: 0 };
    return {
      roster: [...roster, rp],
      sessions: linkSessionsToRoster(sessions, trimmed, rp.id),
      result: rp,
    };
  }

  it('未連結的同名歷史 Player 會回填到既有成員 id，且不新增重複成員', () => {
    // 名冊已有「阿明」(rosterId=roster-ming)。
    const existing: RosterPlayer = { id: 'roster-ming', name: '阿明', createdAt: 0 };
    const roster = [existing];
    // 某場重新開桌時手動打了「阿明」但沒從名冊選 → 該 Player rosterId 未連結。
    const sessions = [makeSession({ id: 's1', rounds: [round] })];

    // 回填前：未連結，聚合不到任何場次（漏帳）。
    expect(aggregateByRosterId(sessions, existing.id, '阿明').sessionsPlayed).toBe(0);

    const out = addRosterPlayerSim(roster, sessions, '阿明');

    // 走 existing 分支：回傳既有成員、名冊長度不變（沒有新增重複成員）。
    expect(out.result.id).toBe(existing.id);
    expect(out.roster).toHaveLength(1);
    expect(out.roster.filter((r) => r.name === '阿明')).toHaveLength(1);

    // 未連結的同名 Player 已回填到既有成員 id（而非漏回填）。
    expect(out.sessions[0].players[0].rosterId).toBe(existing.id);

    // 回填後：aggregateByRosterId(existing.id) 能聚合到該場次。
    const stats = aggregateByRosterId(out.sessions, existing.id, '阿明');
    expect(stats.sessionsPlayed).toBe(1);
    expect(stats.totalAmount).toBe(100);
  });
});

describe('同名＝同一人（CEO 定案）：加入名冊歸入既有成員、回填涵蓋全部同名未連結場次', () => {
  const rosterId = 'roster-ming';

  it('多場同名未連結 Player 一次回填全部，歸入同一個 rosterId', () => {
    // 三場都各有一個叫「阿明」的未連結 Player（rosterId == null）。
    // s1：阿明放槍贏 +100；s2：阿明放槍輸 -100；s3：阿明放槍贏 +100。
    const lose: Round = {
      id: 'r2',
      winnerId: 'p2',
      tai: 0,
      selfDraw: false,
      loserId: 'p1',
      createdAt: 0,
    };
    const sessions = [
      makeSession({ id: 's1', createdAt: 1, rounds: [round] }),
      makeSession({ id: 's2', createdAt: 2, rounds: [lose] }),
      makeSession({ id: 's3', createdAt: 3, rounds: [{ ...round, id: 'r3' }] }),
    ];

    // 回填前：rosterId 聚合不到任何場次。
    expect(aggregateByRosterId(sessions, rosterId, '阿明').sessionsPlayed).toBe(0);

    // 「加入名冊」回填：把所有同名且未連結的 Player 連到既有成員。
    const linked = linkSessionsToRoster(sessions, '阿明', rosterId);

    // 涵蓋全部三場：每場的「阿明」座位都被回填到同一個 rosterId。
    expect(linked.every((s) => s.players[0].rosterId === rosterId)).toBe(true);

    // 聚合涵蓋全部三場：+100 - 100 + 100 = +100、出場 3 場（不重不漏）。
    const stats = aggregateByRosterId(linked, rosterId, '阿明');
    expect(stats.sessionsPlayed).toBe(3);
    expect(stats.totalAmount).toBe(100);
  });

  it('同一場有兩個同名未連結座位：回填後 rosterId 聚合把兩個座位都算到', () => {
    // 同名＝同人：一場內 p1、p3 都叫「阿明」（皆未連結）。
    // r1：p1 放槍贏 p2 +100；r2：p3 放槍贏 p4 +100。
    const session = makeSession({
      id: 's1',
      players: [
        { id: 'p1', name: '阿明' },
        { id: 'p2', name: '阿華' },
        { id: 'p3', name: '阿明' },
        { id: 'p4', name: '阿龍' },
      ],
      rounds: [
        round,
        { id: 'r2', winnerId: 'p3', tai: 0, selfDraw: false, loserId: 'p4', createdAt: 0 },
      ],
    });

    const linked = linkSessionsToRoster([session], '阿明', rosterId);
    // 兩個同名座位都被回填。
    expect(linked[0].players[0].rosterId).toBe(rosterId);
    expect(linked[0].players[2].rosterId).toBe(rosterId);

    // 聚合把同場兩座位都算到：+100 + 100 = +200，出場 1 場（不漏帳）。
    const stats = aggregateByRosterId(linked, rosterId, '阿明');
    expect(stats.sessionsPlayed).toBe(1);
    expect(stats.totalAmount).toBe(200);
  });
});

describe('aggregateUnlinkedByName（歷史卡片只算未連結同名場次）', () => {
  // 場景：名冊已有「阿明」(roster-ming)，s1 那場的 p1 已連結到名冊（+100）；
  // s2 那場的 p1 同樣叫「阿明」但未連結（rosterId 未填）（-100）。
  // 兩種身分並存的過渡狀態。
  const rosterId = 'roster-ming';

  // s1：阿明已連結名冊，放槍贏 +100。
  const linkedSession = makeSession({
    id: 's1',
    players: [
      { id: 'p1', name: '阿明', rosterId },
      { id: 'p2', name: '阿華' },
      { id: 'p3', name: '阿強' },
      { id: 'p4', name: '阿龍' },
    ],
    rounds: [round],
  });

  // s2：阿明未連結名冊，放槍輸 -100（p2 贏阿明）。
  const unlinkedRound: Round = {
    id: 'r2',
    winnerId: 'p2',
    tai: 0,
    selfDraw: false,
    loserId: 'p1',
    createdAt: 0,
  };
  const unlinkedSession = makeSession({ id: 's2', rounds: [unlinkedRound] });

  it('未連結聚合只算未連結場次，不含已連結場次', () => {
    const sessions = [linkedSession, unlinkedSession];

    // 名冊成員（rosterId）只聚合到已連結那場 +100。
    const rosterStats = aggregateByRosterId(sessions, rosterId, '阿明');
    expect(rosterStats.sessionsPlayed).toBe(1);
    expect(rosterStats.totalAmount).toBe(100);

    // 未連結聚合只算未連結那場 -100，不含已連結的 +100（不雙重計入）。
    const unlinkedStats = aggregateUnlinkedByName(sessions, '阿明');
    expect(unlinkedStats.sessionsPlayed).toBe(1);
    expect(unlinkedStats.totalAmount).toBe(-100);

    // 對照：純名字聚合（aggregatePlayerStats）會把兩場都算進去（會雙重計入），
    // 這正是本次要避免的行為，故歷史卡片改用 aggregateUnlinkedByName。
  });

  it('回填後未連結聚合歸零、名冊聚合涵蓋全部場次', () => {
    const sessions = [linkedSession, unlinkedSession];

    // 「加入名冊」回填：把同名且未連結的 Player 連到既有成員 id。
    const linked = linkSessionsToRoster(sessions, '阿明', rosterId);

    // 回填後：未連結聚合歸零（hasUnlinked 變 false → 歷史卡片消失）。
    const unlinkedStats = aggregateUnlinkedByName(linked, '阿明');
    expect(unlinkedStats.sessionsPlayed).toBe(0);
    expect(unlinkedStats.totalAmount).toBe(0);

    // 名冊聚合涵蓋全部兩場：+100 與 -100，淨額 0、出場 2 場（不重不漏）。
    const rosterStats = aggregateByRosterId(linked, rosterId, '阿明');
    expect(rosterStats.sessionsPlayed).toBe(2);
    expect(rosterStats.totalAmount).toBe(0);
  });
});

describe('場內改名解除 rosterId（#2 改名後不再歸錯人）', () => {
  // 模擬 updatePlayerName 的核心行為：改名一併 rosterId: undefined。
  function renameSeat(session: Session, playerId: string, name: string): Session {
    return {
      ...session,
      players: session.players.map((p) =>
        p.id === playerId ? { ...p, name, rosterId: undefined } : p,
      ),
    };
  }

  it('把名冊成員座位改成別人後，新名字的局數不再算進原名冊成員', () => {
    const rosterId = 'roster-ming';
    // p1 原本連結到阿明的名冊成員，且贏了那一局（+100）。
    const session = makeSession({
      id: 's1',
      players: [
        { id: 'p1', name: '阿明', rosterId },
        { id: 'p2', name: '阿華' },
        { id: 'p3', name: '阿強' },
        { id: 'p4', name: '阿龍' },
      ],
      rounds: [round],
    });

    // 改名前：阿明名冊成員聚合到這場 +100。
    expect(aggregateByRosterId([session], rosterId, '阿明').totalAmount).toBe(100);

    // 場內把 p1 座位改成「小華」（換成別人）。
    const renamed = renameSeat(session, 'p1', '小華');

    // 改名後：座位脫離名冊，阿明名冊成員不再被算到這場。
    const stats = aggregateByRosterId([renamed], rosterId, '阿明');
    expect(stats.sessionsPlayed).toBe(0);
    expect(stats.totalAmount).toBe(0);
    expect(renamed.players[0].rosterId).toBeUndefined();
  });
});
