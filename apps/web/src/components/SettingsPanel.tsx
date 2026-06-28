// 場內設定面板：本場底/台金額、4 位玩家名字，以及開桌規則（自摸加台 / 東錢）。
import type { Player, SessionRules, Settings } from '../types';
import { RulesFields } from './RulesFields';

interface Props {
  settings: Settings;
  players: Player[];
  rules: SessionRules;
  hasRounds: boolean;
  onChangeSettings: (s: Settings) => void;
  onChangePlayerName: (playerId: string, name: string) => void;
  onChangeRules: (r: SessionRules) => void;
}

// 把輸入轉成非負整數：非數字視為 0，負數歸 0，小數無條件捨去。
function toNonNegInt(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0;
}

export function SettingsPanel({
  settings,
  players,
  rules,
  hasRounds,
  onChangeSettings,
  onChangePlayerName,
  onChangeRules,
}: Props) {
  return (
    <section className="card">
      <h2>本場設定</h2>
      <div className="row">
        <label className="field">
          <span>底</span>
          <input
            type="number"
            min={0}
            className="tabular"
            value={settings.base}
            onChange={(e) => onChangeSettings({ ...settings, base: toNonNegInt(e.target.value) })}
          />
        </label>
        <label className="field">
          <span>每台</span>
          <input
            type="number"
            min={0}
            className="tabular"
            value={settings.tai}
            onChange={(e) => onChangeSettings({ ...settings, tai: toNonNegInt(e.target.value) })}
          />
        </label>
      </div>

      <h3>玩家</h3>
      <div className="players-grid">
        {players.map((p, i) => (
          <label className="field" key={p.id}>
            <span>玩家 {i + 1}</span>
            <input
              type="text"
              value={p.name}
              maxLength={12}
              onChange={(e) => onChangePlayerName(p.id, e.target.value)}
            />
          </label>
        ))}
      </div>

      <h3>規則</h3>
      {hasRounds && (
        <p className="setting-hint" style={{ color: 'var(--color-warn)' }}>
          ⚠ 已有記錄，調整規則會重新計算所有局次的分數。
        </p>
      )}
      <RulesFields rules={rules} onChange={onChangeRules} />
    </section>
  );
}
