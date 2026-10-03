// "Can play" AI: tile-efficiency play (shanten + effective tiles) using only public information.
// Personalities differ only in how eagerly they claim discards. No defence yet.

import { seatWind, roundWind, type GameOption, type GameState } from '../engine/engine.js';
import { shanten } from '../engine/hand.js';
import type { Rng } from '../engine/rng.js';
import { KIND_COUNT, isDragonKind, kindOf, toCounts, windKind, type Tile } from '../engine/tiles.js';

export type Personality = 'bear' | 'cat' | 'rabbit';

export interface AiProfile {
  name: string;
  avatar: Personality;
}

export const AI_PROFILES: AiProfile[] = [
  { name: '熊熊', avatar: 'bear' },
  { name: '喵喵', avatar: 'cat' },
  { name: '兔兔', avatar: 'rabbit' },
];

/** Tiles this seat can see: own hand plus every discard, meld and nothing else. */
function visibleCounts(game: GameState, seat: number): number[] {
  const seen = toCounts(game.hand.players[seat]!.hand);
  for (const p of game.hand.players) {
    for (const t of p.discards) seen[kindOf(t)]!++;
    for (const m of p.melds) for (const t of m.tiles) seen[kindOf(t)]!++;
  }
  // The hand is counted once above; melds of this seat are already out of its hand.
  return seen;
}

/** A drawn tile can only help if it connects to a tile already held (same honor, or suit distance <= 2). */
function isConnected(counts: number[], k: number): boolean {
  if (k >= 27) return counts[k]! > 0;
  const base = k - (k % 9);
  for (let d = -2; d <= 2; d++) {
    const j = k + d;
    if (j >= base && j < base + 9 && counts[j]! > 0) return true;
  }
  return false;
}

function effectiveTiles(counts: number[], sets: number, current: number, seen: number[]): number {
  let total = 0;
  for (let k = 0; k < KIND_COUNT; k++) {
    const left = 4 - seen[k]!;
    if (left <= 0 || !isConnected(counts, k)) continue;
    counts[k]!++;
    if (shanten(counts, sets) < current) total += left;
    counts[k]!--;
  }
  return total;
}

interface DiscardChoice {
  tile: Tile;
  shanten: number;
  effective: number;
}

function bestDiscard(hand: Tile[], sets: number, seen: number[], rng: Rng): DiscardChoice {
  const counts = toCounts(hand);
  let best: DiscardChoice | null = null;
  let ties = 0;
  for (const tile of new Set(hand)) {
    const k = kindOf(tile);
    counts[k]!--;
    const s = shanten(counts, sets);
    const e = effectiveTiles(counts, sets, s, seen);
    counts[k]!++;
    const better = !best || s < best.shanten || (s === best.shanten && e > best.effective);
    const equal = best && s === best.shanten && e === best.effective;
    if (better) {
      best = { tile, shanten: s, effective: e };
      ties = 1;
    } else if (equal) {
      // Reservoir-sample among equally good discards for a little variety.
      ties++;
      if (rng.int(ties) === 0) best = { tile, shanten: s, effective: e };
    }
  }
  if (!best) throw new Error('No tile to discard');
  return best;
}

/** Lowest shanten reachable by discarding one tile (no effective-tile tie-break). */
function minShantenAfterDiscard(hand: Tile[], sets: number): number {
  const counts = toCounts(hand);
  let best = Infinity;
  for (let k = 0; k < KIND_COUNT; k++) {
    if (counts[k] === 0) continue;
    counts[k]!--;
    best = Math.min(best, shanten(counts, sets));
    counts[k]!++;
  }
  return best;
}

function without(hand: Tile[], tiles: Tile[]): Tile[] {
  const rest = [...hand];
  for (const t of tiles) {
    const i = rest.indexOf(t);
    if (i >= 0) rest.splice(i, 1);
  }
  return rest;
}

function isValueHonor(game: GameState, seat: number, tile: Tile): boolean {
  const k = kindOf(tile);
  return isDragonKind(k) || k === windKind(seatWind(game, seat)) || k === windKind(roundWind(game));
}

export function chooseAction(
  game: GameState,
  seat: number,
  options: GameOption[],
  personality: Personality,
  rng: Rng,
): string {
  const byType = (t: GameOption['type']): GameOption[] => options.filter((o) => o.type === t);
  if (byType('tsumo').length) return 'tsumo';
  if (byType('ron').length) return 'ron';

  const p = game.hand.players[seat]!;
  const sets = 5 - p.melds.length;
  const seen = visibleCounts(game, seat);

  if (byType('discard').length) {
    const discard = bestDiscard(p.hand, sets, seen, rng);
    for (const o of byType('ankan')) {
      const after = without(p.hand, [o.tile, o.tile, o.tile, o.tile]);
      if (shanten(toCounts(after), sets - 1) <= discard.shanten) return o.id;
    }
    for (const o of byType('kakan')) {
      const after = without(p.hand, [o.tile]);
      if (shanten(toCounts(after), sets) <= discard.shanten) return o.id;
    }
    return `discard:${discard.tile}`;
  }

  // Claim window: compare the hand's shanten now against the best line after claiming.
  const current = shanten(toCounts(p.hand), sets);
  let choice: { id: string; shanten: number; priority: number } | null = null;
  for (const o of options) {
    let used: Tile[];
    let priority: number;
    if (o.type === 'pon') {
      used = [o.tile, o.tile];
      priority = 2;
    } else if (o.type === 'chi') {
      used = without(o.tiles, [o.tile]);
      priority = 1;
    } else if (o.type === 'kan') {
      used = [o.tile, o.tile, o.tile];
      priority = 3;
    } else {
      continue;
    }
    const after = without(p.hand, used);
    const s = o.type === 'kan' ? shanten(toCounts(after), sets - 1) : minShantenAfterDiscard(after, sets - 1);
    const opened = p.melds.some((m) => m.type !== 'ankan');
    let want: boolean;
    switch (personality) {
      case 'bear':
        want = s <= current;
        break;
      case 'rabbit':
        want = o.type === 'kan' ? s <= current : s < current;
        break;
      case 'cat':
        want =
          o.type === 'kan'
            ? opened && s <= current
            : (s === 0 && s < current) || (o.type === 'pon' && isValueHonor(game, seat, o.tile) && s <= current);
        break;
    }
    if (!want) continue;
    if (!choice || s < choice.shanten || (s === choice.shanten && priority > choice.priority)) {
      choice = { id: o.id, shanten: s, priority };
    }
  }
  return choice ? choice.id : 'pass';
}
