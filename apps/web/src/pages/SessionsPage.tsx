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

/** 穩健牌 3「再開同組」：從既有場次帶入到新增牌局 sheet 的預填內容。 */
interface SessionPrefill {
  name: string;
  seats: NewSessionPlayer[];
  rules: SessionRules;
  base: number;
  tai: number;
}

export function SessionsPage() {
  const { sessions, addSession, removeSession, renameSession, globalSettings } = useAppData();
  const navigate = useNavigate();
  const [sheetOpen, setSheetOpen] = useState(false);
  // 穩健牌 3：非 null 時，開 sheet 帶入此場設定（在 sheet 的「open 重設」之後套用）。
  const [prefill, setPrefill] = useState<SessionPrefill | null>(null);

  // 「再開同組」：以指定場次為模板，帶入 4 人（含 rosterId 連結）、底/台、規則，打開 sheet 供確認。
  function handleDuplicate(s: Session) {
    setPrefill({
      name: nextSessionName(sessions),
      seats: s.players.map((p) => ({ name: p.name, rosterId: p.rosterId })),
      rules: { ...s.rules },
      base: s.settings.base,
      tai: s.settings.tai,
    });
    setSheetOpen(true);
  }

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
              onDuplicate={() => handleDuplicate(s)}
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
        prefill={prefill}
        onClose={() => {
          setSheetOpen(false);
          setPrefill(null);
        }}
        onCreate={(name, players, rules, settings) => {
          const id = addSession(name, players, rules, settings);
          setSheetOpen(false);
          setPrefill(null);
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
  onDuplicate,
}: {
  session: Session;
  onOpen: () => void;
  onRename: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
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
    // 穩健牌 3：新增「3=再開同組」——帶入本場 4 人、底/台、規則到新增牌局 sheet。
    const action = prompt('輸入動作：1=重新命名、2=刪除、3=再開同組', '1');
    if (action === '1') onRename();
    else if (action === '2') onDelete();
    else if (action === '3') onDuplicate();
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
  prefill,
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
  /** 穩健牌 3：「再開同組」帶入的模板（null＝一般新增，用全域預設）。 */
  prefill: SessionPrefill | null;
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
      // 先重設為全域預設；若本次是「再開同組」（prefill 非 null），重設後立即以模板覆蓋。
      // 兩步在同一個 effect 內完成，確保帶入值不會被「open 重設」邏輯蓋掉（穩健牌 3 需求）。
      if (prefill) {
        setName(prefill.name);
        setSeats(prefill.seats.map((s) => ({ ...s })));
        setRules({ ...prefill.rules });
        setBase(prefill.base);
        setTai(prefill.tai);
      } else {
        setName('');
        setSeats([{ name: '' }, { name: '' }, { name: '' }, { name: '' }]);
        setRules(defaultRules);
        setBase(defaultBase);
        setTai(defaultTai);
      }
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
        {seats.map((seat, i) => {
          // 穩健牌 5：座位有名字時，於名字旁顯示頭像小圖。
          // 有 rosterId → 用該名冊成員的頭像與其名冊順序色（與上方 chip 同源同色）；
          // 手動輸入（無 rosterId）→ 用座位序當色、字母 fallback。
          const linked = seat.rosterId
            ? roster.find((r) => r.id === seat.rosterId)
            : undefined;
          const seatColorIndex = linked
            ? roster.indexOf(linked) % 4
            : i % 4;
          const hasName = !!seat.name.trim();
          return (
            <label className="field" key={i}>
              <span>玩家 {i + 1}</span>
              <div className="seat-input">
                {hasName && (
                  <PlayerAvatar
                    name={seat.name}
                    avatar={linked?.avatar}
                    colorIndex={seatColorIndex}
                    size={24}
                    className="seat-avatar"
                  />
                )}
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
              </div>
            </label>
          );
        })}
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
              // 穩健牌 5：chip 一律帶頭像（size=32，較有「臉」的辨識度），統一走 <PlayerAvatar>
              // ——涵蓋 PNG、emoji 舊資料與空值字母 fallback，不再把 PNG 路徑當文字輸出破版。
              // colorIndex 用名冊順序 mod 4，與 resolvePlayerVisual 同源同色。
              // 已選入者不再灰掉 disabled，而是反白高亮（selected）＝「這個人已在桌上」的正回饋。
              const selected = usedRosterIds.has(rp.id);
              return (
                <button
                  key={rp.id}
                  className={`known-chip has-avatar${selected ? ' selected' : ''}`}
                  disabled={selected}
                  aria-pressed={selected}
                  onClick={() => fillRoster(rp)}
                >
                  <PlayerAvatar
                    name={rp.name}
                    avatar={rp.avatar}
                    colorIndex={i % 4}
                    size={32}
                    className="known-chip-avatar"
                  />
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
