// 本場每人累計輸贏。
import type { Player, Round, Settings } from '../types';
import { scoreSession } from '../scoring/scoring';

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

  return (
    <section className="card">
      <h2>本場累計</h2>
      <div className="standings">
        {players.map((p) => {
          const v = total[p.id] ?? 0;
          const cls = v > 0 ? 'win' : v < 0 ? 'lose' : '';
          return (
            <div className="standing-row" key={p.id}>
              <span className="standing-name">{p.name}</span>
              <span className={`standing-amt ${cls}`}>
                {v > 0 ? '+' : ''}
                {v}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
