// Session-level 報聽 behaviour: once the human has declared, the server plays the forced discards
// itself (only `step`s) and publishes a `state` only when a win is possible or the hand ends.
import { describe, expect, it, vi } from 'vitest';
import type { GameOption, GameState } from '../src/engine/engine.js';
import { RULES } from '../src/engine/rules.js';
import { sortTiles } from '../src/engine/tiles.js';
import { BusyError, GameSession, type Step } from '../src/game/session.js';
import type { GameViewDto } from '../src/game/view.js';
import { tiles } from './helpers.js';

// Scripted AI: never claims, never wins, always lets its drawn tile go, so the table is fully predictable.
vi.mock('../src/ai/ai.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/ai/ai.js')>();
  return {
    ...actual,
    chooseAction: (game: GameState, seat: number, options: GameOption[]): string => {
      if (options.some((o) => o.type === 'pass')) return 'pass';
      const drawn = game.hand.players[seat]!.drawn;
      return (options.find((o) => o.type === 'discard' && o.tile === drawn) ?? options.find((o) => o.type === 'discard'))!.id;
    },
  };
});

function makeSession(): { session: GameSession; steps: Step[]; states: GameViewDto[]; errors: unknown[] } {
  const steps: Step[] = [];
  const states: GameViewDto[] = [];
  const errors: unknown[] = [];
  const session = new GameSession(
    'g_test',
    'p_test',
    '我',
    {
      onHandEnd: () => {},
      coins: () => 20000,
      onStep: (s) => steps.push(s),
      onState: (v) => states.push(v),
      onError: (e) => errors.push(e),
    },
    { seed: 3, aiDelayMs: 0 },
  );
  return { session, steps, states, errors };
}

/** Puts the session's game into a scripted hand: seat 0 (human) to move, `front` drawn in turn order. */
function script(game: GameState, hands: string[], drawn: string, front: string): void {
  // The session has already dealt a real hand; overwrite the parts the test controls.
  const hand = game.hand;
  hand.players.forEach((p, i) => {
    p.hand = sortTiles(tiles(hands[i]!));
    p.melds = [];
    p.flowers = [];
    p.discards = [];
    p.drawn = i === 0 ? drawn : null;
    p.hasDiscarded = true;
    p.declared = false;
  });
  hand.noCallsYet = false;
  hand.result = null;
  hand.lastDiscard = null;
  hand.wall = [...tiles(front), ...Array.from({ length: RULES.deadWallSize }, () => 'WD')];
  hand.phase = { type: 'turn', seat: 0, justDrew: true };
}

const AI_HAND = '1s 1s 2s 2s 3s 3s 4s 4s 6s 6s 7s 7s 8s 8s RD GD';
const ids = (v: GameViewDto): string[] => v.options.map((o) => o.id);

describe('session: 報聽 auto-play', () => {
  it('auto-discards for a declared human, stops for tsumo / ron, and the next hand resets', async () => {
    const { session, steps, states, errors } = makeSession();
    session.start();
    await session.idle();
    states.length = 0;
    steps.length = 0;

    // Human: ready on E (單吊) after letting N go. The AI seats draw S; the human draws W, W, then E.
    script(session.game, ['123m 456m 789m 123p 456p E N', AI_HAND, AI_HAND, AI_HAND], 'N', 'S S S W S S S W S S S E E');
    expect(ids(session.view())).toContain('ting:N');

    session.act('ting:N');
    // The server is now playing for everyone; the human cannot act until it stops.
    expect(session.isBusy).toBe(true);
    expect(() => session.act('discard:W')).toThrow(BusyError);
    await session.idle();

    // Exactly one state: the self-draw decision (win, or let the tile go).
    expect(states).toHaveLength(1);
    const tsumo = states[0]!;
    expect(ids(tsumo)).toEqual(['tsumo', 'discard:E']);
    expect(tsumo.players[0]!.declared).toBe(true);
    expect(tsumo.players.slice(1).map((p) => p.declared)).toEqual([false, false, false]);
    expect(tsumo.players[0]!.drawnTile).toBe('E');

    const events = steps.map((s) => s.event);
    expect(events[0]).toEqual({ type: 'ting', seat: 0, tile: 'N', tiles: [], text: '我 聽牌' });
    expect(events[1]).toMatchObject({ type: 'discard', seat: 0, tile: 'N' });
    // The two W draws were let go by the server, with nothing but steps in between.
    const mine = events.filter((e) => e.seat === 0).map((e) => `${e.type}:${e.tile}`);
    expect(mine).toEqual(['ting:N', 'discard:N', 'draw:W', 'discard:W', 'draw:W', 'discard:W', 'draw:E']);
    for (const s of steps) expect(s.view.options).toEqual([]);
    expect(steps.at(-1)!.view.players[0]!.declared).toBe(true);

    // 過: let the winning tile go; the server keeps playing until seat 1 discards E (ron offer).
    steps.length = 0;
    session.act('discard:E');
    await session.idle();
    expect(states).toHaveLength(2);
    const ron = states[1]!;
    expect(ids(ron)).toEqual(['ron', 'pass']);
    expect(ron.lastDiscardTile).toBe('E');
    expect(ron.lastDiscardSeat).toBe(1);

    session.act('ron');
    await session.idle();
    expect(states).toHaveLength(3);
    const end = states[2]!;
    expect(end.phase).toBe('hand_end');
    expect(end.result.winnerSeat).toBe(0);
    expect(ids(end)).toEqual(['next']);

    session.act('next');
    await session.idle();
    expect(states).toHaveLength(4);
    expect(states[3]!.players.map((p) => p.declared)).toEqual([false, false, false, false]);
    expect(states[3]!.options.length).toBeGreaterThan(0);
    expect(errors).toEqual([]);
  });

  it('an undeclared human is never auto-played', async () => {
    const { session, steps, states } = makeSession();
    session.start();
    await session.idle();
    states.length = 0;
    steps.length = 0;
    script(session.game, ['123m 456m 789m 123p 456p E N', AI_HAND, AI_HAND, AI_HAND], 'N', 'S S S W S S S W');
    session.act('discard:N');
    await session.idle();
    expect(states).toHaveLength(1);
    expect(states[0]!.players[0]!.declared).toBe(false);
    expect(states[0]!.players[0]!.drawnTile).toBe('W');
    expect(ids(states[0]!)).toEqual(expect.arrayContaining(['discard:W', 'ting:W', 'ting:E']));
    expect(steps.some((s) => s.event.type === 'ting')).toBe(false);
  });
});
