// All-AI games for invariant testing and balance checks (no human seat).

import { chooseAction, type Personality } from '../ai/ai.js';
import { applyAction, createGame, nextHand, optionsFor, pendingSeats, tileCount, type GameState } from '../engine/engine.js';
import { createRng } from '../engine/rng.js';
import type { HandResult } from '../engine/types.js';

export interface SimulationStats {
  hands: number;
  wins: number;
  selfDraws: number;
  exhaustive: number;
  taiHistogram: Record<number, number>;
  itemCounts: Record<string, number>;
  /** Wins per seat (seat personalities: PERSONALITIES). */
  seatWins: number[];
  /** Hands in which each seat had declared ready (報聽) by the end of the hand. */
  seatDeclared: number[];
  /** Wins by a seat that had declared. */
  declaredWins: number;
}

const PERSONALITIES: Personality[] = ['rabbit', 'bear', 'cat', 'rabbit'];

export function simulateGame(seed: number, onHand?: (result: HandResult, game: GameState) => void): GameState {
  const rng = createRng(seed ^ 0x2545f491);
  const check = (game: GameState): void => {
    const n = tileCount(game);
    if (n !== 144) throw new Error(`Tile count ${n} != 144 (seed ${seed}, hand ${game.handNo})`);
  };
  let game: GameState | null = null;
  const emit = (): void => {
    if (game) check(game);
  };
  game = createGame({ id: `sim-${seed}`, names: ['甲', '乙', '丙', '丁'], seed });
  nextHand(game, emit);
  for (let guard = 0; guard < 100_000; guard++) {
    check(game);
    if (game.hand.phase.type === 'ended') {
      onHand?.(game.hand.result!, game);
      if (game.over) return game;
      nextHand(game, emit);
      continue;
    }
    const seat = pendingSeats(game)[0];
    if (seat === undefined) throw new Error(`No pending seat (seed ${seed})`);
    const action = chooseAction(game, seat, optionsFor(game, seat), PERSONALITIES[seat]!, rng);
    applyAction(game, seat, action, emit);
  }
  throw new Error(`Game did not finish (seed ${seed})`);
}

export function simulate(games: number, firstSeed = 1): SimulationStats {
  const stats: SimulationStats = {
    hands: 0,
    wins: 0,
    selfDraws: 0,
    exhaustive: 0,
    taiHistogram: {},
    itemCounts: {},
    seatWins: [0, 0, 0, 0],
    seatDeclared: [0, 0, 0, 0],
    declaredWins: 0,
  };
  for (let i = 0; i < games; i++) {
    simulateGame(firstSeed + i, (r, game) => {
      stats.hands++;
      const sum = r.deltas.reduce((a, b) => a + b, 0);
      if (sum !== 0) throw new Error(`Non-zero-sum settlement (seed ${firstSeed + i})`);
      game.hand.players.forEach((p, seat) => {
        if (p.declared) stats.seatDeclared[seat]!++;
      });
      if (r.kind === 'exhaustive') {
        stats.exhaustive++;
        return;
      }
      stats.wins++;
      stats.seatWins[r.winnerSeat]!++;
      if (game.hand.players[r.winnerSeat]!.declared) stats.declaredWins++;
      if (r.selfDraw) stats.selfDraws++;
      stats.taiHistogram[r.totalTai] = (stats.taiHistogram[r.totalTai] ?? 0) + 1;
      for (const it of r.items) {
        const name = it.name.replace(/ ×\d+$/, '');
        stats.itemCounts[name] = (stats.itemCounts[name] ?? 0) + 1;
      }
    });
  }
  return stats;
}
