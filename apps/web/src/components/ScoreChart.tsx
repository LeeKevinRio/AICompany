// 走勢圖外層：以 React.lazy 動態載入 recharts（企劃技術風險：避免拖慢 PWA 首載）。
import { lazy, Suspense } from 'react';
import type { Player, Round, Settings } from '../types';
import { buildCumulativeTimeline } from '../scoring/timeline';

const ScoreChartInner = lazy(() => import('./ScoreChartInner'));

interface Props {
  rounds: Round[];
  players: Player[];
  settings: Settings;
}

export function ScoreChart({ rounds, players, settings }: Props) {
  const timeline = buildCumulativeTimeline(rounds, players, settings);

  if (rounds.length === 0) {
    return (
      <div className="chart-card">
        <div className="chart-loading">尚無局數，記一局就能看走勢。</div>
      </div>
    );
  }

  return (
    <div className="chart-card">
      <Suspense fallback={<div className="chart-loading">圖表載入中…</div>}>
        <ScoreChartInner timeline={timeline} players={players} />
      </Suspense>
    </div>
  );
}
