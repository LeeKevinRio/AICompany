import { describe, expect, it } from 'vitest';
import { createRng } from '../src/engine/rng.js';
import { GameSession } from '../src/game/session.js';

describe('rng', () => {
  it('unseeded RNG (production) stays in range', () => {
    const rng = createRng();
    for (let i = 0; i < 1000; i++) {
      const n = rng.int(4);
      expect(n).toBeGreaterThanOrEqual(0);
      expect(n).toBeLessThan(4);
      const x = rng.next();
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThan(1);
    }
  });

  it('seeded RNG is deterministic', () => {
    const a = createRng(42);
    const b = createRng(42);
    expect(Array.from({ length: 10 }, () => a.int(1000))).toEqual(Array.from({ length: 10 }, () => b.int(1000)));
  });
});

describe('session', () => {
  it('a rejected action does not leak buffered steps into the next response', () => {
    const session = new GameSession('g_0000000000000000', 'p', '你', { onHandEnd() {}, coins: () => 0 }, 3);
    session.start();
    expect(() => session.act('discard:XX')).toThrow();
    const view = session.view();
    const legal = view.options[0]!;
    const res = session.act(legal.id);
    for (const step of res.steps) expect(step.event.type).not.toBe('hand_start');
  });
});
