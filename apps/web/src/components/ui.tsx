// 通用展示元件與小工具：金額顯示、玩家代表色對應。
import { formatSigned } from '../scoring/timeline';

/** 4 位玩家代表色 token（依出場順序 p1~p4 對應 a~d） */
export const PLAYER_COLOR_VARS = [
  'var(--color-player-a)',
  'var(--color-player-b)',
  'var(--color-player-c)',
  'var(--color-player-d)',
] as const;

/** 依玩家在 players 陣列中的索引取代表色 */
export function playerColor(index: number): string {
  return PLAYER_COLOR_VARS[index % PLAYER_COLOR_VARS.length];
}

interface AmountProps {
  value: number;
  className?: string;
}

/**
 * 金額顯示：自動帶正負號、千位逗號、語意色（綠贏/紅輸/灰零），tabular-nums。
 * 全站金額顯示都走這個元件，確保語意色與格式一致。
 */
export function Amount({ value, className }: AmountProps) {
  const tone = value > 0 ? 'win' : value < 0 ? 'lose' : 'zero';
  return (
    <span className={`amt ${tone}${className ? ` ${className}` : ''}`}>
      {formatSigned(value)}
    </span>
  );
}
