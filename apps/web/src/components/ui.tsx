// 通用展示元件與小工具：金額顯示、玩家代表色對應。
import { formatSigned } from '../scoring/timeline';
import type { Player, RosterPlayer } from '../types';

/** 4 位玩家代表色 token（依出場順序 p1~p4 對應 a~d） */
export const PLAYER_COLOR_VARS = [
  'var(--color-player-a)',
  'var(--color-player-b)',
  'var(--color-player-c)',
  'var(--color-player-d)',
] as const;

/**
 * 4 位玩家代表色的實際 hex。
 * ⚠️ 必須與 styles.css :root 的 --color-player-a~d 同步！改色時兩處要一起改，
 * 否則字母 fallback 頭像底色會與畫面上其他玩家色元素撞不同色。
 * 用途：字母 fallback 頭像的底色需要以 rgba 疊層計算，且 ShareCard 走 html2canvas
 * 光柵化——html2canvas 1.4.1 不支援 color-mix()，故底色一律用可被光柵化的 rgba 字面值。
 */
export const PLAYER_COLOR_HEX = ['#5b9cf6', '#f6c55b', '#c47ef5', '#5bcfc4'] as const;

/** 依玩家在 players 陣列中的索引取代表色 */
export function playerColor(index: number): string {
  return PLAYER_COLOR_VARS[index % PLAYER_COLOR_VARS.length];
}

/**
 * colorIndex 統一分配（規範 5-6 第 5 條）：同一玩家在名冊 / 排名條 / 圖卡三處同色。
 *
 * 規則：優先以「名冊順序 mod 4」決定（與 PlayersPage 的 rosterColorIndex 一致）；
 * 未連結名冊（rosterId 為空）的玩家 fallback 用其座位順序 seatIndex，
 * 讓純歷史玩家仍有穩定顏色、不會全部撞成同一色。
 *
 * 回傳同時附上該玩家的 avatar（源自 RosterPlayer；未連結者為 undefined），
 * 讓 RankBar / ShareCard 不必各自再查一次名冊。
 */
export function resolvePlayerVisual(
  player: Player,
  seatIndex: number,
  roster: RosterPlayer[],
): { colorIndex: number; avatar?: string } {
  if (player.rosterId) {
    const idx = roster.findIndex((r) => r.id === player.rosterId);
    if (idx >= 0) {
      return { colorIndex: idx % 4, avatar: roster[idx].avatar };
    }
  }
  return { colorIndex: seatIndex % 4, avatar: undefined };
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
