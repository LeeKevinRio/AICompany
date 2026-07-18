// v2.1：開桌規則設定欄位（自摸加台 + 東錢）。
// 共用於「開桌 Bottom Sheet」與「牌局內規則調整」，確保兩處 UI 一致。
import type { SessionRules } from '../types';
import { toNonNegInt } from '../utils';

interface Props {
  rules: SessionRules;
  onChange: (next: SessionRules) => void;
}

/** ON/OFF 開關（規範第 6 節提示：ON 用 primary，OFF 用 border）。 */
function Toggle({
  on,
  onToggle,
  label,
}: {
  on: boolean;
  onToggle: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      className={`toggle${on ? ' on' : ''}`}
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onToggle}
    >
      <span className="toggle-knob" />
    </button>
  );
}

export function RulesFields({ rules, onChange }: Props) {
  const selfDrawOn = rules.selfDrawBonusTai > 0;
  const dongOn = rules.selfDrawDongAmount > 0;
  const eyeTileOn = rules.eyeTileEnabled;
  const dealerOn = rules.dealerEnabled;

  return (
    <div className="rules-fields">
      {/* 自摸加台 */}
      <div className="rule-row">
        <div className="rule-row-main">
          <span className="rule-name">自摸加台</span>
          <Toggle
            on={selfDrawOn}
            label="自摸加台開關"
            // 關 → 0；開 → 回到 1（常見值）。
            onToggle={() =>
              onChange({ ...rules, selfDrawBonusTai: selfDrawOn ? 0 : 1 })
            }
          />
        </div>
        <label className="rule-input">
          <span>加</span>
          <input
            type="number"
            min={0}
            className="tabular"
            disabled={!selfDrawOn}
            value={rules.selfDrawBonusTai}
            onChange={(e) =>
              onChange({ ...rules, selfDrawBonusTai: toNonNegInt(e.target.value) })
            }
          />
          <span>台</span>
        </label>
      </div>

      {/* 東錢 */}
      <div className="rule-row">
        <div className="rule-row-main">
          <span className="rule-name">東錢（自摸付公基金）</span>
          <Toggle
            on={dongOn}
            label="東錢開關"
            // 關 → 0；開 → 回到 100（預設）。
            onToggle={() =>
              onChange({ ...rules, selfDrawDongAmount: dongOn ? 0 : 100 })
            }
          />
        </div>
        <label className="rule-input">
          <span>每次</span>
          <input
            type="number"
            min={0}
            className="tabular"
            disabled={!dongOn}
            value={rules.selfDrawDongAmount}
            onChange={(e) =>
              onChange({ ...rules, selfDrawDongAmount: toNonNegInt(e.target.value) })
            }
          />
          <span>元</span>
        </label>
      </div>

      {/* 眼牌（v2.2）：被標記為眼牌的局額外加台，自摸/放槍都算，照一般支付規則。 */}
      <div className="rule-row">
        <div className="rule-row-main">
          <span className="rule-name">眼牌</span>
          <Toggle
            on={eyeTileOn}
            label="眼牌開關"
            // 關 → enabled=false；開 → enabled=true 並把台數補回 1（常見值）。
            onToggle={() =>
              onChange({
                ...rules,
                eyeTileEnabled: !eyeTileOn,
                eyeTileTai: !eyeTileOn && rules.eyeTileTai <= 0 ? 1 : rules.eyeTileTai,
              })
            }
          />
        </div>
        <label className="rule-input">
          <span>加</span>
          <input
            type="number"
            min={0}
            className="tabular"
            disabled={!eyeTileOn}
            value={rules.eyeTileTai}
            onChange={(e) =>
              onChange({ ...rules, eyeTileTai: toNonNegInt(e.target.value) })
            }
          />
          <span>台</span>
        </label>
      </div>

      {/* 連莊 / 圈風（v2.3）：總開關；做莊 1 台、連 N 拉 N = 2N 台、只牽涉莊家的支付（CEO 拍板固定值）。 */}
      <div className="rule-row">
        <div className="rule-row-main">
          <span className="rule-name">連莊 / 圈風</span>
          <Toggle
            on={dealerOn}
            label="連莊系統開關"
            onToggle={() =>
              onChange({
                ...rules,
                dealerEnabled: !dealerOn,
                // 開啟時把固定加台補回 CEO 拍板值（若先前為 0）。
                dealerBaseTai: !dealerOn && rules.dealerBaseTai <= 0 ? 1 : rules.dealerBaseTai,
                dealerStreakTaiPerStreak:
                  !dealerOn && rules.dealerStreakTaiPerStreak <= 0
                    ? 2
                    : rules.dealerStreakTaiPerStreak,
              })
            }
          />
        </div>
        <span className="rule-fixed-note">做莊 +1 台、連 N 拉 N +2N 台</span>
      </div>

      <p className="setting-hint">
        自摸者額外付一筆東錢進「公基金」，獨立累計、不併入四人輸贏。
        眼牌則是記局時勾選、額外加台，自摸/放槍都算。
        連莊開啟後，開桌需選首莊，莊家胡牌 / 流局則連莊，加台只影響與莊家的輸贏。
      </p>
    </div>
  );
}
