// localStorageRepository validator 的向後相容測試。
//
// 重點覆蓋：v1 舊格式 session（缺 note / 缺 endedAt）能正確通過、不被誤判毀損；
// 以及 v2 新欄位型別錯（note 非字串、endedAt 非數字）會被正確判為毀損。
//
// validator（isValidSession 等）未對外 export，這裡透過 LocalStorageRepository.loadSessions()
// 的公開行為驗證——以 corrupted 旗標與留下/丟棄的 sessions 作為斷言依據。

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { LocalStorageRepository } from './localStorageRepository';
import type { Player, Round, Session } from '../types';

const STORAGE_KEY = 'mahjong-score:sessions:v1';

// 簡易記憶體版 localStorage（測試環境為 node，無瀏覽器 storage）。
class MemoryStorage {
  private map = new Map<string, string>();
  getItem(k: string): string | null {
    return this.map.has(k) ? this.map.get(k)! : null;
  }
  setItem(k: string, v: string): void {
    this.map.set(k, v);
  }
  removeItem(k: string): void {
    this.map.delete(k);
  }
  clear(): void {
    this.map.clear();
  }
}

beforeEach(() => {
  (globalThis as { localStorage?: unknown }).localStorage = new MemoryStorage();
});

afterEach(() => {
  delete (globalThis as { localStorage?: unknown }).localStorage;
});

const players: Player[] = [
  { id: 'p1', name: 'A' },
  { id: 'p2', name: 'B' },
  { id: 'p3', name: 'C' },
  { id: 'p4', name: 'D' },
];

function makeRound(partial: Partial<Round> = {}): Round {
  return {
    id: 'r1',
    winnerId: 'p1',
    tai: 0,
    selfDraw: false,
    loserId: 'p2',
    createdAt: 1000,
    ...partial,
  };
}

// 注意：刻意回傳 Record，方便在測試裡塞入「不合法型別」的欄位（繞過 TS 型別檢查）。
function makeSession(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const base: Session = {
    id: 's1',
    name: '週五場',
    players,
    settings: { base: 100, tai: 50 },
    rounds: [makeRound()],
    createdAt: 2000,
  };
  return { ...base, ...overrides };
}

function seed(data: unknown): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

describe('LocalStorageRepository validator 向後相容', () => {
  it('舊格式 session（round 缺 note）通過、不被判毀損', async () => {
    // 直接用 makeRound 不帶 note，模擬 v1 沒有 note 欄位的資料。
    const session = makeSession({ rounds: [makeRound()] });
    expect('note' in (session.rounds as Round[])[0]).toBe(false);
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
    expect(res.sessions[0].id).toBe('s1');
  });

  it('舊格式 session（缺 endedAt）通過、不被判毀損', async () => {
    const session = makeSession();
    expect('endedAt' in session).toBe(false);
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
    expect(res.sessions[0].endedAt).toBeUndefined();
  });

  it('同時缺 note 與 endedAt 的純 v1 資料完整通過', async () => {
    const session = makeSession({
      rounds: [makeRound(), makeRound({ id: 'r2', selfDraw: true, loserId: null })],
    });
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(false);
    expect(res.sessions).toHaveLength(1);
    expect(res.sessions[0].rounds).toHaveLength(2);
  });

  it('note 為非字串型別 → 該 session 判毀損並丟棄', async () => {
    const session = makeSession({ rounds: [makeRound({ note: 123 as unknown as string })] });
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(res.sessions).toHaveLength(0);
  });

  it('endedAt 為非數字型別 → 該 session 判毀損並丟棄', async () => {
    const session = makeSession({ endedAt: '2026-01-01' });
    seed([session]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(res.sessions).toHaveLength(0);
  });

  it('壞資料與好資料混雜：只丟壞的、保留好的，並回報 corrupted', async () => {
    const good = makeSession({ id: 'good' });
    const bad = makeSession({ id: 'bad', endedAt: NaN });
    seed([good, bad]);

    const res = await new LocalStorageRepository().loadSessions();
    expect(res.corrupted).toBe(true);
    expect(res.sessions.map((s) => s.id)).toEqual(['good']);
  });
});
