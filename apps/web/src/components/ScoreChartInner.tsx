// 走勢折線圖內層：直接 import recharts（會被 React.lazy 切成獨立 chunk）。
// 依視覺規範 7-3：4 玩家色、Y=0 基準線、tooltip、可點擊圖例 toggle。
import { useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TooltipProps } from 'recharts';
import type { Player } from '../types';
import type { TimelinePoint } from '../scoring/timeline';
import { formatSigned } from '../scoring/timeline';
import { playerColor } from './ui';

interface Props {
  timeline: TimelinePoint[];
  players: Player[];
}

// 把 TimelinePoint[] 攤平成 recharts 需要的扁平 row：{ round, p1, p2, ... }
function toChartData(timeline: TimelinePoint[]) {
  return timeline.map((pt) => ({
    round: pt.roundIndex,
    ...pt.cumulative,
  }));
}

function ChartTooltip({
  active,
  payload,
  label,
  players,
  hidden,
}: TooltipProps<number, string> & {
  players: Player[];
  hidden: Set<string>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="chart-tooltip">
      <div className="tt-title">第 {label} 局</div>
      {players.map((p) => {
        if (hidden.has(p.id)) return null;
        const row = payload.find((x) => x.dataKey === p.id);
        const v = typeof row?.value === 'number' ? row.value : 0;
        const tone = v > 0 ? 'win' : v < 0 ? 'lose' : 'zero';
        return (
          <div className="tt-row" key={p.id}>
            <span style={{ color: row?.color }}>{p.name}</span>
            <span className={`amt ${tone}`}>{formatSigned(v)}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function ScoreChartInner({ timeline, players }: Props) {
  const data = toChartData(timeline);
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  function toggle(id: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div>
      <div className="chart-legend">
        {players.map((p, i) => (
          <button
            key={p.id}
            className={`legend-item${hidden.has(p.id) ? ' off' : ''}`}
            onClick={() => toggle(p.id)}
          >
            <span className="legend-dot" style={{ background: playerColor(i) }} />
            {p.name}
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid
            stroke="var(--color-border)"
            strokeOpacity={0.5}
            vertical={false}
          />
          <XAxis
            dataKey="round"
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }}
            stroke="var(--color-border)"
          />
          <YAxis
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }}
            stroke="var(--color-border)"
            width={44}
          />
          <ReferenceLine
            y={0}
            stroke="var(--color-text-secondary)"
            strokeOpacity={0.7}
            strokeWidth={1.5}
          />
          <Tooltip
            content={<ChartTooltip players={players} hidden={hidden} />}
            cursor={{ stroke: 'var(--color-text-secondary)', strokeDasharray: '3 3', strokeOpacity: 0.7 }}
          />
          {players.map((p, i) => (
            <Line
              key={p.id}
              type="monotone"
              dataKey={p.id}
              name={p.name}
              stroke={playerColor(i)}
              strokeWidth={2.5}
              hide={hidden.has(p.id)}
              dot={{ r: 2.5, strokeWidth: 0 }}
              activeDot={{ r: 5, stroke: 'var(--color-surface)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
