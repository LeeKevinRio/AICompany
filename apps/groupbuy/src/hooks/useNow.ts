// 讓依賴「當下時間」的畫面（倒數、過期判定）每隔一段時間自動刷新。
// 刻意只做輕量的 UI 重繪 tick，不輪詢任何後端、不做精準到秒的 timer。
import { useEffect, useState } from 'react';

/**
 * 回傳當下 epoch 毫秒，並每 intervalMs（預設 60 秒）觸發一次重繪，
 * 讓倒數 / 過期狀態隨時間更新。元件卸載時清除 timer。
 */
export function useNow(intervalMs = 60_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}
