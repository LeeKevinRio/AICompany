// 主畫面：組裝設定、場次選擇、逐局輸入、明細與累計。
import { useState } from 'react';
import { useSessions } from './hooks/useSessions';
import { SettingsPanel } from './components/SettingsPanel';
import { RoundForm } from './components/RoundForm';
import { RoundList } from './components/RoundList';
import { Standings } from './components/Standings';

export default function App() {
  const {
    loaded,
    storageError,
    dataCorrupted,
    dismissCorruptNotice,
    sessions,
    current,
    currentId,
    setCurrentId,
    addSession,
    removeSession,
    updateSettings,
    updatePlayerName,
    addRound,
    removeRound,
  } = useSessions();

  const [newName, setNewName] = useState('');

  if (!loaded) {
    return <main className="app">載入中…</main>;
  }

  function handleAddSession() {
    addSession(newName);
    setNewName('');
  }

  return (
    <main className="app">
      <header className="app-header">
        <h1>麻將記分</h1>
        <p className="subtitle">台灣麻將 16 張 · 個人記分工具</p>
      </header>

      {storageError && (
        <p className="banner error" role="alert">
          資料未成功儲存：{storageError}
        </p>
      )}

      {dataCorrupted && (
        <p className="banner warn" role="alert">
          偵測到本機資料毀損，已丟棄壞掉的部分（必要時已重置）。
          <button className="link" onClick={dismissCorruptNotice}>
            知道了
          </button>
        </p>
      )}

      {/* 場次管理 */}
      <section className="card">
        <h2>牌局（場）</h2>
        <div className="row">
          <input
            type="text"
            placeholder="場名（可留空）"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <button className="primary" onClick={handleAddSession}>
            新增牌局
          </button>
        </div>

        {sessions.length > 0 && (
          <div className="row">
            <select value={currentId ?? ''} onChange={(e) => setCurrentId(e.target.value)}>
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}（{s.rounds.length} 局）
                </option>
              ))}
            </select>
            {current && (
              <button
                className="link danger"
                onClick={() => {
                  if (confirm(`確定刪除「${current.name}」？此動作無法復原。`)) {
                    removeSession(current.id);
                  }
                }}
              >
                刪除此牌局
              </button>
            )}
          </div>
        )}
      </section>

      {!current ? (
        <p className="muted">尚無牌局，請先新增一場。</p>
      ) : (
        <>
          <SettingsPanel
            settings={current.settings}
            players={current.players}
            onChangeSettings={(s) => updateSettings(current.id, s)}
            onChangePlayerName={(pid, name) => updatePlayerName(current.id, pid, name)}
          />

          <RoundForm players={current.players} onAdd={(r) => addRound(current.id, r)} />

          <Standings
            rounds={current.rounds}
            players={current.players}
            settings={current.settings}
          />

          <RoundList
            rounds={current.rounds}
            players={current.players}
            settings={current.settings}
            onRemove={(rid) => removeRound(current.id, rid)}
          />
        </>
      )}
    </main>
  );
}
