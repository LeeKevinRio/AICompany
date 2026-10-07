import { describe, expect, it } from 'vitest';
import { chooseAction, type Personality } from '../src/ai/ai.js';
import {
  IllegalActionError,
  applyAction,
  createGame,
  nextHand,
  optionsFor,
  pendingSeats,
  tileCount,
  type GameEvent,
  type GameState,
} from '../src/engine/engine.js';
import { RULES } from '../src/engine/rules.js';
import { createRng } from '../src/engine/rng.js';
import { sortTiles } from '../src/engine/tiles.js';
import type { Meld } from '../src/engine/types.js';
import { simulateGame } from '../src/game/simulate.js';
import { meld, tiles } from './helpers.js';

interface Setup {
  hands: string[];
  /** Live tiles drawn from the front. */
  front?: string;
  /** Tiles at the very back (kong replacements), last one drawn first. */
  back?: string;
  turn: number;
  justDrew?: boolean;
  drawn?: string;
  melds?: Meld[][];
  flowers?: string[][];
  dealer?: number;
  /** First go-around: nobody has discarded or called yet (天胡 / 地胡 / 人胡). */
  fresh?: boolean;
  /** Seats that have already declared ready (報聽). */
  declared?: number[];
}

function setup(cfg: Setup): { game: GameState; events: GameEvent[]; emit: (e: GameEvent) => void } {
  const events: GameEvent[] = [];
  const emit = (e: GameEvent): void => {
    events.push(e);
  };
  const game = createGame({ id: 't', names: ['A', 'B', 'C', 'D'], seed: 7 });
  nextHand(game, () => {});
  game.dealer = cfg.dealer ?? 0;
  game.streak = 0;
  const hand = game.hand;
  hand.dealer = game.dealer;
  hand.streak = 0;
  hand.roundIndex = 0;
  hand.result = null;
  hand.noCallsYet = cfg.fresh ?? false;
  hand.kongBloom = false;
  hand.lastDiscard = null;
  hand.players.forEach((p, i) => {
    p.hand = sortTiles(tiles(cfg.hands[i] ?? ''));
    p.melds = cfg.melds?.[i] ?? [];
    p.flowers = cfg.flowers?.[i] ?? [];
    p.discards = [];
    p.drawn = i === cfg.turn ? (cfg.drawn ?? null) : null;
    p.hasDiscarded = !cfg.fresh;
    p.declared = cfg.declared?.includes(i) ?? false;
  });
  const back = tiles(cfg.back ?? '');
  const filler = Array.from({ length: RULES.deadWallSize - back.length }, () => 'WD');
  hand.wall = [...tiles(cfg.front ?? ''), ...filler, ...back];
  hand.phase = { type: 'turn', seat: cfg.turn, justDrew: cfg.justDrew ?? true };
  return { game, events, emit };
}

const ids = (game: GameState, seat: number) => optionsFor(game, seat).map((o) => o.id);

// Seat 3 waits on 5m (單吊); seat 1 can chi 4m-6m; seat 2 can pon 5m.
const CLAIM_HANDS = [
  '5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s 4s 5s 6s E',
  '4m 6m 111p 222p 333s 444s 9s 7s',
  '5m 5m 111s 999s 777p 333p E N',
  '123m 456p 789p 234s 567s 5m',
];

describe('claims', () => {
  it('offers chi only to the next seat, pon / ron to anyone', () => {
    const { game, emit } = setup({ hands: CLAIM_HANDS, front: '9m 9m', turn: 0 });
    applyAction(game, 0, 'discard:5m', emit);
    expect(ids(game, 1)).toEqual(['chi:4m', 'pass']);
    expect(ids(game, 2)).toEqual(['pon', 'pass']);
    expect(ids(game, 3)).toEqual(['ron', 'pass']);
  });

  it('ron beats pon beats chi', () => {
    const { game, emit } = setup({ hands: CLAIM_HANDS, front: '9m 9m', turn: 0 });
    applyAction(game, 0, 'discard:5m', emit);
    applyAction(game, 1, 'chi:4m', emit);
    applyAction(game, 2, 'pon', emit);
    applyAction(game, 3, 'ron', emit);
    expect(game.hand.result?.winnerSeat).toBe(3);
    expect(game.hand.result?.loserSeat).toBe(0);
  });

  it('pon beats chi and gives the turn without a draw', () => {
    const { game, emit } = setup({ hands: CLAIM_HANDS, front: '9m 9m', turn: 0 });
    applyAction(game, 0, 'discard:5m', emit);
    applyAction(game, 1, 'chi:4m', emit);
    applyAction(game, 2, 'pon', emit);
    applyAction(game, 3, 'pass', emit);
    expect(game.hand.players[2]!.melds).toEqual([{ type: 'pon', tiles: ['5m', '5m', '5m'], fromSeat: 0, claimedTile: '5m' }]);
    expect(game.hand.players[0]!.discards).toEqual([]);
    expect(game.hand.phase).toEqual({ type: 'turn', seat: 2, justDrew: false });
    // No draw, so no tsumo / kongs: only discards, plus 報聽 for the discards that leave the hand ready.
    expect(ids(game, 2).every((id) => id.startsWith('discard:') || id.startsWith('ting:'))).toBe(true);
    expect(ids(game, 2).filter((id) => id.startsWith('ting:')).sort()).toEqual(['ting:E', 'ting:N']);
  });

  it('chi when nobody else claims', () => {
    const { game, emit } = setup({ hands: CLAIM_HANDS, front: '9m 9m', turn: 0 });
    applyAction(game, 0, 'discard:5m', emit);
    applyAction(game, 1, 'chi:4m', emit);
    applyAction(game, 2, 'pass', emit);
    applyAction(game, 3, 'pass', emit);
    expect(game.hand.players[1]!.melds[0]).toEqual({ type: 'chi', tiles: ['4m', '5m', '6m'], fromSeat: 0, claimedTile: '5m' });
    expect(game.hand.players[1]!.hand).not.toContain('4m');
  });

  it('nearest seat wins when two players can ron (no double ron)', () => {
    const hands = [...CLAIM_HANDS];
    hands[1] = '123m 456p 789p 234s 567s 5m';
    const { game, emit } = setup({ hands, front: '9m 9m', turn: 0 });
    applyAction(game, 0, 'discard:5m', emit);
    applyAction(game, 1, 'ron', emit);
    applyAction(game, 2, 'pass', emit);
    applyAction(game, 3, 'ron', emit);
    expect(game.hand.result?.winnerSeat).toBe(1);
  });

  it('rejects illegal actions', () => {
    const { game, emit } = setup({ hands: CLAIM_HANDS, front: '9m 9m', turn: 0 });
    expect(() => applyAction(game, 0, 'discard:9s', emit)).toThrow(IllegalActionError);
    expect(() => applyAction(game, 1, 'discard:4m', emit)).toThrow(IllegalActionError);
  });
});

describe('kongs', () => {
  it('kakan can be robbed (搶槓)', () => {
    const { game, emit } = setup({
      hands: ['5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s E', '', '123m 456p 789p 234s 567s 5m', ''],
      melds: [[meld('pon', '5m 5m 5m', 1)]],
      front: '9m',
      turn: 0,
      drawn: '5m',
    });
    expect(ids(game, 0)).toContain('kakan:5m');
    applyAction(game, 0, 'kakan:5m', emit);
    expect(ids(game, 2)).toEqual(['ron', 'pass']);
    applyAction(game, 2, 'ron', emit);
    const r = game.hand.result!;
    expect(r.winnerSeat).toBe(2);
    expect(r.loserSeat).toBe(0);
    expect(r.items.map((i) => i.name)).toContain('搶槓');
  });

  it('kakan completes and draws a replacement when not robbed', () => {
    const { game, emit } = setup({
      hands: ['5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s E', '', '123m 456p 789p 234s 567s 5m', ''],
      melds: [[meld('pon', '5m 5m 5m', 1)]],
      front: '9m',
      back: 'S',
      turn: 0,
      drawn: '5m',
    });
    applyAction(game, 0, 'kakan:5m', emit);
    applyAction(game, 2, 'pass', emit);
    const p = game.hand.players[0]!;
    expect(p.melds[0]).toEqual({ type: 'kakan', tiles: ['5m', '5m', '5m', '5m'], fromSeat: 1, claimedTile: '5m' });
    expect(p.drawn).toBe('S');
    expect(game.hand.kongBloom).toBe(true);
  });

  it('ankan then winning on the replacement tile scores 槓上開花', () => {
    const { game, emit } = setup({
      hands: ['9s 9s 9s 9s 123m 456m 789m 234p 5p', '', '', ''],
      front: '1s',
      back: '5p',
      turn: 0,
      drawn: '9s',
    });
    applyAction(game, 0, 'ankan:9s', emit);
    expect(ids(game, 0)).toContain('tsumo');
    applyAction(game, 0, 'tsumo', emit);
    const r = game.hand.result!;
    expect(r.selfDraw).toBe(true);
    expect(r.items.map((i) => i.name)).toContain('槓上開花');
  });
});

describe('flowers', () => {
  it('七搶一: the holder of 7 flowers wins from whoever reveals the 8th', () => {
    const { game, emit } = setup({
      hands: ['1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 2p 3p 4p 5p 6p 7p 8p', '', '', ''],
      flowers: [[], [], ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7'], []],
      front: 'F8 9p',
      turn: 0,
    });
    applyAction(game, 0, 'discard:8p', emit);
    const r = game.hand.result!;
    expect(r.winnerSeat).toBe(2);
    expect(r.loserSeat).toBe(1);
    expect(r.items).toEqual([{ name: '七搶一', tai: 8 }]);
  });

  it('八仙過海: collecting all 8 flowers wins as a self-draw', () => {
    const { game, emit } = setup({
      hands: ['1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 2p 3p 4p 5p 6p 7p 8p', '', '', ''],
      flowers: [[], ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7'], [], []],
      front: 'F8 9p',
      turn: 0,
    });
    applyAction(game, 0, 'discard:8p', emit);
    const r = game.hand.result!;
    expect(r.winnerSeat).toBe(1);
    expect(r.selfDraw).toBe(true);
    expect(r.items).toEqual([{ name: '八仙過海', tai: 8 }]);
  });
});

describe('hand end', () => {
  it('exhaustive draw when only the dead wall remains; dealer keeps the deal', () => {
    const { game, emit, events } = setup({
      hands: ['1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 2p 3p 4p 5p 6p 7p 8p', '', '', ''],
      turn: 0,
      dealer: 0,
    });
    applyAction(game, 0, 'discard:8p', emit);
    expect(game.hand.result?.kind).toBe('exhaustive');
    expect(game.hand.result?.deltas).toEqual([0, 0, 0, 0]);
    expect(game.dealer).toBe(0);
    expect(game.streak).toBe(1);
    expect(events.map((e) => e.type)).toContain('exhaustive');
  });

  it('a full game ends after one round with zero-sum scores and 144 tiles throughout', () => {
    for (const seed of [1, 2, 3, 4, 5]) {
      const game = simulateGame(seed);
      expect(game.over).toBe(true);
      expect(game.roundIndex).toBe(RULES.rounds);
      expect(game.sessionDeltas.reduce((a, b) => a + b, 0)).toBe(0);
    }
  });
});

const WIN_17 = '123m 456m 789m 234p 567s 99s';
const names = (game: GameState) => game.hand.result!.items.map((i) => i.name);

describe('first go-around wins', () => {
  it('天胡: the dealer wins with the opening hand', () => {
    const { game, emit } = setup({ hands: [WIN_17, '', '', ''], turn: 0, dealer: 0, fresh: true, front: '1s' });
    applyAction(game, 0, 'tsumo', emit);
    expect(names(game)).toContain('天胡');
    expect(names(game)).not.toContain('門清自摸');
  });

  it('地胡: a non-dealer self-draws on the first draw', () => {
    const { game, emit } = setup({
      hands: ['1m 1m 1m 2m 2m 2m 3m 3m 3m 4m 4m 4m 5p 5p 5p 7s 8s', '123m 456m 789m 234p 567s 9s', '', ''],
      front: '9s',
      turn: 0,
      dealer: 0,
      fresh: true,
    });
    applyAction(game, 0, 'discard:8s', emit);
    applyAction(game, 1, 'pass', emit); // could chi the 8s; declining keeps the first go-around call-free
    expect(ids(game, 1)).toContain('tsumo');
    applyAction(game, 1, 'tsumo', emit);
    expect(names(game)).toContain('地胡');
  });

  it('人胡: a non-dealer wins on the dealer’s first discard; not after a call', () => {
    const hands = ['5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s 4s 5s 6s E', '', '', '123m 456p 789p 234s 567s 5m'];
    const first = setup({ hands, front: '9m', turn: 0, dealer: 0, fresh: true });
    applyAction(first.game, 0, 'discard:5m', first.emit);
    applyAction(first.game, 3, 'ron', first.emit);
    expect(names(first.game)).toContain('人胡');
    expect(names(first.game)).not.toContain('門清');

    const later = setup({ hands, front: '9m', turn: 0, dealer: 0, fresh: true });
    later.game.hand.noCallsYet = false;
    applyAction(later.game, 0, 'discard:5m', later.emit);
    applyAction(later.game, 3, 'ron', later.emit);
    expect(names(later.game)).not.toContain('人胡');
  });

  it('the dealer cannot score 人胡', () => {
    const { game, emit } = setup({
      hands: ['', '5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s 4s 5s 6s E', '', ''],
      front: '9m',
      turn: 1,
      dealer: 0,
      fresh: true,
    });
    game.hand.players[0]!.hand = sortTiles(tiles('123m 456p 789p 234s 567s 5m'));
    applyAction(game, 1, 'discard:5m', emit);
    applyAction(game, 0, 'ron', emit);
    expect(names(game)).not.toContain('人胡');
  });
});

describe('more kongs and last tiles', () => {
  it('明槓 from a discard draws a replacement from the back', () => {
    const { game, emit } = setup({
      hands: ['5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s 4s 5s 6s E', '', '5m 5m 5m 111s 999s 777p E N', ''],
      front: '9m',
      back: 'S',
      turn: 0,
    });
    applyAction(game, 0, 'discard:5m', emit);
    applyAction(game, 2, 'kan', emit);
    const p = game.hand.players[2]!;
    expect(p.melds[0]).toEqual({ type: 'kan', tiles: ['5m', '5m', '5m', '5m'], fromSeat: 0, claimedTile: '5m' });
    expect(p.drawn).toBe('S');
    expect(game.hand.phase).toEqual({ type: 'turn', seat: 2, justDrew: true });
  });

  it('暗槓 cannot be robbed', () => {
    const { game, emit } = setup({
      hands: ['5m 5m 5m 5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s E', '', '123m 456p 789p 234s 567s 5m', ''],
      front: '9m',
      back: 'S',
      turn: 0,
      drawn: '5m',
    });
    applyAction(game, 0, 'ankan:5m', emit);
    expect(ids(game, 2)).toEqual([]);
    expect(game.hand.phase).toEqual({ type: 'turn', seat: 0, justDrew: true });
  });

  it('海底撈月 on the last drawable tile, 河底撈魚 on the discard after it', () => {
    const draw = setup({
      hands: ['1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 2p 3p 4p 5p 6p 7p 8p', '123m 456m 789m 234p 567s 9s', '', ''],
      front: '9s',
      turn: 0,
    });
    applyAction(draw.game, 0, 'discard:8p', draw.emit);
    applyAction(draw.game, 1, 'tsumo', draw.emit);
    expect(names(draw.game)).toContain('海底撈月');

    const discard = setup({
      hands: ['', '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 2p 3p 4p 5p 6p 7p 9s', '123m 456m 789m 234p 567s 9s', ''],
      turn: 1,
    });
    applyAction(discard.game, 1, 'discard:9s', discard.emit);
    applyAction(discard.game, 2, 'ron', discard.emit);
    expect(names(discard.game)).toContain('河底撈魚');
  });
});

describe('dealer rotation', () => {
  it('dealer win keeps the deal (連莊); a non-dealer win passes it on', () => {
    const hands = ['5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s 4s 5s 6s E', '', '', '123m 456p 789p 234s 567s 5m'];
    const nonDealer = setup({ hands, front: '9m', turn: 0, dealer: 0 });
    applyAction(nonDealer.game, 0, 'discard:5m', nonDealer.emit);
    applyAction(nonDealer.game, 3, 'ron', nonDealer.emit);
    expect(nonDealer.game.dealer).toBe(1);
    expect(nonDealer.game.streak).toBe(0);
    expect(nonDealer.game.dealerRotations).toBe(1);

    const dealer = setup({ hands, front: '9m', turn: 0, dealer: 3 });
    applyAction(dealer.game, 0, 'discard:5m', dealer.emit);
    applyAction(dealer.game, 3, 'ron', dealer.emit);
    expect(dealer.game.dealer).toBe(3);
    expect(dealer.game.streak).toBe(1);
    // Dealer bonus 1 + 0 streak applies because the dealer is involved.
    expect(dealer.game.hand.result!.dealerTai).toBe(1);
  });

  it('the round ends after the deal has passed four times', () => {
    const hands = ['5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s 4s 5s 6s E', '', '', '123m 456p 789p 234s 567s 5m'];
    const { game, emit } = setup({ hands, front: '9m', turn: 0, dealer: 0 });
    game.dealerRotations = 3;
    applyAction(game, 0, 'discard:5m', emit);
    applyAction(game, 3, 'ron', emit);
    expect(game.roundIndex).toBe(1);
    expect(game.over).toBe(true);
    expect(game.hand.result!.gameOver).toBe(true);
  });
});

describe('coin floor (budgets)', () => {
  const hands = ['5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s 4s 5s 6s E', '', '', '123m 456p 789p 234s 567s 5m'];

  it('caps the payment at the remaining coins and ends the game when they reach 0', () => {
    const { game, emit, events } = setup({ hands, front: '9m', turn: 0, dealer: 1 });
    game.budgets[0] = 120;
    applyAction(game, 0, 'discard:5m', emit);
    applyAction(game, 3, 'ron', emit);
    const r = game.hand.result!;
    expect(r.deltas[0]).toBe(-120);
    expect(r.deltas[3]).toBe(120);
    expect(r.deltas.reduce((a, b) => a + b, 0)).toBe(0);
    expect(game.budgets[0]).toBe(0);
    expect(game.over).toBe(true);
    expect(game.endReason).toBe('bankrupt');
    expect(r.gameOver).toBe(true);
    expect(events.at(-1)).toMatchObject({ type: 'game_end', text: '金幣歸零，牌局結束' });
  });

  it('a payment that leaves coins above 0 does not end the game', () => {
    const { game, emit } = setup({ hands, front: '9m', turn: 0, dealer: 1 });
    game.budgets[0] = 5000;
    applyAction(game, 0, 'discard:5m', emit);
    applyAction(game, 3, 'ron', emit);
    expect(game.budgets[0]).toBe(5000 + game.hand.result!.deltas[0]!);
    expect(game.over).toBe(false);
    expect(game.endReason).toBe('');
  });
});

describe('meld display', () => {
  it('chi shows the claimed tile in the middle; the engine keeps tiles sorted for scoring', async () => {
    const { toMeldDto } = await import('../src/game/view.js');
    for (const [claimed, expected] of [
      ['3m', ['4m', '3m', '5m']],
      ['4m', ['3m', '4m', '5m']],
      ['5m', ['3m', '5m', '4m']],
    ] as const) {
      const dto = toMeldDto({ type: 'chi', tiles: ['3m', '4m', '5m'], fromSeat: 3, claimedTile: claimed });
      expect(dto.tiles).toEqual(expected);
      expect(dto.claimedIndex).toBe(1);
      expect(dto.claimedTile).toBe(claimed);
    }
    expect(toMeldDto({ type: 'ankan', tiles: ['E', 'E', 'E', 'E'], fromSeat: 0, claimedTile: '' }).claimedIndex).toBe(-1);
    expect(toMeldDto({ type: 'pon', tiles: ['E', 'E', 'E'], fromSeat: 2, claimedTile: 'E' }).claimedIndex).toBe(0);
  });

  it('a chi claimed on its lowest tile still scores as the right sequence', () => {
    const { game, emit } = setup({
      hands: ['3m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s 4s 5s 6s E', '4m 5m 111p 222p 333s 444s 9s 7s', '', ''],
      front: '9m 9m',
      turn: 0,
    });
    applyAction(game, 0, 'discard:3m', emit);
    applyAction(game, 1, 'chi:3m', emit);
    expect(game.hand.players[1]!.melds[0]).toEqual({ type: 'chi', tiles: ['3m', '4m', '5m'], fromSeat: 0, claimedTile: '3m' });
  });
});

describe('報聽 (ting)', () => {
  // 16 ready tiles plus N: discarding N waits on E (單吊), discarding E waits on N.
  const READY = '123m 456m 789m 123p 456p E N';

  it('offers ting:<tile> only where the discard leaves the hand ready; every discard stays', () => {
    const { game } = setup({ hands: [READY, '', '', ''], front: '9s', turn: 0, drawn: 'N' });
    const options = optionsFor(game, 0);
    const discards = options.filter((o) => o.type === 'discard');
    expect(discards.map((o) => o.tile)).toEqual([...new Set(game.hand.players[0]!.hand)]);
    const ting = options.filter((o) => o.type === 'ting');
    expect(ting.map((o) => o.id).sort()).toEqual(['ting:E', 'ting:N']);
    for (const o of ting) {
      const same = discards.find((d) => d.tile === o.tile)!;
      expect(o.waits.length).toBeGreaterThan(0);
      expect(o.waits).toEqual(same.waits);
      expect(o.tai).toBe(-1);
      expect(o.tiles).toEqual([]);
    }
    expect(ting.find((o) => o.id === 'ting:N')!.label).toBe('聽牌 打 北風（聽 東風）');
    expect(ting.find((o) => o.id === 'ting:N')!.waits).toEqual([{ tile: 'E', left: 3 }]);
  });

  it('offers no ting when no discard makes the hand ready', () => {
    const { game } = setup({ hands: ['1m 3m 5m 7m 9m 1p 3p 5p 7p 9p 1s 3s 5s 7s 9s E N', '', '', ''], front: '9s', turn: 0 });
    expect(ids(game, 0).some((id) => id.startsWith('ting:'))).toBe(false);
    expect(() => applyAction(game, 0, 'ting:E', () => {})).toThrow(IllegalActionError);
  });

  it('declaring marks the seat, announces ting, then plays exactly like the discard', () => {
    const { game, events, emit } = setup({ hands: [READY, '', '', ''], front: '9s 9s', turn: 0, drawn: 'N' });
    applyAction(game, 0, 'ting:N', emit);
    const p = game.hand.players[0]!;
    expect(p.declared).toBe(true);
    expect(events.slice(0, 2)).toEqual([
      { type: 'ting', seat: 0, tile: 'N', tiles: [], text: 'A 聽牌' },
      { type: 'discard', seat: 0, tile: 'N', tiles: [], text: 'A 打出 北風' },
    ]);
    expect(p.discards).toEqual(['N']);
    expect(p.hand).not.toContain('N');
    expect(game.hand.lastDiscard).toEqual({ seat: 0, tile: 'N' });
    expect(game.hand.phase).toEqual({ type: 'turn', seat: 1, justDrew: true });
    expect(game.hand.players.filter((x) => x.declared)).toHaveLength(1);
  });

  it('a declared seat can only let the drawn tile go: no kong, no other discard, no ting', () => {
    // Four 1s (ankan) and a pon of 5m with the fourth 5m in hand (kakan); the drawn E does not win.
    const cfg = {
      hands: ['1s 1s 1s 1s 5m 123p 456p 9p 9p E', '', '', ''],
      melds: [[meld('pon', '5m 5m 5m', 1)]],
      front: '9m',
      turn: 0,
      drawn: 'E',
    };
    const open = setup(cfg);
    expect(ids(open.game, 0)).toEqual(expect.arrayContaining(['ankan:1s', 'kakan:5m', 'discard:1s']));
    const { game, emit } = setup({ ...cfg, declared: [0] });
    expect(ids(game, 0)).toEqual(['discard:E']);
    expect(() => applyAction(game, 0, 'discard:1s', emit)).toThrow(IllegalActionError);
    expect(() => applyAction(game, 0, 'ankan:1s', emit)).toThrow(IllegalActionError);
    applyAction(game, 0, 'discard:E', emit);
    expect(game.hand.players[0]!.discards).toEqual(['E']);
  });

  it('a declared seat that can self-draw chooses between tsumo and letting the tile go (過)', () => {
    const cfg = { hands: ['123m 456m 789m 123p 456p E E', '', '', ''], front: '9s 9s', turn: 0, drawn: 'E', declared: [0] };
    const win = setup(cfg);
    const options = optionsFor(win.game, 0);
    expect(options.map((o) => o.id)).toEqual(['tsumo', 'discard:E']);
    expect(options[0]!.tai).toBeGreaterThanOrEqual(0);
    applyAction(win.game, 0, 'tsumo', win.emit);
    expect(win.game.hand.result?.winnerSeat).toBe(0);
    expect(win.game.hand.result?.totalTai).toBe(options[0]!.tai);

    const skip = setup(cfg);
    applyAction(skip.game, 0, 'discard:E', skip.emit);
    expect(skip.game.hand.result).toBeNull();
    expect(skip.game.hand.players[0]!.declared).toBe(true);
    expect(skip.game.hand.phase).toEqual({ type: 'turn', seat: 1, justDrew: true });
  });

  it('a declared seat gets no chi / pon / kan on a discard, only ron + pass when it wins', () => {
    const { game, emit } = setup({ hands: CLAIM_HANDS, front: '9m 9m', turn: 0, declared: [1, 2, 3] });
    applyAction(game, 0, 'discard:5m', emit);
    expect(ids(game, 1)).toEqual([]);
    expect(ids(game, 2)).toEqual([]);
    expect(ids(game, 3)).toEqual(['ron', 'pass']);
    applyAction(game, 3, 'ron', emit);
    expect(game.hand.result?.winnerSeat).toBe(3);

    const kan = setup({
      hands: ['5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s 4s 5s 6s E', '', '5m 5m 5m 111s 999s 777p E N', ''],
      front: '9m',
      turn: 0,
      declared: [2],
    });
    applyAction(kan.game, 0, 'discard:5m', kan.emit);
    expect(ids(kan.game, 2)).toEqual([]);
    expect(kan.game.hand.phase).toEqual({ type: 'turn', seat: 1, justDrew: true });

    // Declining a win keeps the seat declared and the draw goes on as usual.
    const pass = setup({ hands: CLAIM_HANDS, front: '9m 9m', turn: 0, declared: [1, 2, 3] });
    applyAction(pass.game, 0, 'discard:5m', pass.emit);
    applyAction(pass.game, 3, 'pass', pass.emit);
    expect(pass.game.hand.phase).toEqual({ type: 'turn', seat: 1, justDrew: true });
    expect(pass.game.hand.players[3]!.declared).toBe(true);
  });

  it('a declared seat may still rob a kong (ron + pass)', () => {
    const { game, emit } = setup({
      hands: ['5m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s E', '', '123m 456p 789p 234s 567s 5m', ''],
      melds: [[meld('pon', '5m 5m 5m', 1)]],
      front: '9m',
      turn: 0,
      drawn: '5m',
      declared: [2],
    });
    applyAction(game, 0, 'kakan:5m', emit);
    expect(ids(game, 2)).toEqual(['ron', 'pass']);
    applyAction(game, 2, 'ron', emit);
    expect(game.hand.result?.winnerSeat).toBe(2);
  });

  it('every new hand starts undeclared', () => {
    const { game, emit } = setup({ hands: CLAIM_HANDS, front: '9m 9m', turn: 0, declared: [0, 1, 2, 3] });
    applyAction(game, 0, 'discard:5m', emit);
    applyAction(game, 3, 'ron', emit);
    expect(game.hand.phase.type).toBe('ended');
    nextHand(game, emit);
    expect(game.hand.players.map((p) => p.declared)).toEqual([false, false, false, false]);
  });

  it('the AI never declares', () => {
    for (const personality of ['bear', 'cat', 'rabbit'] as Personality[]) {
      const { game } = setup({ hands: [READY, '', '', ''], front: '9s', turn: 0, drawn: 'N' });
      const options = optionsFor(game, 0);
      expect(options.some((o) => o.type === 'ting')).toBe(true);
      expect(chooseAction(game, 0, options, personality, createRng(1))).toMatch(/^discard:/);
    }
  });

  it('full games where one seat declares whenever it can: 144 tiles, zero-sum, declared seats stay restricted', () => {
    let declarations = 0;
    let declaredWins = 0;
    for (let seed = 101; seed <= 130; seed++) {
      const game = createGame({ id: `ting-${seed}`, names: ['甲', '乙', '丙', '丁'], seed });
      const rng = createRng(seed);
      const emit = (): void => {
        expect(tileCount(game)).toBe(144);
      };
      nextHand(game, emit);
      for (let guard = 0; guard < 100_000; guard++) {
        const hand = game.hand;
        if (hand.phase.type === 'ended') {
          const r = hand.result!;
          expect(r.deltas.reduce((a, b) => a + b, 0)).toBe(0);
          if (r.kind === 'win' && hand.players[r.winnerSeat]!.declared) declaredWins++;
          if (game.over) break;
          nextHand(game, emit);
          continue;
        }
        const seat = pendingSeats(game)[0]!;
        const options = optionsFor(game, seat);
        const p = hand.players[seat]!;
        if (p.declared) {
          expect(options.every((o) => ['tsumo', 'ron', 'pass', 'discard'].includes(o.type))).toBe(true);
          const discards = options.filter((o) => o.type === 'discard');
          expect(discards.length).toBeLessThanOrEqual(1);
          if (discards.length === 1) expect(discards[0]!.tile).toBe(p.drawn);
        }
        const ting = seat === 0 ? options.find((o) => o.type === 'ting') : undefined;
        if (ting) declarations++;
        applyAction(game, seat, ting?.id ?? chooseAction(game, seat, options, 'rabbit', rng), emit);
      }
      expect(game.over).toBe(true);
    }
    expect(declarations).toBeGreaterThan(0);
    expect(declaredWins).toBeGreaterThan(0);
  });
});
