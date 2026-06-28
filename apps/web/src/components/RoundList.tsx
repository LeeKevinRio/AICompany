// 每局明細：贏家、台數、自摸/放槍、放槍者、備註，以及該局贏家收多少。
import type { Player, Round, SessionRules, Settings } from '../types';
import { calcDong, calcUnitAmount, effectiveTai } from '../scoring/scoring';
import { formatSigned } from '../scoring/timeline';

interface Props {
  rounds: Round[];
  players: Player[];
  settings: Settings;
  rules: SessionRules;
  onRemove: (roundId: string) => void;
}

export function RoundList({ rounds, players, settings, rules, onRemove }: Props) {
  const nameOf = (id: string | null) => players.find((p) => p.id === id)?.name ?? '—';

  if (rounds.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon">🀄</div>
        <p className="empty-title">尚無紀錄</p>
        <p>切到「記局」開始第一局吧。</p>
      </div>
    );
  }

  return (
    <section className="card">
      <h2>每局明細</h2>
      <ol className="round-list">
        {rounds.map((r, i) => {
          const eTai = effectiveTai(r, rules);
          const amount = calcUnitAmount(settings, eTai);
          const win = r.selfDraw ? amount * (players.length - 1) : amount;
          const bonus = r.selfDraw ? eTai - r.tai : 0;
          const dong = calcDong(r, rules);
          return (
            <li key={r.id} className="round-item">
              <span className="round-no">#{i + 1}</span>
              <span className="round-main">
                <strong>{nameOf(r.winnerId)}</strong> {r.tai}
                {bonus > 0 && <span className="round-bonus">+{bonus}</span>} 台{' '}
                {r.selfDraw ? '自摸' : `放槍（${nameOf(r.loserId)}）`}
                {dong > 0 && <span className="round-dong">東錢 ${dong}</span>}
                {r.note && <span className="round-note">📝 {r.note}</span>}
              </span>
              <span className="round-amt">{formatSigned(win)}</span>
              <button
                className="link danger"
                onClick={() => onRemove(r.id)}
                aria-label="刪除此局"
              >
                刪除
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
