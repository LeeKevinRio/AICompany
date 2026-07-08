// 載入畫面：依視覺規範第 5 節。
// 最短顯示 1500ms（避免資料讀太快閃過）；資料未就緒最長等 3000ms 後仍進主畫面。
import { useEffect, useState } from 'react';

interface Props {
  /** 資料是否已讀取完畢 */
  dataReady: boolean;
  /** Splash 結束（淡出完成）時呼叫 */
  onDone: () => void;
}

const MIN_DISPLAY = 1500;
const MAX_WAIT = 3000;
const FADE_MS = 300;

export function Splash({ dataReady, onDone }: Props) {
  const [hiding, setHiding] = useState(false);
  const [showLoading, setShowLoading] = useState(false);
  const [startedAt] = useState(() => Date.now());

  // 超過 MIN_DISPLAY 後資料還沒好，顯示「讀取中…」
  useEffect(() => {
    const t = setTimeout(() => setShowLoading(true), MIN_DISPLAY);
    return () => clearTimeout(t);
  }, []);

  // 判斷何時開始淡出：max(MIN_DISPLAY, 資料就緒時間)，且不超過 MAX_WAIT。
  useEffect(() => {
    if (hiding) return;
    const elapsed = Date.now() - startedAt;
    const canHide = dataReady && elapsed >= MIN_DISPLAY;
    if (canHide) {
      setHiding(true);
      return;
    }
    // 還不能淡出：排程在「補滿 MIN_DISPLAY」或「MAX_WAIT 上限」較早者觸發。
    const waitMore = dataReady
      ? MIN_DISPLAY - elapsed
      : Math.min(MIN_DISPLAY, MAX_WAIT) - elapsed;
    const hardCap = MAX_WAIT - elapsed;
    const delay = Math.max(0, Math.min(waitMore, hardCap));
    const t = setTimeout(() => setHiding(true), delay);
    return () => clearTimeout(t);
  }, [dataReady, hiding, startedAt]);

  // 淡出動畫結束後通知 parent 卸載
  useEffect(() => {
    if (!hiding) return;
    const t = setTimeout(onDone, FADE_MS);
    return () => clearTimeout(t);
  }, [hiding, onDone]);

  return (
    <div className={`splash${hiding ? ' hiding' : ''}`} aria-hidden={hiding}>
      <div className="splash-tile">麻</div>
      <h1 className="splash-title">MaJong</h1>
      <p className="splash-subtitle">台灣麻將，局局記分。</p>
      {showLoading && !dataReady && <p className="splash-loading">讀取中…</p>}
    </div>
  );
}
