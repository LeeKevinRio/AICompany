// 逐局輸入表單：贏家、台數、自摸/放槍、放槍者。
import { useState } from 'react';
import type { Player, Round } from '../types';

interface Props {
  players: Player[];
  onAdd: (round: Omit<Round, 'id' | 'createdAt'>) => void;
}

export function RoundForm({ players, onAdd }: Props) {
  const [winnerId, setWinnerId] = useState(players[0]?.id ?? '');
  const [tai, setTai] = useState(0);
  const [selfDraw, setSelfDraw] = useState(false);
  const [loserId, setLoserId] = useState('');
  const [error, setError] = useState('');

  // 放槍者候選：扣掉贏家本人
  const loserCandidates = players.filter((p) => p.id !== winnerId);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');

    if (!winnerId) {
      setError('請選擇贏家');
      return;
    }
    if (!selfDraw && !loserId) {
      setError('放槍時必須選擇放槍者');
      return;
    }
    if (!selfDraw && loserId === winnerId) {
      setError('放槍者不能是贏家');
      return;
    }

    onAdd({
      winnerId,
      tai,
      selfDraw,
      loserId: selfDraw ? null : loserId,
    });

    // 重置（保留贏家與台數，方便連續輸入）
    setLoserId('');
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h2>新增一局</h2>

      <label className="field">
        <span>贏家</span>
        <select
          value={winnerId}
          onChange={(e) => {
            const newWinnerId = e.target.value;
            setWinnerId(newWinnerId);
            // 若舊放槍者剛好是新贏家，dropdown 會濾掉它但 state 仍殘留舊值，
            // 會造成錯誤狀態，這裡直接重置。
            if (loserId === newWinnerId) {
              setLoserId('');
            }
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

      <div className="row">
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
              </option>
            ))}
          </select>
        </label>
      )}

      {error && <p className="error">{error}</p>}

      <button type="submit" className="primary">
        新增並算分
      </button>
    </form>
  );
}
