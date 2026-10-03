// Single source of truth for configurable rule values.
// Spec: work/manjong-unity/規則與台數表.md — keep both in sync.

export const TAI = {
  menqing: { name: '門清', tai: 1 },
  zimo: { name: '自摸', tai: 1 },
  menqingZimo: { name: '門清自摸', tai: 3 },
  roundWind: { name: '圈風刻', tai: 1 },
  seatWind: { name: '門風刻', tai: 1 },
  dragonRed: { name: '紅中', tai: 1 },
  dragonGreen: { name: '青發', tai: 1 },
  dragonWhite: { name: '白板', tai: 1 },
  seatFlower: { name: '正花', tai: 1 },
  flowerSetSeasons: { name: '花槓（春夏秋冬）', tai: 2 },
  flowerSetPlants: { name: '花槓（梅蘭竹菊）', tai: 2 },
  singleWait: { name: '獨聽', tai: 1 },
  robKong: { name: '搶槓', tai: 1 },
  kongBloom: { name: '槓上開花', tai: 1 },
  lastTileDraw: { name: '海底撈月', tai: 1 },
  lastTileDiscard: { name: '河底撈魚', tai: 1 },
  pinghu: { name: '平胡', tai: 2 },
  allMelded: { name: '全求人', tai: 2 },
  threeConcealed: { name: '三暗刻', tai: 2 },
  allTriplets: { name: '碰碰胡', tai: 4 },
  halfFlush: { name: '混一色', tai: 4 },
  littleDragons: { name: '小三元', tai: 4 },
  fourConcealed: { name: '四暗刻', tai: 5 },
  fullFlush: { name: '清一色', tai: 8 },
  fiveConcealed: { name: '五暗刻', tai: 8 },
  bigDragons: { name: '大三元', tai: 8 },
  littleWinds: { name: '小四喜', tai: 8 },
  ligu: { name: '嚦咕嚦咕', tai: 8 },
  eightFlowers: { name: '八仙過海', tai: 8 },
  sevenRobOne: { name: '七搶一', tai: 8 },
  humanWin: { name: '人胡', tai: 8 },
  earthWin: { name: '地胡', tai: 16 },
  heavenWin: { name: '天胡', tai: 24 },
  bigWinds: { name: '大四喜', tai: 16 },
  allHonors: { name: '字一色', tai: 16 },
} as const;

export type TaiKey = keyof typeof TAI;

export const RULES = {
  /** Tiles kept back at the end of the wall; the hand is drawn when only these remain. */
  deadWallSize: 16,
  /** Number of prevailing-wind rounds per game (1 = 東風圈 only). */
  rounds: 1,
  /** Dealer bonus on dealer-involved payments: base + perStreak * streak (連 N 拉 N = 2N). */
  dealerBaseTai: 1,
  dealerTaiPerStreak: 2,
} as const;

export const ECONOMY = {
  base: 100,
  perTai: 50,
  startingCoins: 20_000,
  minCoinsToPlay: 1_000,
  reliefAmount: 10_000,
} as const;
