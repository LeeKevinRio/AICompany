// 通用 Bottom Sheet（視覺規範 8-6）。點 backdrop 關閉。
import type { ReactNode } from 'react';
import { useEffect, useId } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

export function BottomSheet({ open, onClose, title, children }: Props) {
  // 供 aria-labelledby 指向標題的穩定 id。
  const titleId = useId();

  // 開啟時鎖背景捲動
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open) return null;

  return (
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
    </div>
  );
}
