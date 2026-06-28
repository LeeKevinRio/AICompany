// 核心資料型別：場（Session）/ 局（Round）/ 玩家（Player）/ 設定（Settings）
// 這層完全不依賴 React 或 DOM，未來可被原生 app 直接重用。

/** 玩家：MVP 固定 4 人，名字可改 */
export interface Player {
  id: string; // 'p1' | 'p2' | 'p3' | 'p4'
  name: string;
}

/** 金額設定：底與每台金額 */
export interface Settings {
  base: number; // 底
  tai: number; // 每台金額
}

/** 一局紀錄 */
export interface Round {
  id: string;
  winnerId: string; // 贏家 player id
  tai: number; // 台數（預留：莊家/連莊加台未來也疊在這欄）
  selfDraw: boolean; // true=自摸；false=胡牌(放槍)
  loserId: string | null; // 放槍者 id；自摸時為 null
  createdAt: number;
}

/** 一場牌局 */
export interface Session {
  id: string;
  name: string; // 場名
  players: Player[]; // 4 人
  settings: Settings; // 該場的底/台
  rounds: Round[];
  createdAt: number;
}

/** 預設玩家（名字可後續編輯） */
export const DEFAULT_PLAYERS: Player[] = [
  { id: 'p1', name: '玩家 1' },
  { id: 'p2', name: '玩家 2' },
  { id: 'p3', name: '玩家 3' },
  { id: 'p4', name: '玩家 4' },
];

/** 預設金額：底 100、台 50 */
export const DEFAULT_SETTINGS: Settings = { base: 100, tai: 50 };
