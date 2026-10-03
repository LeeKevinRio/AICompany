import type { Meld } from '../src/engine/types.js';

/**
 * Compact tile notation: "123m 456p 9s E E RD".
 * Digit runs followed by a suit letter expand to suited tiles; other tokens are taken as-is.
 */
export function tiles(notation: string): string[] {
  const out: string[] = [];
  for (const token of notation.trim().split(/\s+/)) {
    if (!token) continue;
    const m = /^(\d+)([mps])$/.exec(token);
    if (m) for (const d of m[1]!) out.push(`${d}${m[2]}`);
    else out.push(token);
  }
  return out;
}

export function meld(type: Meld['type'], notation: string, fromSeat = 1): Meld {
  return { type, tiles: tiles(notation), fromSeat };
}

export function names(items: { name: string }[]): string[] {
  return items.map((i) => i.name);
}
