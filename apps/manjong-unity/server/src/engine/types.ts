import type { Tile, Wind } from './tiles.js';

export type MeldType = 'chi' | 'pon' | 'kan' | 'ankan' | 'kakan';

export interface Meld {
  type: MeldType;
  /** Sorted tiles; 3 for chi/pon, 4 for any kong. */
  tiles: Tile[];
  /** Seat the claimed tile came from; the owner's seat for ankan. */
  fromSeat: number;
  /** The tile taken from another player ("" for ankan). For kakan it is the originally ponged tile. */
  claimedTile: Tile;
}

export interface TaiItem {
  name: string;
  tai: number;
}

export interface HandResult {
  kind: 'win' | 'exhaustive';
  winnerSeat: number;
  loserSeat: number;
  selfDraw: boolean;
  winningTile: Tile;
  totalTai: number;
  items: TaiItem[];
  dealerTai: number;
  deltas: number[];
  gameOver: boolean;
}

export type { Tile, Wind };
