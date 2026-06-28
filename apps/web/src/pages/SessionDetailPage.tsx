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
import type { SessionRules } from '../types';

type SubTab = 'record' | 'chart' | 'detail';

/** v2.1：進場規則提示 chip（自摸加台 / 東錢開啟時顯示，讓玩家確認規則）。 */
function RuleChips({ rules }: { rules: SessionRules }) {
  const chips: string[] = [];
  if (rules.selfDrawBonusTai > 0) chips.push(`自摸 +${rules.selfDrawBonusTai} 台`);
  if (rules.selfDrawDongAmount > 0) chips.push(`東錢 $${rules.selfDrawDongAmount}`);
  if (chips.length === 0) return null;
  return (
    <div className="rule-chips">
      {chips.map((c) => (
        <span className="rule-chip" key={c}>
          {c}
        </span>
      ))}
    </div>
  );
}

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
    updateRules,
    addSession,
    globalSettings,
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
          <RuleChips rules={session.rules} />
          <RankBar
            rounds={session.rounds}
            players={session.players}
            settings={session.settings}
            rules={session.rules}
            loseAlertThreshold={globalSettings.loseAlertThreshold}
          />
          <RoundForm
            players={session.players}
            rounds={session.rounds}
            onAdd={(r) => addRound(session.id, r)}
          />
          <SettingsPanel
            settings={session.settings}
            players={session.players}
            rules={session.rules}
            hasRounds={session.rounds.length > 0}
            onChangeSettings={(s) => updateSettings(session.id, s)}
            onChangePlayerName={(pid, name) => updatePlayerName(session.id, pid, name)}
            onChangeRules={(r) => updateRules(session.id, r)}
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
            rules={session.rules}
          />
          <Highlights
            rounds={session.rounds}
            players={session.players}
            settings={session.settings}
            rules={session.rules}
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
            rules={session.rules}
          />
          <RoundList
            rounds={session.rounds}
            players={session.players}
            settings={session.settings}
            rules={session.rules}
            onRemove={(rid) => removeRound(session.id, rid)}
          />
          <button
            className="secondary"
            style={{ width: '100%', marginTop: 12 }}
            onClick={() => {
              // v2.1 建議做：快速重開同組牌局——帶入本場 4 人（含 rosterId）與規則。
              const newId = addSession(
                `${new Date().toLocaleDateString('zh-TW')} 場`,
                session.players.map((p) => ({ name: p.name, rosterId: p.rosterId })),
                session.rules,
              );
              navigate(`/sessions/${newId}`);
            }}
          >
            再開一場（同組玩家）
          </button>
        </>
      )}
    </div>
  );
}
