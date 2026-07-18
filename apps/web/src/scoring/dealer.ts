// v2.3（批次 2）：圈風 / 莊家 / 連莊推導——連莊系統的唯一真相來源只存 Session.dealerStartSeat，
// 當前莊家 / 圈風 / 局風 / 連莊數一律由本檔對 rounds 由前往後 fold 推導，**不 denormalize 進 Round**。
//
// 為什麼用推導而非狀態機：競品「北風圈最後兩風消失」正是手動維護狀態機 desync 的 bug。
// 純函式 fold 讓「刪一局 / 改一局」後圈風自動一致，永遠不會 desync；也符合本專案
// 「計分是純函式、可單元測試、未來原生 app 重用」的架構原則。代價是每次顯示要 fold 一次
// rounds（局數量級小，效能無虞）。
//
// 圈風模型（CEO 拍板 + 規劃 2-1）：
//   - 莊家胡牌 或 流局（drawn）→ 連莊（同一人續坐，streak += 1，dealerTurn 不動）。
//   - 別家胡 / 別家自摸 / 莊家放槍 → 過莊（下一座位坐莊，streak 歸 0，dealerTurn += 1）。
//   - dealerTurn = 累計「過莊」次數；圈風 = WINDS[⌊dealerTurn/4⌋ mod 4]、局風 = WINDS[dealerTurn mod 4]。
//     完整一場（東南西北四圈十六莊）= dealerTurn 0..15，過北風北局後續打（app 不強制結束）則 mod 4 續繞。
//
// 本檔不依賴 React / DOM，純資料進出。

import type { Session } from '../types';
import type { DealerContext } from './scoring';

/** 四風（圈風 / 局風）顯示字，順序即輪轉序。 */
export const WINDS = ['東', '南', '西', '北'] as const;
export type Wind = (typeof WINDS)[number];

/** 某一局的莊家 / 圈風上下文（推導結果，roundIndex 對齊 session.rounds）。 */
export interface PerRoundDealer {
  roundIndex: number;
  dealerId: string;
  circleWind: Wind;
  roundWind: Wind;
  /** 這一局的連莊數：0 = 該莊首坐、1 = 連 1（拉 1）… */
  streak: number;
}

/** 下一局（尚未記錄的當前局）的莊家 / 圈風。 */
export interface CurrentDealer {
  dealerId: string;
  circleWind: Wind;
  roundWind: Wind;
  streak: number;
}

/** 整場推導結果。 */
export interface TableState {
  /** 是否啟用連莊：dealerStartSeat 存在、rules.dealerEnabled 開、且起始座位合法。 */
  active: boolean;
  /** 每一局的莊家上下文（active=false 時為空陣列）。 */
  perRound: PerRoundDealer[];
  /** 下一局的莊 / 風（active=false 時為 null）。 */
  current: CurrentDealer | null;
}

const INACTIVE: TableState = { active: false, perRound: [], current: null };

/**
 * 從 session fold 推導圈風 / 莊家 / 連莊。舊場無 dealerStartSeat、或 dealerEnabled 關、
 * 或起始座位不在玩家清單 → 回 INACTIVE（連莊功能整體靜默不啟用）。
 */
export function deriveTableState(session: Session): TableState {
  const rules = session.rules;
  if (!session.dealerStartSeat) return INACTIVE;
  if (!rules || !rules.dealerEnabled) return INACTIVE;

  const seatOrder = session.players.map((p) => p.id);
  const startIndex = seatOrder.indexOf(session.dealerStartSeat);
  if (startIndex < 0 || seatOrder.length === 0) return INACTIVE;

  const seatCount = seatOrder.length; // MVP 恒為 4，但不寫死以防未來人數變動
  let dealerTurn = 0; // 累計過莊次數
  let streak = 0; // 當前莊連莊數（0 = 首坐莊）

  const dealerIdAt = (turn: number) => seatOrder[(startIndex + turn) % seatCount];
  const circleWindAt = (turn: number) => WINDS[Math.floor(turn / 4) % 4];
  const roundWindAt = (turn: number) => WINDS[turn % 4];

  const perRound: PerRoundDealer[] = [];

  session.rounds.forEach((round, i) => {
    const dealerId = dealerIdAt(dealerTurn);
    perRound.push({
      roundIndex: i,
      dealerId,
      circleWind: circleWindAt(dealerTurn),
      roundWind: roundWindAt(dealerTurn),
      streak,
    });

    // 連莊判定：莊家胡（winnerId === dealerId）或流局（drawn）→ 續莊；其餘 → 過莊。
    const continues = round.drawn === true || round.winnerId === dealerId;
    if (continues) {
      streak += 1;
    } else {
      dealerTurn += 1;
      streak = 0;
    }
  });

  const current: CurrentDealer = {
    dealerId: dealerIdAt(dealerTurn),
    circleWind: circleWindAt(dealerTurn),
    roundWind: roundWindAt(dealerTurn),
    streak,
  };

  return { active: true, perRound, current };
}

/**
 * 便利函式：把 deriveTableState 的 perRound 攤成「對齊 rounds 的 DealerContext 陣列」，
 * 供 scoreSession / settleSession / buildCumulativeTimeline / aggregateBy 逐局傳入計分。
 * active=false（含舊場）時回空陣列——呼叫端以 index 取值天然得到 undefined，計分零回歸。
 */
export function deriveDealerContexts(session: Session): (DealerContext | undefined)[] {
  const ts = deriveTableState(session);
  if (!ts.active) return [];
  return ts.perRound.map((pr) => ({ dealerId: pr.dealerId, streak: pr.streak }));
}
