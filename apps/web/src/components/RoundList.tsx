// 每局明細：贏家、台數、自摸/放槍、放槍者、備註，以及該局贏家收多少。
import { Fragment } from 'react';
import type { Player, Round, SessionRules, Settings, Substitution } from '../types';
import type { DealerContext } from '../scoring/scoring';
import {
  calcDealerBonusTai,
  calcDong,
  calcEyeTileTai,
  effectiveTai,
  scoreRound,
} from '../scoring/scoring';
import type { TableState } from '../scoring/dealer';
import { formatSigned } from '../scoring/timeline';
import { seatOccupantAt } from '../scoring/substitution';

interface Props {
  rounds: Round[];
  /** 初始佔用者（第 0 局起）；配合 substitutions 由 seatOccupantAt 解析每局實際在座者。 */
  players: Player[];
  settings: Settings;
  rules: SessionRules;
  /** v2.3：連莊推導。流局列顯示「莊連N」、連莊加台局標「含莊X台」，金額含連莊加台。 */
  tableState?: TableState;
  /** v2.4（批次 3）：中途換人時間軸。每局贏家 / 放槍者名字顯示「當時在座者」，換人局前插分隔列。 */
  substitutions?: Substitution[];
  onRemove: (roundId: string) => void;
}

export function RoundList({
  rounds,
  players,
  settings,
  rules,
  tableState,
  substitutions,
  onRemove,
}: Props) {
  const perRound = tableState?.active ? tableState.perRound : undefined;
  const seatSource = { players, substitutions };
  // v2.4：某座位在第 i 局的實際在座者名字（無換人時等同初始 players，零回歸）。
  const nameAt = (id: string | null, roundIndex: number) =>
    id ? seatOccupantAt(seatSource, id, roundIndex).name : '—';
  // 換人分隔列：以 fromRoundIndex 為 key 收集「這局起生效」的換人（顯示前一位 → 接手者）。
  const subsByRound = new Map<number, Substitution[]>();
  for (const sub of substitutions ?? []) {
    const list = subsByRound.get(sub.fromRoundIndex) ?? [];
    list.push(sub);
    subsByRound.set(sub.fromRoundIndex, list);
  }
  const seatLabel = (seatId: string) => {
    const idx = players.findIndex((p) => p.id === seatId);
    return idx >= 0 ? `玩家 ${idx + 1}` : seatId;
  };

  if (rounds.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon">🀄</div>
        <p className="empty-title">尚無紀錄</p>
        <p>切到「記局」開始第一局吧。</p>
      </div>
    );
  }

  return (
    <section className="card">
      <h2>每局明細</h2>
      <ol className="round-list">
        {rounds.map((r, i) => {
          // v2.4：這局起生效的換人 → 前插分隔列「↓ 此局起 玩家X＝阿明」（顯示前一位與接手者）。
          const subsHere = subsByRound.get(i);
          const divider = subsHere && (
            <li className="round-subst-divider" aria-hidden>
              {subsHere.map((sub) => (
                <span key={sub.seatId} className="round-subst-tag">
                  ↓ 此局起 {seatLabel(sub.seatId)}：{nameAt(sub.seatId, i - 1)} → {sub.name}
                </span>
              ))}
            </li>
          );

          // v2.3：流局列——無金額、灰階、顯示「流局 莊連N」（streak 由推導取得）。
          if (r.drawn) {
            const streak = perRound?.[i]?.streak ?? 0;
            return (
              <Fragment key={r.id}>
                {divider}
                <li className="round-item round-drawn-row">
                  <span className="round-no">#{i + 1}</span>
                  <span className="round-drawn-label">流局</span>
                  <span className="round-drawn-streak">
                    {streak >= 1 ? `莊連${streak}` : '莊'}
                  </span>
                  <span className="round-drawn-amount">—</span>
                  <button
                    className="link danger"
                    onClick={() => onRemove(r.id)}
                    aria-label="刪除此局"
                  >
                    刪除
                  </button>
                </li>
              </Fragment>
            );
          }

          const dctx: DealerContext | undefined = perRound?.[i]
            ? { dealerId: perRound[i].dealerId, streak: perRound[i].streak }
            : undefined;
          const eTai = effectiveTai(r, rules);
          const eyeTai = calcEyeTileTai(r, rules);
          // 「+N」只表示自摸加台（眼牌另用「眼」標示，維持金額來源可回推）。
          const bonus = eTai - r.tai - eyeTai;
          const dong = calcDong(r, rules);
          // 贏家實收：直接取計分 delta（含連莊 / 眼牌加台），確保與排名條 / 結算一致。
          let win = 0;
          try {
            win = scoreRound(r, players, settings, rules, dctx)[r.winnerId] ?? 0;
          } catch {
            win = 0;
          }
          // 連莊加台是否實際套在本局（scope='dealer' 只在牽涉莊家的支付才加）：
          // 自摸一定牽涉莊家；放槍看贏家 / 放槍者是否為莊。
          const dealerBonusTai = calcDealerBonusTai(rules, dctx);
          const dealerInvolved =
            !!dctx &&
            dealerBonusTai > 0 &&
            (r.selfDraw || r.winnerId === dctx.dealerId || r.loserId === dctx.dealerId);
          return (
            <Fragment key={r.id}>
              {divider}
              <li className="round-item">
                <span className="round-no">#{i + 1}</span>
                <span className="round-main">
                  <strong>{nameAt(r.winnerId, i)}</strong> {r.tai}
                  {bonus > 0 && <span className="round-bonus">+{bonus}</span>} 台{' '}
                  {r.selfDraw ? '自摸' : `放槍（${nameAt(r.loserId, i)}）`}
                  {eyeTai > 0 && <span className="round-eye">眼 +{eyeTai} 台</span>}
                  {dong > 0 && <span className="round-dong">東錢 ${dong}</span>}
                  {r.note && <span className="round-note">📝 {r.note}</span>}
                </span>
                <span className="round-amt-col">
                  <span className="round-amt">{formatSigned(win)}</span>
                  {dealerInvolved && <span className="tai-source">含莊{dealerBonusTai}台</span>}
                </span>
                <button
                  className="link danger"
                  onClick={() => onRemove(r.id)}
                  aria-label="刪除此局"
                >
                  刪除
                </button>
              </li>
            </Fragment>
          );
        })}
      </ol>
    </section>
  );
}
