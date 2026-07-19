// Tab 3：設定。全域底/台預設、規則預設、輸贏警戒線、常用玩家管理、資料匯出/匯入、清空資料。
// 玩家名冊的「新增/管理」入口在「玩家」頁，這裡只放偏好設定。
import { useRef, useState } from 'react';
import { useAppData } from '../AppData';
import { MAX_KNOWN_PLAYERS } from '../types';
import { RulesFields } from '../components/RulesFields';
import { BottomSheet } from '../components/BottomSheet';
import { BACKUP_VERSION, parseBackupText } from '../data/backup';
import type { BackupPayload, BackupSummary } from '../data/backup';
import { toNonNegInt } from '../utils';

export function SettingsPage() {
  const {
    sessions,
    globalSettings,
    updateGlobalSettings,
    backupBeforeImport,
    importBackup,
    clearAll,
  } = useAppData();
  const [newPlayer, setNewPlayer] = useState('');
  // 匯入流程狀態：選檔驗證 → 待確認（pending）→ 覆蓋寫入。
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [pendingImport, setPendingImport] = useState<{
    payload: BackupPayload;
    summary: BackupSummary;
    // 開啟確認 sheet 前是否成功保命備份現有資料——false 時 sheet 改顯示警示而非承諾。
    backedUp: boolean;
  } | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importSuccess, setImportSuccess] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  function addKnown() {
    const name = newPlayer.trim();
    if (!name) return;
    if (globalSettings.knownPlayers.includes(name)) {
      setNewPlayer('');
      return;
    }
    if (globalSettings.knownPlayers.length >= MAX_KNOWN_PLAYERS) return;
    updateGlobalSettings({
      ...globalSettings,
      knownPlayers: [...globalSettings.knownPlayers, name],
    });
    setNewPlayer('');
  }

  function removeKnown(name: string) {
    updateGlobalSettings({
      ...globalSettings,
      knownPlayers: globalSettings.knownPlayers.filter((n) => n !== name),
    });
  }

  function exportData() {
    const payload = {
      exportedAt: new Date().toISOString(),
      version: BACKUP_VERSION,
      globalSettings,
      sessions,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `MaJong備份_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  /**
   * 選檔後：讀成文字 → 驗證 → 通過才進「待確認」。
   * 驗證未過絕不動 storage，只顯示錯誤訊息。
   */
  async function handleFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // 立刻清空 input value，否則使用者選同一個檔案第二次不會觸發 change。
    e.target.value = '';
    if (!file) return;
    setImportError(null);
    setImportSuccess(null);

    let text: string;
    try {
      text = await file.text();
    } catch {
      setImportError('讀取檔案失敗，請確認檔案仍存在後再試一次。');
      return;
    }

    const result = parseBackupText(text);
    if (!result.ok) {
      setImportError(result.reason);
      return;
    }
    // 開啟確認 sheet 前先做保命備份，並把成敗告訴 sheet：
    // 備份不成功就不能照樣承諾「覆蓋前會自動保留」，改在 sheet 上警示。
    // sheet 為 modal，其間現有資料不會變動，此時備份與稍後 confirm 覆蓋時的原始內容一致，
    // 也讓 importBackup 的 global rollback 有正確依據。
    const backedUp = backupBeforeImport();
    setPendingImport({ payload: result.data, summary: result.summary, backedUp });
  }

  /** 使用者在確認 sheet 按下覆蓋：先自動備份現有資料，再整份覆蓋寫入。 */
  async function handleConfirmImport() {
    if (!pendingImport || importing) return;
    setImporting(true);
    try {
      await importBackup(pendingImport.payload);
      const { sessionCount, roundCount } = pendingImport.summary;
      setPendingImport(null);
      setImportSuccess(`匯入完成：${sessionCount} 場牌局、${roundCount} 局紀錄已還原。`);
    } catch (err) {
      console.error('匯入備份失敗：', err);
      setImportError(
        err instanceof Error
          ? `匯入失敗：${err.message}`
          : '匯入失敗，資料未變更，請稍後再試。',
      );
      setPendingImport(null);
    } finally {
      setImporting(false);
    }
  }

  function handleClearAll() {
    if (!confirm('確定清空所有牌局與設定？此動作無法復原。')) return;
    if (!confirm('再次確認：所有資料將被刪除，建議先匯出備份。確定繼續？')) return;
    clearAll();
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>設定</h1>
      </header>

      <section className="card">
        <h2>預設金額</h2>
        <div className="row">
          <label className="field">
            <span>底</span>
            <input
              type="number"
              min={0}
              className="tabular"
              value={globalSettings.defaultBase}
              onChange={(e) =>
                updateGlobalSettings({
                  ...globalSettings,
                  defaultBase: toNonNegInt(e.target.value),
                })
              }
            />
          </label>
          <label className="field">
            <span>每台</span>
            <input
              type="number"
              min={0}
              className="tabular"
              value={globalSettings.defaultTai}
              onChange={(e) =>
                updateGlobalSettings({
                  ...globalSettings,
                  defaultTai: toNonNegInt(e.target.value),
                })
              }
            />
          </label>
        </div>
        <p className="setting-hint">新建牌局時套用此預設，進入牌局後仍可個別調整。</p>
      </section>

      <section className="card">
        <h2>預設規則</h2>
        <RulesFields
          rules={globalSettings.defaultRules}
          onChange={(defaultRules) =>
            updateGlobalSettings({ ...globalSettings, defaultRules })
          }
        />
      </section>

      <section className="card">
        <h2>輸贏警戒線</h2>
        <p className="setting-hint">單場淨輸超過此金額時，排名條會紅色警示（0 = 關閉）。</p>
        <label className="field" style={{ marginTop: 12 }}>
          <span>金額（元）</span>
          <input
            type="number"
            min={0}
            className="tabular"
            value={globalSettings.loseAlertThreshold}
            onChange={(e) =>
              updateGlobalSettings({
                ...globalSettings,
                loseAlertThreshold: toNonNegInt(e.target.value),
              })
            }
          />
        </label>
      </section>

      <section className="card">
        <h2>常用玩家</h2>
        <p className="setting-hint">最多 {MAX_KNOWN_PLAYERS} 位，新增牌局時可一鍵帶入。</p>
        <div className="row" style={{ marginTop: 12 }}>
          <input
            type="text"
            placeholder="玩家名字"
            value={newPlayer}
            maxLength={12}
            onChange={(e) => setNewPlayer(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') addKnown();
            }}
          />
          <button
            className="secondary"
            onClick={addKnown}
            disabled={globalSettings.knownPlayers.length >= MAX_KNOWN_PLAYERS}
          >
            新增
          </button>
        </div>

        {globalSettings.knownPlayers.length > 0 && (
          <div className="known-list">
            {globalSettings.knownPlayers.map((name) => (
              <div className="known-item" key={name}>
                <span>{name}</span>
                <button className="link danger" onClick={() => removeKnown(name)}>
                  移除
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <h2>資料管理</h2>
        <button className="secondary" style={{ width: '100%', marginBottom: 12 }} onClick={exportData}>
          匯出所有資料（JSON）
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          style={{ display: 'none' }}
          onChange={handleFilePicked}
        />
        <button
          className="secondary"
          style={{ width: '100%', marginBottom: 12 }}
          onClick={() => fileInputRef.current?.click()}
        >
          從備份檔匯入（JSON）
        </button>

        {importError && (
          <p className="banner error" role="alert">
            {importError}
          </p>
        )}
        {importSuccess && (
          <p className="banner success" role="status">
            ✓ {importSuccess}
          </p>
        )}

        <button className="danger" style={{ width: '100%' }} onClick={handleClearAll}>
          清空所有資料
        </button>
        <p className="setting-hint">
          匯出可作為備份，防止 localStorage 意外清除；換手機時用匯入還原。
          匯入會覆蓋現有全部資料，覆蓋前會自動保留一份現有資料。
        </p>
      </section>

      <ImportConfirmSheet
        pending={pendingImport}
        importing={importing}
        onCancel={() => setPendingImport(null)}
        onConfirm={handleConfirmImport}
      />
    </div>
  );
}

/**
 * 匯入確認 sheet：整份覆蓋是破壞性且不可復原的操作，一律走全站一致的 BottomSheet 二次確認，
 * 並先把即將匯入的內容摘要攤在使用者眼前（避免匯到空檔或錯檔還按下去）。
 */
function ImportConfirmSheet({
  pending,
  importing,
  onCancel,
  onConfirm,
}: {
  pending: { payload: BackupPayload; summary: BackupSummary; backedUp: boolean } | null;
  importing: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const summary = pending?.summary;
  return (
    <BottomSheet open={pending !== null} onClose={onCancel} title="確認匯入備份">
      {summary && (
        <>
          <p className="banner error" role="alert">
            匯入將<strong>覆蓋現有全部資料</strong>（所有牌局、名冊、設定），且<strong>無法復原</strong>。
          </p>
          <div className="known-list">
            <div className="known-item">
              <span>牌局場數</span>
              <span className="tabular">{summary.sessionCount} 場</span>
            </div>
            <div className="known-item">
              <span>局數紀錄</span>
              <span className="tabular">{summary.roundCount} 局</span>
            </div>
            <div className="known-item">
              <span>名冊玩家</span>
              <span className="tabular">{summary.rosterCount} 位</span>
            </div>
            {summary.exportedAt && (
              <div className="known-item">
                <span>備份時間</span>
                <span className="tabular">{formatExportedAt(summary.exportedAt)}</span>
              </div>
            )}
          </div>
          {pending?.backedUp ? (
            <p className="setting-hint" style={{ marginTop: 12 }}>
              已自動保留一份現有資料，萬一匯錯仍有機會救回。
            </p>
          ) : (
            <p className="banner warn" role="alert" style={{ marginTop: 12 }}>
              無法自動備份現有資料（儲存空間可能已滿或被停用）。<strong>建議先手動匯出</strong>再繼續，否則此次覆蓋將無法救回。
            </p>
          )}
          <button
            className="danger"
            style={{ width: '100%', marginTop: 16 }}
            disabled={importing}
            onClick={onConfirm}
          >
            {importing ? '匯入中…' : '確認覆蓋匯入'}
          </button>
          <button
            className="secondary"
            style={{ width: '100%', marginTop: 8 }}
            disabled={importing}
            onClick={onCancel}
          >
            取消
          </button>
        </>
      )}
    </BottomSheet>
  );
}

/** 把備份檔的 ISO 時間字串轉成在地顯示；不合法就原樣顯示，不因顯示層而擋下匯入。 */
function formatExportedAt(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  return new Date(t).toLocaleString('zh-TW');
}
