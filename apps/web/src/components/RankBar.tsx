// 即時排名條（記局頁頂部）。依視覺規範 7-2。
// 含企劃 5-3 排名動畫：金額 rolling number、排名變動箭頭、贏家亮起。
import { useEffect, useRef, useState } from 'react';
import type { Player, Round, Settings } from '../types';
import { scoreSession } from '../scoring/scoring';
import { formatSigned } from '../scoring/timeline';
import { playerColor } from './ui';

interface Props {
  rounds: Round[];
  players: Player[];
  settings: Settings;
}

interface Ranked {
  player: Player;
  colorIndex: number;
  amount: number;
  rank: number;
}

/** 數字滾動：在 prefers-reduced-motion 下直接顯示終值。 */
function useRolling(target: number): number {
  const [display, setDisplay] = useState(target);
  const fromRef = useRef(target);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      fromRef.current = target;
      setDisplay(target);
      return;
    }

    const from = fromRef.current;
    if (from === target) return;
    const start = performance.now();
    const DURATION = 400;

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / DURATION);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - t, 3);
      const val = Math.round(from + (target - from) * eased);
      setDisplay(val);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = target;
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      fromRef.current = target;
    };
  }, [target]);

  return display;
}

function RankRow({
  item,
  arrow,
  flash,
}: {
  item: Ranked;
  arrow: 'up' | 'down' | 'same';
  flash: boolean;
}) {
  const shown = useRolling(item.amount);
  const tone = shown > 0 ? 'win' : shown < 0 ? 'lose' : 'zero';
  const arrowChar = arrow === 'up' ? '↑' : arrow === 'down' ? '↓' : '─';
  // 正確的英文序數後綴（避免 2st/3st/4st）。
  const ordinal = item.rank === 1 ? '1st' : item.rank === 2 ? '2nd' : item.rank === 3 ? '3rd' : `${item.rank}th`;
  return (
    <div className={`rank-row${flash ? ' winner-flash' : ''}`}>
      <span className="rank-color-bar" style={{ background: playerColor(item.colorIndex) }} />
      <span className="rank-name">{item.player.name}</span>
      <span className={`rank-amt amt ${tone}`}>{formatSigned(shown)}</span>
      <span className="rank-meta">
        <span>{ordinal}</span>
        <span className={`rank-arrow ${arrow}`}>{arrowChar}</span>
      </span>
    </div>
  );
}

export function RankBar({ rounds, players, settings }: Props) {
  let totals: Record<string, number>;
  try {
    totals = scoreSession(rounds, players, settings);
  } catch {
    totals = {};
    for (const p of players) totals[p.id] = 0;
  }

  // 依累計排序
  const ranked: Ranked[] = players
    .map((player, i) => ({
      player,
      colorIndex: i,
      amount: totals[player.id] ?? 0,
      rank: 0,
    }))
    .sort((a, b) => b.amount - a.amount)
    .map((r, i) => ({ ...r, rank: i + 1 }));

  // 記錄上一輪排名，算箭頭方向
  const prevRankRef = useRef<Record<string, number>>({});
  const arrows: Record<string, 'up' | 'down' | 'same'> = {};
  for (const r of ranked) {
    const prev = prevRankRef.current[r.player.id];
    arrows[r.player.id] =
      prev === undefined || prev === r.rank ? 'same' : prev > r.rank ? 'up' : 'down';
  }

  // 本局贏家（最後一局）→ 亮起
  const lastWinnerId = rounds.length > 0 ? rounds[rounds.length - 1].winnerId : null;
  const [flashId, setFlashId] = useState<string | null>(null);
  const roundsLenRef = useRef(rounds.length);

  useEffect(() => {
    if (rounds.length > roundsLenRef.current && lastWinnerId) {
      setFlashId(lastWinnerId);
      const t = setTimeout(() => setFlashId(null), 800);
      roundsLenRef.current = rounds.length;
      return () => clearTimeout(t);
    }
    roundsLenRef.current = rounds.length;
  }, [rounds.length, lastWinnerId]);

  // render 後更新 prevRank（供下次比較）
  useEffect(() => {
    const next: Record<string, number> = {};
    for (const r of ranked) next[r.player.id] = r.rank;
    prevRankRef.current = next;
  });

  return (
    <div className="rank-bar">
      {ranked.map((item) => (
        <RankRow
          key={item.player.id}
          item={item}
          arrow={arrows[item.player.id]}
          flash={flashId === item.player.id}
        />
      ))}
    </div>
  );
}
