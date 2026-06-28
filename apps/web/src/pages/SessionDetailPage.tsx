// 牌局詳情頁：三子頁籤（記局 / 走勢圖 / 明細）。
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppData } from '../AppData';
import { SettingsPanel } from '../components/SettingsPanel';
import { RoundForm } from '../components/RoundForm';
import { RoundList } from '../components/RoundList';
import { Standings } from '../components/Standings';
import { RankBar } from '../components/RankBar';
import { ScoreChart } from '../components/ScoreChart';
import { Highlights } from '../components/Highlights';
import { ShareCard } from '../components/ShareCard';

type SubTab = 'record' | 'chart' | 'detail';

export function SessionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const {
    sessions,
    updateSettings,
    updatePlayerName,
    addRound,
    removeRound,
    toggleEnded,
  } = useAppData();

  const [sub, setSub] = useState<SubTab>('record');

  const session = sessions.find((s) => s.id === id) ?? null;

  if (!session) {
    return (
      <div className="page">
        <header className="page-header">
          <button className="back-btn" onClick={() => navigate('/')} aria-label="返回">
            ‹
          </button>
          <h1>找不到牌局</h1>
        </header>
        <p className="muted">這場牌局可能已被刪除。</p>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="page-header">
        <button className="back-btn" onClick={() => navigate('/')} aria-label="返回牌局清單">
          ‹
        </button>
        <h1>{session.name}</h1>
      </header>

      <div className="subtabs">
        <button
          className={`subtab${sub === 'record' ? ' active' : ''}`}
          onClick={() => setSub('record')}
        >
          記局
        </button>
        <button
          className={`subtab${sub === 'chart' ? ' active' : ''}`}
          onClick={() => setSub('chart')}
        >
          走勢圖
        </button>
        <button
          className={`subtab${sub === 'detail' ? ' active' : ''}`}
          onClick={() => setSub('detail')}
        >
          明細
        </button>
      </div>

      {sub === 'record' && (
        <>
          <RankBar
            rounds={session.rounds}
            players={session.players}
            settings={session.settings}
          />
          <RoundForm
            players={session.players}
            onAdd={(r) => addRound(session.id, r)}
          />
          <SettingsPanel
            settings={session.settings}
            players={session.players}
            onChangeSettings={(s) => updateSettings(session.id, s)}
            onChangePlayerName={(pid, name) => updatePlayerName(session.id, pid, name)}
          />
          <button
            className={session.endedAt ? 'secondary' : 'primary'}
            style={{ width: '100%' }}
            onClick={() => toggleEnded(session.id)}
          >
            {session.endedAt ? '取消結算（繼續記局）' : '結算本場'}
          </button>
        </>
      )}

      {sub === 'chart' && (
        <>
          <ScoreChart
            rounds={session.rounds}
            players={session.players}
            settings={session.settings}
          />
          <Highlights
            rounds={session.rounds}
            players={session.players}
            settings={session.settings}
          />
          <ShareCard
            session={session}
            players={session.players}
            rounds={session.rounds}
            settings={session.settings}
          />
        </>
      )}

      {sub === 'detail' && (
        <>
          <Standings
            rounds={session.rounds}
            players={session.players}
            settings={session.settings}
          />
          <RoundList
            rounds={session.rounds}
            players={session.players}
            settings={session.settings}
            onRemove={(rid) => removeRound(session.id, rid)}
          />
        </>
      )}
    </div>
  );
}
