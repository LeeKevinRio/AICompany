// 結算分享圖卡（企劃 5-1 / 視覺規範 7-4）。
// 用 html2canvas 把離畫面 DOM 轉 PNG 下載；html2canvas 以動態 import 載入，
// 避免拖慢首載（與 recharts 同樣考量）。
import { useRef, useState } from 'react';
import type { Player, Round, Session, Settings } from '../types';
import { settleSession } from '../scoring/scoring';
import { buildCumulativeTimeline, formatSigned } from '../scoring/timeline';
import { Sparkline } from './Sparkline';
import { playerColor } from './ui';

interface Props {
  session: Session;
  players: Player[];
  rounds: Round[];
  settings: Settings;
}

const RANK_BADGE = ['冠', '亞', '季', '殿'];

export function ShareCard({ session, players, rounds, settings }: Props) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // 分享圖卡顯示「淨額」（含自摸付出的東錢），與結算頁一致。
  let totals: Record<string, number>;
  try {
    totals = settleSession(rounds, players, settings, session.rules).net;
  } catch {
    totals = {};
    for (const p of players) totals[p.id] = 0;
  }

  const ranked = players
    .map((p, i) => ({ player: p, colorIndex: i, amount: totals[p.id] ?? 0 }))
    .sort((a, b) => b.amount - a.amount);

  const dateStr = new Date(session.createdAt).toLocaleDateString('zh-TW');
  const timeline = buildCumulativeTimeline(rounds, players, settings, session.rules);

  async function handleExport() {
    if (!cardRef.current) return;
    setBusy(true);
    setError('');
    try {
      const { default: html2canvas } = await import('html2canvas');
      const canvas = await html2canvas(cardRef.current, {
        backgroundColor: '#0a1209',
        scale: 2,
        logging: false,
      });
      // 大圖（scale=2）用 dataURL 會把整張 base64 字串留在記憶體，
      // 改用 Blob + objectURL，下載後 revoke 釋放。
      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, 'image/png'),
      );
      if (!blob) throw new Error('canvas.toBlob 回傳空值');

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `麻將戰績_${dateStr.replace(/\//g, '')}.png`;
      // Firefox 部分版本需 a 實際在 DOM 中才會觸發下載。
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('產生分享圖卡失敗：', err);
      setError('產生圖卡失敗，請稍後再試。');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>結算分享圖卡</h2>
      <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        產生一張 PNG 戰績圖卡，可下載後傳到群組。
      </p>
      <button className="primary" onClick={handleExport} disabled={busy || rounds.length === 0}>
        {busy ? '產生中…' : '產生並下載圖卡'}
      </button>
      {rounds.length === 0 && <p className="muted" style={{ fontSize: 12 }}>尚無局數，無法產生。</p>}
      {error && <p className="error">{error}</p>}

      {/* 離畫面渲染版面：實際輸出用，不在畫面上顯示 */}
      <div className="offscreen" aria-hidden>
        <div className="share-card" ref={cardRef}>
          <div className="share-watermark">MahjongScore</div>
          <div className="share-date">
            {dateStr} · {session.name}
          </div>
          {ranked.map((r, i) => (
            <div className={`share-rank${i === 0 ? ' first' : ''}`} key={r.player.id}>
              <span className="share-rank-badge">{RANK_BADGE[i] ?? ''}</span>
              <span className="share-rank-name">{r.player.name}</span>
              <span
                className="share-rank-amt"
                style={{
                  color:
                    r.amount > 0
                      ? 'var(--color-win)'
                      : r.amount < 0
                        ? 'var(--color-lose)'
                        : 'var(--color-text-secondary)',
                }}
              >
                {formatSigned(r.amount)}
              </span>
            </div>
          ))}

          <div className="share-chart">
            <MiniTrend timeline={timeline} players={players} />
          </div>

          <div className="share-footer">
            {rounds.length} 局 · 底 {settings.base} · 台 {settings.tai}
          </div>
        </div>
      </div>
    </section>
  );
}

// 圖卡用迷你折線：4 色疊一起，無軸標籤，只看走勢。
function MiniTrend({
  timeline,
  players,
}: {
  timeline: ReturnType<typeof buildCumulativeTimeline>;
  players: Player[];
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, position: 'relative' }}>
      {players.map((p, i) => (
        <div key={p.id} style={{ position: i === 0 ? 'relative' : 'absolute', inset: 0 }}>
          <Sparkline
            // Sparkline 期望輸入是「逐局增量」（內部會自行累加成累計曲線），
            // 因此這裡傳每局相對前一局的 delta；timeline[k] 對應第 k 局結束後的累計，
            // 第 k 局增量 = cumulative[k] − cumulative[k−1]，最終畫出的即累計走勢。
            values={timeline.slice(1).map((pt, idx) => {
              const prev = timeline[idx].cumulative[p.id] ?? 0;
              return (pt.cumulative[p.id] ?? 0) - prev;
            })}
            color={playerColor(i)}
            width={358}
            height={120}
          />
        </div>
      ))}
    </div>
  );
}
