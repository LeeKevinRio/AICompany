// Hand analysis on 34-kind count arrays: completeness, decompositions, waits and shanten.
//
// "setsNeeded" is the number of sets (melds) the concealed part must still form:
// 5 minus the number of exposed/declared melds. A complete concealed hand has 3*setsNeeded + 2 tiles.

import { KIND_COUNT } from './tiles.js';

export type SetType = 'seq' | 'tri';

export interface HandSet {
  type: SetType;
  /** Lowest kind of a sequence, or the kind of a triplet. */
  kind: number;
}

export interface Decomposition {
  pair: number;
  sets: HandSet[];
}

function sum(counts: readonly number[]): number {
  let s = 0;
  for (const c of counts) s += c;
  return s;
}

function canSequenceAt(kind: number): boolean {
  return kind < 27 && kind % 9 <= 6;
}

/** True when every tile can be grouped into sets (no pair). Mutates and restores counts. */
function allSets(counts: number[], start: number): boolean {
  let i = start;
  while (i < KIND_COUNT && counts[i] === 0) i++;
  if (i === KIND_COUNT) return true;
  if (counts[i]! >= 3) {
    counts[i]! -= 3;
    const ok = allSets(counts, i);
    counts[i]! += 3;
    if (ok) return true;
  }
  if (canSequenceAt(i) && counts[i + 1]! > 0 && counts[i + 2]! > 0) {
    counts[i]!--;
    counts[i + 1]!--;
    counts[i + 2]!--;
    const ok = allSets(counts, i);
    counts[i]!++;
    counts[i + 1]!++;
    counts[i + 2]!++;
    if (ok) return true;
  }
  return false;
}

/** Standard winning shape: setsNeeded sets + 1 pair. */
export function isStandardComplete(counts: readonly number[], setsNeeded: number): boolean {
  if (sum(counts) !== setsNeeded * 3 + 2) return false;
  const work = [...counts];
  for (let k = 0; k < KIND_COUNT; k++) {
    if (work[k]! < 2) continue;
    work[k]! -= 2;
    const ok = allSets(work, 0);
    work[k]! += 2;
    if (ok) return true;
  }
  return false;
}

/** 嚦咕嚦咕: a fully concealed 17-tile hand of 7 pairs + 1 triplet. */
export function isLigu(counts: readonly number[]): boolean {
  if (sum(counts) !== 17) return false;
  let triplets = 0;
  for (const c of counts) {
    if (c === 1) return false;
    if (c === 3) triplets++;
  }
  return triplets === 1;
}

export function isComplete(counts: readonly number[], setsNeeded: number): boolean {
  return isStandardComplete(counts, setsNeeded) || (setsNeeded === 5 && isLigu(counts));
}

/** Every distinct standard decomposition (pair + sets). */
export function decompositions(counts: readonly number[], setsNeeded: number): Decomposition[] {
  if (sum(counts) !== setsNeeded * 3 + 2) return [];
  const results: Decomposition[] = [];
  const seen = new Set<string>();
  const work = [...counts];
  const sets: HandSet[] = [];

  const walk = (pair: number, start: number): void => {
    let i = start;
    while (i < KIND_COUNT && work[i] === 0) i++;
    if (i === KIND_COUNT) {
      const key = `${pair}|${sets.map((s) => `${s.type}${s.kind}`).join(',')}`;
      if (!seen.has(key)) {
        seen.add(key);
        results.push({ pair, sets: [...sets] });
      }
      return;
    }
    if (work[i]! >= 3) {
      work[i]! -= 3;
      sets.push({ type: 'tri', kind: i });
      walk(pair, i);
      sets.pop();
      work[i]! += 3;
    }
    if (canSequenceAt(i) && work[i + 1]! > 0 && work[i + 2]! > 0) {
      work[i]!--;
      work[i + 1]!--;
      work[i + 2]!--;
      sets.push({ type: 'seq', kind: i });
      walk(pair, i);
      sets.pop();
      work[i]!++;
      work[i + 1]!++;
      work[i + 2]!++;
    }
  };

  for (let k = 0; k < KIND_COUNT; k++) {
    if (work[k]! < 2) continue;
    work[k]! -= 2;
    walk(k, 0);
    work[k]! += 2;
  }
  return results;
}

/** Kinds that would complete a hand of 3*setsNeeded + 1 tiles. */
export function waitingKinds(counts: readonly number[], setsNeeded: number): number[] {
  const waits: number[] = [];
  const work = [...counts];
  for (let k = 0; k < KIND_COUNT; k++) {
    if (work[k]! >= 4) continue;
    work[k]!++;
    if (isComplete(work, setsNeeded)) waits.push(k);
    work[k]!--;
  }
  return waits;
}

// ---------------------------------------------------------------------------
// Shanten (distance to tenpai). -1 = complete, 0 = tenpai.
// Each of the 4 groups (three suits + honors) is analysed independently into a table
// keyed by (sets, headPair) -> best partial-set count, then the groups are combined.
// ---------------------------------------------------------------------------

type GroupTable = Map<number, number>; // key = sets * 2 + head, value = max partials

const groupCache = new Map<number, GroupTable>();

function analyseGroup(counts: readonly number[], from: number, len: number, honor: boolean): GroupTable {
  let key = honor ? 1 : 0;
  for (let i = 0; i < len; i++) key = key * 5 + counts[from + i]!;
  const cached = groupCache.get(key);
  if (cached) return cached;
  const table: GroupTable = new Map();
  const c = counts.slice(from, from + len);

  const record = (m: number, t: number, p: number): void => {
    const k = m * 2 + p;
    const prev = table.get(k);
    if (prev === undefined || t > prev) table.set(k, t);
  };

  const walk = (start: number, m: number, t: number, p: number): void => {
    let i = start;
    while (i < len && c[i] === 0) i++;
    if (i === len) {
      record(m, t, p);
      return;
    }
    if (c[i]! >= 3) {
      c[i]! -= 3;
      walk(i, m + 1, t, p);
      c[i]! += 3;
    }
    if (!honor && i + 2 < len && c[i + 1]! > 0 && c[i + 2]! > 0) {
      c[i]!--;
      c[i + 1]!--;
      c[i + 2]!--;
      walk(i, m + 1, t, p);
      c[i]!++;
      c[i + 1]!++;
      c[i + 2]!++;
    }
    if (c[i]! >= 2) {
      c[i]! -= 2;
      if (p === 0) walk(i, m, t, 1);
      walk(i, m, t + 1, p);
      c[i]! += 2;
    }
    if (!honor && i + 1 < len && c[i + 1]! > 0) {
      c[i]!--;
      c[i + 1]!--;
      walk(i, m, t + 1, p);
      c[i]!++;
      c[i + 1]!++;
    }
    if (!honor && i + 2 < len && c[i + 2]! > 0) {
      c[i]!--;
      c[i + 2]!--;
      walk(i, m, t + 1, p);
      c[i]!++;
      c[i + 2]!++;
    }
    // Treat one tile at i as isolated.
    c[i]!--;
    walk(i, m, t, p);
    c[i]!++;
  };

  walk(0, 0, 0, 0);
  groupCache.set(key, table);
  return table;
}

export function shanten(counts: readonly number[], setsNeeded: number): number {
  if (setsNeeded === 0) {
    // Only a pair is needed.
    for (const c of counts) if (c >= 2) return -1;
    return 0;
  }
  const groups: GroupTable[] = [
    analyseGroup(counts, 0, 9, false),
    analyseGroup(counts, 9, 9, false),
    analyseGroup(counts, 18, 9, false),
    analyseGroup(counts, 27, 7, true),
  ];
  // Combine: state key = sets * 2 + head -> max partials.
  let states: GroupTable = new Map([[0, 0]]);
  for (const g of groups) {
    const next: GroupTable = new Map();
    for (const [sk, st] of states) {
      const sm = sk >> 1;
      const sp = sk & 1;
      for (const [gk, gt] of g) {
        const gp = gk & 1;
        if (sp + gp > 1) continue;
        const m = Math.min(setsNeeded, sm + (gk >> 1));
        const k = m * 2 + sp + gp;
        const t = st + gt;
        const prev = next.get(k);
        if (prev === undefined || t > prev) next.set(k, t);
      }
    }
    states = next;
  }
  let best = Infinity;
  for (const [k, t] of states) {
    const m = k >> 1;
    const p = k & 1;
    const value = 2 * setsNeeded - 2 * m - Math.min(t, setsNeeded - m) - p;
    if (value < best) best = value;
  }
  return best;
}

export function isHonorOnly(counts: readonly number[]): boolean {
  for (let k = 0; k < 27; k++) if (counts[k]! > 0) return false;
  return true;
}

