// 逐局輸入表單：贏家、台數、自摸/放槍、放槍者、備註。
// 支援兩種模式：一般（dropdown）與快速（大按鈕，企劃 5-4）。
import { useMemo, useState } from 'react';
import type { Player, Round } from '../types';
import { MAX_NOTE_LENGTH } from '../types';
import { playerColor } from './ui';

interface Props {
  players: Player[];
  rounds: Round[];
  onAdd: (round: Omit<Round, 'id' | 'createdAt'>) => void;
}

type Mode = 'normal' | 'quick';

/** 放槍警示門檻（企劃 5「放槍者標記警示」）：本場放槍達此次數即提示。 */
const GUN_ALERT_THRESHOLD = 3;

export function RoundForm({ players, rounds, onAdd }: Props) {
  // 本場各玩家放槍次數（供放槍者欄位警示）。
  const gunCount = useMemo(() => {
    const c: Record<string, number> = {};
    for (const p of players) c[p.id] = 0;
    for (const r of rounds) {
      if (!r.selfDraw && r.loserId && c[r.loserId] !== undefined) c[r.loserId] += 1;
    }
    return c;
  }, [players, rounds]);
  const [mode, setMode] = useState<Mode>('normal');
  const [winnerId, setWinnerId] = useState(players[0]?.id ?? '');
  const [tai, setTai] = useState(0);
  const [selfDraw, setSelfDraw] = useState(false);
  const [loserId, setLoserId] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const loserCandidates = players.filter((p) => p.id !== winnerId);

  function reset() {
    setLoserId('');
    setNote('');
  }

  function submit(payload: {
    winnerId: string;
    tai: number;
    selfDraw: boolean;
    loserId: string;
    note: string;
  }): boolean {
    setError('');
    if (!payload.winnerId) {
      setError('請選擇贏家');
      return false;
    }
    if (!payload.selfDraw && !payload.loserId) {
      setError('放槍時必須選擇放槍者');
      return false;
    }
    if (!payload.selfDraw && payload.loserId === payload.winnerId) {
      setError('放槍者不能是贏家');
      return false;
    }
    onAdd({
      winnerId: payload.winnerId,
      tai: payload.tai,
      selfDraw: payload.selfDraw,
      loserId: payload.selfDraw ? null : payload.loserId,
      note: payload.note.trim() || undefined,
    });
    return true;
  }

  function handleNormalSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submit({ winnerId, tai, selfDraw, loserId, note })) {
      reset();
    }
  }

  const noteField = (
    <label className="field">
      <span>
        備註（可選，{note.length}/{MAX_NOTE_LENGTH}）
      </span>
      <input
        type="text"
        placeholder="如：連莊第三圈、清一色加台"
        value={note}
        maxLength={MAX_NOTE_LENGTH}
        onChange={(e) => setNote(e.target.value)}
      />
    </label>
  );

  return (
    <section className="card">
      <div className="mode-toggle">
        <button
          className={mode === 'normal' ? 'primary' : 'secondary'}
          onClick={() => setMode('normal')}
        >
          一般輸入
        </button>
        <button
          className={mode === 'quick' ? 'primary' : 'secondary'}
          onClick={() => setMode('quick')}
        >
          快速模式
        </button>
      </div>

      {mode === 'normal' ? (
        <form onSubmit={handleNormalSubmit}>
          <label className="field">
            <span>贏家</span>
            <select
              value={winnerId}
              onChange={(e) => {
                const newWinnerId = e.target.value;
                setWinnerId(newWinnerId);
                if (loserId === newWinnerId) setLoserId('');
              }}
            >
              {players.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>台數</span>
            <input
              type="number"
              min={0}
              value={tai}
              onChange={(e) => {
                const n = Number(e.target.value);
                setTai(Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0);
              }}
            />
          </label>

          <div className="radio-group">
            <label className="radio">
              <input
                type="radio"
                name="winType"
                checked={selfDraw}
                onChange={() => setSelfDraw(true)}
              />
              自摸
            </label>
            <label className="radio">
              <input
                type="radio"
                name="winType"
                checked={!selfDraw}
                onChange={() => setSelfDraw(false)}
              />
              胡牌（放槍）
            </label>
          </div>

          {!selfDraw && (
            <label className="field">
              <span>放槍者</span>
              <select value={loserId} onChange={(e) => setLoserId(e.target.value)}>
                <option value="">請選擇</option>
                {loserCandidates.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                    {gunCount[p.id] >= GUN_ALERT_THRESHOLD ? `（已放槍 ${gunCount[p.id]} 次）` : ''}
                  </option>
                ))}
              </select>
              {loserId && gunCount[loserId] >= GUN_ALERT_THRESHOLD && (
                <span className="gun-alert">
                  ⚠ {players.find((p) => p.id === loserId)?.name} 本場已放槍 {gunCount[loserId]} 次
                </span>
              )}
            </label>
          )}

          {noteField}

          {error && <p className="error">{error}</p>}

          <button type="submit" className="primary">
            新增並算分
          </button>
        </form>
      ) : (
        <QuickInput
          players={players}
          error={error}
          onSubmit={(payload) => {
            if (submit({ ...payload, note })) reset();
          }}
        />
      )}
    </section>
  );
}

// ---- 快速輸入模式：大按鈕、3~4 次點擊記完一局 ----

function QuickInput({
  players,
  error,
  onSubmit,
}: {
  players: Player[];
  error: string;
  onSubmit: (p: {
    winnerId: string;
    tai: number;
    selfDraw: boolean;
    loserId: string;
  }) => void;
}) {
  const [winnerId, setWinnerId] = useState('');
  const [selfDraw, setSelfDraw] = useState<boolean | null>(null);
  const [loserId, setLoserId] = useState('');
  const [tai, setTai] = useState(0);

  const canSubmit = winnerId && selfDraw !== null && (selfDraw || loserId);

  function handleSubmit() {
    if (!canSubmit) return;
    onSubmit({ winnerId, tai, selfDraw: selfDraw === true, loserId });
    // 重置整個快速流程
    setWinnerId('');
    setSelfDraw(null);
    setLoserId('');
    setTai(0);
  }

  return (
    <div>
      <p className="quick-step-label">1. 贏家</p>
      <div className="quick-grid">
        {players.map((p, i) => (
          <button
            key={p.id}
            className={`quick-btn color-bar${winnerId === p.id ? ' selected' : ''}`}
            onClick={() => {
              setWinnerId(p.id);
              if (loserId === p.id) setLoserId('');
            }}
          >
            <span className="qb-color" style={{ background: playerColor(i) }} />
            {p.name}
          </button>
        ))}
      </div>

      <p className="quick-step-label">2. 胡牌方式</p>
      <div className="quick-grid">
        <button
          className={`quick-btn${selfDraw === true ? ' selected' : ''}`}
          onClick={() => {
            setSelfDraw(true);
            setLoserId('');
          }}
        >
          自摸
        </button>
        <button
          className={`quick-btn${selfDraw === false ? ' selected' : ''}`}
          onClick={() => setSelfDraw(false)}
        >
          放槍
        </button>
      </div>

      {selfDraw === false && (
        <>
          <p className="quick-step-label">3. 放槍者</p>
          <div className="quick-grid">
            {players
              .filter((p) => p.id !== winnerId)
              .map((p) => {
                const idx = players.findIndex((x) => x.id === p.id);
                return (
                  <button
                    key={p.id}
                    className={`quick-btn color-bar${loserId === p.id ? ' selected' : ''}`}
                    onClick={() => setLoserId(p.id)}
                  >
                    <span className="qb-color" style={{ background: playerColor(idx) }} />
                    {p.name}
                  </button>
                );
              })}
          </div>
        </>
      )}

      <p className="quick-step-label">台數</p>
      <div className="quick-tai">
        <button onClick={() => setTai((t) => Math.max(0, t - 1))} aria-label="減少台數">
          −
        </button>
        <span className="quick-tai-value tabular">{tai} 台</span>
        <button onClick={() => setTai((t) => t + 1)} aria-label="增加台數">
          +
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      <button className="primary" disabled={!canSubmit} onClick={handleSubmit}>
        記錄這一局
      </button>
    </div>
  );
}
