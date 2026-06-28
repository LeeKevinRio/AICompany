// 本場每人累計輸贏（結算頁用）。
import type { Player, Round, Settings } from '../types';
import { scoreSession } from '../scoring/scoring';
import { Amount } from './ui';

interface Props {
  rounds: Round[];
  players: Player[];
  settings: Settings;
}

export function Standings({ rounds, players, settings }: Props) {
  // scoreSession 在資料於執行期被改成非法值時會 throw；
  // 這裡輕量防護，避免讓整個 app 因單一元件 render 例外而白畫面。
  let total: ReturnType<typeof scoreSession>;
  try {
    total = scoreSession(rounds, players, settings);
  } catch (err) {
    console.error('計分失敗，本場資料異常：', err);
    return (
      <section className="card">
        <h2>本場累計</h2>
        <p className="error">本場資料異常，無法計分。</p>
      </section>
    );
  }

  const ranked = players
    .map((p) => ({ player: p, amount: total[p.id] ?? 0 }))
    .sort((a, b) => b.amount - a.amount);

  return (
    <section className="card">
      <h2>本場累計</h2>
      <ol className="round-list">
        {ranked.map(({ player, amount }, i) => (
          <li className="round-item" key={player.id}>
            <span className="round-no">{i + 1}</span>
            <span className="round-main">
              <strong>{player.name}</strong>
            </span>
            <Amount value={amount} />
          </li>
        ))}
      </ol>
    </section>
  );
}
