// 玩家詳情頁：跨場統計、手氣分析（連贏/連輸/勝率）、場次歷史、跨場走勢。
// 支援兩種來源：名冊成員（/players/r/:rosterId，可改名）與歷史唯名字玩家（/players/:name）。
import { lazy, Suspense, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppData } from '../AppData';
import {
  aggregateByRosterId,
  aggregateUnlinkedByName,
  rateWithThreshold,
} from '../scoring/timeline';
import type { TimelinePoint } from '../scoring/timeline';
import type { Player } from '../types';
import { Amount } from '../components/ui';
import { PlayerAvatar } from '../components/PlayerAvatar';

const ScoreChartInner = lazy(() => import('../components/ScoreChartInner'));

export function PlayerDetailPage() {
  // React Router v6 的 useParams() 已自動 decode 一次，這裡不可再 decodeURIComponent，
  // 否則名字含 % 的玩家（如「50%」）會丟 URIError 導致整頁白屏。
  const { name: rawName, rosterId } = useParams<{ name: string; rosterId: string }>();
  const navigate = useNavigate();
  const { sessions, globalSettings, updateRosterPlayer } = useAppData();

  const rosterPlayer = rosterId
    ? globalSettings.roster.find((r) => r.id === rosterId)
    : undefined;

  // 名冊成員以 rosterId 聚合（不受改名影響）；純名字路徑（/players/:name）只算
  // 同名且未連結名冊的場次，與主頁歷史卡片一致、不與名冊成員數字重疊。
  const displayName = rosterPlayer?.name ?? rawName ?? '';

  // 5-6：頭像 colorIndex 沿用名冊順序 mod 4，與名冊 / 排名條 / 圖卡三處同色。
  // 純名字歷史玩家（無名冊連結）用名字首字 hash 出穩定色。
  const avatarColorIndex = rosterId
    ? Math.max(0, globalSettings.roster.findIndex((r) => r.id === rosterId)) % 4
    : (displayName.charCodeAt(0) || 0) % 4;

  const stats = rosterId
    ? aggregateByRosterId(sessions, rosterId, displayName)
    : aggregateUnlinkedByName(sessions, displayName);

  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState(displayName);

  // useState(displayName) 只在初次掛載取值；切換到不同玩家路由時元件不會重掛，
  // 編輯框會留著上一位玩家的舊名字。改名後同步 displayName，避免顯示過期名字。
  useEffect(() => {
    setDraftName(displayName);
  }, [displayName]);

  // 跨場走勢：以「場」為 X 軸，累計金額為 Y。借用 ScoreChartInner 的單線渲染。
  const virtualPlayer: Player = { id: 'self', name: displayName };
  let acc = 0;
  const timeline: TimelinePoint[] = [
    { roundIndex: 0, cumulative: { self: 0 } },
    ...stats.history.map((h, i) => {
      acc += h.amount;
      return { roundIndex: i + 1, cumulative: { self: acc } };
    }),
  ];

  function saveName() {
    if (rosterId && draftName.trim()) {
      updateRosterPlayer(rosterId, { name: draftName.trim() });
    }
    setEditing(false);
  }

  return (
    <div className="page">
      <header className="page-header">
        <button className="icon-btn" onClick={() => navigate('/players')} aria-label="返回玩家清單">
          ‹
        </button>
        {editing && rosterPlayer ? (
          <div className="row" style={{ flex: 1 }}>
            <input
              type="text"
              value={draftName}
              maxLength={12}
              autoFocus
              onChange={(e) => setDraftName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') saveName();
              }}
            />
            <button className="secondary" onClick={saveName}>
              儲存
            </button>
          </div>
        ) : (
          <>
            <PlayerAvatar
              name={displayName}
              avatar={rosterPlayer?.avatar}
              colorIndex={avatarColorIndex}
              size={64}
              className="detail-avatar"
            />
            <h1>{displayName}</h1>
            {rosterPlayer && (
              <button
                className="link"
                aria-label="編輯名字"
                onClick={() => {
                  setDraftName(displayName);
                  setEditing(true);
                }}
              >
                ✏️
              </button>
            )}
          </>
        )}
      </header>

      {stats.sessionsPlayed === 0 ? (
        <p className="muted">查無此玩家的紀錄。</p>
      ) : (
        <>
          {/* 數據系統 Phase 1：核心三率卡（主視線，永遠展開）。率值主數字一律中性色，
              語意色只出現在基準比較指示器；樣本不足以「—」誠實標注，不假裝有數字。 */}
          <section className="rate-card">
            <div className="rate-card-grid">
              <RoundRateCell
                label="胡牌率"
                count={stats.totalWins}
                rounds={stats.totalRounds}
                kind="win"
              />
              <SelfDrawRateCell
                wins={stats.totalWins}
                selfDraws={stats.totalSelfDraws}
                rounds={stats.totalRounds}
              />
              <RoundRateCell
                label="放槍率"
                count={stats.totalGunned}
                rounds={stats.totalRounds}
                kind="gun"
              />
            </div>
          </section>

          <section className="card">
            <h2>跨場統計</h2>
            <div className="stat-grid">
              <div className="stat-box">
                <div className="stat-value">
                  <Amount value={stats.totalAmount} />
                </div>
                <div className="stat-label">總輸贏</div>
              </div>
              <div className="stat-box">
                <div className="stat-value tabular">{stats.sessionsPlayed}</div>
                <div className="stat-label">出場場次</div>
              </div>
              <div className="stat-box">
                <div className="stat-value">
                  <Amount value={stats.recentAvg} />
                </div>
                <div className="stat-label">近 5 場均輸贏</div>
              </div>
              <div className="stat-box">
                <div className="stat-value tabular">
                  {Math.round(stats.winRate * 100)}%
                </div>
                <div className="stat-label">場次勝率</div>
              </div>
              <div className="stat-box">
                <div className="stat-value tabular">{stats.totalWins}</div>
                <div className="stat-label">胡牌局數</div>
              </div>
              <div className="stat-box">
                <div className="stat-value tabular">{stats.totalSelfDraws}</div>
                <div className="stat-label">自摸局數</div>
              </div>
              <div className="stat-box">
                <div className="stat-value tabular">{stats.totalGunned}</div>
                <div className="stat-label">放槍局數</div>
              </div>
            </div>
          </section>

          <section className="card">
            <h2>手氣分析</h2>
            <div className="stat-grid">
              <div className="stat-box">
                <div className="stat-value tabular" style={{ color: 'var(--color-win)' }}>
                  {stats.longestWinStreak}
                </div>
                <div className="stat-label">最長連贏場</div>
              </div>
              <div className="stat-box">
                <div className="stat-value tabular" style={{ color: 'var(--color-lose)' }}>
                  {stats.longestLoseStreak}
                </div>
                <div className="stat-label">最長連輸場</div>
              </div>
            </div>
          </section>

          {stats.history.length > 0 && (
            <div className="chart-card">
              <h2 style={{ margin: '0 0 12px', fontSize: 18 }}>跨場累計走勢</h2>
              <Suspense fallback={<div className="chart-loading">圖表載入中…</div>}>
                <ScoreChartInner timeline={timeline} players={[virtualPlayer]} />
              </Suspense>
            </div>
          )}

          <section className="card">
            <h2>場次歷史</h2>
            <ol className="round-list">
              {[...stats.history].reverse().map((h) => (
                <li
                  className="history-row"
                  key={h.sessionId}
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/sessions/${h.sessionId}`)}
                >
                  <span>
                    <strong>{h.sessionName}</strong>
                    <br />
                    <span className="muted" style={{ fontSize: 12 }}>
                      {new Date(h.createdAt).toLocaleDateString('zh-TW')}
                    </span>
                  </span>
                  <Amount value={h.amount} />
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </div>
  );
}

/**
 * 基準比較指示器（僅胡牌率 / 放槍率、且 N≥30 時顯示）。
 * class（above/below/neutral）代表「相對均值的表現好壞」而非單純數字大小：
 * 胡牌率高＝好、放槍率低＝好，兩者的「好」都對應 above（綠）。
 * 4 人麻將理論基準 25%：>28% 視為高、<22% 視為低、±3% 內視為接近均值。
 */
function rateBaseline(pct: number, kind: 'win' | 'gun'): { cls: string; text: string } {
  const high = pct > 28;
  const low = pct < 22;
  if (!high && !low) return { cls: 'neutral', text: '接近均值' };
  const good = kind === 'win' ? high : low;
  return { cls: good ? 'above' : 'below', text: `${high ? '↑' : '↓'} ${high ? '高' : '低'}於均值` };
}

/** 胡牌率 / 放槍率欄（分母＝總局數，N<10 顯示「—」）。 */
function RoundRateCell({
  label,
  count,
  rounds,
  kind,
}: {
  label: string;
  count: number;
  rounds: number;
  kind: 'win' | 'gun';
}) {
  const { insufficient, pct } = rateWithThreshold(count, rounds, 10);
  const baseline = !insufficient && rounds >= 30 ? rateBaseline(pct, kind) : null;
  return (
    <div className="rate-cell">
      <div className="rate-label">{label}</div>
      <div className={`rate-value${insufficient ? ' insufficient' : ''}`}>
        {insufficient ? '—' : `${pct}%`}
      </div>
      <div className="rate-cell-footer">
        {/* 「—」態也顯示樣本數：讓使用者知道還差幾局才達門檻（誠實資訊，非填充） */}
        {rounds < 30 && <span className="rate-sample">(N={rounds}局)</span>}
        {baseline && <span className={`rate-baseline ${baseline.cls}`}>{baseline.text}</span>}
      </div>
    </div>
  );
}

/**
 * 自摸率欄（主口徑＝自摸/胡牌，分母為胡牌次數，totalWins<5 顯示「—」）。
 * 副口徑「占局 X%」＝自摸/總局數，僅在主口徑有值時一併顯示（次要色小字）。
 */
function SelfDrawRateCell({
  wins,
  selfDraws,
  rounds,
}: {
  wins: number;
  selfDraws: number;
  rounds: number;
}) {
  const { insufficient, pct } = rateWithThreshold(selfDraws, wins, 5);
  const perRoundPct = rounds > 0 ? Math.round((selfDraws / rounds) * 100) : 0;
  return (
    <div className="rate-cell">
      <div className="rate-label">自摸率</div>
      <div className={`rate-value${insufficient ? ' insufficient' : ''}`}>
        {insufficient ? '—' : `${pct}%`}
      </div>
      <div className="rate-cell-footer">
        {/* 「—」態同樣顯示樣本數（此欄門檻以胡牌次數計） */}
        {wins < 30 && <span className="rate-sample">(N={wins}勝)</span>}
      </div>
      {/* 副口徑列在兩態都渲染以維持等高；「—」態用 nbsp 佔位保留行高、不顯示數字 */}
      <div className="rate-self-draw-alt">{insufficient ? ' ' : `占局 ${perRoundPct}%`}</div>
    </div>
  );
}
