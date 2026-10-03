// Tile codes and helpers for Taiwanese 16-tile mahjong.
//
// Playable tiles are mapped to a dense index 0..33 so hands can be analysed as count arrays:
//   0..8   characters (1m..9m)
//   9..17  dots       (1p..9p)
//   18..26 bamboo     (1s..9s)
//   27..30 winds      (E S W N)
//   31..33 dragons    (RD GD WD)
// Flowers (F1..F8) are never part of a hand; they are revealed and replaced immediately.

export type Tile = string;

export const KIND_COUNT = 34;

const SUITS = ['m', 'p', 's'] as const;
export const WINDS = ['E', 'S', 'W', 'N'] as const;
export const DRAGONS = ['RD', 'GD', 'WD'] as const;
export const FLOWERS = ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8'] as const;

export type Wind = (typeof WINDS)[number];

const KIND_CODES: Tile[] = [
  ...SUITS.flatMap((s) => Array.from({ length: 9 }, (_, i) => `${i + 1}${s}`)),
  ...WINDS,
  ...DRAGONS,
];

const CODE_TO_KIND = new Map<Tile, number>(KIND_CODES.map((c, i) => [c, i]));

export function kindOf(tile: Tile): number {
  const k = CODE_TO_KIND.get(tile);
  if (k === undefined) throw new Error(`Not a playable tile: ${tile}`);
  return k;
}

export function codeOf(kind: number): Tile {
  const c = KIND_CODES[kind];
  if (c === undefined) throw new Error(`Invalid tile kind: ${kind}`);
  return c;
}

export function isFlower(tile: Tile): boolean {
  return /^F[1-8]$/.test(tile);
}

export function isPlayable(tile: Tile): boolean {
  return CODE_TO_KIND.has(tile);
}

export function isHonorKind(kind: number): boolean {
  return kind >= 27;
}

export function isDragonKind(kind: number): boolean {
  return kind >= 31;
}

export function isWindKind(kind: number): boolean {
  return kind >= 27 && kind <= 30;
}

/** 0 = characters, 1 = dots, 2 = bamboo, 3 = honors */
export function suitOfKind(kind: number): number {
  return Math.min(3, Math.floor(kind / 9));
}

/** 1..9 for suited tiles, 0 for honors. */
export function rankOfKind(kind: number): number {
  return kind < 27 ? (kind % 9) + 1 : 0;
}

export function windKind(w: Wind): number {
  return 27 + WINDS.indexOf(w);
}

/** Flower number 1..8; seat-matching flowers are n and n+4 for seat wind index n-1. */
export function flowerNumber(tile: Tile): number {
  return Number(tile.slice(1));
}

/** Full 144-tile set, unshuffled. */
export function fullTileSet(): Tile[] {
  const tiles: Tile[] = [];
  for (const code of KIND_CODES) for (let i = 0; i < 4; i++) tiles.push(code);
  tiles.push(...FLOWERS);
  return tiles;
}

/** Sort order: suits, winds, dragons, then flowers (flowers only appear in hands while dealing). */
function sortKey(tile: Tile): number {
  return isFlower(tile) ? KIND_COUNT + flowerNumber(tile) : kindOf(tile);
}

export function sortTiles(tiles: Tile[]): Tile[] {
  return [...tiles].sort((a, b) => sortKey(a) - sortKey(b));
}

export function toCounts(tiles: Tile[]): number[] {
  const counts = new Array<number>(KIND_COUNT).fill(0);
  for (const t of tiles) counts[kindOf(t)]!++;
  return counts;
}

const NUM_ZH = ['一', '二', '三', '四', '五', '六', '七', '八', '九'];
const SUIT_ZH: Record<string, string> = { m: '萬', p: '筒', s: '條' };
const HONOR_ZH: Record<string, string> = {
  E: '東風',
  S: '南風',
  W: '西風',
  N: '北風',
  RD: '紅中',
  GD: '青發',
  WD: '白板',
};
const FLOWER_ZH = ['春', '夏', '秋', '冬', '梅', '蘭', '竹', '菊'];
export const WIND_ZH: Record<Wind, string> = { E: '東', S: '南', W: '西', N: '北' };

/** Traditional Chinese display name, e.g. "5m" -> "五萬". */
export function tileName(tile: Tile): string {
  if (isFlower(tile)) return FLOWER_ZH[flowerNumber(tile) - 1]!;
  const honor = HONOR_ZH[tile];
  if (honor) return honor;
  const n = Number(tile[0]);
  return `${NUM_ZH[n - 1]}${SUIT_ZH[tile[1]!]}`;
}

/** Compact name for a run of suited tiles, e.g. ["3m","4m","5m"] -> "三四五萬". */
export function runName(tiles: Tile[]): string {
  const suit = tiles[0]![1]!;
  return tiles.map((t) => NUM_ZH[Number(t[0]) - 1]).join('') + SUIT_ZH[suit];
}
