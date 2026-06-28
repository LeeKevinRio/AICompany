// 場內設定面板：本場底/台金額，以及 4 位玩家名字。
import type { Player, Settings } from '../types';

interface Props {
  settings: Settings;
  players: Player[];
  onChangeSettings: (s: Settings) => void;
  onChangePlayerName: (playerId: string, name: string) => void;
}

// 把輸入轉成非負整數：非數字視為 0，負數歸 0，小數無條件捨去。
function toNonNegInt(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0;
}

export function SettingsPanel({
  settings,
  players,
  onChangeSettings,
  onChangePlayerName,
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
    </section>
  );
}
