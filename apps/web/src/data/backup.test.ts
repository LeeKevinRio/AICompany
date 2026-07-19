// 匯入備份驗證（validateBackup / parseBackupText）的單元測試。
//
// 這層是「壞資料絕不進 storage」的唯一守門，所以覆蓋重點放在各種拒絕路徑：
// 非 JSON、非備份格式、版本不符、內容毀損；以及正常檔 / 空資料檔要能通過。

import { describe, expect, it } from 'vitest';
import {
  BACKUP_VERSION,
  parseBackupText,
  summarizeBackup,
  validateBackup,
} from './backup';
import type { BackupPayload } from './backup';
import { DEFAULT_GLOBAL_SETTINGS, DEFAULT_NEW_SESSION_RULES } from '../types';
import type { Player, Round, Session } from '../types';

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
    tai: 2,
    selfDraw: false,
    loserId: 'p2',
    createdAt: 1000,
    ...partial,
  };
}

// 刻意回傳 Record，方便塞入不合法欄位（繞過 TS 型別檢查），與 repository 測試同一套路。
function makeSession(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const base: Session = {
    id: 's1',
    name: '週五場',
    players,
    settings: { base: 100, tai: 50 },
    rules: { ...DEFAULT_NEW_SESSION_RULES },
    rounds: [makeRound()],
    createdAt: 2000,
  };
  return { ...base, ...overrides };
}

function makeBackup(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    exportedAt: '2026-07-19T00:00:00.000Z',
    version: BACKUP_VERSION,
    globalSettings: { ...DEFAULT_GLOBAL_SETTINGS },
    sessions: [makeSession()],
    ...overrides,
  };
}

describe('validateBackup — 正常檔', () => {
  it('完整備份檔通過驗證，並回傳正確摘要', () => {
    const result = validateBackup(makeBackup());
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.sessions).toHaveLength(1);
    expect(result.data.version).toBe(BACKUP_VERSION);
    expect(result.summary).toEqual({
      sessionCount: 1,
      roundCount: 1,
      rosterCount: 0,
      exportedAt: '2026-07-19T00:00:00.000Z',
    });
  });

  it('空 sessions 陣列是合法備份（剛清空過的資料也能匯入）', () => {
    const result = validateBackup(makeBackup({ sessions: [] }));
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.summary.sessionCount).toBe(0);
    expect(result.summary.roundCount).toBe(0);
  });

  it('舊格式 session（無 rules、endedAt 為 null）通過驗證並補上 migration 預設', () => {
    const legacy = makeSession({ endedAt: null });
    delete legacy.rules;
    const result = validateBackup(makeBackup({ sessions: [legacy] }));
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    // migration 補值必須為全 0（不得改變歷史分數）。
    expect(result.data.sessions[0].rules.selfDrawBonusTai).toBe(0);
    expect(result.data.sessions[0].rules.dealerEnabled).toBe(false);
  });

  it('名冊人數正確計入摘要', () => {
    const backup = makeBackup({
      globalSettings: {
        ...DEFAULT_GLOBAL_SETTINGS,
        roster: [
          { id: 'u1', name: '阿明', createdAt: 1 },
          { id: 'u2', name: '小華', createdAt: 2 },
        ],
      },
    });
    const result = validateBackup(backup);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.summary.rosterCount).toBe(2);
  });
});

describe('validateBackup — 不是備份檔', () => {
  it.each([
    ['null', null],
    ['數字', 42],
    ['字串', 'hello'],
    ['陣列（舊的純 sessions 陣列不是本格式）', [{ id: 's1' }]],
    ['空物件', {}],
  ])('%s 一律判為「不是備份檔」', (_label, input) => {
    const result = validateBackup(input);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('not-backup');
    expect(result.reason).toContain('不是 MaJong 備份檔');
  });

  it('缺 version 欄位 → not-backup', () => {
    const backup = makeBackup();
    delete backup.version;
    const result = validateBackup(backup);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('not-backup');
  });

  it('version 非字串 → not-backup', () => {
    const result = validateBackup(makeBackup({ version: 2 }));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('not-backup');
  });

  it('缺 sessions 欄位 → not-backup', () => {
    const backup = makeBackup();
    delete backup.sessions;
    const result = validateBackup(backup);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('not-backup');
  });

  it('缺 globalSettings 欄位 → not-backup', () => {
    const backup = makeBackup();
    delete backup.globalSettings;
    const result = validateBackup(backup);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('not-backup');
  });
});

describe('validateBackup — 版本不相容', () => {
  it('未來版本 v99 被擋下，訊息點名版本', () => {
    const result = validateBackup(makeBackup({ version: 'v99' }));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('unsupported-version');
    expect(result.reason).toContain('版本不相容');
    expect(result.reason).toContain('v99');
  });
});

describe('validateBackup — 資料格式損毀', () => {
  it('sessions 非陣列 → corrupt', () => {
    const result = validateBackup(makeBackup({ sessions: { a: 1 } }));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('corrupt');
  });

  it('globalSettings 缺必要欄位（defaultBase）→ corrupt', () => {
    const g: Record<string, unknown> = { ...DEFAULT_GLOBAL_SETTINGS };
    delete g.defaultBase;
    const result = validateBackup(makeBackup({ globalSettings: g }));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('corrupt');
    expect(result.reason).toContain('設定資料不合法');
  });

  it('session 缺必要欄位（id）→ corrupt', () => {
    const bad = makeSession();
    delete bad.id;
    const result = validateBackup(makeBackup({ sessions: [bad] }));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('corrupt');
  });

  it('session 玩家不足 4 人 → corrupt', () => {
    const bad = makeSession({ players: players.slice(0, 3) });
    const result = validateBackup(makeBackup({ sessions: [bad] }));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('corrupt');
  });

  it('round 的 winnerId 指向不存在的玩家 → corrupt', () => {
    const bad = makeSession({ rounds: [makeRound({ winnerId: 'p9' })] });
    const result = validateBackup(makeBackup({ sessions: [bad] }));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('corrupt');
  });

  it('只要一場毀損就整份拒絕（絕不部分匯入）', () => {
    const good = makeSession({ id: 's-good' });
    const bad = makeSession({ id: 's-bad', name: '壞場', settings: { base: -1, tai: 50 } });
    const result = validateBackup(makeBackup({ sessions: [good, bad] }));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('corrupt');
    // 訊息要點名是哪一場，方便使用者判斷。
    expect(result.reason).toContain('壞場');
  });
});

describe('parseBackupText', () => {
  it('合法 JSON 備份字串通過', () => {
    const result = parseBackupText(JSON.stringify(makeBackup()));
    expect(result.ok).toBe(true);
  });

  it('非 JSON 內容 → invalid-json', () => {
    const result = parseBackupText('這不是 JSON <html>');
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('invalid-json');
    expect(result.reason).toContain('JSON');
  });

  it('空字串 → invalid-json', () => {
    const result = parseBackupText('');
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('invalid-json');
  });

  it('JSON 合法但不是備份格式 → not-backup', () => {
    const result = parseBackupText('{"foo":"bar"}');
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('not-backup');
  });
});

// ---------------------------------------------------------------------------
// 匯入從嚴：parseGlobalSettings 沿用「載入寬容」策略會靜默濾掉壞的 roster / knownPlayers
// 條目。匯入若照抄這套，使用者會在毫無察覺下少了名冊成員 / 常用玩家。validateBackup 必須
// 比對解析前後長度，有被濾就整份拒絕。
// ---------------------------------------------------------------------------
describe('validateBackup — 匯入從嚴：roster / knownPlayers 不得靜默過濾', () => {
  it('10 人 roster 壞 3 人 → 整份拒絕（corrupt），不部分匯入', () => {
    const roster = Array.from({ length: 10 }, (_, i) => ({
      id: `u${i}`,
      name: `玩家${i}`,
      createdAt: i + 1,
    }));
    // 弄壞 3 筆：空 id / name 非字串 / createdAt 非數字（皆會被 parseGlobalSettings 濾掉）。
    (roster[2] as Record<string, unknown>).id = '';
    (roster[5] as Record<string, unknown>).name = 123;
    (roster[8] as Record<string, unknown>).createdAt = 'x';

    const result = validateBackup(
      makeBackup({ globalSettings: { ...DEFAULT_GLOBAL_SETTINGS, roster } }),
    );
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('corrupt');
    expect(result.reason).toContain('名冊');
  });

  it('roster 有重複 id（會被去重）→ 拒絕', () => {
    const roster = [
      { id: 'dup', name: 'A', createdAt: 1 },
      { id: 'dup', name: 'B', createdAt: 2 },
    ];
    const result = validateBackup(
      makeBackup({ globalSettings: { ...DEFAULT_GLOBAL_SETTINGS, roster } }),
    );
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('corrupt');
  });

  it('roster 存在但不是陣列 → 拒絕（不當成空名冊放行）', () => {
    const result = validateBackup(
      makeBackup({ globalSettings: { ...DEFAULT_GLOBAL_SETTINGS, roster: 'oops' } }),
    );
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('corrupt');
  });

  it('knownPlayers 含非字串 / 重複 → 拒絕', () => {
    const g = {
      ...DEFAULT_GLOBAL_SETTINGS,
      knownPlayers: ['阿明', '阿明', 42 as unknown as string],
    };
    const result = validateBackup(makeBackup({ globalSettings: g }));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe('corrupt');
    expect(result.reason).toContain('常用玩家');
  });

  it('乾淨的 roster / knownPlayers → 通過（不誤殺正常備份）', () => {
    const g = {
      ...DEFAULT_GLOBAL_SETTINGS,
      knownPlayers: ['阿明', '小華'],
      roster: [{ id: 'u1', name: '阿明', createdAt: 1 }],
    };
    const result = validateBackup(makeBackup({ globalSettings: g }));
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.summary.rosterCount).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// 整合：SettingsPage.exportData 產出的 payload 形狀，序列化後要能原樣被 parseBackupText 吃回。
// 守住「匯出→匯入」這條使用者主要救援路徑不會因驗證變嚴而自打嘴巴。
// ---------------------------------------------------------------------------
describe('exportData → parseBackupText roundtrip（整合）', () => {
  it('依 exportData 的 payload 形狀（indent 2 序列化）能原樣通過驗證', () => {
    const globalSettings = {
      ...DEFAULT_GLOBAL_SETTINGS,
      defaultBase: 100,
      defaultTai: 50,
      knownPlayers: ['阿明', '小華'],
      roster: [
        { id: 'u1', name: '阿明', createdAt: 1 },
        { id: 'u2', name: '小華', avatar: 'avatar_3', createdAt: 2 },
      ],
    };
    const sessions = [
      makeSession({ id: 's-rt', rounds: [makeRound(), makeRound({ id: 'r2' })] }),
    ];
    // 與 SettingsPage.exportData 完全一致的 payload 形狀與序列化參數（null, 2）。
    const payload = {
      exportedAt: new Date('2026-07-20T00:00:00.000Z').toISOString(),
      version: BACKUP_VERSION,
      globalSettings,
      sessions,
    };
    const text = JSON.stringify(payload, null, 2);

    const result = parseBackupText(text);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.summary).toEqual({
      sessionCount: 1,
      roundCount: 2,
      rosterCount: 2,
      exportedAt: '2026-07-20T00:00:00.000Z',
    });
    expect(result.data.sessions[0].id).toBe('s-rt');
    expect(result.data.globalSettings.knownPlayers).toEqual(['阿明', '小華']);
    expect(result.data.globalSettings.roster).toHaveLength(2);
  });
});

describe('summarizeBackup', () => {
  it('累加多場的局數，exportedAt 為空字串時回 undefined', () => {
    const payload: BackupPayload = {
      exportedAt: '',
      version: BACKUP_VERSION,
      globalSettings: { ...DEFAULT_GLOBAL_SETTINGS },
      sessions: [
        { ...(makeSession() as unknown as Session), rounds: [makeRound(), makeRound()] },
        { ...(makeSession() as unknown as Session), rounds: [makeRound()] },
      ],
    };
    expect(summarizeBackup(payload)).toEqual({
      sessionCount: 2,
      roundCount: 3,
      rosterCount: 0,
      exportedAt: undefined,
    });
  });
});
