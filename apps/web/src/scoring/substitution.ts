// v2.4（批次 3）：中途換人——座位時間軸解析。
//
// 唯一真相來源：Session.players（第 0 局起的初始佔用者）+ Session.substitutions（時間軸異動）。
// 「某局某座位實際是誰」一律由本檔對 substitutions 解析推導，**不 denormalize 進 Round**，
// 與 dealer.ts 的 deriveTableState 同一種 fold 心智模型（先做連莊、再做換人可複用）。
//
// 核心不變量：錢永遠掛在座位（p1~p4），四人零和結構不動——scoreRound / settleSession 完全不看
// substitutions。換人只影響「歸戶 / 顯示層」（哪些局算在哪個人頭上、座位當下顯示誰的名字）。
//
// 本檔不依賴 React / DOM，純資料進出。

import type { Player, Session } from '../types';

/** 解析座位佔用者只需要 players 與 substitutions 兩塊，故收窄型別、方便被局部資料呼叫。 */
export type SeatSource = Pick<Session, 'players' | 'substitutions'>;

/**
 * 解析「第 roundIndex 局時，seatId 座位實際是誰」。
 *
 * 演算法：取所有 seatId 座位、`fromRoundIndex ≤ roundIndex` 的換人紀錄中 fromRoundIndex 最大者；
 * 沒有換人紀錄命中 → 回 players 裡該座位的初始佔用者（第 0 局起）。回傳的 id 一律為座位 id。
 *
 * 邊界：
 *  - 第 0 局（roundIndex=0）：只有 fromRoundIndex=0 的換人才會命中；一般 UI 限制 fromRoundIndex ≥
 *    已記局數，故第 0 局通常回初始佔用者。
 *  - 舊場無 substitutions → 一律回初始佔用者，行為零變化。
 *  - 座位不存在於 players（理論上不會發生）→ 回一個以 seatId 命名的占位 Player，避免回傳 undefined。
 */
export function seatOccupantAt(
  source: SeatSource,
  seatId: string,
  roundIndex: number,
): Player {
  const subs = source.substitutions ?? [];
  let latest: { fromRoundIndex: number; name: string; rosterId?: string } | null = null;
  for (const sub of subs) {
    if (sub.seatId !== seatId) continue;
    if (sub.fromRoundIndex > roundIndex) continue;
    // fromRoundIndex 相同時取後出現者（陣列順序即加入順序），與 UI「後換人覆蓋」直覺一致。
    if (!latest || sub.fromRoundIndex >= latest.fromRoundIndex) latest = sub;
  }
  if (latest) {
    return { id: seatId, name: latest.name, rosterId: latest.rosterId };
  }
  const base = source.players.find((p) => p.id === seatId);
  return base ?? { id: seatId, name: seatId };
}

/**
 * 便利函式：回傳「第 roundIndex 局時」四個座位的實際佔用者（保持 players 的座位順序）。
 * 顯示層用來把座位標成當下 / 當局在座者的名字與名冊連結（頭像 / 代表色）。
 * 舊場 / 無換人時回傳與 players 等價（僅名字 / rosterId 相同）的新陣列，零回歸。
 */
export function occupantPlayersAt(source: SeatSource, roundIndex: number): Player[] {
  return source.players.map((p) => seatOccupantAt(source, p.id, roundIndex));
}

/** 這場是否有任何換人紀錄（供 UI 決定要不要顯示「本場已換人」提示）。 */
export function hasSubstitutions(source: SeatSource): boolean {
  return (source.substitutions?.length ?? 0) > 0;
}
