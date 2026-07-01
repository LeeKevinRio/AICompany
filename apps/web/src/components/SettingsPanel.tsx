// 本場設定編輯面板：本場底/台金額、4 位玩家名字，以及開桌規則（自摸加台 / 東錢）。
// #1：場內不再常駐顯示，改由牌局詳情右上角齒輪開 BottomSheet 載入此面板編輯。
import type { Player, SessionRules, Settings } from '../types';
import { RulesFields } from './RulesFields';
import { toNonNegInt } from '../utils';

interface Props {
  settings: Settings;
  players: Player[];
  rules: SessionRules;
  hasRounds: boolean;
  onChangeSettings: (s: Settings) => void;
  onChangePlayerName: (playerId: string, name: string) => void;
  onChangeRules: (r: SessionRules) => void;
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
    <div>
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

      <h3 className="rules-heading">玩家</h3>
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

      <h3 className="rules-heading">規則</h3>
      {hasRounds && (
        <p className="setting-hint" style={{ color: 'var(--color-warn)' }}>
          ⚠ 已有記錄，調整規則會重新計算所有局次的分數。
        </p>
      )}
      <RulesFields rules={rules} onChange={onChangeRules} />
    </div>
  );
}
