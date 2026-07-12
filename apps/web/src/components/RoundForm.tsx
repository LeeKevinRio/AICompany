// 逐局快速記局（P1，企劃穩健牌 1）：大按鈕、三步完成，直接取代舊表單式輸入。
// 動線：1. 選贏家（大頭像按鈕）→ 2. 自摸 / 胡牌 → 3.（胡牌時）放槍者 → 台數確認 → 送出。
// 內建局次備註欄（P4，企劃穩健牌 6）：選填、20 字上限，收在送出鈕附近的次要位置。
// 放槍警示（本場放槍達門檻）與舊表單一致，功能不退化。
import { useEffect, useMemo, useRef, useState } from 'react';
import type { Player, Round, RosterPlayer } from '../types';
import { MAX_NOTE_LENGTH } from '../types';
import { resolvePlayerVisual } from './ui';
import { PlayerAvatar } from './PlayerAvatar';

interface Props {
  players: Player[];
  rounds: Round[];
  /** 玩家名冊：解析每位玩家的頭像與代表色（與排名條 / 圖卡統一）。 */
  roster: RosterPlayer[];
  onAdd: (round: Omit<Round, 'id' | 'createdAt'>) => void;
}

/** 放槍警示門檻（企劃 5「放槍者標記警示」）：本場放槍達此次數即提示。 */
const GUN_ALERT_THRESHOLD = 3;

export function RoundForm({ players, rounds, roster, onAdd }: Props) {
  // 本場各玩家放槍次數（供放槍者按鈕警示）。
  const gunCount = useMemo(() => {
    const c: Record<string, number> = {};
    for (const p of players) c[p.id] = 0;
    for (const r of rounds) {
      if (!r.selfDraw && r.loserId && c[r.loserId] !== undefined) c[r.loserId] += 1;
    }
    return c;
  }, [players, rounds]);

  // 台數預設帶入上一局（企劃：預設台數從上一局帶入）。記完一局保留不重置，連續記局順手。
  const lastTai = rounds.length > 0 ? rounds[rounds.length - 1].tai : 0;

  const [winnerId, setWinnerId] = useState('');
  const [selfDraw, setSelfDraw] = useState<boolean | null>(null);
  const [loserId, setLoserId] = useState('');
  const [tai, setTai] = useState(lastTai);
  const [note, setNote] = useState('');

  const canSubmit = !!winnerId && selfDraw !== null && (selfDraw || !!loserId);

  function handleSubmit() {
    if (!canSubmit) return;
    onAdd({
      winnerId,
      tai,
      selfDraw: selfDraw === true,
      loserId: selfDraw ? null : loserId,
      note: note.trim() || undefined,
    });
    // 記完一局重置為初始態；tai 保留（即本局台數＝下一局的「上一局」預設）。
    setWinnerId('');
    setSelfDraw(null);
    setLoserId('');
    setNote('');
  }

  return (
    <section className="card">
      <p className="quick-step-label">1. 選贏家</p>
      <div className="quick-grid">
        {players.map((p, i) => (
          <PlayerPickButton
            key={p.id}
            player={p}
            seatIndex={i}
            roster={roster}
            selected={winnerId === p.id}
            onClick={() => {
              setWinnerId(p.id);
              if (loserId === p.id) setLoserId('');
            }}
          />
        ))}
      </div>

      <p className="quick-step-label">2. 自摸或胡牌</p>
      <div className="quick-grid">
        <button
          type="button"
          className={`quick-btn${selfDraw === true ? ' selected' : ''}`}
          onClick={() => {
            setSelfDraw(true);
            setLoserId('');
          }}
        >
          自摸
        </button>
        <button
          type="button"
          className={`quick-btn${selfDraw === false ? ' selected' : ''}`}
          onClick={() => setSelfDraw(false)}
        >
          胡牌（放槍）
        </button>
      </div>

      {selfDraw === false && (
        <>
          <p className="quick-step-label">3. 放槍者</p>
          <div className="quick-grid">
            {players
              .filter((p) => p.id !== winnerId)
              .map((p) => (
                <PlayerPickButton
                  key={p.id}
                  player={p}
                  seatIndex={players.findIndex((x) => x.id === p.id)}
                  roster={roster}
                  selected={loserId === p.id}
                  gunCount={gunCount[p.id]}
                  onClick={() => setLoserId(p.id)}
                />
              ))}
          </div>
          {loserId && gunCount[loserId] >= GUN_ALERT_THRESHOLD && (
            <p className="gun-alert">
              ⚠ {players.find((p) => p.id === loserId)?.name} 本場已放槍 {gunCount[loserId]} 次
            </p>
          )}
        </>
      )}

      <p className="quick-step-label">台數</p>
      <TaiStepper value={tai} onChange={setTai} />

      <label className="field quick-note">
        <span>
          這局備註（選填，{note.length}/{MAX_NOTE_LENGTH}）
        </span>
        <input
          type="text"
          placeholder="如：十三幺、連莊第三圈"
          value={note}
          maxLength={MAX_NOTE_LENGTH}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>

      <button type="button" className="primary" disabled={!canSubmit} onClick={handleSubmit}>
        記錄這一局
      </button>
    </section>
  );
}

/** 玩家選擇大按鈕：頭像 + 名字，選中 primary 高亮。放槍者用時附上本場放槍次數警示。 */
function PlayerPickButton({
  player,
  seatIndex,
  roster,
  selected,
  gunCount,
  onClick,
}: {
  player: Player;
  seatIndex: number;
  roster: RosterPlayer[];
  selected: boolean;
  gunCount?: number;
  onClick: () => void;
}) {
  const { colorIndex, avatar } = resolvePlayerVisual(player, seatIndex, roster);
  const alert = gunCount !== undefined && gunCount >= GUN_ALERT_THRESHOLD;
  return (
    <button
      type="button"
      className={`quick-pick${selected ? ' selected' : ''}`}
      onClick={onClick}
    >
      <PlayerAvatar
        name={player.name}
        avatar={avatar}
        colorIndex={colorIndex}
        size={40}
        className="quick-pick-avatar"
      />
      <span className="quick-pick-name">{player.name}</span>
      {alert && <span className="quick-pick-gun">放槍 {gunCount}</span>}
    </button>
  );
}

/**
 * 台數加減：左右大按鈕（≥44px，實際 56px），支援長按加速（按住連續增減）。
 * 快速點＝單步；按住 ≥400ms 後每 80ms 連加，讓高台數也能快速輸入，不因去掉數字鍵盤而退化。
 */
function TaiStepper({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  const valueRef = useRef(value);
  valueRef.current = value;
  const timerRef = useRef<{ timeout?: number; interval?: number }>({});
  // 標記「本次已由 pointer 處理」，避免 pointerdown 後接著觸發的 click 重複計數。
  const pointerHandled = useRef(false);

  function step(delta: number) {
    onChange(Math.max(0, valueRef.current + delta));
  }

  function startHold(delta: number) {
    stopHold(); // 防重複啟動：先清掉可能殘留的 timer 再開新的
    pointerHandled.current = true;
    step(delta); // 立即先動一步
    timerRef.current.timeout = window.setTimeout(() => {
      timerRef.current.interval = window.setInterval(() => step(delta), 80);
    }, 400);
  }

  // 只清 timer。刻意不動 pointerHandled：pointerup 後還會跟一個 click，
  // 旗標要留給 handleClick 去 swallow-and-reset，否則短點會被算兩次（+2）。
  function stopHold() {
    if (timerRef.current.timeout) window.clearTimeout(timerRef.current.timeout);
    if (timerRef.current.interval) window.clearInterval(timerRef.current.interval);
    timerRef.current = {};
  }

  // 拖曳離開 / 取消這兩條路徑後面不會有 click 跟隨，
  // 在這裡清旗標才安全，避免跨按鈕洩漏而吞掉下一顆鈕的計數。
  function cancelHold() {
    stopHold();
    pointerHandled.current = false;
  }

  // unmount 時清理 timeout/interval，避免長按中切 tab/離頁後 interval 仍在背景跑。
  useEffect(() => () => stopHold(), []);

  function handleClick(delta: number) {
    // 鍵盤（Enter / Space）不會觸發 pointerdown，走這條；pointer 已處理過則吞掉。
    if (pointerHandled.current) {
      pointerHandled.current = false;
      return;
    }
    step(delta);
  }

  const holdProps = (delta: number) => ({
    onPointerDown: () => startHold(delta),
    onPointerUp: stopHold,
    onPointerLeave: cancelHold,
    onPointerCancel: cancelHold,
    onClick: () => handleClick(delta),
  });

  return (
    <div className="quick-tai">
      <button type="button" aria-label="減少台數" {...holdProps(-1)}>
        −
      </button>
      <span className="quick-tai-value tabular">{value} 台</span>
      <button type="button" aria-label="增加台數" {...holdProps(1)}>
        +
      </button>
    </div>
  );
}
