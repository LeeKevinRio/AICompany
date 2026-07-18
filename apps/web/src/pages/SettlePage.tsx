// P6 結算頁面（穩健牌 2 / 結算頁視覺規範）。
//
// 全螢幕「本場結算儀式」畫面：整合既有四個元件（Highlights 資料→徽章、排名、
// Sparkline、再開一場 CTA）成一條動線，不新增計分邏輯。已結算場次可從牌局詳情
// 再次進入回看。進場動畫只用 opacity/translateY 淡入（規範 3-2 禁止 FLIP/列重排）。
import { useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppData } from '../AppData';
import { settleSession } from '../scoring/scoring';
import { deriveDealerContexts } from '../scoring/dealer';
import { hasSubstitutions } from '../scoring/substitution';
import {
  buildCumulativeTimeline,
  calcSessionHighlights,
  formatSigned,
  HIGHLIGHT_EMOJI,
} from '../scoring/timeline';
import { resolvePlayerVisual } from '../components/ui';
import { PlayerAvatar } from '../components/PlayerAvatar';
import { ShareCard, MiniTrend } from '../components/ShareCard';
import type { ShareCardHandle } from '../components/ShareCard';

const RANK_BADGE = ['冠', '亞', '季', '殿'];

export function SettlePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { sessions, globalSettings } = useAppData();

  // 下載圖卡：透過 ref 觸發 headless ShareCard 的匯出（規範 7-3 共用同一份匯出邏輯）。
  const shareRef = useRef<ShareCardHandle>(null);
  const [exporting, setExporting] = useState(false);
  // 匯出圖卡的錯誤訊息（來自 headless ShareCard 的 onError 回呼，顯示在 CTA 附近）。
  const [exportError, setExportError] = useState('');

  const session = sessions.find((s) => s.id === id) ?? null;

  if (!session) {
    return (
      <div className="settle-page">
        <div className="settle-nav">
          <button className="settle-nav-close" onClick={() => navigate('/')} aria-label="關閉">
            ‹ 關閉
          </button>
          <span className="settle-nav-brand">MaJong</span>
        </div>
        <p className="muted" style={{ padding: 24 }}>
          找不到這場牌局，可能已被刪除。
        </p>
      </div>
    );
  }

  // 未結算場次不該顯示結算儀式（直打 /settle URL 會誤入）。給明確提示與返回詳情頁連結。
  if (!session.endedAt) {
    return (
      <div className="settle-page">
        <div className="settle-nav">
          <button
            className="settle-nav-close"
            onClick={() => navigate(`/sessions/${session.id}`)}
            aria-label="返回牌局詳情"
          >
            ‹ 返回
          </button>
          <span className="settle-nav-brand">MaJong</span>
        </div>
        <p className="muted" style={{ padding: 24 }}>
          這場牌局尚未結算，請先在牌局詳情按「結算本場」。
        </p>
      </div>
    );
  }

  const { players, rounds, settings, rules } = session;
  // v2.3：連莊加台由 session 推導（舊場 / 未啟用回空陣列，零回歸）。
  const dealerCtxs = deriveDealerContexts(session);
  // v2.3：流局不計入胡牌率 / 放槍率分母（本場三率快照用）。
  const scoredCount = rounds.filter((r) => !r.drawn).length;

  // 淨額（含自摸付出的東錢），與 ShareCard / 卡片預覽一致。
  let totals: Record<string, number>;
  try {
    totals = settleSession(rounds, players, settings, rules, dealerCtxs).net;
  } catch {
    totals = {};
    for (const p of players) totals[p.id] = 0;
  }

  const ranked = players
    .map((p, i) => {
      const { colorIndex, avatar } = resolvePlayerVisual(p, i, globalSettings.roster);
      return { player: p, colorIndex, avatar, amount: totals[p.id] ?? 0 };
    })
    .sort((a, b) => b.amount - a.amount);

  const { highlights, perPlayer } = calcSessionHighlights(
    rounds,
    players,
    settings,
    rules,
    dealerCtxs,
  );
  const timeline = buildCumulativeTimeline(rounds, players, settings, rules, dealerCtxs);
  const dateStr = new Date(session.createdAt).toLocaleDateString('zh-TW');

  const hasRounds = rounds.length > 0;
  // v2.4（批次 3）：換人場——結算排名以「座位整場加總」呈現，補一行次要說明避免誤讀。
  const substituted = hasSubstitutions(session);

  // ❸.5 本場三率快照：只標正向名次——最低放槍（防守最佳）與最高胡牌（進攻最佳），
  // 各只標「唯一者」，並列（同率）時不標，避免無意義或批鬥感。本場資料量小，
  // 依規範刻意不套 N<10 門檻（這是「本場快照」而非跨場統計）。
  let bestDefenseId: string | null = null;
  let bestWinId: string | null = null;
  if (hasRounds) {
    let minGun = Infinity;
    let minGunTies = 0;
    let maxWin = -Infinity;
    let maxWinTies = 0;
    for (const p of players) {
      const pp = perPlayer[p.id] ?? { wins: 0, selfDraws: 0, gunned: 0 };
      if (pp.gunned < minGun) {
        minGun = pp.gunned;
        bestDefenseId = p.id;
        minGunTies = 1;
      } else if (pp.gunned === minGun) {
        minGunTies += 1;
      }
      if (pp.wins > maxWin) {
        maxWin = pp.wins;
        bestWinId = p.id;
        maxWinTies = 1;
      } else if (pp.wins === maxWin) {
        maxWinTies += 1;
      }
    }
    if (minGunTies > 1) bestDefenseId = null;
    if (maxWinTies > 1) bestWinId = null;
  }

  function toneClass(amount: number): string {
    if (amount > 0) return 'win';
    if (amount < 0) return 'lose';
    return 'zero';
  }

  // 下載圖卡：再入護欄——匯出進行中（exporting）直接 return，與 CTA 的 disabled 形成雙保險，
  // 避免連點並行觸發多次 html2canvas / 重複下載。
  async function handleExport() {
    if (exporting) return;
    setExportError('');
    await shareRef.current?.exportCard();
  }

  // 再開一場（同組）：複用批次一（穩健牌 3）的「再開同組」流程——導回牌局清單並帶上
  // duplicateFrom，由 SessionsPage 以既有 handleDuplicate 帶入 4 人/底台/規則、開確認 sheet。
  function handleReopen() {
    navigate('/', { state: { duplicateFrom: session!.id } });
  }

  return (
    <div className="settle-page">
      {/* 頂部導航 */}
      <div className="settle-nav">
        <button
          className="settle-nav-close"
          onClick={() => navigate(`/sessions/${session.id}`)}
          aria-label="關閉結算畫面"
        >
          ‹ 關閉
        </button>
        <span className="settle-nav-brand">MaJong</span>
      </div>

      {/* ❶ 場名大字區 */}
      <div className="settle-block settle-block-hero settle-hero">
        <div className="settle-title">{session.name}</div>
        <div className="settle-subtitle">
          {dateStr} · {rounds.length} 局
        </div>
      </div>

      {/* ❷ 趣味標籤（徽章橫排） */}
      {highlights.length > 0 && (
        <div className="settle-block settle-block-badges">
          <div className="settle-badges-scroll">
            {highlights.map((h) => (
              <div
                className={`settle-badge${h.key === 'champion' ? ' champion' : ''}`}
                key={h.key}
              >
                <span className="settle-badge-emoji">{HIGHLIGHT_EMOJI[h.key]}</span>
                <span className="settle-badge-label">{h.label}</span>
                <span className="settle-badge-name">{h.playerName ?? '—'}</span>
                <span className="settle-badge-detail">{h.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ❸ 四人最終排名 */}
      <div className="settle-block settle-block-ranking settle-ranking">
        {ranked.map((r, i) => (
          <div className={`settle-rank-row${i === 0 ? ' first' : ''}`} key={r.player.id}>
            <span className={`settle-rank-badge rank-${i + 1}`}>
              {RANK_BADGE[i] ?? ''}
            </span>
            {/* 頭像 size=40；第一名金框金暈由 CSS .settle-rank-row.first .rank-avatar-wrapper 帶 */}
            <span className="rank-avatar-wrapper">
              <PlayerAvatar
                name={r.player.name}
                avatar={r.avatar}
                colorIndex={r.colorIndex}
                size={40}
              />
            </span>
            <span className="settle-rank-name">{r.player.name}</span>
            <span
              className={`settle-rank-amt${i === 0 ? '' : ` ${toneClass(r.amount)}`}`}
            >
              {formatSigned(r.amount)}
            </span>
          </div>
        ))}
        {substituted && (
          <p className="subst-notice" style={{ marginTop: 8 }}>
            本場有換人，結算依座位加總顯示。
          </p>
        )}
      </div>

      {/* ❸.5 本場三率快照（排名下方、走勢上方） */}
      {hasRounds && (
        <div className="settle-block settle-block-snapshot settle-snapshot">
          <div className="settle-snapshot-title">本場三率</div>
          <div className="settle-snapshot-rows">
            {ranked.map((r) => {
              const pp = perPlayer[r.player.id] ?? { wins: 0, selfDraws: 0, gunned: 0 };
              // v2.3：分母排除流局（scoredCount）；全流局的極端場以 0 呈現，不除以 0。
              const winPct = scoredCount > 0 ? Math.round((pp.wins / scoredCount) * 100) : 0;
              const gunPct = scoredCount > 0 ? Math.round((pp.gunned / scoredCount) * 100) : 0;
              // 自摸率分母為本場胡牌次數；0 胡無從計算 → 「—」。
              const sdPct = pp.wins > 0 ? Math.round((pp.selfDraws / pp.wins) * 100) : null;
              // 每列最多一個標籤；同時符合兩者時優先顯示最高胡牌（金、進攻最佳）。
              const tag =
                r.player.id === bestWinId
                  ? { cls: 'best-win', text: '最高胡牌' }
                  : r.player.id === bestDefenseId
                    ? { cls: 'best-defense', text: '最低放槍' }
                    : null;
              return (
                <div className="settle-snapshot-row" key={r.player.id}>
                  <PlayerAvatar
                    name={r.player.name}
                    avatar={r.avatar}
                    colorIndex={r.colorIndex}
                    size={24}
                  />
                  <span className="snapshot-name">{r.player.name}</span>
                  <div className="snapshot-stats">
                    <span className="snapshot-stat">
                      胡 <strong>{pp.wins}</strong>次(<strong>{winPct}%</strong>)
                    </span>
                    <span className="snapshot-sep">·</span>
                    <span className="snapshot-stat">
                      摸 <strong>{sdPct === null ? '—' : `${sdPct}%`}</strong>
                    </span>
                    <span className="snapshot-sep">·</span>
                    <span className="snapshot-stat">
                      放 <strong>{pp.gunned}</strong>次(<strong>{gunPct}%</strong>)
                    </span>
                  </div>
                  {tag && (
                    <span className={`snapshot-highlight-tag ${tag.cls}`}>{tag.text}</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ❹ 迷你走勢（同 ShareCard MiniTrend 疊圖，height=100） */}
      {hasRounds && (
        <div className="settle-block settle-block-sparkline settle-sparkline">
          <div className="settle-sparkline-label">本場走勢</div>
          <div className="settle-sparkline-chart">
            <MiniTrend
              timeline={timeline}
              players={players}
              roster={globalSettings.roster}
              width={358}
              height={100}
            />
          </div>
        </div>
      )}

      {/* ❺ 底部雙 CTA（sticky） */}
      <div className="settle-block settle-block-cta settle-cta">
        <button
          className="settle-cta-secondary"
          onClick={handleExport}
          disabled={!hasRounds || exporting}
          style={exporting ? { opacity: 0.6 } : undefined}
        >
          {exporting ? '產生中…' : '下載圖卡'}
        </button>
        <button className="settle-cta-primary" onClick={handleReopen} disabled={!hasRounds}>
          <span aria-hidden>▶</span> 再開一場（同組）
        </button>
        {exportError && (
          <p className="error" style={{ margin: '8px 0 0', textAlign: 'center' }}>
            {exportError}
          </p>
        )}
      </div>

      {/* headless ShareCard：只提供離畫面 DOM 與匯出邏輯，不顯示自身 UI（規範 7-3） */}
      <ShareCard
        ref={shareRef}
        session={session}
        players={players}
        rounds={rounds}
        settings={settings}
        roster={globalSettings.roster}
        headless
        onBusyChange={setExporting}
        onError={setExportError}
      />
    </div>
  );
}
