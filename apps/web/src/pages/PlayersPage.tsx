// Tab 2：玩家。跨場以名字聚合的清單，點入看詳情。
import { useNavigate } from 'react-router-dom';
import { useAppData } from '../AppData';
import { aggregatePlayerStats, collectPlayerNames } from '../scoring/timeline';
import { Amount } from '../components/ui';
import { Sparkline } from '../components/Sparkline';

export function PlayersPage() {
  const { sessions } = useAppData();
  const navigate = useNavigate();
  const names = collectPlayerNames(sessions);

  return (
    <div className="page">
      <header className="page-header">
        <h1>玩家</h1>
      </header>

      {names.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">👤</div>
          <p className="empty-title">還沒有玩家紀錄</p>
          <p>建立牌局並填入玩家名字後，就會在這裡看到統計。</p>
        </div>
      ) : (
        names.map((name) => {
          const stats = aggregatePlayerStats(sessions, name);
          return (
            <div
              className="player-card"
              key={name}
              onClick={() => navigate(`/players/${encodeURIComponent(name)}`)}
            >
              <div className="player-card-info">
                <div className="player-card-name">{name}</div>
                <div className="player-card-meta">
                  出場 {stats.sessionsPlayed} 場 · <Amount value={stats.totalAmount} />
                </div>
              </div>
              <Sparkline
                values={stats.recentTrend.slice(-8)}
                color={stats.totalAmount >= 0 ? 'var(--color-win)' : 'var(--color-lose)'}
              />
            </div>
          );
        })
      )}
    </div>
  );
}
