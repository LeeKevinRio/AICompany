// Tab 3：設定。全域底/台預設、規則預設、輸贏警戒線、常用玩家管理、資料匯出、清空資料。
// 玩家名冊的「新增/管理」入口在「玩家」頁，這裡只放偏好設定。
import { useState } from 'react';
import { useAppData } from '../AppData';
import { MAX_KNOWN_PLAYERS } from '../types';
import { RulesFields } from '../components/RulesFields';

function toNonNegInt(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0;
}

export function SettingsPage() {
  const { sessions, globalSettings, updateGlobalSettings, clearAll } = useAppData();
  const [newPlayer, setNewPlayer] = useState('');

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
      version: 'v2',
      globalSettings,
      sessions,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `麻將記分備份_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
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
        <button className="danger" style={{ width: '100%' }} onClick={handleClearAll}>
          清空所有資料
        </button>
        <p className="setting-hint">匯出可作為備份，防止 localStorage 意外清除。</p>
      </section>
    </div>
  );
}
