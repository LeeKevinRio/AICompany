// Tai (台) calculation and settlement. Spec: work/manjong-unity/規則與台數表.md

import { decompositions, isLigu, waitingKinds, type HandSet } from './hand.js';
import { ECONOMY, RULES, TAI, type TaiKey } from './rules.js';
import {
  FLOWERS,
  WINDS,
  flowerNumber,
  isDragonKind,
  isWindKind,
  kindOf,
  suitOfKind,
  toCounts,
  windKind,
  type Tile,
  type Wind,
} from './tiles.js';
import type { Meld, TaiItem } from './types.js';

export interface WinInput {
  /** Concealed tiles including the winning tile. */
  concealed: Tile[];
  melds: Meld[];
  flowers: Tile[];
  winTile: Tile;
  selfDraw: boolean;
  seatWind: Wind;
  roundWind: Wind;
  robKong?: boolean;
  kongBloom?: boolean;
  /** Won on the last drawable tile (self-draw) or the discard after it. */
  lastTile?: boolean;
  heaven?: boolean;
  earth?: boolean;
  human?: boolean;
}

export interface ScoreResult {
  items: TaiItem[];
  total: number;
}

interface FullSet {
  type: 'seq' | 'tri';
  kind: number;
  concealed: boolean;
}

/** Where the winning tile sits in a decomposition. */
type WinSlot = { group: 'pair' } | { group: 'set'; index: number };

function item(key: TaiKey, times = 1): TaiItem {
  const def = TAI[key];
  return { name: times > 1 ? `${def.name} ×${times}` : def.name, tai: def.tai * times };
}

function meldToSet(m: Meld): FullSet {
  const kind = kindOf(m.tiles[0]!);
  return { type: m.type === 'chi' ? 'seq' : 'tri', kind, concealed: m.type === 'ankan' };
}

function flowerItems(flowers: Tile[], seatWind: Wind): TaiItem[] {
  const items: TaiItem[] = [];
  const have = new Set(flowers);
  const seatIdx = WINDS.indexOf(seatWind);
  const seasonsDone = FLOWERS.slice(0, 4).every((f) => have.has(f));
  const plantsDone = FLOWERS.slice(4).every((f) => have.has(f));
  if (seasonsDone) items.push(item('flowerSetSeasons'));
  if (plantsDone) items.push(item('flowerSetPlants'));
  let seatFlowers = 0;
  for (const f of flowers) {
    const n = flowerNumber(f);
    const isSeason = n <= 4;
    if ((n - 1) % 4 !== seatIdx) continue;
    if ((isSeason && seasonsDone) || (!isSeason && plantsDone)) continue;
    seatFlowers++;
  }
  if (seatFlowers > 0) items.push(item('seatFlower', seatFlowers));
  return items;
}

/** Items that do not depend on how the hand is decomposed. */
function situationalItems(input: WinInput): TaiItem[] {
  const items: TaiItem[] = [];
  if (input.heaven) items.push(item('heavenWin'));
  if (input.earth) items.push(item('earthWin'));
  if (input.human) items.push(item('humanWin'));
  if (input.robKong) items.push(item('robKong'));
  if (input.kongBloom && input.selfDraw) items.push(item('kongBloom'));
  if (input.lastTile) items.push(item(input.selfDraw ? 'lastTileDraw' : 'lastTileDiscard'));
  items.push(...flowerItems(input.flowers, input.seatWind));
  return items;
}

function colorItems(allKinds: number[]): TaiItem[] {
  const suits = new Set<number>();
  let honors = false;
  for (const k of allKinds) {
    const s = suitOfKind(k);
    if (s === 3) honors = true;
    else suits.add(s);
  }
  if (suits.size === 0) return [item('allHonors')];
  if (suits.size === 1) return [item(honors ? 'halfFlush' : 'fullFlush')];
  return [];
}

function selfDrawItems(input: WinInput, closed: boolean, allowMenqing: boolean): TaiItem[] {
  if (input.heaven || input.earth) return [];
  if (input.selfDraw) return [item(closed && allowMenqing ? 'menqingZimo' : 'zimo')];
  if (closed && allowMenqing && !input.human) return [item('menqing')];
  return [];
}

function evaluateStandard(
  input: WinInput,
  pair: number,
  handSets: HandSet[],
  slot: WinSlot,
  waits: number[],
): TaiItem[] {
  const winKind = kindOf(input.winTile);
  const sets: FullSet[] = handSets.map((s, i) => ({
    type: s.type,
    kind: s.kind,
    // A triplet completed by someone else's discard is exposed, not concealed.
    concealed: !(slot.group === 'set' && slot.index === i && s.type === 'tri' && !input.selfDraw),
  }));
  sets.push(...input.melds.map(meldToSet));

  const closed = input.melds.every((m) => m.type === 'ankan');
  const items: TaiItem[] = [];

  const triplets = sets.filter((s) => s.type === 'tri');
  const dragonTriplets = triplets.filter((s) => isDragonKind(s.kind));
  const windTriplets = triplets.filter((s) => isWindKind(s.kind));

  // Dragons
  if (dragonTriplets.length === 3) items.push(item('bigDragons'));
  else if (dragonTriplets.length === 2 && isDragonKind(pair)) items.push(item('littleDragons'));
  else {
    for (const t of dragonTriplets) {
      items.push(item(t.kind === 31 ? 'dragonRed' : t.kind === 32 ? 'dragonGreen' : 'dragonWhite'));
    }
  }

  // Winds
  if (windTriplets.length === 4) items.push(item('bigWinds'));
  else if (windTriplets.length === 3 && isWindKind(pair)) items.push(item('littleWinds'));
  else {
    if (windTriplets.some((t) => t.kind === windKind(input.roundWind))) items.push(item('roundWind'));
    if (windTriplets.some((t) => t.kind === windKind(input.seatWind))) items.push(item('seatWind'));
  }

  // Concealed triplets
  const concealedTriplets = triplets.filter((s) => s.concealed).length;
  if (concealedTriplets >= 5) items.push(item('fiveConcealed'));
  else if (concealedTriplets === 4) items.push(item('fourConcealed'));
  else if (concealedTriplets === 3) items.push(item('threeConcealed'));

  if (triplets.length === sets.length) items.push(item('allTriplets'));

  const allKinds = [pair, ...sets.map((s) => s.kind)];
  items.push(...colorItems(allKinds));

  // Melded-ness and waits
  const allMelded =
    input.melds.length === 5 && input.melds.every((m) => m.type !== 'ankan') && !input.selfDraw;
  const pinghu = isPinghu(input, sets, slot, handSets, waits, winKind);
  if (allMelded) items.push(item('allMelded'));
  if (pinghu) items.push(item('pinghu'));
  if (!allMelded && !pinghu && waits.length === 1) items.push(item('singleWait'));

  items.push(...selfDrawItems(input, closed, true));
  return items;
}

function isPinghu(
  input: WinInput,
  sets: FullSet[],
  slot: WinSlot,
  handSets: HandSet[],
  waits: number[],
  winKind: number,
): boolean {
  if (input.selfDraw || input.flowers.length > 0 || waits.length < 2) return false;
  if (!sets.every((s) => s.type === 'seq')) return false;
  if (slot.group !== 'set') return false;
  const allKinds = [...input.concealed.map(kindOf), ...input.melds.flatMap((m) => m.tiles.map(kindOf))];
  if (allKinds.some((k) => k >= 27)) return false;
  const seq = handSets[slot.index]!;
  const low = seq.kind;
  // Two-sided wait: the winning tile is an end of the run and the other side exists.
  if (winKind === low) return low % 9 < 6;
  if (winKind === low + 2) return low % 9 > 0;
  return false;
}

function evaluateLigu(input: WinInput): TaiItem[] {
  const items: TaiItem[] = [item('ligu')];
  items.push(...colorItems(input.concealed.map(kindOf)));
  items.push(...selfDrawItems(input, true, false));
  return items;
}

function total(items: TaiItem[]): number {
  return items.reduce((s, i) => s + i.tai, 0);
}

/** Best-scoring interpretation of a winning hand, or null if the hand is not complete. */
export function scoreWin(input: WinInput): ScoreResult | null {
  const counts = toCounts(input.concealed);
  const setsNeeded = 5 - input.melds.length;
  const winKind = kindOf(input.winTile);
  if (counts[winKind]! < 1) throw new Error('Winning tile must be part of the concealed tiles');

  const before = [...counts];
  before[winKind]!--;
  const waits = waitingKinds(before, setsNeeded);
  const situational = situationalItems(input);

  let best: TaiItem[] | null = null;
  const consider = (items: TaiItem[]): void => {
    const all = [...items, ...situational];
    if (best === null || total(all) > total(best)) best = all;
  };

  for (const d of decompositions(counts, setsNeeded)) {
    const slots: WinSlot[] = [];
    if (d.pair === winKind) slots.push({ group: 'pair' });
    d.sets.forEach((s, index) => {
      const contains = s.type === 'tri' ? s.kind === winKind : winKind >= s.kind && winKind <= s.kind + 2;
      if (contains) slots.push({ group: 'set', index });
    });
    for (const slot of slots) consider(evaluateStandard(input, d.pair, d.sets, slot, waits));
  }
  if (input.melds.length === 0 && isLigu(counts)) consider(evaluateLigu(input));

  if (best === null) return null;
  return { items: best, total: total(best) };
}

/** 八仙過海 / 七搶一: flower wins ignore the hand entirely. */
export function scoreFlowerWin(kind: 'eightFlowers' | 'sevenRobOne'): ScoreResult {
  const items = [item(kind)];
  return { items, total: total(items) };
}

export function dealerBonusTai(streak: number): number {
  return RULES.dealerBaseTai + RULES.dealerTaiPerStreak * streak;
}

/**
 * Zero-sum settlement. Each payer pays base + tai * perTai; the dealer bonus is added only to
 * payments where the dealer is the winner or the payer.
 */
export function settle(params: {
  winner: number;
  payers: number[];
  tai: number;
  dealer: number;
  streak: number;
}): number[] {
  const deltas = [0, 0, 0, 0];
  const bonus = dealerBonusTai(params.streak);
  for (const payer of params.payers) {
    const involvesDealer = payer === params.dealer || params.winner === params.dealer;
    const tai = params.tai + (involvesDealer ? bonus : 0);
    const amount = ECONOMY.base + tai * ECONOMY.perTai;
    deltas[payer]! -= amount;
    deltas[params.winner]! += amount;
  }
  return deltas;
}
