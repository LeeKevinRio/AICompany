// 通用 Bottom Sheet（視覺規範 8-6）。點 backdrop 關閉。
//
// #1：與 Fab 相同的理由——.sheet-backdrop 若渲染在 .page 內，會被 .page 的
// `animation: page-fade` 建立的 stacking context 困住，z-index 200 只在 .page 內有效，
// 蓋不過已 portal 到 body 的 FAB（z-index 120）。改用 createPortal 掛到 document.body，
// 讓 sheet-backdrop 與 FAB 同在 root stacking context，200 > 120，遮罩正確蓋住 FAB。
import type { ReactNode } from 'react';
import { useEffect, useId, useState } from 'react';
import { createPortal } from 'react-dom';

interface Props {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

export function BottomSheet({ open, onClose, title, children }: Props) {
  // 供 aria-labelledby 指向標題的穩定 id。
  const titleId = useId();
  // SSR / 初次 render 時 document 不一定可用；mounted 後才掛 portal（與 Fab 同寫法）。
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // 開啟時鎖背景捲動
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open || !mounted) return null;

  return createPortal(
    <div className="sheet-backdrop" onClick={onClose}>
      <div
        className="sheet"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
      >
        <div className="sheet-handle" />
        {title && <h2 id={titleId}>{title}</h2>}
        {children}
      </div>
    </div>,
    document.body,
  );
}
