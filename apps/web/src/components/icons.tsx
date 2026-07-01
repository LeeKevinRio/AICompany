// Tab bar 與通用 SVG 圖示。stroke-width 1.5，24×24，沿用 currentColor 上色。
import type { SVGProps } from 'react';

const base = {
  width: 24,
  height: 24,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

/** 牌局：一張側視角麻將牌 */
export function IconSessions(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props} className="tab-icon">
      <rect x="6" y="3" width="12" height="18" rx="2.5" />
      <line x1="9.5" y1="7" x2="14.5" y2="7" />
      <line x1="9.5" y1="11" x2="14.5" y2="11" />
      <circle cx="12" cy="16" r="1.4" />
    </svg>
  );
}

/** 玩家：單人半身輪廓 */
export function IconPlayers(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props} className="tab-icon">
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" />
    </svg>
  );
}

/** 設定：齒輪。預設套 tab-icon class，呼叫端可用 className 覆蓋（如牌局詳情右上角按鈕）。 */
export function IconSettings({ className = 'tab-icon', ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props} className={className}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8 6 18M18 6l1.8-1.8" />
    </svg>
  );
}
