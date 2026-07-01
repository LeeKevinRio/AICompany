// Tab 2：玩家名冊。名冊成員（以 rosterId 聚合）+ 歷史唯名字玩家（fallback 名字聚合）。
// 新增玩家入口在此頁（不在設定 / 開桌流程）。
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppData } from '../AppData';
import {
  aggregateByRosterId,
  aggregateUnlinkedByName,
  collectPlayerNames,
} from '../scoring/timeline';
import { Amount } from '../components/ui';
import { Sparkline } from '../components/Sparkline';
import { BottomSheet } from '../components/BottomSheet';
import { Fab } from '../components/Fab';

type SortKey = 'sessions' | 'amount' | 'name';

export function PlayersPage() {
  const { sessions, globalSettings, addRosterPlayer } = useAppData();
  const navigate = useNavigate();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<SortKey>('sessions');

  const { roster } = globalSettings;

  // 名冊成員：以 rosterId 聚合（不受改名影響）。
  const rosterRows = useMemo(
    () =>
      roster.map((rp) => ({
        rosterId: rp.id,
        name: rp.name,
        avatar: rp.avatar,
        stats: aggregateByRosterId(sessions, rp.id, rp.name),
      })),
    [roster, sessions],
  );

  // 歷史唯名字玩家：出現在 session 但「尚有同名且未連結到名冊」的名字。
  const historicalNames = useMemo(() => {
    // 仍有「同名且未連結（rosterId == null）」Player 的名字——這些場次尚未歸帳。
    const hasUnlinked = new Set<string>();
    for (const s of sessions) {
      for (const p of s.players) {
        if (p.rosterId == null) hasUnlinked.add(p.name);
      }
    }
    // 只要還有同名且未連結的 Player，就保留顯示——即使名冊已有同名成員，這批未歸帳的
    // 場次也要讓使用者看得到、能點「加入名冊」觸發回填。回填走 addRosterPlayer 的 existing
    // 分支連到既有成員，不會新增重複成員。
    //
    // 反之，名字已在名冊「且」已無同名未連結 Player（hasUnlinked 為 false）時，代表全數歸帳，
    // 自動不顯示——這也涵蓋原本「名冊名字／已連結名字不重複顯示」的需求。
    return collectPlayerNames(sessions).filter((n) => hasUnlinked.has(n));
  }, [sessions]);

  const q = query.trim();
  const visibleRoster = rosterRows.filter((r) => !q || r.name.includes(q));
  const visibleHistorical = historicalNames.filter((n) => !q || n.includes(q));

  const sortedRoster = [...visibleRoster].sort((a, b) => {
    if (sort === 'amount') return b.stats.totalAmount - a.stats.totalAmount;
    if (sort === 'name') return a.name.localeCompare(b.name, 'zh-TW');
    return b.stats.sessionsPlayed - a.stats.sessionsPlayed;
  });

  const isEmpty = roster.length === 0 && historicalNames.length === 0;

  return (
    <div className="page">
      <header className="page-header">
        <h1>玩家</h1>
      </header>

      {isEmpty ? (
        <div className="empty-state">
          <div className="empty-icon">👤</div>
          <p className="empty-title">還沒有玩家</p>
          <p>點右下角「＋」新增第一位玩家，開桌時就能直接帶入。</p>
        </div>
      ) : (
        <>
          <div className="players-toolbar">
            <input
              type="text"
              placeholder="搜尋玩家名字…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
              <option value="sessions">出場多→少</option>
              <option value="amount">總輸贏高→低</option>
              <option value="name">名字</option>
            </select>
          </div>

          {sortedRoster.map((row) => (
            <div
              className="player-card"
              key={row.rosterId}
              onClick={() => navigate(`/players/r/${row.rosterId}`)}
            >
              <span className="player-avatar" aria-hidden>
                {row.avatar || row.name.slice(0, 1)}
              </span>
              <div className="player-card-info">
                <div className="player-card-name">{row.name}</div>
                <div className="player-card-meta">
                  出場 {row.stats.sessionsPlayed} 場 · <Amount value={row.stats.totalAmount} />
                </div>
              </div>
              <Sparkline
                values={row.stats.recentTrend.slice(-8)}
                color={
                  row.stats.totalAmount >= 0 ? 'var(--color-win)' : 'var(--color-lose)'
                }
              />
            </div>
          ))}

          {visibleHistorical.length > 0 && (
            <>
              <h3 className="players-subhead">歷史玩家（未加入名冊）</h3>
              {visibleHistorical.map((name) => {
                // 只算「同名且未連結名冊」的場次，避免與名冊成員（aggregateByRosterId）
                // 已聚合的同名場次重複計入。
                const stats = aggregateUnlinkedByName(sessions, name);
                return (
                  <div className="player-card historical" key={name}>
                    <div
                      className="player-card-info"
                      onClick={() => navigate(`/players/${encodeURIComponent(name)}`)}
                    >
                      <div className="player-card-name">{name}</div>
                      <div className="player-card-meta">
                        出場 {stats.sessionsPlayed} 場 · <Amount value={stats.totalAmount} />
                      </div>
                    </div>
                    <button
                      className="link"
                      onClick={(e) => {
                        e.stopPropagation();
                        addRosterPlayer(name);
                      }}
                    >
                      ＋ 加入名冊
                    </button>
                  </div>
                );
              })}
            </>
          )}
        </>
      )}

      <Fab label="新增玩家" onClick={() => setSheetOpen(true)} />

      <NewRosterSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        onCreate={(name, avatar) => {
          addRosterPlayer(name, avatar);
          setSheetOpen(false);
        }}
      />
    </div>
  );
}

// 常用 emoji 頭像快選（建議做：玩家頭像）。
const AVATAR_CHOICES = ['🀄', '😀', '😎', '🐯', '🐶', '🐰', '🐲', '🦊', '🐼', '🦁'];

function NewRosterSheet({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string, avatar?: string) => void;
}) {
  const [name, setName] = useState('');
  const [avatar, setAvatar] = useState('');

  function handleCreate() {
    if (!name.trim()) return;
    onCreate(name.trim(), avatar || undefined);
    setName('');
    setAvatar('');
  }

  return (
    <BottomSheet open={open} onClose={onClose} title="新增玩家">
      <label className="field">
        <span>姓名</span>
        <input
          type="text"
          placeholder="玩家名字"
          value={name}
          maxLength={12}
          autoFocus
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleCreate();
          }}
        />
      </label>

      <span className="field" style={{ display: 'block' }}>
        <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
          頭像（可選）
        </span>
      </span>
      <div className="avatar-choices">
        {AVATAR_CHOICES.map((a) => (
          <button
            key={a}
            type="button"
            className={`avatar-choice${avatar === a ? ' selected' : ''}`}
            onClick={() => setAvatar(avatar === a ? '' : a)}
          >
            {a}
          </button>
        ))}
      </div>

      <button className="primary" style={{ marginTop: 16 }} onClick={handleCreate}>
        確認新增
      </button>
    </BottomSheet>
  );
}
