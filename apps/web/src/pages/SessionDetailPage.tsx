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
import { SubstitutionPanel } from '../components/SubstitutionPanel';
import { IconSettings } from '../components/icons';
import { deriveTableState } from '../scoring/dealer';
import { hasSubstitutions, occupantPlayersAt } from '../scoring/substitution';
import type { SessionRules } from '../types';

type SubTab = 'record' | 'chart' | 'detail';

// v2.4（批次 3）：換人場的顯示語義提示——排名/累計/圖卡的金額都是「各座位整場加總」，
// 分帳細節（哪一局歸誰）以每局明細為準，避免玩家誤把座位加總當成某個人的個人分帳。
const SUBST_AGGREGATE_NOTE = '排名金額為各座位整場加總，分帳依每局明細。';

/** v2.1：進場規則提示 chip（自摸加台 / 東錢 / 眼牌 / 連莊開啟時顯示，讓玩家確認規則）。 */
function RuleChips({ rules, dealerActive }: { rules: SessionRules; dealerActive: boolean }) {
  const chips: string[] = [];
  if (rules.selfDrawBonusTai > 0) chips.push(`自摸 +${rules.selfDrawBonusTai} 台`);
  if (rules.selfDrawDongAmount > 0) chips.push(`東錢 $${rules.selfDrawDongAmount}`);
  if (rules.eyeTileEnabled && rules.eyeTileTai > 0) chips.push(`眼牌 +${rules.eyeTileTai} 台`);
  // v2.3：連莊實際啟用（有首莊）時才提示，避免舊場開了 rules 卻無首莊的誤導。
  if (dealerActive) chips.push('連莊 · 做莊+1台');
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
    addSubstitution,
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

  // v2.3：圈風 / 莊家 / 連莊推導（唯一真相：session.dealerStartSeat + rules；純函式 fold）。
  // 一次算好，下傳給排名條 / 記局 / 明細 / 走勢 / 累計，確保各處金額與圈風一致。
  const tableState = deriveTableState(session);

  // v2.4（批次 3）：當前在座者（每座位在「下一局」的實際佔用者）。金額仍以座位計，
  // 這裡只把顯示名字 / 頭像換成當下在座者——排名條 / 記局 / 走勢 / 累計 / 圖卡皆用它。
  // 舊場 / 無換人時等同 session.players（零回歸）。明細頁另按「每局」解析歷史在座者。
  const displayPlayers = occupantPlayersAt(session, session.rounds.length);
  const substituted = hasSubstitutions(session);

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
          <RuleChips rules={session.rules} dealerActive={tableState.active} />
          {substituted && (
            <>
              <p className="subst-notice">本場已換人：座位顯示當前在座者，歷史局仍歸當時玩家。</p>
              <p className="subst-notice">{SUBST_AGGREGATE_NOTE}</p>
            </>
          )}
          <RankBar
            rounds={session.rounds}
            players={displayPlayers}
            settings={session.settings}
            rules={session.rules}
            roster={globalSettings.roster}
            loseAlertThreshold={globalSettings.loseAlertThreshold}
            tableState={tableState}
          />
          <RoundForm
            players={displayPlayers}
            rounds={session.rounds}
            roster={globalSettings.roster}
            rules={session.rules}
            tableState={tableState}
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
          {substituted && <p className="subst-notice">{SUBST_AGGREGATE_NOTE}</p>}
          <ScoreChart
            rounds={session.rounds}
            players={displayPlayers}
            settings={session.settings}
            rules={session.rules}
            tableState={tableState}
          />
          {/* 減法（創意檢視第六節）：Highlights 移出走勢圖 tab，集中到 P6 結算頁登場，不重複出現 */}
          <ShareCard
            session={session}
            players={displayPlayers}
            rounds={session.rounds}
            settings={session.settings}
            roster={globalSettings.roster}
          />
        </>
      )}

      {sub === 'detail' && (
        <>
          {substituted && <p className="subst-notice">{SUBST_AGGREGATE_NOTE}</p>}
          <Standings
            rounds={session.rounds}
            players={displayPlayers}
            settings={session.settings}
            rules={session.rules}
            tableState={tableState}
          />
          <RoundList
            rounds={session.rounds}
            players={session.players}
            settings={session.settings}
            rules={session.rules}
            tableState={tableState}
            substitutions={session.substitutions}
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
        {/* v2.4（批次 3）：換人入口——選當前在座座位、換成新玩家，自「下一局」起生效。 */}
        <SubstitutionPanel
          players={displayPlayers}
          roster={globalSettings.roster}
          roundCount={session.rounds.length}
          onSubstitute={(seatId, name, rosterId) =>
            addSubstitution(session.id, seatId, name, rosterId)
          }
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
