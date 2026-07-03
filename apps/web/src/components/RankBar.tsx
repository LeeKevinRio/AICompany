// 即時排名條（記局頁頂部）。依視覺規範 7-2。
// 含企劃 5-3 排名動畫：金額 rolling number、排名變動箭頭、贏家亮起。
import { useEffect, useRef, useState } from 'react';
import type { Player, RosterPlayer, Round, SessionRules, Settings } from '../types';
import { settleSession } from '../scoring/scoring';
import { formatSigned } from '../scoring/timeline';
import { resolvePlayerVisual } from './ui';
import { PlayerAvatar } from './PlayerAvatar';

interface Props {
  rounds: Round[];
  players: Player[];
  settings: Settings;
  rules: SessionRules;
  /** 玩家名冊：用來決定每位玩家的 colorIndex（統一同色）與頭像（5-3-c / 5-6）。 */
  roster: RosterPlayer[];
  /** v2.1 建議做：單場輸贏警戒線（0=關閉）。淨額輸超過此值時該行紅色警示。 */
  loseAlertThreshold?: number;
}

interface Ranked {
  player: Player;
  colorIndex: number;
  avatar?: string;
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
  alert,
}: {
  item: Ranked;
  arrow: 'up' | 'down' | 'same';
  flash: boolean;
  alert: boolean;
}) {
  const shown = useRolling(item.amount);
  const tone = shown > 0 ? 'win' : shown < 0 ? 'lose' : 'zero';
  const arrowChar = arrow === 'up' ? '↑' : arrow === 'down' ? '↓' : '─';
  // 正確的英文序數後綴（避免 2st/3st/4st）。
  const ordinal = item.rank === 1 ? '1st' : item.rank === 2 ? '2nd' : item.rank === 3 ? '3rd' : `${item.rank}th`;
  return (
    <div className={`rank-row${flash ? ' winner-flash' : ''}${alert ? ' lose-alert' : ''}`}>
      {/* 5-3-c 選項 2：移除 4px 色條，改由 28px 頭像的邊框色代表玩家色 */}
      <PlayerAvatar
        name={item.player.name}
        avatar={item.avatar}
        colorIndex={item.colorIndex}
        size={28}
        className="rank-avatar"
      />
      <span className="rank-name">
        {alert && <span className="lose-alert-dot" aria-label="超過輸贏警戒線">⚠</span>}
        {item.player.name}
      </span>
      <span className={`rank-amt amt ${tone}`}>{formatSigned(shown)}</span>
      <span className="rank-meta">
        <span>{ordinal}</span>
        <span className={`rank-arrow ${arrow}`}>{arrowChar}</span>
      </span>
    </div>
  );
}

export function RankBar({
  rounds,
  players,
  settings,
  rules,
  roster,
  loseAlertThreshold = 0,
}: Props) {
  // 排名以「淨額」呈現（含自摸付出的東錢），與結算一致。
  let totals: Record<string, number>;
  let kitty = 0;
  try {
    const settled = settleSession(rounds, players, settings, rules);
    totals = settled.net;
    kitty = settled.kitty;
  } catch {
    totals = {};
    for (const p of players) totals[p.id] = 0;
  }

  // 依累計排序。colorIndex / avatar 統一由 resolvePlayerVisual 依名冊順序決定（5-6）。
  const ranked: Ranked[] = players
    .map((player, i) => {
      const { colorIndex, avatar } = resolvePlayerVisual(player, i, roster);
      return {
        player,
        colorIndex,
        avatar,
        amount: totals[player.id] ?? 0,
        rank: 0,
      };
    })
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
          alert={loseAlertThreshold > 0 && item.amount <= -loseAlertThreshold}
        />
      ))}
      {kitty > 0 && (
        <div className="rank-kitty">
          <span>公基金</span>
          <span className="tabular">${kitty.toLocaleString('en-US')}</span>
        </div>
      )}
    </div>
  );
}
