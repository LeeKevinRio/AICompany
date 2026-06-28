// Tab 1：牌局清單。卡片清單 + FAB 新增 + Bottom Sheet。
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppData } from '../AppData';
import { scoreSession } from '../scoring/scoring';
import type { Session } from '../types';
import { Amount } from '../components/ui';
import { BottomSheet } from '../components/BottomSheet';

export function SessionsPage() {
  const { sessions, addSession, removeSession, renameSession, globalSettings } = useAppData();
  const navigate = useNavigate();
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <div className="page">
      <header className="page-header">
        <h1>牌局</h1>
      </header>

      {sessions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🀄</div>
          <p className="empty-title">還沒有牌局</p>
          <p>點右下角「＋」開始一場吧。</p>
        </div>
      ) : (
        <div className="session-list">
          {sessions.map((s) => (
            <SessionCard
              key={s.id}
              session={s}
              onOpen={() => navigate(`/sessions/${s.id}`)}
              onRename={() => {
                const name = prompt('重新命名牌局', s.name);
                if (name !== null) renameSession(s.id, name);
              }}
              onDelete={() => {
                if (confirm(`確定刪除「${s.name}」？此動作無法復原。`)) {
                  removeSession(s.id);
                }
              }}
            />
          ))}
        </div>
      )}

      <button className="fab" aria-label="新增牌局" onClick={() => setSheetOpen(true)}>
        ＋
      </button>

      <NewSessionSheet
        open={sheetOpen}
        knownPlayers={globalSettings.knownPlayers}
        onClose={() => setSheetOpen(false)}
        onCreate={(name, playerNames) => {
          const id = addSession(name, playerNames);
          setSheetOpen(false);
          navigate(`/sessions/${id}`);
        }}
      />
    </div>
  );
}

function SessionCard({
  session,
  onOpen,
  onRename,
  onDelete,
}: {
  session: Session;
  onOpen: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  let totals: Record<string, number>;
  try {
    totals = scoreSession(session.rounds, session.players, session.settings);
  } catch {
    totals = {};
    for (const p of session.players) totals[p.id] = 0;
  }

  const dateStr = new Date(session.createdAt).toLocaleDateString('zh-TW');
  const ended = !!session.endedAt;

  function handleMenu(e: React.MouseEvent) {
    e.stopPropagation();
    const action = prompt('輸入動作：1=重新命名、2=刪除', '1');
    if (action === '1') onRename();
    else if (action === '2') onDelete();
  }

  return (
    <div className="session-card" onClick={onOpen}>
      <button className="session-menu-btn" onClick={handleMenu} aria-label="牌局選單">
        ⋯
      </button>
      <div className="session-card-top">
        <span className="session-date">{dateStr}</span>
        <span className={`chip ${ended ? 'ended' : 'ongoing'}`}>
          {ended ? '已結算' : '進行中●'}
        </span>
      </div>
      <div className="session-name">{session.name}</div>

      <div className="session-scores">
        {session.players.map((p) => (
          <span className="session-score" key={p.id}>
            <span className="name">{p.name}</span>
            <Amount value={totals[p.id] ?? 0} />
          </span>
        ))}
      </div>

      <div className="session-card-bottom">
        <span className="tabular">{session.rounds.length} 局</span>
        <span>進入 ›</span>
      </div>
    </div>
  );
}

function NewSessionSheet({
  open,
  knownPlayers,
  onClose,
  onCreate,
}: {
  open: boolean;
  knownPlayers: string[];
  onClose: () => void;
  onCreate: (name: string, playerNames: string[]) => void;
}) {
  const [name, setName] = useState('');
  const [names, setNames] = useState<string[]>(['', '', '', '']);

  // 開啟時帶入預設場名
  const defaultName = `${new Date().toLocaleDateString('zh-TW')} 場`;

  function fillKnown(playerName: string) {
    // 填入第一個空欄
    setNames((prev) => {
      const idx = prev.findIndex((n) => !n.trim());
      if (idx === -1) return prev;
      const next = [...prev];
      next[idx] = playerName;
      return next;
    });
  }

  function handleCreate() {
    onCreate(name.trim() || defaultName, names);
    setName('');
    setNames(['', '', '', '']);
  }

  return (
    <BottomSheet open={open} onClose={onClose} title="新增牌局">
      <label className="field">
        <span>場名</span>
        <input
          type="text"
          placeholder={defaultName}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>

      <div className="players-grid" style={{ marginBottom: 16 }}>
        {names.map((n, i) => (
          <label className="field" key={i}>
            <span>玩家 {i + 1}</span>
            <input
              type="text"
              placeholder={`玩家 ${i + 1}`}
              value={n}
              maxLength={12}
              onChange={(e) => {
                const next = [...names];
                next[i] = e.target.value;
                setNames(next);
              }}
            />
          </label>
        ))}
      </div>

      {knownPlayers.length > 0 && (
        <>
          <span className="field" style={{ display: 'block' }}>
            <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
              常用玩家（點選填入空欄）
            </span>
          </span>
          <div className="known-player-chips">
            {knownPlayers.map((kp) => (
              <button key={kp} className="known-chip" onClick={() => fillKnown(kp)}>
                {kp}
              </button>
            ))}
          </div>
        </>
      )}

      <button className="primary" style={{ marginTop: 16 }} onClick={handleCreate}>
        建立牌局
      </button>
    </BottomSheet>
  );
}
