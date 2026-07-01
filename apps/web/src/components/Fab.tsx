// 浮動「＋」新增鈕（FAB）。
//
// #2 加固重點：早期版本把 .fab 放在 .page 內，雖然 z-index(110) > tab-bar(100)，
// 但 .page 有 `animation: page-fade`——有 animation 的元素會建立自己的 stacking
// context，導致 .fab 的 z-index 只在 .page 內部有效；而 .page 本身 z-index 為 auto，
// 於是整個 .page（含 FAB）被排在同層 .tab-bar 之下，tab-bar 攔截了 FAB 的下半部點擊，
// 只剩露在 tab-bar 上緣的一小條可點。這正是「z-index 照理對、實際被蓋」的真因。
//
// 修法：用 React Portal 把 FAB 渲染到 document.body，徹底脫離 .page 的 stacking
// context；DOM 順序也在最後，z-index 拉到 120（高於 tab-bar 100、sheet-backdrop 200
// 之下）。這樣不論頁面動畫或巢狀層級如何，FAB 都在最上層、整顆可點。
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

interface Props {
  /** 無障礙標籤（如「新增牌局」） */
  label: string;
  onClick: () => void;
}

export function Fab({ label, onClick }: Props) {
  // SSR / 初次 render 時 document 不一定可用；mounted 後才掛 portal。
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  return createPortal(
    <button className="fab" aria-label={label} onClick={onClick}>
      ＋
    </button>,
    document.body,
  );
}
