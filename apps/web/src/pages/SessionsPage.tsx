// Tab 1：牌局清單。卡片清單 + FAB 新增 + Bottom Sheet（含開桌規則設定）。
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppData } from '../AppData';
import type { NewSessionPlayer } from '../hooks/useSessions';
import { settleSession } from '../scoring/scoring';
import type { RosterPlayer, Session, SessionRules, Settings } from '../types';
import { Amount } from '../components/ui';
import { PlayerAvatar } from '../components/PlayerAvatar';
import { BottomSheet } from '../components/BottomSheet';
import { RulesFields } from '../components/RulesFields';
import { Fab } from '../components/Fab';
import { toNonNegInt } from '../utils';

/**
 * #3：開新局沒取名稱時的預設場名「牌局 N」。
 * 取既有「牌局 N」場名中的最大 N + 1（刪過場次也不撞名）；
 * 若沒有任何「牌局 N」場名，則用「現有場數 + 1」起算。
 */
function nextSessionName(sessions: Session[]): string {
  let maxNo = 0;
  for (const s of sessions) {
    const m = /^牌局 (\d+)$/.exec(s.name.trim());
    if (m) maxNo = Math.max(maxNo, Number(m[1]));
  }
  const next = maxNo > 0 ? maxNo + 1 : sessions.length + 1;
  return `牌局 ${next}`;
}

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

      <Fab label="新增牌局" onClick={() => setSheetOpen(true)} />

      <NewSessionSheet
        open={sheetOpen}
        roster={globalSettings.roster}
        knownPlayers={globalSettings.knownPlayers}
        defaultRules={globalSettings.defaultRules}
        defaultBase={globalSettings.defaultBase}
        defaultTai={globalSettings.defaultTai}
        defaultName={nextSessionName(sessions)}
        onClose={() => setSheetOpen(false)}
        onCreate={(name, players, rules, settings) => {
          const id = addSession(name, players, rules, settings);
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
  // 卡片預覽顯示淨額（含東錢），與牌局詳情結算一致。
  let totals: Record<string, number>;
  try {
    totals = settleSession(session.rounds, session.players, session.settings, session.rules).net;
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
  roster,
  knownPlayers,
  defaultRules,
  defaultBase,
  defaultTai,
  defaultName,
  onClose,
  onCreate,
}: {
  open: boolean;
  roster: RosterPlayer[];
  knownPlayers: string[];
  defaultRules: SessionRules;
  defaultBase: number;
  defaultTai: number;
  defaultName: string;
  onClose: () => void;
  onCreate: (
    name: string,
    players: NewSessionPlayer[],
    rules: SessionRules,
    settings: Settings,
  ) => void;
}) {
  const [name, setName] = useState('');
  // 4 個座位：名字 + 可選 rosterId（從名冊帶入時連結）。
  const [seats, setSeats] = useState<NewSessionPlayer[]>([
    { name: '' },
    { name: '' },
    { name: '' },
    { name: '' },
  ]);
  const [rules, setRules] = useState<SessionRules>(defaultRules);
  // #1：底/台改為開局時設定（預設帶入全域 defaultBase/defaultTai）。
  const [base, setBase] = useState(defaultBase);
  const [tai, setTai] = useState(defaultTai);

  // 這個 sheet 關閉後仍保持 mounted，useState 初值只在首次 mount 生效；
  // 若不重設，使用者先到設定頁改了全域預設、再回來開新局，會帶到過期舊值。
  // 因此在 sheet 由關閉變開啟（open false→true）那一刻，把欄位重設為當前全域預設。
  // 依賴陣列只放 open，避免打字途中因 defaultBase/defaultTai 等變動而把使用者輸入洗掉。
  const wasOpen = useRef(false);
  useEffect(() => {
    if (open && !wasOpen.current) {
      setName('');
      setSeats([{ name: '' }, { name: '' }, { name: '' }, { name: '' }]);
      setRules(defaultRules);
      setBase(defaultBase);
      setTai(defaultTai);
    }
    wasOpen.current = open;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // 已帶入的 rosterId 集合（同一名冊成員不重複選入兩個座位）。
  const usedRosterIds = new Set(seats.map((s) => s.rosterId).filter(Boolean) as string[]);

  function fillRoster(rp: RosterPlayer) {
    setSeats((prev) => {
      if (prev.some((s) => s.rosterId === rp.id)) return prev;
      const idx = prev.findIndex((s) => !s.name.trim() && !s.rosterId);
      if (idx === -1) return prev;
      const next = [...prev];
      next[idx] = { name: rp.name, rosterId: rp.id };
      return next;
    });
  }

  function fillKnown(playerName: string) {
    setSeats((prev) => {
      const idx = prev.findIndex((s) => !s.name.trim() && !s.rosterId);
      if (idx === -1) return prev;
      const next = [...prev];
      next[idx] = { name: playerName };
      return next;
    });
  }

  function handleCreate() {
    onCreate(name.trim() || defaultName, seats, rules, { base, tai });
    setName('');
    setSeats([{ name: '' }, { name: '' }, { name: '' }, { name: '' }]);
    setRules(defaultRules);
    setBase(defaultBase);
    setTai(defaultTai);
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

      {/* #1：底/台在開局時設定 */}
      <div className="row" style={{ marginTop: 16 }}>
        <label className="field">
          <span>底</span>
          <input
            type="number"
            min={0}
            className="tabular"
            value={base}
            onChange={(e) => setBase(toNonNegInt(e.target.value))}
          />
        </label>
        <label className="field">
          <span>每台</span>
          <input
            type="number"
            min={0}
            className="tabular"
            value={tai}
            onChange={(e) => setTai(toNonNegInt(e.target.value))}
          />
        </label>
      </div>

      <div className="players-grid" style={{ margin: '16px 0' }}>
        {seats.map((seat, i) => (
          <label className="field" key={i}>
            <span>玩家 {i + 1}</span>
            <input
              type="text"
              placeholder={`玩家 ${i + 1}`}
              value={seat.name}
              maxLength={12}
              onChange={(e) => {
                const next = [...seats];
                // 手動改名 → 解除名冊連結（避免名字與名冊不符卻仍掛 rosterId）。
                next[i] = { name: e.target.value };
                setSeats(next);
              }}
            />
          </label>
        ))}
      </div>

      {roster.length > 0 && (
        <>
          <span className="field" style={{ display: 'block' }}>
            <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
              名冊（點選帶入空欄）
            </span>
          </span>
          <div className="known-player-chips">
            {roster.map((rp, i) => {
              // PNG 路徑（/avatars/…）不可當文字輸出，否則 chip 會顯示原始路徑破版；
              // 一律用 <PlayerAvatar> 渲染（含 emoji 舊資料與空值 fallback），與全站統一。
              // colorIndex 用名冊順序 mod 4，與 resolvePlayerVisual 同源同色。
              const showAvatar = !!rp.avatar && rp.avatar.startsWith('/avatars/');
              return (
                <button
                  key={rp.id}
                  className="known-chip"
                  disabled={usedRosterIds.has(rp.id)}
                  onClick={() => fillRoster(rp)}
                >
                  {showAvatar ? (
                    <PlayerAvatar
                      name={rp.name}
                      avatar={rp.avatar}
                      colorIndex={i % 4}
                      size={18}
                      className="known-chip-avatar"
                    />
                  ) : rp.avatar ? (
                    `${rp.avatar} `
                  ) : (
                    ''
                  )}
                  {rp.name}
                </button>
              );
            })}
          </div>
        </>
      )}

      {roster.length === 0 && knownPlayers.length > 0 && (
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

      <h3 className="rules-heading">規則設定</h3>
      <RulesFields rules={rules} onChange={setRules} />

      <button className="primary" style={{ marginTop: 16 }} onClick={handleCreate}>
        建立牌局
      </button>
    </BottomSheet>
  );
}
