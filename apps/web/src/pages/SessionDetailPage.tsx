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
import { ShareCard } from '../components/ShareCard';
import { BottomSheet } from '../components/BottomSheet';
import { IconSettings } from '../components/icons';
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
  // #1：本場設定改在開局時設定、場內不顯示；改由右上角齒輪開此 sheet 編輯。
  const [settingsOpen, setSettingsOpen] = useState(false);

  const session = sessions.find((s) => s.id === id) ?? null;

  if (!session) {
    return (
      <div className="page">
        <header className="page-header">
          <button className="icon-btn" onClick={() => navigate('/')} aria-label="返回">
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
        <button className="icon-btn" onClick={() => navigate('/')} aria-label="返回牌局清單">
          ‹
        </button>
        <h1 style={{ flex: 1 }}>{session.name}</h1>
        {/* #1：右上角編輯本場設定（底/台/規則）入口 */}
        <button
          className="icon-btn"
          onClick={() => setSettingsOpen(true)}
          aria-label="編輯本場設定"
        >
          <IconSettings className="" width={20} height={20} />
        </button>
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
            roster={globalSettings.roster}
            loseAlertThreshold={globalSettings.loseAlertThreshold}
          />
          <RoundForm
            players={session.players}
            rounds={session.rounds}
            roster={globalSettings.roster}
            onAdd={(r) => addRound(session.id, r)}
          />
          {session.endedAt ? (
            <>
              {/* 已結算：主按鈕回看結算儀式頁（P6），次按鈕取消結算繼續記局 */}
              <button
                className="primary"
                style={{ width: '100%' }}
                onClick={() => navigate(`/sessions/${session.id}/settle`)}
              >
                查看本場結算
              </button>
              <button
                className="secondary"
                style={{ width: '100%', marginTop: 8 }}
                onClick={() => toggleEnded(session.id)}
              >
                取消結算（繼續記局）
              </button>
            </>
          ) : (
            // 尚未結算：結算本場＝打時間戳並進入 P6 結算儀式頁
            <button
              className="primary"
              style={{ width: '100%' }}
              disabled={session.rounds.length === 0}
              onClick={() => {
                toggleEnded(session.id);
                navigate(`/sessions/${session.id}/settle`);
              }}
            >
              結算本場
            </button>
          )}
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
          {/* 減法（創意檢視第六節）：Highlights 移出走勢圖 tab，集中到 P6 結算頁登場，不重複出現 */}
          <ShareCard
            session={session}
            players={session.players}
            rounds={session.rounds}
            settings={session.settings}
            roster={globalSettings.roster}
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
              // v2.1 建議做：快速重開同組牌局——帶入本場 4 人（含 rosterId），
              // 並沿用本場規則（rules）與底/台設定（settings），與原場一致，不退回全域預設。
              const newId = addSession(
                `${new Date().toLocaleDateString('zh-TW')} 場`,
                session.players.map((p) => ({ name: p.name, rosterId: p.rosterId })),
                session.rules,
                session.settings,
              );
              navigate(`/sessions/${newId}`);
            }}
          >
            再開一場（同組玩家）
          </button>
        </>
      )}

      {/* #1：右上角齒輪開啟——編輯本場底/台/規則。改設定後既有局數自動以新設定重算顯示。 */}
      <BottomSheet
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        title="編輯本場設定"
      >
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
          className="primary"
          style={{ marginTop: 8 }}
          onClick={() => setSettingsOpen(false)}
        >
          完成
        </button>
      </BottomSheet>
    </div>
  );
}
