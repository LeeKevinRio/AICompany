// v2.4（批次 3）：中途換人面板——牌局詳情「編輯本場設定」內的換人入口。
// 動線：選離場座位 → 輸入接手者名字 / 從名冊選 → 確認自第 N+1 局起生效（N=當前局數）。
// 防呆：fromRoundIndex 一律由 hook 鎖成當前已記局數，不允許改寫過去局的歸屬。
import { useState } from 'react';
import type { Player, RosterPlayer } from '../types';
import { PlayerAvatar } from './PlayerAvatar';

interface Props {
  /** 當前在座者（每座位當下佔用者，供選座位與顯示「誰離場」）。 */
  players: Player[];
  roster: RosterPlayer[];
  /** 目前已記局數＝換人生效的 fromRoundIndex（自第 roundCount+1 局起）。 */
  roundCount: number;
  onSubstitute: (seatId: string, name: string, rosterId?: string) => void;
}

export function SubstitutionPanel({ players, roster, roundCount, onSubstitute }: Props) {
  const [seatId, setSeatId] = useState('');
  const [name, setName] = useState('');
  const [rosterId, setRosterId] = useState<string | undefined>(undefined);

  const outgoing = players.find((p) => p.id === seatId);
  const canSubmit = seatId !== '' && name.trim() !== '';

  function reset() {
    setSeatId('');
    setName('');
    setRosterId(undefined);
  }

  function pickRoster(rp: RosterPlayer) {
    setName(rp.name);
    setRosterId(rp.id);
  }

  function handleNameInput(v: string) {
    setName(v);
    // 手動改名 → 解除名冊連結（與開桌 sheet 一致，避免名字與名冊不符卻仍掛 rosterId）。
    setRosterId(undefined);
  }

  function handleSubmit() {
    if (!canSubmit) return;
    onSubstitute(seatId, name.trim(), rosterId);
    reset();
  }

  return (
    <div className="subst-panel">
      <h3 className="rules-heading">中途換人</h3>
      <p className="setting-hint">
        選擇離場座位換成新玩家。自第 {roundCount + 1} 局起生效；之前 {roundCount} 局仍歸
        {outgoing ? `〈${outgoing.name}〉` : '前一位'}，接手者從接手局起自成一帳。
      </p>

      <div className="open-dealer-grid">
        {players.map((p, i) => {
          const selected = seatId === p.id;
          return (
            <button
              key={p.id}
              type="button"
              className={`open-dealer-btn${selected ? ' selected' : ''}`}
              aria-pressed={selected}
              onClick={() => setSeatId(selected ? '' : p.id)}
            >
              玩家 {i + 1}·{p.name}
            </button>
          );
        })}
      </div>

      {seatId && (
        <>
          <label className="field" style={{ display: 'block', marginTop: 12 }}>
            <span>接手者名字</span>
            <input
              type="text"
              value={name}
              maxLength={12}
              placeholder="輸入接手者名字"
              onChange={(e) => handleNameInput(e.target.value)}
            />
          </label>

          {roster.length > 0 && (
            <>
              <span className="field" style={{ display: 'block' }}>
                <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
                  名冊（點選帶入）
                </span>
              </span>
              <div className="known-player-chips">
                {roster.map((rp, i) => {
                  const selected = rosterId === rp.id;
                  return (
                    <button
                      key={rp.id}
                      type="button"
                      className={`known-chip has-avatar${selected ? ' selected' : ''}`}
                      aria-pressed={selected}
                      onClick={() => pickRoster(rp)}
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

          <p className="subst-confirm">
            <strong>{outgoing?.name ?? '—'}</strong> ↓ 換成{' '}
            <strong>{name.trim() || '（未填）'}</strong>，自第 {roundCount + 1} 局起。
          </p>
          <button
            className="primary"
            style={{ width: '100%' }}
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            確認換人
          </button>
        </>
      )}
    </div>
  );
}
