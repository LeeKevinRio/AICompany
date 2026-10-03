// Builds the per-seat view sent to the client. Hidden information (other hands, the wall)
// never leaves the server while a hand is in progress.

import { liveWallCount, optionsFor, roundWind, seatWind, type GameEvent, type GameOption, type GameState } from '../engine/engine.js';
import type { HandResult, Meld } from '../engine/types.js';

export interface MeldDto {
  type: Meld['type'];
  tiles: string[];
  fromSeat: number;
}

export interface PlayerViewDto {
  seat: number;
  name: string;
  avatar: string;
  isAi: boolean;
  seatWind: string;
  handCount: number;
  hand: string[];
  drawnTile: string;
  melds: MeldDto[];
  flowers: string[];
  discards: string[];
  sessionDelta: number;
}

export interface GameViewDto {
  gameId: string;
  phase: 'playing' | 'hand_end' | 'game_end';
  handNo: number;
  roundWind: string;
  dealerSeat: number;
  dealerStreak: number;
  mySeat: number;
  turnSeat: number;
  wallRemaining: number;
  lastDiscardSeat: number;
  lastDiscardTile: string;
  myCoins: number;
  players: PlayerViewDto[];
  options: GameOption[];
  hasResult: boolean;
  result: HandResult;
}

export interface EventDto {
  type: string;
  seat: number;
  tile: string;
  tiles: string[];
  text: string;
}

export interface SeatInfo {
  avatar: string;
  isAi: boolean;
}

const EMPTY_RESULT: HandResult = {
  kind: 'exhaustive',
  winnerSeat: -1,
  loserSeat: -1,
  selfDraw: false,
  winningTile: '',
  totalTai: 0,
  items: [],
  dealerTai: 0,
  deltas: [0, 0, 0, 0],
  gameOver: false,
};

export const NEXT_OPTION: GameOption = { id: 'next', type: 'next', tile: '', tiles: [], label: '下一局' };

/** Options for the viewer, including the session-level "next hand" option. */
export function viewerOptions(game: GameState, seat: number): GameOption[] {
  if (game.hand.phase.type === 'ended') return game.over ? [] : [NEXT_OPTION];
  return optionsFor(game, seat);
}

export function buildView(
  game: GameState,
  viewer: number,
  seats: SeatInfo[],
  myCoins: number,
  includeOptions: boolean,
): GameViewDto {
  const hand = game.hand;
  const ended = hand.phase.type === 'ended';
  const phase = hand.phase;
  const turnSeat = phase.type === 'turn' ? phase.seat : -1;

  const players = hand.players.map((p, seat): PlayerViewDto => {
    const visible = ended || seat === viewer;
    let concealed: string[] = [];
    let drawnTile = '';
    if (visible) {
      concealed = [...p.hand];
      if (!ended && p.drawn) {
        const i = concealed.lastIndexOf(p.drawn);
        if (i >= 0) concealed.splice(i, 1);
        drawnTile = p.drawn;
      }
    }
    return {
      seat,
      name: game.names[seat]!,
      avatar: seats[seat]!.avatar,
      isAi: seats[seat]!.isAi,
      seatWind: seatWind(game, seat),
      handCount: p.hand.length,
      hand: concealed,
      drawnTile,
      melds: p.melds.map((m) => ({ type: m.type, tiles: [...m.tiles], fromSeat: m.fromSeat })),
      flowers: [...p.flowers],
      discards: [...p.discards],
      sessionDelta: game.sessionDeltas[seat]!,
    };
  });

  return {
    gameId: game.id,
    phase: ended ? (game.over ? 'game_end' : 'hand_end') : 'playing',
    handNo: game.handNo,
    roundWind: roundWind(game),
    dealerSeat: hand.dealer,
    dealerStreak: hand.streak,
    mySeat: viewer,
    turnSeat,
    wallRemaining: liveWallCount(hand),
    lastDiscardSeat: hand.lastDiscard?.seat ?? -1,
    lastDiscardTile: hand.lastDiscard?.tile ?? '',
    myCoins,
    players,
    options: includeOptions ? viewerOptions(game, viewer) : [],
    hasResult: hand.result !== null,
    result: hand.result ?? EMPTY_RESULT,
  };
}

export function toEventDto(event: GameEvent, viewer: number): EventDto {
  const hidden = event.privateTo !== undefined && event.privateTo !== viewer;
  return {
    type: event.type,
    seat: event.seat,
    tile: hidden ? '' : event.tile,
    tiles: hidden ? [] : [...event.tiles],
    text: event.text,
  };
}
