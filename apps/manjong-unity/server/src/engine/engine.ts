// Authoritative game state machine for one game (a sequence of hands) with four seats.
// Seats are 0..3 in turn order; the seat after s is (s + 1) % 4 (下家).
//
// The engine knows nothing about humans or AI: callers ask for each seat's legal options and
// submit an option id. Every state change is reported through an emit callback.

import { isComplete } from './hand.js';
import { createRng, shuffle, type Rng } from './rng.js';
import { RULES } from './rules.js';
import { dealerBonusTai, scoreFlowerWin, scoreWin, settle, type ScoreResult } from './scoring.js';
import {
  WINDS,
  WIND_ZH,
  codeOf,
  fullTileSet,
  isFlower,
  kindOf,
  runName,
  sortTiles,
  tileName,
  toCounts,
  type Tile,
  type Wind,
} from './tiles.js';
import type { HandResult, Meld } from './types.js';

export type EventType =
  | 'hand_start'
  | 'draw'
  | 'flower'
  | 'discard'
  | 'chi'
  | 'pon'
  | 'kan'
  | 'ankan'
  | 'kakan'
  | 'win'
  | 'exhaustive'
  | 'game_end';

export interface GameEvent {
  type: EventType;
  seat: number;
  tile: Tile;
  tiles: Tile[];
  text: string;
  /** When set, only this seat may see `tile` / `tiles`. */
  privateTo?: number;
}

export type Emit = (event: GameEvent) => void;

export type OptionType =
  | 'discard'
  | 'tsumo'
  | 'ron'
  | 'pon'
  | 'kan'
  | 'chi'
  | 'ankan'
  | 'kakan'
  | 'pass'
  | 'next';

export interface GameOption {
  id: string;
  type: OptionType;
  tile: Tile;
  tiles: Tile[];
  label: string;
}

export interface PlayerState {
  /** Concealed tiles, kept sorted; includes `drawn`. */
  hand: Tile[];
  drawn: Tile | null;
  melds: Meld[];
  flowers: Tile[];
  discards: Tile[];
  /** Has discarded at least once this hand (used for 天胡 / 地胡 / 人胡). */
  hasDiscarded: boolean;
}

type Phase =
  | { type: 'dealing' }
  | { type: 'turn'; seat: number; justDrew: boolean }
  | {
      type: 'claim';
      discarder: number;
      tile: Tile;
      options: GameOption[][];
      responses: (string | null)[];
    }
  | {
      type: 'robKong';
      seat: number;
      tile: Tile;
      options: GameOption[][];
      responses: (string | null)[];
    }
  | { type: 'ended' };

export interface HandState {
  /** Dealer, dealer streak and round index this hand was played with (the game advances them at hand end). */
  dealer: number;
  streak: number;
  roundIndex: number;
  wall: Tile[];
  players: PlayerState[];
  phase: Phase;
  noCallsYet: boolean;
  kongBloom: boolean;
  lastDiscard: { seat: number; tile: Tile } | null;
  result: HandResult | null;
}

export interface GameState {
  id: string;
  names: string[];
  rng: Rng;
  handNo: number;
  dealer: number;
  streak: number;
  dealerRotations: number;
  roundIndex: number;
  sessionDeltas: number[];
  over: boolean;
  hand: HandState;
}

const NO_TILE = '';

function opt(id: string, type: OptionType, label: string, tile: Tile = NO_TILE, tiles: Tile[] = []): GameOption {
  return { id, type, tile, tiles, label };
}

export function roundWind(game: GameState): Wind {
  return WINDS[Math.min(game.hand.roundIndex, 3)]!;
}

export function seatWind(game: GameState, seat: number): Wind {
  return WINDS[(seat - game.hand.dealer + 4) % 4]!;
}

export function liveWallCount(hand: HandState): number {
  return Math.max(0, hand.wall.length - RULES.deadWallSize);
}

function setsNeeded(p: PlayerState): number {
  return 5 - p.melds.length;
}

function removeTiles(hand: Tile[], tiles: Tile[]): void {
  for (const t of tiles) {
    const i = hand.indexOf(t);
    if (i < 0) throw new Error(`Tile ${t} not in hand`);
    hand.splice(i, 1);
  }
}

function countOf(hand: Tile[], tile: Tile): number {
  return hand.reduce((n, t) => (t === tile ? n + 1 : n), 0);
}

function removeLastDiscard(game: GameState, seat: number, tile: Tile): void {
  const river = game.hand.players[seat]!.discards;
  if (river[river.length - 1] === tile) river.pop();
}

// ---------------------------------------------------------------------------
// Game / hand lifecycle
// ---------------------------------------------------------------------------

/** Create a game in the "between hands" state; call nextHand() to deal the first hand. */
export function createGame(params: { id: string; names: string[]; seed?: number }): GameState {
  const rng = createRng(params.seed);
  const game: GameState = {
    id: params.id,
    names: params.names,
    rng,
    handNo: 0,
    dealer: rng.int(4),
    streak: 0,
    dealerRotations: 0,
    roundIndex: 0,
    sessionDeltas: [0, 0, 0, 0],
    over: false,
    hand: emptyHand(0, 0, 0),
  };
  return game;
}

function emptyHand(dealer: number, streak: number, roundIndex: number): HandState {
  return {
    dealer,
    streak,
    roundIndex,
    wall: [],
    players: [0, 1, 2, 3].map(() => ({
      hand: [],
      drawn: null,
      melds: [],
      flowers: [],
      discards: [],
      hasDiscarded: false,
    })),
    phase: { type: 'ended' },
    noCallsYet: true,
    kongBloom: false,
    lastDiscard: null,
    result: null,
  };
}

function startHand(game: GameState, emit: Emit): void {
  game.handNo++;
  const hand = emptyHand(game.dealer, game.streak, game.roundIndex);
  hand.phase = { type: 'dealing' };
  hand.wall = shuffle(fullTileSet(), game.rng);
  game.hand = hand;

  for (let i = 0; i < 4; i++) {
    const seat = (game.dealer + i) % 4;
    const count = i === 0 ? 17 : 16;
    const p = hand.players[seat]!;
    p.hand = sortTiles(hand.wall.splice(0, count));
  }

  emit({
    type: 'hand_start',
    seat: game.dealer,
    tile: NO_TILE,
    tiles: [],
    text: `第 ${game.handNo} 局開始（${WIND_ZH[roundWind(game)]}風圈，莊家：${game.names[game.dealer]}${
      game.streak > 0 ? `，連 ${game.streak}` : ''
    }）`,
  });

  // Initial flower replacement, dealer first, until nobody holds a flower.
  let replaced = true;
  while (replaced) {
    replaced = false;
    for (let i = 0; i < 4; i++) {
      const seat = (game.dealer + i) % 4;
      const p = hand.players[seat]!;
      let flower = p.hand.find(isFlower);
      while (flower !== undefined) {
        replaced = true;
        removeTiles(p.hand, [flower]);
        revealFlower(game, seat, flower, emit);
        if (hand.result) return;
        const replacement = hand.wall.pop();
        if (replacement === undefined) throw new Error('Wall exhausted during deal');
        p.hand = sortTiles([...p.hand, replacement]);
        flower = p.hand.find(isFlower);
      }
    }
  }
  hand.phase = { type: 'turn', seat: game.dealer, justDrew: true };
}

function revealFlower(game: GameState, seat: number, flower: Tile, emit: Emit): void {
  const hand = game.hand;
  hand.players[seat]!.flowers.push(flower);
  emit({ type: 'flower', seat, tile: flower, tiles: [], text: `${game.names[seat]} 補花 ${tileName(flower)}` });

  // 八仙過海
  if (hand.players[seat]!.flowers.length === 8) {
    finishWin(game, emit, {
      winner: seat,
      loser: -1,
      tile: flower,
      score: scoreFlowerWin('eightFlowers'),
    });
    return;
  }
  // 七搶一: a seat holding 7 flowers wins from the seat holding the 8th.
  const seven = hand.players.findIndex((p) => p.flowers.length === 7);
  const one = hand.players.findIndex((p) => p.flowers.length === 1);
  if (seven >= 0 && one >= 0 && seven !== one) {
    finishWin(game, emit, {
      winner: seven,
      loser: one,
      tile: flower,
      score: scoreFlowerWin('sevenRobOne'),
    });
  }
}

/** Draw for `seat` (from the back after a kong), replacing flowers, then hand the turn over. */
function drawFor(game: GameState, seat: number, fromBack: boolean, emit: Emit): void {
  const hand = game.hand;
  const p = hand.players[seat]!;
  let back = fromBack;
  for (;;) {
    if (liveWallCount(hand) <= 0) {
      finishExhaustive(game, emit);
      return;
    }
    const tile = back ? hand.wall.pop()! : hand.wall.shift()!;
    if (isFlower(tile)) {
      revealFlower(game, seat, tile, emit);
      if (hand.result) return;
      back = true;
      continue;
    }
    p.hand = sortTiles([...p.hand, tile]);
    p.drawn = tile;
    emit({ type: 'draw', seat, tile, tiles: [], text: '', privateTo: seat });
    hand.phase = { type: 'turn', seat, justDrew: true };
    return;
  }
}

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------

export function optionsFor(game: GameState, seat: number): GameOption[] {
  const hand = game.hand;
  const phase = hand.phase;
  switch (phase.type) {
    case 'turn':
      return phase.seat === seat ? turnOptions(game, seat, phase.justDrew) : [];
    case 'claim':
    case 'robKong':
      return phase.responses[seat] === null ? (phase.options[seat] ?? []) : [];
    case 'dealing':
    case 'ended':
      return [];
  }
}

/** Seats that currently owe a decision. */
export function pendingSeats(game: GameState): number[] {
  return [0, 1, 2, 3].filter((s) => optionsFor(game, s).length > 0);
}

function turnOptions(game: GameState, seat: number, justDrew: boolean): GameOption[] {
  const p = game.hand.players[seat]!;
  const options: GameOption[] = [];
  const canKong = liveWallCount(game.hand) > 0;
  if (justDrew) {
    if (isComplete(toCounts(p.hand), setsNeeded(p))) options.push(opt('tsumo', 'tsumo', '自摸'));
    if (canKong) {
      for (const t of new Set(p.hand)) {
        if (countOf(p.hand, t) === 4) options.push(opt(`ankan:${t}`, 'ankan', `暗槓 ${tileName(t)}`, t));
      }
      for (const m of p.melds) {
        const t = m.tiles[0]!;
        if (m.type === 'pon' && p.hand.includes(t)) {
          options.push(opt(`kakan:${t}`, 'kakan', `加槓 ${tileName(t)}`, t));
        }
      }
    }
  }
  for (const t of new Set(p.hand)) options.push(opt(`discard:${t}`, 'discard', `打 ${tileName(t)}`, t));
  return options;
}

function claimOptions(game: GameState, seat: number, discarder: number, tile: Tile): GameOption[] {
  const p = game.hand.players[seat]!;
  const options: GameOption[] = [];
  if (isComplete(toCounts([...p.hand, tile]), setsNeeded(p))) options.push(opt('ron', 'ron', '胡', tile));
  const n = countOf(p.hand, tile);
  if (n >= 2) options.push(opt('pon', 'pon', `碰 ${tileName(tile)}`, tile));
  if (n >= 3 && liveWallCount(game.hand) > 0) options.push(opt('kan', 'kan', `槓 ${tileName(tile)}`, tile));
  if (seat === (discarder + 1) % 4) {
    const k = kindOf(tile);
    if (k < 27) {
      const rank = k % 9;
      for (const low of [k - 2, k - 1, k]) {
        const lowRank = rank - (k - low);
        if (lowRank < 0 || lowRank > 6) continue;
        const run = [low, low + 1, low + 2].map(codeOf);
        const need = run.filter((t) => t !== tile);
        if (need.every((t) => p.hand.includes(t))) {
          options.push(opt(`chi:${run[0]}`, 'chi', `吃 ${runName(run)}`, tile, run));
        }
      }
    }
  }
  if (options.length > 0) options.push(opt('pass', 'pass', '過'));
  return options;
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

export class IllegalActionError extends Error {}

export function applyAction(game: GameState, seat: number, actionId: string, emit: Emit): void {
  const option = optionsFor(game, seat).find((o) => o.id === actionId);
  if (!option) throw new IllegalActionError(`Illegal action ${actionId} for seat ${seat}`);
  const phase = game.hand.phase;

  if (phase.type === 'claim' || phase.type === 'robKong') {
    phase.responses[seat] = actionId;
    if (phase.responses.every((r, s) => r !== null || (phase.options[s]?.length ?? 0) === 0)) {
      if (phase.type === 'claim') resolveClaim(game, emit);
      else resolveRobKong(game, emit);
    }
    return;
  }
  if (phase.type !== 'turn') throw new IllegalActionError('No action expected');

  switch (option.type) {
    case 'tsumo':
      return doTsumo(game, seat, emit);
    case 'discard':
      return doDiscard(game, seat, option.tile, emit);
    case 'ankan':
      return doAnkan(game, seat, option.tile, emit);
    case 'kakan':
      return doKakan(game, seat, option.tile, emit);
    default:
      throw new IllegalActionError(`Unexpected action ${actionId}`);
  }
}

/** Deal the first hand, or the next one after a hand has ended. */
export function nextHand(game: GameState, emit: Emit): void {
  if (game.hand.phase.type !== 'ended' || game.over) throw new IllegalActionError('Cannot start next hand');
  startHand(game, emit);
}

function doDiscard(game: GameState, seat: number, tile: Tile, emit: Emit): void {
  const hand = game.hand;
  const p = hand.players[seat]!;
  removeTiles(p.hand, [tile]);
  p.drawn = null;
  p.discards.push(tile);
  p.hasDiscarded = true;
  hand.kongBloom = false;
  hand.lastDiscard = { seat, tile };
  emit({ type: 'discard', seat, tile, tiles: [], text: `${game.names[seat]} 打出 ${tileName(tile)}` });

  const options = [0, 1, 2, 3].map((s) => (s === seat ? [] : claimOptions(game, s, seat, tile)));
  if (options.every((o) => o.length === 0)) {
    drawFor(game, (seat + 1) % 4, false, emit);
    return;
  }
  hand.phase = {
    type: 'claim',
    discarder: seat,
    tile,
    options,
    responses: options.map((o) => (o.length === 0 ? 'none' : null)),
  };
}

function resolveClaim(game: GameState, emit: Emit): void {
  const hand = game.hand;
  const phase = hand.phase;
  if (phase.type !== 'claim') return;
  const { discarder, tile } = phase;
  const order = [1, 2, 3].map((i) => (discarder + i) % 4);
  const chose = (s: number, prefix: string): boolean => phase.responses[s]?.startsWith(prefix) ?? false;

  const ronSeat = order.find((s) => phase.responses[s] === 'ron');
  if (ronSeat !== undefined) {
    removeLastDiscard(game, discarder, tile);
    const winner = hand.players[ronSeat]!;
    winner.hand = sortTiles([...winner.hand, tile]);
    const lastTile = liveWallCount(hand) <= 0;
    const human = hand.noCallsYet && !winner.hasDiscarded && ronSeat !== game.dealer;
    finishWin(game, emit, {
      winner: ronSeat,
      loser: discarder,
      tile,
      score: scoreFor(game, ronSeat, tile, false, { lastTile, human }),
    });
    return;
  }

  const ponSeat = order.find((s) => chose(s, 'pon') || chose(s, 'kan'));
  if (ponSeat !== undefined) {
    const isKan = phase.responses[ponSeat] === 'kan';
    const p = hand.players[ponSeat]!;
    removeTiles(p.hand, isKan ? [tile, tile, tile] : [tile, tile]);
    removeLastDiscard(game, discarder, tile);
    const tiles = isKan ? [tile, tile, tile, tile] : [tile, tile, tile];
    p.melds.push({ type: isKan ? 'kan' : 'pon', tiles, fromSeat: discarder });
    hand.noCallsYet = false;
    hand.lastDiscard = null;
    emit({
      type: isKan ? 'kan' : 'pon',
      seat: ponSeat,
      tile,
      tiles,
      text: `${game.names[ponSeat]} ${isKan ? '槓' : '碰'} ${tileName(tile)}`,
    });
    if (isKan) drawFor(game, ponSeat, true, emit);
    else hand.phase = { type: 'turn', seat: ponSeat, justDrew: false };
    if (isKan && hand.phase.type === 'turn') hand.kongBloom = true;
    return;
  }

  const chiSeat = (discarder + 1) % 4;
  const chiId = phase.responses[chiSeat];
  if (chiId?.startsWith('chi:')) {
    const option = phase.options[chiSeat]!.find((o) => o.id === chiId)!;
    const p = hand.players[chiSeat]!;
    const need = [...option.tiles];
    need.splice(need.indexOf(tile), 1);
    removeTiles(p.hand, need);
    removeLastDiscard(game, discarder, tile);
    p.melds.push({ type: 'chi', tiles: option.tiles, fromSeat: discarder });
    hand.noCallsYet = false;
    hand.lastDiscard = null;
    emit({ type: 'chi', seat: chiSeat, tile, tiles: option.tiles, text: `${game.names[chiSeat]} 吃 ${runName(option.tiles)}` });
    hand.phase = { type: 'turn', seat: chiSeat, justDrew: false };
    return;
  }

  drawFor(game, (discarder + 1) % 4, false, emit);
}

function doTsumo(game: GameState, seat: number, emit: Emit): void {
  const hand = game.hand;
  const p = hand.players[seat]!;
  const firstTurn = hand.noCallsYet && !p.hasDiscarded;
  const heaven = firstTurn && seat === game.dealer;
  const earth = firstTurn && seat !== game.dealer;
  const lastTile = liveWallCount(hand) <= 0;
  // The dealer's opening hand has no drawn tile: pick the interpretation that scores best.
  const candidates = p.drawn ? [p.drawn] : [...new Set(p.hand)];
  let best: { tile: Tile; score: ScoreResult } | null = null;
  for (const tile of candidates) {
    const score = scoreFor(game, seat, tile, true, { lastTile, heaven, earth, kongBloom: hand.kongBloom });
    if (!best || score.total > best.score.total) best = { tile, score };
  }
  if (!best) throw new Error('Tsumo without a winning hand');
  finishWin(game, emit, { winner: seat, loser: -1, tile: best.tile, score: best.score });
}

function doAnkan(game: GameState, seat: number, tile: Tile, emit: Emit): void {
  const hand = game.hand;
  const p = hand.players[seat]!;
  removeTiles(p.hand, [tile, tile, tile, tile]);
  p.drawn = null;
  p.melds.push({ type: 'ankan', tiles: [tile, tile, tile, tile], fromSeat: seat });
  hand.noCallsYet = false;
  emit({ type: 'ankan', seat, tile, tiles: [tile, tile, tile, tile], text: `${game.names[seat]} 暗槓` });
  drawFor(game, seat, true, emit);
  if (hand.phase.type === 'turn') hand.kongBloom = true;
}

function doKakan(game: GameState, seat: number, tile: Tile, emit: Emit): void {
  const hand = game.hand;
  const options = [0, 1, 2, 3].map((s) => {
    if (s === seat) return [];
    const p = hand.players[s]!;
    if (!isComplete(toCounts([...p.hand, tile]), setsNeeded(p))) return [];
    return [opt('ron', 'ron', '搶槓胡', tile), opt('pass', 'pass', '過')];
  });
  if (options.every((o) => o.length === 0)) {
    completeKakan(game, seat, tile, emit);
    return;
  }
  hand.phase = {
    type: 'robKong',
    seat,
    tile,
    options,
    responses: options.map((o) => (o.length === 0 ? 'none' : null)),
  };
}

function completeKakan(game: GameState, seat: number, tile: Tile, emit: Emit): void {
  const hand = game.hand;
  const p = hand.players[seat]!;
  removeTiles(p.hand, [tile]);
  p.drawn = null;
  const meld = p.melds.find((m) => m.type === 'pon' && m.tiles[0] === tile)!;
  meld.type = 'kakan';
  meld.tiles = [tile, tile, tile, tile];
  hand.noCallsYet = false;
  emit({ type: 'kakan', seat, tile, tiles: meld.tiles, text: `${game.names[seat]} 加槓 ${tileName(tile)}` });
  drawFor(game, seat, true, emit);
  if (hand.phase.type === 'turn') hand.kongBloom = true;
}

function resolveRobKong(game: GameState, emit: Emit): void {
  const hand = game.hand;
  const phase = hand.phase;
  if (phase.type !== 'robKong') return;
  const order = [1, 2, 3].map((i) => (phase.seat + i) % 4);
  const ronSeat = order.find((s) => phase.responses[s] === 'ron');
  if (ronSeat === undefined) {
    completeKakan(game, phase.seat, phase.tile, emit);
    return;
  }
  const kongPlayer = hand.players[phase.seat]!;
  removeTiles(kongPlayer.hand, [phase.tile]);
  kongPlayer.drawn = null;
  const winner = hand.players[ronSeat]!;
  winner.hand = sortTiles([...winner.hand, phase.tile]);
  finishWin(game, emit, {
    winner: ronSeat,
    loser: phase.seat,
    tile: phase.tile,
    score: scoreFor(game, ronSeat, phase.tile, false, { robKong: true }),
  });
}

function scoreFor(
  game: GameState,
  seat: number,
  winTile: Tile,
  selfDraw: boolean,
  flags: { lastTile?: boolean; heaven?: boolean; earth?: boolean; human?: boolean; robKong?: boolean; kongBloom?: boolean },
): ScoreResult {
  const p = game.hand.players[seat]!;
  const score = scoreWin({
    concealed: p.hand,
    melds: p.melds,
    flowers: p.flowers,
    winTile,
    selfDraw,
    seatWind: seatWind(game, seat),
    roundWind: roundWind(game),
    ...flags,
  });
  if (!score) throw new Error(`Seat ${seat} declared a win without a complete hand`);
  return score;
}

// ---------------------------------------------------------------------------
// Hand end
// ---------------------------------------------------------------------------

function finishWin(
  game: GameState,
  emit: Emit,
  win: { winner: number; loser: number; tile: Tile; score: ScoreResult },
): void {
  const selfDraw = win.loser < 0;
  const payers = selfDraw ? [0, 1, 2, 3].filter((s) => s !== win.winner) : [win.loser];
  const deltas = settle({
    winner: win.winner,
    payers,
    tai: win.score.total,
    dealer: game.dealer,
    streak: game.streak,
  });
  const dealerInvolved = win.winner === game.dealer || payers.includes(game.dealer);
  const result: HandResult = {
    kind: 'win',
    winnerSeat: win.winner,
    loserSeat: win.loser,
    selfDraw,
    winningTile: win.tile,
    totalTai: win.score.total,
    items: win.score.items,
    dealerTai: dealerInvolved ? dealerBonusTai(game.streak) : 0,
    deltas,
    gameOver: false,
  };
  const names = game.names;
  const text = selfDraw
    ? `${names[win.winner]} 自摸！${win.score.total} 台`
    : `${names[win.winner]} 胡牌！${names[win.loser]} 放槍，${win.score.total} 台`;
  endHand(game, result, win.winner === game.dealer, emit, {
    type: 'win',
    seat: win.winner,
    tile: win.tile,
    tiles: [],
    text,
  });
}

function finishExhaustive(game: GameState, emit: Emit): void {
  const result: HandResult = {
    kind: 'exhaustive',
    winnerSeat: -1,
    loserSeat: -1,
    selfDraw: false,
    winningTile: NO_TILE,
    totalTai: 0,
    items: [],
    dealerTai: 0,
    deltas: [0, 0, 0, 0],
    gameOver: false,
  };
  endHand(game, result, true, emit, { type: 'exhaustive', seat: -1, tile: NO_TILE, tiles: [], text: '流局，莊家連莊' });
}

function endHand(game: GameState, result: HandResult, dealerStays: boolean, emit: Emit, event: GameEvent): void {
  const hand = game.hand;
  for (let s = 0; s < 4; s++) game.sessionDeltas[s]! += result.deltas[s]!;
  if (dealerStays) {
    game.streak++;
  } else {
    game.dealer = (game.dealer + 1) % 4;
    game.streak = 0;
    game.dealerRotations++;
    if (game.dealerRotations % 4 === 0) game.roundIndex++;
  }
  game.over = game.roundIndex >= RULES.rounds;
  result.gameOver = game.over;
  hand.result = result;
  hand.phase = { type: 'ended' };
  for (const p of hand.players) p.drawn = null;
  emit(event);
  if (game.over) emit({ type: 'game_end', seat: -1, tile: NO_TILE, tiles: [], text: '整場結束' });
}

/** Total number of tiles in play; must always be 144. */
export function tileCount(game: GameState): number {
  const hand = game.hand;
  let n = hand.wall.length;
  for (const p of hand.players) {
    n += p.hand.length + p.flowers.length + p.discards.length;
    for (const m of p.melds) n += m.tiles.length;
  }
  return n;
}
