// 統一玩家頭像元件（規範 5-4 / 5-6）。所有顯示頭像的場景（名冊、排名條、圖卡、
// 選擇器 preview、詳情頁）都走這個元件，不各自處理 fallback。
//
// 三種來源，依序判斷：
//   1. PNG 路徑（以 /avatars/ 開頭）→ <img>，載入失敗時真正 fallback 到字母頭像。
//   2. emoji（舊資料向下相容，短字串）→ 直接顯示 emoji 字元。
//   3. 空 / undefined / null → 字母 fallback（名字首字 + 玩家代表色底/框）。
import { useState } from 'react';
import { PLAYER_COLOR_HEX, PLAYER_COLOR_VARS } from './ui';

interface Props {
  name: string;
  /** PNG 路徑（/avatars/…）、舊 emoji 字元，或空值（→ 字母 fallback） */
  avatar?: string;
  /** 0-3，對應 player-a/b/c/d 代表色 */
  colorIndex: number;
  /** 容器邊長（px） */
  size: number;
  /** 額外 class（各場景用不同 class 疊在共用 .player-avatar 上） */
  className?: string;
}

/**
 * emoji 頭像判定：非 PNG 路徑、且長度短（單一 emoji 可能由多個 code unit 組成，放寬到 4）。
 *
 * 限制：length <= 4 是以 JavaScript 字串的 UTF-16 code unit 計數，非「視覺上的 1 個字元」。
 * 多數常見 emoji（1~2 個 code unit）可通過；但複合 emoji——例如帶膚色修飾（👍🏽）、
 * 旗幟（🇹🇼 由兩個 regional indicator 組成）、ZWJ 組合（👨‍👩‍👧）——其 code unit 數常 > 4，
 * 會被判為非 emoji 而落入字母 fallback。舊資料頭像為單一基本 emoji，此限制不影響現況；
 * #5 之後新資料一律用 PNG 路徑，故此分支僅供向下相容。
 */
function isEmoji(avatar: string): boolean {
  return !avatar.startsWith('/avatars/') && avatar.length > 0 && avatar.length <= 4;
}

export function PlayerAvatar({ name, avatar, colorIndex, size, className }: Props) {
  // PNG 載入失敗時切到字母 fallback（不是只隱藏 img 留白）。
  const [imgFailed, setImgFailed] = useState(false);

  const idx = ((colorIndex % 4) + 4) % 4; // 防負數
  const colorVar = PLAYER_COLOR_VARS[idx];
  const colorHex = PLAYER_COLOR_HEX[idx];
  const fontSize = Math.round(size * 0.45);

  const baseClass = `player-avatar${className ? ` ${className}` : ''}`;
  const isPng = !!avatar && avatar.startsWith('/avatars/');

  // PNG 頭像（未失敗）
  if (isPng && !imgFailed) {
    return (
      <span
        className={baseClass}
        style={{ width: size, height: size, borderColor: colorVar }}
        role="img"
        aria-label={name}
      >
        {/* 語意交給外層 span（role=img + aria-label），內部 img 設為裝飾性避免重複朗讀 */}
        <img src={avatar} alt="" onError={() => setImgFailed(true)} />
      </span>
    );
  }

  // emoji（舊資料向下相容）——只有非 PNG 路徑才會走到這裡
  if (avatar && !isPng && isEmoji(avatar)) {
    return (
      <span
        className={baseClass}
        style={{ width: size, height: size, fontSize: fontSize + 2, borderColor: colorVar }}
        aria-label={name}
      >
        {avatar}
      </span>
    );
  }

  // 字母 fallback（空值、null，或 PNG 載入失敗）。
  // 底色用玩家色 rgba 疊層字面值——html2canvas（ShareCard）不支援 color-mix()，
  // 故不用 color-mix，改以 rgba 直接組出 opacity 0.22 的底色，圖卡光柵化才不會破。
  return (
    <span
      className={baseClass}
      style={{
        width: size,
        height: size,
        borderColor: colorVar,
        background: hexToRgba(colorHex, 0.22),
        fontSize,
        color: colorVar,
        fontWeight: 700,
      }}
      aria-label={name}
    >
      {name.slice(0, 1) || '?'}
    </span>
  );
}

/** #rrggbb → rgba(r,g,b,a)。供字母 fallback 底色使用（html2canvas 可光柵化）。 */
function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
