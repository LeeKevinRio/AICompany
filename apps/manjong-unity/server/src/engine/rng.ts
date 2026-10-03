import { randomInt } from 'node:crypto';

export interface Rng {
  next(): number; // [0, 1)
  int(maxExclusive: number): number;
}

/**
 * Without a seed the RNG is backed by the OS CSPRNG, so shuffles cannot be predicted from the tiles a
 * player sees. A seed gives a deterministic sfc32 stream for tests and simulations only.
 */
export function createRng(seed?: number): Rng {
  if (seed === undefined) {
    return {
      int: (n) => randomInt(n),
      next: () => randomInt(2 ** 32) / 2 ** 32,
    };
  }
  let s = seed;
  let a = 0x9e3779b9 ^ s;
  let b = 0x243f6a88 ^ (s = Math.imul(s ^ (s >>> 16), 0x85ebca6b));
  let c = 0xb7e15162 ^ (s = Math.imul(s ^ (s >>> 13), 0xc2b2ae35));
  let d = 0x13198a2e ^ (s ^ (s >>> 16));
  const next = (): number => {
    a >>>= 0;
    b >>>= 0;
    c >>>= 0;
    d >>>= 0;
    let t = (a + b) | 0;
    a = b ^ (b >>> 9);
    b = (c + (c << 3)) | 0;
    c = (c << 21) | (c >>> 11);
    d = (d + 1) | 0;
    t = (t + d) | 0;
    c = (c + t) | 0;
    return (t >>> 0) / 4294967296;
  };
  for (let i = 0; i < 15; i++) next();
  return { next, int: (n) => Math.floor(next() * n) };
}

export function shuffle<T>(items: T[], rng: Rng): T[] {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = rng.int(i + 1);
    [arr[i], arr[j]] = [arr[j]!, arr[i]!];
  }
  return arr;
}
