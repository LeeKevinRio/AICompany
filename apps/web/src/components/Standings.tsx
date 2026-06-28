// 本場每人累計輸贏（結算頁用）。淨額含自摸付出的東錢；另顯示公基金累計。
import type { Player, Round, SessionRules, Settings } from '../types';
import { settleSession } from '../scoring/scoring';
import { Amount } from './ui';

interface Props {
  rounds: Round[];
  players: Player[];
  settings: Settings;
  rules: SessionRules;
}

export function Standings({ rounds, players, settings, rules }: Props) {
  // settleSession 在資料於執行期被改成非法值時會 throw；
  // 這裡輕量防護，避免讓整個 app 因單一元件 render 例外而白畫面。
  let net: Record<string, number>;
  let kitty = 0;
  try {
    const settled = settleSession(rounds, players, settings, rules);
    net = settled.net;
    kitty = settled.kitty;
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
    .map((p) => ({ player: p, amount: net[p.id] ?? 0 }))
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
      {kitty > 0 && (
        <div className="kitty-row">
          <span>公基金（東錢累計）</span>
          <span className="tabular">${kitty.toLocaleString('en-US')}</span>
        </div>
      )}
    </section>
  );
}
