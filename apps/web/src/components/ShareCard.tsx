// 結算分享圖卡（企劃 5-1 / 視覺規範 7-4）。
// 用 html2canvas 把離畫面 DOM 轉 PNG 下載；html2canvas 以動態 import 載入，
// 避免拖慢首載（與 recharts 同樣考量）。
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import type { Player, RosterPlayer, Round, Session, Settings } from '../types';
import { settleSession } from '../scoring/scoring';
import { buildCumulativeTimeline, formatSigned } from '../scoring/timeline';
import { deriveDealerContexts } from '../scoring/dealer';
import { Sparkline } from './Sparkline';
import { playerColor, resolvePlayerVisual } from './ui';
import { PlayerAvatar } from './PlayerAvatar';

interface Props {
  session: Session;
  players: Player[];
  rounds: Round[];
  settings: Settings;
  /** 玩家名冊：決定圖卡頭像與 colorIndex（與名冊 / 排名條同色，5-6）。 */
  roster: RosterPlayer[];
  /**
   * P6 結算頁：headless 模式只渲染離畫面 DOM，不顯示預設的「結算分享圖卡」按鈕卡片，
   * 由外部（結算頁 CTA）透過 ref.exportCard() 觸發匯出（結算頁視覺規範 7-3：
   * 不另維護一套 ShareCard DOM 版面，共用同一份匯出邏輯）。
   */
  headless?: boolean;
  /** 匯出忙碌狀態變化回呼（結算頁用來把 CTA 文字切成「產生中…」）。 */
  onBusyChange?: (busy: boolean) => void;
  /**
   * 匯出失敗回呼。headless 模式不渲染自身 UI，錯誤無處顯示，
   * 交由外部（結算頁）在 CTA 附近提示；成功時回傳空字串清除舊訊息。
   */
  onError?: (msg: string) => void;
}

/** 供外部（結算頁 CTA）以 ref 觸發匯出的 imperative handle。 */
export interface ShareCardHandle {
  exportCard: () => Promise<void>;
}

const RANK_BADGE = ['冠', '亞', '季', '殿'];

export const ShareCard = forwardRef<ShareCardHandle, Props>(function ShareCard(
  { session, players, rounds, settings, roster, headless = false, onBusyChange, onError },
  ref,
) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // v2.3：連莊加台由 session 推導（舊場 / 未啟用回空陣列，零回歸）。
  const dealerCtxs = deriveDealerContexts(session);
  // 分享圖卡顯示「淨額」（含自摸付出的東錢），與結算頁一致。
  let totals: Record<string, number>;
  try {
    totals = settleSession(rounds, players, settings, session.rules, dealerCtxs).net;
  } catch {
    totals = {};
    for (const p of players) totals[p.id] = 0;
  }

  const ranked = players
    .map((p, i) => {
      const { colorIndex, avatar } = resolvePlayerVisual(p, i, roster);
      return { player: p, colorIndex, avatar, amount: totals[p.id] ?? 0 };
    })
    .sort((a, b) => b.amount - a.amount);

  const dateStr = new Date(session.createdAt).toLocaleDateString('zh-TW');
  const timeline = buildCumulativeTimeline(rounds, players, settings, session.rules, dealerCtxs);

  async function handleExport() {
    if (!cardRef.current) return;
    setBusy(true);
    setError('');
    onError?.('');
    try {
      const { default: html2canvas } = await import('html2canvas');
      const canvas = await html2canvas(cardRef.current, {
        backgroundColor: '#0a1209',
        scale: 2,
        logging: false,
        // useCORS：未來若頭像改由 CDN 提供，跨網域圖片需帶 CORS 才能被光柵化，
        // 否則畫布會污染（tainted）導致頭像變空白。本機 same-origin 下無副作用。
        useCORS: true,
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
      const msg = '產生圖卡失敗，請稍後再試。';
      setError(msg);
      onError?.(msg);
    } finally {
      setBusy(false);
    }
  }

  // 曝露匯出方法給結算頁 CTA。不帶 deps → 每次 render 重建 handle，
  // 確保 exportCard 永遠關住當前的 dateStr / rounds（避免 stale closure）。
  useImperativeHandle(ref, () => ({ exportCard: handleExport }));

  // busy 變化回報給外部（結算頁 CTA 切「產生中…」）。
  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);

  // 離畫面渲染版面（實際輸出用，不在畫面上顯示）。headless / 一般模式共用同一份 DOM。
  const offscreenCard = (
    <div className="offscreen" aria-hidden>
      <div className="share-card" ref={cardRef}>
        <div className="share-watermark">MaJong</div>
        <div className="share-date">
          {dateStr} · {session.name}
        </div>
        {ranked.map((r, i) => (
          <div className={`share-rank${i === 0 ? ' first' : ''}`} key={r.player.id}>
            <span className="share-rank-badge">{RANK_BADGE[i] ?? ''}</span>
            {/* 5-3-d：名次徽章右側 36px 頭像；第一名金框金暈由 CSS .share-rank.first 帶 */}
            <PlayerAvatar
              name={r.player.name}
              avatar={r.avatar}
              colorIndex={r.colorIndex}
              size={36}
              className="share-player-avatar"
            />
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
          <MiniTrend timeline={timeline} players={players} roster={roster} />
        </div>

        <div className="share-footer">
          {rounds.length} 局 · 底 {settings.base} · 台 {settings.tai}
        </div>
      </div>
    </div>
  );

  // headless（結算頁）：只保留離畫面 DOM，不渲染預設按鈕卡片。
  if (headless) return offscreenCard;

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

      {offscreenCard}
    </section>
  );
});

// 圖卡用迷你折線：4 色疊一起，無軸標籤，只看走勢。
// 結算頁走勢區（規範 8-8）與圖卡共用同一份疊圖邏輯，僅 width/height 不同，故對外 export。
export function MiniTrend({
  timeline,
  players,
  roster,
  width = 358,
  height = 120,
}: {
  timeline: ReturnType<typeof buildCumulativeTimeline>;
  players: Player[];
  roster: RosterPlayer[];
  width?: number;
  height?: number;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, position: 'relative' }}>
      {players.map((p, i) => {
        // 折線顏色與頭像 / 排名條同源：走 resolvePlayerVisual 取 colorIndex，
        // 不再直接用座位索引 i，避免與頭像代表色不同源而撞色。
        const { colorIndex } = resolvePlayerVisual(p, i, roster);
        return (
          <div key={p.id} style={{ position: i === 0 ? 'relative' : 'absolute', inset: 0 }}>
            <Sparkline
              // Sparkline 期望輸入是「逐局增量」（內部會自行累加成累計曲線），
              // 因此這裡傳每局相對前一局的 delta；timeline[k] 對應第 k 局結束後的累計，
              // 第 k 局增量 = cumulative[k] − cumulative[k−1]，最終畫出的即累計走勢。
              values={timeline.slice(1).map((pt, idx) => {
                const prev = timeline[idx].cumulative[p.id] ?? 0;
                return (pt.cumulative[p.id] ?? 0) - prev;
              })}
              color={playerColor(colorIndex)}
              width={width}
              height={height}
            />
          </div>
        );
      })}
    </div>
  );
}
