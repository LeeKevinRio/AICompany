import type { FastifyInstance } from 'fastify';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/api/app.js';
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
    for (const nickname of ['', '   ', '一二三四五六七八九十一二三', 'a\u0000b', 'x'.repeat(100)]) {
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
