import { describe, expect, it } from 'vitest';
import { decompositions, isComplete, isLigu, shanten, waitingKinds } from '../src/engine/hand.js';
import { codeOf, toCounts } from '../src/engine/tiles.js';
import { tiles } from './helpers.js';

const counts = (s: string) => toCounts(tiles(s));

describe('hand analysis', () => {
  it('detects a complete 17-tile hand', () => {
    expect(isComplete(counts('123m 456m 789m 234p 567s 99s'), 5)).toBe(true);
    expect(isComplete(counts('123m 456m 789m 234p 567s 98s'), 5)).toBe(false);
  });

  it('handles exposed melds by reducing the sets needed', () => {
    expect(isComplete(counts('123m 456p 99s'), 2)).toBe(true);
    expect(isComplete(counts('N N'), 0)).toBe(true);
  });

  it('recognises 嚦咕嚦咕 (7 pairs + 1 triplet) only with exactly one triplet', () => {
    expect(isLigu(counts('11m 22m 33m 55p 66p 77s 88s E E E'))).toBe(true);
    expect(isLigu(counts('1111m 33m 55p 66p 77s 88s E E E'))).toBe(true); // four of a kind = 2 pairs
    expect(isLigu(counts('111m 333m 55p 66p 77s 88s E E'))).toBe(false); // two triplets
    expect(isComplete(counts('11m 22m 33m 55p 66p 77s 88s E E E'), 5)).toBe(true);
  });

  it('lists waits', () => {
    const w = waitingKinds(counts('123m 456m 234s 567s 88s 23p'), 5).map(codeOf);
    expect(w.sort()).toEqual(['1p', '4p']);
    const single = waitingKinds(counts('123m 456m 234s 567s 88s 24p'), 5).map(codeOf);
    expect(single).toEqual(['3p']);
  });

  it('enumerates all decompositions', () => {
    const ds = decompositions(counts('111m 222m 333m 456p 789s 55s'), 5);
    const shapes = ds.map((d) => d.sets.filter((s) => s.type === 'tri').length).sort();
    expect(shapes).toEqual([0, 3]);
  });

  it('shanten caches for honors and suits do not collide', () => {
    // Honors E S W and suit 2345 share the same base-5 key; analysing honors first used to poison the suit.
    expect(shanten(counts('E S W 1p 9p 1s 9s'), 5)).toBe(10);
    expect(shanten(counts('2m 3m 4m 5m 1p 9p 1s 9s'), 5)).toBe(8);
  });

  it('computes shanten', () => {
    expect(shanten(counts('123m 456m 789m 234p 567s 99s'), 5)).toBe(-1);
    expect(shanten(counts('123m 456m 234s 567s 88s 23p'), 5)).toBe(0);
    expect(shanten(counts('123m 456m 234s 567s 88s 2p 9p'), 5)).toBe(1);
    expect(shanten(counts('1m 4m 7m 1p 4p 7p 1s 4s 7s E S W N RD GD WD'), 5)).toBeGreaterThanOrEqual(8);
  });
});
