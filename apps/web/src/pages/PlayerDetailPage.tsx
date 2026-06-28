// 玩家詳情頁：跨場統計、手氣分析（連贏/連輸/勝率）、場次歷史、跨場走勢。
import { lazy, Suspense } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppData } from '../AppData';
import { aggregatePlayerStats } from '../scoring/timeline';
import type { TimelinePoint } from '../scoring/timeline';
import type { Player } from '../types';
import { Amount } from '../components/ui';

const ScoreChartInner = lazy(() => import('../components/ScoreChartInner'));

export function PlayerDetailPage() {
  // React Router v6 的 useParams() 已自動 decode 一次，這裡不可再 decodeURIComponent，
  // 否則名字含 % 的玩家（如「50%」）會丟 URIError 導致整頁白屏。
  const { name: raw } = useParams<{ name: string }>();
  const name = raw ?? '';
  const navigate = useNavigate();
  const { sessions } = useAppData();

  const stats = aggregatePlayerStats(sessions, name);

  // 跨場走勢：以「場」為 X 軸，累計金額為 Y。借用 ScoreChartInner 的單線渲染。
  const virtualPlayer: Player = { id: 'self', name };
  let acc = 0;
  const timeline: TimelinePoint[] = [
    { roundIndex: 0, cumulative: { self: 0 } },
    ...stats.history.map((h, i) => {
      acc += h.amount;
      return { roundIndex: i + 1, cumulative: { self: acc } };
    }),
  ];

  return (
    <div className="page">
      <header className="page-header">
        <button className="back-btn" onClick={() => navigate('/players')} aria-label="返回玩家清單">
          ‹
        </button>
        <h1>{name}</h1>
      </header>

      {stats.sessionsPlayed === 0 ? (
        <p className="muted">查無此玩家的紀錄。</p>
      ) : (
        <>
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
              <div className="stat-box">
                <div className="stat-value tabular">
                  {Math.round(stats.winRate * 100)}%
                </div>
                <div className="stat-label">場次勝率</div>
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
                <li className="history-row" key={h.sessionId}>
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
