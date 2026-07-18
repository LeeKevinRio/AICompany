// 逐局快速記局（P1，企劃穩健牌 1）：大按鈕、三步完成，直接取代舊表單式輸入。
// 動線：1. 選贏家（大頭像按鈕）→ 2. 自摸 / 胡牌 → 3.（胡牌時）放槍者 → 台數確認 → 送出。
// 內建局次備註欄（P4，企劃穩健牌 6）：選填、20 字上限，收在送出鈕附近的次要位置。
// 放槍警示（本場放槍達門檻）與舊表單一致，功能不退化。
import { useEffect, useMemo, useRef, useState } from 'react';
import type { Player, Round, RosterPlayer, SessionRules } from '../types';
import { MAX_NOTE_LENGTH } from '../types';
import type { TableState } from '../scoring/dealer';
import { resolvePlayerVisual } from './ui';
import { PlayerAvatar } from './PlayerAvatar';

interface Props {
  players: Player[];
  rounds: Round[];
  /** 玩家名冊：解析每位玩家的頭像與代表色（與排名條 / 圖卡統一）。 */
  roster: RosterPlayer[];
  /** 本場規則：眼牌勾選僅在 rules.eyeTileEnabled 時顯示（v2.2）。 */
  rules: SessionRules;
  /** v2.3：連莊推導。active 時選贏家步驟標莊家 chip、動線末端出現「流局」按鈕。 */
  tableState?: TableState;
  onAdd: (round: Omit<Round, 'id' | 'createdAt'>) => void;
}

/** 放槍警示門檻（企劃 5「放槍者標記警示」）：本場放槍達此次數即提示。 */
const GUN_ALERT_THRESHOLD = 3;

/**
 * 滑桿粗調範圍上限（僅 range max），**非台數上限**。
 * 專案未定義台數上限（scoring 只驗 >= 0），台麻偶有超高台，故台數本身不封頂。
 * 取 100 讓天胡 24 台等高台可直接拖到；台數本身無上限，>100 用 + 按鈕。
 */
const SLIDER_MAX_TAI = 100;

export function RoundForm({ players, rounds, roster, rules, tableState, onAdd }: Props) {
  const dealer = tableState?.active ? tableState.current : null;
  // 本場各玩家放槍次數（供放槍者按鈕警示）。
  const gunCount = useMemo(() => {
    const c: Record<string, number> = {};
    for (const p of players) c[p.id] = 0;
    for (const r of rounds) {
      if (!r.selfDraw && r.loserId && c[r.loserId] !== undefined) c[r.loserId] += 1;
    }
    return c;
  }, [players, rounds]);

  const [winnerId, setWinnerId] = useState('');
  const [selfDraw, setSelfDraw] = useState<boolean | null>(null);
  const [loserId, setLoserId] = useState('');
  // 台數每局從 0 起算（CEO 實測後定案：不帶入上一局，避免忘了歸零記錯台）。
  const [tai, setTai] = useState(0);
  const [note, setNote] = useState('');
  // v2.2：眼牌勾選（僅本場啟用眼牌時可用），每局送出後歸零。
  const [eyeTile, setEyeTile] = useState(false);

  const canSubmit = !!winnerId && selfDraw !== null && (selfDraw || !!loserId);

  function handleSubmit() {
    if (!canSubmit) return;
    onAdd({
      winnerId,
      tai,
      selfDraw: selfDraw === true,
      loserId: selfDraw ? null : loserId,
      note: note.trim() || undefined,
      // 僅本場啟用眼牌且有勾選才寫入 flag，否則留 undefined（= 非眼牌）。
      eyeTile: rules.eyeTileEnabled && eyeTile ? true : undefined,
    });
    // 記完一局全部重置為初始態，台數歸 0。
    setWinnerId('');
    setSelfDraw(null);
    setLoserId('');
    setTai(0);
    setNote('');
    setEyeTile(false);
  }

  // v2.3：流局——一鍵記一筆 drawn 局（無贏家 / 放槍者、金額全 0），莊家連莊、圈風前進。
  function handleDrawn() {
    if (!window.confirm('本局流局（無人胡牌）？莊家將連莊、四人金額不變。')) return;
    onAdd({ winnerId: '', tai: 0, selfDraw: false, loserId: null, drawn: true });
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
            isDealer={!!dealer && dealer.dealerId === p.id}
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

      {/* v2.2：眼牌勾選——次要位階，不擋三步主動線；僅本場啟用眼牌時顯示。 */}
      {rules.eyeTileEnabled && (
        <button
          type="button"
          className={`quick-eye${eyeTile ? ' selected' : ''}`}
          role="switch"
          aria-checked={eyeTile}
          onClick={() => setEyeTile((v) => !v)}
        >
          <span className="quick-eye-box" aria-hidden="true">
            {eyeTile ? '✓' : ''}
          </span>
          眼牌（加 {rules.eyeTileTai} 台）
        </button>
      )}

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

      {/* v2.3：流局——低頻邊緣動作，ghost 全寬、與選贏家主動線用分隔線隔開；僅連莊啟用時出現。 */}
      {dealer && (
        <>
          <div className="drawn-divider" />
          <button type="button" className="drawn-btn" onClick={handleDrawn}>
            流局（本局無人胡牌）
          </button>
        </>
      )}
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
  isDealer = false,
  onClick,
}: {
  player: Player;
  seatIndex: number;
  roster: RosterPlayer[];
  selected: boolean;
  gunCount?: number;
  /** v2.3：此座位是否為當前莊家（選贏家步驟右下角標「莊」chip）。 */
  isDealer?: boolean;
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
      {isDealer && <span className="dealer-chip">莊</span>}
    </button>
  );
}

/**
 * 台數調整：滑桿粗調 + ± 按鈕微調並存。
 * - 滑桿（原生 range）：0 ~ SLIDER_MAX_TAI，牌桌上一拖到位；鍵盤方向鍵原生支援。
 * - ± 按鈕（縮小放滑桿兩端）：單步微調，支援長按加速（按住 ≥400ms 後每 80ms 連加）。
 * 大字當前值顯示在最上方，牌桌上一眼可見。
 */
function TaiStepper({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  const valueRef = useRef(value);
  valueRef.current = value;
  const timerRef = useRef<{ timeout?: number; interval?: number }>({});
  // 標記「本次已由 pointer 處理」，避免 pointerdown 後接著觸發的 click 重複計數。
  const pointerHandled = useRef(false);

  function step(delta: number) {
    // 只夾下界 0，不封頂：台數無上限，± 按鈕可超過滑桿 SLIDER_MAX_TAI（超高台走這條）。
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
      <span className="quick-tai-value tabular">{value} 台</span>
      <div className="quick-tai-controls">
        <button type="button" className="quick-tai-step" aria-label="減少台數" {...holdProps(-1)}>
          −
        </button>
        <input
          type="range"
          className="quick-tai-slider"
          min={0}
          max={SLIDER_MAX_TAI}
          step={1}
          value={value}
          aria-label="台數"
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <button type="button" className="quick-tai-step" aria-label="增加台數" {...holdProps(1)}>
          +
        </button>
      </div>
    </div>
  );
}
