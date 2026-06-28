// 趣味統計標籤（企劃 5-2）+ 本場統計摘要。放走勢圖頁下方。
import type { Player, Round, Settings } from '../types';
import { calcSessionHighlights } from '../scoring/timeline';

interface Props {
  rounds: Round[];
  players: Player[];
  settings: Settings;
}

const EMOJI: Record<string, string> = {
  champion: '🏆',
  gunKing: '💥',
  selfDrawKing: '🀄',
  biggestRound: '🔥',
};

export function Highlights({ rounds, players, settings }: Props) {
  const { highlights, perPlayer } = calcSessionHighlights(rounds, players, settings);

  if (rounds.length === 0) return null;

  return (
    <>
      <section className="card">
        <h2>本場話題</h2>
        <div className="highlights">
          {highlights.map((h) => (
            <div className="highlight-card" key={h.key}>
              <div className="highlight-label">
                <span className="highlight-emoji">{EMOJI[h.key]}</span>
                {h.label}
              </div>
              <div className="highlight-name">{h.playerName ?? '—'}</div>
              <div className="highlight-detail">{h.detail}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>本場統計</h2>
        <ol className="round-list">
          {players.map((p) => {
            const s = perPlayer[p.id] ?? { wins: 0, selfDraws: 0, gunned: 0 };
            return (
              <li className="round-item" key={p.id}>
                <span className="round-main">
                  <strong>{p.name}</strong>
                </span>
                <span className="muted" style={{ fontSize: 13 }}>
                  胡 {s.wins} · 自摸 {s.selfDraws} · 放槍 {s.gunned}
                </span>
              </li>
            );
          })}
        </ol>
      </section>
    </>
  );
}
