// 每局明細：顯示贏家、台數、自摸/放槍、放槍者，以及該局贏家收多少。
import type { Player, Round, Settings } from '../types';
import { calcUnitAmount } from '../scoring/scoring';

interface Props {
  rounds: Round[];
  players: Player[];
  settings: Settings;
  onRemove: (roundId: string) => void;
}

export function RoundList({ rounds, players, settings, onRemove }: Props) {
  const nameOf = (id: string | null) => players.find((p) => p.id === id)?.name ?? '—';

  if (rounds.length === 0) {
    return (
      <section className="card">
        <h2>每局明細</h2>
        <p className="muted">尚無紀錄，從上方新增第一局。</p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>每局明細</h2>
      <ol className="round-list">
        {rounds.map((r, i) => {
          const amount = calcUnitAmount(settings, r.tai);
          const win = r.selfDraw ? amount * (players.length - 1) : amount;
          return (
            <li key={r.id} className="round-item">
              <span className="round-no">#{i + 1}</span>
              <span className="round-main">
                <strong>{nameOf(r.winnerId)}</strong> {r.tai} 台{' '}
                {r.selfDraw ? '自摸' : `放槍（${nameOf(r.loserId)}）`}
              </span>
              <span className="round-amt win">+{win}</span>
              <button className="link danger" onClick={() => onRemove(r.id)} aria-label="刪除此局">
                刪除
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
