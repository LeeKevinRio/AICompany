// 備份檔（JSON）的格式定義與匯入驗證——純函式，不碰 storage、不碰 DOM，方便單元測試。
//
// 設計原則：匯入是「整份覆蓋」的破壞性操作，因此守門一律從嚴——
// 只要有任何一場 session 或全域設定不合法，整份拒絕，絕不部分匯入、
// 更不可把壞資料寫進 storage（載入時的「壞的丟掉、好的留下」寬容策略只適用讀既有資料，
// 匯入若照抄那套，使用者會在毫無察覺下被靜默吃掉幾場牌局）。
//
// 驗證共用 localStorageRepository 的 validator，避免「匯入放行、載入判毀損」的雙標。

import type { GlobalSettings, Session } from '../types';
import { isValidSession, migrateSession, parseGlobalSettings } from './localStorageRepository';

/** 匯出檔目前的版本字串（與 SettingsPage 匯出的 payload.version 一致）。 */
export const BACKUP_VERSION = 'v2';

/** 可被匯入的版本清單。日後升版時把舊版留在這裡並補 migration，才不會鎖死舊備份。 */
export const SUPPORTED_BACKUP_VERSIONS: readonly string[] = [BACKUP_VERSION];

/** 備份檔頂層結構。 */
export interface BackupPayload {
  exportedAt: string;
  version: string;
  globalSettings: GlobalSettings;
  sessions: Session[];
}

/** 匯入前給使用者確認用的摘要。 */
export interface BackupSummary {
  sessionCount: number;
  roundCount: number;
  /** 名冊人數（跨場玩家實體）。 */
  rosterCount: number;
  /** 匯出時間（ISO 字串；備份檔沒有或格式不對時為 undefined）。 */
  exportedAt?: string;
}

/** 驗證失敗的分類：UI 可據此決定要不要提供不同的補救建議。 */
export type BackupErrorCode =
  | 'invalid-json'
  | 'not-backup'
  | 'unsupported-version'
  | 'corrupt';

export type BackupValidationResult =
  | { ok: true; data: BackupPayload; summary: BackupSummary }
  | { ok: false; code: BackupErrorCode; reason: string };

function fail(code: BackupErrorCode, reason: string): BackupValidationResult {
  return { ok: false, code, reason };
}

/**
 * 驗證任意值是否為合法的備份檔內容。
 *
 * 檢查順序刻意由「是不是我們的檔」→「版本能不能吃」→「內容有沒有壞」，
 * 讓錯誤訊息指向使用者真正該做的事（選錯檔 / 版本太新 / 檔案損毀）。
 *
 * 回傳 ok:true 時，sessions 已套過與載入路徑相同的 migration 補值（migrateSession），
 * 可直接寫進 storage。
 */
export function validateBackup(data: unknown): BackupValidationResult {
  // 1) 頂層結構：必須是物件（陣列不算——舊的「只匯出 sessions 陣列」不是本格式）。
  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    return fail('not-backup', '這不是 MaJong 備份檔（檔案內容不是備份格式）。');
  }
  const d = data as Record<string, unknown>;

  // 2) 識別欄位：version + sessions + globalSettings 三者齊全才視為本 app 的備份檔。
  if (typeof d.version !== 'string' || d.version === '') {
    return fail('not-backup', '這不是 MaJong 備份檔（缺少版本資訊）。');
  }
  if (!('sessions' in d) || !('globalSettings' in d)) {
    return fail('not-backup', '這不是 MaJong 備份檔（缺少牌局或設定資料）。');
  }

  // 3) 版本相容性。
  if (!SUPPORTED_BACKUP_VERSIONS.includes(d.version)) {
    return fail(
      'unsupported-version',
      `備份檔版本不相容（檔案為 ${d.version}，本 app 支援 ${SUPPORTED_BACKUP_VERSIONS.join('、')}）。`,
    );
  }

  // 4) 內容型別：從嚴驗證，任何一筆壞掉就整份拒絕。
  if (!Array.isArray(d.sessions)) {
    return fail('corrupt', '資料格式損毀（牌局資料不是陣列）。');
  }
  const globalSettings = parseGlobalSettings(d.globalSettings);
  if (!globalSettings) {
    return fail('corrupt', '資料格式損毀（設定資料不合法）。');
  }
  // 匯入從嚴：parseGlobalSettings 沿用「載入寬容」策略，會靜默濾掉壞的 roster / knownPlayers
  // 條目（非字串、重複、超過上限等）。匯入若照抄這套，使用者會在毫無察覺下少了幾個名冊成員 /
  // 常用玩家。因此逐一比對解析前後的長度，只要有條目被濾就整份拒絕（絕不部分匯入）。
  const rawGlobal = d.globalSettings as Record<string, unknown>;
  // knownPlayers：parseGlobalSettings 已保證此欄位為陣列（否則上面就回 null），可直接比長度。
  if (globalSettings.knownPlayers.length !== (rawGlobal.knownPlayers as unknown[]).length) {
    return fail('corrupt', '資料格式損毀（常用玩家名單含無效或重複項目）。');
  }
  // roster：舊備份可能無此欄位（視為空，合法）；一旦存在就必須是陣列且無任何條目被濾。
  if ('roster' in rawGlobal) {
    if (
      !Array.isArray(rawGlobal.roster) ||
      globalSettings.roster.length !== rawGlobal.roster.length
    ) {
      return fail('corrupt', '資料格式損毀（玩家名冊含無效或重複項目）。');
    }
  }

  const sessions: Session[] = [];
  for (let i = 0; i < d.sessions.length; i++) {
    const item = d.sessions[i];
    if (!isValidSession(item)) {
      const meta = item as Record<string, unknown> | null;
      const name = meta && typeof meta.name === 'string' ? meta.name : `第 ${i + 1} 筆`;
      return fail('corrupt', `資料格式損毀（牌局〈${name}〉資料不合法）。`);
    }
    sessions.push(migrateSession(item));
  }

  const payload: BackupPayload = {
    exportedAt: typeof d.exportedAt === 'string' ? d.exportedAt : '',
    version: d.version,
    globalSettings,
    sessions,
  };
  return { ok: true, data: payload, summary: summarizeBackup(payload) };
}

/** 產生確認畫面用的摘要（純計數，不做驗證）。 */
export function summarizeBackup(payload: BackupPayload): BackupSummary {
  return {
    sessionCount: payload.sessions.length,
    roundCount: payload.sessions.reduce((sum, s) => sum + s.rounds.length, 0),
    rosterCount: payload.globalSettings.roster.length,
    exportedAt: payload.exportedAt || undefined,
  };
}

/** 從檔案文字內容解析並驗證：JSON 本身壞掉會回 invalid-json，其餘轉交 validateBackup。 */
export function parseBackupText(text: string): BackupValidationResult {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return fail('invalid-json', '檔案不是有效的 JSON，可能已損毀或選錯檔案。');
  }
  return validateBackup(data);
}
