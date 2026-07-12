// 核心資料型別：場（Session）/ 局（Round）/ 玩家（Player）/ 設定（Settings）
// 這層完全不依賴 React 或 DOM，未來可被原生 app 直接重用。

/** 玩家：MVP 固定 4 人，名字可改 */
export interface Player {
  id: string; // 'p1' | 'p2' | 'p3' | 'p4'
  name: string;
  /**
   * v2.1：連結到名冊成員 RosterPlayer.id（從名冊選入才有值）。
   * 舊資料無此欄位 → undefined，視為「無掛勾的歷史玩家」，統計時 fallback 用名字聚合。
   */
  rosterId?: string;
}

/**
 * v2.1：玩家名冊成員——跨場的獨立玩家實體。
 * id 為全域唯一 UUID，不隨名字變動，讓跨場戰績能精準辨識「同一個人」。
 */
export interface RosterPlayer {
  id: string; // crypto.randomUUID()
  name: string; // 顯示名稱（可改）
  avatar?: string; // v2.1 建議做：emoji 頭像（單一字元 emoji；無則用名字首字）
  createdAt: number;
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
  /** v2：局次備註（最多 20 字，可選；舊資料無此欄位視為空字串） */
  note?: string;
  /**
   * v2.2（牌桌規則補完 批次 1）：這局是否為「眼牌」。
   * 記局時勾選；舊資料無此欄位 → undefined，視為「非眼牌」。
   * 只有在該場 rules.eyeTileEnabled 時才會生效並顯示勾選。
   */
  eyeTile?: boolean;
}

/**
 * v2.1：開桌規則組——存進每場 Session，跨場可不同。
 * 計分相關規則放這裡，與底/台金額（Settings）分離。
 */
export interface SessionRules {
  /** 自摸自動加台數（0=關閉）。僅自摸時生效，放槍不受影響。 */
  selfDrawBonusTai: number;
  /**
   * 東錢：自摸者每次自摸要付的金額（0=關閉）。
   * CEO 定案解讀：這筆錢是自摸者「單向流出」，進該場「公基金」（kitty），
   * 獨立累計、不併入四人互相輸贏的零和。詳見 scoring.ts。
   */
  selfDrawDongAmount: number;
  /**
   * v2.2（牌桌規則補完 批次 1）：眼牌規則總開關（舊場 migration = false）。
   * 開啟後，記局才會出現「眼牌」勾選，且被標記的局會套用眼牌加台。
   */
  eyeTileEnabled: boolean;
  /**
   * v2.2：眼牌加台數。CEO 拍板：加 1 台、自摸/放槍都算、照一般支付規則（維持四人零和）。
   * 舊場 migration = 0（中性值，不動歷史分數）。
   */
  eyeTileTai: number;
}

/** 一場牌局 */
export interface Session {
  id: string;
  name: string; // 場名
  players: Player[]; // 4 人
  settings: Settings; // 該場的底/台
  /** v2.1：開桌規則組（舊場次 migration 用 DEFAULT_SESSION_RULES 補入，行為不變） */
  rules: SessionRules;
  rounds: Round[];
  createdAt: number;
  /** v2：結算時間戳（按下「結算本場」才有；未結算為 undefined） */
  endedAt?: number;
}

/**
 * v2：全域設定（與單場 session 內設定分離）。
 * 新建牌局時套用此預設，常用玩家可一鍵帶入。
 */
export interface GlobalSettings {
  defaultBase: number; // 預設底
  defaultTai: number; // 預設每台
  knownPlayers: string[]; // 常用玩家名稱列表（最多 8 個）
  /** v2.1：玩家名冊（跨場獨立玩家實體） */
  roster: RosterPlayer[];
  /** v2.1：開桌規則預設（新建牌局時套用，開桌仍可調整） */
  defaultRules: SessionRules;
  /** v2.1 建議做：單場輸贏警戒線金額（0=關閉）。單場輸超過此值在排名條紅色警示。 */
  loseAlertThreshold: number;
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

/**
 * v2.1：新開桌的規則預設——CEO 定案：自摸加台預設 1、東錢預設開啟 100。
 * 注意：與「舊場次 migration 補值」（DEFAULT_SESSION_RULES）不同，
 * 後者必須補 0，避免改變歷史分數。
 */
export const DEFAULT_NEW_SESSION_RULES: SessionRules = {
  selfDrawBonusTai: 1,
  selfDrawDongAmount: 100,
  // v2.2：眼牌 CEO 拍板預設開、加 1 台（自摸/放槍都算）。
  eyeTileEnabled: true,
  eyeTileTai: 1,
};

/**
 * v2.1：舊場次（無 rules 欄位）migration 補入的預設值。
 * 必須全為 0，否則所有歷史場次的分數會被改變，造成資料錯亂（見企劃 7-1）。
 */
export const DEFAULT_SESSION_RULES: SessionRules = {
  selfDrawBonusTai: 0,
  selfDrawDongAmount: 0,
  // v2.2：舊場眼牌一律關、加台 0 → 歷史分數一字不變。
  eyeTileEnabled: false,
  eyeTileTai: 0,
};

/** v2：預設全域設定 */
export const DEFAULT_GLOBAL_SETTINGS: GlobalSettings = {
  defaultBase: 100,
  defaultTai: 50,
  knownPlayers: [],
  roster: [],
  defaultRules: { ...DEFAULT_NEW_SESSION_RULES },
  loseAlertThreshold: 0,
};

/** 常用玩家數量上限 */
export const MAX_KNOWN_PLAYERS = 8;

/** 局次備註長度上限 */
export const MAX_NOTE_LENGTH = 20;
