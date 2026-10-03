import { describe, expect, it } from 'vitest';
import { createRng } from '../src/engine/rng.js';
import { IllegalActionError } from '../src/engine/engine.js';
import { BusyError, GameSession } from '../src/game/session.js';

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
  it('rejects actions while the AI is playing and accepts them once it stops', async () => {
    const states: number[] = [];
    let steps = 0;
    const session = new GameSession(
      'g_0000000000000000',
      'p',
      '你',
      {
        onHandEnd() {},
        coins: () => 0,
        onStep: () => {
          steps++;
        },
        onState: (v) => states.push(v.options.length),
        onError: (e) => {
          throw e;
        },
      },
      { seed: 3 },
    );
    session.start();
    expect(session.isBusy).toBe(true);
    expect(() => session.act('pass')).toThrow(BusyError);
    await session.idle();
    expect(steps).toBeGreaterThan(0);
    expect(states).toHaveLength(1);
    expect(() => session.act('discard:XX')).toThrow(IllegalActionError);
    session.act(session.view().options[0]!.id);
    await session.idle();
    expect(states).toHaveLength(2);
  });
});
