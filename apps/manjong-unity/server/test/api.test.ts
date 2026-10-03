import type { FastifyInstance } from 'fastify';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/api/app.js';
import type { ActionResponse } from '../src/game/session.js';
import type { GameViewDto } from '../src/game/view.js';
import { JsonPlayerRepository } from '../src/store/players.js';

let app: FastifyInstance;

beforeEach(async () => {
  ({ app } = await buildApp({ repo: new JsonPlayerRepository(null), corsOrigin: true }));
});

afterEach(async () => {
  await app.close();
});

async function guest(): Promise<{ token: string; auth: Record<string, string> }> {
  const res = await app.inject({ method: 'POST', url: '/api/auth/guest', payload: {} });
  expect(res.statusCode).toBe(200);
  const token = res.json().token as string;
  return { token, auth: { authorization: `Bearer ${token}` } };
}

function assertNoLeaks(view: GameViewDto): void {
  // Hands are revealed only once the hand has a result.
  if (view.hasResult) return;
  expect(view.phase).toBe('playing');
  for (const p of view.players) {
    if (p.seat === view.mySeat) continue;
    expect(p.hand).toEqual([]);
    expect(p.drawnTile).toBe('');
  }
}

/** Plays the whole game choosing simple legal actions; returns the final view. */
async function playToEnd(auth: Record<string, string>, first: ActionResponse): Promise<GameViewDto> {
  let res = first;
  for (let i = 0; i < 5000; i++) {
    for (const step of res.steps) {
      assertNoLeaks(step.view);
      if (step.event.type === 'draw' && step.event.seat !== step.view.mySeat) expect(step.event.tile).toBe('');
    }
    const view = res.view;
    assertNoLeaks(view);
    if (view.phase === 'game_end') return view;
    const pick =
      view.options.find((o) => ['tsumo', 'ron', 'next'].includes(o.type)) ??
      view.options.find((o) => o.type === 'pass') ??
      view.options.find((o) => o.type === 'discard' && o.tile === view.players[view.mySeat]!.drawnTile) ??
      view.options[view.options.length - 1];
    expect(pick, 'the human must always have something to do while the game is running').toBeDefined();
    const r = await app.inject({
      method: 'POST',
      url: `/api/games/${view.gameId}/actions`,
      headers: auth,
      payload: { actionId: pick!.id },
    });
    expect(r.statusCode).toBe(200);
    res = r.json();
  }
  throw new Error('game did not finish');
}

describe('accounts', () => {
  it('creates a guest with starting coins and authenticates by token', async () => {
    const { auth } = await guest();
    const me = await app.inject({ method: 'GET', url: '/api/me', headers: auth });
    expect(me.statusCode).toBe(200);
    expect(me.json().player.coins).toBe(20000);
    expect(me.json().player.nickname).toMatch(/^訪客\d{4}$/);
  });

  it('rejects missing or unknown tokens', async () => {
    expect((await app.inject({ method: 'GET', url: '/api/me' })).statusCode).toBe(401);
    const bad = await app.inject({ method: 'GET', url: '/api/me', headers: { authorization: 'Bearer xxxxxxxxxxxxxxxxxxxxxxxx' } });
    expect(bad.statusCode).toBe(401);
    expect(bad.json().error.code).toBe('UNAUTHORIZED');
  });

  it('validates nicknames', async () => {
    const { auth } = await guest();
    const ok = await app.inject({ method: 'POST', url: '/api/me/nickname', headers: auth, payload: { nickname: '  小明  ' } });
    expect(ok.json().player.nickname).toBe('小明');
    for (const nickname of ['', '   ', '一二三四五六七八九十一二三', 'a\u0000b']) {
      const r = await app.inject({ method: 'POST', url: '/api/me/nickname', headers: auth, payload: { nickname } });
      expect(r.statusCode).toBe(400);
      expect(r.json().error.code).toBe('INVALID_NICKNAME');
    }
  });

  it('only grants relief below the threshold', async () => {
    const { auth } = await guest();
    const r = await app.inject({ method: 'POST', url: '/api/me/relief', headers: auth, payload: {} });
    expect(r.statusCode).toBe(400);
    expect(r.json().error.code).toBe('RELIEF_NOT_ELIGIBLE');
  });

  it('lists the leaderboard by coins and marks the caller', async () => {
    const a = await guest();
    await guest();
    const r = await app.inject({ method: 'GET', url: '/api/leaderboard', headers: a.auth });
    const entries = r.json().entries as { rank: number; isMe: boolean }[];
    expect(entries).toHaveLength(2);
    expect(entries.filter((e) => e.isMe)).toHaveLength(1);
    expect(entries.map((e) => e.rank)).toEqual([1, 2]);
  });
});

describe('games', () => {
  it('plays a full game, hides other hands, persists coins and updates stats', async () => {
    const { auth } = await guest();
    const start = await app.inject({ method: 'POST', url: '/api/games', headers: auth, payload: {} });
    expect(start.statusCode).toBe(200);
    const first = start.json() as ActionResponse;
    expect(first.steps[0]!.event.type).toBe('hand_start');
    expect(first.view.players[0]!.name).toMatch(/^訪客/);
    expect(first.view.players.slice(1).map((p) => p.avatar)).toEqual(['bear', 'cat', 'rabbit']);

    const end = await playToEnd(auth, first);
    expect(end.hasResult).toBe(true);
    expect(end.result.gameOver).toBe(true);

    const me = (await app.inject({ method: 'GET', url: '/api/me', headers: auth })).json().player;
    expect(me.handsPlayed).toBe(end.handNo);
    expect(me.coins).toBe(20000 + end.players[0]!.sessionDelta);
    expect(end.myCoins).toBe(me.coins);
  });

  it('resumes the active game instead of starting another', async () => {
    const { auth } = await guest();
    const a = (await app.inject({ method: 'POST', url: '/api/games', headers: auth, payload: {} })).json();
    const b = (await app.inject({ method: 'POST', url: '/api/games', headers: auth, payload: {} })).json();
    expect(b.view.gameId).toBe(a.view.gameId);
    expect(b.steps).toEqual([]);
    const get = await app.inject({ method: 'GET', url: `/api/games/${a.view.gameId}`, headers: auth });
    expect(get.json().view.gameId).toBe(a.view.gameId);
  });

  it('rejects illegal actions and other players’ games', async () => {
    const me = await guest();
    const other = await guest();
    const start = (await app.inject({ method: 'POST', url: '/api/games', headers: me.auth, payload: {} })).json();
    const url = `/api/games/${start.view.gameId}/actions`;
    const illegal = await app.inject({ method: 'POST', url, headers: me.auth, payload: { actionId: 'discard:XX' } });
    expect(illegal.statusCode).toBe(400);
    expect(illegal.json().error.code).toBe('ILLEGAL_ACTION');
    const stolen = await app.inject({ method: 'POST', url, headers: other.auth, payload: { actionId: 'pass' } });
    expect(stolen.statusCode).toBe(404);
    const malformed = await app.inject({ method: 'POST', url, headers: me.auth, payload: { foo: 1 } });
    expect(malformed.statusCode).toBe(400);
  });
});
